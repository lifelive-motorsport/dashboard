import pytest
from fastapi.testclient import TestClient

from app import rides, resources, timesheets, users
from app.auth import require_user
from app.main import app


@pytest.fixture()
def api(monkeypatch):
    for n in ("_cars", "_parts", "_runs", "_circuits", "_catalog", "_maint", "_templates"):
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
    g = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Moteur", "group": True}).json()
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
    g = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Transmission", "group": True}).json()
    p = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Boîte", "parent_id": g["id"], "limit_km": 100, "limit_hours": 2}).json()
    run = api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-01", "name": "T", "km": 80, "hours": 1}).json()
    node = api.get(f"/api/rides/cars/{c}").json()["tree"][0]["children"][0]
    assert node["state"] == "warn" and node["ratio"] == 0.8                                  # 80 % de la limite km, seuil 75 %
    api.put(f"/api/rides/runs/{run['id']}", json={"date": "2026-06-01", "name": "T", "km": 120, "hours": 1})
    assert api.get(f"/api/rides/cars/{c}").json()["tree"][0]["children"][0]["state"] == "over"             # corrigé sans rien recalculer à la main
    new = api.post(f"/api/rides/parts/{p['id']}/replace", json={"on": "2026-06-02", "serial": "N2"}).json()
    d = api.get(f"/api/rides/cars/{c}").json()
    kids = d["tree"][0]["children"]
    olds = [n for n in kids if n.get("removed_at")]
    news = [n for n in kids if not n.get("removed_at")]
    assert olds[0]["km"] == 120 and news[0]["km"] == 0 and news[0]["state"] == "ok" and news[0]["id"] == new["id"]
    assert d["alerts"] == 0                                                                  # une pièce démontée ne déclenche plus d'alerte
    api.delete(f"/api/rides/runs/{run['id']}")
    assert api.get(f"/api/rides/cars/{c}").json()["km_total"] == 0


def test_validation_depth_and_photo(api):
    c = car(api)["key"]
    a = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Freins", "group": True}).json()
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
    assert api.put(f"/api/rides/cars/{c}", json={"bu": "HISTORIC_RACING"}).json() == {"bu": "HISTORIC_RACING", "archived": False, "odoo": None}
    assert car(api)["bu"] == "HISTORIC_RACING"
    assert api.put(f"/api/rides/cars/{c}", json={"bu": "CARS"}).status_code == 422
    assert api.put("/api/rides/cars/inconnue", json={"bu": "XC"}).status_code == 404


def test_archive_then_delete_car_data(api):
    c = car(api)["key"]
    g = api.post(f"/api/rides/cars/{c}/parts", json={"name": "Moteur", "group": True}).json()
    api.post(f"/api/rides/cars/{c}/parts", json={"name": "Moteur", "parent_id": g["id"], "limit_km": 100})
    api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-01", "name": "T", "km": 50})
    api.post(f"/api/rides/cars/{c}/photo", content=b"\xff\xd8\xff", headers={"Content-Type": "image/jpeg"})
    assert api.delete(f"/api/rides/cars/{c}").status_code == 422                              # pas sans archivage
    assert api.put(f"/api/rides/cars/{c}", json={"archived": True}).json()["archived"] is True
    assert car(api)["archived"] is True and car(api)["km_total"] == 50                        # données conservées
    assert api.put(f"/api/rides/cars/{c}", json={"archived": False}).json()["archived"] is False
    assert api.put(f"/api/rides/cars/{c}", json={"bu": "XC"}).json() == {"bu": "XC", "archived": False, "odoo": None}    # un champ absent ne change rien
    api.put(f"/api/rides/cars/{c}", json={"archived": True})
    assert api.delete(f"/api/rides/cars/{c}").json() == {"parts": 2, "runs": 1}
    d = car(api)
    assert d["km_total"] == 0 and d["parts"] == 0 and d["photo"] is False and d["archived"] is False and d["bu"] == ""   # la voiture revient vide (elle est toujours une ressource)
    assert api.get(f"/api/rides/cars/{c}/photo").status_code == 404


