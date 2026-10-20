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
    assert r.json() == {"email": "md@lifelive-motorsport.com", "session": True, "role": "custom", "super": False, "workshop_role": None, "name": "Md", "first": "Md", "profile": "Non classé", "pages": []} and "lm_session" in r.headers["set-cookie"]
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
    assert c.get("/api/config").json()["partner_link"] == "https://lifelive.odoo.com/odoo/contacts/{id}/action-1439"
    assert c.get("/api/config").json()["client_link"] == "https://lifelive.odoo.com/odoo/contacts/{id}"            # un client n'a pas de factures fournisseurs : on ouvre sa fiche


def test_hit_parade_rows_carry_partner_id():
    from datetime import date
    from app.providers.demo import DemoProvider
    d = DemoProvider()
    assert all(r["id"] for r in d.top_clients(date(2026, 1, 1), date(2026, 12, 31))["total"])
    assert all(r["id"] for r in d.top_suppliers(date(2026, 1, 1), date(2026, 12, 31))["total"])


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
    assert r1["real"]["buy"] == 32.0 and r1["real"]["freight"] == 1.7631 and r1["real"]["unit"] == 33.7631 and r1["margin"]["theoretical"] == 42.86 and r1["margin"]["real"] == 42.55 and r1["gap"] == -0.31
    r2 = next(r for r in j["rows"] if r["ref"] == "611001")
    assert r2["gap"] == -13.0 and r2["rate"]["theoretical"] == "orange" and r2["rate"]["real"] == "red"
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


def test_allocate_orders_global_bill_like_the_tn11_tubes():
    from app import margins
    # Commande P00668 : 30 tubes [325061] à 198,33 € et 24 découpes-cintrages [611010] à 820 € ; une seule facture globale (1 pièce, 17 661,84 €) sur la ligne des tubes.
    orders = {1: {"lines": {10: {"product": 325061, "qty": 30, "received": 30, "price": 198.33}, 11: {"product": 611010, "qty": 24, "received": 24, "price": 820.0},
                            12: {"product": 999, "qty": 144, "received": 0, "price": 5.27}},
                  "bills": {10: {"amount": 17661.84, "qty": 1}}}}
    a = margins.allocate_orders(orders)
    assert round(a[325061]["amount"] / a[325061]["qty"], 2) == 198.33 and a[325061]["flags"] == {"globale"}      # les tubes gardent leur prix de commande
    assert round(a[611010]["amount"], 2) == round(17661.84 - 198.33 * 30, 2) and a[611010]["qty"] == 24         # l'excédent va à la découpe-cintrage reçue mais non facturée
    assert 999 not in a                                                                                         # ligne non reçue : rien
    # Facture cohérente : on garde le montant facturé (ici 5 % de plus que la commande)
    ok = margins.allocate_orders({2: {"lines": {1: {"product": 5, "qty": 10, "received": 10, "price": 10.0}}, "bills": {1: {"amount": 105.0, "qty": 10}}}})
    assert ok[5]["amount"] == 105.0 and ok[5]["qty"] == 10 and not ok[5]["flags"]


def test_freight_rate_prorata_of_sale_price():
    from app import margins
    prods = [{"id": 1, "sale": 100.0}, {"id": 2, "sale": 50.0}]
    real = {1: {"qty": 10.0}, 2: {"qty": 20.0}}
    assert margins.freight_rate(100.0, prods, real) == 0.05                       # 100 € de transport pour 2 000 € de ventes valorisées
    assert margins.freight_rate(0.0, prods, real) == 0.0 and margins.freight_rate(100.0, prods, {}) == 0.0


def test_xc_only_category(monkeypatch):
    """La catégorie « XC » ne peut appeler que les routes des pages XC ; le tableau de bord est neutralisé côté serveur."""
    from app import settings
    monkeypatch.setattr(settings, "XC_ONLY_EMAILS", ["anonymous"])
    from starlette.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.get("/api/session").json()["role"] == "custom"
    for path in ("/api/adjustments", "/api/staff", "/api/stockvar", "/api/tags", "/api/expenses/allocation?year=2026", "/api/pnl/unassigned?year=2026"):
        assert c.get(path).status_code == 403, path
    d = c.get("/api/dashboard").json()
    assert d["pnl"]["total"]["ca"] == 0 and d["top_clients"] == {"unavailable": "Réservé"}
    assert all(e["group"] != "CARS" for e in d["events"]["events"])
    assert "site" not in d["analytics"]
    assert c.get("/api/stock").status_code != 403 and c.get("/api/xc/margins").status_code != 403


