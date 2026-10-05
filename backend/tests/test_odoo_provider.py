from datetime import date

from app.providers.odoo import OdooProvider


def make(rows, partners=None, tags=None):
    p = OdooProvider.__new__(OdooProvider)  # sans client HTTP
    p._grouped = lambda domain, groupby: rows

    def call(model, method, **kw):
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
    assert r["XC"][0] == {"name": "B", "ca": 120}
    assert r["HISTORIC_RACING"] == [{"name": "A", "ca": 50}]
    assert all(c["name"] != "C" for k, board in r.items() if k != "_meta" for c in board)


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
    assert r["total"] == [{"name": "Groupe Alpha", "ca": 150}, {"name": "Beta", "ca": 120}]
    assert r["_meta"] == {"grouping": True, "groups": 1}
    assert r["HISTORIC_RACING"] == [{"name": "Groupe Alpha", "ca": 50}]


def test_contacts_of_same_company_are_merged_and_tag_on_company_applies():
    rows = [_row(1, "Alpha SA, Jean", "700010 CA XC", 30), _row(2, "Alpha SA, Marie", "700010 CA XC", 20)]
    partners = [_partner(1, "Alpha SA, Jean", com=9), _partner(2, "Alpha SA, Marie", com=9), _partner(9, "Alpha SA", cats=[10])]
    r = make(rows, partners, {10: "regroup_client=Groupe A"}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert r["total"] == [{"name": "Groupe A", "ca": 50}]
    r2 = make(rows, [_partner(1, "x", com=9), _partner(2, "y", com=9), _partner(9, "Alpha SA")], {}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert r2["total"] == [{"name": "Alpha SA", "ca": 50}]  # sans étiquette : fusion par société


def test_other_tags_are_ignored():
    rows = [_row(1, "Alpha", "700010 CA XC", 10)]
    r = make(rows, [_partner(1, "Alpha", cats=[5])], {5: "VIP"}).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert r["total"] == [{"name": "Alpha", "ca": 10}] and r["_meta"]["groups"] == 0


def test_grouping_failure_falls_back_to_raw_names():
    rows = [_row(1, "Alpha", "700010 CA XC", 10), _row(2, "Beta", "700010 CA XC", 20)]
    r = make(rows, None).top_clients(date(2026, 1, 1), date(2026, 9, 4))
    assert [c["name"] for c in r["total"]] == ["Beta", "Alpha"] and r["_meta"]["grouping"] is False
