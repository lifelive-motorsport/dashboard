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
