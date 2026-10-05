import os
import pytest
from app.bu import classify, aggregate, is_old


def test_goldspeed_is_not_old():
    assert not is_old("CA XC Goldspeed EAX")
    assert is_old("old - Purchases of Raw Materials")
    assert classify("700013", "CA XC Goldspeed EAX").bu == "XC"


@pytest.mark.parametrize("code,kind,bu", [
    ("700010", "revenue", "XC"), ("700020", "revenue", "MODERN_RALLY"),
    ("700030", "revenue", "HISTORIC_RALLY"), ("700040", "revenue", "HISTORIC_RACING"),
    ("700050", "revenue", "CARS_OTHERS"), ("700000", "revenue", "UNASSIGNED"),
    ("700099", "revenue", "UNASSIGNED"), ("602019", "direct_cost", "XC"),
    ("603040", "direct_cost", "HISTORIC_RACING"), ("604050", "direct_cost", "CARS_OTHERS"),
    ("604099", "direct_cost", "UNASSIGNED"),
])
def test_classify(code, kind, bu):
    c = classify(code)
    assert (c.kind, c.bu) == (kind, bu)


@pytest.mark.parametrize("code", ["615001", "620200", "613010", "707010", "40000000", "60400000"])
def test_excluded_from_gross_margin(code):
    assert classify(code) is None


def test_aggregate():
    r = aggregate({"700010": -1000.0, "604010": 800.0, "700040": -500.0, "603040": 100.0, "615001": 999.0})
    assert r["total"]["ca"] == 1500 and r["total"]["margin"] == 600
    g = {x["key"]: x for x in r["groups"]}
    assert g["XC"]["margin"] == 200 and g["CARS"]["margin"] == 400


XLSX = os.environ.get("CHART_XLSX")


@pytest.mark.skipif(not XLSX, reason="CHART_XLSX non défini")
def test_every_live_pnl_account_is_mapped():
    """Vérifie contre l'export Odoo que chaque compte 602/603/604/700 actif a une BU connue."""
    import openpyxl
    rows = list(openpyxl.load_workbook(XLSX).active.iter_rows(values_only=True))[1:]
    for code, name, *_ in rows:
        name = (name or "").replace("\xa0", " ")
        if code[:3] in ("602", "603", "604", "700") and len(code) == 6 and not is_old(name):
            c = classify(code, name)
            assert c is not None
            if code[3:] not in ("000", "099"):
                assert c.bu != "UNASSIGNED", (code, name)
