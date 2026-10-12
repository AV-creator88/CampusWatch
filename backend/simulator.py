"""
Meter data simulator for CampusWatch.
Generates realistic hourly diurnal consumption profiles across campus buildings
and injects anomalies (leaks, appliances left running) for demonstration.
"""

from datetime import datetime, timedelta
import math
import random
from typing import List, Dict, Any, Optional
import numpy as np

from .config import (
    BUILDINGS,
    RESOURCES,
    MIN_EXCESS,
    BASELINE_DAYS,
)
from .db import insert_readings, get_readings


# Typical base consumption and peak factors per building and resource
# Water in liters/hour, Electricity in kWh/hour
BUILDING_PROFILES = {
    "Hostel A": {
        "water": {"base": 120, "peak": 650, "peak_hours": [7, 8, 9, 19, 20, 21, 22]},
        "electricity": {"base": 8, "peak": 32, "peak_hours": [18, 19, 20, 21, 22, 23, 0]},
    },
    "Hostel B": {
        "water": {"base": 110, "peak": 620, "peak_hours": [7, 8, 9, 19, 20, 21, 22]},
        "electricity": {"base": 7.5, "peak": 30, "peak_hours": [18, 19, 20, 21, 22, 23, 0]},
    },
    "Library": {
        "water": {"base": 20, "peak": 120, "peak_hours": [11, 12, 13, 14, 15, 16, 17]},
        "electricity": {"base": 4, "peak": 42, "peak_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20]},
    },
    "Academic Block": {
        "water": {"base": 30, "peak": 280, "peak_hours": [10, 11, 12, 13, 14, 15, 16]},
        "electricity": {"base": 6, "peak": 55, "peak_hours": [9, 10, 11, 12, 13, 14, 15, 16, 17]},
    },
    "Canteen": {
        "water": {"base": 60, "peak": 750, "peak_hours": [7, 8, 12, 13, 14, 19, 20, 21]},
        "electricity": {"base": 5, "peak": 38, "peak_hours": [7, 8, 12, 13, 14, 19, 20, 21]},
    },
}


def _get_hourly_profile_value(
    building: str, resource: str, hour: int, is_weekend: bool
) -> float:
    """Computes a realistic baseline consumption value for a given hour."""
    profile = BUILDING_PROFILES.get(building, {}).get(resource, {"base": 50, "peak": 200, "peak_hours": [12]})
    base = profile["base"]
    peak = profile["peak"]
    peak_hours = profile["peak_hours"]

    # Weekends reduce usage in academic/library, but hostel and canteen remain active
    weekend_factor = 1.0
    if is_weekend:
        if building in ["Academic Block", "Library"]:
            weekend_factor = 0.25
        elif building in ["Hostel A", "Hostel B"]:
            weekend_factor = 1.15
        elif building == "Canteen":
            weekend_factor = 0.9

    if hour in peak_hours:
        # Peak hours with diurnal curve
        distance_from_center = min(abs(hour - ph) for ph in peak_hours)
        factor = max(0.6, 1.0 - distance_from_center * 0.15)
        expected = (base + (peak - base) * factor) * weekend_factor
    else:
        # Off-peak base load with slight smooth wave
        night_dip = 0.5 if (1 <= hour <= 5) else 0.8
        expected = base * night_dip * weekend_factor

    # Add realistic random meter noise (+/- 6%)
    noise = np.random.normal(0, max(0.8, expected * 0.05))
    val = max(1.0, round(float(expected + noise), 2))
    return val


def seed_history(days: int = 14) -> None:
    """
    Seeds historical hourly meter readings for all campus buildings and resources.
    Generates readings for the past `days` days ending at the current hour.
    """
    now = datetime.now().replace(minute=0, second=0, microsecond=0)
    total_hours = days * 24

    rows: List[Dict[str, Any]] = []

    for h_offset in range(total_hours, -1, -1):
        ts_dt = now - timedelta(hours=h_offset)
        ts_str = ts_dt.isoformat()
        hour = ts_dt.hour
        is_weekend = ts_dt.weekday() >= 5

        for building in BUILDINGS:
            for resource in RESOURCES:
                val = _get_hourly_profile_value(building, resource, hour, is_weekend)
                rows.append({
                    "building": building,
                    "resource": resource,
                    "ts": ts_str,
                    "value": val,
                })

    insert_readings(rows)


def inject_leak(
    building: str, resource: str, hours: int = 3, multiplier: float = 4.0
) -> None:
    """
    Simulates a leak or abnormal waste by scaling the latest readings
    for the specified building and resource.
    """
    # Fetch recent readings for this stream
    recent = get_readings(building=building, resource=resource, hours=hours + 2)
    if not recent:
        # If no readings exist, seed first
        seed_history(BASELINE_DAYS)
        recent = get_readings(building=building, resource=resource, hours=hours + 2)

    target_slice = recent[-hours:]
    min_diff = MIN_EXCESS.get(resource, 10) * 1.5

    updated_rows = []
    for r in target_slice:
        old_val = float(r["value"])
        # Ensure it safely exceeds both RATIO_THRESHOLD and MIN_EXCESS
        new_val = max(old_val * multiplier, old_val + min_diff)
        updated_rows.append({
            "building": r["building"],
            "resource": r["resource"],
            "ts": r["ts"],
            "value": round(float(new_val), 2),
        })

    insert_readings(updated_rows)