def test_users_admin(monkeypatch):
    """Le Super User crée des utilisateurs et leurs rôles ; un rôle enregistré l'emporte sur la configuration."""
    from app import settings, users
    from starlette.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.put("/api/users", json={"users": [{"email": "Ext@Example.com", "role": "xc"}, {"email": "b@x.com", "role": "admin"}]})
    assert r.status_code == 200 and {u["email"] for u in r.json()["users"]} == {"ext@example.com", "b@x.com"}
    assert c.put("/api/users", json={"users": [{"email": "a@x.com", "role": "xc"}, {"email": "a@x.com", "role": "admin"}]}).status_code == 422
    assert c.put("/api/users", json={"users": [{"email": "pas-un-mail", "role": "xc"}]}).status_code == 422
    assert users.is_registered("ext@example.com") and users.role_of("ext@example.com") == "xc" or users.role_of("ext@example.com") == "cat:xc"        # AUTH désactivée (démo) : tout le monde peut gérer les utilisateurs
    monkeypatch.setattr(settings, "AUTH_ENABLED", True)
    assert users.role_of("ext@example.com") == "cat:xc" and users.role_of("b@x.com") == "admin" and users.role_of("z@lifelive-motorsport.com") == "pending"
    monkeypatch.setattr(settings, "SUPER_USERS", ["z@lifelive-motorsport.com"])
    assert users.role_of("z@lifelive-motorsport.com") == "super"
    users.store().put([], "t"); users.invalidate()


def test_custom_category_pages_and_routes(monkeypatch):
    """Une catégorie = nom + pages cochées : le serveur n'ouvre que les routes et les données de ces pages."""
    from app import settings, users
    from starlette.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.put("/api/users", json={"categories": [{"id": "compta", "name": "Compta", "pages": ["staff/people", "cars/vehicles"]}],
                                  "users": [{"email": "me@x.com", "role": "cat:compta"}]})
    assert r.status_code == 200 and any(x["id"] == "xc" for x in r.json()["categories"])
    assert c.put("/api/users", json={"categories": [], "users": [{"email": "me@x.com", "role": "cat:nope"}]}).status_code == 422
    assert c.put("/api/users", json={"categories": [{"id": "z", "name": "Z", "pages": ["page/inconnue"]}], "users": []}).status_code == 422
    c.put("/api/users", json={"categories": [{"id": "xc", "name": "XC", "pages": ["xc/margins", "cars/vehicles"]}], "users": []})
    monkeypatch.setattr(settings, "XC_ONLY_EMAILS", ["anonymous"])
    users.invalidate()
    assert c.get("/api/session").json()["pages"] == ["cars/vehicles", "xc/margins"]
    assert c.get("/api/xc/margins").status_code != 403 and c.get("/api/staff").status_code == 403 and c.get("/api/stock").status_code == 403
    d = c.get("/api/dashboard").json()
    assert d["pnl"]["total"]["ca"] == 0 and d["vehicles"] != {"unavailable": "Réservé"} and d["events"] == {"unavailable": "Réservé"}
    users.store().put([], "t"); users.invalidate()


def test_projection_monthly_and_expected():
    from starlette.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    j = c.get("/api/projection?year=2026").json()
    assert j["months"] and set(j["months"][0]) >= {"month", "XC", "CARS", "OTHER", "partial"} and j["expected"] == {"XC": {}, "CARS": {}}
    assert len(j["prev_months"]) == 12 and all(set(x) == {"month", "ca"} for x in j["prev_months"])
    r = c.put("/api/projection", json={"year": 2026, "expected": {"XC": {"11": 150000, "12": 90000.5}, "CARS": {"11": 80000}}})
    assert r.status_code == 200 and c.get("/api/projection?year=2026").json()["expected"] == {"XC": {"11": 150000.0, "12": 90000.5}, "CARS": {"11": 80000.0}}
    assert c.put("/api/projection", json={"year": 2026, "expected": {"XC": {"13": 5}}}).status_code == 422
    assert c.put("/api/projection", json={"year": 2026, "expected": {"XC": {"3": -150}}}).status_code == 422


def test_identity_nickname_and_super_row(monkeypatch):
    from app import settings, users
    from starlette.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    monkeypatch.setattr(settings, "SUPER_USERS", ["raphael.deborman@lifelive-motorsport.com"])
    r = c.put("/api/users", json={"categories": [], "users": [{"email": "raphael.deborman@lifelive-motorsport.com", "role": "standard", "note": "Raphaël de Borman", "nickname": "Raph"}]})
    assert r.status_code == 200
    users.invalidate()
    i = users.identity("raphael.deborman@lifelive-motorsport.com")
    assert i == {"name": "Raphaël de Borman", "first": "Raph", "profile": "Super User"}
    assert users.role_of("raphael.deborman@lifelive-motorsport.com") == "super"
    users.store().put([], "t"); users.invalidate()


