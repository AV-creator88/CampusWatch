"""
Configuration settings for CampusWatch.
Defines campus buildings, resources, utility tariffs, CO2 factors,
detection thresholds, and database path.
"""

import os
from pathlib import Path

# Monitored campus buildings
BUILDINGS = ["Hostel A", "Hostel B", "Library", "Academic Block", "Canteen"]

# Monitored resources
# Units: water = liters/hour, electricity = kWh/hour
RESOURCES = ["water", "electricity"]

# Resource display units
RESOURCE_UNITS = {
    "water": "liters",
    "electricity": "kWh"
}

RESOURCE_HOURLY_UNITS = {
    "water": "liters/hour",
    "electricity": "kWh/hour"
}

# Financial and Environmental impact factors
ELEC_RATE_INR = 8       # INR per kWh
WATER_RATE_INR = 0.05   # INR per liter
CO2_KG_PER_KWH = 0.82   # kg CO2 per kWh

# Detection parameters
RATIO_THRESHOLD = 2.0
MIN_EXCESS = {
    "water": 100,       # liters/hour minimum excess over baseline
    "electricity": 3    # kWh/hour minimum excess over baseline
}
MIN_CONSECUTIVE_HOURS = 2
BASELINE_DAYS = 14

# Database path (campuswatch.db in campus-watch root or configurable)
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = Path(os.environ.get("CAMPUSWATCH_DB", str(BASE_DIR / "campuswatch.db")))
