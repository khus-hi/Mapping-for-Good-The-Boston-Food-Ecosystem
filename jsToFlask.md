# JS to Flask Migration

## What Changed

### Server: `server.js` → `app.py`

The original `server.js` was a Node.js HTTP server that:
- Manually parsed `.env` for the Google Maps API key
- Served static files with correct content-type headers
- Exposed `/config.js` to inject `window.APP_CONFIG` into the browser
- Protected against path traversal attacks

All of that was rewritten in Python using **Flask** in `app.py`. The behavior is identical, but Flask handles routing, static file serving, and responses more cleanly.

| server.js (Node) | app.py (Flask) |
|---|---|
| `http.createServer()` | `Flask(__name__)` |
| Manual `.env` parser | Same logic, ported to Python |
| `fs.readFile()` for static files | `send_from_directory()` |
| `/config.js` route | `@app.route("/config.js")` |
| Path traversal check via `path.normalize` | `Path.resolve().relative_to(ROOT)` |
| `server.listen(PORT)` | `app.run(port=PORT)` |

---

## What Was Added

### MongoDB Integration

The Flask server now connects to MongoDB using `pymongo`.

- `MONGO_URI` is loaded from `.env` (same pattern as `GOOGLE_MAPS_API`)
- The database is named `equitable`
- Two collections are used: `farmers_markets` and `income_inequality`

**New API endpoints:**

| Endpoint | Collection | Source CSV |
|---|---|---|
| `GET /api/farmers-markets` | `farmers_markets` | `data/cleaned_data/farmers_market.csv` |
| `GET /api/income-inequality` | `income_inequality` | `data/Income_inequality_index_PolicyMap.csv` |

### Seed Script: `seed.py`

Run once to load the CSV data files into MongoDB:

```bash
python seed.py
```

This drops and re-inserts both collections from the local CSV files.

---

## Vite Proxy

Since Vite (frontend, port 5173) and Flask (backend, port 3000) run as separate servers during development, `vite.config.mjs` was updated to proxy API requests to Flask:

```
/api/*      →  http://localhost:3000
/config.js  →  http://localhost:3000
```

This means React components can fetch data with simple paths:

```js
fetch("/api/farmers-markets")
fetch("/api/income-inequality")
```

No hardcoded ports or CORS issues.

---

## How to Run

**Requirements:**
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt   # flask, pymongo
npm install
```

**`.env` file:**
```
GOOGLE_MAPS_API=your_google_maps_key
MONGO_URI=mongodb+srv://user:password@cluster.mongodb.net/dbname
```

**Seed the database (once):**
```bash
python seed.py
```

**Start both servers (two terminals):**
```bash
# Terminal 1 — Flask
source .venv/bin/activate
python app.py

# Terminal 2 — Vite
npm run dev
```

Open **http://localhost:5173** in your browser.