def test_legacy_host_redirect(monkeypatch):
    from app import settings
    from starlette.testclient import TestClient
    from app.main import app
    c = TestClient(app, follow_redirects=False)
    assert c.get("/api/health", headers={"host": "dashboard-app.lifelive-motorsport.com"}).status_code == 200           # désactivé tant que CANONICAL_HOST est vide
    monkeypatch.setattr(settings, "CANONICAL_HOST", "logbook.lifelive-motorsport.com")
    r = c.get("/api/dashboard?from=2026-01-01", headers={"host": "dashboard-app.lifelive-motorsport.com"})
    assert r.status_code == 301 and r.headers["location"] == "https://logbook.lifelive-motorsport.com/api/dashboard?from=2026-01-01"
    assert c.get("/api/health", headers={"host": "dashboard-app.lifelive-motorsport.com"}).status_code == 200
    assert c.get("/api/health", headers={"host": "logbook.lifelive-motorsport.com"}).status_code == 200
    assert c.get("/api/health", headers={"host": "dashboard-xyz.europe-west1.run.app"}).status_code == 200


def test_resources_super_user_only_and_demo_flow(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    r = c.get("/api/resources")
    assert r.status_code == 200 and {"staff", "externals", "vehicles", "delegation"} <= set(r.json())
    assert r.json()["vehicles"]["items"]
    # compte Google d'une personne du staff (créée à la volée)
    from app import staff
    cur = staff.store().get()
    people = [{"id": "r1", "name": "Test Resource", "kind": "salarie"}]
    assert staff.store().put({"params": cur["data"]["params"], "people": people}, "t", cur["updated_at"]) is not None
    ok = c.put("/api/resources/staff/r1", json={"email": "Test@Lifelive-Motorsport.com"})
    assert ok.status_code == 200 and ok.json()["email"] == "test@lifelive-motorsport.com"
    assert c.put("/api/resources/staff/r1", json={"email": "pas-un-mail"}).status_code == 422
    assert c.put("/api/resources/staff/nope", json={"email": ""}).status_code == 404
    both = c.put("/api/resources/staff/r1", json={"all_bus": True}).json()
    assert both == {"id": "r1", "email": "test@lifelive-motorsport.com", "all_bus": True, "bus": [], "workshop": "", "work_days": [0, 1, 2, 3, 4]}          # seuls les champs fournis changent
    assert c.get("/api/resources").json()["staff"][0]["all_bus"] is True
    assert c.put("/api/resources/staff/r1", json={"all_bus": False}).json()["all_bus"] is False
    got = c.get("/api/resources").json()["staff"]
    assert got[0]["email"] == "test@lifelive-motorsport.com"
    # prestataires externes : liste, doublon refusé, conflit de version
    base = c.get("/api/resources").json()["externals"]["updated_at"]
    ext = {"partner_id": 9101, "name": "Julien Garage", "email": "julien@garage-exemple.be", "bus": ["XC", "HISTORIC_RACING"]}
    assert c.put("/api/resources/externals", json={"data": {"externals": [{**ext, "bus": ["MARS"]}]}, "base": base}).status_code == 422
    assert c.put("/api/resources/externals", json={"data": {"externals": [ext, ext]}, "base": base}).status_code == 422
    assert c.put("/api/resources/externals", json={"data": {"externals": [ext]}, "base": base}).status_code == 200
    assert c.get("/api/resources").json()["externals"]["data"]["externals"][0]["bus"] == ["XC", "HISTORIC_RACING"]
    assert c.put("/api/resources/externals", json={"data": {"externals": []}, "base": base}).status_code == 409
    q = c.get("/api/resources/contacts", params={"q": "garage"}).json()["contacts"]
    assert q and q[0]["email"]


def test_resources_directory_users_demo():
    from fastapi.testclient import TestClient
    from app.main import app
    j = TestClient(app).get("/api/resources/directory-users").json()
    assert j["configured"] and j["items"][0]["email"].endswith("@lifelive-motorsport.com")


def _ev(**kw):
    base = {"title": "Spa Classic", "bu": "HISTORIC_RACING", "confirmed": False, "start": "2026-06-20", "end": "2026-06-22", "immo_start": "2026-06-18", "immo_end": "2026-06-24",
            "place": {"id": "demo-spa", "name": "Circuit de Spa-Francorchamps", "address": "Route du Circuit 55, 4970 Stavelot", "country": "BE"},
            "notes": "Camion + 2 mécanos", "staff": ["a@lifelive-motorsport.com"], "externals": ["ext@garage.be"], "vehicles": ["sprinter@resource.calendar.google.com"]}
    base.update(kw)
    return base


def test_planned_events_full_cycle():
    from fastapi.testclient import TestClient
    from app.main import app
    from app import planning
    c = TestClient(app)
    assert c.get("/api/events/config").json()["maps"] is True
    r = c.post("/api/events", json=_ev())
    assert r.status_code == 200, r.text
    lbid = r.json()["id"]
    be = planning.backend()
    cal = planning.calendars_by_bu()["HISTORIC_RACING"]
    evs = list(be.events[cal].values())
    main = next(e for e in evs if e["extendedProperties"]["shared"]["kind"] == "main")
    veh = next(e for e in evs if e["extendedProperties"]["shared"]["kind"] == "vehicles")
    assert main["summary"] == "[TBC] Spa Classic" and main["colorId"] == "10"
    assert [a["email"] for a in main["attendees"]] == ["a@lifelive-motorsport.com"]            # prestataires pas encore invités (TBC)
    assert main["end"]["date"] == "2026-06-23" and veh["start"]["date"] == "2026-06-18" and veh["end"]["date"] == "2026-06-25"
    assert veh["attendees"] == [{"email": "sprinter@resource.calendar.google.com", "resource": True}]
    assert "63 km" in main["description"] and main["description"].startswith("Camion + 2 mécanos")
    got = c.get("/api/events", params={"from": "2026-06-01", "to": "2026-06-30"}).json()["events"]
    assert got[0]["externals_pending"] == ["ext@garage.be"]
    assert got[0]["title"] == "Spa Classic" and not got[0]["confirmed"] and got[0]["notes"] == "Camion + 2 mécanos" and got[0]["vehicles"] == ["sprinter@resource.calendar.google.com"]
    assert (got[0]["immo_start"], got[0]["immo_end"]) == ("2026-06-18", "2026-06-24") and got[0]["km"] == 63
    assert got[0]["responses"] == {"a@lifelive-motorsport.com": "needsAction", "sprinter@resource.calendar.google.com": "needsAction"}      # pas encore de réponse
    main["attendees"][0]["responseStatus"] = "accepted"                                       # Google met à jour la réponse dans l'événement
    veh["attendees"][0]["responseStatus"] = "declined"
    got = c.get("/api/events", params={"from": "2026-06-01", "to": "2026-06-30"}).json()["events"]
    assert got[0]["responses"] == {"a@lifelive-motorsport.com": "accepted", "sprinter@resource.calendar.google.com": "declined"}
    # confirmation : titre sans TBC, prestataires invités
    assert c.put(f"/api/events/{lbid}", json=_ev(confirmed=True)).status_code == 200
    main = next(e for e in be.events[cal].values() if e["extendedProperties"]["shared"]["kind"] == "main")
    assert main["summary"] == "Spa Classic" and "ext@garage.be" in [a["email"] for a in main["attendees"]]
    # dates d'immobilisation identiques : un seul événement, véhicules sur l'événement principal
    assert c.put(f"/api/events/{lbid}", json=_ev(confirmed=True, immo_start="2026-06-20", immo_end="2026-06-22")).status_code == 200
    kinds = [e["extendedProperties"]["shared"]["kind"] for e in be.events[cal].values()]
    assert kinds == ["main"]
    main = next(iter(be.events[cal].values()))
    assert {"email": "sprinter@resource.calendar.google.com", "resource": True} in main["attendees"]
    # changement de BU : déplacé dans l'autre agenda
    assert c.put(f"/api/events/{lbid}", json=_ev(bu="XC")).status_code == 200
    assert not be.events[cal] and len(be.events[planning.calendars_by_bu()["XC"]]) == 2
    assert c.delete(f"/api/events/{lbid}").status_code == 200
    assert c.delete(f"/api/events/{lbid}").status_code == 404
    assert c.get("/api/events", params={"from": "2026-06-01", "to": "2026-06-30"}).json()["events"] == []


def test_planned_events_validation_and_places():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    assert c.post("/api/events", json=_ev(place={"id": ""})).status_code == 422                # lieu obligatoire
    assert c.post("/api/events", json=_ev(immo_start="2026-06-21")).status_code == 422          # l'immobilisation doit couvrir l'événement
    assert c.post("/api/events", json=_ev(end="2026-06-19")).status_code == 422
    assert c.post("/api/events", json=_ev(bu="MARS")).status_code == 422
    assert c.post("/api/events", json=_ev(staff=["pas-un-mail"])).status_code == 422
    s = c.get("/api/places/autocomplete", params={"q": "silver"}).json()["suggestions"]
    assert s[0]["id"] == "demo-silverstone"
    uk = c.get("/api/places/demo-silverstone").json()
    assert "le Royaume-Uni" in uk["route"]["alerts"][0] and uk["route"]["km"] == 780
    ch = c.get("/api/places/demo-monza").json()
    assert ch["route"]["via"] == ["CH"] and "la Suisse" in ch["route"]["alerts"][0]
    assert c.get("/api/places/demo-spa").json()["route"]["alerts"] == []
    assert c.get("/api/places/inconnu").status_code == 404
    b = c.post("/api/events/busy", json={"emails": ["sprinter@resource.calendar.google.com", "citan@resource.calendar.google.com"], "start": "2026-06-20", "end": "2026-06-22"}).json()["busy"]
    assert b["sprinter@resource.calendar.google.com"] and not b["citan@resource.calendar.google.com"]


def test_maps_countries_crossed_samples_only_watched_boxes(monkeypatch):
    from app import maps
    calls = []
    monkeypatch.setattr(maps, "_country_at", lambda p: (calls.append(p), "CH" if p[0] > 46.5 else "FR")[1])
    # trajet Belgique -> Suisse -> Italie : seuls les points dans la zone suisse sont vérifiés
    pts = [(50.2, 6.1), (49.0, 6.5), (47.6, 7.6), (47.1, 8.0), (46.8, 8.3), (46.0, 8.9), (45.6, 9.2)]
    assert maps.countries_crossed(pts) == {"CH"}
    assert all(45.7 <= p[0] <= 47.9 for p in calls)
    assert maps.countries_crossed([(50.2, 6.1), (49.5, 2.0)]) == set() and len(calls) == len(calls)


def test_planned_event_with_custom_origin():
    from fastapi.testclient import TestClient
    from app.main import app
    from app import planning
    c = TestClient(app)
    origin = {"id": "demo-ricard", "name": "Circuit Paul Ricard", "address": "Le Castellet, France", "country": "FR"}
    r = c.get("/api/places/demo-silverstone", params={"origin": "demo-ricard"}).json()
    assert r["route"]["origin_label"] == "Circuit Paul Ricard" and r["route"]["km"] == 250 and "depuis Circuit Paul Ricard" in r["route"]["alerts"][0]
    assert c.get("/api/places/demo-spa", params={"route": "false"}).json()["route"] is None
    assert c.get("/api/places/demo-spa", params={"origin": "inconnu"}).status_code == 404
    lbid = c.post("/api/events", json=_ev(origin=origin, vehicles=[], externals=[])).json()["id"]
    got = c.get("/api/events", params={"from": "2026-06-01", "to": "2026-06-30"}).json()["events"][0]
    assert got["origin"] == {"id": "demo-ricard", "address": "Circuit Paul Ricard, Le Castellet, France"} and got["km"] == 250
    cal = next(iter(planning.backend().events[planning.calendars_by_bu()["HISTORIC_RACING"]].values()))
    assert "Départ : Circuit Paul Ricard, Le Castellet, France" in cal["description"] and "Distance depuis Circuit Paul Ricard" in cal["description"]
    c.delete(f"/api/events/{lbid}")
    lb2 = c.post("/api/events", json=_ev(vehicles=[], externals=[])).json()["id"]          # sans départ : Lifelive
    assert c.get("/api/events", params={"from": "2026-06-01", "to": "2026-06-30"}).json()["events"][0]["origin"] is None
    c.delete(f"/api/events/{lb2}")


def test_external_contact_details_are_read_from_odoo_and_override_stored_copy():
    from fastapi.testclient import TestClient
    from app.main import app
    c = TestClient(app)
    base = c.get("/api/resources").json()["externals"]["updated_at"]
    exts = [{"partner_id": 9101, "name": "Julien Garage", "role": "saisi à la main", "email": "ancien@x.be", "phone": "1"},
            {"partner_id": 9103, "name": "Marc", "role": "autre saisie", "email": "vieux@x.be"}, {"partner_id": 5, "name": "Inconnu", "role": "gardé", "email": "garde@x.be"}]
    assert c.put("/api/resources/externals", json={"data": {"externals": exts}, "base": base}).status_code == 200
    j = c.get("/api/resources").json()
    got = {e["partner_id"]: (e["role"], e["email"], e["phone"]) for e in j["externals"]["data"]["externals"]}
    assert got == {9101: ("Mécanicien", "julien@garage-exemple.be", "+32 470 00 00 01"), 9103: ("", "", "+32 470 00 00 03"), 5: ("gardé", "garde@x.be", "")} and j["roles_from_odoo"] is True
    from app import resources
    assert resources.store().get()["data"]["externals"][0]["role"] == "saisi à la main"          # la copie enregistrée n'est pas modifiée par la lecture
    c.put("/api/resources/externals", json={"data": {"externals": []}, "base": c.get("/api/resources").json()["externals"]["updated_at"]})



def test_service_worker_lists_every_script_and_is_not_empty():
    """Le service worker ne doit jamais être vide et doit mettre en cache tous les scripts de index.html (et seulement des fichiers qui existent)."""
    import re
    from pathlib import Path
    root = Path(__file__).resolve().parents[2] / "frontend"
    sw = (root / "sw.js").read_text()
    assert re.search(r"const C = 'shell-v\d+'", sw)
    shell = set(re.findall(r"'([A-Za-z0-9_./-]+\.(?:js|css|json|png|svg))'", sw))
    scripts = set(re.findall(r'<script src="([^"]+)"', (root / "index.html").read_text()))
    assert scripts <= shell, f"absents du cache : {scripts - shell}"
    assert all((root / f).exists() for f in shell), [f for f in shell if not (root / f).exists()]


def test_maps_api_key_is_cleaned_and_rejected_when_corrupted(monkeypatch):
    import pytest
    from app import maps, settings
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", ' "AIzaSyABC123\u200b"\n')
    assert maps.api_key() == "AIzaSyABC123"
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "AIzaSyD8\uff21\uff22\u2026")
    with pytest.raises(RuntimeError, match="caractères non valides"):
        maps.api_key()


