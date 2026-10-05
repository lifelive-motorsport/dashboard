"""Lecture seule d'Odoo 19 via l'API externe JSON-2 (/json/2/<modèle>/<méthode>).

ATTENTION : non testé contre une vraie instance (aucun accès à ce stade) ; à valider
dès que la base Odoo.sh et la clé API de l'utilisateur technique sont disponibles.
"""
from __future__ import annotations

import re
from datetime import date

import httpx

from .. import settings

PNL_PREFIXES = ("602", "603", "604", "700")
READ_METHODS = frozenset({"search_read", "search_count", "read", "formatted_read_group", "read_group", "fields_get"})


class OdooProvider:
    name = "odoo"

    def __init__(self) -> None:
        self._http = httpx.Client(
            base_url=settings.ODOO_URL.rstrip("/"),
            headers={"Authorization": f"bearer {settings.ODOO_API_KEY}", "X-Odoo-Database": settings.ODOO_DB},
            timeout=30,
        )

    def _call(self, model: str, method: str, **payload):
        # Odoo n'a pas de clé API en lecture seule : la garantie est appliquée ici.
        if method not in READ_METHODS:
            raise PermissionError(f"Méthode Odoo non autorisée (lecture seule) : {method}")
        r =self._http.post(f"/json/2/{model}/{method}", json=payload)
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

    def top_clients(self, d_from: date, d_to: date) -> dict:
        raise NotImplementedError("Hit-parade clients : à implémenter (étape suivante)")

    def webshops(self, d_from: date, d_to: date) -> list[dict]:
        raise NotImplementedError("Webshops : à implémenter (étape suivante)")
