
"""
Anomaly detection engine for CampusWatch.
Implements diurnal hourly baseline learning with weekday/weekend segregation
and consecutive anomaly clustering.
"""

from datetime import datetime, timedelta
from typing import List, Dict, Any
import numpy as np

from .config import (
    RATIO_THRESHOLD,
    MIN_EXCESS,
    MIN_CONSECUTIVE_HOURS,
    BASELINE_DAYS,
)


def detect_anomalies(readings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Detects abnormal water and electricity consumption patterns.
    
    For each (building, resource) stream:
    1. Learns the baseline median consumption for each hour of day (weekday vs weekend)
       from the previous baseline days.
    2. Identifies anomalous hours where:
       actual > RATIO_THRESHOLD * expected AND (actual - expected) > MIN_EXCESS[resource]
    3. Merges consecutive anomalous hours (>= MIN_CONSECUTIVE_HOURS) into a single alert.
    
    Returns:
        List[dict{id, building, resource, start_ts, end_ts, hours, expected, actual}]
    """
    if not readings:
        return []

    # Group readings by (building, resource)
    grouped: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in readings:
        key = (r["building"], r["resource"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(r)

    alerts: List[Dict[str, Any]] = []

    for (building, resource), stream_readings in grouped.items():
        # Sort chronologically
        sorted_readings = sorted(stream_readings, key=lambda x: x["ts"])

        # Pre-process datetime metadata
        enriched = []
        for r in sorted_readings:
            dt = datetime.fromisoformat(r["ts"])
            enriched.append({
                "building": building,
                "resource": resource,
                "ts": r["ts"],
                "dt": dt,
                "value": float(r["value"]),
                "hour": dt.hour,
                "is_weekend": dt.weekday() >= 5,
            })

        # Calculate baseline median for each reading
        # Pre-group by (hour, is_weekend) for fast fallback lookup
        hour_weekend_map: Dict[tuple, List[float]] = {}
        for item in enriched:
            hw_key = (item["hour"], item["is_weekend"])
            if hw_key not in hour_weekend_map:
                hour_weekend_map[hw_key] = []
            hour_weekend_map[hw_key].append(item["value"])

        overall_medians = {
            k: float(np.median(vals)) if vals else 1.0
            for k, vals in hour_weekend_map.items()
        }

        min_excess_val = MIN_EXCESS.get(resource, 0)
        evaluated_readings = []

        baseline_delta = timedelta(days=BASELINE_DAYS)

        for i, item in enumerate(enriched):
            cur_dt = item["dt"]
            cur_hw = (item["hour"], item["is_weekend"])
            cutoff_dt = cur_dt - baseline_delta

            # Historical readings strictly prior to cur_dt within the baseline window
            prior_vals = [
                prev["value"]
                for prev in enriched[:i]
                if prev["dt"] >= cutoff_dt
                and (prev["hour"], prev["is_weekend"]) == cur_hw
            ]

            if len(prior_vals) >= 2:
                expected = float(np.median(prior_vals))
            else:
                expected = overall_medians.get(cur_hw, 1.0)

            # Prevent zero or negative baseline division
            expected = max(expected, 0.01)

            actual = item["value"]
            ratio = actual / expected
            excess = actual - expected

            is_anom = (ratio > RATIO_THRESHOLD) and (excess > min_excess_val)

            evaluated_readings.append({
                **item,
                "expected": expected,
                "is_anom": is_anom,
            })

        # Cluster consecutive anomalous hours
        current_streak: List[Dict[str, Any]] = []

        def _record_streak(streak: List[Dict[str, Any]]):
            if len(streak) >= MIN_CONSECUTIVE_HOURS:
                start_ts = streak[0]["ts"]
                end_ts = streak[-1]["ts"]
                hours_count = len(streak)
                avg_expected = round(float(np.mean([s["expected"] for s in streak])), 2)
                avg_actual = round(float(np.mean([s["value"] for s in streak])), 2)
                alert_id = f"alert_{building.lower().replace(' ', '_')}_{resource}_{start_ts}"

                alerts.append({
                    "id": alert_id,
                    "building": building,
                    "resource": resource,
                    "start_ts": start_ts,
                    "end_ts": end_ts,
                    "hours": hours_count,
                    "expected": avg_expected,
                    "actual": avg_actual,
                })

        for item in evaluated_readings:
            if item["is_anom"]:
                if not current_streak:
                    current_streak.append(item)
                else:
                    prev_item = current_streak[-1]
                    # Check if consecutive hour
                    if item["dt"] - prev_item["dt"] == timedelta(hours=1):
                        current_streak.append(item)
                    else:
                        _record_streak(current_streak)
                        current_streak = [item]
            else:
                if current_streak:
                    _record_streak(current_streak)
                    current_streak = []

        if current_streak:
            _record_streak(current_streak)

    return alerts
