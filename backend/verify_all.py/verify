from fastapi.testclient import TestClient
from backend.main import app

c = TestClient(app)
fails = 0

def check(name, ok, info=""):
    global fails
    if not ok:
        fails += 1
    print(("PASS" if ok else "FAIL"), "-", name, info)

# ---- DATA LAYER (Member 1) ----
check("reset endpoint", c.post("/api/reset").status_code == 200)
b = c.get("/api/buildings").json()
check("5 buildings returned", len(b) == 5, str(len(b)))
rd = c.get("/api/readings", params={"building": "Hostel B", "resource": "water", "hours": 72}).json()
check("about 72 hourly readings", len(rd) >= 70, str(len(rd)))
check("no negative values", all(x["value"] >= 0 for x in rd))

# ---- DETECTION: false positives (Member 2) ----
alerts = c.get("/api/alerts").json()
check("ZERO alerts on clean data", len(alerts) == 0,
      str([(a["building"], a["resource"]) for a in alerts]))
check("all buildings ok on clean data", all(x["status"] == "ok" for x in b))

# ---- DETECTION: real leak, water ----
check("inject water leak", c.post("/api/inject-leak",
      json={"building": "Hostel B", "resource": "water"}).status_code == 200)
alerts = c.get("/api/alerts").json()
hb = [a for a in alerts if a["building"] == "Hostel B" and a["resource"] == "water"]
check("Hostel B water alert detected", len(hb) == 1, str(len(hb)))
check("ONLY that alert (no extras)", len(alerts) == 1, str(len(alerts)))

# ---- IMPACT (Member 2) ----
if hb:
    a = hb[0]
    check("water: excess > 0, unit liters", a["excess"] > 0 and a["unit"] == "liters", str(a["excess"]))
    check("water: cost > 0, co2 == 0", a["cost_inr"] > 0 and a["co2_kg"] == 0)
    check("alert has message", bool(a.get("message")))
    print("   message:", a.get("message"))

# ---- API: summary + status (Member 3) ----
s = c.get("/api/summary").json()
check("summary alert_count == 1", s.get("alert_count") == 1, str(s))
bs = {x["name"]: x["status"] for x in c.get("/api/buildings").json()}
check("Hostel B status == alert", bs.get("Hostel B") == "alert", str(bs))

# ---- electricity leak ----
c.post("/api/reset")
c.post("/api/inject-leak", json={"building": "Library", "resource": "electricity"})
al = [a for a in c.get("/api/alerts").json() if a["building"] == "Library"]
check("Library electricity alert detected", len(al) == 1)
if al:
    check("electricity: kWh unit, co2 > 0", al[0]["unit"] == "kWh" and al[0]["co2_kg"] > 0)

# ---- bad input ----
check("bad building -> 400", c.post("/api/inject-leak",
      json={"building": "Nope", "resource": "water"}).status_code == 400)

c.post("/api/reset")
print("\nDONE -", "ALL PASSED" if fails == 0 else f"{fails} FAILED")