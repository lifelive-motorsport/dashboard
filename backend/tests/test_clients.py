import re
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app import clients, mailer, rides, resources, settings, timesheets, users
from app.auth import require_user
from app.main import app

CLIENT_MAIL = "pilote@client.example"


@pytest.fixture()
def env(monkeypatch):
    for n in ("_clients", "_links", "_audit"):
        monkeypatch.setattr(clients, n, None)
    for n in ("_cars", "_parts", "_runs", "_circuits", "_catalog", "_maint", "_templates", "_sessions"):
        monkeypatch.setattr(rides, n, None)
    for n in ("_jobs", "_entries", "_blobs", "_templates"):
        monkeypatch.setattr(timesheets, n, None)
    monkeypatch.setattr(users, "is_super", lambda e: True)
    mailer.OUTBOX.clear()
    import app.main as m
    m._client_hits.clear()
    app.dependency_overrides[require_user] = lambda: "md@lifelive-motorsport.com"
    yield TestClient(app)
    app.dependency_overrides.pop(require_user, None)


def keys(api):
    return {c["name"]: c["key"] for c in api.get("/api/rides/cars").json()["cars"]}


def make_client(api, cars, emails=(CLIENT_MAIL,), name="Écurie Test"):
    return api.post("/api/admin/clients", json={"name": name, "emails": list(emails), "cars": cars})


def login(api, email=CLIENT_MAIL):
    """Demande un lien, le lit dans l'e-mail envoyé et le valide : renvoie le client HTTP avec son cookie de session."""
    mailer.OUTBOX.clear()
    assert api.post("/api/client/request-link", json={"email": email}).json() == {"ok": True}
    body = mailer.OUTBOX[-1]["body"]
    token = re.search(r"#t=([\w-]+)", body).group(1)
    c = TestClient(app)
    r = c.post("/api/client/verify", json={"token": token})
    assert r.status_code == 200
    return c, token


def test_admin_manages_clients_and_validates_input(env):
    k = keys(env)
    assert make_client(env, ["inconnue"]).status_code == 422
    assert make_client(env, [k["BMW M3 E30"]], emails=["pas une adresse"]).status_code == 422
    r = make_client(env, [k["BMW M3 E30"]])
    assert r.status_code == 200 and r.json()["cars"][0]["name"] == "BMW M3 E30" and r.json()["emails"] == [CLIENT_MAIL]
    assert make_client(env, [], name="écurie test").status_code == 422                                # nom déjà pris
    cid = r.json()["id"]
    assert env.put(f"/api/admin/clients/{cid}", json={"name": "Écurie Test", "emails": [CLIENT_MAIL, "Autre@Client.example"], "cars": [], "active": True}).json()["emails"][1] == "autre@client.example"
    listing = env.get("/api/admin/clients").json()
    assert len(listing["clients"]) == 1 and any(c["name"] == "Porsche 992 Rally" for c in listing["cars"])
    assert env.delete(f"/api/admin/clients/{cid}").status_code == 200 and env.get("/api/admin/clients").json()["clients"] == []


def test_magic_link_is_single_use_expires_and_does_not_reveal_unknown_addresses(env):
    k = keys(env)
    cid = make_client(env, [k["BMW M3 E30"]]).json()["id"]
    mailer.OUTBOX.clear()
    assert env.post("/api/client/request-link", json={"email": "inconnu@nulle.part"}).json() == {"ok": True}        # même réponse
    assert mailer.OUTBOX == []                                                                                       # mais rien n'est envoyé
    c, token = login(env)
    assert c.get("/api/client/me").json()["cars"][0]["name"] == "BMW M3 E30"
    assert TestClient(app).post("/api/client/verify", json={"token": token}).status_code == 400                      # à usage unique
    # expiré
    mailer.OUTBOX.clear()
    env.post("/api/client/request-link", json={"email": CLIENT_MAIL})
    t2 = re.search(r"#t=([\w-]+)", mailer.OUTBOX[-1]["body"]).group(1)
    doc = clients.links_coll().get(clients._h(t2))
    doc["exp"] = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    clients.links_coll().put(doc["id"], doc)
    assert TestClient(app).post("/api/client/verify", json={"token": t2}).status_code == 400
    assert TestClient(app).post("/api/client/verify", json={"token": "n'importe quoi"}).status_code == 400
    # le jeton n'est jamais stocké en clair
    assert token not in str(clients.links_coll().all())
    # désactiver le client coupe la session en cours et les nouveaux liens
    env.put(f"/api/admin/clients/{cid}", json={"name": "Écurie Test", "emails": [CLIENT_MAIL], "cars": [k["BMW M3 E30"]], "active": False})
    assert c.get("/api/client/me").status_code == 401
    mailer.OUTBOX.clear()
    env.post("/api/client/request-link", json={"email": CLIENT_MAIL})
    assert mailer.OUTBOX == []


