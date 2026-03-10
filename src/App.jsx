import { useCallback, useEffect, useRef, useState } from "react";
import SplashScreen from "./components/SplashScreen";
import ComparisonDashboard from "./components/ComparisonDashboard";
import NeighborhoodChartsModal from "./components/NeighborhoodChartsModal";
import {
  TRANSLATIONS, BOSTON_CENTER, BOSTON_GEOJSON, COUNTY_COLOR,
  BASE_MAP_STYLES, MAP_THEME_STYLES, BOSTON_FALLBACK_BOUNDS, MASSACHUSETTS_BOUNDS,
  NEIGHBORHOOD_NAMES, PLACE_TYPE_COLORS, PLACE_TYPE_LABELS, CHIP_ACTIVE_TEXT_COLOR,
  GOOGLE_MAPS_API_KEY, MIN_RADIUS_MILES, DEFAULT_RADIUS_MILES, DEFAULT_LIMIT,
  DEFAULT_NEIGHBORHOOD_LIMIT, PREVIEW_SAMPLE_PCT, METERS_PER_MILE,
  AREA_PROMPT_PIN_PEEK_OFFSET_Y, PIN_CHANGE_EPSILON,
} from "./constants";
import {
  normalizeNeighborhood, isExcludedNeighborhoodForSearch, normalizePlaceTypesInput,
  giniToColor, darkenColor, getNeighborhoodName, hasPinMoved,
  polygonContainsLatLng, geometryContainsLatLng, getMapStyles,
  expandBoundsLiteral, toBoundsLiteral, extendBoundsFromGeometry,
  loadGoogleMaps, buildMarkerIcon,
} from "./utils";

// --- Component and constant definitions moved to:
// src/components/SplashScreen.jsx
// src/components/ComparisonDashboard.jsx
// src/components/NeighborhoodChartsModal.jsx
// src/constants.js
// src/utils.js

