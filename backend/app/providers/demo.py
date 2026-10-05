"""Données FICTIVES (ordres de grandeur seulement) pour valider l'interface sans accès Odoo."""
from __future__ import annotations

import math
import random
from datetime import date


def _scale(d_from: date, d_to: date) -> float:
    return max((d_to - d_from).days + 1, 1) / 365


class DemoProvider:
    name = "demo"

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
            return [{"name": n, "ca": round(total * s * 0.8 * x / sum(w)), "open": round(total * s * 0.8 * x / sum(w) * (0.0 if i % 3 == 0 else 0.15 * (i % 5)))}
                    for i, (n, x) in enumerate(list(zip(names, w))[:15])]  # 15 premiers ≈ 80 % du CA

        out = {"total": board(2_800_000), "XC": board(1_700_000), "MODERN_RALLY": board(160_000),
               "HISTORIC_RALLY": board(130_000), "HISTORIC_RACING": board(580_000)}
        out["CARS"] = board(930_000)                         # vue agrégée (3 BU CARS + CARS Others)
        out["CARS_OTHERS"] = board(40_000)
        out["_open_totals"] = {k: round(sum(c["open"] for c in v) * 1.3) for k, v in out.items()}
        out["_meta"] = {"grouping": True, "groups": 0, "open": True}
        return out

    def top_suppliers(self, d_from: date, d_to: date) -> dict:
        rnd = random.Random(11)
        names = [f"Fournisseur {c}" for c in "ABCDEFGHIJKLMNOPQRST"]
        s = _scale(d_from, d_to)

        def board(total: float) -> list[dict]:
            w = sorted((rnd.random() ** 2 for _ in names), reverse=True)
            return [{"name": n, "ca": round(total * s * 0.75 * x / sum(w)), "open": round(total * s * 0.75 * x / sum(w) * (0.0 if i % 4 == 0 else 0.1 * (i % 4)))}
                    for i, (n, x) in enumerate(list(zip(names, w))[:15])]
        sizes = {"XC": 1_200_000, "MODERN_RALLY": 45_000, "HISTORIC_RALLY": 90_000, "HISTORIC_RACING": 300_000,
                 "CARS_OTHERS": 40_000, "HORS_BU": 520_000}
        sizes = {"total": sum(sizes.values()), **sizes}                       # le total est la somme des parties
        sizes["CARS"] = sizes["MODERN_RALLY"] + sizes["HISTORIC_RALLY"] + sizes["HISTORIC_RACING"] + sizes["CARS_OTHERS"]   # vue agrégée, hors total
        out = {k: board(v) for k, v in sizes.items()}
        out["_totals"] = {k: round(v * s) for k, v in sizes.items()}
        out["_open_totals"] = {k: round(sum(c["open"] for c in v) * 1.2) for k, v in out.items() if not k.startswith("_")}
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
