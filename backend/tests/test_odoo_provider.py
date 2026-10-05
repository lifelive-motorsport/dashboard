from datetime import date

from app.providers.odoo import OdooProvider


def make(rows):
    p = OdooProvider.__new__(OdooProvider)  # sans client HTTP
    p._grouped = lambda domain, groupby: rows
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
    assert all(c["name"] != "C" for board in r.values() for c in board)
