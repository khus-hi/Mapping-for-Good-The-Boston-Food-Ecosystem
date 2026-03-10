#!/usr/bin/env python3
"""
Pull tract/block-group ACS 5-year Census data and upsert into MongoDB.

The script writes records with explicit trust metadata:
- source
- last_updated
- confidence
- completeness

Usage:
  python scripts/pull_census_acs.py --city-scope Boston --state 25 --county 025
  python scripts/pull_census_acs.py --level tract --dry-run
  python scripts/pull_census_acs.py --year 2024 --collection census_geo_profiles
"""

from __future__ import annotations

import argparse
import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COLLECTION = "census_geo_profiles"
DEFAULT_LEVELS = ("tract", "block_group")
YEAR_CANDIDATES = (2025, 2024, 2023, 2022, 2021)
ACS_PATH_TEMPLATE = "https://api.census.gov/data/{year}/acs/acs5"

# Verified ACS tables:
# - B01003: Total Population
# - B17001: Poverty Status in Past 12 Months
# - B19013: Median Household Income
# - B19083: Gini Index
TABLE_VARIABLES = {
    "B01003_001E": "total_population",
    "B01003_001M": "total_population_moe",
    "B17001_001E": "poverty_universe",
    "B17001_001M": "poverty_universe_moe",
    "B17001_002E": "below_poverty",
    "B17001_002M": "below_poverty_moe",
    "B19013_001E": "median_household_income",
    "B19013_001M": "median_household_income_moe",
    "B19083_001E": "gini_index",
    "B19083_001M": "gini_index_moe",
}

TRUST_SOURCE_LINKS = [
    "https://www.census.gov/data/developers/data-sets/acs-5year.html",
    "https://api.census.gov/data.html",
]


def load_dot_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding="utf-8").splitlines():
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


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Pull ACS tract/block-group data and upsert into MongoDB")
    parser.add_argument("--collection", default=DEFAULT_COLLECTION, help="Mongo collection for ACS geo profiles")
    parser.add_argument("--city-scope", default="Boston", help="Human-readable scope label")
    parser.add_argument("--state", default="25", help="2-digit state FIPS (MA=25)")
    parser.add_argument("--county", default="025", help="3-digit county FIPS (Suffolk=025)")
    parser.add_argument(
        "--level",
        action="append",
        choices=DEFAULT_LEVELS,
        help="Geography level. Repeat for multiple levels. Defaults to both.",
    )
    parser.add_argument("--year", type=int, default=None, help="ACS vintage year. Defaults to latest available.")
    parser.add_argument("--limit", type=int, default=None, help="Optional max rows per geography level")
    parser.add_argument("--dry-run", action="store_true", help="Print summary only; do not write to Mongo")
    parser.add_argument("--replace-scope", action="store_true", help="Delete existing docs for same scope/year/level before upsert")
    return parser.parse_args()


