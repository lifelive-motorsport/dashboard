from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient

from app import leaves, mailer, planning, staff, timesheets, users
from app.auth import require_user
from app.main import app

MEC, MEC2, CHEF, CHEF_XC, MD, OFFICE = ("mec@lifelive-motorsport.com", "mec2@lifelive-motorsport.com", "julien@lifelive-motorsport.com", "morgan@lifelive-motorsport.com",
                                       "md@lifelive-motorsport.com", "office@lifelive-motorsport.com")


@pytest.fixture()
def api(monkeypatch):
    for n in ("_jobs", "_entries", "_blobs", "_templates", "_alert_coll"):
        monkeypatch.setattr(timesheets, n, None)
    monkeypatch.setattr(leaves, "_reqs", None)
    monkeypatch.setattr(leaves, "_proofs", None)
    mailer.OUTBOX.clear()
    monkeypatch.setattr(users, "is_super", lambda e: e == MD)
    monkeypatch.setattr(users, "supers", lambda: [MD])
    cur = staff.store().get()
    y = date.today().year
    people = [{"id": "m1", "name": "Nolan Collinet", "kind": "salarie", "workshop": "mechanic", "google_email": MEC, "alloc": {"HISTORIC_RACING": 100}, "leave_alloc": {str(y): {"paid": 10, "comp": 3}}},
              {"id": "m2", "name": "Tom Duckers", "kind": "salarie", "workshop": "mechanic", "google_email": MEC2, "alloc": {"XC": 100}},
              {"id": "c1", "name": "Julien Durbecq", "kind": "salarie", "workshop": "chef_cars", "google_email": CHEF},
              {"id": "c2", "name": "Morgan Duyckaerts", "kind": "salarie", "workshop": "chef_xc", "google_email": CHEF_XC},
              {"id": "o1", "name": "Alain Neuville", "kind": "salarie", "google_email": OFFICE}]
    assert staff.store().put({"params": cur["data"]["params"], "people": people}, "t", cur["updated_at"]) is not None
    who = {"u": MEC}
    app.dependency_overrides[require_user] = lambda: who["u"]
    c = TestClient(app)
    c.who = who
    yield c
    app.dependency_overrides.pop(require_user, None)


def as_(c, e):
    c.who["u"] = e


def nxt(wd, weeks=2):
    d = date.today() + timedelta(days=7 * weeks)
    return d - timedelta(days=d.weekday()) + timedelta(days=wd)


def req(**kw):
    s = nxt(0)
    return {"type": "paid", "start": s.isoformat(), "end": (s + timedelta(days=2)).isoformat(), **kw}


def test_days_halves_and_holidays():
    from app import presence
    assert sum(leaves.day_values(None, date(2026, 10, 12), date(2026, 10, 16), "full", "full").values()) == 5
    assert sum(leaves.day_values(None, date(2026, 10, 12), date(2026, 10, 16), "pm", "am").values()) == 4              # lundi après-midi, vendredi matin
    assert sum(leaves.day_values(None, date(2026, 10, 12), date(2026, 10, 12), "pm", "full").values()) == 0.5          # une demi-journée
    assert sum(leaves.day_values(None, date(2026, 11, 9), date(2026, 11, 13), "full", "full").values()) == 4            # 11 novembre férié


def test_create_balance_approve_flow_with_calendar_and_mails(api):
    as_(api, MEC)
    r = api.post("/api/leaves", json=req()).json()
    assert r["status"] == "pending" and r["days"] == 3 and r["mine"] is True
    assert [m["to"] for m in mailer.OUTBOX] == [CHEF]                                                  # mécanicien CARS : son chef d'atelier CARS (pas Morgan, XC)
    b = {x["type"]: x for x in api.get("/api/leaves/me").json()["balances"]}
    assert b["paid"]["allocated"] == 10 and b["paid"]["pending"] == 3 and b["paid"]["remaining"] == 10
    as_(api, MEC)
    assert api.post(f"/api/leaves/{r['id']}/approve").status_code == 403                                  # on ne s'approuve pas
    as_(api, CHEF_XC)
    assert api.post(f"/api/leaves/{r['id']}/approve").status_code == 403                                  # chef de l'autre BU
    as_(api, CHEF)
    assert api.get("/api/leaves/me").json()["to_decide"][0]["id"] == r["id"]
    a = api.post(f"/api/leaves/{r['id']}/approve").json()
    assert a["status"] == "approved" and a["event_id"]
    ev = next(iter(planning.backend().events[leaves.calendar_id()].values()))
    assert ev["summary"] == "Nolan Collinet — Congés payés" and ev["start"]["date"] == r["start"] and ev["end"]["date"] == (date.fromisoformat(r["end"]) + timedelta(days=1)).isoformat()
    assert mailer.OUTBOX[-1]["to"] == MEC and "approuvée" in mailer.OUTBOX[-1]["body"]
    as_(api, MEC)
    b = {x["type"]: x for x in api.get("/api/leaves/me").json()["balances"]}
    assert b["paid"]["used"] == 3 and b["paid"]["remaining"] == 7
    assert api.delete(f"/api/leaves/{r['id']}").json()["status"] == "cancelled"                          # annulée avant le début : événement retiré, solde rendu
    assert not planning.backend().events[leaves.calendar_id()]
    assert {x["type"]: x for x in api.get("/api/leaves/me").json()["balances"]}["paid"]["remaining"] == 10


