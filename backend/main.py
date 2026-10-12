"""
CampusWatch · FastAPI application
─────────────────────────────────
Owns: every endpoint in the API contract, CORS, static-file serving.
Teammate modules (db, simulator, detection, impact) are imported with
graceful stub fallbacks so the server can start before they land.
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

# ── Config (always local, owned by us) ──────────────────────────────────
from .config import (
    BASELINE_DAYS,
    BUILDINGS,
    CO2_KG_PER_KWH,
    ELEC_RATE_INR,
    RESOURCES,
    RESOURCE_UNITS,
    WATER_RATE_INR,
)

log = logging.getLogger("campuswatch")

# ── Stub-first imports ──────────────────────────────────────────────────
# Each teammate module is wrapped in try/except so the server boots
# immediately with fake data; swap in the real module by simply
# placing the .py file in backend/.
#
# Stubs return data that matches the contract shapes exactly.

# --- db.py ---------------------------------------------------------------
try:
    from .db import count_readings, get_readings, init_db, insert_readings  # noqa: F401
except ImportError:
    log.warning("db.py not found – using in-memory stub")

    _mem_store: List[Dict[str, Any]] = []

    def init_db() -> None:  # type: ignore[misc]
        pass

    def insert_readings(rows: List[Dict[str, Any]]) -> None:  # type: ignore[misc]
        _mem_store.extend(rows)

    def get_readings(  # type: ignore[misc]
        building: Optional[str] = None,
        resource: Optional[str] = None,
        hours: Optional[int] = 168,
    ) -> List[Dict[str, Any]]:
        now = datetime.now()
        cutoff = now - timedelta(hours=hours or 9999)
        return [
            r for r in _mem_store
            if (building is None or r["building"] == building)
            and (resource is None or r["resource"] == resource)
            and datetime.fromisoformat(r["ts"]) >= cutoff
        ]

    def count_readings() -> int:  # type: ignore[misc]
        return len(_mem_store)

# --- simulator.py --------------------------------------------------------
try:
    from .simulator import inject_leak, seed_history
except ImportError:
    log.warning("simulator.py not found – using no-op stubs")

    def seed_history(days: int = 14) -> None:  # type: ignore[misc]
        """Generate trivial flat readings so the dashboard isn't empty."""
        now = datetime.now().replace(minute=0, second=0, microsecond=0)
        rows: List[Dict[str, Any]] = []
        for h in range(days * 24, -1, -1):
            ts = (now - timedelta(hours=h)).isoformat()
            for b in BUILDINGS:
                rows.append({"building": b, "resource": "water",       "ts": ts, "value": 200.0})
                rows.append({"building": b, "resource": "electricity", "ts": ts, "value": 15.0})
        insert_readings(rows)

    def inject_leak(  # type: ignore[misc]
        building: str,
        resource: str,
        hours: int = 3,
        multiplier: float = 4.0,
    ) -> None:
        recent = get_readings(building=building, resource=resource, hours=hours + 2)
        if not recent:
            return
        for r in recent[-hours:]:
            r["value"] = round(r["value"] * multiplier, 2)
        insert_readings(recent[-hours:])

# --- detection.py --------------------------------------------------------
try:
    from .detection import detect_anomalies
