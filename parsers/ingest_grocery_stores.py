#!/usr/bin/env python3
"""Ingest grocery stores CSV into MongoDB using normalized food unit schema."""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pymongo import MongoClient
from pymongo.collection import Collection

from parsers.ingest_farmers_markets import (
    GEOCODE_CACHE_COLLECTION,
    STORE_MODE_COORDS,
    STORE_MODE_PLACE_ID_ONLY,
    RateLimiter,
    apply_geocode_to_doc,
    build_geocode_query,
    clean_text,
    collapse_spaces,
    geocode_address,
    get_field,
    normalize_zip,
    sha256_hash,
    title_case_city,
)
from parsers.neighborhood_mapper import NeighborhoodMapper, assign_neighborhood

SOURCE_NAME = "BostonGroceryStores"
SOURCE_FILE = "grocery_store_locations_clean.csv"
DEFAULT_INPUT = "data/cleaned_data/grocery_store_locations_clean.csv"
DEFAULT_REJECTS = "data/rejects/grocery_stores_rejects.json"
DEFAULT_DB = "food-distributors"
DEFAULT_COLLECTION = "food-distributors"

LOGGER = logging.getLogger("grocery_stores_ingest")


class ValidationError(Exception):
    """Raised when a row cannot be normalized."""


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def load_csv(path: Path, limit: int | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if limit is not None and limit > 0:
        return df.head(limit)
    return df


def resolve_input_path(cli_path: str) -> Path:
    candidate = Path(cli_path)
    if candidate.exists():
        return candidate

    fallbacks = [
        Path("data/cleaned_data/grocery_store_locations_clean.csv"),
        Path("data/cleaned_data/grocery_stores_cleaned.csv"),
        Path("data/grocery_store_locations_clean.csv"),
        Path("data/grocery_stores_cleaned.csv"),
    ]
    for fallback in fallbacks:
        if fallback.exists():
            LOGGER.info("Input not found at %s; using fallback %s", cli_path, fallback)
            return fallback

    raise FileNotFoundError(f"Input file not found: {cli_path}")


def normalize_city(value: Any) -> tuple[str | None, str | None]:
    city_raw = clean_text(value)
    if not city_raw:
        return None, None
    cleaned = collapse_spaces(city_raw.rstrip("/").strip())
    if not cleaned:
        return None, None
    return cleaned, title_case_city(cleaned)


def parse_float(value: Any) -> float | None:
    text = clean_text(value)
    if not text:
        return None
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def derive_subtype(store_type: str | None) -> str:
    text = (store_type or "").strip().lower()
    if not text:
        return "grocery_store"
    text = text.replace("&", " and ")
    subtype = re.sub(r"[^a-z0-9]+", "_", text).strip("_")
    return subtype or "grocery_store"


def source_prefix() -> str:
    return re.sub(r"[^a-z0-9]+", "", SOURCE_NAME.lower())


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = {k: (None if pd.isna(v) else v) for k, v in row.items()}

    name = clean_text(get_field(row, "Store Name", "Name"))
    line1 = clean_text(get_field(row, "Address", "Street Address", "Street"))
    city_raw, city_norm = normalize_city(get_field(row, "City", "Town"))
    state = (clean_text(get_field(row, "State")) or "MA").upper()
    zip_code = normalize_zip(get_field(row, "Zip", "ZIP", "Zip Code", "Postal Code"))
    county = clean_text(get_field(row, "County"))
    store_type = clean_text(get_field(row, "Store Type", "Type"))
    lat = parse_float(get_field(row, "Latitude", "Lat", "latitude", "lat"))
    lng = parse_float(get_field(row, "Longitude", "Lng", "Long", "Lon", "longitude", "lng"))

    if not name:
        raise ValidationError("missing required field: name")
    if not line1:
        raise ValidationError("missing required field: address.line1")
    line1 = collapse_spaces(line1)

    city_for_key = city_norm or city_raw or "boston"
    zip_for_key = zip_code or ""
    dedupe_hash = sha256_hash(SOURCE_NAME, name, line1, city_for_key, state, zip_for_key)
    dedupe_key = f"{source_prefix()}:{dedupe_hash}"
    source_row_hash = sha256_hash(SOURCE_NAME, name, line1, city_raw or "", state, zip_for_key)

    has_coords = lat is not None and lng is not None
    description = store_type or county

    if has_coords:
        geocoding = {
            "provider": "source_csv",
            "status": "SOURCE_COORDINATES",
            "place_id": None,
            "location_type": None,
            "partial_match": None,
            "confidence": "high",
        }
    else:
        geocoding = {
            "provider": "google",
            "status": "NOT_REQUESTED",
            "place_id": None,
            "location_type": None,
            "partial_match": None,
            "confidence": None,
        }

    return {
        "dedupe_key": dedupe_key,
        "name": name,
        "datatype": "grocery store",
        "place_type": "grocery_store",
        "subtype": derive_subtype(store_type),
        "description": description,
        "address": {
            "line1": line1,
            "city_raw": city_raw,
            "city_norm": city_norm,
            "state": state,
            "zip": zip_code,
            "formatted_address": None,
        },
        "location": {"type": "Point", "coordinates": [lng, lat]} if has_coords else None,
        "geocoding": geocoding,
        "contact": {
            "website": None,
            "phone": None,
        },
        "neighborhood_id": None,
        "neighborhood_name": None,
        "sources": [
            {
                "source_name": SOURCE_NAME,
                "source_file": SOURCE_FILE,
                "source_row_hash": source_row_hash,
                "needs_geocoding": not has_coords,
                "raw": raw,
            }
        ],
    }


def infer_schema(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: infer_schema(v) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return []
        return [infer_schema(value[0])]
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, str):
        return "string"
    return type(value).__name__


def upsert_unit(collection: Collection, doc: dict[str, Any]) -> str:
    now = datetime.now(timezone.utc)
    update = {
        "$set": {
            "dedupe_key": doc["dedupe_key"],
            "name": doc["name"],
            "datatype": doc["datatype"],
            "place_type": doc["place_type"],
            "subtype": doc["subtype"],
            "description": doc["description"],
            "address": doc["address"],
            "location": doc["location"],
            "geocoding": doc["geocoding"],
            "contact": doc["contact"],
            "neighborhood_id": doc["neighborhood_id"],
            "neighborhood_name": doc["neighborhood_name"],
            "sources": doc["sources"],
            "updated_at": now,
        },
        "$setOnInsert": {"created_at": now},
    }
    result = collection.update_one({"dedupe_key": doc["dedupe_key"]}, update, upsert=True)
    return "inserted" if result.upserted_id is not None else "updated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest grocery stores CSV into MongoDB")
    parser.add_argument("--input", default=DEFAULT_INPUT, help=f"CSV path (default: {DEFAULT_INPUT})")
    parser.add_argument("--dry-run", action="store_true", help="Parse but do not write MongoDB")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N rows")
    parser.add_argument("--max-qps", type=float, default=10.0, help="Max geocoding requests per second")
    parser.add_argument("--no-geocode", action="store_true", help="Skip geocoding when source coordinates are missing")
    parser.add_argument("--rejects", default=DEFAULT_REJECTS, help=f"Rejects JSON path (default: {DEFAULT_REJECTS})")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    mapper = NeighborhoodMapper()

    mongo_uri = os.getenv("MONGO_CONNECTION") or os.getenv("MONGO_URI")
    mongo_db = os.getenv("MONGO_DB", DEFAULT_DB)
    mongo_collection_name = os.getenv("MONGO_COLLECTION", DEFAULT_COLLECTION)
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    store_mode = os.getenv("GEOCODE_STORE_MODE", STORE_MODE_COORDS).strip().lower()
    if store_mode not in {STORE_MODE_COORDS, STORE_MODE_PLACE_ID_ONLY}:
        raise ValueError(
            f"Invalid GEOCODE_STORE_MODE={store_mode}; expected {STORE_MODE_COORDS} or {STORE_MODE_PLACE_ID_ONLY}"
        )

    input_path = resolve_input_path(args.input)
    rejects_path = Path(args.rejects)
    rejects_path.parent.mkdir(parents=True, exist_ok=True)

    client: MongoClient | None = None
    units_collection: Collection | None = None
    geocode_cache_collection: Collection | None = None

    if not args.dry_run:
        if not mongo_uri:
            raise EnvironmentError("MONGO_CONNECTION or MONGO_URI is required unless --dry-run is used")
        client = MongoClient(mongo_uri)
        db = client[mongo_db]
        units_collection = db[mongo_collection_name]
        geocode_cache_collection = db[GEOCODE_CACHE_COLLECTION]

    df = load_csv(input_path, limit=args.limit)

    if not args.no_geocode and not api_key:
        raise EnvironmentError("GOOGLE_MAPS_API_KEY is required unless --no-geocode is set")

    stats = {
        "rows_read": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "rows_rejected": 0,
        "rows_with_source_coords": 0,
        "rows_geocoded_ok": 0,
    }
    status_counts: Counter[str] = Counter()
    rejects: list[dict[str, Any]] = []
    sample_doc: dict[str, Any] | None = None
    limiter = RateLimiter(max_qps=args.max_qps)

    LOGGER.info(
        "Starting ingest input=%s rows=%s dry_run=%s no_geocode=%s max_qps=%s store_mode=%s",
        input_path,
        len(df.index),
        args.dry_run,
        args.no_geocode,
        args.max_qps,
        store_mode,
    )

    for idx, row in df.iterrows():
        stats["rows_read"] += 1
        row_dict = row.to_dict()
        line_no = idx + 2

        try:
            doc = normalize_row(row_dict)
        except ValidationError as exc:
            stats["rows_rejected"] += 1
            stats["rows_skipped"] += 1
            rejects.append({
                "csv_line_number": line_no,
                "reason": str(exc),
                "raw": {k: (None if pd.isna(v) else v) for k, v in row_dict.items()},
            })
            continue

        if doc["location"] is not None:
            stats["rows_with_source_coords"] += 1
        else:
            if args.no_geocode:
                doc["geocoding"] = {
                    "provider": "google",
                    "status": "SKIPPED_NO_GEOCODE",
                    "place_id": None,
                    "location_type": None,
                    "partial_match": None,
                    "confidence": None,
                }
                doc["sources"][0]["needs_geocoding"] = True
            else:
                query = build_geocode_query(doc)
                geocode_result = geocode_address(
                    query=query,
                    api_key=api_key or "",
                    limiter=limiter,
                    cache_collection=geocode_cache_collection,
                )
                apply_geocode_to_doc(doc, geocode_result, store_mode)
                if geocode_result.get("status") == "OK":
                    stats["rows_geocoded_ok"] += 1

        assign_neighborhood(doc, mapper)

        status_counts[doc["geocoding"]["status"]] += 1

        if args.dry_run and sample_doc is None:
            sample_doc = json.loads(json.dumps(doc, default=str))

        if args.dry_run:
            continue

        try:
            assert units_collection is not None
            outcome = upsert_unit(units_collection, doc)
            if outcome == "inserted":
                stats["rows_inserted"] += 1
            else:
                stats["rows_updated"] += 1
        except Exception as exc:  # pylint: disable=broad-except
            stats["rows_skipped"] += 1
            stats["rows_rejected"] += 1
            rejects.append({
                "csv_line_number": line_no,
                "reason": f"mongo_upsert_error: {exc}",
                "raw": doc["sources"][0]["raw"],
            })

    with rejects_path.open("w", encoding="utf-8") as fh:
        json.dump(rejects, fh, indent=2, ensure_ascii=False, default=str)

    LOGGER.info("rows read: %s", stats["rows_read"])
    LOGGER.info("rows with source coords: %s", stats["rows_with_source_coords"])
    LOGGER.info("rows geocoded OK: %s", stats["rows_geocoded_ok"])
    LOGGER.info("status counts: %s", dict(status_counts))
    LOGGER.info("inserted: %s", stats["rows_inserted"])
    LOGGER.info("updated: %s", stats["rows_updated"])
    LOGGER.info("skipped: %s", stats["rows_skipped"])
    LOGGER.info("rejected: %s", stats["rows_rejected"])
    LOGGER.info("rejects file: %s", rejects_path)

    if args.dry_run and sample_doc is not None:
        print("\nDry-run sample normalized document (pretty):")
        print(json.dumps(sample_doc, indent=2, ensure_ascii=False, default=str))
        print("\nDry-run inferred schema (pretty):")
        print(json.dumps(infer_schema(sample_doc), indent=2, ensure_ascii=False))

    collection_expr = (
        mongo_collection_name
        if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", mongo_collection_name)
        else f'getCollection("{mongo_collection_name}")'
    )

    print("\nRecommended MongoDB indexes:")
    print(f"1. db.{collection_expr}.createIndex({{ dedupe_key: 1 }}, {{ unique: true }})")
    print(f'2. db.{collection_expr}.createIndex({{ location: "2dsphere" }})')
    print(f"3. db.{collection_expr}.createIndex({{ datatype: 1, subtype: 1 }})")
    print("4. db.geocode_cache.createIndex({ geocode_query_hash: 1 }, { unique: true })")

    if client is not None:
        client.close()


if __name__ == "__main__":
    main()