def test_who_approves_and_refusal_reason(api):
    as_(api, CHEF)
    r = api.post("/api/leaves", json=req()).json()                                                       # un chef d'atelier : Managing Director
    assert [m["to"] for m in mailer.OUTBOX] == [MD]
    as_(api, CHEF_XC)
    assert api.post(f"/api/leaves/{r['id']}/approve").status_code == 403
    as_(api, OFFICE)
    r2 = api.post("/api/leaves", json=req()).json()                                                      # le reste du personnel : Managing Director
    as_(api, CHEF)
    assert api.post(f"/api/leaves/{r2['id']}/approve").status_code == 403
    as_(api, MD)
    assert api.post(f"/api/leaves/{r2['id']}/refuse", json={"reason": "x"}).status_code == 422
    assert api.post(f"/api/leaves/{r2['id']}/refuse", json={"reason": "Période de rush"}).json()["status"] == "refused"
    assert "Période de rush" in mailer.OUTBOX[-1]["body"]
    assert api.post(f"/api/leaves/{r['id']}/approve").json()["status"] == "approved"
    assert api.post(f"/api/leaves/{r['id']}/approve").status_code == 422                                  # déjà traitée


def test_sick_leave_needs_proof_over_one_day_and_proof_access(api):
    as_(api, MEC)
    assert api.post("/api/leaves", json=req(type="sick")).status_code == 422                              # 3 jours sans certificat
    one = nxt(0)
    assert api.post("/api/leaves", json={"type": "sick", "start": one.isoformat(), "end": one.isoformat()}).status_code == 200      # 1 jour : pas de justificatif
    up = api.post("/api/leaves-proofs?filename=cert.pdf", content=b"%PDF-1.4 x", headers={"Content-Type": "application/pdf"})
    assert up.status_code == 200
    assert api.post("/api/leaves-proofs", content=b"x", headers={"Content-Type": "text/html"}).status_code == 422
    r = api.post("/api/leaves", json=req(type="sick", proofs=[up.json()["id"]]))
    assert r.status_code == 200
    assert api.get(f"/api/leaves-proofs/{up.json()['id']}").content.startswith(b"%PDF")
    as_(api, MEC2)
    assert api.get(f"/api/leaves-proofs/{up.json()['id']}").status_code == 403                            # collègue : non
    as_(api, CHEF)
    assert api.get(f"/api/leaves-proofs/{up.json()['id']}").status_code == 200                            # validateur : oui
    as_(api, CHEF)
    a = api.post(f"/api/leaves/{r.json()['id']}/approve").json()
    ev = list(planning.backend().events[leaves.calendar_id()].values())[-1]
    assert ev["summary"] == "Nolan Collinet — Absence"                                                     # maladie : jamais le motif dans l'agenda


def test_leave_feeds_planning_presence_and_edit_rules(api):
    as_(api, MEC)
    r = api.post("/api/leaves", json=req()).json()
    assert api.put(f"/api/leaves/{r['id']}", json=req(comment="modifié")).json()["comment"] == "modifié"
    as_(api, CHEF)
    api.post(f"/api/leaves/{r['id']}/approve")
    as_(api, MEC)
    assert api.put(f"/api/leaves/{r['id']}", json=req()).status_code == 403                               # approuvée : plus modifiable
    pl = planning.planning_view(date.fromisoformat(r["start"]), date.fromisoformat(r["end"]))
    assert pl["leaves"] and pl["leaves"][0]["rid"] == "s:m1" and "type" not in pl["leaves"][0]
    from app import presence
    d = date.fromisoformat(r["start"])
    assert leaves.absences({MEC}, d, d)[MEC][d] == "Congé"
    assert presence.excused({MEC}, d, d).get(MEC, {}).get(d) == "Congé"
