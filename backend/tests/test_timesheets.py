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
    assert {t["id"] for t in types} == {"clutch4", "clutch6", "gearbox_m3", "gearbox_z4", "gearbox_diff", "rear_axle", "setup_request", "setup_request_circuit", "setup_reading", "setdown_reading"}
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
    assert len(api.get(f"/api/timesheets/jobs/{jid}/forms").json()["forms"]) == 3
    assert api.delete(f"/api/timesheets/forms/{fid}").status_code == 200
    # un job qui n'est pas d'atelier n'accepte pas de formulaire
    bg = mkjob(api, kind="background", title="Rangement", bu="ALL").json()["id"]
    assert api.post(f"/api/timesheets/jobs/{bg}/forms", json={"type": "clutch4", "data": {}}).status_code == 422


def test_clutch_form_links_to_garage_part_and_logs_inspection(api, monkeypatch):
    from app import rides, tforms
    for n in ("_cars", "_parts", "_runs", "_circuits", "_catalog", "_maint", "_templates", "_sessions"):
        monkeypatch.setattr(rides, n, None)
    monkeypatch.setattr(tforms, "_forms", None)
    car = rides.race_cars()[0]
    rides.cars_coll().put(car["key"], {"id": car["key"], "odoo_id": 77})
    ens = rides.add_part(car["key"], rides.PartIn(name="Embrayage", group=True), "t")
    part = rides.add_part(car["key"], rides.PartIn(name="Embrayage 4 patins", parent_id=ens["id"], types=["inspection"], maint={"inspection": {"limit_events": 1}}, km_start=250), "t")
    other = rides.add_part(car["key"], rides.PartIn(name="Disque de frein", parent_id=rides.add_part(car["key"], rides.PartIn(name="Freins", group=True), "t")["id"]), "t")
    jid = mkjob(api, vehicle={"id": "77", "name": "Voiture test"}).json()["id"]
    lst = api.get(f"/api/timesheets/jobs/{jid}/forms").json()
    assert lst["car_key"] == car["key"] and [p["id"] for p in lst["parts"]] == [part["id"]]                  # seul l'embrayage est proposé, pas les freins
    f = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "clutch4", "data": _clutch4_data(km=None)}).json()
    assert f["part_id"] == part["id"] and f["data"]["header"]["km"] == 250                                    # un seul embrayage : lié d'office, km repris du Garage
    assert api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "clutch4", "data": {}, "part_id": other["id"]}).status_code == 422
    # validation : un contrôle est enregistré sur la pièce, la réouverture le retire
    assert api.post(f"/api/timesheets/forms/{f['id']}/validate").json()["garage"]["logged"] is True
    logs = [l for l in rides.maint_coll().all() if l["part_id"] == part["id"]]
    assert len(logs) == 1 and logs[0]["type"] == "inspection" and "Mesure d'embrayage" in logs[0]["notes"]
    assert api.post(f"/api/timesheets/forms/{f['id']}/validate?validated=false").json()["garage"] == {}
    assert [l for l in rides.maint_coll().all() if l["part_id"] == part["id"]] == []
    # pièce qui ne suit pas le contrôle : rien d'enregistré, jamais de remplacement automatique
    p = rides.parts_coll().get(part["id"]); p["types"] = []; rides.parts_coll().put(p["id"], p)
    g = api.post(f"/api/timesheets/forms/{f['id']}/validate").json()["garage"]
    assert g["logged"] is False and g["reason"] == "not_tracked"
    assert rides.parts_coll().get(part["id"]).get("removed_at") is None
    # sans embrayage encodé : le formulaire fonctionne sans lien
    jid2 = mkjob(api, title="Révision autre voiture", vehicle={"id": "999", "name": "Inconnue"}).json()["id"]
    f2 = api.post(f"/api/timesheets/jobs/{jid2}/forms", json={"type": "clutch4", "data": _clutch4_data()}).json()
    assert f2["part_id"] == "" and api.post(f"/api/timesheets/forms/{f2['id']}/validate").json()["garage"]["reason"] == "no_part"


