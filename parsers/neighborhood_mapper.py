#!/usr/bin/env python3
"""Map geolocated objects to Boston neighborhoods using GeoJSON boundaries."""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

def _resolve_default_population_csv() -> Path:
    candidates = [
        Path("data/cleaned_data/population_up.csv"),
        Path("data/cleaned_data/populated_up.csv"),
        Path("data/cleaned_data/population_updated.csv"),
    ]
    for path in candidates:
        if path.exists():
            return path
    return candidates[0]


DEFAULT_POPULATION_CSV = _resolve_default_population_csv()
DEFAULT_NEIGHBORHOODS_GEOJSON = Path("data/boston_neighborhood_boundaries.geojson")


def canonicalize_name(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


@dataclass(frozen=True)
class NeighborhoodFeature:
    neighborhood_id: int
    neighborhood_name: str
    geometry: dict[str, Any]


def _to_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        if isinstance(value, float) and math.isnan(value):
            return None
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _point_on_segment(lng: float, lat: float, a: list[float], b: list[float], eps: float = 1e-12) -> bool:
    ax, ay = a[0], a[1]
    bx, by = b[0], b[1]
    squared_len = (bx - ax) * (bx - ax) + (by - ay) * (by - ay)
    if squared_len <= eps:
        return (lng - ax) * (lng - ax) + (lat - ay) * (lat - ay) <= eps

    cross = (lng - ax) * (by - ay) - (lat - ay) * (bx - ax)
    if abs(cross) > eps:
        return False
    dot = (lng - ax) * (bx - ax) + (lat - ay) * (by - ay)
    if dot < -eps:
        return False
    if dot - squared_len > eps:
        return False
    return True


def _point_in_ring(lng: float, lat: float, ring: list[list[float]]) -> bool:
    if len(ring) < 4:
        return False

    inside = False
    for i in range(len(ring)):
        a = ring[i]
        b = ring[(i + 1) % len(ring)]

        if _point_on_segment(lng, lat, a, b):
            return True

        x1, y1 = a[0], a[1]
        x2, y2 = b[0], b[1]

        intersects = ((y1 > lat) != (y2 > lat)) and (
            lng < ((x2 - x1) * (lat - y1) / (y2 - y1) + x1)
        )
        if intersects:
            inside = not inside
    return inside


def _point_in_polygon(lng: float, lat: float, polygon_coords: list[list[list[float]]]) -> bool:
    if not polygon_coords:
        return False
    outer = polygon_coords[0]
    if not _point_in_ring(lng, lat, outer):
        return False
    for hole in polygon_coords[1:]:
        if _point_in_ring(lng, lat, hole):
            return False
    return True


def geometry_contains_point(geometry: dict[str, Any], lng: float, lat: float) -> bool:
    geom_type = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return False
    if geom_type == "Polygon":
        return _point_in_polygon(lng, lat, coords)
    if geom_type == "MultiPolygon":
        return any(_point_in_polygon(lng, lat, polygon) for polygon in coords)
    return False


def load_population_ids(population_csv_path: Path) -> dict[str, tuple[int, str]]:
    if not population_csv_path.exists():
        raise FileNotFoundError(f"Population CSV not found: {population_csv_path}")

    mapping: dict[str, tuple[int, str]] = {}
    with population_csv_path.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        if "Neighborhood" not in (reader.fieldnames or []):
            raise ValueError("Population CSV must contain a 'Neighborhood' column")

        next_id = 1
        for row in reader:
            name = (row.get("Neighborhood") or "").strip()
            if not name:
                continue
            key = canonicalize_name(name)
            if key in mapping:
                continue
            mapping[key] = (next_id, name)
            next_id += 1

    if not mapping:
        raise ValueError(f"No neighborhoods loaded from {population_csv_path}")
    return mapping


def load_neighborhood_features(
    geojson_path: Path,
    population_id_map: dict[str, tuple[int, str]],
) -> list[NeighborhoodFeature]:
    if not geojson_path.exists():
        raise FileNotFoundError(f"GeoJSON not found: {geojson_path}")

    obj = json.loads(geojson_path.read_text(encoding="utf-8"))
    features = obj.get("features")
    if not isinstance(features, list):
        raise ValueError(f"Invalid GeoJSON (missing features): {geojson_path}")

    resolved: list[NeighborhoodFeature] = []
    seen_population_keys: set[str] = set()

    for feature in features:
        props = feature.get("properties") or {}
        geometry = feature.get("geometry") or {}
        name = (props.get("name") or "").strip()
        if not name:
            continue
        key = canonicalize_name(name)
        if key not in population_id_map:
            continue
        neighborhood_id, canonical_name = population_id_map[key]
        resolved.append(
            NeighborhoodFeature(
                neighborhood_id=neighborhood_id,
                neighborhood_name=canonical_name,
                geometry=geometry,
            )
        )
        seen_population_keys.add(key)

    missing = set(population_id_map.keys()) - seen_population_keys
    if missing:
        missing_names = [population_id_map[key][1] for key in sorted(missing)]
        raise ValueError(
            "Some neighborhoods from population CSV are missing in GeoJSON: "
            + ", ".join(missing_names)
        )

    resolved.sort(key=lambda x: x.neighborhood_id)
    return resolved


class NeighborhoodMapper:
    """Maps lng/lat points to neighborhood id and name."""

    def __init__(
        self,
        population_csv_path: Path = DEFAULT_POPULATION_CSV,
        geojson_path: Path = DEFAULT_NEIGHBORHOODS_GEOJSON,
    ) -> None:
        population_ids = load_population_ids(population_csv_path)
        self.features = load_neighborhood_features(geojson_path, population_ids)

    def find_for_point(self, lng: float, lat: float) -> tuple[int, str] | None:
        for feature in self.features:
            if geometry_contains_point(feature.geometry, lng=lng, lat=lat):
                return feature.neighborhood_id, feature.neighborhood_name
        return None

    def assign_to_object(self, obj: dict[str, Any]) -> dict[str, Any]:
        """Mutate object with neighborhood fields based on geolocation, if available."""
        lng, lat = extract_lng_lat(obj)
        if lng is None or lat is None:
            obj["neighborhood_id"] = None
            obj["neighborhood_name"] = None
            return obj

        match = self.find_for_point(lng=lng, lat=lat)
        if match is None:
            obj["neighborhood_id"] = None
            obj["neighborhood_name"] = None
            return obj

        neighborhood_id, neighborhood_name = match
        obj["neighborhood_id"] = neighborhood_id
        obj["neighborhood_name"] = neighborhood_name
        return obj


def extract_lng_lat(obj: dict[str, Any]) -> tuple[float | None, float | None]:
    location = obj.get("location")
    if isinstance(location, dict):
        coords = location.get("coordinates")
        if isinstance(coords, (list, tuple)) and len(coords) >= 2:
            lng = _to_float(coords[0])
            lat = _to_float(coords[1])
            if lng is not None and lat is not None:
                return lng, lat

    lng = _to_float(obj.get("longitude") or obj.get("lng"))
    lat = _to_float(obj.get("latitude") or obj.get("lat"))
    return lng, lat


def assign_neighborhood(
    obj: dict[str, Any],
    mapper: NeighborhoodMapper | None = None,
) -> dict[str, Any]:
    if mapper is None:
        mapper = NeighborhoodMapper()
    return mapper.assign_to_object(obj)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Lookup neighborhood for a point")
    parser.add_argument("--lng", type=float, required=True, help="Longitude")
    parser.add_argument("--lat", type=float, required=True, help="Latitude")
    parser.add_argument("--population-csv", default=str(DEFAULT_POPULATION_CSV))
    parser.add_argument("--geojson", default=str(DEFAULT_NEIGHBORHOODS_GEOJSON))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    mapper = NeighborhoodMapper(
        population_csv_path=Path(args.population_csv),
        geojson_path=Path(args.geojson),
    )
    match = mapper.find_for_point(lng=args.lng, lat=args.lat)
    if match is None:
        print("No neighborhood match")
        return
    neighborhood_id, neighborhood_name = match
    print(json.dumps({"neighborhood_id": neighborhood_id, "neighborhood_name": neighborhood_name}, indent=2))


if __name__ == "__main__":
    main()