except ImportError:
    log.warning("detection.py not found – using empty-list stub")

    def detect_anomalies(readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:  # type: ignore[misc]
        return []

# --- impact.py -----------------------------------------------------------
try:
    from .impact import compute_impact
except ImportError:
    log.warning("impact.py not found – using inline calculator")

    def compute_impact(anomaly: Dict[str, Any]) -> Dict[str, Any]:  # type: ignore[misc]
        resource = anomaly.get("resource", "water")
        hours = anomaly.get("hours", 1)
        excess_per_hour = max(0.0, anomaly.get("actual", 0) - anomaly.get("expected", 0))
        total_excess = round(excess_per_hour * hours, 2)
        unit = RESOURCE_UNITS.get(resource, "liters")
        if resource == "water":
            return {"excess": total_excess, "unit": unit,
                    "cost_inr": round(total_excess * WATER_RATE_INR, 2), "co2_kg": 0.0}
        return {"excess": total_excess, "unit": unit,
                "cost_inr": round(total_excess * ELEC_RATE_INR, 2),
                "co2_kg": round(total_excess * CO2_KG_PER_KWH, 2)}


# ── Filesystem paths ────────────────────────────────────────────────────
FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
INDEX_HTML = FRONTEND_DIR / "index.html"


# ── Pydantic request model ──────────────────────────────────────────────
class InjectLeakRequest(BaseModel):
    building: str
    resource: str


# ── Lifespan: init DB + seed once ───────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """On startup: create tables and, if the DB is empty, seed 14 days of
    simulated history plus two demo anomalies so judges see something
    immediately."""
    init_db()
    if count_readings() == 0:
        log.info("Empty database – seeding %d days of simulated meter history", BASELINE_DAYS)
        seed_history(days=BASELINE_DAYS)
        # Pre-inject demo anomalies so the first page-load has alerts
        inject_leak("Hostel A", "water", hours=3, multiplier=3.8)
        inject_leak("Academic Block", "electricity", hours=4, multiplier=3.2)
    yield


# ── FastAPI app ─────────────────────────────────────────────────────────
app = FastAPI(
    title="CampusWatch API",
    description="Detects abnormal water & electricity usage across a college campus.",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS – allow any origin so the dashboard works from file:// or any port
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Internal helpers ────────────────────────────────────────────────────

def _format_number(n: float) -> str:
    """Friendly number: 1050 → '1,050', 3.2 → '3.2'."""
    if n == int(n):
        return f"{int(n):,}"
    return f"{n:,.1f}"


def _build_alerts(max_age_days: int = 7) -> List[Dict[str, Any]]:
    """
    Core alert pipeline (used by /api/alerts, /api/buildings, /api/summary):
    1. Load the last 15 days of readings (14-day baseline + recent data).
    2. Run detect_anomalies() to get raw anomaly dicts.
    3. Keep only alerts whose end_ts falls within the last `max_age_days`.
    4. Attach compute_impact fields and a human-readable message.
    5. Sort newest-first by start_ts.
    """
    # 15 days = baseline window + 1 day of "recent" readings to detect
    all_readings = get_readings(hours=(BASELINE_DAYS + 1) * 24)
    raw_anomalies = detect_anomalies(all_readings)

    # Recency cutoff: only surface alerts that ended in the last 7 days
    now = datetime.now()
    if all_readings:
        try:
            last_ts_dt = datetime.fromisoformat(all_readings[-1]["ts"])
            if last_ts_dt.tzinfo is not None:
                last_ts_dt = last_ts_dt.astimezone(timezone.utc).replace(tzinfo=None)
            ref_dt = max(now, last_ts_dt)
        except Exception:
            ref_dt = now
    else:
        ref_dt = now
    cutoff = ref_dt - timedelta(days=max_age_days)

    enriched: List[Dict[str, Any]] = []
    for anom in raw_anomalies:
        try:
            end_dt = datetime.fromisoformat(anom["end_ts"])
            if end_dt.tzinfo is not None:
                end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except (ValueError, KeyError):
            continue
        if end_dt < cutoff:
            continue  # stale alert, skip

        imp = compute_impact(anom)

        # Compute ratio for the message (guard against zero expected)
        expected = max(anom["expected"], 0.01)
        ratio = round(anom["actual"] / expected, 1)

        # Human-readable message matching the spec example style
        if anom["resource"] == "water":
            msg = (
                f"{anom['building']} water usage was {ratio}x normal for "
                f"{anom['hours']} hour{'s' if anom['hours'] != 1 else ''} "
                f"(~{_format_number(imp['excess'])} liters wasted, "
                f"₹{_format_number(imp['cost_inr'])})"
            )
        else:
            msg = (
                f"{anom['building']} electricity usage was {ratio}x normal for "
                f"{anom['hours']} hour{'s' if anom['hours'] != 1 else ''} "
                f"(~{_format_number(imp['excess'])} kWh excess, "
                f"₹{_format_number(imp['cost_inr'])}, "
                f"{_format_number(imp['co2_kg'])} kg CO₂)"
            )

        enriched.append({
            "id":       anom["id"],
            "building": anom["building"],
            "resource": anom["resource"],
            "start_ts": anom["start_ts"],
            "end_ts":   anom["end_ts"],
            "hours":    anom["hours"],
            "expected": anom["expected"],
            "actual":   anom["actual"],
            "excess":   imp["excess"],
            "unit":     imp["unit"],
            "cost_inr": imp["cost_inr"],
            "co2_kg":   imp["co2_kg"],
            "message":  msg,
        })

    # Sort newest first
    enriched.sort(key=lambda a: a["start_ts"], reverse=True)
    return enriched


# ── Endpoints ───────────────────────────────────────────────────────────

@app.get("/")
def serve_index():
    """Serve frontend/index.html at the root URL."""
    if INDEX_HTML.exists():
        return FileResponse(str(INDEX_HTML), media_type="text/html")
    raise HTTPException(status_code=404, detail="frontend/index.html not found")


@app.get("/api/buildings")
def get_buildings() -> List[Dict[str, Any]]:
    """
    GET /api/buildings
    → [{name, status: "ok"|"alert", water_now, electricity_now}]

    Status is "alert" if ANY alert for that building overlaps the last 6 hours.
    """
    alerts = _build_alerts()

    # Determine reference time (latest reading ts or current time)
    recent = get_readings(hours=24)
    now = datetime.now()
    if recent:
        try:
            last_ts = datetime.fromisoformat(recent[-1]["ts"])
            if last_ts.tzinfo is not None:
                last_ts = last_ts.astimezone(timezone.utc).replace(tzinfo=None)
            ref_dt = max(now, last_ts)
        except Exception:
            ref_dt = now
    else:
        ref_dt = now

    # A building is "alert" if an alert's end_ts is within the last 6 hours
    six_hours_ago = ref_dt - timedelta(hours=6)
    alerting_buildings: set[str] = set()
    for a in alerts:
        try:
            end_dt = datetime.fromisoformat(a["end_ts"])
            if end_dt.tzinfo is not None:
                end_dt = end_dt.astimezone(timezone.utc).replace(tzinfo=None)
        except (ValueError, KeyError):
            continue
        if end_dt >= six_hours_ago:
            alerting_buildings.add(a["building"])

    # Index latest value per (building, resource)
    latest: Dict[tuple, float] = {}
    for r in recent:
        key = (r["building"], r["resource"])
        latest[key] = float(r["value"])  # readings are sorted ASC, last wins

    result = []
    for b in BUILDINGS:
        result.append({
            "name": b,
            "status": "alert" if b in alerting_buildings else "ok",
            "water_now": round(latest.get((b, "water"), 0.0), 1),
            "electricity_now": round(latest.get((b, "electricity"), 0.0), 1),
        })

    return result

get_buildings_endpoint = get_buildings


@app.get("/api/readings")
def get_readings_endpoint(
    building: Optional[str] = Query(default=None),
    resource: Optional[str] = Query(default=None),
    hours: int = Query(default=72),
) -> List[Dict[str, Any]]:
    """
    GET /api/readings?building=…&resource=…&hours=72
    → [{ts, value}]
    """
    rows = get_readings(building=building, resource=resource, hours=hours)
    return [{"ts": r["ts"], "value": r["value"]} for r in rows]


@app.get("/api/alerts")
def get_alerts() -> List[Dict[str, Any]]:
    """
    GET /api/alerts
    → [{id, building, resource, start_ts, end_ts, hours,
        expected, actual, excess, unit, cost_inr, co2_kg, message}]
    Newest first.  Only alerts whose end_ts is within the last 7 days.
    """
    return _build_alerts()

get_alerts_endpoint = get_alerts


@app.get("/api/summary")
def get_summary() -> Dict[str, Any]:
    """
    GET /api/summary
    → {total_cost_inr, total_co2_kg, total_water_liters, total_kwh, alert_count}
    """
    alerts = _build_alerts()

    total_cost  = round(sum(a["cost_inr"] for a in alerts), 2)
    total_co2   = round(sum(a["co2_kg"]   for a in alerts), 2)
    total_water = round(sum(a["excess"]   for a in alerts if a["resource"] == "water"), 2)
    total_kwh   = round(sum(a["excess"]   for a in alerts if a["resource"] == "electricity"), 2)

    return {
        "total_cost_inr":    total_cost,
        "total_co2_kg":      total_co2,
        "total_water_liters": total_water,
        "total_kwh":         total_kwh,
        "alert_count":       len(alerts),
    }

get_summary_endpoint = get_summary


@app.post("/api/inject-leak")
def post_inject_leak(req: InjectLeakRequest) -> Dict[str, bool]:
    """
    POST /api/inject-leak  body: {building, resource}
    → {ok: true}
    """
    if req.building not in BUILDINGS:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown building '{req.building}'. Valid: {BUILDINGS}",
        )
    if req.resource not in RESOURCES:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown resource '{req.resource}'. Valid: {RESOURCES}",
        )
    inject_leak(building=req.building, resource=req.resource, hours=3, multiplier=4.0)
    return {"ok": True}

    
@app.post("/api/reset")
def reset_demo():
    from backend.db import clear_readings
    from backend.simulator import seed_history
    clear_readings()
    seed_history(14)
    return {"ok": True}
    


# ── Static file serving ─────────────────────────────────────────────────
# Mount AFTER API routes so /api/* takes precedence.
# html=True serves index.html at "/".
if FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="frontend")
