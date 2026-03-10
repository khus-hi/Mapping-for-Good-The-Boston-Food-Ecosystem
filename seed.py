"""
Run once to load CSV data into MongoDB:
    python seed.py
"""
import csv
import os
from pathlib import Path
from pymongo import MongoClient

ROOT = Path(__file__).parent.resolve()


def load_dot_env(filepath: Path) -> dict:
    env = {}
    if not filepath.exists():
        return env
    for line in filepath.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        env[key] = value
    return env


dot_env = load_dot_env(ROOT / ".env")
MONGO_URI = os.environ.get("MONGO_CONNECTION") or dot_env.get("MONGO_CONNECTION", "")

if not MONGO_URI:
    raise SystemExit("Error: MONGO_CONNECTION not set in .env")

client = MongoClient(MONGO_URI)
db = client["food-distributors"]


def seed_farmers_markets():
    collection = db["farmers_markets"]
    collection.drop()
    rows = []

    with open(ROOT / "data" / "cleaned_data" / "farmers_market.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            record = {k.strip(): v.strip() for k, v in row.items()}
            # lat/lng are already in the CSV as fake coordinates
            record["lat"] = float(record["lat"]) if record.get("lat") else None
            record["lng"] = float(record["lng"]) if record.get("lng") else None
            rows.append(record)

    collection.insert_many(rows)
    print(f"Inserted {len(rows)} farmers market records with lat/lng")


def seed_income_inequality():
    collection = db["income_inequality"]
    collection.drop()
    rows = []
    with open(ROOT / "data" / "Income_inequality_index_PolicyMap.csv", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        next(reader)  # skip the second header row (field name aliases)
        for row in reader:
            rows.append({k.strip(): v.strip() for k, v in row.items()})
    collection.insert_many(rows)
    print(f"Inserted {len(rows)} income inequality records")


if __name__ == "__main__":
    seed_farmers_markets()
    seed_income_inequality()
    print("Done — MongoDB seeded successfully")
