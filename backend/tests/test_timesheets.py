from datetime import date, datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import staff, timesheets, users
from app.auth import require_user
from app.main import app

MEC, CHEF, CHEF_XC, NOBODY = "mec@lifelive-motorsport.com", "julien@lifelive-motorsport.com", "morgan@lifelive-motorsport.com", "autre@lifelive-motorsport.com"


@pytest.fixture()
def api(monkeypatch):
    monkeypatch.setattr(timesheets, "_jobs", None)
    monkeypatch.setattr(timesheets, "_entries", None)
    monkeypatch.setattr(timesheets, "_blobs", None)
    monkeypatch.setattr(users, "is_super", lambda e: False)
    cur = staff.store().get()
    people = [{"id": "m1", "name": "Nolan Collinet", "kind": "salarie", "function": "Mechanic", "workshop": "mechanic", "google_email": MEC, "hours_week": 38, "fte": 100},
              {"id": "c1", "name": "Julien Durbecq", "kind": "salarie", "function": "Workshop Manager", "workshop": "chef_cars", "google_email": CHEF},
              {"id": "c2", "name": "Morgan Duyckaerts", "kind": "salarie", "function": "XC Workshop Manager", "workshop": "chef_xc", "google_email": CHEF_XC}]
    assert staff.store().put({"params": cur["data"]["params"], "people": people}, "t", cur["updated_at"]) is not None
    who = {"u": MEC}
    app.dependency_overrides[require_user] = lambda: who["u"]
    c = TestClient(app)
    c.who = who
    yield c
    app.dependency_overrides.pop(require_user, None)


def as_(c, email):
    c.who["u"] = email


def mkjob(c, kind="atelier", title="Pre-event Spa / Porsche", bu="CARS", **kw):
    as_(c, CHEF)
    body = {"kind": kind, "title": title, "bu": bu, **kw}
    return c.post("/api/timesheets/jobs", json=body)


def entry(job, **kw):
    return {"job_id": job, "date": date.today().isoformat(), "minutes": 90, "assignment": "prepa", "system": "moteur", "text": "Vidange", **kw}


def test_roles(api):
    assert timesheets.role_of(MEC)["role"] == "mechanic"
    assert timesheets.role_of(CHEF)["bus"] == ["CARS"] and timesheets.role_of(CHEF_XC)["bus"] == ["XC"]
    assert timesheets.role_of(NOBODY)["role"] is None
    assert api.put("/api/resources/staff/m1", json={"workshop": "chef_all"}).status_code in (200, 403)
    assert timesheets.role_of(MEC)["role"] in ("mechanic", "chef")
    as_(api, NOBODY)
    assert api.get("/api/timesheets/me").json()["role"] is None
    assert api.get("/api/timesheets/week", params={"start": "2026-06-01"}).status_code == 403


def test_only_chef_creates_jobs_and_background_defaults(api):
    as_(api, MEC)
    assert api.post("/api/timesheets/jobs", json={"kind": "atelier", "title": "x", "bu": "CARS"}).status_code == 403
    titles = [j["title"] for j in api.get("/api/timesheets/jobs").json()["jobs"]]
    assert "Nettoyage atelier" in titles
    assert mkjob(api, bu="XC").status_code == 403                                  # le chef CARS ne crée pas de job XC
    r = mkjob(api, vehicle={"id": "12", "name": "Porsche 996 GT3 Cup"})
    assert r.status_code == 200 and r.json()["billable"] is True
    assert mkjob(api, kind="background", title="Balayage", bu="ALL").json()["billable"] is False


def test_entry_create_edit_24h_validate(api, monkeypatch):
    jid = mkjob(api, vehicle={"id": "1", "name": "P"}).json()["id"]
    as_(api, MEC)
    r = api.post("/api/timesheets/entries", json=entry(jid))
    assert r.status_code == 200 and r.json()["can_edit"] is True
    eid = r.json()["id"]
    assert api.put(f"/api/timesheets/entries/{eid}", json=entry(jid, minutes=120)).json()["minutes"] == 120
    assert api.post("/api/timesheets/entries", json=entry(jid, minutes=7)).status_code == 422
    assert api.post(f"/api/timesheets/entries/{eid}/validate").status_code == 403           # le mécanicien ne valide pas
    as_(api, CHEF)
    assert api.post(f"/api/timesheets/entries/{eid}/validate").json()["validated"] is True
    as_(api, MEC)
    assert api.put(f"/api/timesheets/entries/{eid}", json=entry(jid)).status_code == 403    # validé : plus modifiable
    as_(api, CHEF)
    api.post(f"/api/timesheets/entries/{eid}/validate", params={"validated": "false"})
    as_(api, MEC)
    e = timesheets.entries().get(eid)
    e["created_at"] = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()
    timesheets.entries().put(eid, e)
    assert api.put(f"/api/timesheets/entries/{eid}", json=entry(jid)).status_code == 403    # 24 h écoulées
    assert api.delete(f"/api/timesheets/entries/{eid}").status_code == 403
    as_(api, CHEF)
    assert api.put(f"/api/timesheets/entries/{eid}", json=entry(jid, minutes=60)).status_code == 200   # le chef peut toujours
    assert api.delete(f"/api/timesheets/entries/{eid}").status_code == 200


