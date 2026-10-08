from fastapi.testclient import TestClient

from app import tn11
from app.main import app

SAMPLE = """Nom du client : POST - FIA

  Ref LL                                        DESIGNATION EN                        Qté    INCLUS (X) :

            SUBSET FRAME
  205089    TN11 Tubular frame with all welded brackets not painted   1,00        x

            SUBSET FRONT ARM
  205167    TN11 Front down left arm Complete                         1,00        x
  205090    TN11 Front down left arm                                  1,00
  611013    Snap ring FH-028                                          1,00
  330073    Uniball M12 right thread (Fluro)                          2,00

            SUBSET STEERING
            Washer diameter 13                                        2,00        x

            OPTIONS
  611669    Front L upright TN11 Complete CNC                         1,00        x

            SUBSET MOUNTING
  205164    Complete mounting chassis                                 1,00        x
                                                       TOTAL HT   1 234,50 €
                                                       TVA 21%      259,25 €
"""


def test_parse_quote_reads_sold_lines_sections_and_total():
    p = tn11.parse_quote(SAMPLE)
    assert p["client"] == "POST - FIA" and p["total_ht"] == 1234.50 and len(p["lines"]) == 8
    sold = [l for l in p["lines"] if l["included"]]
    assert [l["ref"] for l in sold] == ["205089", "205167", "", "611669", "205164"]
    assert sold[1]["section"] == "Front Arm" and sold[2]["name"] == "Washer diameter 13" and sold[2]["qty"] == 2.0 and sold[3]["option"] is True
    assert not any(l["included"] for l in p["lines"] if l["ref"] in ("205090", "611013", "330073"))


INFO = {1: {"id": 1, "ref": "205089", "name": "Châssis nu", "sale": 3000.0, "cost": 2500.0, "type": "consu", "categ": "Châssis"},
        2: {"id": 2, "ref": "205167", "name": "Triangle avant complet", "sale": 200.0, "cost": 120.0, "type": "consu", "categ": "Triangles"},
        3: {"id": 3, "ref": "205090", "name": "Triangle nu", "sale": 0.0, "cost": 50.0, "type": "consu", "categ": "Pièces"},
        4: {"id": 4, "ref": "330073", "name": "Rotule", "sale": 30.0, "cost": 15.0, "type": "consu", "categ": "Pièces"},
        5: {"id": 5, "ref": "611100", "name": "Soudure triangle", "sale": 0.0, "cost": 20.0, "type": "service", "categ": "Services"},
        6: {"id": 6, "ref": "205164", "name": "Complete mounting chassis", "sale": 800.0, "cost": 600.0, "type": "service", "categ": "Services"}}
BOMS = {2: {"qty": 1.0, "lines": [{"product": 3, "qty": 1.0}, {"product": 4, "qty": 2.0}, {"product": 5, "qty": 1.0}],
            "operations": [{"name": "Montage triangle", "workcenter": "Atelier", "minutes": 30.0, "cost_hour": 60.0}]}}
UNIT = {3: 62.0, 4: 18.0, 1: 2900.0}                       # coût réel unitaire connu (achats) ; le service 5 n'en a pas -> coût Odoo


def test_build_report_costs_labour_and_flags():
    p = tn11.parse_quote(SAMPLE)
    products = {i["ref"]: i for i in INFO.values()}
    r = tn11.build_report(p, products, BOMS, INFO, UNIT.get, 0.0)
    by = {x["ref"]: x for x in r["rows"] if x["included"]}
    tri = by["205167"]
    assert tri["sale_total"] == 200.0 and tri["odoo"] == 120.0 and tri["has_bom"] is True
    assert tri["real"] == 62.0 + 2 * 18.0 + 20.0 + 30.0                         # composants (62 + 2 × 18) + service au coût Odoo (20) + opération 30 min × 60 €/h
    kinds = sorted(l["kind"] for l in tri["labour"])
    assert kinds == ["article", "operation"] and tri["labour_cost"] == 50.0 and tri["labour_minutes"] == 30.0
    assert tri["margin"]["theoretical"] == 40.0 and tri["margin"]["real"] == round((200 - 148) / 200 * 100, 2)
    frame = by["205089"]
    assert frame["real"] == 2900.0 and frame["has_bom"] is False and frame["labour_cost"] == 0.0
    assert by["205164"]["self_labour"] and by[""]["found"] is False and r["unmatched"] == 2                  # 611669 absent d'Odoo ici, et la ligne sans référence
    assert r["totals"]["labour_cost"] == 50.0 + by["205164"]["real"]            # la ligne vendue qui est de la main-d'œuvre compte en entier
    assert r["totals"]["gap_pdf"] == round(r["totals"]["sale"] - 1234.50, 2)


def test_tn11_endpoint_rejects_non_pdf_and_reports_demo(monkeypatch):
    c = TestClient(app)
    assert c.post("/api/xc/tn11/check", content=b"pas un pdf").status_code == 422
    monkeypatch.setattr("app.main.dkv.extract_text", lambda *a, **k: SAMPLE)
    r = c.post("/api/xc/tn11/check", content=b"%PDF-1.4 faux")
    assert r.status_code == 200
    j = r.json()
    assert j["client"] == "POST - FIA" and j["pdf_total"] == 1234.5 and any(x["found"] for x in j["rows"]) and "labour_like" in j
    monkeypatch.setattr("app.main.dkv.extract_text", lambda *a, **k: "rien d'utile")
    assert c.post("/api/xc/tn11/check", content=b"%PDF-1.4 faux").status_code == 422


def test_parts_outlier_and_hours_labour(monkeypatch):
    from app import tn11
    info = {1: {"ref": "A1", "name": "Bras", "cost": 105.0, "type": "consu", "categ": ""},
            2: {"ref": "C1", "name": "Pièce", "cost": 67.0, "type": "consu", "categ": ""},
            3: {"ref": "810005", "name": "Hourly Rate XC Pre-Assembly", "cost": 37.5, "type": "consu", "categ": ""}}
    boms = {1: {"qty": 1.0, "operations": [], "lines": [{"product": 2, "qty": 1.0, "uom": "Units"}, {"product": 3, "qty": 0.3, "uom": "Hours"}]}}
    real = {2: 5000.0, 3: 37.5}
    r = tn11.line_costs(1, 1, boms, info, real.get)
    assert any(p["warn"] and p["ref"] == "C1" for p in r["parts"])
    assert abs(r["real"] - (67 + 0.3 * 37.5)) < 0.01
    assert r["labour"] and r["labour"][0]["reason"] == "quantité en heures"
