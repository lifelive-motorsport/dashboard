from fastapi.testclient import TestClient
from app.main import app

c = TestClient(app)


def test_dashboard_demo():
    r = c.get("/api/dashboard?from=2026-01-01&to=2026-12-31").json()
    assert r["source"] == "demo"
    pnl = r["pnl"]
    assert abs(sum(b["ca"] for b in pnl["bus"]) - pnl["total"]["ca"]) < 1e-6
    g = {x["key"]: x for x in pnl["groups"]}
    assert g["XC"]["ca"] + g["CARS"]["ca"] + g["OTHER"]["ca"] == pnl["total"]["ca"]
    assert r["balance_sheet"]["cash"] > 0 and "XC" in r["top_clients"]


def test_source_failure_returns_502_not_500(monkeypatch):
    import app.main as m

    class Boom:
        name = "boom"
        def pnl_balances(self, *a): raise RuntimeError("secret detail")

    monkeypatch.setattr(m, "_provider", Boom())
    m._cache.clear()
    r = c.get("/api/dashboard?from=2020-01-01&to=2020-01-31")
    assert r.status_code == 502 and "secret" not in r.text


def test_health_endpoint():
    assert c.get("/api/health").json() == {"ok": True}  # « /healthz » est réservé par Cloud Run


def test_adjustments_roundtrip_validation_and_edit_rights(monkeypatch):
    import app.adjustments as adj
    import app.main as m
    monkeypatch.setattr(adj, "_store", adj.MemoryStore())
    item = {"id": "andalucia", "label": "Andalucia – investissement", "bu": "HISTORIC_RACING", "kind": "meeting",
            "sel": [{"id": 10, "name": "LLM/GDM event Andalucia"}], "measure": "result"}
    r = c.put("/api/adjustments", json={"items": [item]})
    assert r.status_code == 200
    got = c.get("/api/adjustments").json()
    assert got["items"][0]["label"].startswith("Andalucia") and got["can_edit"] is True and got["updated_at"]
    assert c.put("/api/adjustments", json={"items": [{**item, "bu": "NOPE"}]}).status_code == 422          # BU inconnue
    assert c.put("/api/adjustments", json={"items": [item, item]}).status_code == 422                       # doublon
    assert c.put("/api/adjustments", json={"items": [{**item, "kind": "manual", "date": "pas-une-date"}]}).status_code == 422
    monkeypatch.setattr(m.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(adj.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(adj.settings, "ADMIN_EMAILS", ["md@x.be"])
    app.dependency_overrides[m.require_user] = lambda: "actionnaire@x.be"
    try:
        assert c.put("/api/adjustments", json={"items": []}).status_code == 403                             # lecture seule
        assert c.get("/api/adjustments").json()["can_edit"] is False
        app.dependency_overrides[m.require_user] = lambda: "md@x.be"
        assert c.put("/api/adjustments", json={"items": []}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_dashboard_carries_the_previous_year_same_period_and_handles_leap_day():
    from datetime import date
    import app.main as m
    m._cache.clear()
    r = c.get("/api/dashboard?from=2026-01-01&to=2026-10-05").json()
    assert r["pnl_prev"]["period"] == {"from": "2025-01-01", "to": "2025-10-05"} and r["pnl_prev"]["total"]["ca"] >= 0
    assert m._year_back(date(2024, 2, 29)) == date(2023, 2, 28) and m._year_back(date(2026, 10, 5)) == date(2025, 10, 5)


def test_session_cookie_roundtrip_expiry_tampering_and_revocation(monkeypatch):
    import time
    import app.auth as a
    import app.main as m
    monkeypatch.setattr(a.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(a.settings, "SESSION_SECRET", "x" * 40)
    monkeypatch.setattr(a.settings, "SESSION_DAYS", 14)
    monkeypatch.setattr(a.settings, "ALLOWED_DOMAIN", "lifelive-motorsport.com")
    monkeypatch.setattr(a.settings, "ALLOWED_EMAILS", ["actio@gmail.com"])
    monkeypatch.setattr(a, "verify_google", lambda auth: "md@lifelive-motorsport.com" if auth == "Bearer ok" else (_ for _ in ()).throw(HTTPException(401, "x")))
    monkeypatch.setattr(m, "verify_google", a.verify_google)
    from fastapi import HTTPException
    cl = TestClient(app)
    assert cl.get("/api/session").status_code == 401                                   # ni cookie ni jeton
    r = cl.post("/api/session", headers={"Authorization": "Bearer ok"})
    assert r.json() == {"email": "md@lifelive-motorsport.com", "session": True} and "lm_session" in r.headers["set-cookie"]
    assert "HttpOnly" in r.headers["set-cookie"] and "SameSite=strict" in r.headers["set-cookie"]
    assert cl.get("/api/session").json()["email"] == "md@lifelive-motorsport.com"      # le cookie suffit, plus de jeton Google
    good = a.make_session("md@lifelive-motorsport.com")
    assert a.read_session(good) is not None
    assert a.read_session(good[:-2] + "xx") is None                                    # signature falsifiée
    assert a.read_session(good, now=time.time() + 15 * 86400) is None                  # expirée après SESSION_DAYS
    assert a.read_session(a.make_session("intrus@autre.com")) is None                  # adresse plus autorisée : accès retiré immédiatement
    assert a.read_session(a.make_session("actio@gmail.com")) is not None               # liste blanche
    cl.cookies.clear()
    assert cl.get("/api/session").status_code == 401
    monkeypatch.setattr(a.settings, "SESSION_SECRET", "")
    assert TestClient(app).post("/api/session", headers={"Authorization": "Bearer ok"}).json()["session"] is False   # non configuré : jeton seul


def test_config_exposes_odoo_analytic_link_only_with_odoo_source(monkeypatch):
    import app.main as m
    assert c.get("/api/config").json()["analytic_link"] == ""                             # démo : pas de lien
    monkeypatch.setattr(m.settings, "PROVIDER", "odoo")
    monkeypatch.setattr(m.settings, "ODOO_PUBLIC_URL", "https://lifelive.odoo.com/")
    assert c.get("/api/config").json()["analytic_link"] == "https://lifelive.odoo.com/odoo/account.analytic.account/{id}/action-183"


def test_analytics_unconfigured_then_filters_and_buckets(monkeypatch):
    from datetime import date
    import app.ga as ga
    import app.main as m
    assert m._safe(ga.report, date(2026, 1, 1), date(2026, 3, 31)) == {"unconfigured": True}                 # rien de configuré
    monkeypatch.setattr(ga.settings, "GA_PROPERTY_ID", "123456")
    seen = []

    def fake(prop, body):
        seen.append((prop, body))
        dims = [d["name"] for d in body["dimensions"]]
        if dims == []:
            return {"rows": [{"dimensionValues": [{"value": "date_range_0"}], "metricValues": [{"value": str(i + 10)} for i in range(9)]},
                             {"dimensionValues": [{"value": "date_range_1"}], "metricValues": [{"value": "5"} for _ in range(9)]}]}
        if dims == ["yearMonth"]:
            return {"rows": [{"dimensionValues": [{"value": "202601"}], "metricValues": [{"value": v} for v in ("100", "60", "300", "2")]},
                             {"dimensionValues": [{"value": "202603"}], "metricValues": [{"value": v} for v in ("50", "30", "150", "1")]}]}
        if dims == ["sessionDefaultChannelGroup"]:
            return {"rows": [{"dimensionValues": [{"value": "Direct"}], "metricValues": [{"value": v} for v in ("30", "20", "1")]},
                             {"dimensionValues": [{"value": "Organic Search"}], "metricValues": [{"value": v} for v in ("70", "40", "2")]}]}
        if dims == ["pagePath", "pageTitle"]:
            return {"rows": [{"dimensionValues": [{"value": "/shop/a"}, {"value": "(not set)"}], "metricValues": [{"value": "9"}, {"value": "4"}]}]}
        return {"rows": []}
    monkeypatch.setattr(ga, "_post", fake)
    ga._cache.clear()
    r = ga.report(date(2026, 1, 1), date(2026, 3, 31))
    xc = r["xc"]
    assert xc["totals"]["current"]["sessions"] == 10.0 and xc["totals"]["previous"]["sessions"] == 5.0
    assert xc["series"]["granularity"] == "month" and [p["sessions"] for p in xc["series"]["points"]] == [100, 0, 50]      # février absent : 0
    assert [c["name"] for c in xc["channels"]] == ["Direct", "Organic Search"] and round(xc["channels"][0]["share"], 2) == 0.3
    assert xc["pages"][0]["title"] == "/shop/a"                                                                               # titre absent : on garde le chemin
    flt = seen[0][1]["dimensionFilter"]["andGroup"]["expressions"]
    assert {"filter": {"fieldName": "hostName", "stringFilter": {"matchType": "EXACT", "value": "www.lifelive-motorsport.com"}}} in flt
    assert any(e["filter"]["fieldName"] == "pagePath" for e in flt)                                                           # chemin /shop pour le webshop
    site = [b for _, b in seen if "dimensionFilter" in b and len(b["dimensionFilter"]["andGroup"]["expressions"]) == 1]
    assert site                                                                                                              # site vitrine : hôte seul


def _staff_app(monkeypatch, role):
    import app.adjustments as adj
    import app.main as m
    import app.staff as st
    monkeypatch.setattr(st, "_store", st.Store())
    monkeypatch.setattr(st, "_files", st.Files())
    monkeypatch.setattr(adj.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(adj.settings, "ADMIN_EMAILS", ["md@x.be"])
    app.dependency_overrides[m.require_user] = lambda: role
    return st


def test_staff_data_is_admin_only_and_conflicts_are_detected(monkeypatch):
    st = _staff_app(monkeypatch, "actionnaire@x.be")
    try:
        assert c.get("/api/staff").json() == {"restricted": True, "can_edit": False}                      # aucune donnée pour un actionnaire
        assert c.put("/api/staff", json={"data": {}, "base": None}).status_code == 403
        assert c.get("/api/staff/accounting?year=2026").status_code == 403 and c.get("/api/staff/payslip?person=a&month=2026-01").status_code == 403
        import app.main as m
        app.dependency_overrides[m.require_user] = lambda: "md@x.be"
        person = {"id": "p1", "name": "Alice", "kind": "salarie", "alloc": {"XC": 60, "SHARED": 40}, "payslips": [{"month": "2026-01", "brut": 3000}]}
        r = c.put("/api/staff", json={"data": {"people": [person]}, "base": None})
        assert r.status_code == 200 and r.json()["updated_by"] == "md@x.be"
        got = c.get("/api/staff").json()
        assert got["data"]["people"][0]["name"] == "Alice" and got["data"]["params"]["annual_factor"] == 13.92
        assert c.put("/api/staff", json={"data": {"people": [person]}, "base": None}).status_code == 409        # base périmée
        assert c.put("/api/staff", json={"data": {"people": [person]}, "base": got["updated_at"]}).status_code == 200
        bad = {**person, "alloc": {"XC": 80, "SHARED": 40}}
        assert c.put("/api/staff", json={"data": {"people": [bad]}, "base": None}).status_code == 422          # > 100 %
        assert c.put("/api/staff", json={"data": {"people": [{**person, "alloc": {"AUTRE": 10}}]}, "base": None}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_payslip_upload_accepts_only_small_pdfs_and_roundtrips(monkeypatch):
    _staff_app(monkeypatch, "md@x.be")
    try:
        monkeypatch.setattr("app.main.settings.PROVIDER", "demo")
        r = c.put("/api/staff/payslip?person=p1&month=2026-01", content=b"%PDF-1.4 test")
        assert r.status_code == 200 and r.json()["size"] == 13
        assert c.get("/api/staff/payslip?person=p1&month=2026-01").content == b"%PDF-1.4 test"
        assert c.put("/api/staff/payslip?person=p1&month=2026-01", content=b"MZ not a pdf").status_code == 415
        assert c.put("/api/staff/payslip?person=../x&month=2026-01", content=b"%PDF").status_code == 422     # pas de traversée de dossier
        assert c.put("/api/staff/payslip?person=p1&month=2026-13", content=b"%PDF").status_code == 422
        assert c.get("/api/staff/payslip?person=p1&month=2025-05").status_code == 404
        assert c.get("/api/staff/accounting?year=2026").json()["pay_prefixes"] == ["620", "621"]
        assert c.get("/api/staff/invoices?ids=9001&year=2026").json()["invoices"]
    finally:
        app.dependency_overrides.clear()


def test_staff_import_zip_adds_people_merges_slips_and_stores_pdfs(monkeypatch):
    import io
    import json
    import zipfile
    _staff_app(monkeypatch, "md@x.be")
    try:
        monkeypatch.setattr("app.main.settings.PROVIDER", "demo")
        person = {"id": "dupont-jean", "name": "DUPONT Jean", "kind": "salarie", "factor": 12,
                  "payslips": [{"month": "2026-01", "brut": 3000, "patronal": 1000}, {"month": "2026-02", "brut": 3100, "patronal": 1050}]}
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("staff.json", json.dumps({"people": [person]}))
            z.writestr("payslips/dupont-jean/2026-01.pdf", b"%PDF-1.4 a")
            z.writestr("payslips/dupont-jean/2026-xx.pdf", b"%PDF-1.4 ignore")
            z.writestr("payslips/../x/2026-01.pdf", b"%PDF-1.4 ignore")
            z.writestr("payslips/dupont-jean/2026-02.pdf", b"pas un pdf")
        c = TestClient(app)
        r = c.post("/api/staff/import", content=buf.getvalue())
        assert r.status_code == 200 and r.json()["added"] == ["dupont-jean"] and r.json()["pdfs"] == 1
        assert c.get("/api/staff/payslip?person=dupont-jean&month=2026-01").content == b"%PDF-1.4 a"
        # deuxième import : la personne existe, ses fiches sont fusionnées, sans écraser le reste de sa fiche
        cur = c.get("/api/staff").json()
        edited = {**cur["data"]["people"][0], "function": "Mécanicien"}
        assert c.put("/api/staff", json={"data": {"people": [edited]}, "base": cur["updated_at"]}).status_code == 200
        person["payslips"].append({"month": "2026-03", "brut": 3200, "patronal": 1100})
        buf2 = io.BytesIO()
        with zipfile.ZipFile(buf2, "w") as z:
            z.writestr("staff.json", json.dumps({"people": [person]}))
        r = c.post("/api/staff/import", content=buf2.getvalue())
        assert r.json()["merged"] == ["dupont-jean"]
        got = c.get("/api/staff").json()["data"]["people"][0]
        assert got["function"] == "Mécanicien" and [s["month"] for s in got["payslips"]] == ["2026-01", "2026-02", "2026-03"]
        assert c.post("/api/staff/import", content=b"pas une archive").status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_pnl_unassigned_demo():
    c = TestClient(app)
    r = c.get("/api/pnl/unassigned?year=2026")
    assert r.status_code == 200 and r.json()["accounts"][0]["code"] == "700099"


def test_reference_values_can_only_be_saved_by_their_owner(monkeypatch):
    st = _staff_app(monkeypatch, "md@x.be")
    import app.main as m
    monkeypatch.setattr(m.settings, "ADMIN_EMAILS", ["md@x.be", "autre@x.be"])
    monkeypatch.setattr(m.adjustments.settings, "ADMIN_EMAILS", ["md@x.be", "autre@x.be"])
    monkeypatch.setattr(m.adjustments.settings, "REFERENCE_EDITORS", ["md@x.be"])
    try:
        app.dependency_overrides[m.require_user] = lambda: "autre@x.be"
        got = c.get("/api/staff").json()
        assert got["can_edit"] is True and got["can_save"] is False                                         # il peut simuler, pas enregistrer
        assert c.put("/api/staff", json={"data": {}, "base": None}).status_code == 403
        assert c.put("/api/expenses/split", json={"split": {}, "base": None}).status_code == 403
        assert c.put("/api/expenses/key", json={"key_mode": "pct", "xc_pct": 40}).status_code == 403
        app.dependency_overrides[m.require_user] = lambda: "md@x.be"
        assert c.get("/api/staff").json()["can_save"] is True
        assert c.put("/api/staff", json={"data": {}, "base": None}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_staff_common_split_is_validated(monkeypatch):
    _staff_app(monkeypatch, "md@x.be")
    try:
        person = {"id": "p1", "name": "Alice", "kind": "salarie", "alloc": {"SHARED": 100}, "common_split": {"XC": 50, "MODERN_RALLY": 50}}
        assert c.put("/api/staff", json={"data": {"people": [person]}, "base": None}).status_code == 200
        assert c.get("/api/staff").json()["data"]["people"][0]["common_split"] == {"XC": 50.0, "MODERN_RALLY": 50.0}
        assert c.put("/api/staff", json={"data": {"people": [{**person, "common_split": {"XC": 80, "MODERN_RALLY": 40}}]}, "base": None}).status_code == 422
        assert c.put("/api/staff", json={"data": {"people": [{**person, "common_split": {"SHARED": 10}}]}, "base": None}).status_code == 422
    finally:
        app.dependency_overrides.clear()


def test_margin_control_demo_and_rules():
    from app import margins
    assert margins.rate(26) == "green" and margins.rate(25) == "orange" and margins.rate(15.01) == "orange" and margins.rate(15) == "red" and margins.rate(None) is None
    j = c.get("/api/xc/margins").json()
    r1 = next(r for r in j["rows"] if r["ref"] == "611363")
    assert r1["real"]["unit"] == 32.0 and r1["margin"]["theoretical"] == 42.86 and r1["margin"]["real"] == 45.55 and r1["gap"] == 2.69 and "worst" not in r1
    r2 = next(r for r in j["rows"] if r["ref"] == "611001")
    assert r2["gap"] == -10.0 and r2["rate"]["theoretical"] == "orange" and r2["rate"]["real"] == "red"
    r4 = next(r for r in j["rows"] if r["ref"] == "611003")
    assert r4["real"] is None and r4["gap"] is None and r4["rate"]["real"] is None
    assert j["summary"]["count"] == 4 and sum(b["count"] for b in j["summary"]["buckets"]) == j["summary"]["compared"]


def test_margins_ignore_zero_costs():
    from app import margins
    assert margins.margin_pct(446.0, 0.0) is None and margins.margin_pct(100.0, 60.0) == 40.0


def test_stockvar_roundtrip_and_validation(monkeypatch):
    from app import stockvar
    monkeypatch.setattr(stockvar, "_store", stockvar.MemoryStore())
    item = {"id": "s1", "label": "Inventaire de fin d'année", "amount": -12500.5, "date": "2026-06-30", "enabled": True, "note": "dépréciation"}
    r = c.put("/api/stockvar", json={"items": [item]})
    assert r.status_code == 200
    got = c.get("/api/stockvar").json()
    assert got["items"][0]["amount"] == -12500.5 and got["can_edit"] is True
    assert c.put("/api/stockvar", json={"items": [item, item]}).status_code == 422
    assert c.put("/api/stockvar", json={"items": [{**item, "date": "pas une date"}]}).status_code == 422
