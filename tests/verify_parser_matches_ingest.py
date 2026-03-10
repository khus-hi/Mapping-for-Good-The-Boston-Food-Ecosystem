#!/usr/bin/env python3
"""Verify a parser's row output matches parsers.ingest_farmers_markets.normalize_row.

How to run:
python tests/verify_parser_matches_ingest.py --input data/cleaned_data/farmers_market.csv --limit 5
If this passes upload to mongodb.
"""

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

from parsers.ingest_farmers_markets import normalize_row


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Compare a parser output against parsers.ingest_farmers_markets.normalize_row "
            "for each CSV row."
        )
    )
    parser.add_argument("--input", default="data/cleaned_data/farmers_market.csv", help="CSV input file path")
    parser.add_argument(
        "--parser-module",
        default="parsers.ingest_farmers_markets",
        help="Python module containing parser function under test",
    )
    parser.add_argument(
        "--parser-fn",
        default="normalize_row",
        help="Parser function name in --parser-module. Signature: fn(row_dict) -> dict",
    )
    parser.add_argument("--limit", type=int, default=25, help="Max rows to test")
    parser.add_argument(
        "--show-mismatches",
        type=int,
        default=3,
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


def compare_expected_subset(expected: Any, actual: Any, path: str = "") -> list[str]:
    errors: list[str] = []

    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            errors.append(f"{path or '<root>'}: expected dict, got {type(actual).__name__}")
            return errors
        for key, expected_val in expected.items():
            next_path = f"{path}.{key}" if path else key
            if key not in actual:
                errors.append(f"{next_path}: missing key")
                continue
            errors.extend(compare_expected_subset(expected_val, actual[key], next_path))
        return errors

    if isinstance(expected, list):
        if not isinstance(actual, list):
            errors.append(f"{path or '<root>'}: expected list, got {type(actual).__name__}")
            return errors
        if len(expected) != len(actual):
            errors.append(f"{path or '<root>'}: expected list length {len(expected)}, got {len(actual)}")
            return errors
        for idx, (expected_item, actual_item) in enumerate(zip(expected, actual)):
            next_path = f"{path}[{idx}]"
            errors.extend(compare_expected_subset(expected_item, actual_item, next_path))
        return errors

    if expected != actual:
        errors.append(
            f"{path or '<root>'}: expected {expected!r}, got {actual!r}"
        )
    return errors


def load_rows(csv_path: Path, limit: int | None) -> list[dict[str, Any]]:
    df = pd.read_csv(csv_path, skiprows=2, dtype=str, keep_default_na=False)
    if limit is not None and limit > 0:
        df = df.head(limit)
    return [row.to_dict() for _, row in df.iterrows()]


def main() -> int:
    args = parse_args()
    csv_path = Path(args.input)
    if not csv_path.exists():
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    parser_fn = load_parser(args.parser_module, args.parser_fn)
    rows = load_rows(csv_path, args.limit)

    mismatches: list[dict[str, Any]] = []
    total = 0

    for idx, row in enumerate(rows, start=1):
        total += 1
        expected = to_jsonable(normalize_row(row))
        actual = to_jsonable(parser_fn(row))
        errors = compare_expected_subset(expected, actual)
        if errors:
            mismatches.append(
                {
                    "row_index_1_based": idx,
                    "errors": errors,
                    "expected": expected,
                    "actual": actual,
                }
            )

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
            print("Expected:")
            print(json.dumps(mismatch["expected"], indent=2, ensure_ascii=False))
            print("Actual:")
            print(json.dumps(mismatch["actual"], indent=2, ensure_ascii=False))
        return 1

    print("All tested rows match expected ingest output.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
