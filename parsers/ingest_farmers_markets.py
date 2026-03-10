#!/usr/bin/env python3
"""Ingest MassGrown farmers markets CSV into MongoDB with Google geocoding."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pymongo import MongoClient
from pymongo.collection import Collection

from parsers.neighborhood_mapper import NeighborhoodMapper, assign_neighborhood

SOURCE_NAME = "MassGrown"
SOURCE_FILE = "farmers_market.csv"
DEFAULT_INPUT = "data/cleaned_data/farmers_market.csv"
DEFAULT_REJECTS = "data/rejects/farmers_market_rejects.json"
DEFAULT_DB = "food-distributors"
DEFAULT_COLLECTION = "food-distributors"
GEOCODE_CACHE_COLLECTION = "geocode_cache"

# Viewport bias around Greater Boston (bias only, not strict restriction).
BOSTON_BOUNDS = "42.20,-71.30|42.45,-70.95"

# Google allows indefinite storage of Place IDs; geocoded coordinates/formatted addresses
# may have storage/use restrictions depending on your terms. This mode allows choosing
# what is persisted in the main collection.
STORE_MODE_COORDS = "store_coords"
STORE_MODE_PLACE_ID_ONLY = "store_place_id_only"

LOGGER = logging.getLogger("farmers_market_ingest")


class ValidationError(Exception):
    """Raised when a row cannot be normalized."""


@dataclass
class RateLimiter:
    max_qps: float
    _last_call: float = 0.0

    def wait(self) -> None:
        if self.max_qps <= 0:
            return
        min_interval = 1.0 / self.max_qps
        now = time.time()
        elapsed = now - self._last_call
        if elapsed < min_interval:
            time.sleep(min_interval - elapsed)
        self._last_call = time.time()


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")


def clean_text(value: Any) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    return text if text else None


def collapse_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def title_case_city(city: str | None) -> str | None:
    if not city:
        return None
    return collapse_spaces(city).title()


def normalize_zip(value: Any) -> str | None:
    raw = clean_text(value)
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if not digits:
        return None
    if len(digits) >= 5:
        return digits[:5]
    return digits.zfill(5)


def normalize_phone(value: Any) -> str | None:
    raw = clean_text(value)
    if not raw:
        return None
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 10:
        return f"+1{digits}"
    if len(digits) == 11 and digits.startswith("1"):
        return f"+{digits}"
    if digits:
        return f"digits:{digits};raw:{raw}"
    return raw


def normalize_website(value: Any) -> str | None:
    raw = clean_text(value)
    if not raw:
        return None
    if raw.lower().startswith("www."):
        return f"https://{raw}"
    return raw


def canonicalize_key_part(value: Any) -> str:
    if value is None:
        return ""
    return collapse_spaces(str(value)).lower()


def sha256_hash(*parts: Any) -> str:
    joined = "|".join(canonicalize_key_part(p) for p in parts)
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def derive_subtype(name: str, description: str | None) -> str:
    n = name.lower()
    d = (description or "").lower()
    if re.search(r"\bcsa\b", n) or re.search(r"\bcsa\b", d) or "pick-up" in n or "pick up" in n or "pick-up" in d or "pick up" in d:
        return "csa_pickup"
    if "mobile market" in n:
        return "mobile_market"
    if "farmstand" in n or "farmstand" in d:
        return "farmstand"
    return "farmers_market"


def load_csv(path: Path, limit: int | None = None) -> pd.DataFrame:
    df = pd.read_csv(path, skiprows=2, dtype=str, keep_default_na=False)
    if limit is not None and limit > 0:
        return df.head(limit)
    return df


def get_field(row: dict[str, Any], *candidates: str) -> Any:
    norm = {re.sub(r"[^a-z0-9]+", "", str(k).lower()): v for k, v in row.items()}
    for key in candidates:
        nk = re.sub(r"[^a-z0-9]+", "", key.lower())
        if nk in norm:
            return norm[nk]
    return None


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    raw = {k: (None if pd.isna(v) else v) for k, v in row.items()}

    name = clean_text(get_field(row, "LocationName", "Location Name", "Name"))
    line1 = clean_text(get_field(row, "Address", "Street Address", "Location Address"))
    city_raw = clean_text(get_field(row, "City", "Town"))
    city_norm = title_case_city(city_raw)
    zip_code = normalize_zip(get_field(row, "Zip", "ZIP", "Zip Code", "Postal Code"))
    description = clean_text(get_field(row, "Description"))
    website = normalize_website(get_field(row, "Website", "URL", "Url"))
    phone = normalize_phone(get_field(row, "Phone", "Phone Number", "Telephone"))

    # Required for this ingestion and for geocode attempt.
    if not name:
        raise ValidationError("missing required field: name")
    if not line1:
        raise ValidationError("missing required field: address.line1")

    state = "MA"
    city_for_key = city_norm or city_raw or "boston"
    zip_for_key = zip_code or ""

    dedupe_hash = sha256_hash(SOURCE_NAME, name, line1, city_for_key, state, zip_for_key)
    dedupe_key = f"{SOURCE_NAME.lower()}:{dedupe_hash}"

    source_row_hash = sha256_hash(
        SOURCE_NAME,
        name,
        line1,
        city_raw or "",
        state,
        zip_for_key,
    )

    return {
        "dedupe_key": dedupe_key,
        "name": name,
        "datatype": "farmers market",
        "place_type": "farmers_market",
        "subtype": derive_subtype(name, description),
        "description": description,
        "address": {
            "line1": line1,
            "city_raw": city_raw,
            "city_norm": city_norm,
            "state": state,
            "zip": zip_code,
            "formatted_address": None,
        },
        "location": None,
        "geocoding": {
            "provider": "google",
            "status": "NOT_REQUESTED",
            "place_id": None,
            "location_type": None,
            "partial_match": None,
            "confidence": None,
        },
        "contact": {
            "website": website,
            "phone": phone,
        },
        "neighborhood_id": None,
        "neighborhood_name": None,
        "sources": [
            {
                "source_name": SOURCE_NAME,
                "source_file": SOURCE_FILE,
                "source_row_hash": source_row_hash,
                "needs_geocoding": True,
                "raw": raw,
            }
        ],
    }


def build_geocode_query(doc: dict[str, Any]) -> str:
    line1 = doc["address"]["line1"]
    city = doc["address"].get("city_norm") or doc["address"].get("city_raw") or "Boston"
    zip_code = doc["address"].get("zip")
    if zip_code:
        return f"{line1}, {city}, MA {zip_code}, USA"
    return f"{line1}, {city}, MA, USA"


def geocode_query_hash(query: str) -> str:
    return sha256_hash("google_geocode", query, "MA", "US", BOSTON_BOUNDS)


def compute_confidence(location_type: str | None, partial_match: bool | None) -> str | None:
    if not location_type:
        return None
    if location_type == "ROOFTOP" and not partial_match:
        return "high"
    if location_type in ("RANGE_INTERPOLATED", "GEOMETRIC_CENTER") and not partial_match:
        return "medium"
    return "low"


def _parse_google_result(status: str, result: dict[str, Any] | None) -> dict[str, Any]:
    if status != "OK" or not result:
        return {
            "status": status,
            "place_id": None,
            "formatted_address": None,
            "location_type": None,
            "partial_match": None,
            "lat": None,
            "lng": None,
            "confidence": None,
        }

    geometry = result.get("geometry", {})
    location = geometry.get("location", {})
    location_type = geometry.get("location_type")
    partial_match = result.get("partial_match")
    lat = location.get("lat")
    lng = location.get("lng")

    return {
        "status": status,
        "place_id": result.get("place_id"),
        "formatted_address": result.get("formatted_address"),
        "location_type": location_type,
        "partial_match": partial_match,
        "lat": lat,
        "lng": lng,
        "confidence": compute_confidence(location_type, partial_match),
    }


def geocode_address(
    query: str,
    api_key: str,
    limiter: RateLimiter,
    cache_collection: Collection | None,
) -> dict[str, Any]:
    q_hash = geocode_query_hash(query)

    if cache_collection is not None:
        cached = cache_collection.find_one({"geocode_query_hash": q_hash})
        if cached:
            return {
                "status": "OK",
                "place_id": cached.get("place_id"),
                "formatted_address": cached.get("formatted_address"),
                "location_type": cached.get("location_type"),
                "partial_match": cached.get("partial_match"),
                "lat": cached.get("lat"),
                "lng": cached.get("lng"),
                "confidence": compute_confidence(cached.get("location_type"), cached.get("partial_match")),
                "from_cache": True,
                "query_hash": q_hash,
            }

    params = {
        "address": query,
        "components": "administrative_area:MA|country:US",
        "region": "us",
        "bounds": BOSTON_BOUNDS,
        "key": api_key,
    }
    url = "https://maps.googleapis.com/maps/api/geocode/json?" + urllib.parse.urlencode(params)

    max_attempts = 5
    backoff = 0.5

    for attempt in range(max_attempts):
        limiter.wait()
        try:
            with urllib.request.urlopen(url, timeout=15) as resp:
                payload = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            if exc.code in (429, 500, 502, 503, 504) and attempt < max_attempts - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            return {
                "status": f"HTTP_{exc.code}",
                "place_id": None,
                "formatted_address": None,
                "location_type": None,
                "partial_match": None,
                "lat": None,
                "lng": None,
                "confidence": None,
                "from_cache": False,
                "query_hash": q_hash,
            }
        except Exception:
            if attempt < max_attempts - 1:
                time.sleep(backoff)
                backoff *= 2
                continue
            return {
                "status": "REQUEST_FAILED",
                "place_id": None,
                "formatted_address": None,
                "location_type": None,
                "partial_match": None,
                "lat": None,
                "lng": None,
                "confidence": None,
                "from_cache": False,
                "query_hash": q_hash,
            }

        status = payload.get("status", "UNKNOWN")
        if status == "OVER_QUERY_LIMIT" and attempt < max_attempts - 1:
            time.sleep(backoff)
            backoff *= 2
            continue

        results = payload.get("results") or []
        first = results[0] if results else None
        parsed = _parse_google_result(status, first)
        parsed["from_cache"] = False
        parsed["query_hash"] = q_hash

        if status == "OK" and cache_collection is not None:
            cache_collection.update_one(
                {"geocode_query_hash": q_hash},
                {
                    "$set": {
                        "geocode_query_hash": q_hash,
                        "query": query,
                        "place_id": parsed.get("place_id"),
                        "lat": parsed.get("lat"),
                        "lng": parsed.get("lng"),
                        "formatted_address": parsed.get("formatted_address"),
                        "location_type": parsed.get("location_type"),
                        "partial_match": parsed.get("partial_match"),
                        "cached_at": datetime.now(timezone.utc),
                    }
                },
                upsert=True,
            )

        return parsed

    return {
        "status": "OVER_QUERY_LIMIT",
        "place_id": None,
        "formatted_address": None,
        "location_type": None,
        "partial_match": None,
        "lat": None,
        "lng": None,
        "confidence": None,
        "from_cache": False,
        "query_hash": q_hash,
    }


def apply_geocode_to_doc(doc: dict[str, Any], geocode: dict[str, Any], store_mode: str) -> None:
    status = geocode.get("status")
    doc["geocoding"] = {
        "provider": "google",
        "status": status,
        "place_id": geocode.get("place_id"),
        "location_type": geocode.get("location_type"),
        "partial_match": geocode.get("partial_match"),
        "confidence": geocode.get("confidence"),
    }

    doc["address"]["formatted_address"] = geocode.get("formatted_address")

    if status == "OK" and store_mode == STORE_MODE_COORDS:
        lat = geocode.get("lat")
        lng = geocode.get("lng")
        if lat is not None and lng is not None:
            doc["location"] = {"type": "Point", "coordinates": [lng, lat]}
        else:
            doc["location"] = None
    else:
        doc["location"] = None

    doc["sources"][0]["needs_geocoding"] = status != "OK"


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


def resolve_input_path(cli_path: str) -> Path:
    candidate = Path(cli_path)
    if candidate.exists():
        return candidate

    local_fallbacks = [
        Path("data/cleaned_data/farmers_market.csv"),
        Path("data/farmers_market.csv"),
    ]
    for fallback in local_fallbacks:
        if fallback.exists():
            LOGGER.info("Input not found at %s; using fallback %s", cli_path, fallback)
            return fallback
    raise FileNotFoundError(f"Input file not found: {cli_path}")


def resolve_rejects_output_path(requested: Path) -> Path:
    try:
        requested.parent.mkdir(parents=True, exist_ok=True)
        return requested
    except OSError:
        fallback = Path("data/rejects/farmers_market_rejects.json")
        fallback.parent.mkdir(parents=True, exist_ok=True)
        LOGGER.warning(
            "Rejects path %s not writable; falling back to %s",
            requested,
            fallback,
        )
        return fallback


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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest MassGrown farmers markets CSV into MongoDB")
    parser.add_argument("--input", default=DEFAULT_INPUT, help=f"CSV path (default: {DEFAULT_INPUT})")
    parser.add_argument("--dry-run", action="store_true", help="Parse and geocode but do not write MongoDB")
    parser.add_argument("--max-qps", type=float, default=10.0, help="Max geocoding requests per second")
    parser.add_argument("--limit", type=int, default=None, help="Process only first N rows")
    parser.add_argument("--no-geocode", action="store_true", help="Skip geocoding and set location to null")
    parser.add_argument("--rejects", default=DEFAULT_REJECTS, help=f"Rejects JSON path (default: {DEFAULT_REJECTS})")
    return parser.parse_args()


def main() -> None:
    configure_logging()
    args = parse_args()
    mapper = NeighborhoodMapper()

    mongo_uri = os.getenv("MONGO_CONNECTION")
    mongo_db = os.getenv("MONGO_DB", DEFAULT_DB)
    mongo_collection_name = os.getenv("MONGO_COLLECTION", DEFAULT_COLLECTION)
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    store_mode = os.getenv("GEOCODE_STORE_MODE", STORE_MODE_COORDS).strip().lower()
    if store_mode not in {STORE_MODE_COORDS, STORE_MODE_PLACE_ID_ONLY}:
        raise ValueError(
            f"Invalid GEOCODE_STORE_MODE={store_mode}; expected {STORE_MODE_COORDS} or {STORE_MODE_PLACE_ID_ONLY}"
        )

    input_path = resolve_input_path(args.input)
    rejects_path = resolve_rejects_output_path(Path(args.rejects))

    if not args.no_geocode and not api_key:
        raise EnvironmentError("GOOGLE_MAPS_API_KEY is required unless --no-geocode is set")

    client: MongoClient | None = None
    units_collection: Collection | None = None
    geocode_cache_collection: Collection | None = None

    if not args.dry_run:
        if not mongo_uri:
            raise EnvironmentError("MONGO_URI is required unless --dry-run is used")
        client = MongoClient(mongo_uri)
        db = client[mongo_db]
        units_collection = db[mongo_collection_name]
        geocode_cache_collection = db[GEOCODE_CACHE_COLLECTION]

    df = load_csv(input_path, limit=args.limit)

    stats = {
        "rows_read": 0,
        "rows_inserted": 0,
        "rows_updated": 0,
        "rows_skipped": 0,
        "rows_rejected": 0,
        "geocoded_ok": 0,
    }
    geocode_failed_by_status: Counter[str] = Counter()
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
        line_no = idx + 4

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

        if args.no_geocode:
            doc["geocoding"] = {
                "provider": "google",
                "status": "SKIPPED_NO_GEOCODE",
                "place_id": None,
                "location_type": None,
                "partial_match": None,
                "confidence": None,
            }
            doc["location"] = None
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
                stats["geocoded_ok"] += 1
            else:
                geocode_failed_by_status[geocode_result.get("status", "UNKNOWN")] += 1

        assign_neighborhood(doc, mapper)

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

    rejects_path.parent.mkdir(parents=True, exist_ok=True)
    with rejects_path.open("w", encoding="utf-8") as fh:
        json.dump(rejects, fh, indent=2, ensure_ascii=False, default=str)

    LOGGER.info("rows read: %s", stats["rows_read"])
    LOGGER.info("geocoded OK: %s", stats["geocoded_ok"])
    LOGGER.info("geocoded failed by status: %s", dict(geocode_failed_by_status))
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
