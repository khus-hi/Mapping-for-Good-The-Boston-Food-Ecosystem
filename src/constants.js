export const TRANSLATIONS = {
  en: {
    tabMap: "Map Search", tabCompare: "Compare",
    eyebrow: "Boston Food Equity Explorer",
    headerTitle: "Smart Search",
    headerLede: 'Ask in plain language — "grocery stores in Roxbury" or "food pantry near Jamaica Plain".',
    searchPlaceholder: "e.g. grocery stores in Roxbury…",
    searchBtn: "Search", searchBtnBusy: "…",
    nlThinking: "Interpreting with Gemini AI…",
    noLocationFound: "No location found — using pin",
    resolved: "Resolved:", center: "Center:",
    droppedPin: "Dropped Pin", clickToPin: "Click map to drop a pin",
    searchPinBtn: "Search Pin", radiusMiles: "Radius (miles)",
    filterAll: "All", filterFarmersMarkets: "Farmers Markets",
    filterRestaurants: "Restaurants", filterGroceryStores: "Grocery Stores",
    filterFoodPantries: "Food Pantries", clearAll: "Clear all", shown: "shown",
    mapScope: "Map scope", boston: "Boston", massachusetts: "Massachusetts",
    hidePoverty: "Hide Poverty Rate Layer", showPoverty: "Show Poverty Rate Layer",
    lower: "Lower", higher: "Higher",
    legendFarmersMarket: "Farmers Market", legendRestaurant: "Restaurant",
    legendGrocery: "Grocery", legendFoodPantry: "Food Pantry",
    neighborhoodMetrics: "Neighborhood Metrics",
    closeCard: "Close card",
    showMoreStats: "Show more stats",
    hideMoreStats: "Hide more stats",
    population: "Population", avgGiniIndex: "Avg Gini Index",
    citywideAvgGini: "Citywide Avg Gini",
    restaurants: "Restaurants", groceryStores: "Grocery Stores",
    farmersMarkets: "Farmers Markets", foodPantries: "Food Pantries",
    totalAccessPoints: "Total Access Points", per1k: "per 1k:",
    inRadius: "In Radius", searching: "Searching...",
    locationsInRange: "location(s) in range",
    noLocationsMatched: "No locations matched this center + radius.",
    selectionInsideZonesOnly: "Select a point inside an eligible Boston neighborhood zone.",
    areaSearchNeedsPinMove: "Move the pin to a new point before searching this area.",
    areaSearchInsideActiveOnly: "Select a point inside the active search circle, or clear the current search first.",
    areaSearchHintActive: (r) => `Move the pin and search within the active ${r}-mile circle.`,
    areaSearchHintRadius: (r) => `Run a focused ${r}-mile search around this point (uses current Radius value).`,
    noNeighborhood: "No neighborhood",
    loadingMap: "Loading map...", loadingGoogleMaps: "Loading Google Maps...",
    loadingBoundaries: "Loading neighborhood boundaries...",
    loadingSampled: "Loading sampled locations...",
    mapReadyShowing: (n, f) => `Map ready. Showing ${n} sampled locations (10%).${f > 0 ? ` ${f} outside Boston hidden.` : ""} Enter an address or drop a pin.`,
    mapReadyEnter: "Map ready. Enter an address or drop a pin, then search by radius.",
    mapReadyNone: "Map ready. No in-Boston preview locations returned.",
    couldNotInit: "Could not initialize the map.",
    radiusMin: (min) => `Radius must be at least ${min} miles.`,
    enterAddress: "Enter an address before searching by address.",
    dropPin: "Drop a pin on the map before searching by pin.",
    foundLocations: (n, r, f) => `Found ${n} in-Boston location(s) within ${r} miles.${f > 0 ? ` ${f} outside Boston hidden.` : ""}`,
    geminiNoLocation: "Gemini couldn't find a location in your query. Try adding a neighborhood or address.",
    smartSearchFailed: "Smart search failed",
    metricsLoadFailed: "Failed to load neighborhood metrics.",
    compareTitle: "Compare Neighborhoods",
    compareLede: "Enter two neighborhoods to compare food access side by side.",
    comparePlaceholderA: "e.g. Roxbury", comparePlaceholderB: "e.g. Back Bay",
    compareBtn: "Compare", compareBtnBusy: "Loading…",
    compareBothRequired: "Enter both neighborhood names.",
    compareDifferent: "Choose two different neighborhoods.",
    overview: "Overview", povertyRate: "Poverty Rate", avgGini: "Avg Gini",
    foodLocationCounts: "Food Location Counts", per1000Residents: "Per 1,000 Residents",
    censusQualityTitle: "Census Tract Quality",
    sourceLabel: "Source",
    censusRowsLabel: "Tracts loaded",
    lastUpdatedLabel: "Last Updated",
    confidenceLabel: "Confidence",
    completenessLabel: "Completeness",
    notAvailable: "N/A",
    viewNeighborhoodBtn: "View This Neighborhood",
    viewingNeighborhood: (count, neighborhood, hidden) => `Showing ${count} location(s) in ${neighborhood}.${hidden > 0 ? ` ${hidden} outside current scope hidden.` : ""}`,
    neighborhoodViewFailed: "Neighborhood view failed",
  },
  es: {
    tabMap: "Búsqueda en Mapa", tabCompare: "Comparar",
    eyebrow: "Explorador de Equidad Alimentaria de Boston",
    headerTitle: "Búsqueda Inteligente",
    headerLede: 'Pregunta en lenguaje natural — "supermercados en Roxbury" o "banco de alimentos cerca de Jamaica Plain".',
    searchPlaceholder: "ej. supermercados en Roxbury…",
    searchBtn: "Buscar", searchBtnBusy: "…",
    nlThinking: "Interpretando con Gemini AI…",
    noLocationFound: "Ubicación no encontrada — usando pin",
    resolved: "Dirección:", center: "Centro:",
    droppedPin: "Pin Colocado", clickToPin: "Haz clic en el mapa para colocar un pin",
    searchPinBtn: "Buscar con Pin", radiusMiles: "Radio (millas)",
    filterAll: "Todos", filterFarmersMarkets: "Mercados Agrícolas",
    filterRestaurants: "Restaurantes", filterGroceryStores: "Supermercados",
    filterFoodPantries: "Bancos de Alimentos", clearAll: "Limpiar todo", shown: "mostrados",
    mapScope: "Alcance del mapa", boston: "Boston", massachusetts: "Massachusetts",
    hidePoverty: "Ocultar Capa de Pobreza", showPoverty: "Mostrar Capa de Pobreza",
    lower: "Menor", higher: "Mayor",
    legendFarmersMarket: "Mercado Agrícola", legendRestaurant: "Restaurante",
    legendGrocery: "Supermercado", legendFoodPantry: "Banco de Alimentos",
    neighborhoodMetrics: "Métricas del Vecindario",
    closeCard: "Cerrar tarjeta",
    showMoreStats: "Mostrar mas metricas",
    hideMoreStats: "Ocultar metricas extra",
    population: "Población", avgGiniIndex: "Índice Gini Promedio",
    citywideAvgGini: "Gini Promedio Ciudad",
    restaurants: "Restaurantes", groceryStores: "Supermercados",
    farmersMarkets: "Mercados Agrícolas", foodPantries: "Bancos de Alimentos",
    totalAccessPoints: "Puntos de Acceso Totales", per1k: "por 1k:",
    inRadius: "En el Radio", searching: "Buscando...",
    locationsInRange: "lugar(es) encontrado(s)",
    noLocationsMatched: "No se encontraron lugares en este radio.",
    selectionInsideZonesOnly: "Selecciona un punto dentro de una zona elegible de vecindario en Boston.",
    areaSearchNeedsPinMove: "Mueve el pin a un nuevo punto antes de buscar en esta área.",
    areaSearchInsideActiveOnly: "Selecciona un punto dentro del círculo activo, o limpia la búsqueda actual primero.",
    areaSearchHintActive: (r) => `Mueve el pin y busca dentro del círculo activo de ${r} millas.`,
    areaSearchHintRadius: (r) => `Realiza una búsqueda enfocada de ${r} millas alrededor de este punto (usa el radio actual).`,
    noNeighborhood: "Sin vecindario",
    loadingMap: "Cargando mapa...", loadingGoogleMaps: "Cargando Google Maps...",
    loadingBoundaries: "Cargando límites de vecindarios...",
    loadingSampled: "Cargando ubicaciones de muestra...",
    mapReadyShowing: (n, f) => `Mapa listo. Mostrando ${n} ubicaciones de muestra (10%).${f > 0 ? ` ${f} fuera de Boston ocultos.` : ""} Ingresa una dirección o coloca un pin.`,
    mapReadyEnter: "Mapa listo. Ingresa una dirección o coloca un pin para buscar por radio.",
    mapReadyNone: "Mapa listo. No se encontraron ubicaciones en Boston.",
    couldNotInit: "No se pudo inicializar el mapa.",
    radiusMin: (min) => `El radio debe ser al menos ${min} millas.`,
    enterAddress: "Ingresa una dirección antes de buscar.",
    dropPin: "Coloca un pin en el mapa antes de buscar.",
    foundLocations: (n, r, f) => `Se encontraron ${n} lugar(es) en Boston dentro de ${r} millas.${f > 0 ? ` ${f} fuera de Boston ocultos.` : ""}`,
    geminiNoLocation: "Gemini no pudo encontrar una ubicación. Intenta agregar un vecindario o dirección.",
    smartSearchFailed: "La búsqueda inteligente falló",
    metricsLoadFailed: "Error al cargar las métricas del vecindario.",
    compareTitle: "Comparar Vecindarios",
    compareLede: "Ingresa dos vecindarios para comparar el acceso a alimentos.",
    comparePlaceholderA: "ej. Roxbury", comparePlaceholderB: "ej. Back Bay",
    compareBtn: "Comparar", compareBtnBusy: "Cargando…",
    compareBothRequired: "Ingresa ambos nombres de vecindarios.",
    compareDifferent: "Elige dos vecindarios diferentes.",
    overview: "Resumen", povertyRate: "Tasa de Pobreza", avgGini: "Gini Promedio",
    foodLocationCounts: "Cantidad de Lugares de Comida", per1000Residents: "Por 1,000 Residentes",
    censusQualityTitle: "Calidad de Tractos Censales",
    sourceLabel: "Fuente",
    censusRowsLabel: "Tractos cargados",
    lastUpdatedLabel: "Última actualización",
    confidenceLabel: "Confianza",
    completenessLabel: "Completitud",
    notAvailable: "N/D",
    viewNeighborhoodBtn: "Ver Este Vecindario",
    viewingNeighborhood: (count, neighborhood, hidden) => `Mostrando ${count} lugar(es) en ${neighborhood}.${hidden > 0 ? ` ${hidden} fuera del alcance actual ocultos.` : ""}`,
    neighborhoodViewFailed: "La vista de vecindario falló",
  },
};

