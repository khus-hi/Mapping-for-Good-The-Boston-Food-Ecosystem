const PLACE_TYPE_META = {
  farmers_market: { label: "Farmers Market", icon: "FM", color: "#f59e0b" },
  grocery_store: { label: "Grocery Store", icon: "GS", color: "#2563eb" },
  restaurant: { label: "Restaurant", icon: "RS", color: "#16a34a" },
  food_pantry: { label: "Food Pantry", icon: "FP", color: "#dc2626" },
  unknown: { label: "Other", icon: "OT", color: "#4b5563" },
};

function totalFromStats(stats = {}) {
  return (
    Number(stats.farmers_market_count || 0) +
    Number(stats.grocery_count || 0) +
    Number(stats.food_pantry_count || 0) +
    Number(stats.restaurant_count || 0)
  );
}

function neighborhoodFill(total, maxTotal) {
  if (!maxTotal) return "#dbeafe";
  const t = Math.max(0, Math.min(1, total / maxTotal));
  const r = Math.round(224 + (30 - 224) * t);
  const g = Math.round(242 + (64 - 242) * t);
  const b = Math.round(254 + (175 - 254) * t);
  return `rgb(${r}, ${g}, ${b})`;
}

function formatPlaceTypeCounts(counts = {}) {
  const parts = Object.entries(counts)
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
    .map(([k, v]) => `${k}: ${v}`);
  return parts.join(" | ");
}

export function renderNeighborhoodLayer(L, map, layerGroup, neighborhoods) {
  layerGroup.clearLayers();
  if (!Array.isArray(neighborhoods) || !neighborhoods.length) return { shown: 0 };

  const maxTotal = neighborhoods.reduce((max, n) => Math.max(max, totalFromStats(n.stats)), 0);

  neighborhoods.forEach((n) => {
    if (!n?.geometry) return;
    const total = totalFromStats(n.stats);
    const feature = {
      type: "Feature",
      properties: {
        neighborhood_id: n.neighborhood_id,
        name: n.name,
      },
      geometry: n.geometry,
    };

    const polygon = L.geoJSON(feature, {
      style: {
        color: "#1f2937",
        weight: 1,
        fillColor: neighborhoodFill(total, maxTotal),
        fillOpacity: 0.62,
      },
    });

    const summary = [
      `<strong>${n.name || "Unknown"}</strong>`,
      `Total access points: ${total}`,
      `Restaurants: ${n?.stats?.restaurant_count || 0}`,
      `Grocery stores: ${n?.stats?.grocery_count || 0}`,
      `Farmers markets: ${n?.stats?.farmers_market_count || 0}`,
      `Food pantries: ${n?.stats?.food_pantry_count || 0}`,
    ].join("<br/>");

    polygon.bindTooltip(summary, { sticky: true });
    polygon.on("click", () => {
      const bounds = polygon.getBounds();
      if (bounds.isValid()) map.fitBounds(bounds.pad(0.08));
    });

    polygon.addTo(layerGroup);
  });

  return { shown: neighborhoods.length };
}

export function renderClusterLayer(L, map, layerGroup, clusters) {
  layerGroup.clearLayers();
  if (!Array.isArray(clusters) || !clusters.length) return { shown: 0 };

  clusters.forEach((cluster) => {
    const [lng, lat] = cluster.coordinates || [];
    if (lat == null || lng == null) return;

    const count = Number(cluster.count || 0);
    const radius = Math.max(12, Math.min(34, 10 + Math.log2(Math.max(1, count)) * 4));

    const marker = L.circleMarker([lat, lng], {
      radius,
      color: "#111827",
      weight: 1,
      fillColor: "#0ea5e9",
      fillOpacity: 0.75,
    });

    marker.bindTooltip(
      `<strong>${count} locations</strong><br/>${formatPlaceTypeCounts(cluster.counts_by_place_type)}`,
      { sticky: true }
    );

    marker.on("click", () => {
      map.setView([lat, lng], Math.min((map.getZoom() || 12) + 2, 18));
    });

    marker.addTo(layerGroup);
  });

  return { shown: clusters.length };
}

function placeTypeMeta(placeType) {
  return PLACE_TYPE_META[placeType] || PLACE_TYPE_META.unknown;
}

export function renderPointLayer(L, layerGroup, points) {
  layerGroup.clearLayers();
  if (!Array.isArray(points) || !points.length) return { shown: 0 };

  points.forEach((item) => {
    const coords = item?.location?.coordinates || [];
    if (coords.length < 2) return;
    const lng = Number(coords[0]);
    const lat = Number(coords[1]);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) return;

    const meta = placeTypeMeta(item.place_type);
    const icon = L.divIcon({
      className: "place-marker-wrap",
      html: `<span class="place-marker" style="--place-color:${meta.color}">${meta.icon}</span>`,
      iconSize: [28, 28],
      iconAnchor: [14, 14],
    });

    const marker = L.marker([lat, lng], { icon });
    marker.bindTooltip(
      `<strong>${item.name || "Unknown"}</strong><br/>${meta.label}${
        item.subtype ? `<br/>${item.subtype}` : ""
      }`,
      { sticky: true }
    );
    marker.addTo(layerGroup);
  });

  return { shown: points.length };
}