def test_link_requests_are_throttled(env):
    make_client(env, [])
    mailer.OUTBOX.clear()
    for _ in range(8):
        env.post("/api/client/request-link", json={"email": CLIENT_MAIL})
    assert len(mailer.OUTBOX) == clients.MAX_LINKS_PER_HOUR


def test_client_cookie_opens_no_internal_route_and_internal_login_opens_no_client_route(env, monkeypatch):
    k = keys(env)
    make_client(env, [k["BMW M3 E30"]])
    c, _ = login(env)
    app.dependency_overrides.pop(require_user, None)
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)                                                              # comme en production
    for path in ("/api/rides/cars", "/api/timesheets/jobs", "/api/dashboard", "/api/session", "/api/admin/clients", "/api/planning", "/api/alerts"):
        assert c.get(path).status_code in (401, 403), path
    assert TestClient(app).get("/api/client/me").status_code == 401                                                 # sans cookie client


def test_client_sees_only_his_cars_with_documents_runs_and_validated_jobs_without_internal_data(env):
    k = keys(env)
    m3, p992 = k["BMW M3 E30"], k["Porsche 992 Rally"]
    rides.cars_coll().put(m3, {"id": m3, "odoo_id": 77, "odoo_name": "BMW M3", "livery": "Bleu", "race_number": "12"})
    rides.cars_coll().put(p992, {"id": p992})
    env.post("/api/rides/circuits", json={"name": "Dijon", "length_km": 3.8})
    s = env.post("/api/rides/sessions", json={"date": "2026-06-04", "name": "Essais Dijon", "kind": "circuit", "circuit": "Dijon"}).json()
    env.post(f"/api/rides/sessions/{s['id']}/cars/{m3}", json={"laps": 10, "hours": 1, "drivers": ["Max Secret"], "notes": "note interne"})
    env.post(f"/api/rides/sessions/{s['id']}/cars/{p992}", json={"laps": 5})
    env.put(f"/api/rides/cars/{m3}/docs/fia", json={"expires": "2030-01-01", "note": "NOTE INTERNE DOC"})
    env.post(f"/api/rides/cars/{m3}/docs/fia/files?name=fia.pdf", content=b"%PDF-1.4 x", headers={"Content-Type": "application/pdf"})
    # jobs : un du M3 (id Odoo 77), un de la Porsche
    ids = {}
    for name, vid in (("BMW M3", "77"), ("Porsche 992", "5")):
        j = timesheets.create_job(timesheets.JobIn(kind="atelier", nature="custom", bu="CARS", vehicle=timesheets.VehicleRef(id=vid, name=name), title="Révision"), "chef@lifelive-motorsport.com")
        ids[name] = j["id"]
    job = timesheets.jobs().get(ids["BMW M3"])
    job["checklist"] = {"template_id": "t", "template_name": "T", "sections": [{"id": "s", "title": "Moteur", "lines": [{"id": "l1", "text": "Vidange", "note": "NOTE LIGNE", "done": True, "done_by": "Julien SECRET", "done_at": "2026-06-02T10:00:00+00:00", "entry_id": "e1"}]}]}
    timesheets.jobs().put(job["id"], job)
    base = {"user": "julien@lifelive-motorsport.com", "date": "2026-06-02", "minutes": 90, "assignment": "prepa", "system": "moteur", "created_at": "2026-06-02T10:00:00+00:00"}
    timesheets.blobs().put("timesheets/e1/p.jpg", b"\xff\xd8\xff", "image/jpeg")
    timesheets.blobs().put("timesheets/e1/a.webm", b"audio", "audio/webm")
    timesheets.entries().put("e1", {**base, "id": "e1", "job_id": job["id"], "text": "Vidange moteur faite", "lines": ["l1"], "validated": True,
                                    "attachments": [{"id": "pho-1", "kind": "photo", "name": "p.jpg", "key": "timesheets/e1/p.jpg"}, {"id": "aud-secret", "kind": "audio", "name": "a.webm", "key": "timesheets/e1/a.webm"}]})
    timesheets.entries().put("e2", {**base, "id": "e2", "job_id": job["id"], "text": "PAS ENCORE VALIDÉ", "validated": False})
    other = ids["Porsche 992"]
    timesheets.entries().put("e3", {**base, "id": "e3", "job_id": other, "text": "AUTRE CLIENT", "validated": True})
    make_client(env, [m3])
    c, _ = login(env)
    me = c.get("/api/client/me").json()
    assert [x["name"] for x in me["cars"]] == ["BMW M3 E30"]
    car = c.get(f"/api/client/cars/{m3}").json()
    fia = next(d for d in car["docs"] if d["item"] == "fia")
    assert car["race_number"] == "12" and car["km_total"] == 38.0 and fia["files"][0]["name"] == "fia.pdf"
    assert "NOTE INTERNE" not in str(car) and "Max Secret" not in str(car) and "drivers" not in str(car)             # notes et pilotes internes absents
    assert c.get(f"/api/client/cars/{p992}").status_code == 404 and c.get(f"/api/client/cars/{p992}/jobs").status_code == 404
    jobs = c.get(f"/api/client/cars/{m3}/jobs").json()["jobs"]
    assert len(jobs) == 1 and jobs[0]["title"] == "Révision / BMW M3" and [e["id"] for e in jobs[0]["entries"]] == ["e1"]
    raw = str(jobs)
    for secret in ("julien", "SECRET", "NOTE LIGNE", "PAS ENCORE", "AUTRE CLIENT", "audio", "aud-secret", "billable"):
        assert secret not in raw, secret
    assert jobs[0]["entries"][0]["lines"] == ["Vidange"] and jobs[0]["entries"][0]["photos"] == [{"id": "pho-1", "name": "p.jpg"}]
    # photos et fichiers : seulement ceux de ses voitures, pointages validés, photos (pas les mémos vocaux)
    assert c.get(f"/api/client/cars/{m3}/entries/e1/photos/pho-1").content.startswith(b"\xff\xd8")
    assert c.get(f"/api/client/cars/{m3}/entries/e1/photos/aud-secret").status_code == 404
    assert c.get(f"/api/client/cars/{m3}/entries/e2/photos/pho-1").status_code == 404
    assert c.get(f"/api/client/cars/{m3}/entries/e3/photos/pho-1").status_code == 404
    assert c.get(f"/api/client/cars/{p992}/entries/e3/photos/pho-1").status_code == 404
    fid = fia["files"][0]["id"]
    assert c.get(f"/api/client/cars/{m3}/docs/fia/files/{fid}").content.startswith(b"%PDF")
    assert c.get(f"/api/client/cars/{p992}/docs/fia/files/{fid}").status_code == 404
    # une voiture archivée disparaît de l'espace client
    rides.cars_coll().put(m3, {**rides.cars_coll().get(m3), "archived": True})
    assert c.get("/api/client/me").json()["cars"] == [] and c.get(f"/api/client/cars/{m3}").status_code == 404
    # déconnexion
    c.post("/api/client/logout")
    assert c.get("/api/client/me").status_code == 401


def test_job_without_odoo_id_is_matched_by_car_name(env):
    k = keys(env)
    m3 = k["BMW M3 E30"]
    j = timesheets.create_job(timesheets.JobIn(kind="atelier", nature="custom", bu="CARS", vehicle=timesheets.VehicleRef(id="", name="BMW M3 E30"), title="Révision"), "chef@lifelive-motorsport.com")
    make_client(env, [m3])
    c, _ = login(env)
    assert [x["id"] for x in c.get(f"/api/client/cars/{m3}/jobs").json()["jobs"]] == [j["id"]]


def test_similar_car_names_never_leak_jobs_between_clients(env):
    k = keys(env)
    m3, p992 = k["BMW M3 E30"], k["Porsche 992 Rally"]
    timesheets.create_job(timesheets.JobIn(kind="atelier", nature="custom", bu="CARS", vehicle=timesheets.VehicleRef(id="", name="BMW M3 E30 Ducal"), title="Révision"), "chef@lifelive-motorsport.com")
    make_client(env, [m3, p992])
    c, _ = login(env)
    assert c.get(f"/api/client/cars/{m3}/jobs").json()["jobs"] == []                                    # nom proche mais pas identique : rien
