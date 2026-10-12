import os
import sys
from pathlib import Path

# Add campus-watch directory to sys.path
campus_watch_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(campus_watch_dir))

from backend.config import BUILDINGS, RESOURCES
from backend.db import init_db, insert_readings, get_readings, count_readings
from backend.simulator import seed_history, inject_leak
from backend.detection import detect_anomalies
from backend.impact import compute_impact
from backend.main import get_buildings, get_readings_endpoint, get_alerts, get_summary, post_inject_leak, InjectLeakRequest

def run_tests():
    print(">>> 1. Testing DB initialization...")
    init_db()
    c0 = count_readings()
    print(f"Initial count: {c0}")

    print(">>> 2. Testing seed_history...")
    seed_history(days=14)
    c1 = count_readings()
    print(f"Readings after seed: {c1}")
    assert c1 > 0, "Seed failed: count should be > 0"

    print(">>> 3. Testing get_readings...")
    sample_readings = get_readings(building="Hostel A", resource="water", hours=72)
    assert len(sample_readings) > 0, "get_readings should return rows"
    print(f"Found {len(sample_readings)} readings for Hostel A water (72h)")

    print(">>> 4. Testing inject_leak...")
    inject_leak("Hostel A", "water", hours=3, multiplier=4.0)
    readings_after_leak = get_readings(building="Hostel A", resource="water", hours=5)
    print("Latest 3 values after leak injection:", [r["value"] for r in readings_after_leak[-3:]])

    print(">>> 5. Testing detection...")
    all_readings = get_readings(hours=336)
    anomalies = detect_anomalies(all_readings)
    print(f"Detected {len(anomalies)} anomalies")
    assert len(anomalies) > 0, "Should detect at least 1 anomaly"
    anom = anomalies[0]
    print("Sample anomaly:", anom)
    assert "id" in anom and "building" in anom and "expected" in anom and "actual" in anom

    print(">>> 6. Testing compute_impact...")
    impact = compute_impact(anom)
    print("Sample impact:", impact)
    assert "excess" in impact and "cost_inr" in impact and "co2_kg" in impact

    print(">>> 7. Testing FastAPI endpoint functions...")
    # Buildings endpoint
    b_data = get_buildings()
    assert len(b_data) == len(BUILDINGS)
    print("get_buildings():", b_data[0])

    # Readings endpoint
    r_data = get_readings_endpoint(building="Hostel A", resource="water", hours=72)
    assert len(r_data) > 0
    assert "ts" in r_data[0] and "value" in r_data[0]
    print(f"get_readings_endpoint(): {len(r_data)} points")

    # Alerts endpoint
    a_data = get_alerts()
    assert len(a_data) > 0
    print("get_alerts() first item:", a_data[0])

    # Summary endpoint
    s_data = get_summary()
    print("get_summary():", s_data)
    assert "total_cost_inr" in s_data
    assert "total_co2_kg" in s_data
    assert "total_water_liters" in s_data
    assert "total_kwh" in s_data
    assert "alert_count" in s_data

    # Inject leak endpoint
    res = post_inject_leak(InjectLeakRequest(building="Library", resource="electricity"))
    print("post_inject_leak():", res)
    assert res == {"ok": True}

    print("\nALL CONTRACT CHECKS AND ENDPOINTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