def test_clutch_wear_curve_data_in_garage_sheet(api, monkeypatch):
    from app import rides, tforms
    for n in ("_cars", "_parts", "_runs", "_circuits", "_catalog", "_maint", "_templates", "_sessions"):
        monkeypatch.setattr(rides, n, None)
    monkeypatch.setattr(tforms, "_forms", None)
    car = rides.race_cars()[0]
    rides.cars_coll().put(car["key"], {"id": car["key"], "odoo_id": 77})
    ens = rides.add_part(car["key"], rides.PartIn(name="Embrayage", group=True), "t")
    part = rides.add_part(car["key"], rides.PartIn(name="Embrayage", parent_id=ens["id"], types=["inspection"], maint={"inspection": {"limit_events": 1}}), "t")
    jid = mkjob(api, vehicle={"id": "77", "name": "X"}).json()["id"]
    ids = []
    for km, th in ((300, 5.8), (800, 5.2)):
        f = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "clutch4", "data": _clutch4_data(km=km, top=th, bottom=th)}).json()
        ids.append(f["id"])
    api.post(f"/api/timesheets/forms/{ids[0]}/validate"); api.post(f"/api/timesheets/forms/{ids[1]}/validate")
    third = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "clutch4", "data": _clutch4_data(km=900, top=4.0, bottom=4.0)}).json()      # non validée : hors courbe
    d = rides.car_detail(car["key"])
    pts = d["clutch_measures"][part["id"]]
    assert [p["km"] for p in pts] == [300, 800] and pts[1]["discs"]["motor"]["mean"] == 5.2 and d["ep0"] == 6.0 and d["mini"] == 4.6


def test_gearbox_and_rear_axle_checklist_forms(api, monkeypatch):
    from app import tcheck, tforms
    monkeypatch.setattr(tforms, "_forms", None)
    jid = mkjob(api, vehicle={"id": "1", "name": "BMW M3 E30"}).json()["id"]
    spec = tcheck.TYPES["gearbox_diff"]
    ids = [i["id"] for s in spec["sections"] for i in s["items"]]
    assert len(ids) == len(set(ids))                                                                          # identifiants d'éléments uniques dans un type
    as_(api, MEC)
    items = {ids[0]: {"status": "ok"}, ids[1]: {"status": "nok", "comment": "Dent écaillée"}}
    f = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "gearbox_diff", "data": {"header": {"gearbox_no": "545 022", "km": 1500}, "requests": {"preload": "40 Nm"}, "items": items, "notes": "à revoir"}}).json()
    assert f["part_id"] == "" and f["data"]["header"]["gearbox_no"] == "545 022" and f["data"]["requests"]["preload"] == "40 Nm"
    c = f["calc"]
    assert c["ok"] == 1 and c["nok"] == 1 and c["open"] == c["total"] - 2 and c["state"] == "nok"
    # statut invalide refusé ; élément inconnu ignoré
    assert api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "rear_axle", "data": {"items": {"x": {"status": "ok"}, "couple_conique": {"status": "peut-être"}}}}).status_code == 422
    done = {i["id"]: {"status": "ok"} for s in tcheck.TYPES["rear_axle"]["sections"] for i in s["items"]}
    f2 = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "rear_axle", "data": {"items": done}}).json()
    assert f2["calc"]["state"] == "ok" and f2["calc"]["open"] == 0 and "x" not in f2["data"]["items"]
    # validation sans effet sur le Garage ; feuille imprimable
    as_(api, CHEF)
    v = api.post(f"/api/timesheets/forms/{f['id']}/validate").json()
    assert v["validated"] is True and v["garage"] == {}
    page = api.get(f"/api/timesheets/forms/{f['id']}/print").text
    assert "Dent écaillée" in page and "545 022" in page and "BMW M3 E30" in page and "1 NOK" in page
    assert "All OK" in api.get(f"/api/timesheets/forms/{f2['id']}/print?lang=en").text


