import os
import csv
import re
from pathlib import Path
from datetime import datetime
from pymongo import MongoClient, GEOSPHERE

_client = None
_db = None
_geo_index_ready = False
_population_lookup = None
_citywide_gini_from_csv = None

METERS_PER_MILE = 1609.344


def _normalize_neighborhood_name(value):
    text = str(value or "").strip().lower()
    return re.sub(r"\s+", " ", text)


def _to_float_or_none(value):
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text.startswith('="') and text.endswith('"'):
        text = text[2:-1]
    text = text.strip('"')
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def _load_population_lookup():
    global _population_lookup
    if _population_lookup is not None:
        return _population_lookup

    lookup = {}
    base = Path(__file__).resolve().parents[1] / "data" / "cleaned_data"
    candidates = [
        base / "population_up.csv",
        base / "populated_up.csv",
        base / "population_updated.csv",
    ]

    for path in candidates:
        if not path.exists():
            continue
        with path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                name = (row.get("Neighborhood") or "").strip()
                pop_value = _to_float_or_none(row.get("Population"))
                if name and pop_value is not None:
                    lookup[_normalize_neighborhood_name(name)] = int(pop_value)
        break

    _population_lookup = lookup
    return _population_lookup


def _extract_gini(doc):
    for key in ("igini", "Gini Index of Income Inequality", "gini", "gini_index"):
        value = _to_float_or_none(doc.get(key))
        if value is not None:
            return value
    return None


def _avg(values):
    return (sum(values) / len(values)) if values else None


def _iso_or_none(value):
    if isinstance(value, datetime):
        return value.isoformat()
    if value is None:
        return None
    return str(value)


def _load_citywide_gini_from_csv():
    global _citywide_gini_from_csv
    if _citywide_gini_from_csv is not None:
        return _citywide_gini_from_csv

    path = Path(__file__).resolve().parents[1] / "data" / "Income_inequality_index_PolicyMap.csv"
    if not path.exists():
        _citywide_gini_from_csv = None
        return _citywide_gini_from_csv

    values = []
    with path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            # Skip alias/header row often present as first data row.
            if (row.get("Geography Type Description") or "").strip() == "GeoID_Description":
                continue
            gini_value = _extract_gini(row)
            if gini_value is not None:
                values.append(gini_value)

    _citywide_gini_from_csv = _avg(values)
    return _citywide_gini_from_csv


def get_db():
    global _client, _db, _geo_index_ready
    if _db is None:
        uri = os.environ.get("MONGO_CONNECTION", "")
        if not uri:
            raise RuntimeError("MONGO_CONNECTION not set")
        db_name = os.environ.get("MONGO_DB", "food-distributors")
        _client = MongoClient(uri)
        _db = _client[db_name]
    if not _geo_index_ready:
        # Required for geospatial queries like $near.
        try:
            _db["food-distributors"].create_index([("location", GEOSPHERE)])
            _geo_index_ready = True
        except Exception as exc:
            raise RuntimeError(f"Failed to ensure 2dsphere index on location: {exc}") from exc
    return _db


def _build_text_filters(query, place_type=None, place_types=None, neighborhood=None, search=None):
    if place_types:
        valid_types = [str(item).strip() for item in place_types if str(item).strip()]
        if valid_types:
            query["place_type"] = {"$in": valid_types}
    elif place_type:
        query["place_type"] = place_type
    if neighborhood:
        query["neighborhood_name"] = {"$regex": neighborhood, "$options": "i"}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"description": {"$regex": search, "$options": "i"}},
            {"neighborhood_name": {"$regex": search, "$options": "i"}},
        ]
    return query


def _serialize_doc(doc):
    coords = (doc.get("location") or {}).get("coordinates", [])
    return {
        "name": doc.get("name"),
        "address": (doc.get("address") or {}).get("formatted_address") or (doc.get("address") or {}).get("line1"),
        "city": (doc.get("address") or {}).get("city_norm"),
        "neighborhood": doc.get("neighborhood_name"),
        "description": doc.get("description"),
        "website": (doc.get("contact") or {}).get("website"),
        "phone": (doc.get("contact") or {}).get("phone"),
        "place_type": doc.get("place_type"),
        "subtype": doc.get("subtype"),
        "datatype": doc.get("datatype"),
        "lat": coords[1] if len(coords) >= 2 else None,
        "lng": coords[0] if len(coords) >= 2 else None,
    }


