import {
  EXCLUDED_SEARCH_NEIGHBORHOODS,
  BASE_MAP_STYLES,
  MAP_THEME_STYLES,
  PLACE_TYPE_COLORS,
  PIN_CHANGE_EPSILON,
} from "./constants";

export function normalizeNeighborhood(value) {
  return String(value || "").trim().toLowerCase().replace(/\s+/g, " ");
}

export function isExcludedNeighborhoodForSearch(value) {
  return EXCLUDED_SEARCH_NEIGHBORHOODS.has(normalizeNeighborhood(value));
}

export function normalizePlaceTypesInput(value) {
  if (value == null) return [];
  if (Array.isArray(value)) {
    return value.map((item) => String(item).trim()).filter(Boolean);
  }
  const text = String(value).trim();
  return text ? [text] : [];
}

export function giniToColor(t) {
  const r = Math.round(255 + (128 - 255) * t);
  const g = Math.round(255 + (0 - 255) * t);
  const b = Math.round(204 + (38 - 204) * t);
  return `rgb(${r},${g},${b})`;
}

export function darkenColor(color, amount = 0.12) {
  if (typeof color !== "string") return color;

  const clamp = (value) => Math.max(0, Math.min(255, Math.round(value)));
  const scale = 1 - amount;

  const rgbMatch = color.match(/^rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)$/i);
  if (rgbMatch) {
    const r = clamp(Number(rgbMatch[1]) * scale);
    const g = clamp(Number(rgbMatch[2]) * scale);
    const b = clamp(Number(rgbMatch[3]) * scale);
    return `rgb(${r},${g},${b})`;
  }

  const hexMatch = color.match(/^#([0-9a-f]{6})$/i);
  if (hexMatch) {
    const hex = hexMatch[1];
    const r = clamp(parseInt(hex.slice(0, 2), 16) * scale);
    const g = clamp(parseInt(hex.slice(2, 4), 16) * scale);
    const b = clamp(parseInt(hex.slice(4, 6), 16) * scale);
    return `rgb(${r},${g},${b})`;
  }

  return color;
}

export function getNeighborhoodName(feature) {
  const name = feature.getProperty("name");
  return typeof name === "string" && name.trim() ? name.trim() : "Unknown Neighborhood";
}

export function hasPinMoved(currentPin, nextPin) {
  if (!currentPin || !nextPin) return true;
  return (
    Math.abs(Number(currentPin.lat) - Number(nextPin.lat)) > PIN_CHANGE_EPSILON ||
    Math.abs(Number(currentPin.lng) - Number(nextPin.lng)) > PIN_CHANGE_EPSILON
  );
}

export function polygonContainsLatLng(polygonGeometry, latLng) {
  if (!polygonGeometry || !latLng || !window.google?.maps?.geometry?.poly) return false;
  const paths = polygonGeometry.getArray().map((ring) => ring.getArray());
  if (!paths.length) return false;
  const polygon = new window.google.maps.Polygon({ paths });
  return window.google.maps.geometry.poly.containsLocation(latLng, polygon);
}

export function geometryContainsLatLng(geometry, latLng) {
  if (!geometry || !latLng) return false;
  const type = geometry.getType();
  if (type === "Polygon") {
    return polygonContainsLatLng(geometry, latLng);
  }
  if (type === "MultiPolygon" || type === "GeometryCollection") {
    return geometry.getArray().some((inner) => geometryContainsLatLng(inner, latLng));
  }
  return false;
}

export function getMapStyles(theme) {
  const themeStyles = MAP_THEME_STYLES[theme] || MAP_THEME_STYLES.civic;
  return [...BASE_MAP_STYLES, ...themeStyles];
}

export function expandBoundsLiteral(bounds, latPad, lngPad) {
  return {
    north: bounds.north + latPad,
    south: bounds.south - latPad,
    east: bounds.east + lngPad,
    west: bounds.west - lngPad,
  };
}

export function toBoundsLiteral(bounds) {
  const ne = bounds.getNorthEast();
  const sw = bounds.getSouthWest();
  return { north: ne.lat(), south: sw.lat(), east: ne.lng(), west: sw.lng() };
}

export function extendBoundsFromGeometry(bounds, geometry) {
  const type = geometry.getType();
  if (type === "Point") {
    bounds.extend(geometry.get());
    return;
  }
  if (type === "MultiPoint" || type === "LineString" || type === "LinearRing") {
    geometry.getArray().forEach((latLng) => bounds.extend(latLng));
    return;
  }
  if (type === "Polygon" || type === "MultiLineString") {
    geometry.getArray().forEach((inner) => extendBoundsFromGeometry(bounds, inner));
    return;
  }
  if (type === "MultiPolygon" || type === "GeometryCollection") {
    geometry.getArray().forEach((inner) => extendBoundsFromGeometry(bounds, inner));
  }
}

export function loadGoogleMaps(apiKey) {
  if (!apiKey) return Promise.reject(new Error("Missing GOOGLE_MAPS_API in .env."));
  if (window.google?.maps?.geometry) return Promise.resolve(window.google.maps);

  return new Promise((resolve, reject) => {
    const existing = document.getElementById("google-maps-js");
    if (existing) {
      existing.addEventListener("load", () => resolve(window.google.maps), { once: true });
      existing.addEventListener("error", () => reject(new Error("Google Maps failed to load.")), { once: true });
      return;
    }

    const script = document.createElement("script");
    script.id = "google-maps-js";
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(apiKey)}&libraries=geometry`;
    script.async = true;
    script.defer = true;
    script.onload = () => resolve(window.google.maps);
    script.onerror = () => reject(new Error("Google Maps failed to load."));
    document.head.appendChild(script);
  });
}

export function buildMarkerIcon(placeType) {
  return {
    path: window.google.maps.SymbolPath.CIRCLE,
    scale: 8,
    fillColor: PLACE_TYPE_COLORS[placeType] || "#6B7280",
    fillOpacity: 1,
    strokeColor: "#ffffff",
    strokeWeight: 2,
  };
}