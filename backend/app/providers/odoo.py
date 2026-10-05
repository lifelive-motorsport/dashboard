"""Lecture seule d'Odoo 19 via l'API externe JSON-2 (/json/2/<modèle>/<méthode>).

ATTENTION : non testé contre une vraie instance (aucun accès à ce stade) ; à valider
dès que la base Odoo.sh et la clé API de l'utilisateur technique sont disponibles.
"""
from __future__ import annotations

import logging
import re
from datetime import date, timedelta

import httpx

from .. import settings
from ..names import normalize_name

log = logging.getLogger("dashboard.odoo")
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

    def _open_invoices(self, move_types: list[str], year: int) -> float:
        """Montant restant dû (signé, devise société) des factures ET AVOIRS validés non payés ou partiellement payés dont
        la date comptable est dans l'année de référence. Critères de l'écran Odoo « Vendor bills to pay » (statut comptabilisé,
        paiement non payé / partiel), avoirs en plus : un avoir réduit la dette. Les brouillons, les accruals
        (« factures à recevoir ») et les écritures hors factures sont exclus."""
        rows = self._call("account.move", "formatted_read_group",
                          domain=[("state", "=", "posted"), ("move_type", "in", move_types),
                                  ("payment_state", "in", ["not_paid", "partial"]),
                                  ("date", ">=", f"{year}-01-01"), ("date", "<=", f"{year}-12-31")],
                          groupby=[], aggregates=["amount_residual_signed:sum"])
        return float(rows[0]["amount_residual_signed:sum"] or 0.0) if rows else 0.0

    def balance_sheet(self, year: int) -> dict[str, float]:
        """Créances et dettes = factures et avoirs ouverts de l'année `year` ; trésorerie = soldes à date des comptes bancaires/caisse/cartes."""
        rows = self._grouped([("parent_state", "=", "posted"),
                              ("account_id.account_type", "in", ["asset_cash", "liability_credit_card"])], [])
        return {"year": year,
                "receivables": self._open_invoices(["out_invoice", "out_refund"], year),
                "payables": -self._open_invoices(["in_invoice", "in_refund"], year),  # dette affichée positive, avoirs déduits
                "cash": rows[0]["balance:sum"] if rows else 0.0}

    # Regroupement de clients : étiquette de contact Odoo « regroup_client=Nom du groupe »
    TAG = re.compile(r"^\s*regroup_client\s*=\s*(.+?)\s*$", re.IGNORECASE)

    def _client_groups(self, partner_ids: set[int]) -> dict[int, tuple[str, str]]:
        """partner_id -> (clé, libellé).

        1) les contacts d'une même société sont fusionnés (commercial_partner_id) ;
        2) une étiquette « regroup_client=X » sur le contact ou sur sa société regroupe tout ce qui porte X.
        """
        fields = ["display_name", "commercial_partner_id", "category_id"]
        by_id = {x["id"]: x for x in self._call("res.partner", "read", ids=sorted(partner_ids), fields=fields)}
        missing = {x["commercial_partner_id"][0] for x in by_id.values() if x.get("commercial_partner_id")} - by_id.keys()
        if missing:
            by_id.update({x["id"]: x for x in self._call("res.partner", "read", ids=sorted(missing), fields=fields)})
        tag_ids = {t for x in by_id.values() for t in (x.get("category_id") or [])}
        tags = {t["id"]: t["name"] for t in self._call("res.partner.category", "read", ids=sorted(tag_ids), fields=["name"])} if tag_ids else {}
        out: dict[int, tuple[str, str]] = {}
        for pid in partner_ids:
            me = by_id.get(pid)
            if not me:
                continue
            com = by_id.get(me["commercial_partner_id"][0], me) if me.get("commercial_partner_id") else me
            names = sorted({m.group(1) for t in (me.get("category_id") or []) + (com.get("category_id") or [])
                            if (m := self.TAG.match(tags.get(t, "")))}, key=str.lower)
            if names:
                if len(names) > 1:
                    log.warning("Plusieurs étiquettes regroup_client sur le contact %s : %s", pid, names)
                out[pid] = ("g:" + names[0].lower(), names[0])
            else:
                out[pid] = (f"c:{com['id']}", com["display_name"])
        return out

    def top_clients(self, d_from: date, d_to: date, limit: int = 15) -> dict:
        """Classement des clients par CA (comptes 700) : total et par BU, avec regroupement. Lecture seule."""
        from ..bu import classify
        domain = [("parent_state", "=", "posted"), ("date", ">=", d_from.isoformat()),
                  ("date", "<=", d_to.isoformat()), ("account_id.code", "=like", "700%"),
                  ("partner_id", "!=", False)]
        by_bu: dict[str, dict[int, float]] = {}
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

        meta = {"grouping": True, "groups": 0}
        try:
            groups = self._client_groups(set(names))
        except Exception:  # droits insuffisants, etc. : on garde les noms tels que saisis
            log.exception("Regroupement de clients indisponible")
            groups, meta["grouping"] = {}, False
        label: dict[str, str] = {}

        def key_of(pid: int) -> str:
            k, lab = groups.get(pid, (f"p:{pid}", names[pid]))
            label.setdefault(k, lab)
            return k

        def board(per_partner: dict[int, float]) -> list[dict]:
            agg: dict[str, float] = {}
            for pid, v in per_partner.items():
                agg[key_of(pid)] = agg.get(key_of(pid), 0.0) + v
            top = sorted(agg.items(), key=lambda kv: -kv[1])[:limit]
            return [{"name": normalize_name(label[k]), "ca": round(v)} for k, v in top if v > 0]   # affichage uniformisé

        total: dict[int, float] = {}
        for per in by_bu.values():
            for pid, v in per.items():
                total[pid] = total.get(pid, 0.0) + v
        out = {"total": board(total)}
        for bu, per in by_bu.items():
            out[bu] = board(per)
        meta["groups"] = len({k for k in label if k.startswith("g:")})
        out["_meta"] = meta
        return out

    def _fr_lang(self) -> str | None:
        """Code de la langue française installée dans Odoo (fr_BE de préférence), sinon None."""
        if not hasattr(self, "_lang"):
            try:
                codes = {l["code"] for l in self._call("res.lang", "search_read", domain=[("active", "=", True)], fields=["code"])}
                self._lang = next((c for c in ("fr_BE", "fr_FR") if c in codes), next((c for c in sorted(codes) if c.startswith("fr")), None))
            except Exception:
                log.exception("Langue française indisponible : noms de produits dans la langue par défaut")
                self._lang = None
        return self._lang

    def _product_names(self, ids: list[int], fallback: dict[int, str]) -> dict[int, str]:
        """Nom de chaque produit, en français si possible (« [référence] Nom »)."""
        lang = self._fr_lang()
        if not lang or not ids:
            return fallback
        try:
            rows = self._call("product.product", "read", ids=ids, fields=["display_name"],
                              context={"lang": lang, "active_test": False})
            return {**fallback, **{r["id"]: r["display_name"] for r in rows}}
        except Exception:
            log.exception("Traduction des produits indisponible")
            return fallback

    def webshops(self, d_from: date, d_to: date, top: int = 15) -> list[dict]:
        """Ventes des sites web (commandes confirmées, HT) et top produits (valeur, unités, % du total)."""
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
                               aggregates=["price_subtotal:sum", "product_uom_qty:sum"], order="price_subtotal:sum desc")
            prods = [l for l in lines if l.get("product_id")]
            total_value = sum(l["price_subtotal:sum"] for l in prods)
            total_units = sum(l["product_uom_qty:sum"] for l in prods)
            best = prods[:top]
            names = self._product_names([l["product_id"][0] for l in best], {l["product_id"][0]: l["product_id"][1] for l in best})
            out.append({"name": settings.WEBSHOP_LABELS.get(wname, wname), "orders": n, "revenue": round(revenue),
                        "avg_basket": round(revenue / n, 2) if n else 0.0,
                        "products": [{"name": names[l["product_id"][0]], "value": round(l["price_subtotal:sum"]),
                                      "units": round(l["product_uom_qty:sum"], 2),
                                      "share": l["price_subtotal:sum"] / total_value if total_value else 0.0} for l in best],
                        "products_total": {"value": round(total_value), "units": round(total_units, 2), "count": len(prods)}})
        return sorted(out, key=lambda w: -w["revenue"])
