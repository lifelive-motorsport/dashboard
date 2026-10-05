"""Données FICTIVES (ordres de grandeur seulement) pour valider l'interface sans accès Odoo."""
from __future__ import annotations

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

    def balance_sheet(self) -> dict[str, float]:
        return {"receivables": 412_000.0, "payables": 298_000.0, "cash": 187_000.0}

    def top_clients(self, d_from: date, d_to: date) -> dict:
        rnd = random.Random(7)
        names = ["Client A", "Client B", "Client C", "Client D", "Client E", "Client F", "Client G", "Client H"]
        s = _scale(d_from, d_to)

        def board(total: float) -> list[dict]:
            w = sorted((rnd.random() ** 2 for _ in names), reverse=True)
            return [{"name": n, "ca": round(total * s * x / sum(w))} for n, x in zip(names, w)]

        return {"total": board(2_800_000), "XC": board(1_700_000), "MODERN_RALLY": board(160_000),
                "HISTORIC_RALLY": board(130_000), "HISTORIC_RACING": board(580_000)}

    def webshops(self, d_from: date, d_to: date) -> list[dict]:
        s = _scale(d_from, d_to)

        def shop(name, orders, revenue, basket, names):
            vals = [revenue * 0.9 * w / sum(range(1, len(names) + 1)) for w in range(len(names), 0, -1)]
            tot = sum(vals) / 0.6  # les produits listés ≈ 60 % du total
            return {"name": name, "orders": round(orders * s), "revenue": round(revenue * s), "avg_basket": basket,
                    "products": [{"name": n, "value": round(v * s), "units": round(v * s / 40, 2), "share": v / tot} for n, v in zip(names, vals)],
                    "products_total": {"value": round(tot * s), "units": round(tot * s / 40, 2), "count": 120}}
        return [shop("Webshop XC", 345, 188_000, 545.0, [f"[6000{i}] Produit exemple {i}" for i in range(1, 16)]),
                shop("Webshop Goldspeed", 274, 154_000, 561.0, [f"[3652{i}] Pneu exemple {i}" for i in range(1, 6)])]
