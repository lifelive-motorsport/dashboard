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
    monkeypatch.setattr(timesheets, "_templates", None)
    monkeypatch.setattr(timesheets, "_alert_coll", None)
    from app import mailer
    mailer.OUTBOX.clear()
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


def local_today():
    from app import presence
    return presence.local_now().date()                                  # date de Bruxelles : celle du Cockpit (date.today() est en UTC, différent entre 22 h et minuit)


def entry(job, **kw):
    return {"job_id": job, "date": local_today().isoformat(), "minutes": 90, "assignment": "prepa", "system": "moteur", "text": "Vidange", **kw}


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


def test_team_lists_entries_of_accounts_outside_the_staff_list(api):
    car = mkjob(api, vehicle={"id": "1", "name": "P"}).json()["id"]
    eid = "e-hors"                                                   # pointage d'un compte (ex. Super User) sans fiche staff liée
    timesheets.entries().put(eid, {**entry(car, minutes=60), "id": eid, "user": NOBODY.lower(), "created_at": "2026-01-01T00:00:00+00:00", "validated": False, "lines": [], "attachments": []})
    as_(api, CHEF)
    rows = api.get("/api/timesheets/team", params={"start": date.today().isoformat()}).json()["rows"]
    other = next(r for r in rows if r.get("other"))
    assert other["user"] == NOBODY.lower() and other["summary"]["total"] == 60 and other["entries"][0]["id"] == eid
    assert not any(r.get("other") for r in rows if r["name"] == "Nolan Collinet")


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


def test_system_only_for_workshop_jobs(api):
    ev = mkjob(api, kind="event", title="Chargement — Imola", bu="CARS", event={"id": "1", "title": "Imola"}, nature="chargement").json()["id"]
    as_(api, MEC)
    assert api.post("/api/timesheets/entries", json=entry(ev, system="moteur")).json()["system"] == "autre"


def test_team_hours_follow_bu_filter(api):
    cars = mkjob(api, title="Job HR", bu="HISTORIC_RACING").json()["id"]
    bg = mkjob(api, kind="background", title="Rangement 2", bu="ALL").json()["id"]
    as_(api, MEC)
    api.post("/api/timesheets/entries", json=entry(cars, minutes=120))
    api.post("/api/timesheets/entries", json=entry(bg, minutes=60))
    as_(api, CHEF)
    tot = lambda bu: next(r for r in api.get("/api/timesheets/team", params={"start": date.today().isoformat(), "bu": bu}).json()["rows"] if r["name"] == "Nolan Collinet")["summary"]["total"]
    assert (tot("all"), tot("cars"), tot("hrc"), tot("hrl"), tot("xc")) == (180, 120, 120, 0, 0)


def test_remove_attachment(api):
    jid = mkjob(api).json()["id"]
    as_(api, MEC)
    eid = api.post("/api/timesheets/entries", json=entry(jid)).json()["id"]
    aid = api.post(f"/api/timesheets/entries/{eid}/attachments", content=b"voix", headers={"Content-Type": "audio/webm"}).json()["id"]
    as_(api, CHEF_XC)
    assert api.delete(f"/api/timesheets/entries/{eid}/attachments/{aid}").status_code == 403
    as_(api, MEC)
    assert api.delete(f"/api/timesheets/entries/{eid}/attachments/{aid}").status_code == 200
    assert api.get(f"/api/timesheets/entries/{eid}/attachments/{aid}").status_code == 404
    assert api.delete(f"/api/timesheets/entries/{eid}/attachments/{aid}").status_code == 404


def test_edit_job_recomputes_title_and_keeps_rights(api):
    as_(api, CHEF)
    v = {"id": "3", "name": "BMW M3"}
    j = api.post("/api/timesheets/jobs", json={"kind": "atelier", "bu": "HISTORIC_RACING", "nature": "pre_event", "vehicle": v, "event": {"id": "1", "title": "Spa"}}).json()
    r = api.put(f"/api/timesheets/jobs/{j['id']}", json={"kind": "atelier", "bu": "HISTORIC_RACING", "nature": "post_event", "vehicle": v, "event": {"id": "1", "title": "Spa"}})
    assert r.json()["title"] == "Post-event Spa / BMW M3" and r.json()["assignment"] == "revision"
    r = api.put(f"/api/timesheets/jobs/{j['id']}", json={"kind": "atelier", "bu": "HISTORIC_RACING", "nature": "post_event", "vehicle": v, "event": {"id": "1", "title": "Spa"}, "open": False})
    assert r.json()["open"] is False and r.json()["title"] == "Post-event Spa / BMW M3"
    assert api.put(f"/api/timesheets/jobs/{j['id']}", json={"kind": "atelier", "bu": "XC", "nature": "post_event", "vehicle": v, "event": {"id": "1", "title": "Spa"}}).status_code == 403
    as_(api, CHEF_XC)
    assert api.put(f"/api/timesheets/jobs/{j['id']}", json={"kind": "atelier", "bu": "XC", "nature": "post_event", "vehicle": v, "event": {"id": "1", "title": "Spa"}}).status_code == 403


