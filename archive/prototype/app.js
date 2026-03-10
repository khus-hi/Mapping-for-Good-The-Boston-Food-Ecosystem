const BOSTON_CENTER = { lat: 42.3601, lng: -71.0589 };
const NEIGHBORHOODS_PATH = "./data/boston_neighborhood_boundaries.geojson";
const BASE_MAP_STYLES = [
  {
    featureType: "poi",
    stylers: [{ visibility: "off" }],
  },
  {
    featureType: "poi.business",
    stylers: [{ visibility: "off" }],
  },
  {
    featureType: "transit.station",
    stylers: [{ visibility: "off" }],
  },
];

const state = {
  map: null,
  infoWindow: null,
  colorsByNeighborhood: new Map(),
  enabledNeighborhoods: new Set(),
  togglesByNeighborhood: new Map(),
  neighborhoodCount: 0,
};

const palette = [
  "#f94144",
  "#f3722c",
  "#f8961e",
  "#f9844a",
  "#f9c74f",
  "#90be6d",
  "#43aa8b",
  "#4d908e",
  "#577590",
  "#277da1",
  "#b56576",
  "#6d597a",
  "#355070",
  "#8ecae6",
  "#219ebc",
  "#ff006e",
  "#3a86ff",
  "#8338ec",
  "#06d6a0",
  "#118ab2",
  "#ef476f",
  "#ffd166",
  "#7f5539",
  "#588157",
  "#bc4749",
  "#2a9d8f",
  "#e76f51",
  "#264653",
];

const statusEl = document.getElementById("status");
const neighborhoodListEl = document.getElementById("neighborhood-list");
const toggleAllBtn = document.getElementById("toggle-all");

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? "#a60e1a" : "#5e583f";
}

function colorForIndex(index) {
  return palette[index % palette.length];
}

function getNeighborhoodName(feature) {
  const raw = feature.getProperty("name");
  if (typeof raw === "string" && raw.trim()) return raw.trim();
  return "Unknown Neighborhood";
}

function refreshStyles() {
  state.map.data.setStyle((feature) => {
    const neighborhood = getNeighborhoodName(feature);
    const visible = state.enabledNeighborhoods.has(neighborhood);
    const fill = state.colorsByNeighborhood.get(neighborhood) || "#888888";

    return {
      fillColor: fill,
      fillOpacity: visible ? 0.45 : 0,
      strokeColor: fill,
      strokeOpacity: visible ? 0.92 : 0,
      strokeWeight: visible ? 2 : 0,
      clickable: visible,
      zIndex: visible ? 2 : 1,
    };
  });
}

function updateToggleButton(name) {
  const toggle = state.togglesByNeighborhood.get(name);
  if (!toggle) return;
  const enabled = state.enabledNeighborhoods.has(name);
  toggle.classList.toggle("active", enabled);
  toggle.setAttribute("aria-pressed", String(enabled));
  const pill = toggle.querySelector(".pill");
  if (pill) pill.textContent = enabled ? "On" : "Off";
}

function updateToggleAllButton() {
  const allEnabled =
    state.enabledNeighborhoods.size > 0 &&
    state.enabledNeighborhoods.size === state.neighborhoodCount;
  toggleAllBtn.textContent = allEnabled ? "Turn All Off" : "Turn All On";
}

function setNeighborhoodEnabled(name, enabled) {
  if (enabled) state.enabledNeighborhoods.add(name);
  else state.enabledNeighborhoods.delete(name);

  updateToggleButton(name);
  updateToggleAllButton();
  refreshStyles();
}

