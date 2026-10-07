from datetime import date

from fastapi.testclient import TestClient

from app import expenses
from app.main import app

LINES = [
    {"code": "611000", "name": "Entretien", "total": 900.0, "by_month": {"2026-01": 400.0, "2026-02": 500.0}, "partners": {1: {"name": "A", "amount": 900.0, "by_month": {"2026-01": 400.0, "2026-02": 500.0}}}},
    {"code": "612000", "name": "Électricité", "total": 600.0, "by_month": {"2026-01": 300.0, "2026-02": 300.0}, "partners": {2: {"name": "B", "amount": 600.0, "by_month": {"2026-01": 300.0, "2026-02": 300.0}}}},
    {"code": "612050", "name": "Marketing", "total": 800.0, "by_month": {"2026-01": 800.0}, "partners": {}},             # compte marketing : traité ailleurs
    {"code": "613000", "name": "Honoraires", "total": 5000.0, "by_month": {"2026-01": 4000.0, "2026-02": 1000.0},          # pas dans la proposition de départ
     "partners": {7: {"name": "ADC St-Vith", "amount": 800.0, "by_month": {"2026-01": 400.0, "2026-02": 400.0}}, 8: {"name": "Indépendant X", "amount": 4200.0, "by_month": {"2026-01": 3600.0, "2026-02": 600.0}}}},
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
    d = expenses.kind_view(LINES, {"saved": False, "selected": {}}, 2026, "general", today=date(2026, 2, 28))
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


def test_account_by_supplier_keeps_only_chosen_suppliers():
    cfg = {"saved": True, "selected": {"613000": "partners", "612000": "general"}, "partners": {"613000": {"7": "general"}}}
    v = expenses.accounts_view(LINES, cfg, 2026)
    acc = next(a for a in v["accounts"] if a["code"] == "613000")
    assert acc["kind"] == "partners" and [(p["id"], p["kind"]) for p in acc["partners"]] == [("8", None), ("7", "general")]       # triés par montant ; l'indépendant reste de côté
    g = expenses.kind_view(LINES, cfg, 2026, "general")
    assert g["total"] == 1400 and [a["code"] for a in g["accounts"]] == ["613000", "612000"]                                   # 600 + 800 (ADC seulement)
    assert g["series"] == [{"month": "2026-01", "amount": 700.0}, {"month": "2026-02", "amount": 700.0}]
    assert expenses.kind_view(LINES, cfg, 2026, "vehicle")["empty"]


def test_allocation_view_supports_revenue_and_percentage_keys():
    g = expenses.kind_view(LINES, {"saved": False, "selected": {}}, 2026, "general")             # 1 500 € de frais généraux
    a = expenses.allocation_view(g, 300000.0, 100000.0, {"key_mode": "revenue", "xc_pct": 40})
    assert a["shares"]["revenue"] == {"XC": 0.75, "CARS": 0.25} and a["amounts"]["revenue"] == {"XC": 1125.0, "CARS": 375.0}
    assert a["shares"]["pct"] == {"XC": 0.4, "CARS": 0.6} and a["amounts"]["pct"] == {"XC": 600.0, "CARS": 900.0} and a["key_mode"] == "revenue"
    zero = expenses.allocation_view(g, 0.0, 0.0, {})
    assert zero["shares"]["revenue"] == {"XC": 0.5, "CARS": 0.5} and zero["xc_pct"] == 50                  # sans CA : 50/50, % par défaut 50


def test_key_endpoint_is_admin_only_and_keeps_account_choices(monkeypatch):
    import app.adjustments as adj
    import app.main as m
    monkeypatch.setattr(expenses, "_store", expenses.Store())
    monkeypatch.setattr(adj.settings, "AUTH_ENABLED", True)
    monkeypatch.setattr(adj.settings, "ADMIN_EMAILS", ["md@x.be"])
    try:
        app.dependency_overrides[m.require_user] = lambda: "actionnaire@x.be"
        c = TestClient(app)
        assert c.put("/api/expenses/key", json={"key_mode": "pct", "xc_pct": 30}).status_code == 403
        assert c.get("/api/expenses/allocation?year=2026").json()["key_mode"] == "revenue"
        app.dependency_overrides[m.require_user] = lambda: "md@x.be"
        assert c.put("/api/expenses/config", json={"data": {"selected": {"611000": "general"}}, "base": None}).status_code == 200
        r = c.put("/api/expenses/key", json={"key_mode": "pct", "xc_pct": 30})
        assert r.status_code == 200
        al = c.get("/api/expenses/allocation?year=2026").json()
        assert al["key_mode"] == "pct" and al["xc_pct"] == 30 and [a["code"] for a in al["accounts"]] == ["611000"]       # le choix des comptes est conservé
        assert c.put("/api/expenses/key", json={"key_mode": "pct", "xc_pct": 130}).status_code == 422
        # enregistrer à nouveau les comptes ne remet pas la clé à zéro
        cur = c.get("/api/expenses/accounts?year=2026").json()
        assert c.put("/api/expenses/config", json={"data": {"selected": {"611000": "general", "612000": "general"}}, "base": cur["updated_at"]}).status_code == 200
        assert c.get("/api/expenses/allocation?year=2026").json()["xc_pct"] == 30
    finally:
        app.dependency_overrides.clear()


def test_month_lines_keep_chosen_accounts_and_suppliers_and_rank_by_amount():
    raw = [{"code": "611000", "name": "Entretien", "date": "2026-07-03", "amount": 20000.0, "partner_id": 1, "partner": "Bailleur", "move": "F1", "label": "Loyer annuel"},
           {"code": "612000", "name": "Électricité", "date": "2026-07-10", "amount": 300.0, "partner_id": 2, "partner": "Elec", "move": "F2", "label": "x"},
           {"code": "613000", "name": "Honoraires", "date": "2026-07-11", "amount": 900.0, "partner_id": 7, "partner": "ADC St-Vith", "move": "F3", "label": "Compta"},
           {"code": "613000", "name": "Honoraires", "date": "2026-07-12", "amount": 4000.0, "partner_id": 8, "partner": "Indépendant X", "move": "F4", "label": "Prestation"},
           {"code": "604010", "name": "Achats XC", "date": "2026-07-12", "amount": 99999.0, "partner_id": 9, "partner": "Z", "move": "F5", "label": "hors périmètre"}]
    cfg = {"saved": True, "selected": {"611000": "general", "612000": "general", "613000": "partners"}, "partners": {"613000": {"7": "general"}}}
    r = expenses.month_lines(raw, cfg, "general", "2026-07")
    assert [l["move"] for l in r["lines"]] == ["F1", "F3", "F2"] and r["total"] == 21200 and r["count"] == 3


def test_vehicle_accounts_are_proposed_and_split_by_vehicle_and_nature():
    lines = [{"code": "615021", "name": "Carburant Util. CITAN", "total": 3000.0, "by_month": {"2026-01": 3000.0}, "partners": {}},
             {"code": "615022", "name": "Assurance Util. CITAN", "total": 800.0, "by_month": {"2026-01": 800.0}, "partners": {}},
             {"code": "615031", "name": "Carburant Util. SPRINTER", "total": 5000.0, "by_month": {"2026-01": 5000.0}, "partners": {}},
             {"code": "615999", "name": "Divers véhicules", "total": 100.0, "by_month": {"2026-01": 100.0}, "partners": {}}]
    assert expenses.suggestion("615021") == "vehicle" and expenses.suggestion("611000") == "general"
    assert expenses.split_vehicle_account("Carburant Util. CITAN") == ("CITAN", "Carburant") and expenses.split_vehicle_account("Divers")[0] == "(non classé)"
    v = expenses.vehicles_view(lines, {"saved": False, "selected": {}}, 2026)
    assert v["total"] == 8900 and v["types"][0] == "Carburant" and [x["vehicle"] for x in v["vehicles"]] == ["SPRINTER", "CITAN", "(non classé)"]
    citan = next(x for x in v["vehicles"] if x["vehicle"] == "CITAN")
    assert citan["types"] == {"Carburant": 3000.0, "Assurance": 800.0}
    assert expenses.kind_view(lines, {"saved": False, "selected": {}}, 2026, "general")["empty"]            # les 615 ne tombent pas dans les frais généraux


def test_fuel_scope_uses_all_615_accounts_even_when_classed_as_general_expenses():
    lines = [{"code": "615021", "name": "Carburant Util. CITAN", "total": 3000.0, "by_month": {"2026-01": 3000.0}, "partners": {}},
             {"code": "612000", "name": "Électricité", "total": 600.0, "by_month": {"2026-01": 600.0}, "partners": {}}]
    cfg = {"saved": True, "selected": {"615021": "general"}}
    assert expenses.vehicles_view(lines, cfg, 2026)["empty"]
    v = expenses.vehicles_view(lines, cfg, 2026, "all615")
    assert v["total"] == 3000 and v["vehicles"][0]["types"] == {"Carburant": 3000.0}


def test_rent_account_is_excluded_from_general_expenses_and_listed_apart():
    lines = [{"code": "611010", "name": "Loyer Batiment", "total": 21000.0, "by_month": {"2026-07": 21000.0}, "partners": {}},
             {"code": "611011", "name": "Entr. Batiment", "total": 1350.0, "by_month": {"2026-07": 1350.0}, "partners": {}}]
    assert expenses.family("611010", "Loyer Batiment") == "excluded"
    g = expenses.kind_view(lines, {"saved": False, "selected": {}}, 2026, "general")
    assert g["total"] == 1350 and [a["code"] for a in g["accounts"]] == ["611011"]
    assert [a["code"] for a in expenses.accounts_view(lines, {"saved": False, "selected": {}}, 2026)["accounts"]] == ["611011"]
    assert expenses.accounts_view(lines, {}, 2026)["elsewhere"]["excluded"] == 21000
    x = expenses.excluded_view([{"code": "611010", "name": "Loyer Batiment", "date": "2026-07-31", "amount": 21000.0, "move": "DIV/2026/07/0001", "label": "Loyer 01-07/26"}])
    assert x["total"] == 21000 and x["moves"][0]["move"] == "DIV/2026/07/0001"


def test_months_elapsed_include_the_fraction_of_the_current_month_and_smooth_lumpy_costs():
    assert expenses.closed_months(2026, date(2026, 10, 7)) == (9.0, "2026-09") and expenses.closed_months(2026, date(2026, 4, 30)) == (4.0, "2026-04")
    assert expenses.months_elapsed(2025, date(2026, 10, 7)) == 12.0
    one_off = [{"code": "615014", "name": "Entretien Util. TRUCK", "total": 2000.0, "by_month": {"2026-03": 2000.0}, "partners": {}}]
    assert expenses.kind_view(one_off, {"saved": True, "selected": {"615014": "vehicle"}}, 2026, "vehicle", today=date(2026, 4, 30))["monthly_avg"] == 500   # lissé sur 4 mois, pas 2000
    assert expenses.accounts_view(one_off, {}, 2026, today=date(2026, 4, 30))["months_elapsed"] == 4.0
    partial = [{"code": "612000", "name": "Électricité", "total": 1300.0, "by_month": {"2026-08": 600.0, "2026-09": 600.0, "2026-10": 100.0}, "partners": {}}]
    k = expenses.kind_view(partial, {"saved": True, "selected": {"612000": "general"}}, 2026, "general", today=date(2026, 10, 7))
    assert [x["month"] for x in k["series"]] == ["2026-08", "2026-09"] and k["last_closed"] == "2026-09" and [x["month"] for x in k["all_months"]] == ["2026-08", "2026-09", "2026-10"]             # octobre (incomplet) n'est pas tracé
    assert k["total"] == 1300 and round(k["monthly_avg"], 2) == round(1200 / 9, 2) and round(k["projected"], 2) == 1600     # moyenne sur les 9 mois clos


def test_split_vehicle_account_sans_util():
    from app.expenses import split_vehicle_account as f
    assert f("Carburant Util. CITAN") == ("CITAN", "Carburant")
    assert f("Assurance Brian James, Respo & Saris") == ("Brian James, Respo & Saris", "Assurance")
    assert f("Entr. et repar. Semi PAC") == ("Semi PAC", "Entr. et repar.")
    assert f("Assurance Quad Kodiak") == ("Quad Kodiak", "Assurance")
    assert f("Autres frais Semi A6J") == ("Semi A6J", "Autres frais")


def test_links_config_roundtrip_and_preserved():
    c = expenses.Config.model_validate({"links": {" SEMI PAC ": " (TR)-LLM-PKG-Pacton Trailer #1 (1) ", "X": ""}})
    assert c.links == {"SEMI PAC": "(TR)-LLM-PKG-Pacton Trailer #1 (1)"}


def test_vehicles_view_merges_linked_accounts():
    lines = [{"code": "615100", "name": "Assurance Quad Kodiak", "total": 97.0, "by_month": {"2026-03": 97.0}},
             {"code": "615101", "name": "Taxes YAMAHA/KODIAK 700", "total": 49.0, "by_month": {"2026-04": 49.0}}]
    cfg = {"selected": {"615100": "vehicle", "615101": "vehicle"}, "saved": True, "links": {"YAMAHA/KODIAK 700": "Quad Kodiak"}}
    out = expenses.vehicles_view(lines, cfg, 2026)
    assert [v["vehicle"] for v in out["vehicles"]] == ["Quad Kodiak"]
    assert out["vehicles"][0]["total"] == 146.0 and out["vehicles"][0]["merged"] == ["YAMAHA/KODIAK 700"]
    assert out["vehicles"][0]["types"] == {"Assurance": 97.0, "Taxes": 49.0}
