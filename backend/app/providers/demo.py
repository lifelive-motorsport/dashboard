"""Données FICTIVES (ordres de grandeur seulement) pour valider l'interface sans accès Odoo."""
from __future__ import annotations

import math
import random
from datetime import date


def _scale(d_from: date, d_to: date) -> float:
    return max((d_to - d_from).days + 1, 1) / 365


class DemoProvider:
    name = "demo"

    def old_plan_revenue(self, d_from: date, d_to: date) -> float:
        return 0.0

    def pnl_balances(self, d_from: date, d_to: date) -> dict[str, float]:
        s = _scale(d_from, d_to)
        ca = {"700010": 1_300_000, "700011": 20_000, "700012": 60_000, "700013": 190_000, "700014": 30_000,
              "700020": 160_000, "700030": 130_000, "700040": 580_000, "700050": 30_000, "700099": 3_000}
        cost = {"604010": 1_210_000, "603010": 110_000, "602010": 85_000, "602011": 4_000, "602012": 50_000,
                "602013": 140_000, "604020": 30_000, "602020": 40_000, "604030": 90_000, "602030": 25_000,
                "604040": 220_000, "603040": 40_000, "602040": 130_000, "604050": 40_000, "602050": 30_000}
        out = {k: -v * s for k, v in ca.items()}
        out.update({k: v * s for k, v in cost.items()})
        return out

    def balance_sheet(self, year: int) -> dict[str, float]:
        return {"year": year, "receivables": 412_000.0, "payables": 298_000.0, "cash": 187_000.0}

    def top_clients(self, d_from: date, d_to: date) -> dict:
        rnd = random.Random(7)
        names = [f"Client {c}" for c in "ABCDEFGHIJKLMNOPQRST"]
        s = _scale(d_from, d_to)

        def board(total: float) -> list[dict]:
            w = sorted((rnd.random() ** 2 for _ in names), reverse=True)
            return [{"name": n, "ca": round(total * s * 0.8 * x / sum(w)), "open": round(total * s * 0.8 * x / sum(w) * (0.0 if i % 3 == 0 else 0.15 * (i % 5))),
                     "invoices": 3 + (i * 7) % 11, "avg": round(total * s * 0.8 * x / sum(w) / (3 + (i * 7) % 11), 2)}
                    for i, (n, x) in enumerate(list(zip(names, w))[:15])]  # 15 premiers ≈ 80 % du CA

        out = {"total": board(2_800_000), "XC": board(1_700_000), "MODERN_RALLY": board(160_000),
               "HISTORIC_RALLY": board(130_000), "HISTORIC_RACING": board(580_000)}
        out["CARS"] = board(930_000)                         # vue agrégée (3 BU CARS + CARS Others)
        out["CARS_OTHERS"] = board(40_000)
        out["_open_totals"] = {k: round(sum(c["open"] for c in v) * 1.3) for k, v in out.items()}
        out["_stats"] = {k: {"invoices": round(180 * s * (1 + len(v) / 15)), "avg": round(sum(c["ca"] for c in v) / max(1, sum(c["invoices"] for c in v)), 2)} for k, v in out.items() if not k.startswith("_")}
        out["_meta"] = {"grouping": True, "groups": 0, "open": True}
        return out

    def top_suppliers(self, d_from: date, d_to: date) -> dict:
        rnd = random.Random(11)
        names = [f"Fournisseur {c}" for c in "ABCDEFGHIJKLMNOPQRST"]
        s = _scale(d_from, d_to)

        def board(total: float) -> list[dict]:
            w = sorted((rnd.random() ** 2 for _ in names), reverse=True)
            return [{"name": n, "ca": round(total * s * 0.75 * x / sum(w)), "open": round(total * s * 0.75 * x / sum(w) * (0.0 if i % 4 == 0 else 0.1 * (i % 4))),
                     "invoices": 2 + (i * 5) % 13, "avg": round(total * s * 0.75 * x / sum(w) / (2 + (i * 5) % 13), 2),
                     "mix": {"604": round(total * s * 0.75 * x / sum(w) * (0.5 - 0.03 * (i % 5))), "603": round(total * s * 0.75 * x / sum(w) * (0.2 + 0.05 * (i % 4))),
                             "602": round(total * s * 0.75 * x / sum(w) * 0.15), "autres": round(total * s * 0.75 * x / sum(w) * 0.05)}}
                    for i, (n, x) in enumerate(list(zip(names, w))[:15])]
        sizes = {"XC": 1_200_000, "MODERN_RALLY": 45_000, "HISTORIC_RALLY": 90_000, "HISTORIC_RACING": 300_000,
                 "CARS_OTHERS": 40_000, "HORS_BU": 520_000}
        sizes = {"total": sum(sizes.values()), **sizes}                       # le total est la somme des parties
        sizes["CARS"] = sizes["MODERN_RALLY"] + sizes["HISTORIC_RALLY"] + sizes["HISTORIC_RACING"] + sizes["CARS_OTHERS"]   # vue agrégée, hors total
        out = {k: board(v) for k, v in sizes.items()}
        out["_totals"] = {k: round(v * s) for k, v in sizes.items()}
        out["_open_totals"] = {k: round(sum(c["open"] for c in v) * 1.2) for k, v in out.items() if not k.startswith("_")}
        out["_mix"] = {k: {"604": round(out["_totals"][k] * .45), "603": round(out["_totals"][k] * .25), "602": round(out["_totals"][k] * .2), "autres": round(out["_totals"][k] * .1)} for k in sizes}
        out["_stats"] = {k: {"invoices": round(240 * s * (1 + len(v) / 15)), "avg": round(sum(c["ca"] for c in v) / max(1, sum(c["invoices"] for c in v)), 2)} for k, v in out.items() if not k.startswith("_")}
        out["_meta"] = {"grouping": True, "groups": 0, "open": True}
        return out

    def events(self, d_from: date, d_to: date) -> dict:
        s = _scale(d_from, d_to)
        demo = [("Meeting A (démo)", "XC", 180_000, 120_000, 22_000, 0), ("Meeting B (démo)", "XC", 95_000, 80_000, 18_000, 0),
                ("Meeting C (démo)", "CARS", 140_000, 70_000, 30_000, 0), ("Meeting D (démo)", "CARS", 41_500, 35_000, 3_500, 36_000),
                ("Meeting E (démo)", "OTHERS", 12_000, 0, 4_000, 0)]
        out = [{"id": i, "name": n, "plan": "MEETING", "group": g, "ca": round(ca * s), "direct_costs": round(dc * s), "other_costs": round(oc * s),
                "capex": round(cx * s), "amort": round(cx * s / 60 * 5), "amort_monthly": round(cx / 60) if cx else 0, "amort_months": 60 if cx else 0,
                "result": round((ca - dc - oc - cx) * s), "result_accounting": round((ca - dc - oc - cx / 12) * s), "mixed": i == 4,
                "bus": ([{"bu": "XC", "share": 1.0}] if g == "XC" else [{"bu": "Historic Racing", "share": 0.7}, {"bu": "Modern Rally", "share": 0.3}] if g == "CARS" else [])} for i, (n, g, ca, dc, oc, cx) in enumerate(demo, 1)]
        return {"events": out, "plans": ["MEETING"], "bu_axis": "BU", "bu_unmapped": [], "bu_missing": 0}

    def vehicles(self, d_from: date, d_to: date) -> dict:
        s = _scale(d_from, d_to)
        demo = [("Porsche 992 Rally GT #26 (démo)", "Modern Rally", "Client A", "Modern Rally", 236_000, 190_000, 8_000, 0),
                ("BMW M3 E30 #44 (démo)", "Historic Rally", "Client B", "Historic Rally", 62_000, 41_000, 3_000, 0),
                ("Aston Martin Vantage GT3 (démo)", "Historic Racing", "Client C", "Historic Racing / GT3", 39_000, 21_000, 2_500, 15_000)]
        out = [{"id": i, "name": n, "plan": "CARS", "group": "CARS", "client": c, "reference": ref, "ca": round(ca * s), "direct_costs": round(dc * s),
                "other_costs": round(oc * s), "capex": round(cx * s), "amort": round(cx * s / 12), "amort_monthly": round(cx / 60) if cx else 0,
                "amort_months": 60 if cx else 0, "result": round((ca - dc - oc - cx) * s), "result_accounting": round((ca - dc - oc - cx / 12) * s),
                "mixed": False, "bus": [{"bu": bu, "share": 1.0}]} for i, (n, bu, c, ref, ca, dc, oc, cx) in enumerate(demo, 1)]
        return {"vehicles": out, "plans": ["CARS"], "bu_axis": "BU", "bu_unmapped": [], "bu_missing": 0}

    def marketing(self, d_from: date, d_to: date) -> dict:
        from .odoo import OdooProvider
        gran, buckets = OdooProvider._buckets(d_from, d_to)
        pts = [{"label": lbl, "avg": float(3000 + 700 * ((i * 3) % 5)), "total": 3000 + 700 * ((i * 3) % 5), "by_account": {}} for i, (_, lbl) in enumerate(buckets)]
        tot = sum(p["total"] for p in pts)
        accs = [("602019", "Frais XC Sales & Marketing", .5), ("602059", "Frais CARS Sales & Marketing", .3), ("612050", "Frais marketing génériques", .2)]
        return {"total": tot, "codes": [a[0] for a in accs], "series": {"granularity": gran, "points": pts},
                "accounts": [{"code": c, "name": n, "amount": round(tot * s), "share": s} for c, n, s in accs],
                "suppliers": [{"name": f"Fournisseur marketing {i}", "amount": round(tot * .3 / i), "share": .3 / i, "invoices": 2 + i} for i in range(1, 9)],
                "invest": {"year": d_to.year, "total": 11000, "amort": 1100, "amort_monthly": 183.33, "accounts": ["240050"],
                           "items": [{"label": "Création & Développement d'un système graphique", "capex": 5500, "partner": "Actaeon Conseils", "bills": [{"ref": "FACTU/2026/02/0072", "date": "2026-02-24"}, {"ref": "FACTU/2026/04/0013", "date": "2026-04-03"}], "amort": 550, "amort_monthly": 91.67, "amort_months": 60},
                                     {"label": "Package Social Media Almeira 2026", "capex": 5500, "partner": "Actaeon Conseils", "bills": [{"ref": "FACTU/2026/04/0013", "date": "2026-04-03"}], "amort": 550, "amort_monthly": 91.67, "amort_months": 60}]}}

    def tags_overview(self) -> dict:
        return {"invest_tag": "invest marketing", "tags": [{"name": "regroup_client=Koramic / C.Dumolin", "kind": "client", "count": 3},
                {"name": "regroup_fournisseur=Pirelli", "kind": "fournisseur", "count": 2}, {"name": "invest marketing", "kind": "invest", "count": 1}]}

    def staff_accounting(self, year: int) -> dict:
        months = [f"{year}-{m:02d}" for m in range(1, 10)]
        pay = {m: 9000 + 100 * i for i, m in enumerate(months)}
        other = {m: 1200 for m in months}
        acc = [{"code": "620000", "name": "Rémunérations", "pay": True, "by_month": {m: round(v * .75) for m, v in pay.items()}, "total": round(sum(pay.values()) * .75)},
               {"code": "621000", "name": "Cotisations patronales", "pay": True, "by_month": {m: round(v * .25) for m, v in pay.items()}, "total": round(sum(pay.values()) * .25)},
               {"code": "623000", "name": "Autres frais de personnel", "pay": False, "by_month": other, "total": sum(other.values())}]
        return {"year": year, "pay_prefixes": ["620", "621"], "accounts": acc, "pay_by_month": pay, "other_by_month": other,
                "director": {"pay_accounts": ["618000"], "social_accounts": ["618001"], "pay_by_month": {m: 3130 for m in months}, "social_by_month": {m: 900 for m in months}}}

    def expenses_lines(self, year: int) -> list[dict]:
        rnd = random.Random(11)
        spec = [("611000", "Entretien et réparations", 900), ("611100", "Entretien véhicules", 700), ("612000", "Électricité, gaz, eau", 1500), ("612010", "Fournitures de bureau", 400),
                ("613000", "Honoraires", 6000), ("614000", "Publicité", 300), ("640000", "Taxes diverses", 450), ("615021", "Carburant Util. CITAN", 380), ("615022", "Assurance Util. CITAN", 110), ("615031", "Carburant Util. SPRINTER", 900), ("615032", "Entretien Util. SPRINTER", 350), ("604010", "Achats XC", 30000), ("620000", "Rémunérations", 40000), ("612050", "Marketing", 800)]
        out = []
        for code, name, base in spec:
            by = {f"{year}-{m:02d}": round(base * (0.8 + rnd.random() * 0.4), 2) for m in range(1, 10)}
            out.append({"code": code, "name": name, "total": sum(by.values()), "by_month": by,
                        "partners": {1: {"name": "Fournisseur A", "amount": sum(by.values()) * 0.6, "by_month": {m: v * 0.6 for m, v in by.items()}},
                                     2: {"name": "ADC St-Vith (comptable)" if code == "613000" else "Fournisseur B", "amount": sum(by.values()) * 0.4, "by_month": {m: v * 0.4 for m, v in by.items()}}}})
        return out

    def expenses_excluded(self, year: int) -> list[dict]:
        return [{"code": "611010", "name": "Loyer Batiment", "date": f"{year}-07-31", "amount": 21000.0, "move": f"DIV/{year}/07/0001", "label": "Loyer 01-07/26"}]

    def expenses_month(self, month: str) -> list[dict]:
        rnd = random.Random(int(month[5:7]))
        return [{"code": c, "name": n, "date": f"{month}-{rnd.randint(1, 28):02d}", "amount": round(rnd.random() * (30000 if c == "611010" and month.endswith("07") else 1500), 2), "partner_id": 1 + i % 2,
                 "partner": "Fournisseur A" if i % 2 == 0 else "ADC St-Vith", "move": f"FACT/{month}/{i:04d}", "label": f"Facture {n}"}
                for i, (c, n) in enumerate([("611010", "Loyer"), ("612000", "Électricité"), ("612010", "Fournitures"), ("614000", "Publicité"), ("640000", "Taxes")])]

    def fuel_invoices(self, year: int) -> list[dict]:
        return [{"id": 100 + m, "number": f"DKV/{year}/{m:02d}", "ref": f"DKV-{m:02d}", "date": f"{year}-{m:02d}-28", "untaxed": 1200.0 + 40 * m, "total": 1452.0 + 48 * m, "paid": m < 9, "refund": False,
                 "attachments": [{"id": 900 + m, "name": f"DKV_{year}_{m:02d}.pdf", "mimetype": "application/pdf", "size": 52000}],
                 "lines": [{"code": "615021", "name": "Carburant Util. CITAN", "amount": 300.0 + 10 * m}, {"code": "615031", "name": "Carburant Util. SPRINTER", "amount": 900.0 + 30 * m}], "other": []} for m in range(1, 10)]

    def fuel_attachment(self, att_id: int, year: int, allowed=None):
        m = att_id - 900
        txt = (f"DKV Euro Service\nMonnaie: EUR\nVEHICLE: 2BNC759 CARD NO.: 704310.0113082777\n"
               f"01.{m:02d}.{year}   SHELL   ST. VITH   1098661   6521520062 09:33   78000 GAZOLE   0009 LTR   63,260   1,9280   1,5934   100,80   -1,27   1,21   100,74   0,00   100,74\n"
               f"08.{m:02d}.{year}   SHELL   ST. VITH   1098661   6526520130 13:17   80000 GAZOLE   0009 LTR   39,000   1,9280   1,5934   62,15   -0,70   0,70   62,15   0,00   62,15\n"
               f"VEHICLE: 2CEP774 CARD NO.: 704310.0113082999\n"
               f"03.{m:02d}.{year}   SHELL   ST. VITH   1098661   6526520999 08:00   120000 GAZOLE   0009 LTR   70,000   1,9280   1,5934   111,54   -1,00   1,00   111,54   0,00   111,54\n")
        return txt.encode(), "text/plain", "demo.txt"

    def staff_partners(self, q: str) -> list[dict]:
        return [{"id": 9001, "name": "Société exemple SRL", "vat": "BE0123456789", "city": "Liège"}, {"id": 9002, "name": "Consulting exemple SA", "vat": "", "city": "Namur"}]

    def staff_invoices(self, partner_ids: list[int], year: int) -> list[dict]:
        return [{"number": f"FACTU/{year}/0{i}", "ref": f"F{i}", "date": f"{year}-0{i}-15", "untaxed": 4500.0, "fees": 4000.0 if i % 2 else 4500.0, "total": 5445.0, "paid": i < 4, "partner": "Société exemple SRL", "refund": False} for i in range(1, 6)]

    def stock_report(self) -> dict:
        from ..stock import build_report
        rnd = random.Random(5)
        items = [{"ref": f"6{i:05d}", "name": f"Pièce exemple {i}" + (" left" if i % 40 == 1 else " right" if i % 40 == 2 else ""), "pif": "N" if i % 2 else ("F" if i % 3 else ""),
                  "cost": round(rnd.random() ** 2 * 800, 2), "qty": float(rnd.randint(-3, 60)) if i % 50 else 2989.0, "uom": "Units"} for i in range(1, 400)]
        return build_report(items, "x_pif")

    def webshops(self, d_from: date, d_to: date) -> list[dict]:
        s = _scale(d_from, d_to)

        def shop(name, orders, revenue, basket, names):
            vals = [revenue * 0.9 * w / sum(range(1, len(names) + 1)) for w in range(len(names), 0, -1)]
            tot = sum(vals) / 0.6  # les produits listés ≈ 60 % du total
            from .odoo import OdooProvider
            gran, buckets = OdooProvider._buckets(d_from, d_to)
            pts = [{"label": lbl, "orders": 20 + i, "revenue": round((basket + 25 * math.sin(i + len(name))) * (20 + i)),
                    "avg": round(basket + 25 * math.sin(i + len(name)), 2)} for i, (_, lbl) in enumerate(buckets)]
            return {"name": name, "orders": round(orders * s), "revenue": round(revenue * s), "avg_basket": basket,
                    "basket_series": {"granularity": gran, "points": pts},
                    "pickings": {k: {"weeks": 12, "orders": 150, "units": 520, "per_order": 3.5,
                                     "points": [{"label": f"{(i % 4) * 7 + 1} sept.", "orders": 10 + (i * 5) % 9 + (k == "all") * 6, "units": 28 + (i * 11) % 30 + (k == "all") * 20,
                                                 "per_order": 3.2 + (i % 4) * 0.4} for i in range(12)]} for k in ("web", "all")},
                    "customers": {"customers": [{"name": f"Client exemple {i}", "ca": round(revenue * s * (0.09 / i)), "orders": 6 - i // 3, "avg_basket": round(revenue * s * 0.09 / i / max(1, 6 - i // 3)),
                                                 "share": 0.09 / i, "country": ("Belgique", "France", "Allemagne")[i % 3], "last_order": f"2026-09-{28 - i:02d}",
                                                 "payments": [{"name": "Carte bancaire", "count": 3}, {"name": "PayPal", "count": 1}],
                                                 "deliveries": [{"name": "Livraison standard", "count": 4}]} for i in range(1, 16)],
                                  "total_ca": round(revenue * s), "total_orders": round(orders * s), "count": round(orders * s * 0.7), "repeat": round(orders * s * 0.15), "top_ca": round(revenue * s * 0.45)},
                    "visits": {"granularity": gran, "views": round(orders * s * 38), "visitors": round(orders * s * 11), "path": "/shop",
                               "points": [{"label": p["label"], "views": 900 + 60 * ((i * 7) % 9), "visitors": 260 + 15 * ((i * 5) % 7), "avg": float(900 + 60 * ((i * 7) % 9))} for i, p in enumerate(pts)]},
                    "top_pages": [{"label": f"Page produit exemple {i}", "path": f"/shop/produit-exemple-{i}-{100 + i}", "views": 1200 // i, "share": (1200 // i) / 3000} for i in range(1, 16)],
                    "payments": [{"name": n, "count": round(orders * s * sh), "share": sh, "amount": round(revenue * s * sh)}
                                 for n, sh in (("Carte bancaire", .62), ("Bancontact", .21), ("PayPal", .12), ("Virement bancaire", .05))],
                    "deliveries": [{"name": n, "count": round(orders * s * sh), "share": sh, "amount": round(revenue * s * sh)}
                                   for n, sh in (("Livraison standard", .58), ("Livraison express", .27), ("Retrait à l'atelier", .10), ("Sans livraison (retrait, service…)", .05))],
                    "abandoned": {"count": round(orders * s * .8), "identified": round(orders * s * .2), "anonymous": round(orders * s * .6), "amount": round(revenue * s * .7), "rate": .44,
                                  "series": {"granularity": gran, "points": [{"label": p["label"], "orders": p["orders"], "abandoned": 15 + i % 5, "identified": 4,
                                                                              "amount": 9000 + 800 * (i % 5), "avg": round((15 + i % 5) / (35 + i % 5 + i), 4)} for i, p in enumerate(pts)]}},
                    "products": [{"name": n, "value": round(v * s), "units": round(v * s / 40, 2), "share": v / tot} for n, v in zip(names, vals)],
                    "products_total": {"value": round(tot * s), "units": round(tot * s / 40, 2), "count": 120}}
        return [shop("Webshop XC", 345, 188_000, 545.0, [f"[6000{i}] Produit exemple {i}" for i in range(1, 16)]),
                shop("Webshop Goldspeed", 274, 154_000, 561.0, [f"[3652{i}] Pneu exemple {i}" for i in range(1, 6)])]
