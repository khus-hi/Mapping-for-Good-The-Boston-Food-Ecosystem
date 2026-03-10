import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

from .mongo import get_db

FOOD_COLLECTION = "food-distributors"
NEIGHBORHOOD_COLLECTION = "neighboorhoods"

ZOOM_AGG_MAX = 12
ZOOM_CLUSTER_MAX = 15
ZOOM_POINT_MIN = 16

# Prevent oversized point payloads at street zoom.
MAX_POINT_RESULTS = 6000


def _safe_coords(doc: dict[str, Any]) -> tuple[float | None, float | None]:
    coords = (doc.get("location") or {}).get("coordinates") or []
    if len(coords) < 2:
        return None, None
    try:
        lng = float(coords[0])
        lat = float(coords[1])
        return lat, lng
    except (TypeError, ValueError):
        return None, None


def _cluster_cell_size_degrees(zoom: int) -> float:
    # Tuneable grid size: lower zoom => larger cells, higher zoom => finer cells.
    base = 0.35 / (2 ** max(0, int(zoom) - 8))
    return max(0.0015, min(base, 0.2))


def _cluster_key(lat: float, lng: float, cell_size: float) -> tuple[int, int]:
    return (
        int(math.floor((lat + 90.0) / cell_size)),
        int(math.floor((lng + 180.0) / cell_size)),
    )


def _build_bbox_query(sw_lat: float, sw_lng: float, ne_lat: float, ne_lng: float) -> dict[str, Any]:
    min_lat = min(sw_lat, ne_lat)
    max_lat = max(sw_lat, ne_lat)

    # Handle antimeridian crossing defensively even though Boston use-cases won't hit it.
    if sw_lng <= ne_lng:
        return {
            "location": {
                "$geoWithin": {
                    "$box": [
                        [float(sw_lng), float(min_lat)],
                        [float(ne_lng), float(max_lat)],
                    ]
                }
            }
        }

    return {
        "$or": [
            {
                "location": {
                    "$geoWithin": {
                        "$box": [[float(sw_lng), float(min_lat)], [180.0, float(max_lat)]]
                    }
                }
            },
            {
                "location": {
                    "$geoWithin": {
                        "$box": [[-180.0, float(min_lat)], [float(ne_lng), float(max_lat)]]
                    }
                }
            },
        ]
    }


def _serialize_point(doc: dict[str, Any]) -> dict[str, Any] | None:
    lat, lng = _safe_coords(doc)
    if lat is None or lng is None:
        return None

    return {
        "type": "point",
        "_id": str(doc.get("_id")),
        "name": doc.get("name"),
        "place_type": doc.get("place_type"),
        "subtype": doc.get("subtype"),
        "location": {"type": "Point", "coordinates": [lng, lat]},
        "neighborhood_id": doc.get("neighborhood_id"),
        "open_now": doc.get("open_now"),
        "business_status": doc.get("business_status"),
    }


def _cluster_docs(docs: list[dict[str, Any]], zoom: int) -> list[dict[str, Any]]:
    cell_size = _cluster_cell_size_degrees(zoom)
    buckets: dict[tuple[int, int], dict[str, Any]] = {}

    for doc in docs:
        lat, lng = _safe_coords(doc)
        if lat is None or lng is None:
            continue

        key = _cluster_key(lat, lng, cell_size)
        bucket = buckets.setdefault(
            key,
            {
                "sum_lat": 0.0,
                "sum_lng": 0.0,
                "count": 0,
                "counts_by_place_type": defaultdict(int),
            },
        )

        bucket["sum_lat"] += lat
        bucket["sum_lng"] += lng
        bucket["count"] += 1
        place_type = str(doc.get("place_type") or "unknown")
        bucket["counts_by_place_type"][place_type] += 1

    clusters = []
    for (y_idx, x_idx), bucket in buckets.items():
        count = bucket["count"]
        if count <= 0:
            continue
        centroid_lat = bucket["sum_lat"] / count
        centroid_lng = bucket["sum_lng"] / count
        clusters.append(
            {
                "type": "cluster",
                "id": f"{zoom}:{y_idx}:{x_idx}",
                "coordinates": [centroid_lng, centroid_lat],
                "count": int(count),
                "counts_by_place_type": dict(bucket["counts_by_place_type"]),
            }
        )

    clusters.sort(key=lambda c: c["count"], reverse=True)
    return clusters