def test_guess_missing_bus_only_fills_empty_cars(api):
    cars_ = api.get("/api/rides/cars").json()["cars"]
    keep = next(c for c in cars_ if "BMW M3" in c["name"])
    api.put(f"/api/rides/cars/{keep['key']}", json={"bu": "XC"})
    done = api.post("/api/rides/guess-bu").json()["set"]
    names = {d["name"]: d["bu"] for d in done}
    assert names == {"Porsche 992 Rally": "MODERN_RALLY"}                                     # la voiture déjà réglée n'est pas touchée
    assert api.post("/api/rides/guess-bu").json() == {"set": []}
    assert rides.guess_bu({"name": "Ford Escort RS1600", "category": "rally"}) == "HISTORIC_RALLY"
    assert rides.guess_bu({"name": "WRC W7 #29", "category": "rally"}) == "MODERN_RALLY"
    assert rides.guess_bu({"name": "Aston Martin GT3", "category": "circuit"}) == "HISTORIC_RACING"


def test_odoo_link_suggestions_and_uniqueness(api, monkeypatch):
    monkeypatch.setattr(rides, "_acc_cache", None)
    o = api.get("/api/rides/odoo").json()
    assert {a["name"] for a in o["accounts"]} >= {"BMW M3 E30 #44 (démo)", "Porsche 992 Rally GT #26 (démo)"}
    sug = o["suggestions"]
    m3, p992 = car(api)["key"], next(c["key"] for c in api.get("/api/rides/cars").json()["cars"] if "992" in c["name"])
    assert sug[m3]["name"] == "BMW M3 E30 #44 (démo)" and sug[m3]["sure"] and sug[p992]["sure"]
    done = api.post("/api/rides/link-odoo").json()["linked"]
    assert {d["odoo"] for d in done} == {"BMW M3 E30 #44 (démo)", "Porsche 992 Rally GT #26 (démo)"}
    assert car(api)["odoo"]["id"] == 2
    assert api.post("/api/rides/link-odoo").json() == {"linked": []}
    assert api.put(f"/api/rides/cars/{p992}", json={"odoo_id": 2}).status_code == 422          # déjà pris par la M3
    assert api.put(f"/api/rides/cars/{m3}", json={"odoo_id": 999}).status_code == 404
    assert api.put(f"/api/rides/cars/{m3}", json={"odoo_id": 0}).json()["odoo"] is None
    assert api.put(f"/api/rides/cars/{p992}", json={"odoo_id": 2}).json()["odoo"]["id"] == 2   # libéré : peut être reprise
    assert rides.name_score("Bmw 635 csi Würth (GDM)", "BMW 635 CSi Würth") > 0.85 and rides.name_score("Lotus Elan 26R", "Ferrari 250 SWB") < 0.5


def test_refresh_rereads_google_resources(api, monkeypatch):
    calls = []
    real = resources.vehicles
    monkeypatch.setattr(resources, "vehicles", lambda force=False: (calls.append(force), real(force))[1])
    api.get("/api/rides/cars")
    api.get("/api/rides/cars?refresh=1")
    api.get("/api/resources?refresh=1")
    assert True in calls and calls.count(True) >= 2


def _tpl():
    return {"name": "Voiture circuit turbo 2RM", "description": "", "nodes": [
        {"id": "g1", "name": "Moteur", "group": True},
        {"id": "n1", "parent_id": "g1", "name": "Moteur", "types": ["replace", "revision", "fluids"], "replace": {"limit_km": 5000}, "revision": {"limit_km": 1500, "warn_pct": 80}, "fluids": {"limit_km": 500, "limit_hours": 5}},
        {"id": "n2", "parent_id": "g1", "name": "Turbo", "types": ["replace"], "replace": {"limit_km": 2000, "warn_pct": 50}}]}


