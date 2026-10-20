import pytest
from fastapi.testclient import TestClient

from app import resources, rides, timesheets, tyres, users
from app.auth import require_user
from app.main import app


@pytest.fixture()
def api(monkeypatch):
    for n in ("_cars", "_parts", "_runs", "_circuits", "_catalog", "_maint", "_templates", "_sessions"):
        monkeypatch.setattr(rides, n, None)
    monkeypatch.setattr(tyres, "_coll", None)
    monkeypatch.setattr(timesheets, "_blobs", None)
    monkeypatch.setattr(users, "is_super", lambda e: True)
    app.dependency_overrides[require_user] = lambda: "chef@lifelive-motorsport.com"
    yield TestClient(app)
    app.dependency_overrides.pop(require_user, None)


def car(api, name="BMW M3 E30"):
    return {c["name"]: c["key"] for c in api.get("/api/rides/cars").json()["cars"]}[name]


def test_tyre_sets_crud_and_unique_reference(api):
    m3, p992 = car(api), car(api, "Porsche 992 Rally")
    s9 = api.post("/api/rides/tyres", json={"car": m3, "ref": "S9", "brand": "Hoosier", "model": "R8", "size": "27/65-18", "compound": "R8", "limit_km": 200, "start_km": 20}).json()
    assert s9["status"] == "new" and s9["id"].startswith("ty-")
    assert api.post("/api/rides/tyres", json={"car": m3, "ref": "s9"}).status_code == 422                       # référence unique par voiture
    assert api.post("/api/rides/tyres", json={"car": p992, "ref": "S9"}).status_code == 200                      # une autre voiture peut avoir son S9
    assert api.post("/api/rides/tyres", json={"car": "inconnue", "ref": "X"}).status_code == 404
    got = api.get("/api/rides/tyres").json()
    assert len(got["sets"]) == 2 and next(t for t in got["sets"] if t["id"] == s9["id"])["km"] == 20
    up = api.put(f"/api/rides/tyres/{s9['id']}", json={"ref": "S9", "brand": "Hoosier", "model": "R8", "status": "used", "car": "ignoré"}).json()
    assert up["car"] == m3 and up["status"] == "used"
    api.put(f"/api/rides/tyres/{s9['id']}", json={"ref": "S9", "status": "scrap"})
    assert {(o["car"] == m3, o["status"]) for o in api.get("/api/rides/tyres/options").json()["options"]} == {(True, "scrap"), (False, "new")}
    assert api.delete(f"/api/rides/tyres/{s9['id']}").status_code == 200                                         # jamais roulé : suppression possible