def test_mechanic_cannot_enter_for_someone_else_nor_see_others(api):
    jid = mkjob(api).json()["id"]
    as_(api, MEC)
    assert api.post("/api/timesheets/entries", json=entry(jid, user=CHEF)).status_code == 403
    eid = api.post("/api/timesheets/entries", json=entry(jid)).json()["id"]
    as_(api, CHEF_XC)                                                                       # chef de l'autre BU : pas de droit sur ce job CARS
    assert api.put(f"/api/timesheets/entries/{eid}", json=entry(jid)).status_code == 403
    assert api.get("/api/timesheets/team", params={"start": date.today().isoformat()}).status_code == 200
    as_(api, MEC)
    assert api.get("/api/timesheets/team", params={"start": date.today().isoformat()}).status_code == 403
    assert api.get("/api/timesheets/suggestions").status_code == 403


def test_week_summary_occupancy_and_billable(api):
    car = mkjob(api, vehicle={"id": "1", "name": "P"}).json()["id"]
    bg = mkjob(api, kind="background", title="Rangement", bu="ALL").json()["id"]
    as_(api, MEC)
    api.post("/api/timesheets/entries", json=entry(car, minutes=380))
    api.post("/api/timesheets/entries", json=entry(bg, minutes=190))
    s = api.get("/api/timesheets/week", params={"start": date.today().isoformat()}).json()["summary"]
    assert s["total"] == 570 and s["billable"] == 380 and s["theoretical"] == 38 * 60
    assert s["occupancy"] == 0.25 and s["billable_rate"] == round(380 / 2280, 3)
    as_(api, CHEF)
    row = next(r for r in api.get("/api/timesheets/team", params={"start": date.today().isoformat()}).json()["rows"] if r["name"] == "Nolan Collinet")
    assert row["name"] == "Nolan Collinet" and row["summary"]["total"] == 570


def test_attachments_rules(api):
    jid = mkjob(api).json()["id"]
    as_(api, MEC)
    eid = api.post("/api/timesheets/entries", json=entry(jid)).json()["id"]
    r = api.post(f"/api/timesheets/entries/{eid}/attachments?filename=a.jpg", content=b"\xff\xd8abc", headers={"Content-Type": "image/jpeg"})
    assert r.status_code == 200 and "key" not in r.json()
    aid = r.json()["id"]
    assert api.get(f"/api/timesheets/entries/{eid}/attachments/{aid}").content == b"\xff\xd8abc"
    assert api.post(f"/api/timesheets/entries/{eid}/attachments", content=b"x", headers={"Content-Type": "application/pdf"}).status_code == 422
    assert api.post(f"/api/timesheets/entries/{eid}/attachments", content=b"", headers={"Content-Type": "audio/webm"}).status_code == 422
    assert api.post(f"/api/timesheets/entries/{eid}/attachments", content=b"voix", headers={"Content-Type": "audio/webm;codecs=opus"}).status_code == 200
    as_(api, CHEF_XC)
    assert api.get(f"/api/timesheets/entries/{eid}/attachments/{aid}").status_code == 403
    assert "timesheets/" not in str(api.get("/api/timesheets/week", params={"start": date.today().isoformat()}).json())