def get_neighborhood_stats(city: str = "Boston", include_geometry: bool = True) -> list[dict[str, Any]]:
    db = get_db()
    collection_names = set(db.list_collection_names())

    if NEIGHBORHOOD_COLLECTION in collection_names:
        projection = {
            "_id": 0,
            "neighborhood_id": 1,
            "name": 1,
            "city": 1,
            "stats": 1,
            "population": 1,
        }
        if include_geometry:
            projection["geometry"] = 1

        query: dict[str, Any] = {}
        if city:
            query["city"] = {"$regex": f"^{city}$", "$options": "i"}

        rows = list(collection_names and db[NEIGHBORHOOD_COLLECTION].find(query, projection))
        rows.sort(key=lambda x: str(x.get("name") or ""))
        return rows

    # Fallback when neighborhoods collection is missing: derive names/geometry from GeoJSON + zero stats.
    geojson_path = Path(__file__).resolve().parents[1] / "data" / "boston_neighborhood_boundaries.geojson"
    if not geojson_path.exists():
        return []

    data = json.loads(geojson_path.read_text(encoding="utf-8"))
    features = data.get("features") or []

    stats_lookup: dict[str, dict[str, int]] = {}
    if FOOD_COLLECTION in collection_names:
        grouped = db[FOOD_COLLECTION].aggregate(
            [
                {"$match": {"neighborhood_name": {"$ne": None}}},
                {
                    "$group": {
                        "_id": {"name": "$neighborhood_name", "place_type": "$place_type"},
                        "count": {"$sum": 1},
                    }
                },
            ]
        )
        for row in grouped:
            group = row.get("_id") or {}
            name = str(group.get("name") or "").strip()
            if not name:
                continue
            counts = stats_lookup.setdefault(
                name,
                {
                    "farmers_market_count": 0,
                    "grocery_count": 0,
                    "food_pantry_count": 0,
                    "restaurant_count": 0,
                },
            )
            place_type = str(group.get("place_type") or "").strip()
            value = int(row.get("count") or 0)
            if place_type == "farmers_market":
                counts["farmers_market_count"] += value
            elif place_type == "grocery_store":
                counts["grocery_count"] += value
            elif place_type == "food_pantry":
                counts["food_pantry_count"] += value
            elif place_type == "restaurant":
                counts["restaurant_count"] += value

    out: list[dict[str, Any]] = []
    for idx, feature in enumerate(features, start=1):
        props = feature.get("properties") or {}
        name = str(props.get("name") or "").strip()
        if not name:
            continue
        doc = {
            "neighborhood_id": idx,
            "name": name,
            "city": city,
            "population": None,
            "stats": stats_lookup.get(
                name,
                {
                    "farmers_market_count": 0,
                    "grocery_count": 0,
                    "food_pantry_count": 0,
                    "restaurant_count": 0,
                },
            ),
        }
        if include_geometry:
            doc["geometry"] = feature.get("geometry")
        out.append(doc)

    out.sort(key=lambda x: str(x.get("name") or ""))
    return out


def get_food_units_for_viewport(
    *,
    sw_lat: float,
    sw_lng: float,
    ne_lat: float,
    ne_lng: float,
    zoom: int,
    place_type: str | None = None,
) -> dict[str, Any]:
    db = get_db()
    collection = db[FOOD_COLLECTION]

    query = _build_bbox_query(sw_lat, sw_lng, ne_lat, ne_lng)
    if place_type:
        query["place_type"] = place_type

    projection = {
        "_id": 1,
        "name": 1,
        "place_type": 1,
        "subtype": 1,
        "location": 1,
        "neighborhood_id": 1,
        "open_now": 1,
        "business_status": 1,
    }

    if zoom >= ZOOM_POINT_MIN:
        docs = list(collection.find(query, projection).limit(MAX_POINT_RESULTS))
        points = [p for p in (_serialize_point(doc) for doc in docs) if p is not None]
        return {
            "mode": "points",
            "zoom": int(zoom),
            "count": len(points),
            "items": points,
            "truncated": len(points) >= MAX_POINT_RESULTS,
        }

    docs = list(collection.find(query, projection))
    clusters = _cluster_docs(docs, zoom)
    return {
        "mode": "clusters",
        "zoom": int(zoom),
        "count": len(clusters),
        "total_points": len(docs),
        "items": clusters,
    }
