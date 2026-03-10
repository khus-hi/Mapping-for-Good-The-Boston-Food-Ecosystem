# Setup & Running the App

## 1. Environment Variables

Create a `.env` file in the project root with the following keys:

```
GOOGLE_MAPS_API=your_google_maps_api_key
MONGO_CONNECTION=your_mongodb_connection_string
GEMINI_API_KEY=your_gemini_api_key
CENSUS_API_KEY=optional_census_api_key
```

| Variable | Description |
|---|---|
| `GOOGLE_MAPS_API` | Google Maps JavaScript API key (enables the map) |
| `MONGO_CONNECTION` | MongoDB connection URI (e.g. `mongodb+srv://user:pass@cluster.mongodb.net/`) |
| `GEMINI_API_KEY` | Google Gemini API key (enables the AI neighborhood summaries) |
| `CENSUS_API_KEY` | Optional U.S. Census API key for higher rate limits when pulling ACS tract/block-group data |

---

## 2. Install Dependencies

### Python (backend)
```bash
pip install -r requirements.txt
```

### Node (frontend)
```bash
npm install
```

---

## 3. Run the App

You need **two terminals** running at the same time:

### Terminal 1 — Flask backend
```bash
python app.py
```
Runs at `http://localhost:3000`

### Terminal 2 — Vite frontend (dev mode)
```bash
npm run dev
```
Runs at `http://localhost:5173` (proxies API calls to Flask)

---

## 4. Seed the Database (first time only)

To load data into MongoDB:
```bash
python seed.py
```

### Pull ACS tract/block-group data (optional but recommended)
```bash
python scripts/pull_census_acs.py --city-scope Boston --state 25 --county 025
```
This writes to `census_geo_profiles` with trust metadata fields:
`source`, `last_updated`, `confidence`, `completeness`.

---

## API Endpoints

| Endpoint | Description |
|---|---|
| `GET /api/food-distributors` | All food locations (supports `?search=`, `?place_type=`, `?neighborhood=`) |
| `GET /api/farmers-markets` | Farmers markets only |
| `GET /api/income-inequality` | Income inequality data |
| `GET /api/neighborhood-stats` | Neighborhood poverty-rate data (+ source/trust metadata) |
| `GET /api/census-geographies` | Census tract/block-group ACS data (+ source/trust metadata) |
| `POST /api/gemini` | AI neighborhood summary (body: `{ neighborhood, context }`) |
