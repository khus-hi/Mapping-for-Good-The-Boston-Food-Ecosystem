# FoodShed Boston — Food Equity Explorer

An interactive mapping application that visualizes food access and equity across Boston neighborhoods. Users can search for food distributors, farmers markets, and community resources by location, filter by type, and compare neighborhood-level food equity metrics.

---

## Features

- **Map Search** — Search food resources by address or drop a pin; filter by place type, neighborhood, or keyword
- **Radius Search** — Find all food distributors within a configurable mile radius of any point
- **Neighborhood Comparison** — Side-by-side comparison of food equity metrics across Boston neighborhoods
- **Income Inequality Layer** — Choropleth overlay showing poverty rate by neighborhood
- **Neighborhood Metrics** — Poverty rate, food access score, distributor counts, and more per neighborhood
- **Charts Modal** — Bar and line charts for neighborhood data powered by Recharts
- **AI Assistant** — Gemini-powered natural language search parsing and neighborhood Q&A
- **Language Support** — English and Spanish (selected on splash screen)

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | React 19 + Vite |
| Backend | Python 3 + Flask |
| Database | MongoDB Atlas |
| Maps | Google Maps JavaScript API |
| AI | Google Gemini API |
| Charts | Recharts |

---

## Project Structure

```
equitable-dev/
├── app.py                        # Flask backend — all API routes
├── index.html                    # Vite HTML entry point
├── package.json
├── requirements.txt
├── vite.config.mjs
├── seed.py                       # Database seeding script
│
├── src/                          # Frontend source
│   ├── App.jsx                   # Main app component
│   ├── main.jsx                  # React entry point
│   ├── styles.css                # All styles
│   ├── constants.js              # Shared constants and translations
│   ├── utils.js                  # Shared utility functions
│   ├── components/
│   │   ├── SplashScreen.jsx
│   │   ├── ComparisonDashboard.jsx
│   │   └── NeighborhoodChartsModal.jsx
│   ├── api/
│   │   └── mapApi.js
│   ├── config/
│   │   └── mapTiers.js
│   └── map/
│       ├── loadLeaflet.js
│       └── renderers.js
│
├── services/                     # Python backend services
│   ├── mongo.py                  # MongoDB queries
│   ├── gemini.py                 # Gemini AI integration
│   └── map_data.py               # Map data helpers
│
├── data/
│   ├── cleaned_data/             # Source CSVs
│   ├── boston_neighborhood_boundaries.geojson
│   ├── boston_neighborhood_socioeconomic_clean.csv
│   └── Income_inequality_index_PolicyMap.csv
│
├── parsers/                      # Data ingestion scripts
├── scripts/                      # Utility and seeding scripts
├── tests/                        # Parser verification tests
└── archive/prototype/            # Original vanilla JS prototype
```

---

## Getting Started

### Prerequisites

- Python 3.10+
- Node.js 18+
- MongoDB Atlas account
- Google Maps API key
- Google Gemini API key (optional — for AI search features)

### Environment Variables

Create a `.env` file in the project root:

```env
MONGO_URI=your_mongodb_connection_string
MONGO_CONNECTION=your_mongodb_connection_string
MONGO_DB=equitable
MONGO_COLLECTION=food-distributors
GOOGLE_MAPS_API=your_google_maps_api_key
GEMINI_API_KEY=your_gemini_api_key
```

### Installation

```bash
# Install Python dependencies
pip install -r requirements.txt

# Install Node dependencies
npm install
```

### Running the App

Open two terminals:

**Terminal 1 — Backend**
```bash
python app.py
# Runs on http://localhost:3000
```

**Terminal 2 — Frontend**
```bash
npm run dev
# Runs on http://localhost:5173
```

Open [http://localhost:5173](http://localhost:5173) in your browser.

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/farmers-markets` | All farmers market locations |
| GET | `/api/food-distributors` | Food distributors with optional filters |
| GET/POST | `/api/food-distributors/search-radius` | Distributors within radius of a point |
| GET | `/api/income-inequality` | Gini coefficient data by neighborhood |
| GET | `/api/neighborhood-stats` | Aggregate neighborhood statistics |
| GET | `/api/neighborhood-metrics` | Detailed metrics for a single neighborhood |
| GET | `/api/citywide-averages` | Citywide food access averages |
| POST | `/api/gemini/parse-search` | Parse a natural language search query |
| POST | `/api/gemini` | Ask Gemini about a neighborhood |

---

## Data

Food distributor and neighborhood data covers Boston and is stored in MongoDB Atlas. Source CSV files are in `data/cleaned_data/`. The `seed.py` script loads farmers market and income inequality data from CSVs. Full food distributor data is loaded via the ingestion scripts in `parsers/`.

Place types include: grocery stores, food pantries, corner stores, convenience stores, farmers markets, community gardens, WIC vendors, SNAP-authorized retailers, and restaurants.

---

## Contributing

1. Pull the latest from `main` before starting work
2. Create a feature branch
3. Make your changes and verify locally
4. Open a pull request with a brief description of what changed and why