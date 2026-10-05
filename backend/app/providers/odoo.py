"""Lecture seule d'Odoo 19 via l'API externe JSON-2 (/json/2/<modèle>/<méthode>).

ATTENTION : non testé contre une vraie instance (aucun accès à ce stade) ; à valider
dès que la base Odoo.sh et la clé API de l'utilisateur technique sont disponibles.
"""
from __future__ import annotations

import re
from datetime import date, timedelta

import httpx

from .. import settings

PNL_PREFIXES = ("602", "603", "604", "700")


class OdooProvider:
    name = "odoo"

    def __init__(self) -> None:
        key, db = settings.ODOO_API_KEY.strip(), settings.ODOO_DB.strip()
        if not key or not key.isascii() or not key.isprintable() or " " in key or len(key) > 128:
            # Sans jamais afficher la valeur : seule sa forme est décrite.
            raise RuntimeError(f"ODOO_API_KEY invalide (longueur {len(key)}, ASCII={key.isascii()}) : "
                               "elle doit être une seule ligne de lettres/chiffres, sans espace ni accent")
        self._http = httpx.Client(
            base_url=settings.ODOO_URL.strip().rstrip("/"),
            headers={"Authorization": f"bearer {key}", "X-Odoo-Database": db},
            timeout=30,
        )

    def _call(self, model: str, method: str, **payload):
        r = self._http.post(f"/json/2/{model}/{method}", json=payload)
        r.raise_for_status()
        return r.json()

    def _grouped(self, domain: list, groupby: list[str]) -> list[dict]:
        return self._call("account.move.line", "formatted_read_group",
                          domain=domain, groupby=groupby, aggregates=["balance:sum"])

    def pnl_balances(self, d_from: date, d_to: date) -> dict[str, float]:
        any_prefix = ["|"] * (len(PNL_PREFIXES) - 1) + [("account_id.code", "=like", f"{p}%") for p in PNL_PREFIXES]
        domain = [("parent_state", "=", "posted"), ("date", ">=", d_from.isoformat()),
                  ("date", "<=", d_to.isoformat()), *any_prefix]
        out: dict[str, float] = {}
        for row in self._grouped(domain, ["account_id"]):
            acc = row["account_id"]  # [id, "700010 CA XC Manufacturer"]
            m = re.match(r"^\s*(\d+)", acc[1])
            if m and not re.match(r"^\s*\d+\s+old\b", acc[1], re.I):
                out[m.group(1)] = out.get(m.group(1), 0.0) + row["balance:sum"]
        return out

    def balance_sheet(self) -> dict[str, float]:
        def total(types: list[str]) -> float:
            rows = self._grouped([("parent_state", "=", "posted"), ("account_id.account_type", "in", types)], [])
            return rows[0]["balance:sum"] if rows else 0.0
        return {"receivables": total(["asset_receivable"]), "payables": -total(["liability_payable"]),
                "cash": total(["asset_cash", "liability_credit_card"])}

    def top_clients(self, d_from: date, d_to: date, limit: int = 10) -> dict:
        """Classement des clients par CA (comptes 700) : total et par BU. Lecture seule."""
        from ..bu import classify
        domain = [("parent_state", "=", "posted"), ("date", ">=", d_from.isoformat()),
                  ("date", "<=", d_to.isoformat()), ("account_id.code", "=like", "700%"),
                  ("partner_id", "!=", False)]
        by_bu: dict[str, dict[str, float]] = {}
        names: dict[int, str] = {}
        for row in self._grouped(domain, ["partner_id", "account_id"]):
            m = re.match(r"^\s*(\d+)", row["account_id"][1])
            c = m and classify(m.group(1), re.sub(r"^\s*\d+\s*", "", row["account_id"][1]))
            if not c:
                continue
            pid, pname = row["partner_id"]
            names[pid] = pname
            by_bu.setdefault(c.bu, {}).setdefault(pid, 0.0)
            by_bu[c.bu][pid] -= row["balance:sum"]  # crédit = CA

        def board(per_partner: dict[int, float]) -> list[dict]:
            top = sorted(per_partner.items(), key=lambda kv: -kv[1])[:limit]
            return [{"name": names[pid], "ca": round(v)} for pid, v in top if v > 0]

        total: dict[int, float] = {}
        for per in by_bu.values():
            for pid, v in per.items():
                total[pid] = total.get(pid, 0.0) + v
        out = {"total": board(total)}
        for bu, per in by_bu.items():
            out[bu] = board(per)
        return out

    def webshops(self, d_from: date, d_to: date) -> list[dict]:
        """Ventes des sites web (commandes confirmées, HT). Libellés dans settings.WEBSHOP_LABELS."""
        base = [("state", "in", ["sale", "done"]), ("date_order", ">=", d_from.isoformat()),
                ("date_order", "<", (d_to + timedelta(days=1)).isoformat())]
        out = []
        groups = self._call("sale.order", "formatted_read_group", domain=base + [("website_id", "!=", False)],
                            groupby=["website_id"], aggregates=["amount_untaxed:sum", "__count"])
        for g in groups:
            wid, wname = g["website_id"]
            n, revenue = g["__count"], g["amount_untaxed:sum"]
            lines = self._call("sale.order.line", "formatted_read_group", groupby=["product_id"],
                               domain=[("order_id.website_id", "=", wid), ("order_id.state", "in", ["sale", "done"]),
                                       ("product_id.type", "!=", "service"),  # hors livraison, ports, etc.
                                       ("order_id.date_order", ">=", d_from.isoformat()),
                                       ("order_id.date_order", "<", (d_to + timedelta(days=1)).isoformat())],
                               aggregates=["price_subtotal:sum"], order="price_subtotal:sum desc", limit=5)
            out.append({"name": settings.WEBSHOP_LABELS.get(wname, wname), "orders": n, "revenue": round(revenue),
                        "avg_basket": round(revenue / n, 2) if n else 0.0,
                        "top_products": [l["product_id"][1] for l in lines if l.get("product_id")]})
        return sorted(out, key=lambda w: -w["revenue"])