function buildNeighborhoodToggles(neighborhoods) {
  neighborhoods.forEach((name, idx) => {
    const color = colorForIndex(idx);
    state.colorsByNeighborhood.set(name, color);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "neighborhood-toggle";
    button.style.setProperty("--swatch", color);
    button.setAttribute("aria-pressed", "false");

    const swatch = document.createElement("span");
    swatch.className = "swatch";
    swatch.setAttribute("aria-hidden", "true");

    const label = document.createElement("span");
    label.className = "label";
    label.textContent = name;

    const pill = document.createElement("span");
    pill.className = "pill";
    pill.textContent = "Off";

    button.appendChild(swatch);
    button.appendChild(label);
    button.appendChild(pill);
    button.addEventListener("click", () => {
      const enable = !state.enabledNeighborhoods.has(name);
      setNeighborhoodEnabled(name, enable);
    });

    neighborhoodListEl.appendChild(button);
    state.togglesByNeighborhood.set(name, button);
  });

  state.neighborhoodCount = neighborhoods.length;
  updateToggleAllButton();
}

function extendBoundsFromGeometry(bounds, geometry) {
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

async function loadNeighborhoodData() {
  const response = await fetch(NEIGHBORHOODS_PATH);
  if (!response.ok) throw new Error(`Neighborhood file failed to load (${response.status}).`);
  return response.json();
}

async function initMap() {
  state.map = new google.maps.Map(document.getElementById("map"), {
    center: BOSTON_CENTER,
    zoom: 11,
    mapTypeControl: false,
    streetViewControl: false,
    fullscreenControl: true,
    styles: BASE_MAP_STYLES,
  });
  state.infoWindow = new google.maps.InfoWindow();

  const geoJson = await loadNeighborhoodData();
  const features = state.map.data.addGeoJson(geoJson);

  const neighborhoods = Array.from(
    new Set(features.map((feature) => getNeighborhoodName(feature)))
  ).sort((a, b) => a.localeCompare(b));
  buildNeighborhoodToggles(neighborhoods);
  refreshStyles();

  const bounds = new google.maps.LatLngBounds();
  state.map.data.forEach((feature) => {
    const geometry = feature.getGeometry();
    if (geometry) extendBoundsFromGeometry(bounds, geometry);
  });
  if (!bounds.isEmpty()) {
    state.map.fitBounds(bounds, 40);
  }

  state.map.data.addListener("click", (event) => {
    const neighborhood = getNeighborhoodName(event.feature);
    if (!state.enabledNeighborhoods.has(neighborhood)) return;
    const content = document.createElement("strong");
    content.textContent = neighborhood;
    state.infoWindow.setPosition(event.latLng);
    state.infoWindow.setContent(content);
    state.infoWindow.open(state.map);
  });

  toggleAllBtn.addEventListener("click", () => {
    const enableAll = state.enabledNeighborhoods.size !== state.neighborhoodCount;
    state.colorsByNeighborhood.forEach((_, name) => {
      if (enableAll) state.enabledNeighborhoods.add(name);
      else state.enabledNeighborhoods.delete(name);
      updateToggleButton(name);
    });
    updateToggleAllButton();
    refreshStyles();
  });

  setStatus(
    `Map ready. ${state.neighborhoodCount} neighborhoods loaded. Toggle any neighborhood to highlight it.`
  );
}

function loadGoogleMapsScript(apiKey) {
  return new Promise((resolve, reject) => {
    const script = document.createElement("script");
    script.src = `https://maps.googleapis.com/maps/api/js?key=${encodeURIComponent(
      apiKey
    )}&callback=__googleMapsReady`;
    script.async = true;
    script.defer = true;
    script.onerror = () => reject(new Error("Google Maps script failed to load."));
    window.__googleMapsReady = () => resolve();
    document.head.appendChild(script);
  });
}

async function bootstrap() {
  const apiKey = window.APP_CONFIG && window.APP_CONFIG.GOOGLE_MAPS_API_KEY;
  if (!apiKey) {
    setStatus("Missing GOOGLE_MAPS_API in .env.", true);
    return;
  }

  try {
    setStatus("Loading Google Maps...");
    await loadGoogleMapsScript(apiKey);
    setStatus("Loading Boston neighborhood boundaries...");
    await initMap();
  } catch (error) {
    setStatus(error.message, true);
  }
}

bootstrap();