def test_template_assign_and_maintenance_meters(api):
    c = car(api)["key"]
    t = api.post("/api/rides/templates", json=_tpl()).json()
    assert api.post("/api/rides/templates", json=_tpl()).status_code == 422                     # nom déjà pris
    bad = _tpl(); bad["nodes"][1]["parent_id"] = "inconnu"
    assert api.post("/api/rides/templates", json={**bad, "name": "x"}).status_code == 422
    r = api.post(f"/api/rides/cars/{c}/template", json={"template_id": t["id"]}).json()
    assert r["created"] == 3 and r["kept"] == 0
    assert api.post(f"/api/rides/cars/{c}/template", json={"template_id": t["id"]}).json()["created"] == 0   # non destructif
    assert car(api)["template"]["name"] == "Voiture circuit turbo 2RM"
    api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-01", "name": "A", "km": 1300, "hours": 4})
    d = api.get(f"/api/rides/cars/{c}").json()
    eng = next(n for n in d["tree"][0]["children"] if n["name"] == "Moteur")
    m = {x["type"]: x for x in eng["meters"]}
    assert set(m) == {"replace", "revision", "fluids"}
    assert m["replace"]["ratio"] == 0.26 and m["revision"]["state"] == "warn" and m["fluids"]["state"] == "over"      # 1300/1500 = 87 % >= 80 % ; 1300/500 > 100 %
    assert eng["state"] == "over" and d["state"] == "over" and any(a["type"] == "fluids" and a["state"] == "over" for a in d["alerts_list"])
    # vidange faite le 02/06 : le compteur repart
    assert api.post(f"/api/rides/parts/{eng['id']}/maint", json={"type": "fluids", "date": "2026-06-02"}).status_code == 200
    assert api.post(f"/api/rides/parts/{eng['id']}/maint", json={"type": "replace", "date": "2026-06-02"}).status_code == 422
    api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-05", "name": "B", "km": 100})
    eng = next(n for n in api.get(f"/api/rides/cars/{c}").json()["tree"][0]["children"] if n["name"] == "Moteur")
    m = {x["type"]: x for x in eng["meters"]}
    assert m["fluids"]["km"] == 100 and m["fluids"]["state"] == "ok" and m["fluids"]["last"] == "2026-06-02"
    assert m["revision"]["km"] == 1400 and m["replace"]["km"] == 1400                      # la révision n'a pas été faite : elle continue de courir
    hid = eng["history"][0]["id"]
    assert api.delete(f"/api/rides/maint/{hid}").status_code == 200
    turbo = next(n for n in api.get(f"/api/rides/cars/{c}").json()["tree"][0]["children"] if n["name"] == "Turbo")
    assert api.post(f"/api/rides/parts/{turbo['id']}/maint", json={"type": "revision", "date": "2026-06-02"}).status_code == 422    # type non suivi
    assert api.put(f"/api/rides/templates/{t['id']}", json={**_tpl(), "description": "maj"}).json()["description"] == "maj"
    assert api.delete(f"/api/rides/templates/{t['id']}").status_code == 200
    left = api.get("/api/rides/templates").json()["templates"]
    assert [x["name"] for x in left] == ["Toyota GR Yaris Rally2"]                               # modèle de départ, créé une seule fois
    assert api.delete(f"/api/rides/templates/{left[0]['id']}").status_code == 200
    assert api.get("/api/rides/templates").json()["templates"] == []                           # supprimé : il ne revient pas