def _wav(seconds, rate=16000, ch=1):
    import io, wave
    b = io.BytesIO()
    with wave.open(b, "wb") as w:
        w.setnchannels(ch); w.setsampwidth(2); w.setframerate(rate); w.writeframes(b"\0\0" * rate * ch * seconds)
    return b.getvalue()


def test_transcribe_chunks_long_memos_and_rejects_bad_audio(api, monkeypatch):
    from app import speech
    seen = []
    monkeypatch.setattr(speech, "_recognize", lambda chunk: (seen.append(len(chunk)), f"partie {len(seen)}")[1])
    as_(api, MEC)
    r = api.post("/api/timesheets/transcribe", content=_wav(120), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 200 and r.json()["text"] == "partie 1 partie 2 partie 3" and len(seen) == 3          # 50 s + 50 s + 20 s
    assert api.post("/api/timesheets/transcribe", content=_wav(5, rate=44100), headers={"Content-Type": "audio/wav"}).status_code == 422
    assert api.post("/api/timesheets/transcribe", content=b"pas du wav", headers={"Content-Type": "audio/wav"}).status_code == 422
    assert api.post("/api/timesheets/transcribe", content=_wav(200), headers={"Content-Type": "audio/wav"}).status_code == 422
    as_(api, NOBODY)
    assert api.post("/api/timesheets/transcribe", content=_wav(2), headers={"Content-Type": "audio/wav"}).status_code == 403


def test_transcribe_google_error_is_reported_not_crashing(api, monkeypatch):
    from app import speech
    def boom(chunk): raise speech.SpeechError("API non activée")
    monkeypatch.setattr(speech, "_recognize", boom)
    as_(api, MEC)
    r = api.post("/api/timesheets/transcribe", content=_wav(2), headers={"Content-Type": "audio/wav"})
    assert r.status_code == 422 and "API non activée" in r.json()["detail"]


def test_speech_request_shape(monkeypatch):
    from app import speech
    seen = {}

    class R:
        status_code = 200
        def json(self): return {"results": [{"alternatives": [{"transcript": " bonjour "}]}, {"alternatives": [{"transcript": "atelier"}]}]}

    class S:
        def post(self, url, json, timeout):
            seen.update(url=url, body=json)
            return R()
    monkeypatch.setattr(speech, "_session", lambda: (S(), "mon-projet"))
    assert speech._recognize(b"abc") == "bonjour atelier"
    assert seen["url"] == "https://europe-west4-speech.googleapis.com/v2/projects/mon-projet/locations/europe-west4/recognizers/_:recognize"
    c = seen["body"]["config"]
    assert c["model"] == "chirp_2" and c["languageCodes"] == ["fr-FR"] and c["explicitDecodingConfig"]["encoding"] == "LINEAR16"


def test_old_voice_memos_are_flagged_expired_photos_are_not(api):
    jid = mkjob(api).json()["id"]
    as_(api, MEC)
    eid = api.post("/api/timesheets/entries", json=entry(jid)).json()["id"]
    api.post(f"/api/timesheets/entries/{eid}/attachments", content=b"voix", headers={"Content-Type": "audio/webm"})
    api.post(f"/api/timesheets/entries/{eid}/attachments", content=b"\xff\xd8x", headers={"Content-Type": "image/jpeg"})
    e = timesheets.entries().get(eid)
    for a in e["attachments"]:
        a["created_at"] = (datetime.now(timezone.utc) - timedelta(days=100)).isoformat()
    timesheets.entries().put(eid, e)
    atts = api.get("/api/timesheets/week", params={"start": date.today().isoformat()}).json()["entries"][0]["attachments"]
    assert {a["kind"]: a["expired"] for a in atts} == {"audio": True, "photo": False}


TPL = {"name": "Mini révision", "bu": "CARS", "natures": ["pre_event"], "sections": [{"title": "Moteur", "lines": [{"text": "Vidange"}, {"text": "Filtre à air", "note": "si besoin"}]}, {"title": "Freins", "lines": [{"text": "Purge"}]}]}


def checklist_job(api, tid):
    return mkjob(api, vehicle={"id": "1", "name": "P"}, nature="custom", title="Révision", template_id=tid).json()


def test_seed_template_and_rights(api):
    as_(api, CHEF)
    ts_ = api.get("/api/timesheets/templates").json()["templates"]
    assert [t["name"] for t in ts_] == ["Révision Circuit 2RM atmosphérique", "Révision Circuit 2RM turbo", "Révision Rallye 992", "Révision Rallye i20 Rally2", "Révision Rallye M3 E30"]
    assert all(sum(len(s["lines"]) for s in t["sections"]) > 30 for t in ts_)
    for t in ts_:
        assert api.delete(f"/api/timesheets/templates/{t['id']}").status_code == 200
    assert api.get("/api/timesheets/templates").json()["templates"] == []                 # supprimés : les modèles de départ ne reviennent pas
    as_(api, MEC)
    assert api.get("/api/timesheets/templates").status_code == 403
    assert api.post("/api/timesheets/templates", json=TPL).status_code == 403
    as_(api, CHEF_XC)
    assert api.post("/api/timesheets/templates", json=TPL).status_code == 403              # modèle CARS : pas le chef XC
    as_(api, CHEF)
    assert api.post("/api/timesheets/templates", json=TPL).status_code == 200
    assert api.post("/api/timesheets/templates", json=TPL).status_code == 422              # nom déjà pris
    assert api.post("/api/timesheets/templates", json={**TPL, "name": "Vide", "sections": [{"title": "X", "lines": []}]}).status_code == 422


def test_job_gets_a_copy_of_the_checklist_and_lines_are_ticked_by_entries(api):
    as_(api, CHEF)
    t = api.post("/api/timesheets/templates", json=TPL).json()
    job = checklist_job(api, t["id"])
    assert job["progress"] == {"done": 0, "total": 3}
    l0, l1, l2 = [ln["id"] for s in job["checklist"]["sections"] for ln in s["lines"]]
    api.put(f"/api/timesheets/templates/{t['id']}", json={**TPL, "sections": [{"title": "Autre", "lines": [{"text": "Nouveau"}]}]})
    assert api.get("/api/timesheets/jobs").json()["jobs"][0]["progress"]["total"] == 3     # la copie du job ne change pas
    as_(api, MEC)
    e = api.post("/api/timesheets/entries", json=entry(job["id"], lines=[l0, l2])).json()
    assert [x["text"] for x in e["lines"]] == ["Vidange", "Purge"] and e["system"] == "autre"
    j = next(j for j in api.get("/api/timesheets/jobs").json()["jobs"] if j["id"] == job["id"])
    assert j["progress"]["done"] == 2 and j["checklist"]["sections"][0]["lines"][0]["done_by"] == "Nolan Collinet"
    as_(api, CHEF)
    assert api.post("/api/timesheets/entries", json=entry(job["id"], lines=[l0])).status_code == 422       # déjà faite par un collègue
    as_(api, MEC)
    api.put(f"/api/timesheets/entries/{e['id']}", json=entry(job["id"], lines=[l0]))                        # on décoche « Purge »
    assert next(j for j in api.get("/api/timesheets/jobs").json()["jobs"] if j["id"] == job["id"])["progress"]["done"] == 1
    assert api.put(f"/api/timesheets/entries/{e['id']}", json=entry(job["id"], lines=["inconnue"])).status_code == 422
    api.delete(f"/api/timesheets/entries/{e['id']}")
    assert next(j for j in api.get("/api/timesheets/jobs").json()["jobs"] if j["id"] == job["id"])["progress"]["done"] == 0


def test_reject_with_reason_correction_trace_and_job_done(api):
    jid = mkjob(api, vehicle={"id": "1", "name": "P"}).json()["id"]
    as_(api, MEC)
    e = api.post("/api/timesheets/entries", json=entry(jid, minutes=120)).json()
    assert e["status"] == "sent"
    assert api.post(f"/api/timesheets/entries/{e['id']}/reject", json={"reason": "x"}).status_code == 403          # le mécanicien ne renvoie pas
    as_(api, CHEF)
    assert api.post(f"/api/timesheets/entries/{e['id']}/reject", json={"reason": "ab"}).status_code == 422          # motif trop court
    r = api.post(f"/api/timesheets/entries/{e['id']}/reject", json={"reason": "Heures fausses : tu étais à Spa"}).json()
    assert r["status"] == "returned" and r["thread"][-1]["kind"] == "reject"
    old = timesheets.entries().get(e["id"])
    old["created_at"] = (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()                                   # bien au-delà des 24 h
    timesheets.entries().put(e["id"], old)
    as_(api, MEC)
    r = api.put(f"/api/timesheets/entries/{e['id']}", json=entry(jid, minutes=60)).json()                            # renvoyé : corrigeable malgré les 24 h
    assert r["status"] == "sent" and r["thread"][-1]["kind"] == "resubmit" and r["minutes"] == 60
    as_(api, CHEF)
    r = api.put(f"/api/timesheets/entries/{e['id']}", json=entry(jid, minutes=90)).json()                            # correction du chef : tracée
    assert r["adjusted"] is True and "Correction" in r["thread"][-1]["text"]
    assert api.post(f"/api/timesheets/entries/{e['id']}/validate").json()["status"] == "adjusted"
    as_(api, MEC)
    assert api.put(f"/api/timesheets/entries/{e['id']}", json=entry(jid)).status_code == 403                          # validé : verrouillé
    e2 = api.post("/api/timesheets/entries", json=entry(jid, job_done=True)).json()
    assert e2["job_done"] is True
    assert next(j for j in timesheets.jobs().all() if j["id"] == jid)["open"] is False                               # « terminé » : le job est clôturé
    assert api.post("/api/timesheets/entries", json=entry(jid)).status_code == 422


def _at(y, m, d, hh, mm=0):
    from app import presence
    return datetime(y, m, d, hh, mm, tzinfo=presence.TZ)


def test_belgian_holidays_and_cutoffs():
    from app import presence
    h = presence.holidays_be(2026)
    assert date(2026, 4, 6) in h and date(2026, 5, 14) in h and date(2026, 5, 25) in h and date(2026, 7, 21) in h and date(2026, 11, 11) in h
    assert presence.cutoff(date(2026, 10, 12)).hour == 17 and presence.cutoff(date(2026, 10, 16)).hour == 15            # lundi 17 h, vendredi 15 h
    assert not presence.is_workday(date(2026, 11, 11), None) and not presence.is_workday(date(2026, 10, 17), None)    # férié, samedi
    assert presence.is_workday(date(2026, 10, 14), {"work_days": [0, 1, 2, 3, 4]}) and not presence.is_workday(date(2026, 10, 14), {"work_days": [0, 1]})


def test_missing_days_cockpit_and_alert_mail(api, monkeypatch):
    from app import mailer, presence
    jid = mkjob(api, kind="background", title="Rangement 3", bu="ALL").json()["id"]
    monkeypatch.setattr(presence, "event_absences", lambda emails, a, b: {})
    as_(api, MEC)
    api.post("/api/timesheets/entries", json=entry(jid, date="2026-10-12"))                                           # lundi pointé, mardi non
    mon, tue_5pm, tue_noon = date(2026, 10, 12), _at(2026, 10, 13, 17, 5), _at(2026, 10, 13, 12)
    person = timesheets.person_of(MEC)
    assert timesheets.missing_for(person, MEC, lookback=1, now=tue_5pm) == ["2026-10-13"]                                           # mardi 17 h passées : dû
    assert timesheets.missing_for(person, MEC, lookback=1, now=tue_noon) == []                                                       # mardi midi : pas encore dû
    c = {r["user"]: r for r in timesheets.cockpit(tue_5pm)["rows"]}[MEC]
    assert c["state"] == "late" and c["missing"][-1] == "2026-10-13" and "2026-10-12" not in c["missing"]
    assert {r["user"]: r for r in timesheets.cockpit(tue_noon)["rows"]}[MEC]["state"] == "waiting"
    monkeypatch.setattr(presence, "event_absences", lambda emails, a, b: {MEC: {date(2026, 10, 13): "Spa Classic"}})
    c = {r["user"]: r for r in timesheets.cockpit(tue_5pm)["rows"]}[MEC]
    assert c["state"] == "absent" and c["reason"] == "Spa Classic" and "2026-10-13" not in c["missing"]                              # sur événement : excusé
    monkeypatch.setattr(presence, "event_absences", lambda emails, a, b: {})
    r = timesheets.send_alerts(tue_5pm)
    assert MEC in r["sent"] and mailer.OUTBOX[-1]["to"] == MEC and "13/10/2026" in mailer.OUTBOX[-1]["body"]
    n = len(mailer.OUTBOX)
    assert MEC not in timesheets.send_alerts(tue_5pm)["sent"] and len(mailer.OUTBOX) == n                               # une seule fois par jour
    assert timesheets.send_alerts(_at(2026, 10, 17, 17))["sent"] == []                                                  # samedi : rien
    as_(api, CHEF)
    assert api.get("/api/timesheets/cockpit").status_code == 200
    as_(api, MEC)
    assert api.get("/api/timesheets/cockpit").status_code == 403
    assert "missing" in api.get("/api/timesheets/week", params={"start": "2026-10-12"}).json()


def test_recent_jobs_and_cron_auth(api, monkeypatch):
    a = mkjob(api, kind="background", title="Aa", bu="ALL").json()["id"]
    b = mkjob(api, kind="background", title="Bb", bu="ALL").json()["id"]
    as_(api, MEC)
    api.post("/api/timesheets/entries", json=entry(a))
    api.post("/api/timesheets/entries", json=entry(b))
    api.post("/api/timesheets/entries", json=entry(a))
    assert api.get("/api/timesheets/jobs").json()["recent"] == [a, b]                                                   # le plus récent d'abord
    assert api.post("/api/cron/timesheet-alerts").status_code == 503                                                    # non configuré
    from app import settings
    monkeypatch.setattr(settings, "CRON_AUDIENCE", "https://x.run.app")
    monkeypatch.setattr(settings, "CRON_SERVICE_ACCOUNT", "sched@p.iam.gserviceaccount.com")
    assert api.post("/api/cron/timesheet-alerts").status_code == 401
    from google.oauth2 import id_token
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda t, r, audience: {"email": "other@x.com", "email_verified": True})
    assert api.post("/api/cron/timesheet-alerts", headers={"Authorization": "Bearer t"}).status_code == 403
    monkeypatch.setattr(id_token, "verify_oauth2_token", lambda t, r, audience: {"email": "sched@p.iam.gserviceaccount.com", "email_verified": True})
    assert api.post("/api/cron/timesheet-alerts", headers={"Authorization": "Bearer t"}).status_code == 200


def test_alerts_status_paused_active_and_unreadable(monkeypatch):
    from app import scheduler, settings
    monkeypatch.setattr(settings, "CRON_AUDIENCE", "https://x.run.app")
    monkeypatch.setattr(settings, "PROVIDER", "odoo")
    mk = lambda *states: [{"name": f"projects/p/locations/l/jobs/j{i}", "state": s, "schedule": "0 17 * * 1-4", "httpTarget": {"uri": "https://x.run.app/api/cron/timesheet-alerts"}} for i, s in enumerate(states)] + [{"name": "projects/p/locations/l/jobs/autre", "state": "PAUSED", "httpTarget": {"uri": "https://x/autre"}}]
    for states, want in ((("PAUSED", "PAUSED"), "paused"), (("ENABLED", "ENABLED"), "active"), (("ENABLED", "PAUSED"), "mixed"), ((), "none")):
        monkeypatch.setattr(scheduler, "_list_jobs", lambda s=states: mk(*s))
        assert scheduler.alerts_status(force=True)["state"] == want                                     # les autres déclencheurs ne comptent pas
    def boom(): raise RuntimeError("PERMISSION_DENIED")
    monkeypatch.setattr(scheduler, "_list_jobs", boom)
    r = scheduler.alerts_status(force=True)
    assert r["state"] == "unknown" and "PERMISSION_DENIED" in r["error"]


def test_wall_snapshot_has_no_money_and_needs_the_page(api, monkeypatch):
    from app import presence
    monkeypatch.setattr(presence, "event_absences", lambda emails, a, b: {})
    jid = mkjob(api, title="Révision Porsche", vehicle={"id": "9", "name": "Porsche 911"}).json()["id"]
    as_(api, MEC)
    api.post("/api/timesheets/entries", json=entry(jid))
    as_(api, CHEF)
    monkeypatch.setattr(users, "pages_of", lambda e: {"consigner/wall"} if e == CHEF else None)
    r = api.get("/api/wall")
    assert r.status_code == 200
    s = r.json()
    j = next(x for x in s["jobs"] if x["title"] == "Révision Porsche")
    assert j["vehicle"] == "Porsche 911" and j["minutes_week"] == 90 and j["today"] == ["Nolan Collinet"]
    assert s["indicators"]["all"]["jobs_open"] >= 1 and s["indicators"]["all"]["hours_week"] >= 1.5
    assert s["indicators"]["cars"]["hours_week"] >= 1.5 and s["indicators"]["xc"]["hours_week"] == 0      # job CARS : compté dans CARS, pas dans XC
    assert s["indicators"]["xc"]["expected"] <= s["indicators"]["all"]["expected"]
    assert "€" not in str(s) and "amount" not in str(s)
    as_(api, NOBODY)
    monkeypatch.setattr(users, "pages_of", lambda e: {"planifier/planning"})
    assert api.get("/api/wall").status_code == 403


def test_wall_shows_the_staff_name_even_without_workshop_role(api, monkeypatch):
    from app import presence
    monkeypatch.setattr(presence, "event_absences", lambda emails, a, b: {})
    jid = mkjob(api, title="Révision BMW").json()["id"]
    cur = staff.store().get()
    people = cur["data"]["people"] + [{"id": "r1", "name": "Raphaël de Borman", "kind": "independant", "function": "MD", "google_email": "raphael.deborman@lifelive-motorsport.com"}]
    assert staff.store().put({"params": cur["data"]["params"], "people": people}, "t", cur["updated_at"]) is not None
    as_(api, CHEF)
    assert api.post("/api/timesheets/entries", json=entry(jid, user="raphael.deborman@lifelive-motorsport.com")).status_code in (200, 201, 403, 422)
    monkeypatch.setattr(users, "pages_of", lambda e: {"consigner/wall"})
    timesheets.entries().put("x1", {"id": "x1", "job_id": jid, "user": "raphael.deborman@lifelive-motorsport.com", "date": local_today().isoformat(), "minutes": 60, "created_at": "2026-01-01T00:00:00+00:00"})
    j = next(x for x in api.get("/api/wall").json()["jobs"] if x["title"] == "Révision BMW")
    assert "Raphaël de Borman" in j["today"]


def test_resource_bus_is_independent_from_cost_allocation(api, monkeypatch):
    from app import presence
    monkeypatch.setattr(presence, "event_absences", lambda emails, a, b: {})
    cur = staff.store().get()
    people = [dict(p) for p in cur["data"]["people"]]
    for p in people:
        if p["id"] == "c1":
            p["alloc"] = {"XC": 5.0, "MODERN_RALLY": 95.0}               # Julien : un peu de coûts XC, mais ressource CARS
    assert staff.store().put({"params": cur["data"]["params"], "people": people}, "t", cur["updated_at"]) is not None
    assert staff.resource_bus(next(p for p in people if p["id"] == "c1")) == ["XC", "MODERN_RALLY"]       # ancienne fiche : déduit de l'imputation
    monkeypatch.setattr(users, "is_super", lambda e: True)
    r = api.put("/api/resources/staff/c1", json={"resource_bus": ["HISTORIC_RACING", "MODERN_RALLY"]})
    assert r.status_code == 200 and r.json()["bus"] == ["MODERN_RALLY", "HISTORIC_RACING"]
    assert api.put("/api/resources/staff/c1", json={"resource_bus": ["NOPE"]}).status_code == 422
    snap = api.get("/api/wall").json()
    julien = next(x for x in snap["people"] if x["name"] == "Julien Durbecq")
    assert julien["bus"] == ["MODERN_RALLY", "HISTORIC_RACING"]
    from app import wall
    assert not wall._person_in(julien, "xc") and wall._person_in(julien, "cars")                     # plus dans l'équipe XC


def _clutch4_data(km=1000, top=5.6, bottom=5.4):
    return {"header": {"km": km, "after": "Rallye test", "mechanism": "M1", "gearbox": "BV9"},
            "discs": {"motor": [[top, bottom]] * 4, "gearbox": [[5.0, 4.6]] * 4},
            "plates": {"pressure": [10.0, 10.1, 10.0, 10.3, 10.0, 10.1], "inter": [8, 8, 8, 8, 8, 8]}, "notes": "RAS"}


def test_clutch_form_calculations_rights_and_locking(api, monkeypatch):
    from app import tforms
    monkeypatch.setattr(tforms, "_forms", None)
    jid = mkjob(api, vehicle={"id": "1", "name": "Porsche 992"}).json()["id"]
    as_(api, MEC)
    types = api.get("/api/timesheets/form-types").json()["types"]
    assert {t["id"] for t in types} == {"clutch4", "clutch6"}
    r = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "clutch4", "data": _clutch4_data()})
    assert r.status_code == 200
    f = r.json()
    assert f["data"]["header"]["mechanic"] == "Nolan Collinet" and f["data"]["header"]["chassis"] == "Porsche 992"
    motor = f["calc"]["discs"]["motor"]
    assert motor["mean"] == 5.5 and motor["wear"] == 0.5 and motor["wear_per_1000km"] == 0.5 and motor["remaining_km"] == 1800 and motor["state"] == "ok"
    gb = f["calc"]["discs"]["gearbox"]
    assert gb["min"] == 4.6 and gb["state"] == "replace" and f["calc"]["state"] == "replace"
    assert f["calc"]["plates"]["pressure"]["taper"] == 0.3 and f["calc"]["taper_max"] == 0.3
    bad = _clutch4_data(); bad["header"]["chassis"] = "Autre voiture"                                          # « Voiture » vient du job, jamais de la saisie
    assert api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "clutch4", "data": bad}).json()["data"]["header"]["chassis"] == "Porsche 992"
    # valeurs hors limites ou type inconnu : refusés
    assert api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "clutch4", "data": {"discs": {"motor": [[99, 1]]}}}).status_code == 422
    assert api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "nimporte", "data": {}}).status_code == 422
    # 6 patins : une mesure par patin, ressort et trois disques
    f6 = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "clutch6", "data": {"header": {"km": 500}, "discs": {"central": [[5.5]] * 6}, "spring_fingers": 12.5}}).json()
    assert f6["calc"]["discs"]["central"]["mean"] == 5.5 and f6["calc"]["discs"]["motor"]["mean"] is None and f6["data"]["spring_fingers"] == 12.5
    fid = f["id"]
    as_(api, CHEF_XC)                                                                                       # chef d'une autre BU : ni modifier ni valider
    assert api.put(f"/api/timesheets/forms/{fid}", json={"data": _clutch4_data()}).status_code == 403
    assert api.post(f"/api/timesheets/forms/{fid}/validate").status_code == 403
    as_(api, MEC)
    assert api.post(f"/api/timesheets/forms/{fid}/validate").status_code == 403                             # le mécanicien ne valide pas
    assert api.put(f"/api/timesheets/forms/{fid}", json={"data": _clutch4_data(km=2000)}).json()["data"]["header"]["km"] == 2000
    as_(api, CHEF)
    assert api.post(f"/api/timesheets/forms/{fid}/validate").json()["validated"] is True
    as_(api, MEC)
    assert api.put(f"/api/timesheets/forms/{fid}", json={"data": _clutch4_data()}).status_code == 403      # verrouillé après validation
    assert api.delete(f"/api/timesheets/forms/{fid}").status_code == 403
    as_(api, CHEF)
    page = api.get(f"/api/timesheets/forms/{fid}/print")
    assert page.status_code == 200 and "Mesure d&#x27;embrayage" in page.text.replace("'", "&#x27;") and "Porsche 992" in page.text and "Barlow Condensed" in page.text
    assert "2000 km" in page.text and "3600 km" in page.text                                               # pas de zéros avalés (2000 ≠ 2)
    assert api.get(f"/api/timesheets/forms/{fid}/print?lang=en").text.count("Mean thickness") == 2
    assert api.post(f"/api/timesheets/forms/{fid}/validate?validated=false").json()["validated"] is False
    assert len(api.get(f"/api/timesheets/jobs/{jid}/forms").json()["forms"]) == 2
    assert api.delete(f"/api/timesheets/forms/{fid}").status_code == 200
    # un job qui n'est pas d'atelier n'accepte pas de formulaire
    bg = mkjob(api, kind="background", title="Rangement", bu="ALL").json()["id"]
    assert api.post(f"/api/timesheets/jobs/{bg}/forms", json={"type": "clutch4", "data": {}}).status_code == 422
