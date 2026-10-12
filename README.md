# CampusWatch 🏛️💧⚡

**Hackathon MVP** — Intelligent detection of abnormal water and electricity usage across a college campus, visualized on a live dashboard with impact in **liters**, **rupees (₹)** and **CO₂ emissions**.

> Data is **simulated** for the demo (permitted by hackathon rules).  
> The architecture is designed to swap in real meter data via CSV upload or API with minimal changes.

---

## Quick Start

```bash
# 1. Clone / download the project
cd campus-watch

# 2. Install dependencies
pip install -r requirements.txt

# 3. Run the server
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload

# 4. Open the dashboard
#    http://127.0.0.1:8000
```

On first launch the server automatically:
1. Creates `campuswatch.db` (SQLite) with the `readings` table.
2. Seeds **14 days** of realistic hourly simulated meter data.
3. Pre-injects two demo anomalies (water leak in Hostel A, electricity waste in Academic Block).

---

## Project Structure

```
campus-watch/
├── backend/
│   ├── __init__.py        # Package marker
│   ├── config.py          # Constants: buildings, tariffs, CO₂ factor, thresholds
│   ├── db.py              # SQLite CRUD (init, upsert, query, count)
│   ├── simulator.py       # Diurnal consumption generator + leak injector
│   ├── detection.py       # Adaptive median-baseline anomaly detector
│   ├── impact.py          # Financial (₹) & environmental (CO₂) calculator
│   └── main.py            # FastAPI app: endpoints, CORS, static serving, stubs
├── frontend/
│   └── index.html         # Single-page dashboard (vanilla JS + Chart.js CDN)
├── campuswatch.db         # SQLite database (auto-created at runtime)
├── requirements.txt       # Python dependencies
└── README.md              # ← You are here
```

---

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET`  | `/api/buildings` | List of buildings with status (`ok` / `alert`) and latest meter values |
| `GET`  | `/api/readings?building=&resource=&hours=72` | Time-series readings for charts |
| `GET`  | `/api/alerts` | Detected anomaly incidents with impact, newest first |
| `GET`  | `/api/summary` | Aggregated campus-wide waste totals |
| `POST` | `/api/inject-leak` | Simulate a leak: `{"building": "...", "resource": "..."}` |

---

## Detection Logic

CampusWatch does **not** use fixed thresholds. For each `(building, resource)` pair:

1. **Baseline learning** — Computes the **median** consumption for each hour of the day (0–23), separately for weekdays and weekends, over the previous **14 days**.
2. **Dual-criteria trigger** — A reading is anomalous when:
   - `actual > 2.0 × expected`  AND
   - `(actual − expected) > MIN_EXCESS` (100 L/h for water, 3 kWh/h for electricity)
3. **Temporal merging** — Consecutive anomalous hours (≥ 2) are merged into a single incident with cumulative excess, cost, and CO₂.

Heavy usage that occurs at the **same time every day** becomes part of the baseline and is never flagged.

---

## Swapping In Real Data

The simulated data layer is cleanly separated in `simulator.py`. To use real meters:

- **CSV upload**: Insert rows via `db.insert_readings([{building, resource, ts, value}, ...])`.
- **API integration**: POST readings to a new endpoint, or schedule a cron job that calls `insert_readings`.
- **Delete** `simulator.py` — `main.py` will fall back to its built-in stub and run normally.

---

## Deploying to Render

1. Push to a Git repository (GitHub / GitLab).
2. Create a new **Web Service** on [render.com](https://render.com).
3. Set:
   - **Build command**: `pip install -r requirements.txt`
   - **Start command**: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - **Environment**: Python 3.11+
4. Render auto-deploys on every push.

> **Note**: SQLite stores data in `campuswatch.db` on the local filesystem.  
> On Render's free tier, the disk is **ephemeral** — data resets on each deploy.  
> For persistence, switch to PostgreSQL (Render offers a free managed instance).

### Deploying to Railway

1. Push to GitHub.
2. Create a new project on [railway.app](https://railway.app) → **Deploy from GitHub**.
3. Add a **Procfile** or set the start command:
   ```
   web: uvicorn backend.main:app --host 0.0.0.0 --port $PORT
   ```
4. Railway auto-detects `requirements.txt` and installs dependencies.

---

## Tech Stack & Open-Source Licenses (Required Disclosure)

| Library | License | Purpose |
|---------|---------|---------|
| [FastAPI](https://github.com/tiangolo/fastapi) | MIT | Web framework & REST API |
| [Uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | ASGI server |
| [Pydantic](https://github.com/pydantic/pydantic) | MIT | Request/response validation |
| [Pandas](https://github.com/pandas-dev/pandas) | BSD-3-Clause | Data wrangling (simulator, detection) |
| [NumPy](https://github.com/numpy/numpy) | BSD-3-Clause | Numerical computation (medians, noise) |
| [Chart.js](https://github.com/chartjs/Chart.js) | MIT | Frontend charting (CDN, no install) |
| [Plus Jakarta Sans](https://github.com/nicholasdavidson/Plus-Jakarta-Sans) | OFL-1.1 | UI typography (Google Fonts CDN) |
| [JetBrains Mono](https://github.com/JetBrains/JetBrainsMono) | OFL-1.1 | Monospace typography (Google Fonts CDN) |
| **Python** | PSF | Runtime (3.11+) |
| **SQLite** | Public Domain | Embedded database |

---

## Team

Built during **[Hackathon Name]** by **[Team Name]**.

---

## License

MIT — see the open-source table above for dependency licenses.