def test_runs_feed_tyre_counters_and_split_laps(api):
    m3, p992 = car(api), car(api, "Porsche 992 Rally")
    api.post("/api/rides/circuits", json={"name": "Dijon", "length_km": 3.8})
    a = api.post("/api/rides/tyres", json={"car": m3, "ref": "S8", "limit_km": 100, "limit_cycles": 4, "alert_pct": 50}).json()
    b = api.post("/api/rides/tyres", json={"car": m3, "ref": "S9", "limit_laps": 100}).json()
    other = api.post("/api/rides/tyres", json={"car": p992, "ref": "P1"}).json()
    s = api.post("/api/rides/sessions", json={"date": "2026-06-04", "name": "Essais Dijon", "kind": "circuit", "circuit": "Dijon"}).json()
    r = api.post(f"/api/rides/sessions/{s['id']}/cars/{m3}", json={"laps": 20, "tyres": [{"set_id": a["id"]}]})
    assert r.status_code == 200
    by = {t["ref"]: t for t in api.get("/api/rides/tyres").json()["sets"]}
    assert (by["S8"]["km"], by["S8"]["laps"], by["S8"]["cycles"], by["S8"]["runs"]) == (76.0, 20, 1, 1) and by["S8"]["state"] == "warn"
    s2 = api.post("/api/rides/sessions", json={"date": "2026-06-05", "name": "Course", "kind": "circuit", "circuit": "Dijon"}).json()
    assert api.post(f"/api/rides/sessions/{s2['id']}/cars/{m3}", json={"laps": 30, "tyres": [{"set_id": a["id"], "laps": 10, "cycles": 2}, {"set_id": b["id"]}]}).status_code == 200   # 10 + 20 restants
    by = {t["ref"]: t for t in api.get("/api/rides/tyres").json()["sets"]}
    assert (by["S8"]["laps"], by["S8"]["km"], by["S8"]["cycles"]) == (30, 114.0, 3) and by["S8"]["state"] == "over"      # 114 km > 100
    assert (by["S9"]["laps"], by["S9"]["km"], by["S9"]["state"]) == (20, 76.0, "ok") and len(by["S8"]["history"]) == 2
    s3 = api.post("/api/rides/sessions", json={"date": "2026-06-06", "name": "X", "kind": "circuit", "circuit": "Dijon"}).json()
    assert api.post(f"/api/rides/sessions/{s3['id']}/cars/{m3}", json={"laps": 5, "tyres": [{"set_id": other["id"]}]}).status_code == 422        # train d'une autre voiture
    assert api.post(f"/api/rides/sessions/{s3['id']}/cars/{m3}", json={"laps": 5, "tyres": [{"set_id": a["id"]}, {"set_id": a["id"]}]}).status_code == 422
    assert api.delete(f"/api/rides/tyres/{a['id']}").status_code == 422                                           # a roulé : rebut, pas suppression
    # modifier le roulage ne fait pas perdre les trains
    api.put(f"/api/rides/sessions/{s2['id']}", json={"date": "2026-06-05", "name": "Course 2", "kind": "circuit", "circuit": "Dijon"})
    assert {t["ref"]: t["laps"] for t in api.get("/api/rides/tyres").json()["sets"]}["S8"] == 30
    ses = {x["name"]: x for x in api.get("/api/rides/sessions").json()["sessions"]}
    assert ses["Course 2"]["cars"][0]["tyres"][0]["set_id"] == a["id"]


def test_alkamel_import_with_tyres_and_run_report_table(api):
    from app import alkamel, runreport
    m3 = car(api)
    api.post("/api/rides/circuits", json={"name": "Imola", "length_km": 4.909})
    t = api.post("/api/rides/tyres", json={"car": m3, "ref": "S9", "brand": "Hoosier", "model": "R8", "start_km": 10}).json()
    cl = [{"pos": 1, "no": 20, "drivers": ["R. de BORMAN"], "car": "Mustang", "class": "+2L", "classified": True, "laps": 10, "best": "2:18.000"}]
    body = {"event": "Imola Classic", "date": "2026-10-18", "circuit": "Imola", "sessions": [{"session": "RACE", "kind": "race", "classification": cl, "cars": {"20": m3}, "tyres": {m3: [{"set_id": t["id"]}]}}],
            "manual": [{"date": "2026-10-17", "name": "Veille", "cars": [{"key": m3, "laps": 5, "tyres": [{"set_id": t["id"], "cycles": 2}]}]}]}
    assert api.post("/api/rides/alkamel/import", json=body).status_code == 200
    s9 = api.get("/api/rides/tyres").json()["sets"][0]
    assert (s9["laps"], s9["km"], s9["cycles"], s9["runs"]) == (15, round(10 + 15 * 4.909, 1), 3, 2)
    mid = api.get("/api/rides/reports").json()["meetings"][0]["meeting"]
    v = api.get(f"/api/rides/reports/{mid}/{m3}").json()
    assert v["tyres_auto"][0]["ref"] == "S9" and v["tyres_auto"][0]["laps"] == 15 and v["tyres_auto"][0]["total_km"] == s9["km"]
    page = api.get(f"/api/rides/reports/{mid}/{m3}/print").text
    assert "Hoosier R8" in page and "Km (total du set)" in page