def test_setup_request_and_weighing_readings(api, monkeypatch):
    from app import tforms
    monkeypatch.setattr(tforms, "_forms", None)
    jid = mkjob(api, vehicle={"id": "1", "name": "Porsche 992 Rally"}).json()["id"]
    as_(api, MEC)
    req = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "setup_request", "data": {"inputs": {"pilot_name": "A. Pilote", "pilot_kg": "85,5", "copilot_name": "B. Copilote", "copilot_kg": 80},
                                                                                         "rows": {"amortisseur": {"av": "Ohlins 12", "ar": "Ohlins 14"}}, "notes": "Gravel"}}).json()
    assert req["data"]["inputs"]["pilot_kg"] == 85.5 and req["data"]["rows"]["amortisseur"]["av"] == "Ohlins 12" and req["calc"]["filled"] == 2 and req["calc"]["weights"] is None
    # relevé : poids de l'équipage repris de la demande, calculs de pesée
    wr = {"av_g": "380", "av_d": "372", "ar_g": "395", "ar_d": "403"}
    f = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "setup_reading", "data": {"inputs": {"fuel_l": 20, "min_weight": 1400}, "rows": {"wheel_weights": wr}}}).json()
    assert f["data"]["inputs"]["pilot_kg"] == 85.5 and f["data"]["inputs"]["copilot_kg"] == 80
    w = f["calc"]["weights"]
    assert w["total"] == 1550 and w["front_pct"] == 48.52 and w["cross_pct"] == 50.52                         # (380+372)/1550 ; (380+403)/1550
    assert w["no_fuel"] == 1535 and w["no_crew"] == 1384.5 and w["empty"] == 1369.5 and w["min_ok"] is True and f["calc"]["state"] == "ok"
    low = api.put(f"/api/timesheets/forms/{f['id']}", json={"data": {"inputs": {"fuel_l": 20, "min_weight": 1600}, "rows": {"wheel_weights": wr}}}).json()
    assert low["calc"]["weights"]["min_ok"] is False and low["calc"]["state"] == "nok"
    # pesée incomplète : pas de calcul ; texte libre accepté, valeur d'entrée hors limites refusée
    inc = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "setdown_reading", "data": {"rows": {"wheel_weights": {"av_g": "380"}, "carrossage": {"av_g": "-3,2"}}}}).json()
    assert inc["calc"]["weights"] is None and inc["data"]["rows"]["carrossage"]["av_g"] == "-3,2"
    assert api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "setup_reading", "data": {"inputs": {"fuel_l": 99999}}}).status_code == 422
    as_(api, CHEF)
    page = api.get(f"/api/timesheets/forms/{f['id']}/print").text
    assert "Porsche 992 Rally" in page and "Centrage en croix" in page and "Poids sous le minimum" in page
    assert "Ohlins 14" in api.get(f"/api/timesheets/forms/{req['id']}/print?lang=en").text


