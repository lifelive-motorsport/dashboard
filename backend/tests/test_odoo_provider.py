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
    p._grouped = lambda domain, groupby: (seen.update(domain=domain, groupby=groupby) if groupby[0] == "partner_id" else None) or []
    p.top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert ("display_type", "=", "product") in seen["domain"] and ("parent_state", "=", "posted") in seen["domain"]
    assert ("move_id.move_type", "in", ["in_invoice", "in_refund"]) in seen["domain"] and seen["groupby"] == ["partner_id", "account_id", "move_id"]     # + facture : nombre de factures et panier moyen


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
    p._grouped = lambda domain, groupby: (seen.update(domain=domain) if groupby[0] == "partner_id" else None) or []      # requête des lignes de factures
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


def test_old_plan_revenue_sums_old_labelled_70_accounts_only():
    rows = [{"account_id": [1, "700010 CA XC Manufacturer"], "balance:sum": -500.0},          # plan courant : non compté ici
            {"account_id": [2, "700000 OLD - Ventes marchandises"], "balance:sum": -1200.0},
            {"account_id": [3, "701000 old - Ventes services"], "balance:sum": -300.0},
            {"account_id": [4, "700500 Goldspeed ventes"], "balance:sum": -50.0}]             # « Goldspeed » n'est pas « old »
    p = make(rows)
    assert p.old_plan_revenue(date(2025, 1, 1), date(2025, 10, 5)) == 1500.0


def _mrow(pid, name, acc, bal, move):
    return {"partner_id": [pid, name], "account_id": [1, acc], "balance:sum": bal, "move_id": [move, f"M{move}"]}


