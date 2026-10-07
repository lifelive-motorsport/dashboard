from datetime import date

from fastapi.testclient import TestClient

from app import dkv, gcal
from app.main import app
from app.providers.odoo import OdooProvider


def test_calendar_events_keep_vehicle_resources_and_all_day_end_is_exclusive():
    items = [{"id": "1", "summary": "Rallye du Portugal", "start": {"date": "2026-05-10"}, "end": {"date": "2026-05-13"},
              "attendees": [{"displayName": "Sprinter", "resource": True, "responseStatus": "accepted"}, {"email": "jean@x.be"}, {"displayName": "Salle A", "resource": True, "responseStatus": "declined"}]},
             {"id": "2", "summary": "Réunion", "start": {"dateTime": "2026-05-12T09:00:00+02:00"}, "end": {"dateTime": "2026-05-12T10:00:00+02:00"}, "attendees": [{"email": "a@x.be"}]},
             {"id": "3", "status": "cancelled", "start": {"date": "2026-05-01"}, "end": {"date": "2026-05-02"}, "attendees": [{"displayName": "Citan", "resource": True}]},
             {"id": "4", "summary": "Spa", "start": {"dateTime": "2026-06-20T08:00:00+02:00"}, "end": {"dateTime": "2026-06-22T00:00:00+02:00"}, "attendees": [{"displayName": "Citan", "resource": True}]}]
    evs = gcal.normalize(items, "cal")
    assert [(e["title"], e["start"], e["end"], e["resources"]) for e in evs] == [("Rallye du Portugal", "2026-05-10", "2026-05-12", ["Sprinter"]), ("Spa", "2026-06-20", "2026-06-21", ["Citan"])]


def test_usage_counts_booked_days_and_buffered_away_days_without_double_counting():
    evs = [{"title": "A", "start": "2026-05-10", "end": "2026-05-12", "resources": ["Sprinter"]}, {"title": "B", "start": "2026-05-14", "end": "2026-05-14", "resources": ["Sprinter", "Citan"]}]
    u = {x["vehicle"]: x for x in gcal.usage(evs, 2)}
    assert u["Sprinter"]["events"] == 2 and u["Sprinter"]["booked_days"] == 4                      # 10-12 puis 14
    assert u["Sprinter"]["away_days"] == 9                                                         # du 8 au 16 mai : les marges se recouvrent
    assert u["Citan"]["booked_days"] == 1 and u["Citan"]["away_days"] == 5


def test_dkv_text_extraction_and_candidate_lines():
    t = dkv.extract_text("Rechnung\n12.05.2026 1-ABC-123 Diesel 45,20 L 82,35 EUR\nSumme 82,35\n".encode())
    assert dkv.candidate_lines(t) == ["12.05.2026 1-ABC-123 Diesel 45,20 L 82,35 EUR"]
    assert dkv.extract_text(b"%PDF-1.4 pas un vrai pdf", "application/pdf") == ""                   # illisible : chaîne vide, pas d'erreur


def test_odoo_fuel_invoices_with_attachments_and_615_lines_and_attachment_guard():
    p = OdooProvider.__new__(OdooProvider)

    def call(model, method, **kw):
        if model == "res.partner":
            return [{"id": 5}]
        if model == "account.move":
            return [{"id": 1, "name": "F1", "ref": "r", "invoice_date": "2026-01-31", "date": "2026-01-31", "amount_untaxed": 1000.0, "amount_total": 1210.0, "payment_state": "paid", "move_type": "in_invoice"}]
        if model == "ir.attachment" and method == "search_read":
            return [{"id": 77, "name": "dkv.pdf", "mimetype": "application/pdf", "file_size": 1234, "res_id": 1}]
        if model == "ir.attachment":
            import base64
            return [{"name": "dkv.pdf", "mimetype": "application/pdf", "datas": base64.b64encode(b"%PDF-x").decode()}]
        return [{"move_id": [1, "F1"], "balance": 600.0, "account_id": [3, "615021 Carburant Util. CITAN"]}, {"move_id": [1, "F1"], "balance": 400.0, "account_id": [4, "615031 Carburant Util. SPRINTER"]}]
    p._call = call
    inv = p.fuel_invoices(2026)
    assert inv[0]["attachments"][0]["id"] == 77 and [(l["code"], l["amount"]) for l in inv[0]["lines"]] == [("615021", 600.0), ("615031", 400.0)]
    assert p.fuel_attachment(77, 2026)[0] == b"%PDF-x" and p.fuel_attachment(78, 2026) is None             # une pièce jointe étrangère aux factures carburant est refusée


def test_fuel_api_in_demo_and_attachment_is_admin_only(monkeypatch):
    import app.adjustments as adj
    import app.main as m
    monkeypatch.setattr(adj.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(adj.settings, "ADMIN_EMAILS", ["md@x.be"])
    try:
        app.dependency_overrides[m.require_user] = lambda: "actionnaire@x.be"
        c = TestClient(app)
        j = c.get("/api/fuel?year=2026").json()
        assert j["invoices"] and j["calendar"]["configured"] and j["calendar"]["usage"]
        assert c.get("/api/fuel/attachment?att=901&year=2026").status_code == 403
        app.dependency_overrides[m.require_user] = lambda: "md@x.be"
        r = c.get("/api/fuel/attachment?att=901&year=2026").json()
        assert r["candidate_lines"] and "Diesel" in r["text"]
    finally:
        app.dependency_overrides.clear()


def test_calendars_label_gives_the_bu_and_usage_splits_days_per_bu(monkeypatch):
    monkeypatch.setattr(gcal.settings, "CALENDAR_IDS", ["Historic Racing=c_a@group.calendar.google.com", "Logistics=c_b@group.calendar.google.com", "XC=c_c@group.calendar.google.com", "c_d@x.be"])
    assert [(c, b) for c, _l, b in gcal.calendars()] == [("c_a@group.calendar.google.com", "HISTORIC_RACING"), ("c_b@group.calendar.google.com", "LOGISTICS"), ("c_c@group.calendar.google.com", "XC"), ("c_d@x.be", "OTHER")]
    evs = [{"title": "Spa", "start": "2026-06-10", "end": "2026-06-11", "resources": ["Sprinter"], "bu": "HISTORIC_RACING"},
           {"title": "Enlèvement", "start": "2026-06-11", "end": "2026-06-11", "resources": ["Sprinter"], "bu": "LOGISTICS"}]
    u = gcal.usage(evs, 0)[0]
    assert u["booked_days"] == 2 and u["booked_by_bu"] == {"HISTORIC_RACING": 1.5, "LOGISTICS": 0.5}          # le 11 juin est partagé à parts égales
    assert round(sum(u["away_by_bu"].values()), 2) == u["away_days"]