def test_maps_calls_the_documented_google_urls(monkeypatch):
    """Adresses des API Google Maps (Places New, Routes) : une faute d'URL donne un 404 que la démo ne révèle pas."""
    from app import maps, settings
    monkeypatch.setattr(settings, "PROVIDER", "odoo")
    monkeypatch.setattr(settings, "GOOGLE_MAPS_API_KEY", "AIzaSyTEST")
    seen = []

    class R:
        status_code = 200

        def __init__(self, j):
            self._j = j

        def json(self):
            return self._j

    def post(url, json, headers):
        seen.append(("POST", url, headers.get("X-Goog-Api-Key"), headers.get("X-Goog-FieldMask")))
        if url.endswith("computeRoutes"):
            return R({"routes": [{"distanceMeters": 63000, "duration": "3300s", "polyline": {"encodedPolyline": "_p~iF~ps|U_ulLnnqC"}}]})
        return R({"suggestions": [{"placePrediction": {"placeId": "ChIJ1", "text": {"text": "Circuit de Barcelona-Catalunya, Montmeló"}}}]})

    def get(url, **kw):
        seen.append(("GET", url, kw.get("headers", {}).get("X-Goog-Api-Key"), kw.get("headers", {}).get("X-Goog-FieldMask")))
        return R({"id": "ChIJ1", "displayName": {"text": "Circuit"}, "formattedAddress": "Montmeló", "location": {"latitude": 41.57, "longitude": 2.26}, "addressComponents": [{"types": ["country"], "shortText": "ES"}]})
    monkeypatch.setattr(maps, "_post", post)
    monkeypatch.setattr(maps, "_get", get)
    monkeypatch.setattr(maps, "_country_at", lambda p: "")
    assert maps.autocomplete("circuit cata") == [{"id": "ChIJ1", "text": "Circuit de Barcelona-Catalunya, Montmeló"}]
    assert maps.details("ChIJ1")["country"] == "ES"
    assert maps.route({"id": "ChIJ1", "country": "ES"})["km"] == 63
    assert seen[0][1] == "https://places.googleapis.com/v1/places:autocomplete"
    assert seen[1][1] == "https://places.googleapis.com/v1/places/ChIJ1" and "location" in seen[1][3]
    assert seen[2][1] == "https://routes.googleapis.com/directions/v2:computeRoutes" and "routes.polyline" in seen[2][3]