def _fetch_json(base_url: str, params: dict[str, Any], timeout: int = 20) -> Any:
    query = urlencode(params)
    url = f"{base_url}?{query}"
    try:
        with urlopen(url, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise RuntimeError(f"Census API returned HTTP {exc.code} for {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Census API request failed for {url}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Census API returned invalid JSON for {url}") from exc


def resolve_year(explicit_year: int | None, api_key: str, state_fips: str) -> int:
    if explicit_year is not None:
        return explicit_year

    for year in YEAR_CANDIDATES:
        base_url = ACS_PATH_TEMPLATE.format(year=year)
        params = {"get": "NAME", "for": "state:" + state_fips}
        if api_key:
            params["key"] = api_key
        try:
            payload = _fetch_json(base_url, params, timeout=10)
            if isinstance(payload, list) and len(payload) > 1:
                return year
        except RuntimeError:
            continue

    raise RuntimeError(
        "Could not resolve a supported ACS year. Pass --year explicitly or verify Census API availability."
    )


def to_number(value: Any) -> float | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    # ACS uses large negative sentinel values for missing/suppressed data.
    if number <= -666_000_000:
        return None
    return number


def confidence_label(score: float | None) -> str:
    if score is None:
        return "unknown"
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def completeness_label(score: float) -> str:
    if score >= 0.9:
        return "high"
    if score >= 0.7:
        return "medium"
    return "low"


def build_quality(metrics: dict[str, float | None]) -> tuple[dict[str, Any], dict[str, Any]]:
    required = [
        "total_population",
        "poverty_universe",
        "below_poverty",
        "median_household_income",
        "gini_index",
    ]
    missing = [field for field in required if metrics.get(field) is None]
    completeness_score = (len(required) - len(missing)) / len(required)
    completeness = {
        "score": round(completeness_score, 3),
        "label": completeness_label(completeness_score),
        "missing_fields": missing,
    }

    ratio_pairs = [
        ("total_population", "total_population_moe"),
        ("poverty_universe", "poverty_universe_moe"),
        ("below_poverty", "below_poverty_moe"),
        ("median_household_income", "median_household_income_moe"),
        ("gini_index", "gini_index_moe"),
    ]
    moe_ratios: dict[str, float] = {}
    for estimate_key, moe_key in ratio_pairs:
        estimate = metrics.get(estimate_key)
        moe = metrics.get(moe_key)
        if estimate is None or moe is None or estimate <= 0:
            continue
        moe_ratios[estimate_key] = abs(moe / estimate)

    if moe_ratios:
        avg_ratio = sum(moe_ratios.values()) / len(moe_ratios)
        score = max(0.0, 1.0 - min(avg_ratio, 1.0))
    else:
        avg_ratio = None
        score = None

    confidence = {
        "score": round(score, 3) if score is not None else None,
        "label": confidence_label(score),
        "avg_relative_moe": round(avg_ratio, 3) if avg_ratio is not None else None,
        "relative_moe_by_metric": {k: round(v, 3) for k, v in moe_ratios.items()},
    }
    return confidence, completeness


def poverty_rate_moe(
    below_poverty: float | None,
    below_poverty_moe: float | None,
    poverty_universe: float | None,
    poverty_universe_moe: float | None,
) -> float | None:
    if (
        below_poverty is None
        or below_poverty_moe is None
        or poverty_universe is None
        or poverty_universe_moe is None
        or poverty_universe <= 0
    ):
        return None
    try:
        # Approximate propagated MOE for ratio n/d.
        term_a = below_poverty_moe / poverty_universe
        term_b = (below_poverty * poverty_universe_moe) / (poverty_universe * poverty_universe)
        return math.sqrt((term_a * term_a) + (term_b * term_b))
    except ZeroDivisionError:
        return None


def level_query_parts(level: str, state_fips: str, county_fips: str) -> tuple[str, str]:
    if level == "tract":
        return "tract:*", f"state:{state_fips}+county:{county_fips}"
    if level == "block_group":
        return "block group:*", f"state:{state_fips}+county:{county_fips}+tract:*"
    raise ValueError(f"Unsupported level: {level}")


def fetch_level_rows(
    *,
    year: int,
    level: str,
    state_fips: str,
    county_fips: str,
    api_key: str,
    city_scope: str,
    limit: int | None,
) -> list[dict[str, Any]]:
    base_url = ACS_PATH_TEMPLATE.format(year=year)
    for_clause, in_clause = level_query_parts(level, state_fips, county_fips)
    now = datetime.now(timezone.utc)

    params = {
        "get": ",".join(["NAME", *TABLE_VARIABLES.keys()]),
        "for": for_clause,
        "in": in_clause,
    }
    if api_key:
        params["key"] = api_key

    payload = _fetch_json(base_url, params)
    if not isinstance(payload, list) or len(payload) <= 1:
        return []

    header = payload[0]
    rows: list[dict[str, Any]] = []
    for item in payload[1:]:
        row = dict(zip(header, item))
        state = str(row.get("state") or "").strip()
        county = str(row.get("county") or "").strip()
        tract = str(row.get("tract") or "").strip()
        block_group = str(row.get("block group") or "").strip() if level == "block_group" else None
        if not state or not county or not tract:
            continue

        geoid = f"{state}{county}{tract}"
        if block_group:
            geoid += block_group

        metrics: dict[str, float | None] = {}
        for raw_key, renamed in TABLE_VARIABLES.items():
            metrics[renamed] = to_number(row.get(raw_key))

        poverty_universe = metrics.get("poverty_universe")
        below_poverty = metrics.get("below_poverty")
        if poverty_universe and poverty_universe > 0 and below_poverty is not None:
            metrics["poverty_rate"] = below_poverty / poverty_universe
        else:
            metrics["poverty_rate"] = None

        metrics["poverty_rate_moe"] = poverty_rate_moe(
            below_poverty=metrics.get("below_poverty"),
            below_poverty_moe=metrics.get("below_poverty_moe"),
            poverty_universe=metrics.get("poverty_universe"),
            poverty_universe_moe=metrics.get("poverty_universe_moe"),
        )

        confidence, completeness = build_quality(metrics)

        rows.append(
            {
                "geoid": geoid,
                "geo_level": level,
                "name": row.get("NAME"),
                "state_fips": state,
                "county_fips": county,
                "tract_code": tract,
                "block_group_code": block_group,
                "city_scope": city_scope,
                "vintage": year,
                "metrics": metrics,
                "source": {
                    "provider": "U.S. Census Bureau",
                    "dataset": "ACS 5-Year Data (Detailed Tables)",
                    "table_ids": ["B01003", "B17001", "B19013", "B19083"],
                    "api_endpoint": base_url,
                    "verified_links": TRUST_SOURCE_LINKS,
                },
                "last_updated": now,
                "confidence": confidence,
                "completeness": completeness,
            }
        )

        if limit is not None and len(rows) >= limit:
            break

    return rows


def main() -> None:
    args = parse_args()
    levels = tuple(args.level) if args.level else DEFAULT_LEVELS
    dot_env = load_dot_env(ROOT / ".env")

    mongo_uri = os.environ.get("MONGO_CONNECTION") or dot_env.get("MONGO_CONNECTION", "")
    mongo_db_name = os.environ.get("MONGO_DB") or dot_env.get("MONGO_DB", "food-distributors")
    census_api_key = os.environ.get("CENSUS_API_KEY") or dot_env.get("CENSUS_API_KEY", "")

    year = resolve_year(args.year, census_api_key, args.state)
    print(f"Using ACS year: {year}")

    docs: list[dict[str, Any]] = []
    for level in levels:
        fetched = fetch_level_rows(
            year=year,
            level=level,
            state_fips=args.state,
            county_fips=args.county,
            api_key=census_api_key,
            city_scope=args.city_scope,
            limit=args.limit,
        )
        docs.extend(fetched)
        print(f"Fetched {len(fetched)} rows for level '{level}'.")

    if not docs:
        raise SystemExit("No rows returned from Census API.")

    sample = docs[0].copy()
    sample["last_updated"] = sample["last_updated"].isoformat()
    print("Sample row:")
    print(json.dumps(sample, indent=2))
    print(f"Prepared {len(docs)} total records for collection '{args.collection}'.")

    if args.dry_run:
        print("Dry-run mode enabled. No database writes executed.")
        return

    if not mongo_uri:
        raise SystemExit("Error: MONGO_CONNECTION not set in environment or .env")

    client = MongoClient(mongo_uri)
    db = client[mongo_db_name]
    collection = db[args.collection]

    if args.replace_scope:
        for level in levels:
            result = collection.delete_many(
                {
                    "city_scope": args.city_scope,
                    "vintage": year,
                    "geo_level": level,
                    "state_fips": args.state,
                    "county_fips": args.county,
                }
            )
            print(f"Deleted {result.deleted_count} existing '{level}' docs for same scope/year.")

    upserts = 0
    for doc in docs:
        collection.update_one(
            {
                "geo_level": doc["geo_level"],
                "geoid": doc["geoid"],
                "vintage": doc["vintage"],
            },
            {"$set": doc},
            upsert=True,
        )
        upserts += 1

    collection.create_index([("geo_level", 1), ("geoid", 1), ("vintage", 1)], unique=True)
    collection.create_index([("city_scope", 1), ("geo_level", 1), ("vintage", 1)])
    collection.create_index([("state_fips", 1), ("county_fips", 1), ("geo_level", 1), ("vintage", 1)])
    print(f"Upserted {upserts} records into '{args.collection}' (db='{mongo_db_name}').")


if __name__ == "__main__":
    main()
