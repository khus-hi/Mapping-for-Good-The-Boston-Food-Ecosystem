import { useState, useEffect } from "react";
import { TRANSLATIONS, NEIGHBORHOOD_NAMES } from "../constants";

function CompareBar({ label, valueA, valueB, format = (v) => (v ?? 0).toFixed(1) }) {
  const max = Math.max(valueA || 0, valueB || 0, 0.001);
  return (
    <div className="cmp-row">
      <span className="cmp-row-label">{label}</span>
      <div className="cmp-bars">
        <div className="cmp-bar-wrap">
          <div className="cmp-bar cmp-bar-a" style={{ width: `${((valueA || 0) / max) * 100}%` }} />
          <span className="cmp-val">{format(valueA)}</span>
        </div>
        <div className="cmp-bar-wrap">
          <div className="cmp-bar cmp-bar-b" style={{ width: `${((valueB || 0) / max) * 100}%` }} />
          <span className="cmp-val">{format(valueB)}</span>
        </div>
      </div>
    </div>
  );
}

export default function ComparisonDashboard({ lang }) {
  const t = TRANSLATIONS[lang] || TRANSLATIONS.en;
  const [nameA, setNameA] = useState("");
  const [nameB, setNameB] = useState("");
  const [dataA, setDataA] = useState(null);
  const [dataB, setDataB] = useState(null);
  const [povMap, setPovMap] = useState(new Map());
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/neighborhood-stats")
      .then((r) => r.json())
      .then((rows) => {
        const m = new Map();
        rows.forEach((r) => m.set(r.name, r.poverty_rate));
        setPovMap(m);
      })
      .catch(() => {});
  }, []);

  async function compare() {
    const a = nameA.trim();
    const b = nameB.trim();
    if (!a || !b) { setError(t.compareBothRequired); return; }
    if (a.toLowerCase() === b.toLowerCase()) { setError(t.compareDifferent); return; }
    setLoading(true);
    setError("");
    setDataA(null);
    setDataB(null);
    try {
      const [resA, resB] = await Promise.all([
        fetch(`/api/neighborhood-metrics?name=${encodeURIComponent(a)}`),
        fetch(`/api/neighborhood-metrics?name=${encodeURIComponent(b)}`),
      ]);
      const [mA, mB] = await Promise.all([resA.json(), resB.json()]);
      if (!resA.ok) throw new Error(mA?.error || `"${a}" not found`);
      if (!resB.ok) throw new Error(mB?.error || `"${b}" not found`);
      setDataA({ ...mA, poverty_rate: povMap.get(a) });
      setDataB({ ...mB, poverty_rate: povMap.get(b) });
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  const fmt = (v, d = 0) => v != null && !isNaN(v) ? Number(v).toLocaleString(undefined, { maximumFractionDigits: d }) : "N/A";
  const fmtPct = (v) => v != null ? `${(v * 100).toFixed(1)}%` : "N/A";
  const fmtDec = (v) => v != null ? Number(v).toFixed(2) : "N/A";

  const FOOD_KEYS = [
    { key: "restaurants",     label: t.restaurants },
    { key: "grocery_stores",  label: t.groceryStores },
    { key: "farmers_markets", label: t.farmersMarkets },
    { key: "food_pantries",   label: t.foodPantries },
  ];

  return (
    <div className="cmp-panel">
      <div className="panel-header">
        <p className="eyebrow">{t.eyebrow}</p>
        <h1>{t.compareTitle}</h1>
        <p className="lede">{t.compareLede}</p>
      </div>

      <div className="panel-section">
        <div className="cmp-inputs">
          <div className="cmp-input-wrap">
            <span className="cmp-badge cmp-badge-a">A</span>
            <input
              className="search-input"
              list="hood-list-a"
              placeholder={t.comparePlaceholderA}
              value={nameA}
              onChange={(e) => setNameA(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && compare()}
            />
            <datalist id="hood-list-a">
              {NEIGHBORHOOD_NAMES.map((n) => <option key={n} value={n} />)}
            </datalist>
          </div>
          <div className="cmp-input-wrap">
            <span className="cmp-badge cmp-badge-b">B</span>
            <input
              className="search-input"
              list="hood-list-b"
              placeholder={t.comparePlaceholderB}
              value={nameB}
              onChange={(e) => setNameB(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && compare()}
            />
            <datalist id="hood-list-b">
              {NEIGHBORHOOD_NAMES.map((n) => <option key={n} value={n} />)}
            </datalist>
          </div>
        </div>
        <button className="search-btn" style={{ width: "100%" }} onClick={compare} disabled={loading}>
          {loading ? t.compareBtnBusy : t.compareBtn}
        </button>
        {error && <p className="status status-error">{error}</p>}
      </div>

      {dataA && dataB && (
        <>
          <div className="cmp-header-row">
            <span className="cmp-hood-name cmp-hood-a">{dataA.neighborhood || nameA}</span>
            <span className="cmp-vs">vs</span>
            <span className="cmp-hood-name cmp-hood-b">{dataB.neighborhood || nameB}</span>
          </div>

          <div className="panel-section">
            <p className="section-label">{t.overview}</p>
            <table className="cmp-table">
              <thead>
                <tr>
                  <th></th>
                  <th className="cmp-th-a">{dataA.neighborhood || nameA}</th>
                  <th className="cmp-th-b">{dataB.neighborhood || nameB}</th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <td>{t.population}</td>
                  <td>{fmt(dataA.population)}</td>
                  <td>{fmt(dataB.population)}</td>
                </tr>
                <tr>
                  <td>{t.povertyRate}</td>
                  <td>{fmtPct(dataA.poverty_rate)}</td>
                  <td>{fmtPct(dataB.poverty_rate)}</td>
                </tr>
                <tr>
                  <td>{t.avgGini}</td>
                  <td>{fmtDec(dataA.income?.avg_gini_for_neighborhood)}</td>
                  <td>{fmtDec(dataB.income?.avg_gini_for_neighborhood)}</td>
                </tr>
                <tr>
                  <td>{t.totalAccessPoints}</td>
                  <td>{fmt(dataA.totals?.access_points)}</td>
                  <td>{fmt(dataB.totals?.access_points)}</td>
                </tr>
              </tbody>
            </table>
          </div>

          <div className="panel-section">
            <p className="section-label">{t.foodLocationCounts}</p>
            <div className="cmp-legend">
              <span className="cmp-swatch cmp-swatch-a" />{dataA.neighborhood || nameA}
              <span className="cmp-swatch cmp-swatch-b" style={{ marginLeft: "12px" }} />{dataB.neighborhood || nameB}
            </div>
            {FOOD_KEYS.map(({ key, label }) => (
              <CompareBar
                key={key}
                label={label}
                valueA={dataA.counts?.[key] ?? 0}
                valueB={dataB.counts?.[key] ?? 0}
                format={(v) => String(v ?? 0)}
              />
            ))}
          </div>

          <div className="panel-section">
            <p className="section-label">{t.per1000Residents}</p>
            {FOOD_KEYS.map(({ key, label }) => (
              <CompareBar
                key={key}
                label={label}
                valueA={dataA.per_1000?.[key] ?? 0}
                valueB={dataB.per_1000?.[key] ?? 0}
                format={(v) => Number(v ?? 0).toFixed(2)}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}