def test_vehicle_documents_alerts_files_and_mail(api, monkeypatch):
    from datetime import date, timedelta
    from app import mailer, vdocs
    monkeypatch.setattr(vdocs, "_sent", None)
    monkeypatch.setattr(timesheets, "_alert_coll", None, raising=False)
    cs = {c["name"]: c["key"] for c in api.get("/api/rides/cars").json()["cars"]}
    circ, rally = cs["BMW M3 E30"], cs["Porsche 992 Rally"]
    keys = lambda k: {d["item"] for d in api.get(f"/api/rides/cars/{k}/docs").json()}
    labels = [d["label"] for d in api.get(f"/api/rides/cars/{circ}/docs").json()]
    assert labels == sorted(labels, key=lambda s: __import__("unicodedata").normalize("NFD", s).encode("ascii", "ignore").decode().lower()) and "Certificat arceau" in labels      # ordre alphabétique
    assert "transponder" in keys(circ) and "insurance" not in keys(circ)                      # circuit : pas d'immatriculation
    assert "insurance" in keys(rally) and "transponder" not in keys(rally) and "fia" in keys(rally)
    assert api.put(f"/api/rides/cars/{circ}/docs/insurance", json={"expires": "2026-12-01"}).status_code == 404
    assert api.put(f"/api/rides/cars/{circ}/docs/fia", json={"expires": "pas une date"}).status_code == 422
    today = vdocs.today()
    soon, tomorrow, past, far = ((today + timedelta(days=n)).isoformat() for n in (10, 1, -2, 200))
    api.put(f"/api/rides/cars/{circ}/docs/fia", json={"expires": soon, "note": "renouveler"})
    api.put(f"/api/rides/cars/{circ}/docs/harness", json={"expires": tomorrow})
    api.put(f"/api/rides/cars/{circ}/docs/seat", json={"expires": past})
    api.put(f"/api/rides/cars/{circ}/docs/asn", json={"expires": far})
    st = {d["item"]: d for d in api.get(f"/api/rides/cars/{circ}/docs").json()}
    assert [st[i]["state"] for i in ("fia", "harness", "seat", "asn", "extinguisher")] == ["warn", "warn", "over", "ok", "none"]
    api.put(f"/api/rides/cars/{circ}/docs/fia", json={"weeks": 1})                              # alerte réglée à 1 semaine : 10 jours = encore ok
    assert {d["item"]: d for d in api.get(f"/api/rides/cars/{circ}/docs").json()}["fia"]["state"] == "ok"
    d = api.get(f"/api/rides/cars/{circ}").json()
    assert d["doc_alerts"] == 2 and d["doc_over"] == 1
    # fichiers
    r = api.post(f"/api/rides/cars/{circ}/docs/seat/files?name=fia.pdf", content=b"%PDF-1.4 x", headers={"Content-Type": "application/pdf"})
    assert r.status_code == 200
    fid = next(x for x in r.json() if x["item"] == "seat")["files"][0]["id"]
    assert api.get(f"/api/rides/cars/{circ}/docs/seat/files/{fid}").content.startswith(b"%PDF")
    th = api.get(f"/api/rides/cars/{circ}/docs/seat/files/{fid}/thumb")                         # aperçu : 404 propre si le PDF est illisible ou si poppler est absent
    assert th.status_code in (200, 404) and (th.status_code == 404 or th.content[:2] == b"\xff\xd8")
    assert api.post(f"/api/rides/cars/{circ}/docs/seat/files", content=b"x", headers={"Content-Type": "text/html"}).status_code == 422
    assert api.delete(f"/api/rides/cars/{circ}/docs/seat/files/{fid}").status_code == 200
    # accueil : visible du Super User
    al = api.get("/api/alerts").json()["vehicle_docs"]
    assert {a["item"] for a in al} == {"harness", "seat"} and al[0]["car_name"] == "BMW M3 E30"
    # e-mail la veille de l'échéance, une seule fois
    mailer.OUTBOX.clear()
    monkeypatch.setattr(users, "supers", lambda: ["md@lifelive-motorsport.com"])
    monkeypatch.setattr(timesheets, "workshop_people", lambda: [])
    out = vdocs.send_expiry_mails(today)
    assert [s["item"] for s in out["sent"]] == ["harness"] and "expire demain" in mailer.OUTBOX[0]["subject"]
    assert vdocs.send_expiry_mails(today)["sent"] == []


