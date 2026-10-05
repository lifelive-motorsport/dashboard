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
from ..bu import BU_GROUP
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

    # ---- Regroupement des tiers : étiquette de contact Odoo « regroup_client=X » / « regroup_fournisseur=X » ----------------
    def _client_groups(self, partner_ids: set[int], prefix: str = "regroup_client") -> dict[int, tuple[str, str]]:
        """partner_id -> (clé, libellé).

        1) les contacts d'une même société sont fusionnés (commercial_partner_id) ;
        2) une étiquette « <prefix>=X » sur le contact ou sur sa société regroupe tout ce qui porte X.
        """
        tag = re.compile(rf"^\s*{re.escape(prefix)}\s*=\s*(.+?)\s*$", re.IGNORECASE)
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
                            if (m := tag.match(tags.get(t, "")))}, key=str.lower)
            if names:
                if len(names) > 1:
                    log.warning("Plusieurs étiquettes %s sur le contact %s : %s", prefix, pid, names)
                out[pid] = ("g:" + names[0].lower(), names[0])
            else:
                out[pid] = (f"c:{com['id']}", com["display_name"])
        return out

    @staticmethod
    def _code_name(label: str) -> tuple[str | None, str]:
        m = re.match(r"^\s*(\d+)\s*(.*)$", label)
        return (m.group(1), m.group(2)) if m else (None, label)

    @classmethod
    def _bucket_revenue(cls, label: str) -> str | None:
        """BU d'un compte de CA (700…) ; None si le compte n'est pas du CA exploitable."""
        from ..bu import classify
        code, name = cls._code_name(label)
        c = code and classify(code, name)
        return c.bu if c and c.kind == "revenue" else None

    @classmethod
    def _bucket_cost(cls, label: str) -> str:
        """Compte de CHARGES (classe 6) : BU d'après 602/603/604 + suffixe de BU, sinon « HORS_BU » (frais généraux, véhicules,
        honoraires…). Compte « old - … » ou hors classe 6 (immobilisations, stocks…) : « HORS_PERIMETRE », écarté des classements."""
        from ..bu import classify, is_old
        code, name = cls._code_name(label)
        if not code or not code.startswith("6") or is_old(name):
            return "HORS_PERIMETRE"
        c = classify(code, name)
        return c.bu if c and c.kind == "direct_cost" and c.bu != "UNASSIGNED" else "HORS_BU"

    def _open_split(self, d_from: date, d_to: date, move_types: list[str], line_domain: list, bucket, line_sign: int,
                    amount_sign: int) -> tuple[dict[str, dict[int, float]], dict[int, str]]:
        """Solde encore ouvert (reste dû TTC) des factures/avoirs de la période, par tiers puis par BU.

        Le reste dû d'une facture est réparti entre les BU au prorata de ses lignes (comptes classés par `bucket`)."""
        invs = self._call("account.move", "search_read",
                          domain=[("state", "=", "posted"), ("move_type", "in", move_types),
                                  ("payment_state", "in", ["not_paid", "partial"]), ("partner_id", "!=", False),
                                  ("date", ">=", d_from.isoformat()), ("date", "<=", d_to.isoformat())],
                          fields=["partner_id", "amount_residual_signed"])
        shares: dict[int, dict[str, float]] = {}
        ids = [x["id"] for x in invs]
        for k in range(0, len(ids), 400):
            for r in self._grouped([("move_id", "in", ids[k:k + 400])] + line_domain, ["move_id", "account_id"]):
                b = bucket(r["account_id"][1])
                if b:
                    d = shares.setdefault(r["move_id"][0], {})
                    d[b] = d.get(b, 0.0) + line_sign * r["balance:sum"]
        out: dict[str, dict[int, float]] = {}
        names: dict[int, str] = {}
        for inv in invs:
            pid, pname = inv["partner_id"]
            names[pid] = pname
            sh = shares.get(inv["id"]) or {}
            tot = sum(sh.values())
            parts = {b: v / tot for b, v in sh.items()} if tot else {"UNASSIGNED": 1.0}
            for b, f in parts.items():
                out.setdefault(b, {}).setdefault(pid, 0.0)
                out[b][pid] += amount_sign * inv["amount_residual_signed"] * f
        return out, names

    def _boards(self, by_bucket: dict[str, dict[int, float]], open_fn, names: dict[int, str], prefix: str, limit: int,
                ignore: frozenset = frozenset(), aggregates: dict[str, list[str]] | None = None) -> dict:
        """Classements « total » + un par BU, avec regroupement, solde ouvert et totaux de périmètre.

        `aggregates` ajoute des vues qui regroupent plusieurs BU (ex. « CARS ») : elles ne comptent PAS dans « total »."""
        meta = {"grouping": True, "groups": 0, "open": True}
        by_bucket = {b: v for b, v in by_bucket.items() if b not in ignore}
        try:
            open_bucket, open_names = open_fn()
            open_bucket = {b: v for b, v in open_bucket.items() if b not in ignore}   # ex. part d'une facture sur une immobilisation
            names = {**open_names, **names}
        except Exception:  # droits insuffisants, etc. : pas de solde ouvert, le reste fonctionne
            log.exception("Solde ouvert indisponible")
            open_bucket, meta["open"] = {}, False
        try:
            groups = self._client_groups(set(names), prefix)
        except Exception:  # droits insuffisants, etc. : on garde les noms tels que saisis
            log.exception("Regroupement indisponible")
            groups, meta["grouping"] = {}, False
        label: dict[str, str] = {}

        def key_of(pid: int) -> str:
            k, lab = groups.get(pid, (f"p:{pid}", names[pid]))
            label.setdefault(k, lab)
            return k

        def merge(dicts) -> dict[int, float]:
            out: dict[int, float] = {}
            for d in dicts:
                for pid, v in d.items():
                    out[pid] = out.get(pid, 0.0) + v
            return out

        def board(per_partner: dict[int, float], per_open: dict[int, float]) -> list[dict]:
            agg: dict[str, float] = {}
            opn: dict[str, float] = {}
            for pid, v in per_partner.items():
                agg[key_of(pid)] = agg.get(key_of(pid), 0.0) + v
            for pid, v in per_open.items():
                opn[key_of(pid)] = opn.get(key_of(pid), 0.0) + v
            top = sorted(agg.items(), key=lambda kv: -kv[1])[:limit]
            return [{"name": normalize_name(label[k]), "ca": round(v), "open": round(opn.get(k, 0.0)) if meta["open"] else None}
                    for k, v in top if v > 0]   # affichage uniformisé

        out = {"total": board(merge(by_bucket.values()), merge(open_bucket.values()))}
        for b, per in by_bucket.items():
            out[b] = board(per, open_bucket.get(b, {}))
        out["_totals"] = {"total": round(sum(sum(d.values()) for d in by_bucket.values())),
                          **{b: round(sum(d.values())) for b, d in by_bucket.items()}}
        out["_open_totals"] = ({"total": round(sum(sum(d.values()) for d in open_bucket.values())),
                                **{b: round(sum(d.values())) for b, d in open_bucket.items()}} if meta["open"] else {})
        for name, members in (aggregates or {}).items():           # vues agrégées (calculées après, hors du total)
            out[name] = board(merge(by_bucket.get(m, {}) for m in members), merge(open_bucket.get(m, {}) for m in members))
            out["_totals"][name] = round(sum(sum(by_bucket.get(m, {}).values()) for m in members))
            if meta["open"]:
                out["_open_totals"][name] = round(sum(sum(open_bucket.get(m, {}).values()) for m in members))
        meta["groups"] = len({k for k in label if k.startswith("g:")})
        out["_meta"] = meta
        return out

    def top_clients(self, d_from: date, d_to: date, limit: int = 15) -> dict:
        """Classement des clients par CA (comptes 700) : total et par BU, avec regroupement et solde ouvert. Lecture seule."""
        domain = [("parent_state", "=", "posted"), ("date", ">=", d_from.isoformat()),
                  ("date", "<=", d_to.isoformat()), ("account_id.code", "=like", "700%"),
                  ("partner_id", "!=", False)]
        by_bu: dict[str, dict[int, float]] = {}
        names: dict[int, str] = {}
        for row in self._grouped(domain, ["partner_id", "account_id"]):
            bu = self._bucket_revenue(row["account_id"][1])
            if not bu:
                continue
            pid, pname = row["partner_id"]
            names[pid] = pname
            by_bu.setdefault(bu, {}).setdefault(pid, 0.0)
            by_bu[bu][pid] -= row["balance:sum"]  # crédit = CA
        return self._boards(by_bu, lambda: self._open_split(
            d_from, d_to, ["out_invoice", "out_refund"], [("account_id.code", "=like", "700%")], self._bucket_revenue, -1, 1),
            names, "regroup_client", limit, aggregates={"CARS": [b for b, g in BU_GROUP.items() if g == "CARS"]})

    def top_suppliers(self, d_from: date, d_to: date, limit: int = 15) -> dict:
        """Classement des fournisseurs par achats HT (lignes de factures et avoirs fournisseurs comptabilisés).

        Chaque ligne est rattachée à une BU d'après son compte comptable (602/603/604 + suffixe de BU) ; les autres comptes
        (frais généraux, véhicules, honoraires…) vont dans « HORS_BU ». « total » = toutes les lignes de charges (classe 6 ;
        immobilisations et stocks exclus). Lecture seule."""
        line = [("display_type", "=", "product")]            # lignes de facture : ni TVA ni écriture de tiers
        domain = [("parent_state", "=", "posted"), ("move_id.move_type", "in", ["in_invoice", "in_refund"]),
                  ("date", ">=", d_from.isoformat()), ("date", "<=", d_to.isoformat()), ("partner_id", "!=", False),
                  ("account_id.code", "=like", "6%")] + line   # comptes de charges uniquement
        by_bucket: dict[str, dict[int, float]] = {}
        names: dict[int, str] = {}
        for row in self._grouped(domain, ["partner_id", "account_id"]):
            b = self._bucket_cost(row["account_id"][1])
            if b == "HORS_PERIMETRE":
                continue
            pid, pname = row["partner_id"]
            names[pid] = pname
            by_bucket.setdefault(b, {}).setdefault(pid, 0.0)
            by_bucket[b][pid] += row["balance:sum"]           # débit = achat
        return self._boards(by_bucket, lambda: self._open_split(
            d_from, d_to, ["in_invoice", "in_refund"], line, self._bucket_cost, 1, -1),
            names, "regroup_fournisseur", limit, ignore=frozenset({"HORS_PERIMETRE", "UNASSIGNED"}),
            aggregates={"CARS": [b for b, g in BU_GROUP.items() if g == "CARS"]})

    # ---- Événements : comptes analytiques d'un plan « Événements » -------------------------------------------------
    @staticmethod
    def _plain(text: str) -> str:
        import unicodedata
        return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()

    def _event_plans(self) -> tuple[list[dict], list[dict]]:
        """(plans retenus avec leurs sous-plans, tous les plans). Lève une erreur claire si aucun plan « événements »."""
        plans = self._call("account.analytic.plan", "search_read", domain=[], fields=["name", "parent_id"])
        wanted = self._plain(settings.EVENT_PLAN).strip()
        chosen = {p["id"] for p in plans if (wanted in self._plain(p["name"]) if wanted else
                                             any(k in self._plain(p["name"]) for k in ("event", "evenement")))}
        if not chosen:
            names = ", ".join(sorted(p["name"] for p in plans)) or "aucun"
            raise LookupError(f"Aucun plan analytique « Événements » trouvé (plans existants : {names}). "
                              "Indiquez le nom du bon plan (variable EVENT_PLAN).")
        grew = True
        while grew:                                   # ajoute les sous-plans
            grew = False
            for p in plans:
                if p["id"] not in chosen and p.get("parent_id") and p["parent_id"][0] in chosen:
                    chosen.add(p["id"])
                    grew = True
        return [p for p in plans if p["id"] in chosen], plans

    @staticmethod
    def _plan_column(plan: dict, plans: list[dict]) -> str:
        """Colonne de l'axe sur les lignes analytiques : x_plan<id du plan racine>_id (Odoo crée une colonne par axe racine)."""
        by_id = {p["id"]: p for p in plans}
        while plan.get("parent_id") and plan["parent_id"][0] in by_id:
            plan = by_id[plan["parent_id"][0]]
        return f"x_plan{plan['id']}_id"

    BU_AXIS_LABEL = {"XC": "XC", "MODERN_RALLY": "Modern Rally", "HISTORIC_RALLY": "Historic Rally", "HISTORIC_RACING": "Historic Racing",
                     "OTHERS": "Others"}

    @classmethod
    def _bu_of_axis_account(cls, name: str) -> tuple[str, str | None] | None:
        """Compte de l'axe BU -> (clé de BU, groupe).

        Comptes attendus : XC, Modern Rally, Historic Rally, Historic Racing, Others. Un compte « OLD … » (ancien exercice) est
        reconnu mais écarté (clé « OLD », sans groupe). Tout autre nom : None (signalé à l'écran)."""
        n = re.sub(r"\s+", " ", cls._plain(name)).strip()
        if re.match(r"^old\b", n):
            return "OLD", None
        if n == "xc" or n.startswith("xc "):
            return "XC", "XC"
        if n == "modern rally":
            return "MODERN_RALLY", "CARS"
        if n == "historic rally":
            return "HISTORIC_RALLY", "CARS"
        if n == "historic racing":
            return "HISTORIC_RACING", "CARS"
        if n in ("others", "other", "autres"):
            return "OTHERS", "OTHERS"
        return None

    def events(self, d_from: date, d_to: date) -> dict:
        """Résultat par événement : lignes analytiques ventilées sur l'axe « Événements » (MEETING), classées par compte comptable.

        IMPORTANT : une ligne ventilée sur plusieurs axes (BU, MEETING…) ne porte qu'un compte « principal » ; chaque axe a sa
        propre colonne (x_plan<id>_id). On filtre donc sur la colonne de l'axe MEETING, pas sur account_id.
        Montants signés (positif = produit, négatif = charge). Produits = comptes 7xx ; charges = comptes 6xx, dont « frais
        directs » (602/603/604).
        Rattachement à XC ou CARS : uniquement d'après l'axe analytique BU (obligatoire à la saisie). Une ligne sans compte BU
        est comptée dans « bu_missing » (anomalie de saisie à corriger), jamais devinée ; un événement sans BU exploitable : « NONE »."""
        from ..bu import classify
        plans, all_plans = self._event_plans()
        columns = sorted({self._plan_column(p, all_plans) for p in plans})
        bu_plan = next((p for p in all_plans if not p.get("parent_id") and self._plain(p["name"]).strip() == self._plain(settings.BU_PLAN).strip()), None)
        if not bu_plan:
            names = ", ".join(sorted(p["name"] for p in all_plans))
            raise LookupError(f"Axe analytique « {settings.BU_PLAN} » introuvable (plans existants : {names}). "
                              "Indiquez le nom de l'axe des BU (variable BU_PLAN).")
        bu_col = self._plan_column(bu_plan, all_plans)
        ev: dict[tuple[str, int], dict] = {}
        unmapped: set[str] = set()
        missing = 0
        for col in columns:
            rows = self._call("account.analytic.line", "formatted_read_group",
                              domain=[(col, "!=", False), ("date", ">=", d_from.isoformat()), ("date", "<=", d_to.isoformat())],
                              groupby=[col, "general_account_id", bu_col], aggregates=["amount:sum"])
            for r in rows:
                if not r.get(col):
                    continue
                aid, aname = r[col]
                code, name = self._code_name((r.get("general_account_id") or [0, ""])[1])
                if not code or code[0] not in "67":
                    continue
                amount = float(r["amount:sum"] or 0.0)
                e = ev.setdefault((col, aid), {"id": aid, "name": aname, "plan": col, "ca": 0.0, "direct_costs": 0.0, "other_costs": 0.0,
                                               "axis": {}})
                c = classify(code, name) if len(code) == 6 else None
                if code[0] == "7":
                    e["ca"] += amount
                elif c and c.kind == "direct_cost":
                    e["direct_costs"] += -amount
                else:
                    e["other_costs"] += -amount
                if not r.get(bu_col):
                    missing += 1
                    continue
                m = self._bu_of_axis_account(r[bu_col][1])
                if m is None:
                    unmapped.add(r[bu_col][1])
                elif m[1]:                                  # compte OLD : écarté sans alerte
                    e["axis"][m] = e["axis"].get(m, 0.0) + abs(amount)
        out = []
        for e in ev.values():
            axis = e.pop("axis")                                   # {(clé BU, groupe): poids}
            wg: dict[str, float] = {}
            for (_, g), v in axis.items():
                wg[g] = wg.get(g, 0.0) + v
            e["group"] = "NONE" if not wg else max(wg, key=wg.get)
            tot_w = sum(wg.values())
            e["mixed"] = len(wg) > 1 and (tot_w - max(wg.values())) / tot_w >= 0.10     # un autre groupe pèse au moins 10 %
            e["bus"] = [{"bu": self.BU_AXIS_LABEL[k], "share": round(v / tot_w, 3)}
                        for (k, g), v in sorted(axis.items(), key=lambda kv: -kv[1])] if tot_w else []
            e["result"] = e["ca"] - e["direct_costs"] - e["other_costs"]
            for k in ("ca", "direct_costs", "other_costs", "result"):
                e[k] = round(e[k])
            if e["ca"] or e["direct_costs"] or e["other_costs"]:
                out.append(e)
        out.sort(key=lambda e: (-e["ca"], e["name"]))
        return {"events": out, "plans": [p["name"] for p in plans], "bu_axis": bu_plan["name"],
                "bu_unmapped": sorted(unmapped), "bu_missing": missing}

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
