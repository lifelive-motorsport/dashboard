from fastapi.testclient import TestClient

from app import expenses
from app.main import app

LINES = [
    {"code": "611000", "name": "Entretien", "total": 900.0, "by_month": {"2026-01": 400.0, "2026-02": 500.0}, "partners": {1: {"name": "A", "amount": 900.0}}},
    {"code": "612000", "name": "Électricité", "total": 600.0, "by_month": {"2026-01": 300.0, "2026-02": 300.0}, "partners": {2: {"name": "B", "amount": 600.0}}},
    {"code": "612050", "name": "Marketing", "total": 800.0, "by_month": {"2026-01": 800.0}, "partners": {}},             # compte marketing : traité ailleurs
    {"code": "613000", "name": "Honoraires", "total": 5000.0, "by_month": {"2026-01": 5000.0}, "partners": {}},          # pas dans la proposition de départ
    {"code": "61300000", "name": "old - Honoraires", "total": 100.0, "by_month": {"2026-01": 100.0}, "partners": {}},
    {"code": "604010", "name": "Achats XC", "total": 9000.0, "by_month": {"2026-01": 9000.0}, "partners": {}},
    {"code": "620000", "name": "Rémunérations", "total": 7000.0, "by_month": {"2026-01": 7000.0}, "partners": {}},
]


def test_families_and_default_suggestion():
    assert [expenses.family(a["code"], a["name"]) for a in LINES] == ["candidate", "candidate", "marketing", "candidate", "old", "bu", "staff"]
    cfg = {"saved": False, "selected": {}}
    v = expenses.accounts_view(LINES, cfg, 2026)
    assert [(a["code"], a["kind"]) for a in v["accounts"]] == [("611000", "general"), ("612000", "general"), ("613000", None)]      # 613 non proposé, marketing et old absents
    assert v["elsewhere"] == {"marketing": 800, "bu": 9000, "staff": 7000}


def test_saved_selection_overrides_default_and_vehicles_are_separate():
    cfg = {"saved": True, "selected": {"611000": "vehicle", "613000": "general"}}
    g = expenses.kind_view(LINES, cfg, 2026, "general")
    assert g["total"] == 5000 and [a["code"] for a in g["accounts"]] == ["613000"] and g["configured"]
    v = expenses.kind_view(LINES, cfg, 2026, "vehicle")
    assert v["total"] == 900 and v["series"] == [{"month": "2026-01", "amount": 400.0}, {"month": "2026-02", "amount": 500.0}]
    d = expenses.kind_view(LINES, {"saved": False, "selected": {}}, 2026, "general")
    assert d["total"] == 1500 and d["months"] == 2 and d["monthly_avg"] == 750 and d["projected"] == 9000 and [s["name"] for s in d["suppliers"]] == ["A", "B"]


def test_expenses_api_in_demo_and_admin_only_saving(monkeypatch):
    import app.adjustments as adj
    import app.main as m
    monkeypatch.setattr(expenses, "_store", expenses.Store())
    monkeypatch.setattr(adj.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(adj.settings, "ADMIN_EMAILS", ["md@x.be"])
    try:
        app.dependency_overrides[m.require_user] = lambda: "actionnaire@x.be"
        c = TestClient(app)
        r = c.get("/api/expenses/accounts?year=2026").json()
        assert r["can_edit"] is False and any(a["kind"] == "general" for a in r["accounts"])
        assert c.put("/api/expenses/config", json={"data": {"selected": {}}, "base": None}).status_code == 403
        app.dependency_overrides[m.require_user] = lambda: "md@x.be"
        assert c.put("/api/expenses/config", json={"data": {"selected": {"611000": "vehicle"}}, "base": None}).status_code == 200
        assert c.put("/api/expenses/config", json={"data": {"selected": {}}, "base": None}).status_code == 409                 # base périmée
        assert c.put("/api/expenses/config", json={"data": {"selected": {"abc": "general"}}, "base": r["updated_at"]}).status_code == 422
        g = c.get("/api/expenses/general?year=2026&kind=vehicle").json()
        assert g["configured"] and [a["code"] for a in g["accounts"]] == ["611000"]
    finally:
        app.dependency_overrides.clear()
