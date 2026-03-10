#!/usr/bin/env python3
"""Verify food pantry parser output shape and normalization invariants."""

from __future__ import annotations

import argparse
import importlib
import json
import sys
from pathlib import Path
from typing import Any, Callable

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parsers.ingest_farmers_markets import collapse_spaces, normalize_zip, title_case_city

EXPECTED_ROOT_KEYS = {
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

EXPECTED_ADDRESS_KEYS = {"line1", "city_raw", "city_norm", "state", "zip", "formatted_address"}
EXPECTED_GEOCODING_KEYS = {"provider", "status", "place_id", "location_type", "partial_match", "confidence"}
EXPECTED_CONTACT_KEYS = {"website", "phone"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify parser normalization for data/cleaned_data/suffolk_active_food_pantries.csv."
    )
    parser.add_argument("--input", default="data/cleaned_data/suffolk_active_food_pantries.csv", help="CSV input file path")
    parser.add_argument(
        "--parser-module",
        default="parsers.ingest_food_pantries",
        help="Python module containing parser function under test",
    )
    parser.add_argument(
        "--parser-fn",
        default="normalize_row",
        help="Parser function name in --parser-module. Signature: fn(row_dict) -> dict",
    )
    parser.add_argument("--limit", type=int, default=250, help="Max rows to test")
    parser.add_argument(
        "--show-mismatches",
        type=int,
        default=5,
        help="How many mismatch samples to print",
    )
    return parser.parse_args()


def load_parser(module_name: str, fn_name: str) -> Callable[[dict[str, Any]], dict[str, Any]]:
    module = importlib.import_module(module_name)
    parser_fn = getattr(module, fn_name, None)
    if parser_fn is None:
        raise AttributeError(f"Function '{fn_name}' not found in module '{module_name}'")
    if not callable(parser_fn):
        raise TypeError(f"Attribute '{fn_name}' in module '{module_name}' is not callable")
    return parser_fn


def to_jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, default=str))


def expected_city_fields(city_value: Any) -> tuple[str | None, str | None]:
    if city_value is None:
        return None, None
    city = str(city_value).strip()
    if not city:
        return None, None
    cleaned = collapse_spaces(city.rstrip("/").strip())
    if not cleaned:
        return None, None
    return cleaned, title_case_city(cleaned)


def load_rows(csv_path: Path, limit: int | None) -> list[dict[str, Any]]:
    df = pd.read_csv(csv_path, dtype=str, keep_default_na=False)
    if limit is not None and limit > 0:
        df = df.head(limit)
    return [row.to_dict() for _, row in df.iterrows()]


def validate_row(raw_row: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    errors: list[str] = []

    missing_root = sorted(EXPECTED_ROOT_KEYS - set(actual.keys()))
    if missing_root:
        errors.append(f"<root>: missing keys {missing_root}")

    if actual.get("place_type") != "food_pantry":
        errors.append(f"place_type: expected 'food_pantry', got {actual.get('place_type')!r}")
    if actual.get("datatype") != "food pantry":
        errors.append(f"datatype: expected 'food pantry', got {actual.get('datatype')!r}")

    address = actual.get("address")
    if not isinstance(address, dict):
        errors.append(f"address: expected dict, got {type(address).__name__}")
    else:
        missing_address = sorted(EXPECTED_ADDRESS_KEYS - set(address.keys()))
        if missing_address:
            errors.append(f"address: missing keys {missing_address}")
        expected_city_raw, expected_city_norm = expected_city_fields(raw_row.get("City"))
        if address.get("city_raw") != expected_city_raw:
            errors.append(f"address.city_raw: expected {expected_city_raw!r}, got {address.get('city_raw')!r}")
        if address.get("city_norm") != expected_city_norm:
            errors.append(f"address.city_norm: expected {expected_city_norm!r}, got {address.get('city_norm')!r}")
        expected_zip = normalize_zip(raw_row.get("Zip"))
        if address.get("zip") != expected_zip:
            errors.append(f"address.zip: expected {expected_zip!r}, got {address.get('zip')!r}")

    geocoding = actual.get("geocoding")
    if not isinstance(geocoding, dict):
        errors.append(f"geocoding: expected dict, got {type(geocoding).__name__}")
    else:
        missing_geo = sorted(EXPECTED_GEOCODING_KEYS - set(geocoding.keys()))
        if missing_geo:
            errors.append(f"geocoding: missing keys {missing_geo}")
        if geocoding.get("status") != "NOT_REQUESTED":
            errors.append(f"geocoding.status: expected 'NOT_REQUESTED', got {geocoding.get('status')!r}")

    contact = actual.get("contact")
    if not isinstance(contact, dict):
        errors.append(f"contact: expected dict, got {type(contact).__name__}")
    else:
        missing_contact = sorted(EXPECTED_CONTACT_KEYS - set(contact.keys()))
        if missing_contact:
            errors.append(f"contact: missing keys {missing_contact}")

    sources = actual.get("sources")
    if not isinstance(sources, list) or len(sources) != 1 or not isinstance(sources[0], dict):
        errors.append("sources: expected list with one source object")
    else:
        source = sources[0]
        if source.get("source_file") != "suffolk_active_food_pantries.csv":
            errors.append(
                "sources[0].source_file: expected 'suffolk_active_food_pantries.csv', "
                f"got {source.get('source_file')!r}"
            )
        if source.get("needs_geocoding") is not True:
            errors.append("sources[0].needs_geocoding: expected True")
        raw = source.get("raw")
        if not isinstance(raw, dict):
            errors.append("sources[0].raw: expected dict")
        else:
            for required in ("Name", "Street", "City", "State", "Zip", "County", "Status", "Type_Desc"):
                if required not in raw:
                    errors.append(f"sources[0].raw: missing key {required!r}")

    if actual.get("location") is not None:
        errors.append(f"location: expected None before geocoding, got {actual.get('location')!r}")

    return errors


def main() -> int:
    args = parse_args()
    csv_path = Path(args.input)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    parser_fn = load_parser(args.parser_module, args.parser_fn)
    rows = load_rows(csv_path, args.limit)

    mismatches: list[dict[str, Any]] = []

    for idx, row in enumerate(rows, start=1):
        try:
            actual = to_jsonable(parser_fn(row))
            errors = validate_row(row, actual)
        except Exception as exc:  # pylint: disable=broad-except
            actual = None
            errors = [f"parser raised {type(exc).__name__}: {exc}"]
        if errors:
            mismatches.append(
                {
                    "row_index_1_based": idx,
                    "errors": errors,
                    "input": row,
                    "actual": actual,
                }
            )

    total = len(rows)
    passed = total - len(mismatches)
    print(f"Rows tested: {total}")
    print(f"Rows passed: {passed}")
    print(f"Rows mismatched: {len(mismatches)}")

    if mismatches:
        print("")
        print(f"Showing first {min(args.show_mismatches, len(mismatches))} mismatches:")
        for mismatch in mismatches[: args.show_mismatches]:
            print("")
            print(f"Row #{mismatch['row_index_1_based']}")
            print("Errors:")
            for err in mismatch["errors"][:20]:
                print(f"- {err}")
            print("Input:")
            print(json.dumps(mismatch["input"], indent=2, ensure_ascii=False))
            print("Actual:")
            print(json.dumps(mismatch["actual"], indent=2, ensure_ascii=False))
        return 1

    print("All tested rows satisfy parser invariants.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