def test_busy_check_handles_more_than_50_resources_in_chunks(monkeypatch):
    from datetime import date
    from app import planning
    calls = []

    class R:
        status_code = 200

        def __init__(self, j):
            self._j = j

        def json(self):
            return self._j

    class S:
        def post(self, url, json, timeout):
            ids = [x["id"] for x in json["items"]]
            calls.append(len(ids))
            return R({"calendars": {i: {"busy": [{"start": "2027-04-01T00:00:00+02:00", "end": "2027-04-02T00:00:00+02:00"}] if i.endswith("7@r") else []} for i in ids}})
    g = planning.Google()
    monkeypatch.setattr(g, "_s", lambda: S())
    emails = [f"{i}@r" for i in range(120)]
    out = g.busy(emails, date(2027, 4, 1), date(2027, 4, 4))
    assert calls == [50, 50, 20] and len(out) == 120 and out["7@r"] and not out["8@r"]
    from fastapi.testclient import TestClient
    from app.main import app
    assert TestClient(app).post("/api/events/busy", json={"emails": [f"{i}@r.be" for i in range(80)], "start": "2027-04-01", "end": "2027-04-04"}).status_code == 200


def test_planning_view_is_open_to_all_users_and_hides_emails():
    import json
    from fastapi.testclient import TestClient
    from app.main import app
    from app import planning, staff
    c = TestClient(app)
    cur = staff.store().get()
    people = [{"id": "pp1", "name": "Nolan Collinet", "kind": "salarie", "google_email": "nolan@lifelive-motorsport.com", "alloc": {"HISTORIC_RACING": 100}},
              {"id": "pp2", "name": "Alain Neuville", "kind": "salarie", "google_email": "alain@lifelive-motorsport.com", "all_bus": True}]
    assert staff.store().put({"params": cur["data"]["params"], "people": people}, "t", cur["updated_at"]) is not None
    body = {"title": "Spa Classic", "bu": "HISTORIC_RACING", "confirmed": True, "start": "2026-06-20", "end": "2026-06-22", "immo_start": "2026-06-18", "immo_end": "2026-06-24",
            "place": {"id": "demo-spa", "name": "Circuit", "address": "Stavelot", "country": "BE"}, "notes": "RAS", "staff": ["nolan@lifelive-motorsport.com", "inconnu@x.be"],
            "externals": [], "vehicles": ["sprinter@resource.calendar.google.com"]}
    lbid = c.post("/api/events", json=body).json()["id"]
    r = c.get("/api/planning", params={"from": "2026-06-01", "to": "2026-06-30"})
    assert r.status_code == 200
    j = r.json()
    assert "@" not in json.dumps(j)                                                            # aucune adresse e-mail dans la réponse
    names = {x["id"]: x for x in j["resources"]}
    ev = j["events"][0]
    assert names[ev["people"][0]["rid"]]["name"] == "Nolan Collinet" and ev["other_guests"] == 1
    assert names[ev["vehicles"][0]["rid"]]["name"] == "Sprinter" and names[ev["vehicles"][0]["rid"]]["category"] == "sv"
    assert names["s:pp2"]["all_bus"] is True and names["s:pp1"]["bus"] == ["HISTORIC_RACING"]
    assert (ev["immo_start"], ev["immo_end"]) == ("2026-06-18", "2026-06-24") and ev["place"] == "Stavelot"
    assert c.get("/api/planning", params={"from": "2026-06-30", "to": "2026-06-01"}).status_code == 422
    assert c.get("/api/planning", params={"from": "2026-01-01", "to": "2026-12-31"}).status_code == 422
    c.delete(f"/api/events/{lbid}")


