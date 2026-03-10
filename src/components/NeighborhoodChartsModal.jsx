import { useState, useEffect } from "react";
import {
  BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, Cell,
  LineChart, Line, Legend, CartesianGrid, ReferenceLine,
} from "recharts";
import { CHART_ITEMS } from "../constants";

export default function NeighborhoodChartsModal({ neighborhood, metrics, onClose }) {
  const [citywide, setCitywide] = useState(null);
  const [cwLoading, setCwLoading] = useState(true);

  useEffect(() => {
    fetch("/api/citywide-averages")
      .then((r) => r.json())
      .then((d) => setCitywide(d))
      .catch(() => setCitywide(null))
      .finally(() => setCwLoading(false));
  }, []);

  const per1k = metrics.per_1000 ?? {};
  const giniNeighborhood = metrics.income?.avg_gini_for_neighborhood;
  const giniCitywide     = metrics.income?.avg_gini_citywide;
  const giniAbove = giniNeighborhood != null && giniCitywide != null && giniNeighborhood > giniCitywide;
  const giniPct   = giniNeighborhood != null ? Math.min(giniNeighborhood / 0.7, 1) * 100 : null;

  const cwAvg = citywide?.citywide_avg_per_1000 ?? {};
  const groupedData = CHART_ITEMS.map((item) => ({
    name: item.label,
    neighborhood: Number((per1k[item.key] ?? 0).toFixed(2)),
    citywide: Number((cwAvg[item.key] ?? 0).toFixed(2)),
    color: item.color,
  }));

  const lineData = (citywide?.neighborhoods ?? []).slice(0, 20).map((n) => ({
    name: n.neighborhood.length > 12 ? n.neighborhood.slice(0, 11) + "…" : n.neighborhood,
    Restaurants: n.restaurant ?? 0,
    Grocery: n.grocery_store ?? 0,
    Markets: n.farmers_market ?? 0,
    Pantries: n.food_pantry ?? 0,
    _isSelected: n.neighborhood.toLowerCase() === neighborhood.toLowerCase(),
  }));

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <span className="modal-title">{neighborhood} — Food Access Charts</span>
          <button className="modal-close" onClick={onClose} aria-label="Close">×</button>
        </div>

        <div className="modal-section">
          <p className="modal-section-label">Food Access — Neighborhood vs Boston Avg (per 1,000 residents)</p>
          {cwLoading ? (
            <p style={{ fontSize: "0.78rem", color: "#6b6560", fontStyle: "italic" }}>Loading citywide data…</p>
          ) : (
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={groupedData} margin={{ top: 4, right: 8, left: -16, bottom: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2ddd6" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip formatter={(v, name) => [v, name === "neighborhood" ? neighborhood : "Boston Avg"]} />
                <Legend formatter={(v) => v === "neighborhood" ? neighborhood : "Boston Avg"} wrapperStyle={{ fontSize: 11 }} />
                <Bar dataKey="neighborhood" radius={[3, 3, 0, 0]}>
                  {groupedData.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                </Bar>
                <Bar dataKey="citywide" fill="#d1c9be" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          )}
        </div>

        {!cwLoading && lineData.length > 0 && (
          <div className="modal-section">
            <p className="modal-section-label">City-wide Comparison — Per 1,000 Residents (top 20 neighborhoods)</p>
            <ResponsiveContainer width="100%" height={220}>
              <LineChart data={lineData} margin={{ top: 4, right: 8, left: -16, bottom: 40 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e2ddd6" />
                <XAxis dataKey="name" tick={{ fontSize: 9 }} angle={-40} textAnchor="end" interval={0} />
                <YAxis tick={{ fontSize: 11 }} />
                <Tooltip />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="Restaurants" stroke="#10B981" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="Grocery"     stroke="#3B82F6" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="Markets"     stroke="#F59E0B" dot={false} strokeWidth={2} />
                <Line type="monotone" dataKey="Pantries"    stroke="#1a1917" dot={false} strokeWidth={2} />
                {lineData.findIndex((d) => d._isSelected) >= 0 && (
                  <ReferenceLine
                    x={lineData.find((d) => d._isSelected)?.name}
                    stroke="#0b6e4f"
                    strokeWidth={2}
                    strokeDasharray="4 2"
                    label={{ value: "← here", position: "top", fontSize: 9, fill: "#0b6e4f" }}
                  />
                )}
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {giniPct != null && (
          <div className="modal-section">
            <p className="modal-section-label">Income Inequality (Gini Index)</p>
            <div className="gini-bar-track">
              <div
                className="gini-bar-fill"
                style={{ width: `${giniPct}%`, background: giniAbove ? "#b5001f" : "#0b6e4f" }}
              />
            </div>
            <div className="gini-bar-labels">
              <span>{neighborhood}: {giniNeighborhood?.toFixed(3)}</span>
              {giniCitywide != null && <span>Citywide avg: {giniCitywide?.toFixed(3)}</span>}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}