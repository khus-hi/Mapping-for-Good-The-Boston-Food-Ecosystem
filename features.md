Features implemented

---

## [2026-02-22] — In-Radius Result Click Popup (All Facility Types)
- Clicking any item in the **In radius** list now opens a Google Maps popup with facility details (name, type, address, neighborhood)
- List click now recenters to the exact facility location and opens the same info popup used by map marker clicks
- Implemented for all supported facility types (restaurants, grocery stores, farmers markets, food pantries), not just restaurants
- Added shared popup rendering/open logic so marker clicks and sidebar result clicks stay consistent

## [2026-02-22] — Neighborhood Comparison Modal (teammate integration)
- Integrated teammate's `ComparisonDashboard` component (originally a sidebar tab) into a modal
- "Compare" button appears next to "View Charts" in the neighborhood metrics panel header
- Modal shows two-neighborhood side-by-side comparison: population, poverty rate, Gini, food access counts, per-1k bars
- `CompareBar` component renders relative horizontal bars colored blue (A) vs amber (B)
- Dropdown autocomplete from `NEIGHBORHOOD_NAMES` list for both inputs
- Removed sidebar tab bar; comparison is now fully modal-based
- Tab/cmp CSS from teammate preserved in `src/styles.css`

## [2026-02-22] — Recharts Data Visualization Modal
- Installed `recharts` (40 packages)
- "View Charts" button appears in the neighborhood metrics panel header after clicking a neighborhood
- Modal opens with 3 visualizations powered by Recharts:
  1. **Grouped bar chart** — selected neighborhood vs Boston citywide average per 1,000 residents (color-coded by food type, citywide bars in gray)
  2. **Line chart** — top 20 neighborhoods city-wide comparison across all 4 food types, with a dashed green reference line marking the currently selected neighborhood
  3. **Gini progress bar** — neighborhood Gini vs citywide average (green = below avg, red = above)
- New backend: `get_citywide_food_averages()` in `services/mongo.py` — aggregates per-1k counts across all neighborhoods from MongoDB
- New endpoint: `GET /api/citywide-averages` returns `citywide_avg_per_1000` + `neighborhoods` series
- Modal styles: `.modal-backdrop`, `.modal-card`, `.modal-header`, `.modal-close`, `.modal-section`, `.modal-section-label`, `.gini-bar-track`, `.gini-bar-fill`, `.gini-bar-labels`
- Button style: `.charts-btn` (green outlined, fills on hover)

## [2026-02-22] — Smooth Map Zoom
- Enabled fractional zoom (`isFractionalZoomEnabled: true`) so zoom interpolates fluidly between levels instead of snapping
- Added `gestureHandling: "greedy"` so scroll/single-finger gestures respond immediately without modifier keys

## [2026-02-22] — Sidebar Redesign (Flat UI)
- Replaced floating card layout with clean section-divided panel (`border-bottom` dividers, no gradients)
- New CSS variables: `--bg`, `--paper`, `--ink`, `--ink-soft`, `--edge`, `--accent`, `--accent-light`
- All buttons flat solid color; only the choropleth gradient bar retains a gradient
- Sidebar width increased 15% → 414px
- Reorganized into sections: Header · Search · Pin+Radius · Filters · Map Options · Status · Legend · Neighborhood Metrics

## [2026-02-22] — Food Pantry Legend Dot
- Added black (`#1a1917`) dot for Food Pantry to the map legend row
- Added `food_pantry` to `PLACE_TYPE_COLORS` so markers render in black

## [2026-02-22] — Gemini Natural Language Search
- Replaced address-only search bar with a free-text NL input ("grocery stores in Roxbury")
- New `POST /api/gemini/parse-search` endpoint calls Gemini to extract `place_type`, `neighborhood`, and `address` from the query
- `parse_search_query()` added to `services/gemini.py` — prompts Gemini for JSON-only response, strips markdown fences, validates place type, falls back gracefully on parse error
- Frontend shows "Interpreting with Gemini AI…" while parsing, then renders parsed chips (e.g. "Grocery Store · Roxbury")
- Radius search fires automatically using extracted address or neighborhood + geocoding
- `clearAll()` resets NL query and parsed chips

## [2026-02-22] — Poverty Rate in Metrics Panel (replaces Gini display)
- Neighborhood metrics panel now shows **Poverty Rate** sourced from the same choropleth layer data (`/api/neighborhood-stats` → `boston_neighborhood_socioeconomic_clean.csv`)
- Removed Gini Index and Citywide Avg Gini rows from the sidebar panel; replaced with a single "Poverty Rate" row displaying e.g. `27.3%`
- Rate is read directly from `incomeMapRef` (already in memory from map load) — no extra API call
- `seed.py` database name corrected from `"equitable"` to `"food-distributors"` to match `services/mongo.py`

## [2026-02-22] — Neighborhood Metrics Panel
- Clicking any neighborhood boundary on the map loads metrics from `/api/neighborhood-metrics?name=...`
- Panel shows: Population, Poverty Rate, counts + per-1k rates for Restaurants / Grocery Stores / Farmers Markets / Food Pantries / Total Access Points
- Metrics panel only renders when a neighborhood is selected (or loading/error state)

## [2026-02-22 14:00] — Map Blank/Blur Fix
- Fixed map rendering blank on first load (required switching theme to trigger repaint)
- Root cause: map was initializing while splash screen was covering the container (0-size div)
- Fix: map init effect now waits for splash to dismiss before running (`showSplash` guard)
- Also deferred `fitBounds` to fire on the map's first `idle` event so tiles are fully painted

## [2026-02-22 12:53] — Splash Screen Animation
- Added a fullscreen loading splash screen that displays on app open
- Light green background (`#d5f0df`) with a market cart + map pin SVG icon
- Animations: cart drops and bounces in, map pin fades into cart, title and subtitle slide up
- Auto-dismisses after 2.8s with a fade-out transition into the main app
- Implemented as a `SplashScreen` React component in `src/App.jsx`
- Styles added to `src/styles.css`

## [2026-02-22] — Merge dev → main
- Merged dev branch into main, bringing all dev features into main
- Resolved conflicts keeping dev versions of `app.py` and `seed.py`

---

## Previously implemented

### Google Maps API
- Interactive map centered on Boston
- Neighborhood boundary overlays via GeoJSON
- Color-coded markers by place type (farmers markets, restaurants)

### Search & Filtering
- Search bar filters food distributors by name, description, or neighborhood
- Filter chips for place type and neighborhood selection
- Results list with location details shown in sidebar

### Gemini AI Summary
- `POST /api/gemini` endpoint powered by Google Gemini
- Takes neighborhood name + context (Gini index, nearby markets)
- Returns a 2–3 sentence food equity summary

The frontend should call:


POST /api/gemini
With this JSON body:


{
  "neighborhood": "Jamaica Plain",
  "context": {
    "gini": 0.48,
    "markets": ["Jamaica Plain Farmers Market", "Brookfield Farm CSA"]
  }
}
And it gets back:


{
  "response": "Jamaica Plain has a moderately high income inequality score of 0.48. The neighborhood has 2 farmers markets that accept SNAP-EBT, providing some food access for lower-income residents..."
}


example response : const res = await fetch("/api/gemini", {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    neighborhood: "Jamaica Plain",
    context: {
      gini: 0.48,
      markets: ["Jamaica Plain Farmers Market"]
    }
  })
});
const data = await res.json();
console.log(data.response); // AI-generated summary