export const BOSTON_CENTER = { lat: 42.3601, lng: -71.0589 };
export const BOSTON_GEOJSON = "/data/boston_neighborhood_boundaries.geojson";
export const COUNTY_COLOR = "#2A9D8F";

export const BASE_MAP_STYLES = [
  { featureType: "poi", stylers: [{ visibility: "off" }] },
  { featureType: "poi.business", stylers: [{ visibility: "off" }] },
  { featureType: "transit.station", stylers: [{ visibility: "off" }] },
];

export const MAP_THEME_STYLES = {
  civic: [
    { elementType: "geometry", stylers: [{ color: "#f7f4ee" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#ffffff" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#d7e6f2" }] },
  ],
  gray: [
    { elementType: "geometry", stylers: [{ color: "#eceff1" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#d4dbe0" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#ffffff" }] },
  ],
  blueprint: [
    { elementType: "geometry", stylers: [{ color: "#e8f1f8" }] },
    { featureType: "water", elementType: "geometry", stylers: [{ color: "#b7d4ea" }] },
    { featureType: "road", elementType: "geometry", stylers: [{ color: "#f8fbff" }] },
  ],
};

export const BOSTON_FALLBACK_BOUNDS = {
  north: 42.431,
  south: 42.228,
  east: -70.986,
  west: -71.191,
};

export const MASSACHUSETTS_BOUNDS = {
  north: 42.88679,
  south: 41.18705,
  east: -69.85886,
  west: -73.50814,
};

export const NEIGHBORHOOD_NAMES = [
  "Allston","Back Bay","Beacon Hill","Brighton","Charlestown","Chinatown",
  "Dorchester","Downtown","East Boston","Fenway","Hyde Park","Jamaica Plain",
  "Mattapan","Mission Hill","North End","Roslindale","Roxbury","South Boston",
  "South End","West End","West Roxbury","Whittier Street","Longwood","East Boston",
];

export const EXCLUDED_SEARCH_NEIGHBORHOODS = new Set(["harbor islands"]);

export const PLACE_TYPE_COLORS = {
  farmers_market: "#F59E0B",
  restaurant: "#10B981",
  grocery_store: "#3B82F6",
  food_pantry: "#1a1917",
};

export const PLACE_TYPE_LABELS = {
  farmers_market: "Farmers Market",
  restaurant: "Restaurant",
  grocery_store: "Grocery Store",
};

export const CHIP_ACTIVE_TEXT_COLOR = {
  farmers_market: "#1f2937",
};

export const CHART_ITEMS = [
  { key: "restaurants",     label: "Restaurants", color: "#10B981" },
  { key: "grocery_stores",  label: "Grocery",     color: "#3B82F6" },
  { key: "farmers_markets", label: "Markets",     color: "#F59E0B" },
  { key: "food_pantries",   label: "Pantries",    color: "#1a1917" },
];

export const GOOGLE_MAPS_API_KEY =
  typeof __GOOGLE_MAPS_API__ === "string" ? __GOOGLE_MAPS_API__.trim() : "";

export const MIN_RADIUS_MILES = 0.1;
export const DEFAULT_RADIUS_MILES = 0.5;
export const DEFAULT_LIMIT = 350;
export const DEFAULT_NEIGHBORHOOD_LIMIT = 2000;
export const PREVIEW_SAMPLE_PCT = 0.1;
export const METERS_PER_MILE = 1609.344;
export const AREA_PROMPT_PIN_PEEK_OFFSET_Y = -18;
export const PIN_CHANGE_EPSILON = 1e-6;