def test_planning_page_is_allowed_for_categories_that_tick_it():
    from app import access
    assert access.path_ok("/api/planning", {"planifier/planning"}) and not access.path_ok("/api/planning", {"overview/ca"})
    assert not access.path_ok("/api/resources", {"planifier/planning"}) and not access.path_ok("/api/events", {"planifier/planning"}) and access.path_ok("/api/events", {"planifier/events"})
    assert "planifier/planning" in access.PAGES and "planifier/events" in access.PAGES

def test_unregistered_domain_user_is_unclassified_and_sees_no_data(monkeypatch):
    import app.users as u
    monkeypatch.setattr(u.settings, "AUTH_ENABLED", True)
    assert u.role_of("nouveau@lifelive-motorsport.com") == "pending" and u.pages_of("nouveau@lifelive-motorsport.com") == set()
    assert u.identity("nouveau@lifelive-motorsport.com")["profile"] == "Non classé"
    from app import access
    assert not access.path_ok("/api/staff", set()) and not access.path_ok("/api/projection", set()) and access.path_ok("/api/session", set())
    monkeypatch.setattr(u.settings, "AUTH_ENABLED", False)
    assert u.pages_of("nouveau@lifelive-motorsport.com") is None                      # démonstration : tout reste ouvert


def test_transport_and_others_events():
    from fastapi.testclient import TestClient
    from app.main import app
    from app import planning
    c = TestClient(app)
    assert "OTHERS" in [b["id"] for b in c.get("/api/events/config").json()["bus"]]
    r = c.post("/api/events", json=_ev(title="Enlèvement étagères", bu="OTHERS", transport=True, start="2027-03-10", end="2027-03-10", immo_start="2027-03-10", immo_end="2027-03-10", vehicles=[]))
    assert r.status_code in (200, 201), r.text
    be = planning.backend()
    evs = list(be.events[planning.calendars_by_bu()["OTHERS"]].values())
    assert evs[0]["summary"] == "[TBC] [transport] Enlèvement étagères"
    got = c.get("/api/events", params={"from": "2027-03-01", "to": "2027-03-31"}).json()["events"]
    assert got[0]["title"] == "Enlèvement étagères" and got[0]["transport"] is True and got[0]["bu"] == "OTHERS"
    c.delete(f"/api/events/{got[0]['id']}")


