import os
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from flask import Flask, send_from_directory, Response, abort, jsonify, request
from services import mongo, gemini

ROOT = Path(__file__).parent.resolve()

app = Flask(__name__, static_folder=str(ROOT))


def load_dot_env(filepath: Path) -> dict:
    env = {}
    if not filepath.exists():
        return env
    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value
    return env


dot_env = load_dot_env(ROOT / ".env")

# Load env vars from .env into os.environ so services can read them
for k, v in dot_env.items():
    if not os.environ.get(k):
        os.environ[k] = v

GOOGLE_MAPS_API_KEY = (os.environ.get("GOOGLE_MAPS_API") or dot_env.get("GOOGLE_MAPS_API") or "").strip()
METERS_PER_MILE = 1609.344
MIN_RADIUS_MILES = 0.1
MAX_RADIUS_MILES = 50
DEFAULT_RESULT_LIMIT = 250
MAX_RESULT_LIMIT = 1600


def _to_float(value, field_name: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: expected number") from exc


def _to_int(value, field_name: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {field_name}: expected integer") from exc


def _parse_place_types(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        items = value
    else:
        items = str(value).split(",")
    return [str(item).strip() for item in items if str(item).strip()]


def _extract_coordinates(payload: dict):
    if payload.get("lat") is not None and payload.get("lng") is not None:
        return payload.get("lat"), payload.get("lng")
    pin = payload.get("pin")
    if isinstance(pin, dict) and pin.get("lat") is not None and pin.get("lng") is not None:
        return pin.get("lat"), pin.get("lng")
    coords = payload.get("coordinates")
    if isinstance(coords, dict) and coords.get("lat") is not None and coords.get("lng") is not None:
        return coords.get("lat"), coords.get("lng")
    return None, None


def _geocode_address(address: str) -> dict:
    if not GOOGLE_MAPS_API_KEY:
        raise RuntimeError("Address search unavailable: GOOGLE_MAPS_API is not configured")

    query = urlencode({"address": address, "key": GOOGLE_MAPS_API_KEY})
    url = f"https://maps.googleapis.com/maps/api/geocode/json?{query}"
    try:
        with urlopen(url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Google geocoding failed with HTTP {exc.code}") from exc
    except URLError as exc:
        raise RuntimeError("Google geocoding request failed") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError("Invalid geocoding response") from exc

    status = payload.get("status")
    if status != "OK" or not payload.get("results"):
        raise ValueError(f"Address could not be geocoded (status={status})")

    top = payload["results"][0]
    location = top.get("geometry", {}).get("location", {})
    lat = location.get("lat")
    lng = location.get("lng")
    if lat is None or lng is None:
        raise ValueError("Geocoding response missing coordinates")

    return {
        "lat": float(lat),
        "lng": float(lng),
        "formatted_address": top.get("formatted_address"),
        "place_id": top.get("place_id"),
    }


@app.route("/config.js")
def config_js():
    payload = f"window.APP_CONFIG = {json.dumps({'GOOGLE_MAPS_API_KEY': GOOGLE_MAPS_API_KEY})};"
    return Response(payload, content_type="application/javascript; charset=utf-8")


@app.route("/api/farmers-markets")
def farmers_markets():
    try:
        return jsonify(mongo.get_farmers_markets())
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/food-distributors")
def food_distributors():
    try:
        place_type = request.args.get("place_type")
        place_types = _parse_place_types(request.args.get("place_types"))
        neighborhood = request.args.get("neighborhood")
        search = request.args.get("search")
        sample_pct = request.args.get("sample_pct")
        limit = request.args.get("limit")

        sample_pct_value = _to_float(sample_pct, "sample_pct") if sample_pct is not None else None
        limit_value = _to_int(limit, "limit") if limit is not None else None
        if limit_value is not None and limit_value < 1:
            return jsonify({"error": "limit must be at least 1"}), 400

        return jsonify(
            mongo.get_food_distributors(
                place_type=place_type,
                place_types=place_types,
                neighborhood=neighborhood,
                search=search,
                sample_pct=sample_pct_value,
                limit=limit_value,
            )
        )
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/food-distributors/search-radius", methods=["GET", "POST"])
def food_distributors_search_radius():
    payload = request.get_json(silent=True) or {}
    if request.method == "GET":
        payload = {**request.args.to_dict(), **payload}

    address = str(payload.get("address", "")).strip()
    lat_raw, lng_raw = _extract_coordinates(payload)
    radius_raw = payload.get("radius_miles", MIN_RADIUS_MILES)
    limit_raw = payload.get("limit", DEFAULT_RESULT_LIMIT)

    try:
        radius_miles = _to_float(radius_raw, "radius_miles")
        if radius_miles < MIN_RADIUS_MILES:
            raise ValueError(f"radius_miles must be at least {MIN_RADIUS_MILES}")
        if radius_miles > MAX_RADIUS_MILES:
            raise ValueError(f"radius_miles must be at most {MAX_RADIUS_MILES}")

        limit = _to_int(limit_raw, "limit")
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if limit > MAX_RESULT_LIMIT:
            raise ValueError(f"limit must be at most {MAX_RESULT_LIMIT}")
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    geocode_meta = None
    search_source = "pin"
    try:
        if lat_raw is not None and lng_raw is not None:
            lat = _to_float(lat_raw, "lat")
            lng = _to_float(lng_raw, "lng")
        elif address:
            geocode_meta = _geocode_address(address)
            lat = geocode_meta["lat"]
            lng = geocode_meta["lng"]
            search_source = "address"
        else:
            return jsonify({"error": "Provide either address or coordinates (lat/lng or pin.lat/pin.lng)."}), 400
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 502

    if lat < -90 or lat > 90:
        return jsonify({"error": "Invalid lat: must be between -90 and 90"}), 400
    if lng < -180 or lng > 180:
        return jsonify({"error": "Invalid lng: must be between -180 and 180"}), 400

    place_type = request.args.get("place_type") if request.method == "GET" else payload.get("place_type")
    place_types_raw = request.args.get("place_types") if request.method == "GET" else payload.get("place_types")
    place_types = _parse_place_types(place_types_raw)
    neighborhood = request.args.get("neighborhood") if request.method == "GET" else payload.get("neighborhood")
    search = request.args.get("search") if request.method == "GET" else payload.get("search")

    try:
        results = mongo.search_food_distributors_by_radius(
            lat=lat,
            lng=lng,
            radius_miles=radius_miles,
            limit=limit,
            place_type=place_type,
            place_types=place_types,
            neighborhood=neighborhood,
            search=search,
        )
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503

    response = {
        "search_source": search_source,
        "search_center": {"lat": lat, "lng": lng},
        "radius_miles": radius_miles,
        "radius_meters": radius_miles * METERS_PER_MILE,
        "limit": limit,
        "count": len(results),
        "results": results,
    }
    if geocode_meta:
        response["geocode"] = {
            "formatted_address": geocode_meta.get("formatted_address"),
            "place_id": geocode_meta.get("place_id"),
        }
    return jsonify(response)


@app.route("/api/income-inequality")
def income_inequality():
    try:
        return jsonify(mongo.get_income_inequality())
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/neighborhood-stats")
def neighborhood_stats():
    city = (request.args.get("city") or "Boston").strip() or "Boston"
    collection_name = (request.args.get("collection") or "neighborhoods").strip() or "neighborhoods"
    include_meta_raw = (request.args.get("include_meta") or "1").strip().lower()
    include_meta = include_meta_raw not in {"0", "false", "no"}
    try:
        return jsonify(
            mongo.get_neighborhood_stats(
                city=city,
                collection_name=collection_name,
                include_meta=include_meta,
            )
        )
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/census-geographies")
def census_geographies():
    level = (request.args.get("level") or "tract").strip() or "tract"
    city_scope = (request.args.get("city_scope") or "Boston").strip() or "Boston"
    collection_name = (request.args.get("collection") or "census_geo_profiles").strip() or "census_geo_profiles"
    limit_raw = request.args.get("limit")
    vintage_raw = request.args.get("vintage")

    try:
        limit = _to_int(limit_raw, "limit") if limit_raw is not None else 5000
        if limit < 1:
            return jsonify({"error": "limit must be at least 1"}), 400

        vintage = _to_int(vintage_raw, "vintage") if vintage_raw is not None else None
        rows = mongo.get_census_geographies(
            level=level,
            city_scope=city_scope,
            vintage=vintage,
            limit=limit,
            collection_name=collection_name,
        )
        return jsonify(rows)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/neighborhood-metrics")
def neighborhood_metrics():
    neighborhood = (request.args.get("name") or request.args.get("neighborhood") or "").strip()
    if not neighborhood:
        return jsonify({"error": "name (or neighborhood) query parameter is required"}), 400

    try:
        return jsonify(mongo.get_neighborhood_metrics(neighborhood))
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/citywide-averages")
def citywide_averages():
    try:
        return jsonify(mongo.get_citywide_food_averages())
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


@app.route("/api/gemini/parse-search", methods=["POST"])
def gemini_parse_search():
    body = request.get_json(silent=True) or {}
    query = str(body.get("query", "")).strip()
    if not query:
        return jsonify({"error": "query is required"}), 400
    try:
        result = gemini.parse_search_query(query)
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503
    except Exception as e:
        msg = str(e)
        if "429" in msg or "quota" in msg.lower() or "exhausted" in msg.lower():
            return jsonify({"error": "Gemini API rate limit reached. Please try again tomorrow or upgrade your API plan."}), 429
        return jsonify({"error": f"Gemini error: {msg}"}), 503


@app.route("/api/gemini", methods=["POST"])
def gemini_ask():
    body = request.get_json(silent=True) or {}
    neighborhood = body.get("neighborhood", "")
    context = body.get("context", {})
    if not neighborhood:
        return jsonify({"error": "neighborhood is required"}), 400
    try:
        answer = gemini.ask_about_neighborhood(neighborhood, context)
        return jsonify({"response": answer})
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 503


_mbta_stops_cache = None
_mbta_routes_cache = None

MBTA_ROUTE_COLORS = {
    "Red": "#DA291C",
    "Orange": "#ED8B00",
    "Blue": "#003DA5",
    "Green-B": "#00843D",
    "Green-C": "#00843D",
    "Green-D": "#00843D",
    "Green-E": "#00843D",
    "Mattapan": "#DA291C",
}

@app.route("/api/mbta-routes")
def mbta_routes():
    global _mbta_routes_cache
    if _mbta_routes_cache is not None:
        return jsonify(_mbta_routes_cache)
    try:
        from urllib.request import Request as URLRequest
        subway_routes = ["Red", "Orange", "Blue", "Green-B", "Green-C", "Green-D", "Green-E", "Mattapan"]
        routes = []
        for route_id in subway_routes:
            color = MBTA_ROUTE_COLORS.get(route_id, "#888888")
            url = f"https://api-v3.mbta.com/shapes?filter[route]={route_id}&fields[shape]=polyline"
            req = URLRequest(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("data", []):
                polyline = item.get("attributes", {}).get("polyline")
                if polyline:
                    routes.append({"polyline": polyline, "color": color, "route": route_id})
        _mbta_routes_cache = routes
        return jsonify(routes)
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/mbta-stops")
def mbta_stops():
    global _mbta_stops_cache
    if _mbta_stops_cache is not None:
        return jsonify(_mbta_stops_cache)
    try:
        from urllib.request import Request as URLRequest
        subway_routes = ["Red", "Orange", "Blue", "Green-B", "Green-C", "Green-D", "Green-E", "Mattapan"]
        stop_map = {}  # stop_id -> stop dict with lines list
        for route_id in subway_routes:
            color = MBTA_ROUTE_COLORS.get(route_id, "#888888")
            line_name = route_id.split("-")[0]  # Green-B -> Green
            url = f"https://api-v3.mbta.com/stops?filter[route]={route_id}&fields[stop]=name,latitude,longitude,municipality"
            req = URLRequest(url, headers={"Accept": "application/json"})
            with urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            for item in data.get("data", []):
                attrs = item.get("attributes", {})
                lat = attrs.get("latitude")
                lng = attrs.get("longitude")
                if lat is None or lng is None:
                    continue
                stop_id = item.get("id")
                if stop_id not in stop_map:
                    stop_map[stop_id] = {
                        "id": stop_id,
                        "name": attrs.get("name"),
                        "lat": lat,
                        "lng": lng,
                        "municipality": attrs.get("municipality"),
                        "lines": [],
                        "colors": [],
                    }
                if line_name not in stop_map[stop_id]["lines"]:
                    stop_map[stop_id]["lines"].append(line_name)
                    stop_map[stop_id]["colors"].append(color)
        stops = list(stop_map.values())
        _mbta_stops_cache = stops
        return jsonify(stops)
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.route("/api/tts", methods=["POST"])
def text_to_speech():
    api_key = os.environ.get("ELEVENLABS_API_KEY", "")
    if not api_key:
        return jsonify({"error": "ElevenLabs API key not configured"}), 503

    body = request.get_json(silent=True) or {}
    text = str(body.get("text", "")).strip()
    lang = str(body.get("lang", "en")).strip()

    if not text:
        return jsonify({"error": "text is required"}), 400

    # Use a different voice for Spanish vs English
    voice_id = "EXAVITQu4vr4xnSDxMaL" if lang == "es" else "JBFqnCBsd6RMkjVDRZzb"

    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    payload = json.dumps({
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }).encode("utf-8")

    req_headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    try:
        import urllib.request as urlreq
        req = urlreq.Request(url, data=payload, headers=req_headers, method="POST")
        with urlreq.urlopen(req, timeout=15) as resp:
            audio_data = resp.read()
        return Response(audio_data, content_type="audio/mpeg")
    except HTTPError as e:
        return jsonify({"error": f"ElevenLabs error: {e.code}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 502


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return e


@app.errorhandler(500)
def internal_error(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Internal server error"}), 500
    return e


@app.route("/", defaults={"req_path": ""})
@app.route("/<path:req_path>")
def serve_static(req_path: str):
    if not req_path:
        req_path = "index.html"

    try:
        target = (ROOT / req_path).resolve()
        target.relative_to(ROOT)
    except ValueError:
        abort(403)

    if not target.exists():
        abort(404)

    return send_from_directory(str(ROOT), req_path)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print(f"Boston map app running at http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=True)