export default function App() {
  const mapElRef = useRef(null);
  const mapRef = useRef(null);
  const infoWindowRef = useRef(null);
  const bostonBoundsRef = useRef(null);
  const neighborhoodNamesRef = useRef(new Set());
  const activeMarkersRef = useRef([]);
  const incomeMapRef = useRef(new Map()); // neighborhood name → poverty rate
  const giniRangeRef = useRef({ min: 0.3, max: 0.55 });
  const showChoroplethRef = useRef(true);
  const pinMarkerRef = useRef(null);
  const centerMarkerRef = useRef(null);
  const radiusCircleRef = useRef(null);
  const hoveredNeighborhoodRef = useRef("");
  const runAreaSearchAtRef = useRef(async () => {});
  const runNeighborhoodViewRef = useRef(async () => {});
  const openAreaSearchPromptRef = useRef(() => {});
  const lastFeatureClickTsRef = useRef(0);
  const previewResultsScopeRef = useRef([]);
  const searchResultsScopeRef = useRef([]);
  const lastSearchRadiusRef = useRef(DEFAULT_RADIUS_MILES);

  const [showSplash, setShowSplash] = useState(true);
  const [lang, setLang] = useState("en");
  const langRef = useRef("en");
  const [activeTab, setActiveTab] = useState("map");
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");
  const mapTheme = "civic";
  const [mapScope, setMapScope] = useState("boston");
  const [showChoropleth, setShowChoropleth] = useState(true);
  const [showMbta, setShowMbta] = useState(false);
  const [mbtaStops, setMbtaStops] = useState([]);
  const mbtaMarkersRef = useRef([]);
  const mbtaPolylinesRef = useRef([]);
  const directionsRendererRef = useRef(null);
  const mbtaStopsRef = useRef([]);
  const [giniRange, setGiniRange] = useState({ min: 0.3, max: 0.55 });

  const [nlQuery, setNlQuery] = useState("");
  const [parsedIntent, setParsedIntent] = useState(null);
  const [nlSearching, setNlSearching] = useState(false);
  const [addressInput, setAddressInput] = useState("");
  const [selectedTypes, setSelectedTypes] = useState([]);
  const [radiusMiles, setRadiusMiles] = useState(String(DEFAULT_RADIUS_MILES));
  const [droppedPin, setDroppedPin] = useState(null);
  const [previewResults, setPreviewResults] = useState([]);
  const [searchResults, setSearchResults] = useState([]);
  const [searching, setSearching] = useState(false);
  const [hasSearched, setHasSearched] = useState(false);
  const [searchCenter, setSearchCenter] = useState(null);
  const [lastSearchSource, setLastSearchSource] = useState("");
  const [lastResolvedAddress, setLastResolvedAddress] = useState("");
  const [censusTrust, setCensusTrust] = useState(null);
  const [showCensusTrust, setShowCensusTrust] = useState(false);
  const [selectedNeighborhood, setSelectedNeighborhood] = useState("");
  const [neighborhoodMetrics, setNeighborhoodMetrics] = useState(null);
  const [metricsLoading, setMetricsLoading] = useState(false);
  const [metricsError, setMetricsError] = useState("");
  const [showChartsModal, setShowChartsModal] = useState(false);
  const [showCompareModal, setShowCompareModal] = useState(false);
  const [neighborhoodStatsExpanded, setNeighborhoodStatsExpanded] = useState(false);

  const applyMapViewportSettings = useCallback((scope, theme, fitToScope = false) => {
    const map = mapRef.current;
    if (!map) return;

    const scopeBounds =
      scope === "massachusetts"
        ? MASSACHUSETTS_BOUNDS
        : (bostonBoundsRef.current || BOSTON_FALLBACK_BOUNDS);

    map.setOptions({
      styles: getMapStyles(theme),
      restriction: { latLngBounds: scopeBounds, strictBounds: true },
      minZoom: scope === "massachusetts" ? 7 : 10,
      maxZoom: 17,
    });
    if (fitToScope) {
      const padding = scope === "massachusetts" ? 24 : 40;
      window.google.maps.event.addListenerOnce(map, "idle", () => {
        map.fitBounds(scopeBounds, padding);
        window.google.maps.event.trigger(map, "resize");
      });
    }
  }, []);

  const refreshRafRef = useRef(null);
  const refreshBoundaryStyles = useCallback(() => {
    if (!mapRef.current) return;
    if (refreshRafRef.current) return; // already scheduled
    refreshRafRef.current = requestAnimationFrame(() => {
      refreshRafRef.current = null;
      if (!mapRef.current) return;
      mapRef.current.data.setStyle((feature) => {
        const name = getNeighborhoodName(feature);
        const choropleth = showChoroplethRef.current;
        const rate = incomeMapRef.current.get(name);
        const { min, max } = giniRangeRef.current;

        let fillColor = COUNTY_COLOR;
        let fillOpacity = 0.2;

        if (choropleth && rate != null) {
          const t = Math.max(0, Math.min(1, (rate - min) / (max - min)));
          fillColor = giniToColor(t);
          fillOpacity = 0.7;
        }

        const isHovered = hoveredNeighborhoodRef.current === name;
        if (isHovered) {
          fillColor = darkenColor(fillColor, 0.14);
          fillOpacity = Math.min(0.9, fillOpacity + 0.12);
        }

        return {
          clickable: true,
          fillColor,
          fillOpacity,
          strokeColor: isHovered ? "#2f2f2f" : "#555",
          strokeOpacity: isHovered ? 0.85 : 0.5,
          strokeWeight: isHovered ? 1.6 : 1,
        };
      });
    });
  }, []);

  const clearResultMarkers = useCallback(() => {
    activeMarkersRef.current.forEach((marker) => marker.setMap(null));
    activeMarkersRef.current = [];
  }, []);

  const clearSearchOverlay = useCallback(() => {
    if (centerMarkerRef.current) {
      centerMarkerRef.current.setMap(null);
      centerMarkerRef.current = null;
    }
    if (radiusCircleRef.current) {
      radiusCircleRef.current.setMap(null);
      radiusCircleRef.current = null;
    }
  }, []);

  const buildFacilityInfoContent = useCallback((item) => {
    const wrapper = document.createElement("div");
    wrapper.className = "info-window";

    const title = document.createElement("strong");
    title.textContent = item.name || "Unknown";

    const typeTag = document.createElement("div");
    typeTag.className = "info-window-muted";
    typeTag.textContent = PLACE_TYPE_LABELS[item.place_type] || item.place_type || "Unknown Type";

    const address = document.createElement("div");
    address.textContent = item.address || item.city || "No address";

    const neighborhood = document.createElement("div");
    neighborhood.className = "info-window-muted";
    neighborhood.textContent = item.neighborhood || "";

    wrapper.appendChild(title);
    wrapper.appendChild(typeTag);
    wrapper.appendChild(address);
    if (item.neighborhood) wrapper.appendChild(neighborhood);

    // Get Directions button (only if pin is dropped)
    const pin = pinMarkerRef.current;
    if (pin && item.lat != null && item.lng != null) {
      const dirBtn = document.createElement("button");
      dirBtn.className = "info-window-search-btn";
      dirBtn.textContent = "🚇 Get Transit Directions";
      dirBtn.style.marginTop = "8px";
      dirBtn.addEventListener("click", () => {
        const map = mapRef.current;
        if (!map) return;

        // Clear previous route
        if (directionsRendererRef.current) {
          directionsRendererRef.current.setMap(null);
        }
        const renderer = new window.google.maps.DirectionsRenderer({
          suppressMarkers: false,
          polylineOptions: { strokeColor: "#0b6e4f", strokeWeight: 5 },
        });
        renderer.setMap(map);
        directionsRendererRef.current = renderer;

        const service = new window.google.maps.DirectionsService();
        const origin = pin.getPosition();
        service.route(
          {
            origin,
            destination: { lat: item.lat, lng: item.lng },
            travelMode: window.google.maps.TravelMode.TRANSIT,
          },
          (result, status) => {
            if (status === "OK") {
              renderer.setDirections(result);
            } else {
              alert("Could not find a transit route. Try enabling the Directions API in Google Cloud Console.");
            }
          }
        );
      });
      wrapper.appendChild(dirBtn);
    } else if (!pin) {
      const hint = document.createElement("div");
      hint.className = "info-window-muted";
      hint.style.marginTop = "6px";
      hint.textContent = "Drop a pin on the map to get transit directions.";
      wrapper.appendChild(hint);
    }

    return wrapper;
  }, []);

  const openFacilityInfo = useCallback((item, markerOverride = null) => {
    const map = mapRef.current;
    const infoWindow = infoWindowRef.current;
    if (!map || !infoWindow || !item) return;

    let marker = markerOverride;
    if (!marker) {
      marker = activeMarkersRef.current.find((candidate) => {
        const data = candidate.facilityData;
        return (
          data &&
          data.name === item.name &&
          data.place_type === item.place_type &&
          Number(data.lat) === Number(item.lat) &&
          Number(data.lng) === Number(item.lng)
        );
      }) || null;
    }

    infoWindow.setOptions({ pixelOffset: new window.google.maps.Size(0, 0) });
    infoWindow.setContent(buildFacilityInfoContent(item));

    if (marker) {
      infoWindow.open({ map, anchor: marker });
      return;
    }

    if (item.lat == null || item.lng == null) return;
    infoWindow.setPosition({ lat: item.lat, lng: item.lng });
    infoWindow.open({ map });
  }, [buildFacilityInfoContent]);

  const renderSearchOverlay = useCallback((center, radiusInMiles) => {
    const map = mapRef.current;
    clearSearchOverlay();
    if (!map || !center) return;

    centerMarkerRef.current = new window.google.maps.Marker({
      map,
      position: center,
      title: "Search center",
      clickable: false,
      icon: {
        path: window.google.maps.SymbolPath.CIRCLE,
        scale: 7,
        fillColor: "#B91C1C",
        fillOpacity: 1,
        strokeColor: "#ffffff",
        strokeWeight: 2,
      },
    });

    radiusCircleRef.current = new window.google.maps.Circle({
      map,
      center,
      radius: radiusInMiles * METERS_PER_MILE,
      clickable: false,
      strokeColor: "#B91C1C",
      strokeOpacity: 0.85,
      strokeWeight: 2,
      fillColor: "#FCA5A5",
      fillOpacity: 0.15,
    });
  }, [clearSearchOverlay]);

  const filterResultsByScope = useCallback((results) => {
    if (!Array.isArray(results)) return [];

    if (mapScope === "massachusetts") {
      return results.filter((item) => {
        if (item.lat == null || item.lng == null) return false;
        if (isExcludedNeighborhoodForSearch(item.neighborhood)) return false;
        return true;
      });
    }

    const bounds = bostonBoundsRef.current;
    const knownNeighborhoods = neighborhoodNamesRef.current;

    return results.filter((item) => {
      if (item.lat == null || item.lng == null) return false;
      if (isExcludedNeighborhoodForSearch(item.neighborhood)) return false;

      if (bounds) {
        const inBounds =
          item.lat <= bounds.north &&
          item.lat >= bounds.south &&
          item.lng <= bounds.east &&
          item.lng >= bounds.west;
        if (!inBounds) return false;
      }

      if (!knownNeighborhoods.size) return true;
      const neighborhood = String(item.neighborhood || "").trim();
      return neighborhood ? knownNeighborhoods.has(neighborhood) : false;
    });
  }, [mapScope]);

  const applyPlaceTypeFilter = useCallback((results, activePlaceTypes = selectedTypes) => {
    if (!Array.isArray(results)) return [];
    const normalized = normalizePlaceTypesInput(activePlaceTypes);
    if (!normalized.length) return results;

    const allowed = new Set(normalized);
    return results.filter((item) => allowed.has(item.place_type));
  }, [selectedTypes]);

  const placeMarkers = useCallback((results, center, radiusInMiles) => {
    const map = mapRef.current;
    if (!map) return;

    clearResultMarkers();
    renderSearchOverlay(center, radiusInMiles);

    results.forEach((item) => {
      if (item.lat == null || item.lng == null) return;

      const marker = new window.google.maps.Marker({
        map,
        position: { lat: item.lat, lng: item.lng },
        title: item.name,
        icon: buildMarkerIcon(item.place_type),
      });
      marker.facilityData = item;

      marker.addListener("click", () => {
        openFacilityInfo(item, marker);
      });

      activeMarkersRef.current.push(marker);
    });

    if (center) {
      const bounds = new window.google.maps.LatLngBounds();
      bounds.extend(center);
      results.forEach((item) => {
        if (item.lat == null || item.lng == null) return;
        bounds.extend({ lat: item.lat, lng: item.lng });
      });
      map.fitBounds(bounds, 90);
    }
  }, [clearResultMarkers, openFacilityInfo, renderSearchOverlay]);

  const focusNeighborhoodOnMap = useCallback((neighborhoodName) => {
    const map = mapRef.current;
    if (!map || !neighborhoodName) return false;

    const target = normalizeNeighborhood(neighborhoodName);
    const bounds = new window.google.maps.LatLngBounds();
    let found = false;

    map.data.forEach((feature) => {
      const name = getNeighborhoodName(feature);
      if (normalizeNeighborhood(name) !== target) return;

      const geometry = feature.getGeometry();
      if (!geometry) return;
      extendBoundsFromGeometry(bounds, geometry);
      found = true;
    });

    if (found && !bounds.isEmpty()) {
      map.fitBounds(bounds, 80);
    }
    return found;
  }, []);

  const restorePreview = useCallback(() => {
    const tr = TRANSLATIONS[langRef.current] || TRANSLATIONS.en;
    if (previewResults.length > 0) {
      placeMarkers(previewResults, null, DEFAULT_RADIUS_MILES);
      setStatus(tr.mapReadyShowing(previewResults.length, 0));
    } else {
      clearResultMarkers();
      clearSearchOverlay();
      setStatus(tr.mapReadyEnter);
    }
  }, [clearResultMarkers, clearSearchOverlay, placeMarkers, previewResults]);

  const getFocusedSearchRadiusMiles = useCallback(() => {
    const parsed = Number.parseFloat(radiusMiles);
    if (!Number.isFinite(parsed) || parsed < MIN_RADIUS_MILES) {
      return DEFAULT_RADIUS_MILES;
    }
    return parsed;
  }, [radiusMiles]);

  const runAreaSearchAt = useCallback(async (pin, areaLabel = "this area") => {
    if (!pin) return false;

    const radius = getFocusedSearchRadiusMiles();

    const activePlaceTypes = normalizePlaceTypesInput(selectedTypes);
    const payload = {
      pin,
      radius_miles: radius,
      limit: DEFAULT_LIMIT,
    };
    if (activePlaceTypes.length === 1) {
      payload.place_type = activePlaceTypes[0];
    } else if (activePlaceTypes.length > 1) {
      payload.place_types = activePlaceTypes;
    }

    setDroppedPin(pin);
    setSearching(true);
    setError("");
    setHasSearched(true);
    setLastSearchSource("pin");
    setLastResolvedAddress("");

    try {
      const response = await fetch("/api/food-distributors/search-radius", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.error || `Search failed (${response.status})`);
      }

      const rawResults = Array.isArray(data.results) ? data.results : [];
      const scopeFilteredResults = filterResultsByScope(rawResults);
      const filteredResults = applyPlaceTypeFilter(scopeFilteredResults, activePlaceTypes);
      const filteredOut = rawResults.length - filteredResults.length;

      searchResultsScopeRef.current = scopeFilteredResults;
      setSearchResults(filteredResults);
      setSearchCenter(data.search_center || pin);
      lastSearchRadiusRef.current = radius;
      placeMarkers(filteredResults, data.search_center || pin, radius);
      setStatus(
        `Found ${filteredResults.length} location(s) near ${areaLabel} (area search: ${radius} miles).${
          filteredOut > 0 ? ` ${filteredOut} outside current scope hidden.` : ""
        }`
      );
    } catch (err) {
      searchResultsScopeRef.current = [];
      setSearchResults([]);
      setSearchCenter(null);
      setHasSearched(false);
      restorePreview();
      setError(err.message || "Search failed");
      return false;
    } finally {
      setSearching(false);
    }
    return true;
  }, [applyPlaceTypeFilter, filterResultsByScope, getFocusedSearchRadiusMiles, placeMarkers, restorePreview, selectedTypes]);

  const openAreaSearchPrompt = useCallback((latLng, areaLabel = "this area", neighborhoodName = null) => {
    const map = mapRef.current;
    if (!map || !latLng || !infoWindowRef.current) return;

    const tr = TRANSLATIONS[langRef.current] || TRANSLATIONS.en;
    const radius = getFocusedSearchRadiusMiles();
    const wrapper = document.createElement("div");
    wrapper.className = "info-window";

    const title = document.createElement("strong");
    title.textContent = areaLabel;

    const hint = document.createElement("div");
    hint.className = "info-window-muted";
    hint.textContent = tr.areaSearchHintRadius(radius);

    const button = document.createElement("button");
    button.type = "button";
    button.className = "info-window-search-btn";
    button.textContent = "Search this area";
    button.disabled = searching;
    button.addEventListener("click", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const didStart = await runAreaSearchAtRef.current(
        { lat: latLng.lat(), lng: latLng.lng() },
        areaLabel
      );
      if (didStart) {
        infoWindowRef.current?.close();
      }
    });

    let viewNeighborhoodButton = null;
    if (neighborhoodName) {
      viewNeighborhoodButton = document.createElement("button");
      viewNeighborhoodButton.type = "button";
      viewNeighborhoodButton.className = "info-window-view-btn";
      viewNeighborhoodButton.textContent = tr.viewNeighborhoodBtn;
      viewNeighborhoodButton.disabled = searching;
      viewNeighborhoodButton.addEventListener("click", async (event) => {
        event.preventDefault();
        event.stopPropagation();
        await runNeighborhoodViewRef.current(neighborhoodName);
        infoWindowRef.current?.close();
      });
    }

    wrapper.appendChild(title);
    wrapper.appendChild(hint);
    wrapper.appendChild(button);
    if (viewNeighborhoodButton) wrapper.appendChild(viewNeighborhoodButton);

    infoWindowRef.current.setOptions({
      pixelOffset: new window.google.maps.Size(0, AREA_PROMPT_PIN_PEEK_OFFSET_Y),
    });
    infoWindowRef.current.setPosition(latLng);
    infoWindowRef.current.setContent(wrapper);
    infoWindowRef.current.open(map);
  }, [getFocusedSearchRadiusMiles, searching]);

  useEffect(() => {
    runAreaSearchAtRef.current = runAreaSearchAt;
  }, [runAreaSearchAt]);

  useEffect(() => {
    openAreaSearchPromptRef.current = openAreaSearchPrompt;
  }, [openAreaSearchPrompt]);

  useEffect(() => {
    applyMapViewportSettings(mapScope, mapTheme, false);
  }, [mapScope, mapTheme, applyMapViewportSettings]);

  useEffect(() => {
    if (showSplash) return;
    let active = true;

    async function init() {
      try {
        setStatus(t.loadingGoogleMaps);
        await loadGoogleMaps(GOOGLE_MAPS_API_KEY);
        if (!active || !mapElRef.current) return;

        const map = new window.google.maps.Map(mapElRef.current, {
          center: BOSTON_CENTER,
          zoom: 11,
          fullscreenControl: true,
          mapTypeControl: false,
          streetViewControl: false,
          styles: getMapStyles(mapTheme),
          gestureHandling: "greedy",
          isFractionalZoomEnabled: true,
        });

        mapRef.current = map;
        infoWindowRef.current = new window.google.maps.InfoWindow();
        window.google.maps.event.trigger(map, "resize");

        // Hide markers while zooming to reduce jank, restore on idle
        let zoomHideTimer = null;
        map.addListener("zoom_changed", () => {
          activeMarkersRef.current.forEach((m) => m.setVisible(false));
          clearTimeout(zoomHideTimer);
          zoomHideTimer = setTimeout(() => {
            activeMarkersRef.current.forEach((m) => m.setVisible(true));
          }, 150);
        });

        setStatus(t.loadingBoundaries);
        const [response, incomeRes] = await Promise.all([
          fetch(BOSTON_GEOJSON),
          fetch("/api/neighborhood-stats"),
        ]);
        const censusTrustRes = await fetch("/api/census-geographies?level=tract&city_scope=Boston&limit=5000");
        if (!response.ok) throw new Error(`Boundary file failed to load (${response.status}).`);

        if (incomeRes.ok) {
          const incomeData = await incomeRes.json();
          const incomeMap = new Map();
          incomeData.forEach((d) => {
            const name = d["name"]?.trim();
            const rate = parseFloat(d["poverty_rate"]);
            if (name && !isNaN(rate)) incomeMap.set(name, rate);
          });
          incomeMapRef.current = incomeMap;
          if (incomeMap.size > 0) {
            const values = [...incomeMap.values()];
            const min = Math.min(...values);
            const max = Math.max(...values);
            giniRangeRef.current = { min, max };
            setGiniRange({ min, max });
          }
        }

        if (censusTrustRes.ok) {
          const censusRows = await censusTrustRes.json();
          if (Array.isArray(censusRows) && censusRows.length > 0) {
            const first = censusRows[0] || {};
            const confidenceScores = censusRows
              .map((row) => row?.confidence?.score)
              .filter((value) => typeof value === "number" && Number.isFinite(value));
            const completenessScores = censusRows
              .map((row) => row?.completeness?.score)
              .filter((value) => typeof value === "number" && Number.isFinite(value));
            const avg = (values) =>
              values.length ? values.reduce((sum, value) => sum + value, 0) / values.length : null;

            setCensusTrust({
              tractCount: censusRows.length,
              vintage: first.vintage ?? null,
              source: first.source ?? null,
              lastUpdated: first.last_updated ?? null,
              confidenceAvg: avg(confidenceScores),
              completenessAvg: avg(completenessScores),
            });
          } else {
            setCensusTrust(null);
          }
        } else {
          setCensusTrust(null);
        }


        const geoJson = await response.json();
        map.data.addGeoJson(geoJson);
        const bounds = new window.google.maps.LatLngBounds();
        const names = new Set();
        map.data.forEach((feature) => {
          const featureName = getNeighborhoodName(feature);
          if (!isExcludedNeighborhoodForSearch(featureName)) {
            names.add(featureName);
          }
          const geometry = feature.getGeometry();
          if (geometry) extendBoundsFromGeometry(bounds, geometry);
        });
        neighborhoodNamesRef.current = names;
        if (!bounds.isEmpty()) {
          bostonBoundsRef.current = expandBoundsLiteral(toBoundsLiteral(bounds), 0.02, 0.03);
        }

        refreshBoundaryStyles();
        applyMapViewportSettings(mapScope, mapTheme, true);
        setTimeout(() => window.google.maps.event.trigger(map, "resize"), 100);

        const isLatLngInEligibleZone = (latLng) => {
          let inside = false;
          map.data.forEach((feature) => {
            if (inside) return;
            const name = getNeighborhoodName(feature);
            if (isExcludedNeighborhoodForSearch(name)) return;
            const geometry = feature.getGeometry();
            if (geometry && geometryContainsLatLng(geometry, latLng)) {
              inside = true;
            }
          });
          return inside;
        };

        const validateSelectionPoint = (latLng) => {
          const tr = TRANSLATIONS[langRef.current] || TRANSLATIONS.en;
          if (!isLatLngInEligibleZone(latLng)) {
            setError("");
            setStatus(tr.selectionInsideZonesOnly);
            return false;
          }
          return true;
        };

        map.data.addListener("click", async (event) => {
          lastFeatureClickTsRef.current = Date.now();
          const name = getNeighborhoodName(event.feature);
          if (isExcludedNeighborhoodForSearch(name)) {
            setDroppedPin(null);
            setSelectedNeighborhood(name);
            setNeighborhoodMetrics(null);
            setMetricsError("");
            setMetricsLoading(false);
            setStatus(`${name} has no locations and is excluded from search.`);
            infoWindowRef.current?.close();
            return;
          }

          if (!validateSelectionPoint(event.latLng)) {
            infoWindowRef.current?.close();
            return;
          }

          const nextPin = { lat: event.latLng.lat(), lng: event.latLng.lng() };
          setDroppedPin(nextPin);
          setSelectedNeighborhood(name);
          setMetricsError("");
          setMetricsLoading(true);
          openAreaSearchPromptRef.current(event.latLng, name, name);

          try {
            const metricsResponse = await fetch(
              `/api/neighborhood-metrics?name=${encodeURIComponent(name)}`
            );
            if (!metricsResponse.ok) {
              throw new Error(`Neighborhood metrics failed (${metricsResponse.status})`);
            }
            const metricsData = await metricsResponse.json();
            if (!active) return;
            setNeighborhoodMetrics(metricsData);
          } catch (err) {
            if (!active) return;
            setNeighborhoodMetrics(null);
            setMetricsError(err.message || t.metricsLoadFailed);
          } finally {
            if (active) setMetricsLoading(false);
          }

        });

        let hoverRafId = null;
        map.data.addListener("mouseover", (event) => {
          const name = getNeighborhoodName(event.feature);
          if (hoveredNeighborhoodRef.current === name) return;
          hoveredNeighborhoodRef.current = name;
          if (hoverRafId) cancelAnimationFrame(hoverRafId);
          hoverRafId = requestAnimationFrame(() => refreshBoundaryStyles());
        });

        map.data.addListener("mouseout", () => {
          if (hoveredNeighborhoodRef.current === "") return;
          hoveredNeighborhoodRef.current = "";
          if (hoverRafId) cancelAnimationFrame(hoverRafId);
          hoverRafId = requestAnimationFrame(() => refreshBoundaryStyles());
        });

        map.addListener("click", (event) => {
          if (Date.now() - lastFeatureClickTsRef.current < 120) return;
          if (!validateSelectionPoint(event.latLng)) {
            infoWindowRef.current?.close();
            return;
          }
          const nextPin = { lat: event.latLng.lat(), lng: event.latLng.lng() };
          setDroppedPin(nextPin);
          openAreaSearchPromptRef.current(event.latLng, "Selected area", null);
        });

        setStatus(t.loadingSampled);
        const previewResponse = await fetch(`/api/food-distributors?sample_pct=${PREVIEW_SAMPLE_PCT}`);
        if (!previewResponse.ok) {
          throw new Error(`Preview data failed to load (${previewResponse.status}).`);
        }
        const previewData = await previewResponse.json();
        if (!active) return;

        const previewRaw = Array.isArray(previewData) ? previewData : [];
        const scopeFilteredPreview = filterResultsByScope(previewRaw);
        const previewFiltered = applyPlaceTypeFilter(scopeFilteredPreview);
        const filteredOut = previewRaw.length - previewFiltered.length;

        previewResultsScopeRef.current = scopeFilteredPreview;
        setPreviewResults(previewFiltered);
        if (previewFiltered.length > 0) {
          placeMarkers(previewFiltered, null, DEFAULT_RADIUS_MILES);
          setStatus(t.mapReadyShowing(previewFiltered.length, filteredOut));
        } else {
          setStatus(t.mapReadyNone);
        }
      } catch (err) {
        if (!active) return;
        setError(err.message);
        setStatus(t.couldNotInit);
      }
    }

    init();
    return () => {
      active = false;
      clearResultMarkers();
      clearSearchOverlay();
      neighborhoodNamesRef.current = new Set();
      if (pinMarkerRef.current) {
        pinMarkerRef.current.setMap(null);
        pinMarkerRef.current = null;
      }
    };
  }, [
    applyMapViewportSettings,
    clearResultMarkers,
    clearSearchOverlay,
    mapTheme,
    applyPlaceTypeFilter,
    filterResultsByScope,
    placeMarkers,
    refreshBoundaryStyles,
    showSplash,
  ]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;

    if (!droppedPin) {
      if (pinMarkerRef.current) {
        pinMarkerRef.current.setMap(null);
        pinMarkerRef.current = null;
      }
      return;
    }

    if (!pinMarkerRef.current) {
      pinMarkerRef.current = new window.google.maps.Marker({
        map,
        position: droppedPin,
        title: "Dropped pin",
        icon: {
          // Teardrop pin shape
          path: "M12 2C8.13 2 5 5.13 5 9c0 5.1 6.2 11.8 6.46 12.08a.75.75 0 0 0 1.08 0C12.8 20.8 19 14.1 19 9c0-3.87-3.13-7-7-7z",
          scale: 1.2,
          fillColor: "#1D4ED8",
          fillOpacity: 1,
          strokeColor: "#0b3aa6",
          strokeWeight: 1.2,
          anchor: new window.google.maps.Point(12, 22),
        },
      });
    } else {
      pinMarkerRef.current.setPosition(droppedPin);
      pinMarkerRef.current.setMap(map);
    }
  }, [droppedPin]);

  async function runRadiusSearch(sourceHint, overrideAddress = null, overridePlaceTypes = null) {
    setError("");

    const parsedRadius = Number.parseFloat(radiusMiles);
    if (!Number.isFinite(parsedRadius) || parsedRadius < MIN_RADIUS_MILES) {
      setError(t.radiusMin(MIN_RADIUS_MILES));
      return;
    }

    const preferAddress = sourceHint === "address";
    const preferPin = sourceHint === "pin";
    const effectiveAddress = overrideAddress ?? addressInput;
    const hasAddress = effectiveAddress.trim().length > 0;
    const useAddress = preferAddress || (!preferPin && hasAddress);

    const payload = {
      radius_miles: parsedRadius,
      limit: DEFAULT_LIMIT,
    };
    const normalizedOverrideTypes = normalizePlaceTypesInput(overridePlaceTypes);
    const effectivePlaceTypes = normalizedOverrideTypes.length
      ? normalizedOverrideTypes
      : normalizePlaceTypesInput(selectedTypes);

    if (effectivePlaceTypes.length === 1) {
      payload.place_type = effectivePlaceTypes[0];
    } else if (effectivePlaceTypes.length > 1) {
      payload.place_types = effectivePlaceTypes;
    }

    if (useAddress) {
      if (!hasAddress) {
        setError(t.enterAddress);
        return;
      }
      payload.address = effectiveAddress.trim();
    } else {
      if (!droppedPin) {
        setError(t.dropPin);
        return;
      }
      payload.pin = droppedPin;
    }

    setSearching(true);
    setHasSearched(true);
    setLastResolvedAddress("");
    try {
      const response = await fetch("/api/food-distributors/search-radius", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.error || `Search failed (${response.status})`);
      }
      const rawResults = data.results || [];
      const scopeFilteredResults = filterResultsByScope(rawResults);
      const filteredResults = applyPlaceTypeFilter(scopeFilteredResults, effectivePlaceTypes);
      const filteredOut = rawResults.length - filteredResults.length;

      searchResultsScopeRef.current = scopeFilteredResults;
      setSearchResults(filteredResults);
      setSearchCenter(data.search_center || null);
      setLastSearchSource(data.search_source || (useAddress ? "address" : "pin"));
      if (data?.geocode?.formatted_address) {
        setLastResolvedAddress(data.geocode.formatted_address);
      }

      lastSearchRadiusRef.current = parsedRadius;
      placeMarkers(filteredResults, data.search_center || null, parsedRadius);
      setStatus(t.foundLocations(filteredResults.length, parsedRadius, filteredOut));
    } catch (err) {
      searchResultsScopeRef.current = [];
      setSearchResults([]);
      setSearchCenter(null);
      restorePreview();
      setError(err.message || "Search failed");
    } finally {
      setSearching(false);
    }
  }

  const runNeighborhoodView = useCallback(async (neighborhoodNameOverride = null) => {
    const tr = TRANSLATIONS[langRef.current] || TRANSLATIONS.en;
    const neighborhoodName = String(neighborhoodNameOverride ?? selectedNeighborhood ?? "").trim();
    if (!neighborhoodName) return;

    const activePlaceTypes = normalizePlaceTypesInput(selectedTypes);
    const params = new URLSearchParams({
      neighborhood: neighborhoodName,
      limit: String(DEFAULT_NEIGHBORHOOD_LIMIT),
    });
    if (activePlaceTypes.length === 1) {
      params.set("place_type", activePlaceTypes[0]);
    } else if (activePlaceTypes.length > 1) {
      params.set("place_types", activePlaceTypes.join(","));
    }

    setSearching(true);
    setError("");
    setHasSearched(true);
    setLastSearchSource("neighborhood");
    setLastResolvedAddress("");
    setSearchCenter(null);

    try {
      const response = await fetch(`/api/food-distributors?${params.toString()}`);
      const data = await response.json();
      if (!response.ok) {
        throw new Error(data?.error || `Neighborhood search failed (${response.status})`);
      }

      const rawResults = Array.isArray(data) ? data : [];
      const scopeFilteredResults = filterResultsByScope(rawResults);
      const filteredResults = applyPlaceTypeFilter(scopeFilteredResults, activePlaceTypes);
      const filteredOut = rawResults.length - filteredResults.length;

      searchResultsScopeRef.current = scopeFilteredResults;
      setSearchResults(filteredResults);
      clearSearchOverlay();
      placeMarkers(filteredResults, null, DEFAULT_RADIUS_MILES);
      focusNeighborhoodOnMap(neighborhoodName);
      setStatus(tr.viewingNeighborhood(filteredResults.length, neighborhoodName, filteredOut));
    } catch (err) {
      searchResultsScopeRef.current = [];
      setSearchResults([]);
      setSearchCenter(null);
      setHasSearched(false);
      restorePreview();
      setError(err.message || tr.neighborhoodViewFailed);
    } finally {
      setSearching(false);
    }
  }, [applyPlaceTypeFilter, clearSearchOverlay, filterResultsByScope, focusNeighborhoodOnMap, placeMarkers, restorePreview, selectedNeighborhood, selectedTypes]);

  useEffect(() => {
    runNeighborhoodViewRef.current = runNeighborhoodView;
  }, [runNeighborhoodView]);

  function clearSearchState() {
    searchResultsScopeRef.current = [];
    setSearchResults([]);
    setSearchCenter(null);
    setHasSearched(false);
    setLastSearchSource("");
    setLastResolvedAddress("");
    restorePreview();
  }

  async function runNlSearch() {
    if (!nlQuery.trim()) return;
    setNlSearching(true);
    setError("");
    setParsedIntent(null);
    try {
      const res = await fetch("/api/gemini/parse-search", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query: nlQuery }),
      });
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.error || `Gemini parse failed (${res.status})`);
      }
      const intent = await res.json();
      setParsedIntent(intent);
      // Apply extracted place_type as the active filter chip
      if (intent.place_type) setSelectedTypes([intent.place_type]);
      // Use extracted address or neighborhood for the radius search
      if (intent.address) {
        setAddressInput(intent.address);
        await runRadiusSearch(
          "address",
          intent.address,
          intent.place_type ? [intent.place_type] : null
        );
      } else if (intent.neighborhood) {
        setAddressInput(intent.neighborhood + ", Boston, MA");
        await runRadiusSearch(
          "address",
          intent.neighborhood + ", Boston, MA",
          intent.place_type ? [intent.place_type] : null
        );
      } else if (droppedPin) {
        await runRadiusSearch("pin", null, intent.place_type ? [intent.place_type] : null);
      } else {
        setError(t.geminiNoLocation);
      }
    } catch (err) {
      setError(err.message || t.smartSearchFailed);
    } finally {
      setNlSearching(false);
    }
  }

  function clearAll() {
    setNlQuery("");
    setParsedIntent(null);
    setAddressInput("");
    setSelectedTypes([]);
    setRadiusMiles(String(DEFAULT_RADIUS_MILES));
    setDroppedPin(null);
    clearSearchState();
  }

  function clearPinAndRadius() {
    setDroppedPin(null);
    clearSearchOverlay();
    clearSearchState();
    infoWindowRef.current?.close();
  }

  useEffect(() => {
    const filteredPreview = applyPlaceTypeFilter(previewResultsScopeRef.current);
    const filteredSearch = applyPlaceTypeFilter(searchResultsScopeRef.current);

    setPreviewResults(filteredPreview);
    setSearchResults(filteredSearch);

    if (hasSearched) {
      placeMarkers(filteredSearch, searchCenter || null, lastSearchRadiusRef.current);
    } else {
      placeMarkers(filteredPreview, null, DEFAULT_RADIUS_MILES);
    }
  }, [applyPlaceTypeFilter, hasSearched, placeMarkers, searchCenter, selectedTypes]);

  const formatMetric = (value, digits = 2) => {
    if (value == null || Number.isNaN(value)) return "N/A";
    return Number(value).toFixed(digits);
  };

  const formatTimestamp = (value) => {
    if (!value) return t.notAvailable;
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return date.toLocaleString();
  };

  const neighborhoodPovertyRate = selectedNeighborhood ? incomeMapRef.current.get(selectedNeighborhood) ?? null : null;
  const hasPinOrRadiusOnMap = Boolean(droppedPin || searchCenter);

  const shownCount = hasSearched ? searchResults.length : previewResults.length;

  const t = TRANSLATIONS[lang] || TRANSLATIONS.en;
  langRef.current = lang;

  useEffect(() => {
    if (!selectedNeighborhood) return;
    setNeighborhoodStatsExpanded(false);
  }, [selectedNeighborhood]);

  // Fetch MBTA stops + route lines, show/hide when toggle changes
  useEffect(() => {
    if (!mapRef.current) return;
    const map = mapRef.current;

    if (!showMbta) {
      mbtaMarkersRef.current.forEach((m) => m.setMap(null));
      mbtaPolylinesRef.current.forEach((p) => p.setMap(null));
      return;
    }

    if (mbtaStops.length === 0) {
      // Fetch stops and routes in parallel
      Promise.all([
        fetch("/api/mbta-stops").then((r) => r.json()),
        fetch("/api/mbta-routes").then((r) => r.json()),
      ]).then(([stops, routes]) => {
        if (!Array.isArray(stops)) return;
        setMbtaStops(stops);

        // Draw route polylines
        if (Array.isArray(routes)) {
          const polylines = routes.map((route) => {
            const path = window.google.maps.geometry.encoding.decodePath(route.polyline);
            return new window.google.maps.Polyline({
              path,
              map,
              strokeColor: route.color,
              strokeWeight: 3,
              strokeOpacity: 0.85,
              zIndex: 5,
            });
          });
          mbtaPolylinesRef.current = polylines;
        }

        // Draw stop markers with click info
        const mbtaInfoWindow = new window.google.maps.InfoWindow();
        const markers = stops.map((stop) => {
          const primaryColor = stop.colors?.[0] || "#888888";
          const marker = new window.google.maps.Marker({
            position: { lat: stop.lat, lng: stop.lng },
            map,
            title: stop.name,
            icon: {
              path: window.google.maps.SymbolPath.CIRCLE,
              scale: 6,
              fillColor: primaryColor,
              fillOpacity: 1,
              strokeColor: "#ffffff",
              strokeWeight: 2,
            },
            zIndex: 10,
          });

          marker.addListener("click", () => {
            const lines = stop.lines || [];
            const colors = stop.colors || [];
            const lineChips = lines.map((line, i) =>
              `<span style="display:inline-block;background:${colors[i] || "#888"};color:#fff;font-size:11px;font-weight:700;padding:2px 8px;border-radius:999px;margin-right:4px;">${line} Line</span>`
            ).join("");

            mbtaInfoWindow.setContent(`
              <div style="font-family:sans-serif;min-width:140px;">
                <strong style="font-size:13px;">${stop.name}</strong>
                <div style="margin-top:6px;">${lineChips || "MBTA Stop"}</div>
                ${stop.municipality ? `<div style="font-size:11px;color:#888;margin-top:4px;">${stop.municipality}</div>` : ""}
              </div>
            `);
            mbtaInfoWindow.open({ map, anchor: marker });
          });

          return marker;
        });
        mbtaMarkersRef.current = markers;
      }).catch(() => {});
    } else {
      mbtaMarkersRef.current.forEach((m) => m.setMap(map));
      mbtaPolylinesRef.current.forEach((p) => p.setMap(map));
    }
  }, [showMbta, mbtaStops]);

  const closeNeighborhoodCard = () => {
    setSelectedNeighborhood("");
    setNeighborhoodMetrics(null);
    setMetricsLoading(false);
    setMetricsError("");
    setNeighborhoodStatsExpanded(false);
  };

  const speakNeighborhood = async () => {
    if (!selectedNeighborhood || !neighborhoodMetrics) return;
    const m = neighborhoodMetrics;
    const pov = neighborhoodPovertyRate != null ? `${(neighborhoodPovertyRate * 100).toFixed(1)}%` : "N/A";
    const pop = m.population != null ? Number(m.population).toLocaleString() : "N/A";
    const text = langRef.current === "es"
      ? `${selectedNeighborhood}. Población: ${pop}. Tasa de pobreza: ${pov}. Restaurantes: ${m.counts?.restaurants ?? 0}. Supermercados: ${m.counts?.grocery_stores ?? 0}. Mercados agrícolas: ${m.counts?.farmers_markets ?? 0}. Bancos de alimentos: ${m.counts?.food_pantries ?? 0}.`
      : `${selectedNeighborhood}. Population: ${pop}. Poverty rate: ${pov}. Restaurants: ${m.counts?.restaurants ?? 0}. Grocery stores: ${m.counts?.grocery_stores ?? 0}. Farmers markets: ${m.counts?.farmers_markets ?? 0}. Food pantries: ${m.counts?.food_pantries ?? 0}.`;
    try {
      const res = await fetch("/api/tts", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, lang: langRef.current }),
      });
      if (!res.ok) throw new Error("TTS failed");
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.play();
    } catch {
      // fallback to browser speech
      const utt = new SpeechSynthesisUtterance(text);
      utt.lang = langRef.current === "es" ? "es-US" : "en-US";
      window.speechSynthesis.speak(utt);
    }
  };

  if (showSplash) return <SplashScreen onDone={(l) => { setLang(l); setShowSplash(false); }} />;

  return (
    <div className="shell">
      <aside className="panel">

        {/* ── Tab bar ── */}
        <div className="tab-bar">
          <button
            className={`tab ${activeTab === "map" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("map")}
          >{t.tabMap}</button>
          <button
            className={`tab ${activeTab === "compare" ? "tab-active" : ""}`}
            onClick={() => setActiveTab("compare")}
          >{t.tabCompare}</button>
        </div>

        {activeTab === "compare" ? <ComparisonDashboard lang={lang} /> : <>

        {/* ── Header ── */}
        <div className="panel-header">
          <p className="eyebrow">{t.eyebrow}</p>
          <h1>{t.headerTitle}</h1>
          <p className="lede">{t.headerLede}</p>
        </div>

        {/* ── Search ── */}
        <div className="panel-section">
          <div className="nl-search-box">
            <input
              className="search-input"
              type="text"
              placeholder={t.searchPlaceholder}
              value={nlQuery}
              onChange={(e) => setNlQuery(e.target.value)}
              onKeyDown={(e) => { if (e.key === "Enter") runNlSearch(); }}
            />
            <button
              className="search-btn"
              type="button"
              disabled={nlSearching || searching}
              onClick={runNlSearch}
            >
              {nlSearching ? t.searchBtnBusy : t.searchBtn}
            </button>
          </div>

          {nlSearching && <p className="nl-thinking">{t.nlThinking}</p>}

          {parsedIntent && (
            <div className="parsed-chips">
              {parsedIntent.place_type && (
                <span className="parsed-chip">{PLACE_TYPE_LABELS[parsedIntent.place_type] ?? parsedIntent.place_type}</span>
              )}
              {parsedIntent.neighborhood && (
                <span className="parsed-chip">{parsedIntent.neighborhood}</span>
              )}
              {parsedIntent.address && (
                <span className="parsed-chip">{parsedIntent.address}</span>
              )}
              {!parsedIntent.place_type && !parsedIntent.neighborhood && !parsedIntent.address && (
                <span className="parsed-chip parsed-chip-warn">{t.noLocationFound}</span>
              )}
            </div>
          )}

          {(lastSearchSource || lastResolvedAddress) && (
            <div className="search-meta">
              {lastResolvedAddress && <div>{t.resolved} {lastResolvedAddress}</div>}
              {searchCenter && <div>{t.center} {searchCenter.lat.toFixed(5)}, {searchCenter.lng.toFixed(5)}</div>}
            </div>
          )}
        </div>

        {/* ── Pin + Radius ── */}
        <div className="panel-section">
          <p className="section-label">{t.droppedPin}</p>
          <div className="pin-row">
            <span className={`pin-coords${droppedPin ? "" : " pin-coords-empty"}`}>
              {droppedPin ? `${droppedPin.lat.toFixed(5)}, ${droppedPin.lng.toFixed(5)}` : t.clickToPin}
            </span>
            <button className="pin-search-btn" type="button" disabled={searching} onClick={() => runRadiusSearch("pin")}>
              {t.searchPinBtn}
            </button>
            {hasPinOrRadiusOnMap && (
              <button className="pin-cancel-btn" type="button" disabled={searching} onClick={clearPinAndRadius}>
                Cancel
              </button>
            )}
          </div>
          <div className="radius-row">
            <span className="radius-label">{t.radiusMiles}</span>
            <input
              className="control-input"
              type="number"
              min={MIN_RADIUS_MILES}
              step="0.1"
              value={radiusMiles}
              onChange={(event) => setRadiusMiles(event.target.value)}
            />
          </div>
        </div>

        {/* ── Filters ── */}
        <div className="panel-section">
          <div className="filter-chips">
            {[
              { value: "", label: t.filterAll },
              { value: "farmers_market", label: t.filterFarmersMarkets },
              { value: "restaurant", label: t.filterRestaurants },
              { value: "grocery_store", label: t.filterGroceryStores },
              { value: "food_pantry", label: t.filterFoodPantries },
            ].map((option) => {
              const isActive =
                option.value === ""
                  ? selectedTypes.length === 0
                  : selectedTypes.includes(option.value);
              const typeColor = option.value ? PLACE_TYPE_COLORS[option.value] : null;

              let chipStyle = undefined;
              if (typeColor && isActive) {
                chipStyle = {
                  borderColor: typeColor,
                  background: typeColor,
                  color: CHIP_ACTIVE_TEXT_COLOR[option.value] || "#ffffff",
                };
              } else if (typeColor) {
                chipStyle = {
                  borderColor: `${typeColor}66`,
                  color: typeColor,
                };
              }

              return (
                <button
                  key={option.value}
                  className={`chip ${isActive ? "chip-active" : ""}`}
                  style={chipStyle}
                  type="button"
                  onClick={() => {
                    if (option.value === "") {
                      setSelectedTypes([]);
                      return;
                    }

                    setSelectedTypes((current) =>
                      current.includes(option.value)
                        ? current.filter((value) => value !== option.value)
                        : [...current, option.value]
                    );
                  }}
                >
                  {option.label}
                </button>
              );
            })}
          </div>
          <div className="meta-row">
            <button className="toggle-all" type="button" onClick={clearAll}>{t.clearAll}</button>
            <span className="count-pill">{shownCount} {t.shown}</span>
          </div>
        </div>

        {/* ── Map options ── */}
        <div className="panel-section">
          <div className="control-row">
            <span className="control-row-label">{t.mapScope}</span>
            <select className="control-input" value={mapScope} onChange={(e) => setMapScope(e.target.value)}>
              <option value="boston">{t.boston}</option>
              <option value="massachusetts">{t.massachusetts}</option>
            </select>
          </div>
          <button
            className={`choropleth-btn ${showChoropleth ? "choropleth-on" : ""}`}
            onClick={() => {
              const next = !showChoropleth;
              setShowChoropleth(next);
              showChoroplethRef.current = next;
              refreshBoundaryStyles();
            }}
          >
            {showChoropleth ? t.hidePoverty : t.showPoverty}
          </button>
          <button
            className={`choropleth-btn ${showMbta ? "choropleth-on" : ""}`}
            onClick={() => setShowMbta((v) => !v)}
          >
            {showMbta ? "Hide MBTA Stops" : "Show MBTA Stops"}
          </button>
          {showMbta && (
            <div style={{ fontSize: "0.72rem", color: "#6b6560", marginTop: "4px", display: "flex", flexWrap: "wrap", gap: "6px" }}>
              {[["Red", "#DA291C"], ["Orange", "#ED8B00"], ["Blue", "#003DA5"], ["Green", "#00843D"]].map(([name, color]) => (
                <span key={name} style={{ display: "flex", alignItems: "center", gap: "4px" }}>
                  <span style={{ display: "inline-block", width: 18, height: 3, background: color, borderRadius: 2 }} />
                  {name}
                </span>
              ))}
            </div>
          )}
          {showChoropleth && (
            <div className="choropleth-legend">
              <div className="choropleth-bar" />
              <div className="choropleth-labels">
                <span>{(giniRange.min * 100).toFixed(1)}% — {t.lower}</span>
                <span>{t.higher} — {(giniRange.max * 100).toFixed(1)}%</span>
              </div>
            </div>
          )}
        </div>

        {/* ── Status ── */}
        <p className={`status ${error ? "status-error" : ""}`}>{error || status}</p>

        {/* ── Legend ── */}
        <div className="panel-section">
          <div className="legend-row">
            <span className="legend-dot" style={{ background: "#F59E0B" }} /> {t.legendFarmersMarket}
            <span className="legend-dot" style={{ background: "#10B981" }} /> {t.legendRestaurant}
            <span className="legend-dot" style={{ background: "#3B82F6" }} /> {t.legendGrocery}
            <span className="legend-dot" style={{ background: "#1a1917" }} /> {t.legendFoodPantry}
          </div>
        </div>

        {hasSearched && (
          <section className="dataset">
            <h2>{t.inRadius}</h2>
            <p className="dataset-caption">
              {searching ? t.searching : `${searchResults.length} ${t.locationsInRange}`}
            </p>

            {!searching && searchResults.length === 0 && (
              <p className="dataset-caption">{t.noLocationsMatched}</p>
            )}

            <div className="dataset-list" role="list" aria-label="Radius search results">
              {searchResults.map((item, index) => (
                <div
                  key={`${item.name || "item"}-${index}`}
                  className="dataset-item dataset-item-clickable"
                  role="listitem"
                  onClick={() => {
                    if (!mapRef.current || item.lat == null || item.lng == null) return;
                    mapRef.current.panTo({ lat: item.lat, lng: item.lng });
                    if (mapRef.current.getZoom() < 15) mapRef.current.setZoom(15);
                    openFacilityInfo(item);
                  }}
                >
                  <span
                    className="result-dot"
                    style={{ background: PLACE_TYPE_COLORS[item.place_type] || "#6B7280" }}
                  />
                  <div className="result-text">
                    <span className="dataset-name">{item.name || "Unknown"}</span>
                    <span className="dataset-meta">{item.neighborhood || item.city || t.noNeighborhood}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        )}

        {censusTrust && (
          <div className="panel-section">
            <button
              type="button"
              className={`census-toggle${showCensusTrust ? " census-toggle-open" : ""}`}
              onClick={() => setShowCensusTrust((current) => !current)}
              aria-expanded={showCensusTrust}
            >
              <span className="census-toggle-arrow" aria-hidden>{showCensusTrust ? "▾" : "▸"}</span>
              <span className="census-toggle-label">{t.censusQualityTitle}</span>
            </button>
            {showCensusTrust && (
              <section className="dataset census-dataset">
                <div className="dataset-list" role="list">
                  <div className="dataset-item" role="listitem">
                    <span className="dataset-name">{t.sourceLabel}</span>
                    <span className="dataset-meta">
                      {censusTrust.source?.provider || censusTrust.source?.dataset || t.notAvailable}
                    </span>
                  </div>
                  <div className="dataset-item" role="listitem">
                    <span className="dataset-name">{t.censusRowsLabel}</span>
                    <span className="dataset-meta">
                      {censusTrust.tractCount ?? t.notAvailable}
                      {censusTrust.vintage ? ` · ${censusTrust.vintage}` : ""}
                    </span>
                  </div>
                  <div className="dataset-item" role="listitem">
                    <span className="dataset-name">{t.lastUpdatedLabel}</span>
                    <span className="dataset-meta">{formatTimestamp(censusTrust.lastUpdated)}</span>
                  </div>
                </div>
              </section>
            )}
          </div>
        )}
        </>}
      </aside>

      <main className="map-wrap">
        <div ref={mapElRef} className="map" aria-label="Boston neighborhood map" />
        {(selectedNeighborhood || metricsLoading || metricsError) && (
          <section className="map-neighborhood-card" aria-label="Selected neighborhood statistics">
            <div className="map-neighborhood-card-header">
              <div className="map-neighborhood-card-title-row">
                <h3>{selectedNeighborhood || t.neighborhoodMetrics}</h3>
                {neighborhoodMetrics && (
                  <div className="map-neighborhood-card-actions">
                    <button className="charts-btn" onClick={() => setShowChartsModal(true)}>View Charts</button>
                    <button className="charts-btn" onClick={() => setShowCompareModal(true)}>{t.tabCompare}</button>
                    <button className="charts-btn" onClick={speakNeighborhood} title="Read aloud">🔊</button>
                  </div>
                )}
              </div>
              <div className="map-neighborhood-card-header-controls">
                <button
                  type="button"
                  className="map-card-icon-btn"
                  aria-label={t.closeCard}
                  title={t.closeCard}
                  onClick={closeNeighborhoodCard}
                >
                  x
                </button>
              </div>
            </div>

            {metricsLoading && <p className="dataset-caption">{t.compareBtnBusy}</p>}
            {metricsError && <p className="dataset-caption">{metricsError}</p>}

            {!metricsLoading && neighborhoodMetrics && (
              <div className="map-neighborhood-card-body">
                <div className="dataset-item" role="listitem">
                  <span className="dataset-name">{t.population}</span>
                  <span className="dataset-meta">
                    {neighborhoodMetrics.population != null ? Number(neighborhoodMetrics.population).toLocaleString() : "N/A"}
                  </span>
                </div>
                <div className="dataset-item" role="listitem">
                  <span className="dataset-name">{t.povertyRate}</span>
                  <span className="dataset-meta">
                    {neighborhoodPovertyRate != null ? `${(neighborhoodPovertyRate * 100).toFixed(1)}%` : "N/A"}
                  </span>
                </div>
                <button
                  type="button"
                  className="map-neighborhood-card-expand-btn"
                  onClick={() => setNeighborhoodStatsExpanded((current) => !current)}
                >
                  {neighborhoodStatsExpanded ? t.hideMoreStats : t.showMoreStats}
                </button>
                {neighborhoodStatsExpanded && (
                  <div className="map-neighborhood-card-extra">
                    {[
                      [t.restaurants, "restaurants"],
                      [t.groceryStores, "grocery_stores"],
                      [t.farmersMarkets, "farmers_markets"],
                      [t.foodPantries, "food_pantries"],
                      [t.totalAccessPoints, "access_points"],
                    ].map(([label, key]) => (
                      <div className="dataset-item" role="listitem" key={`map-card-${key}`}>
                        <span className="dataset-name">{label}</span>
                        <span className="dataset-meta">
                          {neighborhoodMetrics.counts?.[key] ?? neighborhoodMetrics.totals?.[key] ?? 0}
                          {" · "}{t.per1k} {formatMetric(neighborhoodMetrics.per_1000?.[key])}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            )}
          </section>
        )}
      </main>

      {showChartsModal && neighborhoodMetrics && (
        <NeighborhoodChartsModal
          neighborhood={selectedNeighborhood}
          metrics={neighborhoodMetrics}
          onClose={() => setShowChartsModal(false)}
        />
      )}

      {showCompareModal && (
        <div className="modal-backdrop" onClick={() => setShowCompareModal(false)}>
          <div className="modal-card" style={{ maxWidth: "700px" }} onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <span className="modal-title">Compare Neighborhoods</span>
              <button className="modal-close" onClick={() => setShowCompareModal(false)} aria-label="Close">×</button>
            </div>
            <ComparisonDashboard lang={lang} />
          </div>
        </div>
      )}

    </div>
  );
}
