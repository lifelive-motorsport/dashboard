from datetime import date

from app.providers.odoo import OdooProvider


def make(rows, partners=None, tags=None, invoices=None, lines=None):
    """Fournisseur simulé : rows = CA par client/compte ; invoices = factures ouvertes ; lines = lignes de CA de ces factures."""
    p = OdooProvider.__new__(OdooProvider)  # sans client HTTP

    def grouped(domain, groupby):
        return (lines or []) if groupby == ["move_id", "account_id"] else rows
    p._grouped = grouped

    def call(model, method, **kw):
        if model == "account.move":
            return invoices or []
        if partners is None:
            raise RuntimeError("accès refusé")
        src = partners if model == "res.partner" else [{"id": i, "name": n} for i, n in (tags or {}).items()]
        return [x for x in src if x["id"] in kw["ids"]]
    p._call = call
    return p


def test_top_clients_by_bu_and_total():
    rows = [
        {"partner_id": [1, "A"], "account_id": [10, "700010 CA XC Manufacturer"], "balance:sum": -100.0},
        {"partner_id": [1, "A"], "account_id": [11, "700040 CA Historic Racing"], "balance:sum": -50.0},
        {"partner_id": [2, "B"], "account_id": [10, "700010 CA XC Manufacturer"], "balance:sum": -120.0},
        {"partner_id": [2, "B"], "account_id": [12, "707010 VENTE ASSET XC"], "balance:sum": -999.0},  # hors CA
        {"partner_id": [3, "C"], "account_id": [13, "70000000 old - Ventes"], "balance:sum": -999.0},  # old
    ]
    r = make(rows).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [c["name"] for c in r["total"]] == ["A", "B"]
    assert (r["XC"][0]["name"], r["XC"][0]["ca"]) == ("B", 120)
    assert [(c["name"], c["ca"]) for c in r["HISTORIC_RACING"]] == [("A", 50)]
    assert all(c["name"] != "C" for k, board in r.items() if not k.startswith("_") for c in board)


import pytest
from app import settings


@pytest.mark.parametrize("bad", ["", "clé avec accent", "deux mots", "x" * 300, "ligne1\nligne2"])
def test_invalid_api_key_is_rejected_without_leaking_it(monkeypatch, bad):
    monkeypatch.setattr(settings, "ODOO_API_KEY", bad)
    with pytest.raises(RuntimeError) as e:
        OdooProvider()
    assert bad.strip() == "" or bad.strip() not in str(e.value)


def test_valid_api_key_is_accepted_and_stripped(monkeypatch):
    monkeypatch.setattr(settings, "ODOO_API_KEY", "abc123def456\n")
    monkeypatch.setattr(settings, "ODOO_URL", "https://x.odoo.com")
    assert OdooProvider()._http.headers["authorization"] == "bearer abc123def456"


def _row(pid, name, acc, amount):
    return {"partner_id": [pid, name], "account_id": [1, acc], "balance:sum": -amount}


def _partner(pid, name, com=None, cats=()):
    return {"id": pid, "display_name": name, "commercial_partner_id": [com or pid, name], "category_id": list(cats)}


