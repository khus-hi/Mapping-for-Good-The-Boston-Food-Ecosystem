#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

DRY_RUN=false
NO_GEOCODE=false
SKIP_TESTS=false
LIMIT=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    --no-geocode)
      NO_GEOCODE=true
      shift
      ;;
    --skip-tests)
      SKIP_TESTS=true
      shift
      ;;
    --limit)
      LIMIT="${2:-}"
      if [[ -z "$LIMIT" ]]; then
        echo "Error: --limit requires a value"
        exit 1
      fi
      shift 2
      ;;
    -h|--help)
      cat <<'EOF'
Usage: scripts/reupload/run_all_ingests.sh [options]

Options:
  --dry-run      Parse and test, but do not write to MongoDB.
  --no-geocode   Skip geocoding in ingest scripts.
  --skip-tests   Skip parser/schema tests.
  --limit N      Process only first N rows per ingest.
  -h, --help     Show help.

Environment:
  MONGO_CONNECTION or MONGO_URI required unless --dry-run
  GOOGLE_MAPS_API_KEY required unless --no-geocode
  MONGO_DB defaults to food-distributors
  MONGO_COLLECTION defaults to food-distributors
EOF
      exit 0
      ;;
    *)
      echo "Unknown argument: $1"
      echo "Run with --help for usage."
      exit 1
      ;;
  esac
done

if [[ "$DRY_RUN" != "true" ]]; then
  if [[ -z "${MONGO_CONNECTION:-}" && -z "${MONGO_URI:-}" ]]; then
    echo "Error: set MONGO_CONNECTION (or MONGO_URI) before upload."
    exit 1
  fi
fi

if [[ "$NO_GEOCODE" != "true" ]]; then
  if [[ -z "${GOOGLE_MAPS_API_KEY:-}" ]]; then
    echo "Error: set GOOGLE_MAPS_API_KEY (or run with --no-geocode)."
    exit 1
  fi
fi

TEST_LIMIT_ARGS=(--limit 0)
INGEST_ARGS=()
if [[ "$DRY_RUN" == "true" ]]; then
  INGEST_ARGS+=(--dry-run)
fi
if [[ "$NO_GEOCODE" == "true" ]]; then
  INGEST_ARGS+=(--no-geocode)
fi
if [[ -n "$LIMIT" ]]; then
  INGEST_ARGS+=(--limit "$LIMIT")
fi

if [[ "$SKIP_TESTS" != "true" ]]; then
  echo ""
  echo "== Running parser + schema tests =="
  python tests/verify_parser_matches_ingest.py --input data/cleaned_data/farmers_market.csv "${TEST_LIMIT_ARGS[@]}"
  python tests/verify_restaurants_parser.py --input data/cleaned_data/restaurants_cleaned.csv "${TEST_LIMIT_ARGS[@]}" --allow-parse-errors --max-parse-errors 10
  python tests/verify_grocery_stores_parser.py --input data/cleaned_data/grocery_store_locations_clean.csv "${TEST_LIMIT_ARGS[@]}"
  python tests/verify_food_pantries_parser.py --input data/cleaned_data/suffolk_active_food_pantries.csv "${TEST_LIMIT_ARGS[@]}"
  python tests/verify_normalized_schema_consistency.py
fi

echo ""
echo "== Running ingests (same schema, single collection) =="
python -m parsers.ingest_farmers_markets --input data/cleaned_data/farmers_market.csv "${INGEST_ARGS[@]}"
python -m parsers.ingest_restaurants --input data/cleaned_data/restaurants_cleaned.csv "${INGEST_ARGS[@]}"
python -m parsers.ingest_grocery_stores --input data/cleaned_data/grocery_store_locations_clean.csv "${INGEST_ARGS[@]}"
python -m parsers.ingest_food_pantries --input data/cleaned_data/suffolk_active_food_pantries.csv "${INGEST_ARGS[@]}"

echo ""
echo "All ingest jobs completed."