def test_garage_proposals_from_checked_lines_and_forms(api, monkeypatch):
    from app import rides, tforms, tgarage
    for n in ("_cars", "_parts", "_runs", "_circuits", "_catalog", "_maint", "_templates", "_sessions"):
        monkeypatch.setattr(rides, n, None)
    monkeypatch.setattr(tforms, "_forms", None)
    monkeypatch.setattr(tgarage, "_coll", None)
    car = rides.race_cars()[0]
    rides.cars_coll().put(car["key"], {"id": car["key"], "odoo_id": 77})
    ens = rides.add_part(car["key"], rides.PartIn(name="Transmission", group=True), "t")
    box = rides.add_part(car["key"], rides.PartIn(name="Boîte", parent_id=ens["id"], fn="gearbox", types=["fluids", "revision"], maint={"fluids": {"limit_km": 1000}, "revision": {"limit_km": 3000}}), "t")
    other = rides.add_part(car["key"], rides.PartIn(name="Pont arrière", parent_id=ens["id"], types=["fluids"], maint={"fluids": {"limit_km": 1000}}), "t")            # sans fonction
    jid = mkjob(api, vehicle={"id": "77", "name": "X"}).json()["id"]
    job = timesheets.jobs().get(jid)
    job["checklist"] = {"template_id": "", "template_name": "T", "sections": [{"id": "s", "title": "Transmission", "lines": [
        {"id": "l1", "text": "Vidange BV, nettoyage des filtres", "note": "", "done": True, "done_at": "2026-06-02T10:00:00+00:00"},
        {"id": "l2", "text": "Vidange du pont, nettoyage des filtres", "note": "", "done": True, "done_at": "2026-06-02T11:00:00+00:00"},
        {"id": "l3", "text": "Contrôle des serrages", "note": "", "done": True, "done_at": "2026-06-02T11:30:00+00:00"},
        {"id": "l4", "text": "Vidange moteur", "note": "", "done": False}]}]}
    timesheets.jobs().put(jid, job)
    # texte libre d'un pointage : rien n'est proposé ; ni pour un mécanicien
    as_(api, MEC)
    assert api.get(f"/api/timesheets/jobs/{jid}/garage").status_code == 403
    as_(api, CHEF)
    d = api.get(f"/api/timesheets/jobs/{jid}/garage").json()
    keys = {p["label"]: p for p in d["proposals"]}
    assert set(keys) == {"Vidange BV, nettoyage des filtres", "Vidange du pont, nettoyage des filtres"}            # ligne non cochée ou sans lien : aucune proposition
    bv, pont = keys["Vidange BV, nettoyage des filtres"], keys["Vidange du pont, nettoyage des filtres"]
    assert bv["part_id"] == box["id"] and bv["type"] == "fluids" and bv["date"] == "2026-06-02" and bv["tracked"] is True and pont["part_id"] == ""
    # le pont n'a pas de fonction : le confirmateur choisit la pièce, le choix est mémorisé
    r = api.post(f"/api/timesheets/jobs/{jid}/garage/apply", json={"items": [{"key": bv["key"]}, {"key": pont["key"]}]}).json()
    res = {x["key"]: x for x in r["results"]}
    assert res[bv["key"]]["ok"] is True and res[pont["key"]]["ok"] is False
    r = api.post(f"/api/timesheets/jobs/{jid}/garage/apply", json={"items": [{"key": pont["key"], "part_id": other["id"]}]}).json()
    assert r["results"][0]["ok"] is True
    logs = {l["part_id"]: l for l in rides.maint_coll().all()}
    assert logs[box["id"]]["type"] == "fluids" and logs[box["id"]]["date"] == "2026-06-02" and logs[other["id"]]["type"] == "fluids"
    assert (rides.cars_coll().get(car["key"]) or {}).get("fn_map", {}).get("rear_axle") == other["id"]
    again = api.post(f"/api/timesheets/jobs/{jid}/garage/apply", json={"items": [{"key": bv["key"]}]}).json()
    assert again["results"][0].get("already") is True and len(rides.maint_coll().all()) == 2                              # une ligne = une seule maintenance
    # annulation : la maintenance disparaît de la pièce
    api.post(f"/api/timesheets/jobs/{jid}/garage/restore", json={"key": bv["key"]})
    assert len(rides.maint_coll().all()) == 1 and [p for p in api.get(f"/api/timesheets/jobs/{jid}/garage").json()["proposals"] if p["key"] == bv["key"]][0]["status"] == "pending"
    # pièce qui ne suit pas ce type : erreur claire, rien d'écrit ; ignorer une proposition
    gb = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "gearbox_m3", "data": {"header": {"date": "2026-06-03"}}}).json()
    api.post(f"/api/timesheets/forms/{gb['id']}/validate")
    prop = [p for p in api.get(f"/api/timesheets/jobs/{jid}/garage").json()["proposals"] if p["source"] == "form"][0]
    assert prop["type"] == "revision" and prop["part_id"] == box["id"]
    assert api.post(f"/api/timesheets/jobs/{jid}/garage/ignore", json={"key": prop["key"]}).status_code == 200
    assert [p for p in api.get(f"/api/timesheets/jobs/{jid}/garage").json()["proposals"] if p["key"] == prop["key"]][0]["status"] == "ignored"


