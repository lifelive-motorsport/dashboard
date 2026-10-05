from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def test_dashboard_demo():
    r = c.get("/api/dashboard?from=2026-01-01&to=2026-12-31").json()
    assert r["source"] == "demo"
    pnl = r["pnl"]
    assert abs(sum(b["ca"] for b in pnl["bus"]) - pnl["total"]["ca"]) < 1e-6
    g = {x["key"]: x for x in pnl["groups"]}
    assert g["XC"]["ca"] + g["CARS"]["ca"] + g["OTHER"]["ca"] == pnl["total"]["ca"]
    assert r["balance_sheet"]["cash"] > 0 and "XC" in r["top_clients"]