def get_food_distributors(place_type=None, place_types=None, neighborhood=None, search=None, sample_pct=None, limit=None):
    db = get_db()
    collection = db["food-distributors"]
    query = _build_text_filters(
        {},
        place_type=place_type,
        place_types=place_types,
        neighborhood=neighborhood,
        search=search,
    )
    docs = None

    if sample_pct is not None:
        pct = float(sample_pct)
        if pct <= 0 or pct > 1:
            raise ValueError("sample_pct must be > 0 and <= 1")
        total = collection.count_documents(query)
        sample_size = max(1, int(total * pct)) if total else 0
        if limit is not None:
            sample_size = min(sample_size, int(limit))
        if sample_size == 0:
            return []
        docs = collection.aggregate(
            [
                {"$match": query},
                {"$sample": {"size": sample_size}},
                {"$project": {"_id": 0}},
            ]
        )
    else:
        docs = collection.find(query, {"_id": 0})
        if limit is not None:
            docs = docs.limit(int(limit))

    return [_serialize_doc(doc) for doc in docs]


def search_food_distributors_by_radius(
    *,
    lat,
    lng,
    radius_miles,
    limit=250,
    place_type=None,
    place_types=None,
    neighborhood=None,
    search=None,
):
    db = get_db()
    max_distance_meters = float(radius_miles) * METERS_PER_MILE

    query = _build_text_filters(
        {
            "location": {
                "$near": {
                    "$geometry": {"type": "Point", "coordinates": [float(lng), float(lat)]},
                    "$maxDistance": max_distance_meters,
                }
            }
        },
        place_type=place_type,
        place_types=place_types,
        neighborhood=neighborhood,
        search=search,
    )

    docs = db["food-distributors"].find(query, {"_id": 0}).limit(int(limit))
    return [_serialize_doc(doc) for doc in docs]


def get_farmers_markets():
    return get_food_distributors(place_type="farmers_market")


def get_income_inequality():
    db = get_db()
    return list(db["income_inequality"].find({}, {"_id": 0})) if "income_inequality" in db.list_collection_names() else []


def get_citywide_food_averages():
    """
    Returns per-1k food access averages across all Boston neighborhoods,
    plus per-neighborhood per-1k data for line chart comparison.
    """
    db = get_db()
    population_lookup = _load_population_lookup()

    # Aggregate counts per neighborhood per place_type
    pipeline = [
        {"$group": {"_id": {"neighborhood": "$neighborhood_name", "type": "$place_type"}, "count": {"$sum": 1}}},
    ]
    rows = list(db["food-distributors"].aggregate(pipeline))

    # Build a dict: neighborhood -> {place_type: count}
    nbhd_counts = {}
    for row in rows:
        nbhd = (row["_id"].get("neighborhood") or "").strip()
        ptype = row["_id"].get("type") or "other"
        if not nbhd:
            continue
        if nbhd not in nbhd_counts:
            nbhd_counts[nbhd] = {"restaurant": 0, "grocery_store": 0, "farmers_market": 0, "food_pantry": 0}
        if ptype in nbhd_counts[nbhd]:
            nbhd_counts[nbhd][ptype] += int(row["count"])

    # Compute per-1k for each neighborhood
    KEYS = ["restaurant", "grocery_store", "farmers_market", "food_pantry"]
    per_1k_by_nbhd = {}
    for nbhd, counts in nbhd_counts.items():
        pop = population_lookup.get(_normalize_neighborhood_name(nbhd))
        if not pop or pop <= 0:
            continue
        per_1k_by_nbhd[nbhd] = {k: round((counts[k] / pop) * 1000, 3) for k in KEYS}

    # Citywide averages
    citywide = {}
    for k in KEYS:
        vals = [v[k] for v in per_1k_by_nbhd.values() if v[k] is not None]
        citywide[k] = round(_avg(vals), 3) if vals else None

    # Line-chart series: one entry per neighborhood, sorted by restaurant per-1k
    series = [
        {"neighborhood": nbhd, **vals}
        for nbhd, vals in per_1k_by_nbhd.items()
    ]
    series.sort(key=lambda x: x.get("restaurant") or 0, reverse=True)

    return {
        "citywide_avg_per_1000": {
            "restaurants": citywide["restaurant"],
            "grocery_stores": citywide["grocery_store"],
            "farmers_markets": citywide["farmers_market"],
            "food_pantries": citywide["food_pantry"],
        },
        "neighborhoods": series,
    }


