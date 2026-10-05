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
        return [{"name": "XC Cross Car", "orders": round(310 * s), "revenue": round(185_000 * s),
                 "avg_basket": 597.0, "top_products": ["Produit 1", "Produit 2", "Produit 3"]},
                {"name": "Goldspeed", "orders": round(95 * s), "revenue": round(42_000 * s),
                 "avg_basket": 442.0, "top_products": ["Produit 4", "Produit 5", "Produit 6"]}]