def test_transport_time_range():
    from fastapi.testclient import TestClient
    from app.main import app
    from app import planning
    c = TestClient(app)
    base = dict(title="Enlèvement", bu="OTHERS", transport=True, start="2027-04-12", end="2027-04-12", immo_start="2027-04-12", immo_end="2027-04-12", vehicles=[])
    assert c.post("/api/events", json=_ev(**base, start_time="08:00")).status_code == 422                 # une seule heure
    assert c.post("/api/events", json=_ev(**base, start_time="10:00", end_time="09:00")).status_code == 422
    assert c.post("/api/events", json=_ev(**base, start_time="8h", end_time="09:00")).status_code == 422
    assert c.post("/api/events", json=_ev(**base, start_time="08:00", end_time="12:30")).status_code == 200
    ev = list(planning.backend().events[planning.calendars_by_bu()["OTHERS"]].values())[-1]
    assert ev["start"]["dateTime"] == "2027-04-12T08:00:00" and ev["end"]["dateTime"] == "2027-04-12T12:30:00"
    got = c.get("/api/events", params={"from": "2027-04-01", "to": "2027-04-30"}).json()["events"][0]
    assert (got["start_time"], got["end_time"], got["end"]) == ("08:00", "12:30", "2027-04-12")
    # passage journée entière -> plage horaire à la modification : le patch fusionne, l'ancienne forme doit être effacée
    c.delete(f"/api/events/{got['id']}")
    r = c.post("/api/events", json=_ev(**{**base, "transport": False}))
    assert r.status_code == 200
    got = c.get("/api/events", params={"from": "2027-04-01", "to": "2027-04-30"}).json()["events"][0]
    assert c.put(f"/api/events/{got['id']}", json=_ev(**base, start_time="06:00", end_time="10:00")).status_code == 200
    ev = list(planning.backend().events[planning.calendars_by_bu()["OTHERS"]].values())[-1]
    assert "date" not in ev["start"] and ev["start"]["dateTime"] == "2027-04-12T06:00:00"
    c.delete(f"/api/events/{got['id']}")
    r = c.post("/api/events", json=_ev(**{**base, "transport": False}, start_time="08:00", end_time="12:30"))   # hors transport : heures ignorées
    assert r.status_code == 200
    got = c.get("/api/events", params={"from": "2027-04-01", "to": "2027-04-30"}).json()["events"][0]
    assert got["start_time"] == ""
    c.delete(f"/api/events/{got['id']}")


