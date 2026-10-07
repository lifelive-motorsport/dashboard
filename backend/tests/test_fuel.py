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
        return [{"move_id": [1, "F1"], "balance": 600.0, "account_id": [3, "615021 Carburant Util. CITAN"]}, {"move_id": [1, "F1"], "balance": 400.0, "account_id": [4, "615031 Carburant Util. SPRINTER"]},
                {"move_id": [1, "F1"], "balance": 250.0, "account_id": [5, "602040 FRAIS Historic Racing"]}]
    p._call = call
    inv = p.fuel_invoices(2026)
    assert inv[0]["attachments"][0]["id"] == 77 and [(l["code"], l["amount"]) for l in inv[0]["lines"]] == [("615021", 600.0), ("615031", 400.0)] and [(l["code"], l["amount"]) for l in inv[0]["other"]] == [("602040", 250.0)]
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
        assert r["candidate_lines"] and "GAZOLE" in r["text"]
        a = c.get("/api/fuel/parse?att=901&year=2026").json()
        assert [v["vehicle"] for v in a["summary"]["vehicles"]] == ["2CEP774", "2BNC759"] or a["summary"]["fuel_ht"] == 274.43
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


def test_race_car_resources_are_excluded_but_service_vehicles_stay():
    items = [{"id": "1", "summary": "Spa Six Hours", "start": {"date": "2026-09-24"}, "end": {"date": "2026-09-28"},
              "attendees": [{"displayName": "(Circuit)-LLM-CA-STG-Jaguar E-Type (TdL) (1)", "resource": True}, {"displayName": "(Rally)-LLM-CA-STG-Toyota Starlet blue (YN22) (1)", "resource": True},
                            {"displayName": "(SV)-LLM-PKG-Small Van (Citan) (1)", "resource": True}]},
             {"id": "2", "summary": "Test", "start": {"date": "2026-09-10"}, "end": {"date": "2026-09-11"}, "attendees": [{"displayName": "(Circuit)-LLM-CA-STG-Chevrolet Monza (GDM) (1)", "resource": True}]}]
    evs = gcal.normalize(items, "c", "HISTORIC_RACING", "Historic Racing")
    assert [(e["title"], e["resources"]) for e in evs] == [("Spa Six Hours", ["(SV)-LLM-PKG-Small Van (Citan) (1)"])]          # l'événement sans véhicule de service disparaît


SAMPLE = """VEHICLE: 2 DPG189 CARD NO.: 704310.0113082778
14.07.2026    SHELL           ST. VITH                 1098661                    6534520024 08:00               165000 GAZOLE                               0009 LTR                  28,460     2,0430     1,6883      48,05    -0,57    0,58    48,06    0,00   48,06
VEHICLE: 2-AHQ-408 CARD NO.: 704310.0113442372
12.07.2026   SHELL            ST. VITH                 1098661                    6532520022 08:45                    1 GAZOLE                               0009     LTR             55,140     2,1020     1,7372      95,79    -1,10    1,15    95,84    0,00   95,84
13.07.2026   SHELL            ST. VITH                 1098661                    6533540050 09:02                    1 ADBLUE (vrac)                        0016     LTR             12,040     1,0790     0,8920      10,74             0,32    11,06    0,00   11,06
08.07.2026   TOTALENERGIES    FRANCORCHA               1064606                            62 17:14                      GAZOLE PREMIUM                       0012     LTR             61,450     2,3010     1,9000     116,76    -1,00    1,00   116,76    0,00  116,76
Monnaie: EUR
VEHICLE: 2BQS330 CARD NO.: 98740200.0100635554
01.09.2026 DKV BOX EUROPE BE 1000099 2026-SFC-3001784809 Péage BE - DKV BOX E 0901 PC 1 2,31 2,31 2,31
30.06.2026 DKV EURO S 0000001 323879678 Cotisation carte 0CGF EUR PC 1 2,5000 2,50 2,50
12.08.2026 08:07 12.08.2026 18:43 500000149816819 Steinebrück, Bundesgrenze | A60 | Wittlich, Kreuz | 42A0101 677,3 109,72 205,26
"""