def test_clients_regrouped_by_odoo_tag_case_insensitive():
    rows = [_row(1, "Alpha SA", "700010 CA XC", 100), _row(2, "Alpha GmbH", "700040 CA HR", 50), _row(3, "Beta", "700010 CA XC", 120)]
    partners = [_partner(1, "Alpha SA", cats=[10]), _partner(2, "Alpha GmbH", cats=[11]), _partner(3, "Beta")]
    r = make(rows, partners, {10: "regroup_client=Groupe Alpha", 11: "REGROUP_CLIENT = Groupe Alpha"}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [(c["name"], c["ca"]) for c in r["total"]] == [("Groupe Alpha", 150), ("Beta", 120)]
    assert r["_meta"] == {"grouping": True, "groups": 1, "open": True}
    assert [(c["name"], c["ca"]) for c in r["HISTORIC_RACING"]] == [("Groupe Alpha", 50)]


def test_contacts_of_same_company_are_merged_and_tag_on_company_applies():
    rows = [_row(1, "Alpha SA, Jean", "700010 CA XC", 30), _row(2, "Alpha SA, Marie", "700010 CA XC", 20)]
    partners = [_partner(1, "Alpha SA, Jean", com=9), _partner(2, "Alpha SA, Marie", com=9), _partner(9, "Alpha SA", cats=[10])]
    r = make(rows, partners, {10: "regroup_client=Groupe A"}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [(c["name"], c["ca"]) for c in r["total"]] == [("Groupe A", 50)]
    r2 = make(rows, [_partner(1, "x", com=9), _partner(2, "y", com=9), _partner(9, "Alpha SA")], {}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [(c["name"], c["ca"]) for c in r2["total"]] == [("Alpha SA", 50)]  # sans étiquette : fusion par société


def test_other_tags_are_ignored():
    rows = [_row(1, "Alpha", "700010 CA XC", 10)]
    r = make(rows, [_partner(1, "Alpha", cats=[5])], {5: "VIP"}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [(c["name"], c["ca"]) for c in r["total"]] == [("Alpha", 10)] and r["_meta"]["groups"] == 0


def test_grouping_failure_falls_back_to_raw_names():
    rows = [_row(1, "Alpha", "700010 CA XC", 10), _row(2, "Beta", "700010 CA XC", 20)]
    r = make(rows, None).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [c["name"] for c in r["total"]] == ["Beta", "Alpha"] and r["_meta"]["grouping"] is False


def _shop_provider(langs=("en_US", "fr_BE"), fail_read=False):
    p = OdooProvider.__new__(OdooProvider)
    seen = {}

    def call(model, method, **kw):
        if model == "sale.order" and method == "search_read":
            return [{"website_id": [1, "Lifelive Motorsport"], "date_order": "2026-01-10 09:00:00", "amount_untaxed": 100.0},
                    {"website_id": [1, "Lifelive Motorsport"], "date_order": "2026-01-20 09:00:00", "amount_untaxed": 300.0},
                    {"website_id": [1, "Lifelive Motorsport"], "date_order": "2026-03-02 09:00:00", "amount_untaxed": 50.0}]
        if model == "sale.order":
            return [{"website_id": [1, "Lifelive Motorsport"], "amount_untaxed:sum": 1000.0, "__count": 10}]
        if model == "sale.order.line":
            return [{"product_id": [i, f"[{i}] Name {i}"], "price_subtotal:sum": 100.0 * (4 - i), "product_uom_qty:sum": 2.0 * i} for i in (1, 2, 3)] \
                + [{"product_id": False, "price_subtotal:sum": 5.0, "product_uom_qty:sum": 1.0}]
        if model == "res.lang":
            return [{"code": c} for c in langs]
        if model == "product.product":
            seen["context"] = kw.get("context")
            if fail_read:
                raise RuntimeError("boom")
            return [{"id": i, "display_name": f"[{i}] Nom {i}"} for i in kw["ids"]]
    p._call = call
    return p, seen


def test_webshop_top_products_in_french_with_share_and_units():
    p, seen = _shop_provider()
    (w,) = p.webshops(date(2026, 1, 1), date(2026, 9, 4), top=2)
    assert seen["context"]["lang"] == "fr_BE" and seen["context"]["active_test"] is False
    assert [x["name"] for x in w["products"]] == ["[1] Nom 1", "[2] Nom 2"]            # français, tri par valeur
    assert [x["value"] for x in w["products"]] == [300, 200] and [x["units"] for x in w["products"]] == [2.0, 4.0]
    assert round(w["products"][0]["share"], 4) == round(300 / 600, 4)               # part du total des produits
    assert w["products_total"] == {"value": 600, "units": 12.0, "count": 3}
    assert w["name"] == "Webshop XC" and w["avg_basket"] == 100.0


def test_webshop_french_falls_back_when_translation_fails_or_missing():
    p, _ = _shop_provider(fail_read=True)
    assert p.webshops(date(2026, 1, 1), date(2026, 9, 4), top=1)[0]["products"][0]["name"] == "[1] Name 1"
    p2, seen2 = _shop_provider(langs=("en_US",))
    assert p2.webshops(date(2026, 1, 1), date(2026, 9, 4), top=1)[0]["products"][0]["name"] == "[1] Name 1"
    assert "context" not in seen2   # aucune langue française installée : pas d'appel de traduction


def test_balance_sheet_open_invoices_and_credit_notes_posted_only():
    p = OdooProvider.__new__(OdooProvider)
    domains = []

    def call(model, method, **kw):
        dom = kw["domain"]; domains.append((model, dom))
        assert ("state", "=", "posted") in dom                        # jamais de brouillons
        assert ("payment_state", "in", ["not_paid", "partial"]) in dom
        assert ("date", ">=", "2026-01-01") in dom and ("date", "<=", "2026-12-31") in dom   # année de référence seulement
        vendor = ("move_type", "in", ["in_invoice", "in_refund"]) in dom   # avoirs inclus
        return [{"amount_residual_signed:sum": -150_000.0 if vendor else 197_511.0}]
    p._call = call
    p._grouped = lambda domain, groupby: [{"balance:sum": 7_895.0}]
    assert p.balance_sheet(2026) == {"year": 2026, "receivables": 197_511.0, "payables": 150_000.0, "cash": 7_895.0}
    assert all(m == "account.move" for m, _ in domains)
    assert ("move_type", "in", ["out_invoice", "out_refund"]) in [d for _, d in domains for d in d]


def test_client_names_are_normalized_for_display_only():
    rows = [_row(1, "TÜRKİYE OTOMOBİL SPORLARI FEDERASYONU (TOSFED)", "700010 CA XC", 100), _row(2, "Eduardo Salorio Instalaciones sl", "700010 CA XC", 50)]
    r = make(rows, [_partner(1, "TÜRKİYE OTOMOBİL SPORLARI FEDERASYONU (TOSFED)"), _partner(2, "Eduardo Salorio Instalaciones sl")], {}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [c["name"] for c in r["total"]] == ["Türkiye Otomobil Sporlari Federasyonu (TOSFED)", "Eduardo Salorio Instalaciones SL"]


def test_top_clients_default_is_fifteen_and_sorted():
    rows = [_row(i, f"Client {i:02d}", "700010 CA XC", 1000 - i) for i in range(1, 21)]
    r = make(rows, [_partner(i, f"Client {i:02d}") for i in range(1, 21)], {}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert len(r["total"]) == 15 and len(r["XC"]) == 15
    assert [c["ca"] for c in r["total"]] == sorted((c["ca"] for c in r["total"]), reverse=True)


def test_open_balance_per_client_split_by_bu_pro_rata_of_invoice_revenue():
    rows = [_row(1, "Alpha", "700010 CA XC", 600), _row(1, "Alpha", "700040 CA HR", 400), _row(2, "Beta", "700010 CA XC", 100)]
    invoices = [{"id": 11, "partner_id": [1, "Alpha"], "amount_residual_signed": 1210.0},      # facture TTC 1 210 €, 600 XC + 400 HR
                {"id": 12, "partner_id": [2, "Beta"], "amount_residual_signed": 0.0}]
    lines = [{"move_id": [11, "F1"], "account_id": [1, "700010 CA XC"], "balance:sum": -600.0},
             {"move_id": [11, "F1"], "account_id": [2, "700040 CA HR"], "balance:sum": -400.0},
             {"move_id": [12, "F2"], "account_id": [1, "700010 CA XC"], "balance:sum": -100.0}]
    r = make(rows, [_partner(1, "Alpha"), _partner(2, "Beta")], {}, invoices, lines).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    by = {c["name"]: c["open"] for c in r["total"]}
    assert by == {"Alpha": 1210, "Beta": 0}
    assert {c["name"]: c["open"] for c in r["XC"]}["Alpha"] == 726           # 60 % du reste dû
    assert {c["name"]: c["open"] for c in r["HISTORIC_RACING"]}["Alpha"] == 484
    assert r["_open_totals"] == {"total": 1210, "XC": 726, "HISTORIC_RACING": 484, "CARS": 484}


def test_open_balance_unavailable_does_not_break_the_ranking():
    rows = [_row(1, "Alpha", "700010 CA XC", 600)]
    p = make(rows, [_partner(1, "Alpha")], {})
    orig = p._call
    p._call = lambda model, method, **kw: (_ for _ in ()).throw(RuntimeError("refusé")) if model == "account.move" else orig(model, method, **kw)
    r = p.top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert r["total"][0]["ca"] == 600 and r["total"][0]["open"] is None and r["_meta"]["open"] is False


def test_credit_note_reduces_open_balance():
    rows = [_row(1, "Alpha", "700010 CA XC", 500)]
    invoices = [{"id": 21, "partner_id": [1, "Alpha"], "amount_residual_signed": 1000.0}, {"id": 22, "partner_id": [1, "Alpha"], "amount_residual_signed": -200.0}]
    lines = [{"move_id": [21, "F"], "account_id": [1, "700010 CA XC"], "balance:sum": -826.45}, {"move_id": [22, "A"], "account_id": [1, "700010 CA XC"], "balance:sum": 165.29}]
    r = make(rows, [_partner(1, "Alpha")], {}, invoices, lines).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert r["total"][0]["open"] == 800


def _srow(pid, name, acc, amount):
    return {"partner_id": [pid, name], "account_id": [1, acc], "balance:sum": amount}


def test_suppliers_ranked_by_bu_from_account_of_each_invoice_line():
    rows = [_srow(1, "Four 1", "602010 FRAIS XC Manufacturer", 300), _srow(1, "Four 1", "604040 ACH. MARCH. Historic Racing", 200),
            _srow(1, "Four 1", "615001 Carburant Véhicules loués", 100), _srow(2, "Four 2", "604010 ACH. MARCH. XC Manufacturer", 500),
            _srow(2, "Four 2", "604010 ACH. MARCH. XC Manufacturer", -100),                    # avoir : réduit les achats
            _srow(3, "Four 3", "604099 FRAIS REFACTURÉS", 50)]
    r = make(rows, [_partner(1, "Four 1"), _partner(2, "Four 2"), _partner(3, "Four 3")], {}).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    names = lambda k: [(c["name"], c["ca"]) for c in r[k]]
    assert names("total") == [("Four 1", 600), ("Four 2", 400), ("Four 3", 50)]
    assert names("XC") == [("Four 2", 400), ("Four 1", 300)]
    assert names("HISTORIC_RACING") == [("Four 1", 200)]
    assert names("HORS_BU") == [("Four 1", 100), ("Four 3", 50)]          # 615 et 604099 : pas de BU
    assert r["_totals"]["total"] == 1050 and r["_totals"]["XC"] == 700


def test_suppliers_query_only_posted_bill_lines_not_taxes():
    seen = {}
    p = make([], [], {})
    p._grouped = lambda domain, groupby: seen.update(domain=domain, groupby=groupby) or []
    p.top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert ("display_type", "=", "product") in seen["domain"] and ("parent_state", "=", "posted") in seen["domain"]
    assert ("move_id.move_type", "in", ["in_invoice", "in_refund"]) in seen["domain"] and seen["groupby"] == ["partner_id", "account_id"]


def test_supplier_open_balance_is_debt_split_by_bu_of_bill_lines():
    rows = [_srow(1, "Four 1", "602010 FRAIS XC Manufacturer", 600), _srow(1, "Four 1", "615001 Carburant", 400)]
    invoices = [{"id": 31, "partner_id": [1, "Four 1"], "amount_residual_signed": -1210.0}]            # facture fournisseur : reste dû négatif
    lines = [{"move_id": [31, "B1"], "account_id": [1, "602010 FRAIS XC Manufacturer"], "balance:sum": 600.0},
             {"move_id": [31, "B1"], "account_id": [2, "615001 Carburant"], "balance:sum": 400.0}]
    r = make(rows, [_partner(1, "Four 1")], {}, invoices, lines).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert r["total"][0]["open"] == 1210 and r["XC"][0]["open"] == 726 and r["HORS_BU"][0]["open"] == 484
    assert r["_open_totals"] == {"total": 1210, "XC": 726, "HORS_BU": 484, "CARS": 0}


def test_supplier_grouping_uses_its_own_tag_prefix():
    rows = [_srow(1, "Four 1", "604010 ACH. MARCH. XC", 100), _srow(2, "Four 2", "604010 ACH. MARCH. XC", 50)]
    partners = [_partner(1, "Four 1", cats=[10, 12]), _partner(2, "Four 2", cats=[11])]
    tags = {10: "regroup_fournisseur=Groupe F", 11: "regroup_fournisseur=Groupe F", 12: "regroup_client=Pas pour les fournisseurs"}
    r = make(rows, partners, tags).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert [(c["name"], c["ca"]) for c in r["total"]] == [("Groupe F", 150)]


def test_suppliers_only_expense_accounts_assets_and_old_accounts_excluded():
    rows = [_srow(1, "Four 1", "602010 FRAIS XC Manufacturer", 300), _srow(1, "Four 1", "241000 Matériel et mobilier", 5000),   # immobilisation
            _srow(2, "Four 2", "60400000 old - ACH. MDISES PIECES", 999), _srow(3, "Four 3", "615001 Carburant", 40),
            _srow(4, "Four 4", "300000 Stock marchandises", 777)]
    r = make(rows, [_partner(i, f"Four {i}") for i in range(1, 5)], {}).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert [(c["name"], c["ca"]) for c in r["total"]] == [("Four 1", 300), ("Four 3", 40)]
    assert r["_totals"]["total"] == 340 and "HORS_PERIMETRE" not in r


def test_supplier_query_filters_expense_accounts_in_the_domain():
    seen = {}
    p = make([], [], {})
    p._grouped = lambda domain, groupby: seen.update(domain=domain) or []
    p.top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert ("account_id.code", "=like", "6%") in seen["domain"]


def test_open_balance_of_mixed_bill_counts_only_its_expense_share():
    rows = [_srow(1, "Four 1", "602010 FRAIS XC Manufacturer", 600)]
    invoices = [{"id": 41, "partner_id": [1, "Four 1"], "amount_residual_signed": -1210.0}]
    lines = [{"move_id": [41, "B"], "account_id": [1, "602010 FRAIS XC Manufacturer"], "balance:sum": 600.0},
             {"move_id": [41, "B"], "account_id": [2, "241000 Matériel"], "balance:sum": 400.0}]          # 40 % de la facture = immobilisation
    r = make(rows, [_partner(1, "Four 1")], {}, invoices, lines).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert r["total"][0]["open"] == 726 and r["_open_totals"] == {"total": 726, "XC": 726, "CARS": 0}


def test_suppliers_cars_view_aggregates_cars_bus_without_double_counting_in_total():
    rows = [_srow(1, "Four 1", "604020 ACH. MARCH. Modern Rally", 100), _srow(1, "Four 1", "604040 ACH. MARCH. Historic Racing", 200),
            _srow(2, "Four 2", "603030 SS TRAIT. Historic Rally", 50), _srow(2, "Four 2", "604010 ACH. MARCH. XC Manufacturer", 400),
            _srow(3, "Four 3", "604050 ACH. MARCH. CARS", 30), _srow(3, "Four 3", "615001 Carburant", 20)]
    r = make(rows, [_partner(i, f"Four {i}") for i in (1, 2, 3)], {}).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert [(c["name"], c["ca"]) for c in r["CARS"]] == [("Four 1", 300), ("Four 2", 50), ("Four 3", 30)]   # MR + HR + HRacing + CARS Others
    assert r["_totals"]["CARS"] == 380 and r["_totals"]["total"] == 800     # le total n'inclut pas la vue CARS en double
    assert r["_totals"]["XC"] == 400 and r["_totals"]["HORS_BU"] == 20


def test_cars_aggregate_open_balance_adds_up_its_bus():
    rows = [_srow(1, "Four 1", "604020 ACH. MARCH. Modern Rally", 600), _srow(1, "Four 1", "604040 ACH. MARCH. Historic Racing", 400)]
    invoices = [{"id": 51, "partner_id": [1, "Four 1"], "amount_residual_signed": -1000.0}]
    lines = [{"move_id": [51, "B"], "account_id": [1, "604020 ACH. MARCH. Modern Rally"], "balance:sum": 600.0},
             {"move_id": [51, "B"], "account_id": [2, "604040 ACH. MARCH. Historic Racing"], "balance:sum": 400.0}]
    r = make(rows, [_partner(1, "Four 1")], {}, invoices, lines).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert r["CARS"][0]["open"] == 1000 and r["_open_totals"]["CARS"] == 1000 and r["_open_totals"]["total"] == 1000


def test_clients_cars_view_aggregates_cars_bus_and_not_in_total():
    rows = [_row(1, "Alpha", "700020 CA Modern Rally", 100), _row(1, "Alpha", "700040 CA Historic Racing", 200),
            _row(2, "Beta", "700030 CA Historic Rally", 50), _row(2, "Beta", "700010 CA XC Manufacturer", 400),
            _row(3, "Gamma", "700050 CA CARS Others", 30)]
    invoices = [{"id": 61, "partner_id": [1, "Alpha"], "amount_residual_signed": 300.0}]
    lines = [{"move_id": [61, "F"], "account_id": [1, "700020 CA Modern Rally"], "balance:sum": -100.0},
             {"move_id": [61, "F"], "account_id": [2, "700040 CA Historic Racing"], "balance:sum": -200.0}]
    r = make(rows, [_partner(i, n) for i, n in ((1, "Alpha"), (2, "Beta"), (3, "Gamma"))], {}, invoices, lines).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [(c["name"], c["ca"]) for c in r["CARS"]] == [("Alpha", 300), ("Beta", 50), ("Gamma", 30)]
    assert r["CARS"][0]["open"] == 300 and r["_open_totals"]["CARS"] == 300
    assert r["_totals"]["total"] == 780 and r["_totals"]["CARS"] == 380         # pas de double comptage


def _events_provider(plans=None, lines=None):
    p = OdooProvider.__new__(OdooProvider)
    plans = plans if plans is not None else [{"id": 1, "name": "MEETING", "parent_id": False}, {"id": 2, "name": "BU", "parent_id": False},
                                              {"id": 3, "name": "Rallyes", "parent_id": [1, "MEETING"]}]
    seen = {}

    def call(model, method, **kw):
        seen.setdefault(model, []).append(kw)
        if model == "account.analytic.plan":
            return plans
        return lines if lines is not None else []
    p._call = call
    return p, seen


def _aline(event, gen, amount, col="x_plan1_id", bu=None):
    r = {col: [event[0], event[1]], "general_account_id": [1, gen], "amount:sum": amount}
    if bu is not None:
        r["x_plan2_id"] = [7, bu] if bu else False          # axe BU renseigné (ou vide)
    return r


AND = (10, "Andalucia 2026")
SPA = (11, "Spa 2026")


def test_events_filter_on_the_meeting_plan_column_not_on_the_main_account():
    p, seen = _events_provider(lines=[])
    p.events(date(2026, 1, 1), date(2026, 9, 4))
    q = seen["account.analytic.line"][0]
    assert ("x_plan1_id", "!=", False) in q["domain"] and q["groupby"] == ["x_plan1_id", "general_account_id", "x_plan2_id"]   # colonnes MEETING puis BU
    assert not any(c[0] == "account_id" for c in q["domain"])                                                  # pas le compte principal
    assert len(seen["account.analytic.line"]) == 1                                                            # sans investissement : pas de requête de durée ; le sous-plan partage la colonne du plan racine


def test_events_result_by_meeting_plan_with_signed_analytic_amounts():
    lines = [_aline(AND, "700040 CA Historic Racing", 41_500.0, bu="Historic Racing"), _aline(AND, "604040 ACH. MARCH. Historic Racing", -50_000.0, bu="Historic Racing"),
             _aline(AND, "615001 Carburant", -18_500.0, bu="Historic Racing"),
             _aline(SPA, "700010 CA XC Manufacturer", 30_000.0, bu="XC"), _aline(SPA, "602012 FRAIS XC Race team", -12_000.0, bu="XC"),
             _aline(SPA, "612051 Frais de représentation", -1_000.0, bu="XC"),
             _aline(SPA, "400000 Clients", 999.0, bu="XC")]                                 # compte de bilan : ignoré
    r = _events_provider(lines=lines)[0].events(date(2026, 1, 1), date(2026, 9, 4))
    e = {x["name"]: x for x in r["events"]}
    a = e["Andalucia 2026"]
    assert (a["ca"], a["direct_costs"], a["other_costs"], a["result"], a["group"]) == (41_500, 50_000, 18_500, -27_000, "CARS")   # la perte de l'analyse de septembre
    s = e["Spa 2026"]
    assert (s["ca"], s["direct_costs"], s["other_costs"], s["result"], s["group"]) == (30_000, 12_000, 1_000, 17_000, "XC")
    assert r["plans"] == ["MEETING", "Rallyes"] and r["bu_missing"] == 0


def test_events_with_unrecognized_bu_axis_account_go_to_none():
    lines = [_aline(AND, "612051 Frais de représentation", -500.0, bu="Autre chose"), _aline(AND, "700099 Frais refacturés", 200.0, bu="Autre chose")]
    r = _events_provider(lines=lines)[0].events(date(2026, 1, 1), date(2026, 9, 4))
    assert r["events"][0]["group"] == "NONE" and r["bu_unmapped"] == ["Autre chose"]


def test_events_plan_not_found_gives_a_clear_message():
    p, _ = _events_provider(plans=[{"id": 2, "name": "PROJECTS", "parent_id": False}])
    try:
        p.events(date(2026, 1, 1), date(2026, 9, 4))
        raise AssertionError("aurait dû échouer")
    except LookupError as e:
        assert "PROJECTS" in str(e) and "EVENT_PLAN" in str(e)


def test_event_bu_comes_from_the_bu_axis_before_the_accounts():
    # comptes XC mais axe BU = Historic Rally : l'axe prime
    lines = [_aline(AND, "700010 CA XC Manufacturer", 10_000.0, bu="Historic Rally"), _aline(AND, "602012 FRAIS XC Race team", -4_000.0, bu="Historic Rally")]
    e = _events_provider(lines=lines)[0].events(date(2026, 1, 1), date(2026, 9, 4))["events"][0]
    assert e["group"] == "CARS" and e["mixed"] is False and e["bus"] == [{"bu": "Historic Rally", "share": 1.0}]


def test_event_with_empty_bu_axis_is_flagged_not_guessed_from_accounts():
    lines = [_aline(SPA, "700010 CA XC Manufacturer", 10_000.0, bu=False), _aline(SPA, "602012 FRAIS XC Race team", -4_000.0, bu=False)]
    r = _events_provider(lines=lines)[0].events(date(2026, 1, 1), date(2026, 9, 4))
    assert r["events"][0]["group"] == "NONE" and r["bu_missing"] == 2          # pas de déduction par les comptes : anomalie signalée
    assert r["events"][0]["ca"] == 10_000                                      # les montants restent comptés


def test_events_require_the_bu_axis():
    p, _ = _events_provider(plans=[{"id": 1, "name": "MEETING", "parent_id": False}])
    try:
        p.events(date(2026, 1, 1), date(2026, 9, 4))
        raise AssertionError("aurait dû échouer")
    except LookupError as e:
        assert "BU_PLAN" in str(e) and "MEETING" in str(e)


def test_bu_axis_accounts_of_lifelive_are_all_recognized():
    f = OdooProvider._bu_of_axis_account
    assert f("XC") == ("XC", "XC") and f("Modern Rally") == ("MODERN_RALLY", "CARS") and f("Historic Rally") == ("HISTORIC_RALLY", "CARS")
    assert f("Historic Racing") == ("HISTORIC_RACING", "CARS") and f("Others") == ("OTHERS", "OTHERS")
    assert f("OLD - 2025") == ("OLD", None)                                   # ancien exercice : reconnu mais écarté
    assert f("Truc inconnu") is None and f("  historic   racing ") == ("HISTORIC_RACING", "CARS")


def test_event_with_cars_bus_shows_the_split_and_old_and_others_are_handled():
    lines = [_aline(AND, "700040 CA Historic Racing", 7_000.0, bu="Historic Racing"), _aline(AND, "700020 CA Modern Rally", 3_000.0, bu="Modern Rally"),
             _aline(AND, "612051 Frais", -500.0, bu="OLD - 2025"),                                   # écarté entièrement, sans alerte
             _aline(SPA, "700016 CA XC Others", 1_000.0, bu="Others")]
    r = _events_provider(lines=lines)[0].events(date(2026, 1, 1), date(2026, 9, 4))
    e = {x["name"]: x for x in r["events"]}
    assert e["Andalucia 2026"]["group"] == "CARS" and e["Andalucia 2026"]["bus"] == [{"bu": "Historic Racing", "share": 0.7}, {"bu": "Modern Rally", "share": 0.3}]
    assert e["Andalucia 2026"]["mixed"] is False                               # deux BU, mais un seul groupe (CARS)
    assert e["Andalucia 2026"]["other_costs"] == 0                             # la ligne « OLD - 2025 » (-500 €) n'est pas comptée
    assert e["Spa 2026"]["group"] == "OTHERS" and r["bu_unmapped"] == [] and r["bu_missing"] == 0


def test_event_mixed_xc_and_cars_and_unrecognized_axis_account_are_reported():
    lines = [_aline(AND, "700020 CA Modern Rally", 8_000.0, bu="Modern Rally"), _aline(AND, "700010 CA XC Manufacturer", 2_000.0, bu="XC"),
             _aline(AND, "612051 Frais", -100.0, bu="Autre chose")]
    r = _events_provider(lines=lines)[0].events(date(2026, 1, 1), date(2026, 9, 4))
    e = r["events"][0]
    assert e["group"] == "CARS" and e["mixed"] is True                       # XC pèse 20 % : événement mixte
    assert r["bu_unmapped"] == ["Autre chose"] and r["bu_axis"] == "BU"


def test_event_made_only_of_old_bu_lines_does_not_appear():
    r = _events_provider(lines=[_aline(AND, "700040 CA Historic Racing", 5_000.0, bu="OLD - 2025"), _aline(AND, "604040 ACH", -2_000.0, bu="old-2025")])[0].events(date(2026, 1, 1), date(2026, 9, 4))
    assert r["events"] == [] and r["bu_unmapped"] == [] and r["bu_missing"] == 0


def test_event_cash_result_excludes_amortisation_and_counts_capitalised_spend_with_duration():
    lines = [_aline(AND, "700040 CA Historic Racing", 41_700.0, bu="Historic Racing"), _aline(AND, "602040 FRAIS Historic Racing", -30_466.0, bu="Historic Racing"),
             _aline(AND, "240040 INVEST - Historic Racing", -37_510.0, bu="Historic Racing"),
             _aline(AND, "240940 INVEST - Historic Racing (copie)", 3_840.0, bu="Historic Racing"),     # contrepartie d'amortissement : ignorée
             _aline(AND, "630104 Dot. amortis.", -3_840.0, bu="Historic Racing")]
    p, seen = _events_provider(lines=lines)
    detail = [{"date": "2026-08-31", "x_plan1_id": [10, "Andalucia 2026"], "amount": -312.0}, {"date": "2026-09-30", "x_plan1_id": [10, "Andalucia 2026"], "amount": -312.585},
              {"date": "2026-09-30", "x_plan1_id": [10, "Andalucia 2026"], "amount": -312.585}]
    orig = p._call
    p._call = lambda model, method, **kw: detail if method == "search_read" and model == "account.analytic.line" else orig(model, method, **kw)
    a = p.events(date(2026, 1, 1), date(2026, 10, 5))["events"][0]
    assert (a["ca"], a["direct_costs"], a["other_costs"], a["capex"], a["amort"]) == (41_700, 30_466, 0, 37_510, 3_840)
    assert a["result"] == -26_276 and a["result_accounting"] == 7_394                  # cash vs comptable
    assert a["amort_monthly"] == 625 and a["amort_months"] == 60                         # 37 510 ÷ 625,17 ≈ 60 mois


def test_webshop_basket_series_by_month_with_gaps_and_by_week_for_short_periods():
    p, _ = _shop_provider()
    (w,) = p.webshops(date(2026, 1, 1), date(2026, 3, 31), top=1)
    bs = w["basket_series"]
    assert bs["granularity"] == "month" and [x["label"] for x in bs["points"]] == ["janv. 2026", "févr. 2026", "mars 2026"]
    assert [x["avg"] for x in bs["points"]] == [200.0, None, 50.0] and bs["points"][0]["orders"] == 2    # février sans commande : trou, pas zéro
    gran, weeks = OdooProvider._buckets(date(2026, 9, 1), date(2026, 9, 30))
    assert gran == "week" and weeks[0][0] == date(2026, 8, 31) and len(weeks) == 5                          # semaines commençant le lundi


FIRST_CART = ['2026-01-01 00:00:00']


def test_webshop_payments_deliveries_and_abandoned_carts():
    p, _ = _shop_provider()
    base = p._call

    def call(model, method, **kw):
        if model == "payment.transaction":
            return [{"payment_method_id": [1, "Carte"], "amount:sum": 600.0, "__count": 6}, {"payment_method_id": [2, "Bancontact"], "amount:sum": 400.0, "__count": 4}]
        if model == "sale.order" and method == "formatted_read_group" and kw["groupby"] == ["carrier_id"]:
            return [{"carrier_id": False, "amount_untaxed:sum": 100.0, "__count": 1}, {"carrier_id": [5, "Express"], "amount_untaxed:sum": 900.0, "__count": 9}]
        if model == "website":
            return [{"cart_abandoned_delay": 1.0}]
        if model == "sale.order" and method == "search_read" and ("state", "=", "draft") in kw["domain"] and kw.get("limit") == 1:
            return [{"date_order": FIRST_CART[0]}]                                            # plus ancien panier encore conservé par Odoo
        if model == "sale.order" and method == "search_read" and ("state", "=", "draft") in kw["domain"]:
            allc = [{"id": 1, "date_order": "2026-01-15 10:00:00", "amount_untaxed": 80.0}, {"id": 2, "date_order": "2026-03-05 10:00:00", "amount_untaxed": 20.0},
                    {"id": 3, "date_order": "2026-03-06 10:00:00", "amount_untaxed": 50.0}]       # le n° 3 : visiteur non connecté
            return [{"id": 1}, {"id": 2}] if ("is_abandoned_cart", "=", True) in kw["domain"] else allc
        return base(model, method, **kw)
    p._call = call
    (w,) = p.webshops(date(2026, 1, 1), date(2026, 3, 31), top=1)
    assert [(x["name"], x["count"], round(x["share"], 2)) for x in w["payments"]] == [("Carte", 6, 0.6), ("Bancontact", 4, 0.4)]
    assert [(x["name"], x["count"]) for x in w["deliveries"]] == [("Express", 9), ("Sans livraison (retrait, service…)", 1)]
    a = w["abandoned"]
    assert (a["count"], a["identified"], a["anonymous"], a["amount"]) == (3, 2, 1, 150) and round(a["rate"], 3) == round(3 / 6, 3)   # 3 abandons pour 3 commandes
    assert [x["abandoned"] for x in a["series"]["points"]] == [1, 0, 2] and [x["identified"] for x in a["series"]["points"]] == [1, 0, 1] and a["series"]["points"][1]["avg"] is None


def test_webshop_optional_views_fail_independently():
    p, _ = _shop_provider()                                  # ce simulateur ne connaît pas les transactions de paiement
    (w,) = p.webshops(date(2026, 1, 1), date(2026, 3, 31), top=1)
    assert w["payments"] is None and w["products"]       # les produits restent disponibles


def test_vehicles_use_the_cars_plan_exactly_and_take_bu_from_the_bu_axis():
    plans = [{"id": 1, "name": "MEETING", "parent_id": False}, {"id": 2, "name": "BU", "parent_id": False}, {"id": 5, "name": "CARS", "parent_id": False},
             {"id": 6, "name": "XC", "parent_id": False}]
    car = (50, "[Modern Rally] Porsche 992 Rally GT #26 EMO - EMO Sport")
    lines = [_aline(car, "700020 CA Modern Rally", 1000.0, col="x_plan5_id", bu="Modern Rally"), _aline(car, "602020 FRAIS Modern Rally", -400.0, col="x_plan5_id", bu="Modern Rally"),
             _aline(car, "612000 Divers", -100.0, col="x_plan5_id", bu="Modern Rally")]
    p, seen = _events_provider(plans=plans, lines=lines)
    orig = p._call
    p._call = lambda m, meth, **kw: ([{"id": 50, "name": "Porsche 992 Rally GT #26 EMO", "code": "Modern Rally", "partner_id": [9, "EMO Sport"]}] if m == "account.analytic.account"
                                      else orig(m, meth, **kw))
    r = p.vehicles(date(2026, 1, 1), date(2026, 10, 5))
    q = seen["account.analytic.line"][0]
    assert ("x_plan5_id", "!=", False) in q["domain"] and q["groupby"][0] == "x_plan5_id"            # axe CARS, pas l'axe XC
    (v,) = r["vehicles"]
    assert (v["name"], v["group"], v["client"], v["reference"]) == ("Porsche 992 Rally GT #26 EMO", "CARS", "EMO Sport", "Modern Rally")
    assert (v["ca"], v["direct_costs"], v["other_costs"], v["result"]) == (1000, 400, 100, 500) and r["plans"] == ["CARS"]


def test_missing_bu_lines_are_listed_with_item_account_and_amount():
    lines = [_aline(AND, "700040 CA Historic Racing", 100.0, bu="Historic Racing"), {**_aline(AND, "612000 Divers", -166.0, bu=""), "__count": 2}]
    r = _events_provider(lines=lines)[0].events(date(2026, 1, 1), date(2026, 10, 5))
    assert r["bu_missing"] == 1 and r["bu_missing_detail"] == [{"item": "Andalucia 2026", "account": "612000 Divers", "amount": -166.0, "lines": 2}]


def test_webshop_visits_window_is_fixed_weekly_with_orders_and_top_pages_merge_query_strings():
    p, _ = _shop_provider()
    base = p._call
    seen = []

    def call(model, method, **kw):
        if model == "website.track" and method == "formatted_read_group":
            seen.append(kw)
            if kw["groupby"] == ["url"]:
                return [{"url": "/shop/pneu-cross-car-1234", "__count": 40}, {"url": "/shop/pneu-cross-car-1234?order=asc", "__count": 10},
                        {"url": "/fr/shop", "__count": 25}, {"url": False, "__count": 5}]
            return [{"__count": 10, "visitor_id:count_distinct": 4}]
        if model == "website.track" and method == "search_read":
            return [{"visit_datetime": "2026-09-20 08:00:00"}]                      # plus ancienne visite anonyme conservée par Odoo
        if model == "sale.order" and method == "search_count":
            return 7
        return base(model, method, **kw)
    p._call = call
    v = p._visits(1, date(2026, 8, 17), date(2026, 10, 5))
    assert v["granularity"] == "week" and v["points"][0]["label"] == "17 août" and len(v["points"]) == 8     # semaines commençant le lundi
    assert v["orders"] == 7 and v["visitors"] == 4 and v["views"] == 10 and (v["from"], v["to"]) == ("2026-08-17", "2026-10-05")
    assert v["incomplete"] and v["complete_from"] == "2026-09-20" and v["points"][0]["avg"] is None and v["points"][-1]["avg"] == 10.0
    d0 = seen[0]["domain"]
    assert ("url", "like", "%/shop%") in d0 and ("visitor_id.website_id", "=", 1) in d0
    assert d0[2:6] == ["|", "|", ("product_id", "=", False), ("product_id.website_id", "=", 1)] and ("product_id.website_id", "=", False) in d0   # produits d'un autre site écartés
    pages = p._top_pages(1, date(2026, 8, 17), date(2026, 10, 5))
    assert [(x["label"], x["path"], x["views"]) for x in pages] == [("Pneu cross car", "/shop/pneu-cross-car-1234", 50), ("Page d'accueil du shop", "/fr/shop", 25)]
    assert round(pages[0]["share"], 3) == round(50 / 75, 3)
    (w,) = p.webshops(date(2026, 1, 1), date(2026, 3, 31), top=1)
    assert w["visits"]["to"] == date.today().isoformat() and w["visits"]["granularity"] == "week"           # fenêtre indépendante de la période


def test_abandoned_rate_ignores_months_before_the_oldest_cart_kept_by_odoo():
    FIRST_CART[0] = "2026-02-10 09:00:00"                    # janvier et février (partiel) : Odoo a purgé les paniers
    try:
        p, _ = _shop_provider()
        base = p._call

        def call(model, method, **kw):
            if model == "website":
                return [{"cart_abandoned_delay": 1.0}]
            if model == "sale.order" and method == "search_read" and ("state", "=", "draft") in kw["domain"]:
                if kw.get("limit") == 1:
                    return [{"date_order": FIRST_CART[0]}]
                return [{"id": 3, "date_order": "2026-03-06 10:00:00", "amount_untaxed": 50.0}]
            return base(model, method, **kw)
        p._call = call
        (w,) = p.webshops(date(2026, 1, 1), date(2026, 3, 31), top=1)
        a = w["abandoned"]
        assert a["incomplete"] and a["complete_from"] == "2026-02-10" and a["rate_from"] == "2026-03-01"
        assert [x["avg"] for x in a["series"]["points"]] == [None, None, round(1 / 2, 4)]    # seul mars est entièrement couvert (1 abandon, 1 commande)
        assert round(a["rate"], 3) == 0.5                                                      # taux sur la partie couverte uniquement
    finally:
        FIRST_CART[0] = "2026-01-01 00:00:00"


def test_top_customers_merge_contacts_and_report_payment_delivery_and_share():
    p = OdooProvider.__new__(OdooProvider)
    orders = [{"id": 1, "partner_id": [10, "Jean (ACME)"], "amount_untaxed": 300.0, "date_order": "2026-03-01 10:00:00", "carrier_id": [5, "Express"]},
              {"id": 2, "partner_id": [11, "Marie (ACME)"], "amount_untaxed": 100.0, "date_order": "2026-05-02 10:00:00", "carrier_id": [5, "Express"]},
              {"id": 3, "partner_id": [20, "PIERRE SOLO"], "amount_untaxed": 100.0, "date_order": "2026-04-02 10:00:00", "carrier_id": False}]
    partners = {10: {"id": 10, "display_name": "Jean (ACME)", "commercial_partner_id": [1, "ACME"], "category_id": []},
                11: {"id": 11, "display_name": "Marie (ACME)", "commercial_partner_id": [1, "ACME"], "category_id": []},
                1: {"id": 1, "display_name": "ACME SA", "commercial_partner_id": [1, "ACME"], "category_id": []},
                20: {"id": 20, "display_name": "PIERRE SOLO", "commercial_partner_id": [20, "x"], "category_id": []}}

    def call(model, method, **kw):
        if model == "sale.order":
            return orders
        if model == "res.partner" and kw["fields"] == ["country_id"]:
            return [{"id": 1, "country_id": [3, "Belgique"]}, {"id": 20, "country_id": False}]
        if model == "res.partner":
            return [partners[i] for i in kw["ids"] if i in partners]
        if model == "payment.transaction":
            return [{"sale_order_ids": [1], "payment_method_id": [1, "Carte"]}, {"sale_order_ids": [2], "payment_method_id": [1, "Carte"]},
                    {"sale_order_ids": [3], "payment_method_id": False, "provider_id": [2, "Virement"]}]
        return []
    p._call = call
    r = p._top_customers(1, [])
    a, b = r["customers"]
    assert (a["name"], a["ca"], a["orders"], a["avg_basket"], round(a["share"], 2), a["country"], a["last_order"]) == ("Acme SA", 400, 2, 200.0, 0.8, "Belgique", "2026-05-02")
    assert a["payments"] == [{"name": "Carte", "count": 2}] and a["deliveries"] == [{"name": "Express", "count": 2}]
    assert b["payments"] == [{"name": "Virement", "count": 1}] and b["deliveries"] == [{"name": "Sans livraison", "count": 1}]
    assert (r["total_ca"], r["total_orders"], r["count"], r["repeat"], r["top_ca"]) == (500, 3, 2, 1, 500)
