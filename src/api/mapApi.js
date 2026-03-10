function toQuery(params) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value == null || value === "") return;
    search.set(key, String(value));
  });
  return search.toString();
}

export async function fetchNeighborhoodStats({ city = "Boston", signal } = {}) {
  const query = toQuery({ city, geometry: 1 });
  const res = await fetch(`/api/map/neighborhood-stats?${query}`, { signal });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error || `Neighborhood request failed (${res.status})`);
  }
  return Array.isArray(data) ? data : [];
}

export async function fetchFoodUnits({ bounds, zoom, placeType = "", signal }) {
  const sw = bounds.getSouthWest();
  const ne = bounds.getNorthEast();

  const query = toQuery({
    swLat: sw.lat,
    swLng: sw.lng,
    neLat: ne.lat,
    neLng: ne.lng,
    zoom,
    place_type: placeType || null,
  });

  const res = await fetch(`/api/map/food-units?${query}`, { signal });
  const data = await res.json();
  if (!res.ok) {
    throw new Error(data?.error || `Food units request failed (${res.status})`);
  }
  return data;
}
