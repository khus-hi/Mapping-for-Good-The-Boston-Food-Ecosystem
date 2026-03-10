#!/usr/bin/env python3
"""Verify normalized schema consistency across all ingest parsers."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PARSER_CONFIG = [
    {
        "name": "farmers",
        "module": "parsers.ingest_farmers_markets",
        "csv": Path("data/cleaned_data/farmers_market.csv"),
        "skiprows": 2,
        "expected_datatype": "farmers market",
    },
    {
        "name": "restaurants",
        "module": "parsers.ingest_restaurants",
        "csv": Path("data/cleaned_data/restaurants_cleaned.csv"),
        "skiprows": 0,
        "expected_datatype": "restaurant",
    },
    {
        "name": "grocery",
        "module": "parsers.ingest_grocery_stores",
        "csv": Path("data/cleaned_data/grocery_store_locations_clean.csv"),
        "skiprows": 0,
        "expected_datatype": "grocery store",
    },
    {
        "name": "pantries",
        "module": "parsers.ingest_food_pantries",
        "csv": Path("data/cleaned_data/suffolk_active_food_pantries.csv"),
        "skiprows": 0,
        "expected_datatype": "food pantry",
    },
]

REQUIRED_ROOT_KEYS = {
    "dedupe_key",
    "name",
    "datatype",
    "place_type",
    "subtype",
    "description",
    "address",
    "location",
    "geocoding",
    "contact",
    "neighborhood_id",
    "neighborhood_name",
    "sources",
}
REQUIRED_ADDRESS_KEYS = {"line1", "city_raw", "city_norm", "state", "zip", "formatted_address"}
REQUIRED_GEOCODING_KEYS = {"provider", "status", "place_id", "location_type", "partial_match", "confidence"}
REQUIRED_CONTACT_KEYS = {"website", "phone"}
REQUIRED_SOURCE_KEYS = {"source_name", "source_file", "source_row_hash", "needs_geocoding", "raw"}


def to_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def load_first_row(csv_path: Path, skiprows: int = 0) -> dict[str, Any]:
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")
    df = pd.read_csv(csv_path, skiprows=skiprows, dtype=str, keep_default_na=False)
    if df.empty:
        raise ValueError(f"CSV has no rows: {csv_path}")
    return df.iloc[0].to_dict()


def load_doc(config: dict[str, Any]) -> dict[str, Any]:
    module = importlib.import_module(config["module"])
    normalize_row = getattr(module, "normalize_row", None)
    if normalize_row is None or not callable(normalize_row):
        raise AttributeError(f"Module {config['module']} does not provide callable normalize_row")
    row = load_first_row(config["csv"], skiprows=config["skiprows"])
    return to_jsonable(normalize_row(row))


def keyset(value: Any) -> set[str]:
    return set(value.keys()) if isinstance(value, dict) else set()


def main() -> int:
    docs_by_name: dict[str, dict[str, Any]] = {}
    errors: list[str] = []

    for cfg in PARSER_CONFIG:
        try:
            doc = load_doc(cfg)
        except Exception as exc:  # pylint: disable=broad-except
            errors.append(f"{cfg['name']}: failed to load normalized doc ({type(exc).__name__}: {exc})")
            continue
        docs_by_name[cfg["name"]] = doc

        datatype = doc.get("datatype")
        if datatype != cfg["expected_datatype"]:
            errors.append(
                f"{cfg['name']}: datatype expected {cfg['expected_datatype']!r}, got {datatype!r}"
            )

        root_keys = keyset(doc)
        missing = REQUIRED_ROOT_KEYS - root_keys
        if missing:
            errors.append(f"{cfg['name']}: missing root keys {sorted(missing)}")

        address_keys = keyset(doc.get("address"))
        missing_address = REQUIRED_ADDRESS_KEYS - address_keys
        if missing_address:
            errors.append(f"{cfg['name']}: missing address keys {sorted(missing_address)}")

        geocoding_keys = keyset(doc.get("geocoding"))
        missing_geo = REQUIRED_GEOCODING_KEYS - geocoding_keys
        if missing_geo:
            errors.append(f"{cfg['name']}: missing geocoding keys {sorted(missing_geo)}")

        contact_keys = keyset(doc.get("contact"))
        missing_contact = REQUIRED_CONTACT_KEYS - contact_keys
        if missing_contact:
            errors.append(f"{cfg['name']}: missing contact keys {sorted(missing_contact)}")

        sources = doc.get("sources")
        if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict):
            errors.append(f"{cfg['name']}: sources must be a list with one dict entry")
        else:
            source_keys = keyset(sources[0])
            missing_source = REQUIRED_SOURCE_KEYS - source_keys
            if missing_source:
                errors.append(f"{cfg['name']}: missing source keys {sorted(missing_source)}")

    if not errors:
        docs = list(docs_by_name.values())
        root_sets = [keyset(doc) for doc in docs]
        address_sets = [keyset(doc.get("address")) for doc in docs]
        geocoding_sets = [keyset(doc.get("geocoding")) for doc in docs]
        contact_sets = [keyset(doc.get("contact")) for doc in docs]
        source_sets = [keyset(doc.get("sources")[0]) for doc in docs if isinstance(doc.get("sources"), list) and doc.get("sources")]

        if root_sets and not all(s == root_sets[0] for s in root_sets[1:]):
            errors.append("schema mismatch: root key sets differ across parsers")
        if address_sets and not all(s == address_sets[0] for s in address_sets[1:]):
            errors.append("schema mismatch: address key sets differ across parsers")
        if geocoding_sets and not all(s == geocoding_sets[0] for s in geocoding_sets[1:]):
            errors.append("schema mismatch: geocoding key sets differ across parsers")
        if contact_sets and not all(s == contact_sets[0] for s in contact_sets[1:]):
            errors.append("schema mismatch: contact key sets differ across parsers")
        if source_sets and not all(s == source_sets[0] for s in source_sets[1:]):
            errors.append("schema mismatch: source key sets differ across parsers")

    if errors:
        print("Schema consistency check FAILED")
        for err in errors:
            print(f"- {err}")
        return 1

    print("Schema consistency check PASSED")
    print(f"Parsers checked: {', '.join(cfg['name'] for cfg in PARSER_CONFIG)}")
    print(f"Shared root keys: {sorted(keyset(next(iter(docs_by_name.values()))))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
