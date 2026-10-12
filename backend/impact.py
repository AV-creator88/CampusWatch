"""
Impact calculation module for CampusWatch.
Computes total resource excess, monetary loss in INR, and CO2 emissions impact.
"""

from typing import Dict, Any
from .config import (
    RESOURCE_UNITS,
    WATER_RATE_INR,
    ELEC_RATE_INR,
    CO2_KG_PER_KWH,
)


def compute_impact(anomaly: Dict[str, Any]) -> Dict[str, Any]:
    """
    Computes environmental and financial impact for an anomaly alert.
    
    Returns:
        dict{excess, unit, cost_inr, co2_kg} (co2_kg is 0 for water)
    """
    resource = anomaly.get("resource", "water")
    hours = anomaly.get("hours", 1)
    actual = anomaly.get("actual", 0.0)
    expected = anomaly.get("expected", 0.0)

    # Excess is the cumulative waste over all alert hours
    hourly_excess = max(0.0, actual - expected)
    total_excess = round(hourly_excess * hours, 2)

    unit = RESOURCE_UNITS.get(resource, "liters" if resource == "water" else "kWh")

    if resource == "water":
        cost_inr = round(total_excess * WATER_RATE_INR, 2)
        co2_kg = 0.0
    else:  # electricity
        cost_inr = round(total_excess * ELEC_RATE_INR, 2)
        co2_kg = round(total_excess * CO2_KG_PER_KWH, 2)

    return {
        "excess": total_excess,
        "unit": unit,
        "cost_inr": cost_inr,
        "co2_kg": co2_kg,
    }