def get_neighborhood_stats(city="Boston", collection_name="neighborhoods", include_meta=True):
    """
    Return neighborhood display stats in the shape expected by /api/neighborhood-stats:
    [{ name, poverty_rate, gini_index }, ...]

    poverty_rate is normalized to 0..1 for UI compatibility.
    """
    db = get_db()
    collection_names = set(db.list_collection_names())

    if collection_name in collection_names:
        query = {}
        if city:
            query["city"] = {"$regex": f"^{re.escape(str(city).strip())}$", "$options": "i"}

        projection = {
            "_id": 0,
            "name": 1,
            "gini_index": 1,
            "source": 1,
            "source_file": 1,
            "updated_at": 1,
            "last_updated": 1,
            "confidence": 1,
            "completeness": 1,
        }
        rows = []
        for doc in db[collection_name].find(query, projection):
            name = str(doc.get("name") or "").strip()
            gini_value = _to_float_or_none(doc.get("gini_index"))
            if not name or gini_value is None:
                continue

            # Seed CSV commonly stores percentages (e.g. 23.1). UI expects 0..1.
            normalized = gini_value / 100.0 if gini_value > 1 else gini_value
            row = {"name": name, "poverty_rate": normalized, "gini_index": gini_value}
            if include_meta:
                source = doc.get("source")
                if not source:
                    source = {
                        "provider": "Local seeded neighborhood dataset",
                        "dataset": doc.get("source_file") or "unknown",
                    }
                row["source"] = source
                row["last_updated"] = _iso_or_none(doc.get("last_updated") or doc.get("updated_at"))
                row["confidence"] = doc.get("confidence")
                row["completeness"] = doc.get("completeness")
            rows.append(row)

        rows.sort(key=lambda x: x["name"])
        return rows

    # Fallback to legacy socioeconomic CSV when neighborhoods is unavailable.
    csv_path = Path(__file__).resolve().parents[1] / "data" / "boston_neighborhood_socioeconomic_clean.csv"
    if not csv_path.exists():
        return []

    results = []
    with csv_path.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            try:
                pop = float(row["total_population"])
                below_pov = float(row["population_below_poverty"])
                poverty_rate = round(below_pov / pop, 4) if pop > 0 else 0
                item = {"name": row["name"], "poverty_rate": poverty_rate, "gini_index": None}
                if include_meta:
                    item["source"] = {
                        "provider": "Local fallback CSV",
                        "dataset": csv_path.name,
                    }
                    item["last_updated"] = None
                    item["confidence"] = None
                    item["completeness"] = None
                results.append(item)
            except (ValueError, KeyError):
                continue

    results.sort(key=lambda x: x["name"])
    return results


def get_census_geographies(
    *,
    level="tract",
    city_scope="Boston",
    vintage=None,
    limit=5000,
    collection_name="census_geo_profiles",
):
    db = get_db()
    collection_names = set(db.list_collection_names())
    if collection_name not in collection_names:
        return []

    if level not in {"tract", "block_group"}:
        raise ValueError("level must be 'tract' or 'block_group'")

    query = {"geo_level": level}
    if city_scope:
        query["city_scope"] = {"$regex": f"^{re.escape(str(city_scope).strip())}$", "$options": "i"}
    if vintage is not None:
        query["vintage"] = int(vintage)

    projection = {
        "_id": 0,
        "geoid": 1,
        "geo_level": 1,
        "name": 1,
        "state_fips": 1,
        "county_fips": 1,
        "tract_code": 1,
        "block_group_code": 1,
        "city_scope": 1,
        "vintage": 1,
        "metrics": 1,
        "source": 1,
        "last_updated": 1,
        "confidence": 1,
        "completeness": 1,
    }

    cursor = db[collection_name].find(query, projection).sort("geoid", 1)
    if limit is not None:
        cursor = cursor.limit(int(limit))

    rows = []
    for doc in cursor:
        item = dict(doc)
        item["last_updated"] = _iso_or_none(doc.get("last_updated"))
        rows.append(item)

    return rows