def test_coordinator_role_confirms_garage_but_does_not_validate(api):
    cur = staff.store().get()
    people = cur["data"]["people"] + [{"id": "k1", "name": "Ingrid Coord", "kind": "salarie", "function": "Engineer", "workshop": "coordinator", "google_email": "ingrid@lifelive-motorsport.com"}]
    assert staff.store().put({"params": cur["data"]["params"], "people": people}, "t", cur["updated_at"]) is not None
    jid = mkjob(api, vehicle={"id": "77", "name": "X"}).json()["id"]
    as_(api, "ingrid@lifelive-motorsport.com")
    assert api.get("/api/timesheets/me").json()["role"] == "coordinator"
    assert api.get(f"/api/timesheets/jobs/{jid}/garage").status_code == 200
    assert api.get("/api/timesheets/jobs?all=true").status_code == 200
    assert api.post("/api/timesheets/jobs", json={"kind": "background", "title": "Z", "bu": "ALL"}).status_code == 403            # ne gère pas les jobs


def test_form_models_are_editable_duplicable_and_protected(api, monkeypatch):
    from app import tforms, tmodels
    monkeypatch.setattr(tforms, "_forms", None)
    jid = mkjob(api, vehicle={"id": "1", "name": "BMW M3 E30"}).json()["id"]
    as_(api, MEC)
    assert api.get("/api/timesheets/form-models").status_code == 403                                       # le mécanicien ne voit pas les modèles
    as_(api, CHEF)
    models = api.get("/api/timesheets/form-models").json()["models"]
    assert {m["id"] for m in models} >= {"clutch4", "gearbox_m3", "rear_axle", "setup_reading"} and next(m for m in models if m["id"] == "clutch4")["readonly"] is True
    gm = next(m for m in models if m["id"] == "gearbox_m3")
    spec = gm["spec"]
    first = spec["sections"][0]["items"][0]
    payload = {"label": "Révision de boîte — M3 (maison)", "garage": {"fn": "gearbox", "mt": "revision2"}, "requests": spec["requests"], "sections": [
        {"id": spec["sections"][0]["id"], "title": spec["sections"][0]["title"], "items": [{"id": first["id"], "label": "Pignon de 1ère (renommé)"}, {"id": "", "label": "Nouvel élément"}]}]}
    saved = api.put("/api/timesheets/form-models/gearbox_m3", json=payload).json()
    items = saved["spec"]["sections"][0]["items"]
    assert items[0]["id"] == first["id"] and items[0]["label"] == "Pignon de 1ère (renommé)" and items[1]["id"] not in (first["id"], "") and len(saved["spec"]["sections"]) == 1
    # un formulaire créé avec ce modèle reflète la nouvelle liste ; le lien Garage vient du modèle
    f = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": "gearbox_m3", "data": {"items": {first["id"]: {"status": "nok"}}}}).json()
    assert f["calc"]["total"] == 2 and f["calc"]["nok"] == 1 and f["label"] == "Révision de boîte — M3 (maison)"
    assert any(t["id"] == "gearbox_m3" and t["garage"]["mt"] == "revision2" for t in api.get("/api/timesheets/form-types").json()["types"])
    # duplication : nouveau formulaire utilisable ; un modèle utilisé ou d'origine ne se supprime pas
    dup = api.post("/api/timesheets/form-models", json={"from_id": "rear_axle", "label": "Pont avant (copie)"}).json()
    assert dup["builtin"] is False and api.post("/api/timesheets/form-models", json={"from_id": "rear_axle", "label": "pont avant (copie)"}).status_code == 422
    f2 = api.post(f"/api/timesheets/jobs/{jid}/forms", json={"type": dup["id"], "data": {}}).json()
    assert f2["label"] == "Pont avant (copie)"
    assert api.delete(f"/api/timesheets/form-models/{dup['id']}").status_code == 422                       # utilisé par un formulaire rempli
    assert api.delete("/api/timesheets/form-models/gearbox_m3").status_code == 422                         # modèle d'origine
    api.delete(f"/api/timesheets/forms/{f2['id']}")
    assert api.delete(f"/api/timesheets/form-models/{dup['id']}").status_code == 200
    # la ligne de pesée d'un relevé ne peut pas disparaître ; liste vide refusée
    sr = next(m for m in api.get("/api/timesheets/form-models").json()["models"] if m["id"] == "setup_reading")["spec"]
    bad = {"label": sr["label"], "groups": [g for g in sr["groups"] if g["id"] != "pesee"]}
    assert api.put("/api/timesheets/form-models/setup_reading", json=bad).status_code == 422
    assert api.put("/api/timesheets/form-models/gearbox_m3", json={"label": "X", "sections": []}).status_code == 422


