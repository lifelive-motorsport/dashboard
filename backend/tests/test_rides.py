import pytest
from fastapi.testclient import TestClient

from app import rides, resources, timesheets, users
from app.auth import require_user
from app.main import app


@pytest.fixture()
def api(monkeypatch):
    for n in ("_cars", "_parts", "_runs", "_circuits", "_catalog"):
        monkeypatch.setattr(rides, n, None)
    monkeypatch.setattr(timesheets, "_blobs", None)
    monkeypatch.setattr(users, "is_super", lambda e: True)
    app.dependency_overrides[require_user] = lambda: "chef@lifelive-motorsport.com"
    yield TestClient(app)
    app.dependency_overrides.pop(require_user, None)


def car(api):
    cs = api.get("/api/rides/cars").json()["cars"]
    return next(c for c in cs if "BMW M3" in c["name"])


def test_cars_come_from_race_vehicles_without_the_rpm_number_or_prefix(api):
    names = [c["name"] for c in api.get("/api/rides/cars").json()["cars"]]
    assert "BMW M3 E30" in names and "Porsche 992 Rally" in names                      # « (Circuit)- » retiré
    assert "Sprinter" not in names and "Drone" not in names                              # pas de véhicule de service


def test_km_are_computed_from_runs_and_mounting_dates(api):
    c = car(api)["key"]
    g = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Motorisation", "group": True}).json()
    eng = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Moteur", "parent_id": g["id"], "limit_km": 1000, "km_start": 100}).json()
    turbo = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Turbo", "parent_id": g["id"], "limit_km": 200, "warn_pct": 50}).json()
    assert api.post(f"/api/rides/circuits", json={"name": "Dijon", "length_km": 3.8}).json()["id"] == "dijon"
    r1 = api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-04", "name": "Essais", "circuit": "Dijon", "laps": 22, "hours": 1.5}).json()
    assert r1["km"] == 83.6
    api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-05", "name": "Course", "kind": "rally", "stages": [{"name": "ES1", "length_km": 12.5, "passes": 2}, {"name": "ES2", "length_km": 8, "passes": 1}]})
    d = api.get(f"/api/rides/cars/{c}").json()
    nodes = {n["name"]: n for n in d["tree"][0]["children"]}
    assert nodes["Moteur"]["km"] == 100 + 83.6 + 33 and nodes["Moteur"]["state"] == "ok"
    assert nodes["Turbo"]["state"] == "warn" and d["tree"][0]["state"] == "warn" and d["state"] == "warn"      # 116,6 / 200 = 58 % >= 50 %
    assert d["km_total"] == 116.6


def test_alert_thresholds_replace_and_run_edit(api):
    c = car(api)["key"]
    p = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Boîte", "limit_km": 100, "limit_hours": 2}).json()
    run = api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-01", "name": "T", "km": 80, "hours": 1}).json()
    node = api.get(f"/api/rides/cars/{c}").json()["tree"][0]
    assert node["state"] == "warn" and node["ratio"] == 0.8                                  # 80 % de la limite km, seuil 75 %
    api.put(f"/api/rides/runs/{run['id']}", json={"date": "2026-06-01", "name": "T", "km": 120, "hours": 1})
    assert api.get(f"/api/rides/cars/{c}").json()["tree"][0]["state"] == "over"             # corrigé sans rien recalculer à la main
    new = api.post(f"/api/rides/parts/{p['id']}/replace", json={"on": "2026-06-02", "serial": "N2"}).json()
    d = api.get(f"/api/rides/cars/{c}").json()
    olds = [n for n in d["tree"] if n.get("removed_at")]
    news = [n for n in d["tree"] if not n.get("removed_at")]
    assert olds[0]["km"] == 120 and news[0]["km"] == 0 and news[0]["state"] == "ok" and news[0]["id"] == new["id"]
    assert d["alerts"] == 0                                                                  # une pièce démontée ne déclenche plus d'alerte
    api.delete(f"/api/rides/runs/{run['id']}")
    assert api.get(f"/api/rides/cars/{c}").json()["km_total"] == 0


def test_validation_depth_and_photo(api):
    c = car(api)["key"]
    a = api.post(f"/api/rides/cars/{c}/parts", json={"name": "A", "group": True}).json()
    b = api.post(f"/api/rides/cars/{c}/parts", json={"name": "B", "parent_id": a["id"], "group": True}).json()
    cc = api.post(f"/api/rides/cars/{c}/parts", json={"name": "C", "parent_id": b["id"], "limit_km": 10}).json()
    assert api.post(f"/api/rides/cars/{c}/parts", json={"name": "D", "parent_id": cc["id"]}).status_code == 422       # 4e niveau refusé
    assert api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-01", "name": "x", "circuit": "Inconnu", "laps": 5}).status_code == 422
    assert api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-01", "name": "x"}).status_code == 422
    assert api.post("/api/rides/cars/inconnue/runs", json={"date": "2026-06-01", "name": "x", "km": 5}).status_code == 404
    assert api.post(f"/api/rides/cars/{c}/photo", content=b"x", headers={"Content-Type": "text/html"}).status_code == 422
    assert api.post(f"/api/rides/cars/{c}/photo", content=b"\xff\xd8\xff", headers={"Content-Type": "image/jpeg"}).status_code == 200
    assert api.get(f"/api/rides/cars/{c}/photo").content == b"\xff\xd8\xff"
    assert car(api)["photo"] is True


def test_car_bu_is_set_and_validated(api):
    c = car(api)["key"]
    assert car(api)["bu"] == ""
    assert api.put(f"/api/rides/cars/{c}", json={"bu": "HISTORIC_RACING"}).json() == {"bu": "HISTORIC_RACING", "archived": False}
    assert car(api)["bu"] == "HISTORIC_RACING"
    assert api.put(f"/api/rides/cars/{c}", json={"bu": "CARS"}).status_code == 422
    assert api.put("/api/rides/cars/inconnue", json={"bu": "XC"}).status_code == 404


def test_archive_then_delete_car_data(api):
    c = car(api)["key"]
    api.post(f"/api/rides/cars/{c}/parts", json={"name": "Moteur", "limit_km": 100})
    api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-01", "name": "T", "km": 50})
    api.post(f"/api/rides/cars/{c}/photo", content=b"\xff\xd8\xff", headers={"Content-Type": "image/jpeg"})
    assert api.delete(f"/api/rides/cars/{c}").status_code == 422                              # pas sans archivage
    assert api.put(f"/api/rides/cars/{c}", json={"archived": True}).json()["archived"] is True
    assert car(api)["archived"] is True and car(api)["km_total"] == 50                        # données conservées
    assert api.put(f"/api/rides/cars/{c}", json={"archived": False}).json()["archived"] is False
    assert api.put(f"/api/rides/cars/{c}", json={"bu": "XC"}).json() == {"bu": "XC", "archived": False}    # un champ absent ne change rien
    api.put(f"/api/rides/cars/{c}", json={"archived": True})
    assert api.delete(f"/api/rides/cars/{c}").json() == {"parts": 1, "runs": 1}
    d = car(api)
    assert d["km_total"] == 0 and d["parts"] == 0 and d["photo"] is False and d["archived"] is False and d["bu"] == ""   # la voiture revient vide (elle est toujours une ressource)
    assert api.get(f"/api/rides/cars/{c}/photo").status_code == 404