def get_neighborhood_metrics(neighborhood_name):
    db = get_db()
    normalized_name = _normalize_neighborhood_name(neighborhood_name)
    escaped_name = re.escape(str(neighborhood_name or "").strip())

    place_type_counts = {
        "restaurant": 0,
        "grocery_store": 0,
        "farmers_market": 0,
        "food_pantry": 0,
        "other": 0,
    }

    match_query = {
        "neighborhood_name": {
            "$regex": f"^{escaped_name}$",
            "$options": "i",
        }
    }

    grouped = db["food-distributors"].aggregate(
        [
            {"$match": match_query},
            {"$group": {"_id": "$place_type", "count": {"$sum": 1}}},
        ]
    )

    for item in grouped:
        place_type = item.get("_id")
        count = int(item.get("count", 0) or 0)
        if place_type in place_type_counts:
            place_type_counts[place_type] = count
        else:
            place_type_counts["other"] += count

    total_access_points = sum(place_type_counts.values())

    population = _load_population_lookup().get(normalized_name)
    per_habitant = {}
    per_1000 = {}
    keys = ["restaurant", "grocery_store", "farmers_market", "food_pantry", "other", "total_access_points"]
    for key in keys:
        value = total_access_points if key == "total_access_points" else place_type_counts[key]
        if population and population > 0:
            per_habitant[key] = value / population
            per_1000[key] = (value / population) * 1000
        else:
            per_habitant[key] = None
            per_1000[key] = None

    neighborhood_gini_values = []
    citywide_gini_values = []
    if "income_inequality" in db.list_collection_names():
        projection = {
            "_id": 0,
            "igini": 1,
            "Gini Index of Income Inequality": 1,
            "gini": 1,
            "gini_index": 1,
            "neighborhood_name": 1,
            "Neighborhood": 1,
            "neighborhood": 1,
            "area_name": 1,
        }
        for doc in db["income_inequality"].find({}, projection):
            gini_value = _extract_gini(doc)
            if gini_value is None:
                continue
            citywide_gini_values.append(gini_value)

            raw_neighborhood = (
                doc.get("neighborhood_name")
                or doc.get("Neighborhood")
                or doc.get("neighborhood")
                or doc.get("area_name")
            )
            if raw_neighborhood and _normalize_neighborhood_name(raw_neighborhood) == normalized_name:
                neighborhood_gini_values.append(gini_value)

    citywide_gini_avg = _avg(citywide_gini_values)
    if citywide_gini_avg is None:
        citywide_gini_avg = _load_citywide_gini_from_csv()

    return {
        "neighborhood": neighborhood_name,
        "population": population,
        "counts": {
            "restaurants": place_type_counts["restaurant"],
            "grocery_stores": place_type_counts["grocery_store"],
            "farmers_markets": place_type_counts["farmers_market"],
            "food_pantries": place_type_counts["food_pantry"],
            "other": place_type_counts["other"],
        },
        "totals": {
            "access_points": total_access_points,
        },
        "per_habitant": {
            "restaurants": per_habitant["restaurant"],
            "grocery_stores": per_habitant["grocery_store"],
            "farmers_markets": per_habitant["farmers_market"],
            "food_pantries": per_habitant["food_pantry"],
            "other": per_habitant["other"],
            "access_points": per_habitant["total_access_points"],
        },
        "per_1000": {
            "restaurants": per_1000["restaurant"],
            "grocery_stores": per_1000["grocery_store"],
            "farmers_markets": per_1000["farmers_market"],
            "food_pantries": per_1000["food_pantry"],
            "other": per_1000["other"],
            "access_points": per_1000["total_access_points"],
        },
        "income": {
            "avg_gini_for_neighborhood": _avg(neighborhood_gini_values),
            "avg_gini_citywide": citywide_gini_avg,
            "note": "Neighborhood Gini available only if neighborhood-mapped income rows exist; otherwise citywide average is provided.",
        },
    }
