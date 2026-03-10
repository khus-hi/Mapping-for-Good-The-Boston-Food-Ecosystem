#!/usr/bin/env python3
"""
Seed neighborhood documents into MongoDB collection `neighborhoods`.

Usage:
  python scripts/seed_neighboorhoods.py
  python scripts/seed_neighboorhoods.py --dry-run
  python scripts/seed_neighboorhoods.py --drop
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_GEOJSON = ROOT / "data" / "boston_neighborhood_boundaries.geojson"
DEFAULT_SOCIO_CSV = ROOT / "data" / "boston_neighborhood_socioeconomic_clean.csv"
DEFAULT_COLLECTION = "neighborhoods"
DEFAULT_SECONDARY_COLLECTION = ""
FOOD_COLLECTION = "food-distributors"

INCOME_BUCKET_MIDPOINTS = {
    "households_income_lt_10k": 5_000,
    "households_income_10k_15k": 12_500,
    "households_income_15k_20k": 17_500,
    "households_income_20k_25k": 22_500,
    "households_income_25k_30k": 27_500,
    "households_income_30k_35k": 32_500,
    "households_income_35k_40k": 37_500,
    "households_income_40k_45k": 42_500,
    "households_income_45k_50k": 47_500,
    "households_income_50k_60k": 55_000,
    "households_income_60k_75k": 67_500,
    "households_income_75k_100k": 87_500,
    "households_income_100k_125k": 112_500,
    "households_income_125k_150k": 137_500,
    "households_income_150k_200k": 175_000,
    "households_income_200k_plus": 225_000,
}


def resolve_default_population_csv() -> Path:
    candidates = [
        ROOT / "data" / "cleaned_data" / "population_up.csv",
        ROOT / "data" / "cleaned_data" / "populated_up.csv",
        ROOT / "data" / "cleaned_data" / "population_updated.csv",
    ]
    for path in candidates:
        if path.exists():
            return path
    # Keep the first preferred path for error messages/CLI defaults when file is missing.
    return candidates[0]


DEFAULT_POPULATION_CSV = resolve_default_population_csv()


def load_dot_env(filepath: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not filepath.exists():
        return env
    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value
    return env


def canonicalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", str(value or "").lower()).strip()


def to_float_or_none(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace(",", "")
    if text.startswith('="') and text.endswith('"'):
        text = text[2:-1]
    text = text.strip('"')
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def to_int_or_none(value) -> int | None:
    number = to_float_or_none(value)
    if number is None:
        return None
    return int(round(number))


def load_population_rows(path: Path) -> dict[str, tuple[int, str, int | None, float | None]]:
    rows: dict[str, tuple[int, str, int | None, float | None]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        next_id = 1
        for row in reader:
            name = (row.get("Neighborhood") or "").strip()
            if not name:
                continue
            key = canonicalize_name(name)
            if key in rows:
                continue
            rows[key] = (
                next_id,
                name,
                to_int_or_none(row.get("Population")),
                to_float_or_none(row.get("gini_index")),
            )
            next_id += 1
    if not rows:
        raise ValueError(f"No neighborhoods found in {path}")
    return rows


def load_socioeconomic_income(path: Path) -> dict[str, int | None]:
    income_by_name: dict[str, int | None] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            name = (row.get("name") or "").strip()
            if not name:
                continue
            key = canonicalize_name(name)

            weighted_sum = 0.0
            weighted_count = 0.0
            for bucket, midpoint in INCOME_BUCKET_MIDPOINTS.items():
                count = to_float_or_none(row.get(bucket))
                if count is None or count <= 0:
                    continue
                weighted_sum += count * midpoint
                weighted_count += count

            income_by_name[key] = int(round(weighted_sum / weighted_count)) if weighted_count > 0 else None
    return income_by_name


def load_geo_features(path: Path) -> list[dict]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    features = obj.get("features")
    if not isinstance(features, list) or not features:
        raise ValueError(f"No features found in {path}")
    return features


def build_stats_lookup(collection) -> dict[int, dict[str, int]]:
    pipeline = [
        {"$match": {"neighborhood_id": {"$ne": None}}},
        {
            "$group": {
                "_id": {"neighborhood_id": "$neighborhood_id", "place_type": "$place_type"},
                "count": {"$sum": 1},
            }
        },
    ]

    stats_lookup: dict[int, dict[str, int]] = {}
    for row in collection.aggregate(pipeline):
        group = row.get("_id") or {}
        raw_neighborhood_id = group.get("neighborhood_id")
        try:
            neighborhood_id = int(raw_neighborhood_id)
        except (TypeError, ValueError):
            continue

        place_type = str(group.get("place_type") or "").strip().lower()
        count = int(row.get("count") or 0)

        entry = stats_lookup.setdefault(
            neighborhood_id,
            {
                "farmers_market_count": 0,
                "grocery_count": 0,
                "food_pantry_count": 0,
                "restaurant_count": 0,
            },
        )

        if place_type == "farmers_market":
            entry["farmers_market_count"] += count
        elif place_type == "grocery_store":
            entry["grocery_count"] += count
        elif place_type == "food_pantry":
            entry["food_pantry_count"] += count
        elif place_type == "restaurant":
            entry["restaurant_count"] += count

    return stats_lookup


def quality_label(score: float) -> str:
    if score >= 0.9:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


def build_neighborhood_quality(population, avg_household_income, gini_index, geometry) -> tuple[dict, dict]:
    checks = {
        "population": population is not None,
        "avg_household_income": avg_household_income is not None,
        "gini_index": gini_index is not None,
        "geometry": geometry is not None,
    }
    missing = [key for key, present in checks.items() if not present]
    score = (len(checks) - len(missing)) / len(checks)

    completeness = {
        "score": round(score, 3),
        "label": quality_label(score),
        "missing_fields": missing,
    }
    confidence = {
        "label": "high" if score >= 0.75 else "medium",
        "method": "Neighborhood canonical-name join across population/socioeconomic sources and boundary geometry.",
    }
    return confidence, completeness


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Seed neighborhoods collection")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Target neighborhoods collection name")
    parser.add_argument(
        "--secondary-collection",
        default=DEFAULT_SECONDARY_COLLECTION,
        help="Optional secondary neighborhoods collection name (empty means skip secondary write)",
    )
    parser.add_argument(
        "--no-secondary",
        action="store_true",
        help="Skip writing to secondary neighborhoods collection",
    )
    parser.add_argument("--city", default="Boston", help="City name to write on each neighborhood document")
    parser.add_argument("--drop", action="store_true", help="Drop target collection before writing")
    parser.add_argument("--dry-run", action="store_true", help="Build documents but do not write to MongoDB")
    parser.add_argument(
        "--skip-stats",
        action="store_true",
        help="Do not query food-distributors for cached stats; write zeros instead",
    )
    parser.add_argument("--geojson", default=str(DEFAULT_GEOJSON), help="Path to neighborhood GeoJSON")
    parser.add_argument("--population-csv", default=str(DEFAULT_POPULATION_CSV), help="Path to population CSV")
    parser.add_argument("--socio-csv", default=str(DEFAULT_SOCIO_CSV), help="Path to socioeconomic CSV")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    dot_env = load_dot_env(ROOT / ".env")

    mongo_uri = os.environ.get("MONGO_CONNECTION") or dot_env.get("MONGO_CONNECTION", "")
    mongo_db_name = os.environ.get("MONGO_DB") or dot_env.get("MONGO_DB", "food-distributors")

    population_rows = load_population_rows(Path(args.population_csv))
    socioeconomic_income = load_socioeconomic_income(Path(args.socio_csv))
    features = load_geo_features(Path(args.geojson))

    stats_lookup: dict[int, dict[str, int]] = {}
    if args.skip_stats:
        print("Skipping stats lookup (--skip-stats).")
    elif not mongo_uri:
        if args.dry_run:
            print("Warning: MONGO_CONNECTION not set; continuing dry-run with zero stats.")
        else:
            raise SystemExit("Error: MONGO_CONNECTION not set in environment or .env")
    else:
        try:
            client = MongoClient(mongo_uri)
            db = client[mongo_db_name]
            food_collection = db[FOOD_COLLECTION]
            stats_lookup = build_stats_lookup(food_collection)
        except Exception as exc:
            if args.dry_run:
                print(f"Warning: could not load cached stats ({exc}); continuing dry-run with zero stats.")
                stats_lookup = {}
            else:
                raise

    now = datetime.now(timezone.utc)
    docs = []

    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry")
        name = (props.get("name") or "").strip()
        if not name or not geometry:
            continue

        key = canonicalize_name(name)
        if key not in population_rows:
            continue

        legacy_id, canonical_name, population, gini_index = population_rows[key]
        avg_household_income = socioeconomic_income.get(key)
        confidence, completeness = build_neighborhood_quality(
            population=population,
            avg_household_income=avg_household_income,
            gini_index=gini_index,
            geometry=geometry,
        )

        docs.append(
            {
                "neighborhood_id": legacy_id,
                "name": canonical_name,
                "city": args.city,
                "population": population,
                "avg_household_income": avg_household_income,
                "gini_index": gini_index,
                "geometry": geometry,
                "stats": stats_lookup.get(
                    legacy_id,
                    {
                        "farmers_market_count": 0,
                        "grocery_count": 0,
                        "food_pantry_count": 0,
                        "restaurant_count": 0,
                    },
                ),
                "stats_updated_at": now,
                "source_file": Path(args.geojson).name,
                "source": {
                    "provider": "EquiTable Food Systems / local seed pipeline",
                    "dataset": "Boston neighborhood baseline",
                    "geojson_file": Path(args.geojson).name,
                    "population_file": Path(args.population_csv).name,
                    "socioeconomic_file": Path(args.socio_csv).name,
                    "ingestion_script": "scripts/seed_neighboorhoods.py",
                },
                "last_updated": now,
                "confidence": confidence,
                "completeness": completeness,
                "updated_at": now,
            }
        )

    docs.sort(key=lambda x: x["neighborhood_id"])

    print(f"Prepared {len(docs)} neighborhood documents for collection '{args.collection}'.")
    if docs:
        sample = docs[0].copy()
        sample.pop("geometry", None)
        print("Sample document (without geometry):")
        print(json.dumps(sample, default=str, indent=2))

    if args.dry_run:
        print("Dry-run mode enabled. No database writes executed.")
        return

    if not mongo_uri:
        raise SystemExit("Error: MONGO_CONNECTION not set in environment or .env")

    client = MongoClient(mongo_uri)
    db = client[mongo_db_name]
    target_collection = db[args.collection]

    if args.drop:
        target_collection.drop()
        print(f"Dropped collection '{args.collection}'.")

    upserts = 0
    for doc in docs:
        target_collection.update_one(
            {"neighborhood_id": doc["neighborhood_id"]},
            {"$set": doc},
            upsert=True,
        )
        upserts += 1

    target_collection.create_index("neighborhood_id", unique=True)
    try:
        target_collection.create_index([("geometry", "2dsphere")])
    except Exception as exc:
        print(f"Warning: could not create 2dsphere index on '{args.collection}': {exc}")
    print(f"Upserted {upserts} documents into '{args.collection}' in database '{mongo_db_name}'.")

    if not args.no_secondary:
        secondary_name = args.secondary_collection.strip()
        if secondary_name:
            secondary_collection = db[secondary_name]
            if args.drop and secondary_name != args.collection:
                secondary_collection.drop()
                print(f"Dropped collection '{secondary_name}'.")

            secondary_upserts = 0
            for doc in docs:
                secondary_doc = {k: v for k, v in doc.items() if k != "gini_index"}
                secondary_collection.update_one(
                    {"neighborhood_id": doc["neighborhood_id"]},
                    {
                        "$set": secondary_doc,
                        "$unset": {"gini_index": ""},
                    },
                    upsert=True,
                )
                secondary_upserts += 1

            secondary_collection.create_index("neighborhood_id", unique=True)
            try:
                secondary_collection.create_index([("geometry", "2dsphere")])
            except Exception as exc:
                print(f"Warning: could not create 2dsphere index on '{secondary_name}': {exc}")
            print(
                f"Upserted {secondary_upserts} documents into '{secondary_name}' "
                f"in database '{mongo_db_name}'."
            )


if __name__ == "__main__":
    main()