def test_feedback_mail_to_super_users(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import feedback, mailer, users
    monkeypatch.setattr(users, "supers", lambda: ["md@lifelive-motorsport.com", "bis@lifelive-motorsport.com"])
    feedback._sent.clear(); mailer.OUTBOX.clear()
    c = TestClient(app)
    ok = {"kind": "bug", "message": "Le bouton ne répond pas", "page": "planifier/events", "title": "Planifier › Événements", "url": "https://x/#/planifier/events", "lang": "fr", "agent": "UA", "screen": "1300×900"}
    assert c.post("/api/feedback", json=ok).json() == {"sent": 2}
    m = mailer.OUTBOX[0]
    assert m["to"] == "md@lifelive-motorsport.com" and m["subject"] == "[Logbook] Bug — Planifier › Événements" and "planifier/events" in m["body"] and "Le bouton ne répond pas" in m["body"]
    import base64
    pdf = base64.b64encode(b"%PDF-1.4 x").decode()
    assert c.post("/api/feedback", json={**ok, "attachments": [{"name": "capture ecran.png", "type": "application/pdf", "data": pdf}]}).json() == {"sent": 2}
    assert mailer.OUTBOX[-1]["attachments"] == [("capture ecran.pdf", "application/pdf", 10)]
    assert c.post("/api/feedback", json={**ok, "attachments": [{"name": "x.exe", "type": "application/x-msdownload", "data": pdf}]}).status_code == 422
    assert c.post("/api/feedback", json={**ok, "attachments": [{"name": "x.pdf", "type": "application/pdf", "data": "%%%"}]}).status_code == 422
    assert c.post("/api/feedback", json={**ok, "kind": "x"}).status_code == 422
    assert c.post("/api/feedback", json={**ok, "message": "a"}).status_code == 422
    feedback._sent.clear()
    for _ in range(feedback.MAX_PER_HOUR):
        c.post("/api/feedback", json=ok)
    assert c.post("/api/feedback", json=ok).status_code == 429


def test_adjustment_measure_costs_is_accepted(monkeypatch):
    from fastapi.testclient import TestClient
    from app.main import app
    from app import adjustments
    m = adjustments.Adjustment.model_validate({"id": "x1", "label": "Imola", "bu": "HISTORIC_RACING", "kind": "meeting", "enabled": True, "sel": [{"id": 1, "name": "Imola"}], "measure": "costs"})
    assert m.measure == "costs"


def test_event_notification_choice():
    from fastapi.testclient import TestClient
    from app.main import app
    from app import planning
    c = TestClient(app)
    lbid = c.post("/api/events", json=_ev(title="Passé", start="2026-01-10", end="2026-01-11", immo_start="2026-01-10", immo_end="2026-01-11", notify=False)).json()["id"]
    sent = planning.backend().sent
    assert [x for x in sent if x[0] == "insert"][-1][2] is False                                    # pas d'invitation à la création si on décoche
    assert c.put(f"/api/events/{lbid}", json=_ev(title="Passé", start="2026-01-10", end="2026-01-11", immo_start="2026-01-10", immo_end="2026-01-11", staff=["a@lifelive-motorsport.com", "b@lifelive-motorsport.com"], notify=False)).status_code == 200
    assert [x for x in sent if x[0] == "patch"][-1][2] is False
    assert c.put(f"/api/events/{lbid}", json=_ev(title="Passé", start="2026-01-10", end="2026-01-11", immo_start="2026-01-10", immo_end="2026-01-11")).status_code == 200
    assert [x for x in sent if x[0] == "patch"][-1][2] is True                                      # par défaut on prévient
    c.delete(f"/api/events/{lbid}")