def test_clients_invoice_count_and_average_basket_count_each_invoice_once_even_split_over_bus():
    rows = [_mrow(1, "A", "700010 CA XC Manufacturer", -300.0, 101), _mrow(1, "A", "700040 CA Historic Racing", -100.0, 101),   # une facture sur 2 BU
            _mrow(1, "A", "700010 CA XC Manufacturer", -200.0, 102),
            _mrow(1, "A", "700010 CA XC Manufacturer", 50.0, 103)]                                                      # un avoir : pas une facture
    r = make(rows, [_partner(1, "A")], {}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    t = r["total"][0]
    assert (t["invoices"], t["avg"], t["ca"]) == (2, 300.0, 550)                  # factures 101 (400) et 102 (200) ; l'avoir réduit seulement le CA
    assert r["XC"][0]["invoices"] == 2 and r["XC"][0]["avg"] == 250.0              # XC : 101 -> 300, 102 -> 200
    assert r["HISTORIC_RACING"][0]["invoices"] == 1 and r["HISTORIC_RACING"][0]["avg"] == 100.0
    assert r["_stats"]["total"] == {"invoices": 2, "avg": 300.0} and r["_stats"]["CARS"] == {"invoices": 1, "avg": 100.0}


def test_suppliers_invoice_count_and_average():
    rows = [_mrow(1, "Four", "602010 FRAIS XC Manufacturer", 600.0, 201), _mrow(1, "Four", "615001 Carburant", 400.0, 201), _mrow(1, "Four", "615001 Carburant", 100.0, 202)]
    r = make(rows, [_partner(1, "Four")], {}).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert (r["total"][0]["invoices"], r["total"][0]["avg"]) == (2, 550.0)           # 1 000 € sur la 201, 100 € sur la 202


def test_pickings_per_week_count_orders_and_units_by_date_done():
    from datetime import date as _d, timedelta as _td
    p = OdooProvider.__new__(OdooProvider)
    today = _d.today()
    monday = today - _td(days=today.weekday())
    last_week = monday - _td(days=7)
    seen = {}

    def call(model, method, **kw):
        if model == "stock.picking":
            seen["dom"] = kw["domain"]
            return [{"id": 1, "date_done": f"{last_week + _td(days=1)} 10:00:00"}, {"id": 2, "date_done": f"{last_week + _td(days=3)} 10:00:00"},
                    {"id": 3, "date_done": f"{monday} 08:00:00"}]
        if model == "stock.move":
            return [{"picking_id": [1, "P1"], "quantity:sum": 4.0}, {"picking_id": [2, "P2"], "quantity:sum": 10.0}, {"picking_id": [3, "P3"], "quantity:sum": 1.0}]
    p._call = call
    r = p._pickings(7, 4)
    assert ("sale_id.website_id", "=", 7) in seen["dom"] and ("picking_type_code", "=", "outgoing") in seen["dom"]
    assert [x["orders"] for x in r["points"]] == [0, 0, 2, 1] and [x["units"] for x in r["points"]] == [0, 0, 14, 1]
    assert r["points"][2]["per_order"] == 7.0 and r["points"][0]["per_order"] is None and (r["orders"], r["units"]) == (3, 15)
    p._pickings(None, 4)
    assert not any(c[0] == "sale_id.website_id" for c in seen["dom"])                      # tous les bons de livraison


def test_pickings_exclude_goldspeed_site_but_keep_deliveries_without_sale_order():
    p = OdooProvider.__new__(OdooProvider)
    seen = {}
    p._call = lambda model, method, **kw: seen.update(dom=kw["domain"]) or [] if model == "stock.picking" else []
    p._pickings(None, 4, [9])
    assert ["|", ("sale_id", "=", False), ("sale_id.website_id", "not in", [9])] == seen["dom"][-3:]


def test_pickings_only_computed_for_non_goldspeed_webshops():
    p, _ = _shop_provider()
    base = p._call
    p._call = lambda m, meth, **kw: ([{"id": 1, "name": "Lifelive Motorsport"}, {"id": 2, "name": "Goldspeed XC Cross Car tires - European Championship"}]
                                     if m == "website" else base(m, meth, **kw))
    (w,) = p.webshops(date(2026, 1, 1), date(2026, 3, 31), top=1)           # le simulateur ne connaît qu'un site (id 1) : XC
    assert w["pickings"] is not None or w["errors"].get("pickings")          # calculé (ou en erreur de droits) pour XC


def test_stock_report_values_top_pif_negatives_and_attention_points():
    from app.stock import build_report
    items = [{"ref": "A", "name": "Chassis", "pif": "N", "cost": 100.0, "qty": 6.0, "uom": "Units"},
             {"ref": "B", "name": "Upright front right", "pif": "F", "cost": 10.0, "qty": 20.0, "uom": "Units"},
             {"ref": "C", "name": "Upright front left", "pif": "F", "cost": 10.0, "qty": 16.0, "uom": "Units"},
             {"ref": "D", "name": "Engine", "pif": "", "cost": 500.0, "qty": -4.0, "uom": "Units"},
             {"ref": "E", "name": "Free part", "pif": "", "cost": 0.0, "qty": 7.0, "uom": "Units"},
             {"ref": "F", "name": "Tube", "pif": "N", "cost": 5.0, "qty": 509.7, "uom": "Units"},
             {"ref": "G", "name": "Spacer", "pif": "N", "cost": 3.0, "qty": 2989.0, "uom": "Units"}]
    r = build_report(items, "x_pif")
    assert r["total"] == {"value": round(600 + 200 + 160 - 2000 + 0 + 2548.5 + 8967), "refs": 7, "positive": 12476, "negative": -2000}
    assert r["pif"]["refs"] == 5 and [t["ref"] for t in r["top"]][:2] == ["G", "F"] and r["top"][-1]["cum"] == 1.0
    assert {c["code"]: c["refs"] for c in r["by_pif"]} == {"N": 3, "F": 2} and r["pif_empty"]["refs"] == 2
    att = r["attention"]
    assert att["negatives"]["refs"] == 1 and att["negatives"]["top"][0]["ref"] == "D"
    assert att["zero_cost"] == {"refs": 1, "units": 7.0}
    assert [v["ref"] for v in att["volumes"]] == ["G", "F"]                                   # ≥ 500 pièces dans le top 10
    assert [d["ref"] for d in att["decimals"]] == ["F"]                                       # quantité décimale sur une unité « Units »
    assert att["pairs"] and att["pairs"][0]["gap"] == 40 and {att["pairs"][0]["a_qty"], att["pairs"][0]["b_qty"]} == {20.0, 16.0}
    assert att["no_pif"]["refs"] == 2


def test_marketing_expenses_by_account_supplier_bucket_and_andalucia_investment():
    p = OdooProvider.__new__(OdooProvider)
    lines = [{"date": "2026-01-15", "balance": 1000.0, "account_id": [1, "602019 Frais XC Sales & Marketing"], "partner_id": [10, "AGENCE X"], "move_id": [100, "B1"]},
             {"date": "2026-01-20", "balance": 500.0, "account_id": [2, "612050 Frais marketing génériques"], "partner_id": [10, "AGENCE X"], "move_id": [101, "B2"]},
             {"date": "2026-03-03", "balance": 300.0, "account_id": [3, "602059 Frais CARS Sales & Marketing"], "partner_id": [11, "SALON Y"], "move_id": [102, "B3"]},
             {"date": "2026-03-04", "balance": -100.0, "account_id": [3, "602059 Frais CARS Sales & Marketing"], "partner_id": [11, "SALON Y"], "move_id": [103, "AV1"]}]
    seen = {}

    def call(model, method, **kw):
        if model == "account.move.line" and ("debit", ">", 0) in kw["domain"]:                       # lignes d'investissement (compte INVEST)
            return [{"name": "Création & Développement d'un système graphique", "balance": 2200.0, "date": "2026-02-24", "partner_id": [5, "Actaeon"], "move_id": [1, "FACTU/2026/02/0072"]},
                    {"name": "Création & Développement d'un système graphique", "balance": 3300.0, "date": "2026-04-03", "partner_id": [5, "Actaeon"], "move_id": [2, "FACTU/2026/04/0013"]},
                    {"name": "Package Social Media Almeira 2026", "balance": 5500.0, "date": "2026-04-03", "partner_id": [5, "Actaeon"], "move_id": [2, "FACTU/2026/04/0013"]},
                    {"name": "2 Säulen Hebebühne 4.2 t - BASIC LINE", "balance": 1764.0, "date": "2026-02-10", "partner_id": [6, "Twin-Busch"], "move_id": [3, "FACTU/2026/02/0113"]},   # matériel : pas du marketing
                    {"name": "Dalle à clipser PVC", "balance": 2880.0, "date": "2026-02-12", "partner_id": [7, "Rubber"], "move_id": [4, "FACTU/2026/02/0025"]}]
        if model == "account.move.line" and ("name", "ilike", "amortissement") in kw["domain"]:   # dotations mensuelles
            return [{"name": "Package Social Media Almeira 2026 : Amortissement", "balance": 91.67, "date": "2026-08-31"},
                    {"name": "Package Social Media Almeira 2026 : Amortissement", "balance": 91.66, "date": "2026-09-30"},
                    {"name": "Création & Développement d'un système graphique : Amortissement", "balance": 91.67, "date": "2026-09-30"}]
        if model == "account.move.line":
            seen["dom"] = kw["domain"]
            return lines
        if model == "res.partner.category":
            return []                                                                      # étiquette absente : repli sur les mots-clés
        if model == "res.partner":
            return [{"id": 10, "display_name": "AGENCE X", "commercial_partner_id": [10, "x"], "category_id": []},
                    {"id": 11, "display_name": "SALON Y", "commercial_partner_id": [11, "y"], "category_id": []}]
        return []
    p._call = call
    r = p.marketing(date(2026, 1, 1), date(2026, 3, 31))
    assert ("account_id.code", "in", ["602019", "602059", "612050"]) in seen["dom"]
    assert r["total"] == 1700 and [a["code"] for a in r["accounts"]] == ["602019", "612050", "602059"] and r["accounts"][2]["amount"] == 200   # avoir déduit
    assert [(s["name"], s["amount"], s["invoices"]) for s in r["suppliers"]] == [("Agence X", 1500, 2), ("Salon Y", 200, 1)]            # l'avoir n'est pas une facture
    assert [x["total"] for x in r["series"]["points"]] == [1500, 0, 200] and r["series"]["granularity"] == "month"
    inv = r["invest"]
    assert (inv["total"], inv["year"], len(inv["items"])) == (11000, 2026, 2)               # le matériel du même compte INVEST est écarté
    gfx = next(i for i in inv["items"] if i["label"].startswith("Création"))
    pkg = next(i for i in inv["items"] if i["label"].startswith("Package"))
    assert (gfx["capex"], gfx["amort_months"], [b["ref"] for b in gfx["bills"]]) == (5500, 60, ["FACTU/2026/02/0072", "FACTU/2026/04/0013"])      # 5 500 ÷ 91,67 = 60 mois
    assert (pkg["capex"], pkg["amort"], pkg["amort_months"]) == (5500, 183, 60)


def test_marketing_invest_uses_the_supplier_tag_when_it_exists():
    p = OdooProvider.__new__(OdooProvider)
    seen = {}

    def call(model, method, **kw):
        if model == "res.partner.category":
            return [{"id": 7, "name": "Invest Marketing"}, {"id": 8, "name": "invest marketing 2025"}]       # seule la correspondance exacte compte
        if model == "res.partner":
            seen["partner_dom"] = kw["domain"]
            return [{"id": 5}]
        if model == "account.move.line" and ("debit", ">", 0) in kw["domain"]:
            seen["dom"] = kw["domain"]
            return [{"name": "Prestation sans mot-clé", "balance": 4000.0, "date": "2026-03-01", "partner_id": [5, "Actaeon"], "move_id": [1, "F1"]}]
        return []
    p._call = call
    inv = p._marketing_invest(date(2026, 10, 6))
    assert seen["partner_dom"] == [("category_id", "in", [7])] and ("partner_id", "child_of", [5]) in seen["dom"]
    assert inv["total"] == 4000 and inv["items"][0]["label"] == "Prestation sans mot-clé"                    # le tag suffit : plus besoin de mot-clé


def test_tags_overview_classifies_dashboard_tags_and_counts_contacts():
    p = OdooProvider.__new__(OdooProvider)

    def call(model, method, **kw):
        if model == "res.partner.category":
            return [{"id": 1, "name": "regroup_client=Koramic"}, {"id": 2, "name": "regroup_fournisseur=Pirelli"}, {"id": 3, "name": "invest marketing"}, {"id": 4, "name": "VIP"}]
        return [{"category_id": [1, "regroup_client=Koramic"], "__count": 3}, {"category_id": [3, "invest marketing"], "__count": 1}, {"category_id": [4, "VIP"], "__count": 9}]
    p._call = call
    t = p.tags_overview()["tags"]
    assert [(x["kind"], x["name"], x["count"]) for x in t] == [("client", "regroup_client=Koramic", 3), ("fournisseur", "regroup_fournisseur=Pirelli", 0), ("invest", "invest marketing", 1)]


def test_suppliers_reconciliation_lists_direct_costs_that_are_not_vendor_bill_lines():
    seen = {}

    def grouped(domain, groupby):
        if groupby == ["journal_id", "account_id"]:
            seen["dom"] = domain
            return [{"journal_id": [9, "Opérations diverses"], "account_id": [1, "604010 ACH. MARCH. XC Manufacturer"], "balance:sum": 9000.0},
                    {"journal_id": [8, "Provisions"], "account_id": [1, "604010 ACH. MARCH. XC Manufacturer"], "balance:sum": 4154.0},
                    {"journal_id": [9, "Opérations diverses"], "account_id": [2, "615001 Carburant"], "balance:sum": 777.0},        # pas un frais direct
                    {"journal_id": [9, "Opérations diverses"], "account_id": [3, "604040 ACH. MARCH. Historic Racing"], "balance:sum": 100.0}]
        return []
    p = make([], [], {})
    p._grouped = grouped
    r = p.top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert r["_recon"]["XC"] == {"amount": 13154, "journals": [{"name": "Opérations diverses", "amount": 9000}, {"name": "Provisions", "amount": 4154}]}
    assert r["_recon"]["CARS"]["amount"] == 100 and r["_recon"]["HISTORIC_RACING"]["amount"] == 100        # le carburant (615) n'est pas du frais direct
    assert ("account_id.code", "=like", "60%") in seen["dom"] and "|" in seen["dom"]


def test_suppliers_carry_the_split_between_purchases_subcontracting_expenses_and_other():
    rows = [_mrow(1, "Four", "604010 ACH. MARCH. XC Manufacturer", 600.0, 1), _mrow(1, "Four", "603010 SS TRAIT. XC Manufacturer", 300.0, 2),
            _mrow(1, "Four", "602010 FRAIS XC Manufacturer", 100.0, 3), _mrow(1, "Four", "615001 Carburant", 50.0, 4)]
    r = make(rows, [_partner(1, "Four")], {}).top_suppliers(date(2026, 1, 1), date(2026, 9, 4))
    assert r["total"][0]["mix"] == {"604": 600, "603": 300, "602": 100, "autres": 50}
    assert r["XC"][0]["mix"] == {"604": 600, "603": 300, "602": 100}                               # le carburant est « hors BU »
    assert r["_mix"]["total"] == {"604": 600, "603": 300, "602": 100, "autres": 50} and r["_mix"]["HORS_BU"] == {"autres": 50}


def test_staff_accounting_reads_director_accounts_separately():
    p = OdooProvider.__new__(OdooProvider)

    def call(model, method, **kw):
        codes = [c for t, op, c in kw["domain"] if t == "account_id.code" and op == "in"]
        if codes:                                    # comptes administrateur : 618000 rémunération, 618001 cotisations
            return [{"date": "2026-01-31", "balance": 3130.0, "account_id": [1, "618000 Rémunération administrateurs"]},
                    {"date": "2026-01-31", "balance": 900.4, "account_id": [2, "618001 Cotisations sociales administrateurs"]},
                    {"date": "2026-02-28", "balance": 3130.0, "account_id": [1, "618000 Rémunération administrateurs"]}]
        return [{"date": "2026-01-31", "balance": 1000.0, "account_id": [3, "620000 Rémunérations"]}]
    p._call = call
    r = p.staff_accounting(2026)
    assert r["pay_by_month"] == {"2026-01": 1000}
    assert r["director"]["pay_by_month"] == {"2026-01": 3130, "2026-02": 3130} and r["director"]["social_by_month"] == {"2026-01": 900}


def test_staff_invoices_report_fees_on_613_accounts_only():
    p = OdooProvider.__new__(OdooProvider)
    seen = {}

    def call(model, method, **kw):
        if model == "account.move":
            return [{"id": 1, "name": "F1", "ref": "r1", "invoice_date": "2026-01-31", "date": "2026-01-31", "amount_untaxed": 1000.0, "amount_total": 1210.0, "payment_state": "paid", "move_type": "in_invoice", "commercial_partner_id": [9, "ILP"]},
                    {"id": 3, "name": "F3", "ref": "", "invoice_date": "2025-12-31", "date": "2026-01-02", "amount_untaxed": 5150.0, "amount_total": 5150.0, "payment_state": "paid", "move_type": "in_invoice", "commercial_partner_id": [9, "ILP"]},
                    {"id": 2, "name": "A1", "ref": "", "invoice_date": "2026-02-10", "date": "2026-02-10", "amount_untaxed": 100.0, "amount_total": 121.0, "payment_state": "not_paid", "move_type": "in_refund", "commercial_partner_id": [9, "ILP"]}]
        seen["domain"] = kw["domain"]
        return [{"move_id": [1, "F1"], "balance": 700.0, "account_id": [5, "613000 Honoraires"]}, {"move_id": [2, "A1"], "balance": -100.0, "account_id": [5, "613000 Honoraires"]},
                {"move_id": [1, "F1"], "balance": 50.0, "account_id": [6, "61300000 old - Honoraires"]},       # F1 : 300 € de frais avancés exclus ; ligne « old » ignorée
                {"move_id": [3, "F3"], "balance": 5150.0, "account_id": [6, "61300000 old - Honoraires"]}]      # F3 : uniquement « old » : facture écartée
    p._call = call
    r = p.staff_invoices([9], 2026)
    assert [(x["number"], x["untaxed"], x["fees"]) for x in r] == [("F1", 1000.0, 700.0), ("A1", -100.0, -100.0)]
    assert ("account_id.code", "=like", "613%") in seen["domain"] and ("move_id", "in", [1, 3, 2]) in seen["domain"]


def test_excluded_accounts_entries_are_listed_apart():
    p = OdooProvider.__new__(OdooProvider)

    def call(model, method, **kw):
        assert ("account_id.code", "in", ["611010"]) in kw["domain"]
        return [{"date": "2026-07-31", "balance": 21000.0, "account_id": [1, "611010 Loyer Batiment"], "move_id": [9, "DIV/2026/07/0001"], "name": "Loyer 01-07/26"}]
    p._call = call
    assert [(o["code"], o["amount"], o["move"]) for o in p.expenses_excluded(2026)] == [("611010", 21000.0, "DIV/2026/07/0001")]


def test_margin_products_from_odoo_data(monkeypatch):
    from app import settings
    monkeypatch.setattr(settings, "STOCK_PIF_FIELD", "x_pif")
    today = date.today().isoformat()
    p = OdooProvider.__new__(OdooProvider)

    def call(model, method, **kw):
        if model == "product.product":
            return [{"id": 7, "default_code": "611363", "name": "3D connector", "x_pif": "N", "list_price": 58.77, "standard_price": 33.58, "product_tmpl_id": [70, "3D connector"]}]
        if model == "product.supplierinfo":
            return [{"product_tmpl_id": [70, "x"], "partner_id": [1, "RapidCenter"], "min_qty": 1.0, "price": 35.21, "currency_id": [1, "EUR"], "date_start": False, "date_end": False},
                    {"product_tmpl_id": [70, "x"], "partner_id": [1, "RapidCenter"], "min_qty": 40.0, "price": 26.78, "currency_id": [1, "EUR"], "date_start": False, "date_end": False},
                    {"product_tmpl_id": [70, "x"], "partner_id": [2, "Young"], "min_qty": 1.0, "price": 26.9, "currency_id": [1, "EUR"], "date_start": False, "date_end": False},
                    {"product_tmpl_id": [70, "x"], "partner_id": [3, "Périmé"], "min_qty": 1.0, "price": 99.0, "currency_id": [1, "EUR"], "date_start": False, "date_end": "2020-01-01"},
                    {"product_tmpl_id": [70, "x"], "partner_id": [4, "Dollar"], "min_qty": 1.0, "price": 77.0, "currency_id": [2, "USD"], "date_start": False, "date_end": False}]
        if model == "account.move.line" and kw.get("groupby") == ["product_id"]:
            return [{"product_id": [7, "x"], "balance:sum": 700.0}]
        if model == "account.move.line":
            return [{"product_id": [7, "x"], "move_type": "in_invoice", "quantity:sum": 22.0, "__count": 3}, {"product_id": [7, "x"], "move_type": "in_refund", "quantity:sum": 2.0, "__count": 1}]
        return []
    p._call = call
    j = p.margin_products()
    r = j["rows"][0]
    assert r["worst"] == {"price": 35.21, "partner": "RapidCenter", "min_qty": 1.0}           # fournisseur le plus cher à 1 unité ; tarif périmé et devise étrangère écartés
    assert r["real"]["unit"] == 35.0 and r["real"]["source"] == "factures" and r["real"]["qty"] == 20.0     # 700 € pour 22 − 2 unités
    assert r["margin"]["theoretical"] == 42.86 and r["rate"]["worst"] == "green" and j["foreign_currency_lines"] == 1 and j["real_error"] is None