def test_dkv_parser_reads_fuel_adblue_tolls_and_ignores_toll_detail_rows():
    p = dkv.parse_transactions(SAMPLE)
    tx = p["transactions"]
    assert [(t["vehicle"], t["category"], t["quantity"], t["total_ht"]) for t in tx] == [
        ("2DPG189", "carburant", 28.46, 48.06), ("2AHQ408", "carburant", 55.14, 95.84), ("2AHQ408", "adblue", 12.04, 11.06), ("2AHQ408", "carburant", 61.45, 116.76),
        ("2BQS330", "peage", 1.0, 2.31), ("2BQS330", "frais_dkv", 1.0, 2.5)]
    assert p["ignored"] == 1                                                                        # le détail du péage allemand n'est pas repris (le montant est sur la ligne DKV BOX)
    assert tx[0]["km"] == 165000 and tx[1]["km"] == 1 and tx[3]["km"] is None and tx[0]["station"] == "SHELL ST. VITH"


def test_dkv_summary_totals_per_vehicle_and_keeps_only_credible_odometer_readings():
    s = dkv.summarize(dkv.parse_transactions(SAMPLE))
    by = {v["vehicle"]: v for v in s["vehicles"]}
    assert by["2AHQ408"]["fuel_ht"] == 212.6 and by["2AHQ408"]["fuel_litres"] == 116.59 and by["2AHQ408"]["adblue_ht"] == 11.06
    assert by["2DPG189"]["km"] == [{"date": "2026-07-14", "km": 165000}] and by["2AHQ408"]["km"] == []          # « 1 » n'est pas un relevé
    assert s["toll_ht"] == 2.31 and s["other_ht"] == 2.5 and s["fuel_ht"] == 260.66


def test_dkv_lines_in_another_currency_are_kept_apart():
    txt = "Monnaie: CZK\nVEHICLE: 2BNC759 CARD NO.: 1\n15.08.2026 DKV EURO S 0000001 324 Útdíj 0949 DB 1 751,00 591,00 591,00\n"
    s = dkv.summarize(dkv.parse_transactions(txt))
    assert s["foreign"] == {"CZK": 591.0} and s["vehicles"] == []


def test_plates_mapping_is_admin_only_normalised_and_keeps_the_rest_of_the_configuration(monkeypatch):
    import app.adjustments as adj
    import app.main as m
    from app import expenses
    monkeypatch.setattr(expenses, "_store", expenses.Store())
    monkeypatch.setattr(adj.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(adj.settings, "ADMIN_EMAILS", ["md@x.be"])
    try:
        app.dependency_overrides[m.require_user] = lambda: "md@x.be"
        c = TestClient(app)
        assert c.put("/api/expenses/config", json={"data": {"selected": {"615021": "vehicle"}}, "base": None}).status_code == 200
        r = c.put("/api/expenses/plates", json={"plates": {"2-bnc 759": "Citan", "2CEP774": "  Sprinter 1 ", "XX1": "  "}})
        assert r.status_code == 200 and r.json()["plates"] == {"2BNC759": "Citan", "2CEP774": "Sprinter 1"}
        assert c.get("/api/fuel?year=2026").json()["plates"]["2BNC759"] == "Citan"
        assert c.get("/api/expenses/accounts?year=2026").json()["accounts"]                                              # la configuration des comptes est conservée
        assert c.put("/api/expenses/plates", json={"plates": {"@@": "x"}}).status_code == 422
        app.dependency_overrides[m.require_user] = lambda: "actionnaire@x.be"
        assert c.put("/api/expenses/plates", json={"plates": {}}).status_code == 403
        assert c.get("/api/fuel/parse?att=901&year=2026").json()["transactions"]
    finally:
        app.dependency_overrides.clear()