def test_workshop_manager_sees_only_his_bu_alerts():
    from app import vdocs
    xc, cars = {"super": False, "bus": ["XC"]}, {"super": False, "bus": ["CARS"]}
    assert vdocs.visible(xc, "XC") and not vdocs.visible(xc, "MODERN_RALLY") and not vdocs.visible(xc, "")
    assert vdocs.visible(cars, "HISTORIC_RACING") and vdocs.visible(cars, "") and not vdocs.visible(cars, "XC")
    assert vdocs.status("2026-10-20", 3, __import__("datetime").date(2026, 10, 13)) == "warn"


def test_car_identity_fields(api):
    c = car(api)["key"]
    r = api.put(f"/api/rides/cars/{c}", json={"chassis": " WBA123 ", "engine_no": "S14-77", "gearbox_no": "G-9", "livery": "Bleu / blanc", "race_number": "12"})
    assert r.status_code == 200
    d = api.get(f"/api/rides/cars/{c}").json()
    assert (d["chassis"], d["engine_no"], d["gearbox_no"], d["livery"], d["race_number"]) == ("WBA123", "S14-77", "G-9", "Bleu / blanc", "12")
    api.put(f"/api/rides/cars/{c}", json={"livery": ""})                                           # vide = effacé ; les autres champs ne bougent pas
    d = api.get(f"/api/rides/cars/{c}").json()
    assert d["livery"] == "" and d["chassis"] == "WBA123"


def test_first_level_is_a_locked_list_of_ensembles(api):
    c = car(api)["key"]
    assert api.get("/api/rides/cars").json()["ensembles"][:3] == ["Moteur", "Refroidissement", "Embrayage"]
    assert api.post(f"/api/rides/cars/{c}/parts", json={"name": "Truc libre", "group": True}).status_code == 422        # hors liste
    assert api.post(f"/api/rides/cars/{c}/parts", json={"name": "Moteur", "limit_km": 10}).status_code == 422             # un ensemble est un groupe
    g = api.post(f"/api/rides/cars/{c}/parts", json={"name": "electrique et capteurs", "group": True}).json()
    assert g["name"] == "Électrique et capteurs"                                                                           # nom normalisé (casse, accents)
    assert api.post(f"/api/rides/cars/{c}/parts", json={"name": "Électrique et capteurs", "group": True}).status_code == 422    # une seule fois par voiture
    assert api.put(f"/api/rides/parts/{g['id']}", json={"name": "Autre chose", "group": True}).status_code == 422
    bad = _tpl(); bad["nodes"][0]["name"] = "Motorisation"
    assert api.post("/api/rides/templates", json={**bad, "name": "x"}).status_code == 422
    bad = _tpl(); bad["nodes"].append({"id": "r", "name": "Moteur", "group": False})
    assert api.post("/api/rides/templates", json={**bad, "name": "y"}).status_code == 422