def test_history_records_restores_and_is_super_only(api, monkeypatch):
    from app import history, rides, users
    monkeypatch.setattr(history, "_coll", None)
    monkeypatch.setattr(history, "_last_purge", 0.0)
    monkeypatch.setattr(timesheets, "_templates", None)
    as_(api, CHEF)
    body = {"name": "Modèle test", "bu": "CARS", "natures": ["pre_event"], "sections": [{"title": "Moteur", "lines": [{"text": "Vidange moteur", "note": ""}]}]}
    tid = api.post("/api/timesheets/templates", json=body).json()["id"]
    api.put(f"/api/timesheets/templates/{tid}", json={**body, "name": "Modèle test (modifié par erreur)", "sections": [{"title": "Moteur", "lines": [{"text": "Autre chose", "note": ""}]}]})
    monkeypatch.setattr(users, "is_super", lambda e: e == CHEF)
    entries = api.get("/api/admin/history?days=7").json()["entries"]
    mine = [e for e in entries if e["doc_id"] == tid]
    assert [e["action"] for e in mine] == ["update", "create"] and mine[0]["kind"] == "Modèle de job" and "name" in mine[0]["fields"] and "sections" in mine[0]["fields"]
    d = api.get(f"/api/admin/history/{mine[0]['id']}").json()
    assert d["before"]["name"] == "Modèle test" and d["after"]["name"].endswith("par erreur)") and d["stale"] is False
    # restauration : l'état d'avant revient, et la restauration est elle-même au journal
    assert api.post(f"/api/admin/history/{mine[0]['id']}/restore").json()["restored"] == "updated"
    assert timesheets.templates().get(tid)["name"] == "Modèle test" and timesheets.templates().get(tid)["sections"][0]["lines"][0]["text"] == "Vidange moteur"
    assert api.get("/api/admin/history?days=7").json()["entries"][0]["restored_from"] == mine[0]["id"]
    # suppression par erreur : restauration = recréation
    api.delete(f"/api/timesheets/templates/{tid}")
    gone = [e for e in api.get("/api/admin/history?days=7").json()["entries"] if e["doc_id"] == tid and e["action"] == "delete"][0]
    assert timesheets.templates().get(tid) is None and api.post(f"/api/admin/history/{gone['id']}/restore").json()["restored"] == "recreated" and timesheets.templates().get(tid)["name"] == "Modèle test"
    # réservé au Super User ; les écritures sans changement ne sont pas relevées
    as_(api, MEC)
    assert api.get("/api/admin/history").status_code == 403
    n = len(history.coll().all())
    timesheets.templates().put(tid, timesheets.templates().get(tid))
    assert len(history.coll().all()) == n