def test_suggestions_from_planning(api):
    as_(api, CHEF)
    body = {"title": "Spa Classic", "bu": "HISTORIC_RACING", "confirmed": True, "start": (date.today() + timedelta(days=10)).isoformat(), "end": (date.today() + timedelta(days=12)).isoformat(),
            "immo_start": (date.today() + timedelta(days=8)).isoformat(), "immo_end": (date.today() + timedelta(days=14)).isoformat(),
            "place": {"id": "demo-spa", "name": "Circuit", "address": "Stavelot", "country": "BE"}, "notes": "", "staff": [], "externals": [],
            "vehicles": ["m3@resource.calendar.google.com", "sprinter@resource.calendar.google.com"]}
    from app import planning
    lbid = planning.create(planning.EventIn(**body))["id"]
    try:
        s = api.get("/api/timesheets/suggestions").json()["suggestions"]
        titles = [x["title"] for x in s]
        assert "Spa Classic" in titles and "Pre-event Spa Classic / BMW M3 E30" in titles and "Post-event Spa Classic / BMW M3 E30" in titles
        assert not any("Sprinter" in t for t in titles)                                      # utilitaire : pas de job de préparation
        mkjob(api, title="Pre-event Spa Classic / BMW M3 E30")
        assert "Pre-event Spa Classic / BMW M3 E30" not in [x["title"] for x in api.get("/api/timesheets/suggestions").json()["suggestions"]]
    finally:
        planning.remove(lbid)


def test_pointages_pages_are_grantable():
    from app import access
    assert access.path_ok("/api/timesheets/week", {"consigner/timesheets"}) and not access.path_ok("/api/timesheets/week", {"overview/ca"})


def test_entry_takes_assignment_from_job(api):
    jid = mkjob(api, assignment="setup").json()["id"]
    as_(api, MEC)
    e = api.post("/api/timesheets/entries", json=entry(jid, assignment="crash")).json()
    assert e["assignment"] == "setup"


def test_sub_bu_jobs_belong_to_cars_chef(api):
    assert mkjob(api, bu="MODERN_RALLY", title="Job MR").status_code == 200           # chef CARS : sous-BU CARS acceptées
    as_(api, CHEF_XC)
    assert api.post("/api/timesheets/jobs", json={"kind": "atelier", "title": "x", "bu": "HISTORIC_RACING"}).status_code == 403


def test_delete_job_only_without_entries(api):
    j1 = mkjob(api, title="A").json()["id"]
    j2 = mkjob(api, title="B").json()["id"]
    as_(api, MEC)
    api.post("/api/timesheets/entries", json=entry(j2))
    assert api.delete(f"/api/timesheets/jobs/{j1}").status_code == 403
    as_(api, CHEF)
    assert api.delete(f"/api/timesheets/jobs/{j2}").status_code == 409
    assert api.delete(f"/api/timesheets/jobs/{j1}").status_code == 200


def test_event_job_title_is_built_from_event_and_nature(api):
    as_(api, CHEF)
    body = {"kind": "event", "nature": "chargement", "bu": "HISTORIC_RACING", "event": {"id": "7", "title": "Imola Classic"}}
    r = api.post("/api/timesheets/jobs", json=body)
    assert r.status_code == 200 and r.json()["title"] == "Chargement camion(s) et/ou camionnette(s) — Imola Classic" and r.json()["billable"] is True
    assert api.post("/api/timesheets/jobs", json=body).status_code == 422                       # doublon
    assert api.post("/api/timesheets/jobs", json={**body, "nature": ""}).status_code == 422
    assert api.post("/api/timesheets/jobs", json={**body, "nature": "x"}).status_code == 422


def test_atelier_job_title_from_vehicle_event_nature(api):
    as_(api, CHEF)
    base = {"kind": "atelier", "bu": "HISTORIC_RACING", "vehicle": {"id": "3", "name": "Porsche 996 GT3 Cup"}, "event": {"id": "7", "title": "Spa Classic"}}
    r = api.post("/api/timesheets/jobs", json={**base, "nature": "pre_event"})
    assert r.json()["title"] == "Pre-event Spa Classic / Porsche 996 GT3 Cup" and r.json()["assignment"] == "prepa" and r.json()["billable"] is True
    assert api.post("/api/timesheets/jobs", json={**base, "nature": "post_event"}).json()["title"].startswith("Post-event Spa Classic")
    assert api.post("/api/timesheets/jobs", json={**base, "nature": "pre_event", "event": None}).status_code == 422
    c = api.post("/api/timesheets/jobs", json={"kind": "atelier", "bu": "CARS", "nature": "custom", "title": "Révision boîte", "vehicle": base["vehicle"]})
    assert c.json()["title"] == "Révision boîte / Porsche 996 GT3 Cup"
    assert api.post("/api/timesheets/jobs", json={"kind": "atelier", "bu": "CARS", "nature": "custom", "title": "x"}).status_code == 422