def test_new_maintenance_types_events_condition_and_reference(api):
    from datetime import date
    c = car(api)["key"]
    t = {"name": "Rally2 test", "description": "", "nodes": [
        {"id": "g", "name": "Carburant", "group": True},
        {"id": "tank", "parent_id": "g", "name": "Fuel Tank", "reference": "DYXRQ186021", "types": ["replace", "inspection"], "replace": {"limit_km": 500, "note": "ou si abîmé"}, "inspection": {"limit_events": 1}},
        {"id": "gb", "parent_id": "g", "name": "Gearbox", "types": ["revision", "revision2", "inspection"], "revision": {"limit_km": 500}, "revision2": {"limit_km": 3000}, "inspection": {"limit_km": 650}},
        {"id": "pl", "parent_id": "g", "name": "Clutch plates", "types": ["replace"], "replace": {"note": "sous l'épaisseur minimale"}}]}
    tid = api.post("/api/rides/templates", json=t).json()["id"]
    api.post(f"/api/rides/cars/{c}/template", json={"template_id": tid})
    d = api.get(f"/api/rides/cars/{c}").json()
    kids = {n["name"]: n for n in d["tree"][0]["children"]}
    assert kids["Fuel Tank"]["reference"] == "DYXRQ186021" and kids["Fuel Tank"]["limit_km"] == 500
    assert {m["type"] for m in kids["Gearbox"]["meters"]} == {"revision", "revision2", "inspection"}
    cp = kids["Clutch plates"]["meters"][0]
    assert cp["type"] == "replace" and cp["note"] == "sous l'épaisseur minimale" and cp["state"] == "none"                 # « sur condition » : visible, sans alerte
    api.put(f"/api/rides/parts/{kids['Fuel Tank']['id']}", json={"name": "Fuel Tank", "types": ["replace", "inspection"], "limit_km": 500, "maint": {"inspection": {"limit_events": 1}}, "mounted_from": "2021-01-01"})
    api.post(f"/api/rides/cars/{c}/runs", json={"date": "2026-06-01", "name": "A", "km": 700})
    d = api.get(f"/api/rides/cars/{c}").json()
    kids = {n["name"]: n for n in d["tree"][0]["children"]}
    m = {x["type"]: x for x in kids["Fuel Tank"]["meters"]}
    assert m["replace"]["state"] == "over"
    assert m["inspection"]["events"] == 1 and m["inspection"]["state"] == "warn"                                           # contrôle dû : avertissement, jamais « dépassé »
    gm = {x["type"]: x for x in kids["Gearbox"]["meters"]}
    assert gm["revision"]["state"] == "over" and gm["revision2"]["state"] == "ok" and gm["inspection"]["state"] == "over".replace("over", "warn")
    # alertes : les contrôles sont regroupés en une seule
    al = d["alerts_list"]
    assert sum(1 for a in al if a["type"] == "inspection") == 1 and next(a for a in al if a["type"] == "inspection")["count"] == 2
    # Révision 2 et contrôle s'enregistrent comme la révision
    gid = kids["Gearbox"]["id"]
    assert api.post(f"/api/rides/parts/{gid}/maint", json={"type": "revision2", "date": "2026-06-02"}).status_code == 200
    assert api.post(f"/api/rides/parts/{gid}/maint", json={"type": "inspection", "date": "2026-06-02"}).status_code == 200
    assert api.post(f"/api/rides/parts/{kids['Clutch plates']['id']}/maint", json={"type": "revision", "date": "2026-06-02"}).status_code == 422


def test_toyota_starter_template_applies_to_a_car(api):
    t = api.get("/api/rides/templates").json()["templates"][0]
    assert t["name"] == "Toyota GR Yaris Rally2" and sum(1 for n in t["nodes"] if not n["parent_id"]) == 9
    assert all(rides.canon_ensemble(n["name"]) for n in t["nodes"] if not n["parent_id"])
    c = car(api)["key"]
    r = api.post(f"/api/rides/cars/{c}/template", json={"template_id": t["id"]}).json()
    assert r["created"] == len(t["nodes"]) and r["kept"] == 0
    d = api.get(f"/api/rides/cars/{c}").json()
    eng = next(n for n in d["tree"] if n["name"] == "Moteur")
    engine = next(n for n in eng["children"] if n["name"] == "Engine")
    assert {m["type"] for m in engine["meters"]} == {"revision", "revision2", "inspection"} and engine["reference"] == "DYXRQ202040"
    gb = next(n for n in next(x for x in d["tree"] if x["name"] == "Transmission")["children"] if n["name"] == "Gearbox")
    assert len(gb["children"]) == 15 and next(m for m in gb["meters"] if m["type"] == "revision")["limit_km"] == 500
    fuel = next(n for n in next(x for x in d["tree"] if x["name"] == "Carburant")["children"] if n["name"] == "Fuel tank")
    assert "Certificat réservoir" in next(m for m in fuel["meters"] if m["type"] == "replace")["note"]            # la validité du réservoir se suit dans « Documents et validités »


def test_ensembles_follow_the_list_order(api):
    c = car(api)["key"]
    for n in ("Freins", "Moteur", "Carburant"):
        api.post(f"/api/rides/cars/{c}/parts", json={"name": n, "group": True})
    assert [n["name"] for n in api.get(f"/api/rides/cars/{c}").json()["tree"]] == ["Moteur", "Freins", "Carburant"]
