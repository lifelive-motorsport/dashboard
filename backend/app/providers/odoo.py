"""Lecture seule d'Odoo 19 via l'API externe JSON-2 (/json/2/<modèle>/<méthode>).

ATTENTION : non testé contre une vraie instance (aucun accès à ce stade) ; à valider
dès que la base Odoo.sh et la clé API de l'utilisateur technique sont disponibles.
"""
from __future__ import annotations

import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta, datetime
from urllib.parse import unquote, urlsplit

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

    def old_plan_revenue(self, d_from: date, d_to: date) -> float:
        """Produits (comptes 70…) de l'ANCIEN plan comptable, ceux dont le libellé commence par « OLD » : écartés des chiffres
        courants mais indispensables pour comparer avec 2025, année où cet ancien plan était encore utilisé. Montant positif."""
        domain = [("parent_state", "=", "posted"), ("date", ">=", d_from.isoformat()), ("date", "<=", d_to.isoformat()),
                  ("account_id.code", "=like", "70%")]
        total = 0.0
        for row in self._grouped(domain, ["account_id"]):
            if re.match(r"^\s*\d+\s+old\b", row["account_id"][1], re.I):
                total -= row["balance:sum"]
        return total

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
                ignore: frozenset = frozenset(), aggregates: dict[str, list[str]] | None = None,
                moves: dict[str, dict[int, dict[int, float]]] | None = None,
                mix: dict[str, dict[int, dict[str, float]]] | None = None) -> dict:
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

        def merge_moves(buckets) -> dict[int, dict[int, float]]:
            """pid -> {facture: montant} ; une facture répartie sur plusieurs BU voit ses montants additionnés (une seule facture)."""
            out: dict[int, dict[int, float]] = {}
            for b in buckets:
                for pid, mv in (moves or {}).get(b, {}).items():
                    d = out.setdefault(pid, {})
                    for m, v in mv.items():
                        d[m] = d.get(m, 0.0) + v
            return out

        def invoice_stats(per_moves: dict[int, dict[int, float]]) -> tuple[dict[str, tuple[int, float]], int, float]:
            """({clé de tiers: (nb de factures, montant des factures)}, total factures, montant). Seules les factures de montant net
            positif comptent (un avoir réduit le CA mais n'est pas une « facture »)."""
            per_key: dict[str, dict[int, float]] = {}
            for pid, mv in per_moves.items():
                d = per_key.setdefault(key_of(pid), {})
                for m, v in mv.items():
                    d[m] = d.get(m, 0.0) + v
            res = {k: (sum(1 for v in mv.values() if v > 0), sum(v for v in mv.values() if v > 0)) for k, mv in per_key.items()}
            return res, sum(n for n, _ in res.values()), sum(a for _, a in res.values())

        def merge_mix(buckets) -> dict[int, dict[str, float]]:
            """pid -> {famille de coût: montant} (604 achats de marchandises, 603 sous-traitance, 602 frais, « autres »)."""
            out: dict[int, dict[str, float]] = {}
            for b in buckets:
                for pid, fam in (mix or {}).get(b, {}).items():
                    d = out.setdefault(pid, {})
                    for f, v in fam.items():
                        d[f] = d.get(f, 0.0) + v
            return out

        def mix_by_key(per_mix: dict[int, dict[str, float]]) -> dict[str, dict[str, int]]:
            res: dict[str, dict[str, float]] = {}
            for pid, fam in per_mix.items():
                d = res.setdefault(key_of(pid), {})
                for f, v in fam.items():
                    d[f] = d.get(f, 0.0) + v
            return {k: {f: round(v) for f, v in d.items()} for k, d in res.items()}

        def board(per_partner: dict[int, float], per_open: dict[int, float], per_moves: dict | None = None, per_mix: dict | None = None) -> list[dict]:
            inv = invoice_stats(per_moves)[0] if per_moves else {}
            fam = mix_by_key(per_mix) if per_mix else {}
            agg: dict[str, float] = {}
            opn: dict[str, float] = {}
            for pid, v in per_partner.items():
                agg[key_of(pid)] = agg.get(key_of(pid), 0.0) + v
            for pid, v in per_open.items():
                opn[key_of(pid)] = opn.get(key_of(pid), 0.0) + v
            top = sorted(agg.items(), key=lambda kv: -kv[1])[:limit]
            return [{"name": normalize_name(label[k]), "ca": round(v), "open": round(opn.get(k, 0.0)) if meta["open"] else None,
                     "invoices": inv.get(k, (0, 0.0))[0], "avg": round(inv[k][1] / inv[k][0], 2) if inv.get(k, (0, 0.0))[0] else None,
                     **({"mix": fam.get(k, {})} if per_mix else {})}
                    for k, v in top if v > 0]   # affichage uniformisé

        stats: dict[str, dict] = {}

        def stat(name: str, buckets) -> None:
            if moves is not None:
                _, n, amt = invoice_stats(merge_moves(buckets))
                stats[name] = {"invoices": n, "avg": round(amt / n, 2) if n else None}

        scope_mix: dict[str, dict[str, int]] = {}

        def scope(name: str, buckets) -> None:
            if mix is not None:
                tot: dict[str, float] = {}
                for fam in merge_mix(buckets).values():
                    for f, v in fam.items():
                        tot[f] = tot.get(f, 0.0) + v
                scope_mix[name] = {f: round(v) for f, v in tot.items()}

        out = {"total": board(merge(by_bucket.values()), merge(open_bucket.values()), merge_moves(by_bucket), merge_mix(by_bucket))}
        stat("total", by_bucket)
        scope("total", list(by_bucket))
        for b, per in by_bucket.items():
            out[b] = board(per, open_bucket.get(b, {}), merge_moves([b]), merge_mix([b]))
            stat(b, [b])
            scope(b, [b])
        out["_totals"] = {"total": round(sum(sum(d.values()) for d in by_bucket.values())),
                          **{b: round(sum(d.values())) for b, d in by_bucket.items()}}
        out["_open_totals"] = ({"total": round(sum(sum(d.values()) for d in open_bucket.values())),
                                **{b: round(sum(d.values())) for b, d in open_bucket.items()}} if meta["open"] else {})
        for name, members in (aggregates or {}).items():           # vues agrégées (calculées après, hors du total)
            out[name] = board(merge(by_bucket.get(m, {}) for m in members), merge(open_bucket.get(m, {}) for m in members), merge_moves(members), merge_mix(members))
            stat(name, members)
            scope(name, members)
            out["_totals"][name] = round(sum(sum(by_bucket.get(m, {}).values()) for m in members))
            if meta["open"]:
                out["_open_totals"][name] = round(sum(sum(open_bucket.get(m, {}).values()) for m in members))
        meta["groups"] = len({k for k in label if k.startswith("g:")})
        out["_stats"] = stats
        if mix is not None:
            out["_mix"] = scope_mix
        out["_meta"] = meta
        return out

    def top_clients(self, d_from: date, d_to: date, limit: int = 15) -> dict:
        """Classement des clients par CA (comptes 700) : total et par BU, avec regroupement et solde ouvert. Lecture seule."""
        domain = [("parent_state", "=", "posted"), ("date", ">=", d_from.isoformat()),
                  ("date", "<=", d_to.isoformat()), ("account_id.code", "=like", "700%"),
                  ("partner_id", "!=", False)]
        by_bu: dict[str, dict[int, float]] = {}
        moves: dict[str, dict[int, dict[int, float]]] = {}
        names: dict[int, str] = {}
        for row in self._grouped(domain, ["partner_id", "account_id", "move_id"]):
            bu = self._bucket_revenue(row["account_id"][1])
            if not bu:
                continue
            pid, pname = row["partner_id"]
            names[pid] = pname
            by_bu.setdefault(bu, {}).setdefault(pid, 0.0)
            by_bu[bu][pid] -= row["balance:sum"]  # crédit = CA
            if row.get("move_id"):
                mv = moves.setdefault(bu, {}).setdefault(pid, {})
                mv[row["move_id"][0]] = mv.get(row["move_id"][0], 0.0) - row["balance:sum"]
        return self._boards(by_bu, lambda: self._open_split(
            d_from, d_to, ["out_invoice", "out_refund"], [("account_id.code", "=like", "700%")], self._bucket_revenue, -1, 1),
            names, "regroup_client", limit, aggregates={"CARS": [b for b, g in BU_GROUP.items() if g == "CARS"]}, moves=moves)

    def _non_bill_direct_costs(self, d_from: date, d_to: date) -> dict[str, dict]:
        """Charges directes (comptes 602/603/604 classés par BU) qui NE viennent PAS de lignes de factures fournisseurs avec tiers :
        écritures diverses, provisions / factures à recevoir, notes de frais, paiements directs, lignes sans tiers…
        C'est l'écart entre les « coûts directs » du P&L et le total du hit-parade fournisseurs. {bucket: {amount, journals[]}}."""
        from ..bu import classify
        base = [("parent_state", "=", "posted"), ("date", ">=", d_from.isoformat()), ("date", "<=", d_to.isoformat()),
                ("account_id.code", "=like", "60%")]
        not_bill = ["|", "|", ("move_id.move_type", "not in", ["in_invoice", "in_refund"]), ("partner_id", "=", False), ("display_type", "!=", "product")]
        rows = self._grouped(base + not_bill, ["journal_id", "account_id"])
        out: dict[str, dict] = {}
        for r in rows:
            code, name = self._code_name(r["account_id"][1])
            c = code and len(code) == 6 and classify(code, name)
            if not c or c.kind != "direct_cost" or c.bu == "UNASSIGNED":
                continue
            b = out.setdefault(c.bu, {"amount": 0.0, "journals": {}})
            amt = float(r["balance:sum"] or 0.0)
            b["amount"] += amt
            j = r["journal_id"][1] if r.get("journal_id") else "(sans journal)"
            b["journals"][j] = b["journals"].get(j, 0.0) + amt
        return {k: {"amount": round(v["amount"]), "journals": [{"name": n, "amount": round(a)} for n, a in sorted(v["journals"].items(), key=lambda kv: -abs(kv[1]))[:4] if round(a)]}
                for k, v in out.items()}

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
        moves: dict[str, dict[int, dict[int, float]]] = {}
        mix: dict[str, dict[int, dict[str, float]]] = {}
        names: dict[int, str] = {}
        for row in self._grouped(domain, ["partner_id", "account_id", "move_id"]):
            b = self._bucket_cost(row["account_id"][1])
            if b == "HORS_PERIMETRE":
                continue
            pid, pname = row["partner_id"]
            names[pid] = pname
            by_bucket.setdefault(b, {}).setdefault(pid, 0.0)
            by_bucket[b][pid] += row["balance:sum"]           # débit = achat
            code = (self._code_name(row["account_id"][1])[0] or "")[:3]
            f = mix.setdefault(b, {}).setdefault(pid, {})
            fam = code if code in ("604", "603", "602") else "autres"      # achats de marchandises, sous-traitance, frais, autres charges
            f[fam] = f.get(fam, 0.0) + row["balance:sum"]
            if row.get("move_id"):
                mv = moves.setdefault(b, {}).setdefault(pid, {})
                mv[row["move_id"][0]] = mv.get(row["move_id"][0], 0.0) + row["balance:sum"]
        out = self._boards(by_bucket, lambda: self._open_split(
            d_from, d_to, ["in_invoice", "in_refund"], line, self._bucket_cost, 1, -1),
            names, "regroup_fournisseur", limit, ignore=frozenset({"HORS_PERIMETRE", "UNASSIGNED"}),
            aggregates={"CARS": [b for b, g in BU_GROUP.items() if g == "CARS"]}, moves=moves, mix=mix)
        try:                                                    # rapprochement avec les coûts directs du P&L (facultatif)
            recon = self._non_bill_direct_costs(d_from, d_to)
            recon["CARS"] = {"amount": sum(recon.get(b, {}).get("amount", 0) for b, g in BU_GROUP.items() if g == "CARS"),
                             "journals": [j for b, g in BU_GROUP.items() if g == "CARS" for j in recon.get(b, {}).get("journals", [])][:4]}
            out["_recon"] = recon
        except Exception:
            log.exception("Rapprochement des coûts directs indisponible")
        return out

    def marketing(self, d_from: date, d_to: date, top: int = 15) -> dict:
        """Dépenses marketing : comptes de charges MARKETING_ACCOUNTS (débit net = dépense), par compte, par période et par
        fournisseur ; plus l'investissement marketing immobilisé de l'événement MARKETING_INVEST_EVENT (montant et durée d'amortissement)."""
        codes = settings.MARKETING_ACCOUNTS
        lines = self._call("account.move.line", "search_read",
                           domain=[("parent_state", "=", "posted"), ("date", ">=", d_from.isoformat()), ("date", "<=", d_to.isoformat()),
                                   ("account_id.code", "in", codes)],
                           fields=["date", "balance", "account_id", "partner_id", "move_id"])
        gran, buckets = self._buckets(d_from, d_to)
        starts = [b[0] for b in buckets]
        per_acc: dict[str, dict] = {}
        per_bucket: dict[date, dict[str, float]] = {st: {} for st in starts}
        per_partner: dict[int, dict] = {}
        for ln in lines:
            code, name = self._code_name(ln["account_id"][1])
            amt = float(ln["balance"] or 0.0)
            a = per_acc.setdefault(code or "", {"code": code or "", "name": name, "amount": 0.0})
            a["amount"] += amt
            d = date.fromisoformat(str(ln["date"])[:10])
            st = max((x for x in starts if x <= d), default=None)
            if st is not None:
                per_bucket[st][code or ""] = per_bucket[st].get(code or "", 0.0) + amt
            if ln.get("partner_id"):
                pid, pname = ln["partner_id"]
                p = per_partner.setdefault(pid, {"name": pname, "amount": 0.0, "moves": {}})
                p["amount"] += amt
                mid = (ln.get("move_id") or [0])[0]
                p["moves"][mid] = p["moves"].get(mid, 0.0) + amt
        total = sum(a["amount"] for a in per_acc.values())
        accounts = [{"code": c, "name": a["name"], "amount": round(a["amount"]), "share": a["amount"] / total if total else 0.0}
                    for c, a in sorted(per_acc.items(), key=lambda kv: -kv[1]["amount"])]
        try:
            groups = self._client_groups(set(per_partner), "regroup_fournisseur")
        except Exception:
            groups = {}
        merged: dict[str, dict] = {}
        for pid, p in per_partner.items():
            key, label = groups.get(pid, (f"p:{pid}", p["name"]))
            m = merged.setdefault(key, {"name": normalize_name(label), "amount": 0.0, "moves": {}})
            m["amount"] += p["amount"]
            for mid, v in p["moves"].items():
                m["moves"][mid] = m["moves"].get(mid, 0.0) + v
        suppliers = [{"name": m["name"], "amount": round(m["amount"]), "share": m["amount"] / total if total else 0.0,
                      "invoices": sum(1 for v in m["moves"].values() if v > 0)}
                     for m in sorted(merged.values(), key=lambda m: -m["amount"])[:top] if m["amount"] > 0]
        pts = [{"label": lbl, "avg": round(sum(per_bucket[st].values()), 2), "total": round(sum(per_bucket[st].values())),
                "by_account": {c: round(v) for c, v in per_bucket[st].items()}} for st, lbl in buckets]
        invest = None
        try:
            invest = self._marketing_invest(d_to)
        except Exception:
            log.exception("Investissement marketing indisponible")
        return {"total": round(total), "accounts": accounts, "suppliers": suppliers, "series": {"granularity": gran, "points": pts},
                "codes": codes, "invest": invest}

    def _marketing_invest(self, d_to: date) -> dict | None:
        """Investissements marketing de l'année portés sur les comptes INVEST (MARKETING_INVEST_ACCOUNTS), par libellé de ligne de
        facture : montant, factures, amortissement déjà passé et dotation mensuelle (donc durée = investi ÷ dotation)."""
        y0 = date(d_to.year, 1, 1).isoformat()
        base = [("parent_state", "=", "posted"), ("date", ">=", y0), ("date", "<=", d_to.isoformat())]
        dom = base + [("account_id.code", "in", settings.MARKETING_INVEST_ACCOUNTS), ("debit", ">", 0)]
        tag = settings.MARKETING_INVEST_TAG.strip().lower()
        tag_ids = [c["id"] for c in self._call("res.partner.category", "search_read", domain=[("name", "ilike", tag)], fields=["name"])
                   if (c.get("name") or "").strip().lower() == tag] if tag else []
        partners = self._call("res.partner", "search_read", domain=[("category_id", "in", tag_ids)], fields=["id"]) if tag_ids else []
        if partners:                                    # règle principale : fournisseurs (et leurs contacts) portant l'étiquette « invest marketing »
            inv = self._call("account.move.line", "search_read", domain=dom + [("partner_id", "child_of", [p["id"] for p in partners])],
                             fields=["name", "balance", "date", "partner_id", "move_id"])
        else:                                           # étiquette absente ou sans contact : repli sur des mots-clés dans le libellé
            inv = self._call("account.move.line", "search_read", domain=dom, fields=["name", "balance", "date", "partner_id", "move_id"])
            kw = settings.MARKETING_INVEST_KEYWORDS
            inv = [ln for ln in inv if any(k in (ln.get("name") or "").lower() for k in kw)]
        if not inv:
            return None
        am = self._call("account.move.line", "search_read", domain=base + [("account_id.code", "=like", "630%"), ("name", "ilike", "amortissement")],
                        fields=["name", "balance", "date"])
        items: dict[str, dict] = {}
        for ln in inv:
            label = (ln.get("name") or "").strip() or "(sans libellé)"
            c = items.setdefault(label, {"label": label, "capex": 0.0, "bills": {}, "partner": ""})
            c["capex"] += float(ln["balance"] or 0.0)
            if ln.get("move_id"):
                c["bills"][ln["move_id"][1]] = str(ln["date"])[:10]
            if ln.get("partner_id"):
                c["partner"] = ln["partner_id"][1]
        out = []
        for c in items.values():
            mine = [a for a in am if (a.get("name") or "").lower().startswith(c["label"].lower())]
            months: dict[str, float] = {}
            for a in mine:
                months[str(a["date"])[:7]] = months.get(str(a["date"])[:7], 0.0) + float(a["balance"] or 0.0)
            monthly = months[max(months)] if months else 0.0
            out.append({"label": c["label"], "capex": round(c["capex"]), "partner": c["partner"],
                        "bills": [{"ref": r, "date": d} for r, d in sorted(c["bills"].items(), key=lambda kv: kv[1])],
                        "amort": round(sum(months.values())), "amort_monthly": round(monthly, 2),
                        "amort_months": round(c["capex"] / monthly) if monthly > 0 else 0})
        out.sort(key=lambda c: -c["capex"])
        total_monthly = sum(c["amort_monthly"] for c in out)
        return {"year": d_to.year, "total": sum(c["capex"] for c in out), "amort": sum(c["amort"] for c in out), "amort_monthly": round(total_monthly, 2),
                "items": out, "accounts": settings.MARKETING_INVEST_ACCOUNTS}

    def tags_overview(self) -> dict:
        """Étiquettes de contact utilisées par le dashboard et nombre de contacts qui les portent (aide-mémoire « Tags Odoo »)."""
        cats = {c["id"]: c["name"] for c in self._call("res.partner.category", "search_read", domain=[], fields=["name"])}
        counts: dict[int, int] = {}
        for r in self._call("res.partner", "formatted_read_group", domain=[("category_id", "!=", False)], groupby=["category_id"], aggregates=["__count"]):
            if r.get("category_id"):
                counts[r["category_id"][0]] = int(r["__count"])
        inv = settings.MARKETING_INVEST_TAG.strip().lower()
        out = []
        for cid, name in cats.items():
            low = name.strip().lower()
            kind = ("client" if re.match(r"^\s*regroup_client\s*=", low) else "fournisseur" if re.match(r"^\s*regroup_fournisseur\s*=", low)
                    else "invest" if low == inv else None)
            if kind:
                out.append({"name": name, "kind": kind, "count": counts.get(cid, 0)})
        return {"tags": sorted(out, key=lambda t: (t["kind"], t["name"].lower())), "invest_tag": settings.MARKETING_INVEST_TAG}

    # ---- Personnel : données comptables pour contrôler les fiches de paie, sociétés d'indépendants ---------------------
    def staff_accounting(self, year: int) -> dict:
        """Charges de personnel (comptes 62…) par mois et par compte sur l'année ; la part « rémunération » (STAFF_PAY_PREFIXES, par défaut
        620 et 621) sert à contrôler les fiches de paie. Lecture seule."""
        lines = self._call("account.move.line", "search_read",
                           domain=[("parent_state", "=", "posted"), ("date", ">=", f"{year}-01-01"), ("date", "<=", f"{year}-12-31"),
                                   ("account_id.code", "=like", "62%")], fields=["date", "balance", "account_id"])
        accounts: dict[str, dict] = {}
        pay: dict[str, float] = {}
        other: dict[str, float] = {}
        for ln in lines:
            code, name = self._code_name(ln["account_id"][1])
            code = code or ""
            m = str(ln["date"])[:7]
            amt = float(ln["balance"] or 0.0)
            a = accounts.setdefault(code, {"code": code, "name": name, "pay": any(code.startswith(x) for x in settings.STAFF_PAY_PREFIXES), "by_month": {}, "total": 0.0})
            a["by_month"][m] = a["by_month"].get(m, 0.0) + amt
            a["total"] += amt
            tgt = pay if a["pay"] else other
            tgt[m] = tgt.get(m, 0.0) + amt
        director = {"pay_accounts": settings.STAFF_DIRECTOR_PAY, "social_accounts": settings.STAFF_DIRECTOR_SOCIAL, "pay_by_month": {}, "social_by_month": {}}
        codes = settings.STAFF_DIRECTOR_PAY + settings.STAFF_DIRECTOR_SOCIAL
        if codes:
            dl = self._call("account.move.line", "search_read",
                            domain=[("parent_state", "=", "posted"), ("date", ">=", f"{year}-01-01"), ("date", "<=", f"{year}-12-31"), ("account_id.code", "in", codes)],
                            fields=["date", "balance", "account_id"])
            for ln in dl:
                code, _ = self._code_name(ln["account_id"][1])
                tgt = director["pay_by_month"] if code in settings.STAFF_DIRECTOR_PAY else director["social_by_month"]
                m = str(ln["date"])[:7]
                tgt[m] = tgt.get(m, 0.0) + float(ln["balance"] or 0.0)
            director["pay_by_month"] = {m: round(v) for m, v in sorted(director["pay_by_month"].items())}
            director["social_by_month"] = {m: round(v) for m, v in sorted(director["social_by_month"].items())}
        return {"year": year, "pay_prefixes": settings.STAFF_PAY_PREFIXES, "director": director,
                "accounts": [{**a, "total": round(a["total"]), "by_month": {m: round(v) for m, v in a["by_month"].items()}} for a in sorted(accounts.values(), key=lambda a: a["code"])],
                "pay_by_month": {m: round(v) for m, v in sorted(pay.items())}, "other_by_month": {m: round(v) for m, v in sorted(other.items())}}

    def staff_partners(self, q: str) -> list[dict]:
        """Sociétés Odoo dont le nom contient `q` (pour rattacher un indépendant)."""
        rows = self._call("res.partner", "search_read", domain=[("is_company", "=", True), ("name", "ilike", q.strip())],
                          fields=["name", "vat", "city"], limit=20, order="name")
        return [{"id": r["id"], "name": r["name"], "vat": r.get("vat") or "", "city": r.get("city") or ""} for r in rows]

    def staff_invoices(self, partner_ids: list[int], year: int) -> list[dict]:
        """Factures et avoirs fournisseurs comptabilisés des sociétés données (et de leurs contacts) sur l'année."""
        if not partner_ids:
            return []
        rows = self._call("account.move", "search_read",
                          domain=[("move_type", "in", ["in_invoice", "in_refund"]), ("state", "=", "posted"), ("commercial_partner_id", "in", partner_ids),
                                  ("date", ">=", f"{year}-01-01"), ("date", "<=", f"{year}-12-31")],
                          fields=["name", "ref", "invoice_date", "date", "amount_untaxed", "amount_total", "payment_state", "move_type", "commercial_partner_id"],
                          order="date desc", limit=500)
        fees: dict[int, float] = {}
        if rows and settings.STAFF_FEE_PREFIXES:                # honoraires = lignes sur les comptes 613 ; le reste (frais avancés, refacturés) est exclu
            dom = ["|"] * (len(settings.STAFF_FEE_PREFIXES) - 1) + [("account_id.code", "=like", f"{x}%") for x in settings.STAFF_FEE_PREFIXES]
            for ln in self._call("account.move.line", "search_read", domain=[("move_id", "in", [r["id"] for r in rows]), ("parent_state", "=", "posted")] + dom,
                                 fields=["move_id", "balance"]):
                fees[ln["move_id"][0]] = fees.get(ln["move_id"][0], 0.0) + float(ln["balance"] or 0.0)
        out = []
        for r in rows:
            sign = -1 if r["move_type"] == "in_refund" else 1
            out.append({"fees": round(fees.get(r["id"], 0.0), 2), "number": r["name"], "ref": r.get("ref") or "", "date": str(r.get("invoice_date") or r["date"]),
                        "untaxed": round(sign * float(r["amount_untaxed"] or 0), 2), "total": round(sign * float(r["amount_total"] or 0), 2),
                        "paid": r.get("payment_state") in ("paid", "in_payment"), "partner": (r.get("commercial_partner_id") or [0, ""])[1],
                        "refund": sign < 0})
        return out

    # ---- Stock : valorisation au coût moyen -------------------------------------------------------------------------
    def _pif_field(self) -> str | None:
        """Champ « code PIF » des articles : STOCK_PIF_FIELD, sinon détecté (champ texte/sélection dont le nom ou le libellé contient « PIF »)."""
        if settings.STOCK_PIF_FIELD:
            return settings.STOCK_PIF_FIELD
        try:
            for name, f in self._call("product.product", "fields_get", attributes=["string", "type"]).items():
                if f.get("type") in ("char", "selection") and re.search(r"\bpif\b|_pif|pif_", f"{name} {f.get('string', '')}", re.I):
                    return name
        except Exception:
            log.exception("Détection du champ PIF impossible")
        return None

    def stock_report(self) -> dict:
        """Stock en main valorisé au coût moyen (standard_price) : tous les emplacements internes (ou ceux dont le nom contient
        STOCK_LOCATION_LIKE), quantité nette par article, quantités négatives conservées. Lecture seule."""
        from ..stock import build_report
        dom = [("location_id.usage", "=", "internal")]
        if settings.STOCK_LOCATION_LIKE:
            dom.append(("location_id.complete_name", "ilike", settings.STOCK_LOCATION_LIKE))
        rows = self._call("stock.quant", "formatted_read_group", domain=dom, groupby=["product_id"], aggregates=["quantity:sum"])
        qty = {r["product_id"][0]: float(r["quantity:sum"] or 0.0) for r in rows if r.get("product_id") and abs(r["quantity:sum"] or 0.0) > 1e-9}
        pif = self._pif_field()
        fields = ["default_code", "name", "standard_price", "uom_id"] + ([pif] if pif else [])
        items = []
        ids = sorted(qty)
        for k in range(0, len(ids), 400):
            for p in self._call("product.product", "read", ids=ids[k:k + 400], fields=fields, context={"active_test": False}):
                code = p.get(pif) if pif else None
                items.append({"ref": p.get("default_code") or "", "name": p.get("name") or "", "pif": (str(code).strip() if code else ""),
                              "cost": float(p.get("standard_price") or 0.0), "qty": qty[p["id"]],
                              "uom": (p.get("uom_id") or [0, ""])[1]})
        return build_report(items, pif)

    # ---- Événements : comptes analytiques d'un plan « Événements » -------------------------------------------------
    @staticmethod
    def _plain(text: str) -> str:
        import unicodedata
        return unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode().lower()

    def _event_plans(self, setting: str | None = None, exact: bool = False, label: str = "Événements",
                     var: str = "EVENT_PLAN") -> tuple[list[dict], list[dict]]:
        """(plans retenus avec leurs sous-plans, tous les plans). Lève une erreur claire si aucun plan trouvé."""
        plans = self._call("account.analytic.plan", "search_read", domain=[], fields=["name", "parent_id"])
        wanted = self._plain(settings.EVENT_PLAN if setting is None else setting).strip()
        if exact:
            chosen = {p["id"] for p in plans if self._plain(p["name"]).strip() == wanted}
        else:
            chosen = {p["id"] for p in plans if (wanted in self._plain(p["name"]) if wanted else
                                                 any(k in self._plain(p["name"]) for k in ("event", "evenement")))}
        if not chosen:
            names = ", ".join(sorted(p["name"] for p in plans)) or "aucun"
            raise LookupError(f"Aucun plan analytique « {label} » trouvé (plans existants : {names}). "
                              f"Indiquez le nom du bon plan (variable {var}).")
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
        r = self._by_axis(d_from, d_to)
        return {**{k: v for k, v in r.items() if k != "items"}, "events": r["items"]}

    def vehicles(self, d_from: date, d_to: date) -> dict:
        """Résultat par véhicule : même logique que les événements, sur l'axe analytique « CARS » (un compte = un véhicule),
        rattaché à une BU d'après l'axe BU ; le client et la référence viennent de la fiche du compte analytique."""
        r = self._by_axis(d_from, d_to, settings.VEHICLE_PLAN, True, "Véhicules", "VEHICLE_PLAN")
        items = r.pop("items")
        ids = [e["id"] for e in items]
        info: dict[int, dict] = {}
        if ids:
            try:
                for a in self._call("account.analytic.account", "search_read", domain=[("id", "in", ids)],
                                    fields=["name", "code", "partner_id"], context={"active_test": False}):
                    info[a["id"]] = a
            except Exception:
                pass                                            # colonnes « client » / « référence » facultatives
        for e in items:
            a = info.get(e["id"], {})
            e["name"] = a.get("name") or re.sub(r"^\s*\[[^\]]*\]\s*", "", e["name"])        # nom seul : sans « [référence] » ni « - client »
            e["client"] = (a.get("partner_id") or [0, ""])[1]
            e["reference"] = a.get("code") or ""
        return {**r, "vehicles": items}

    def _by_axis(self, d_from: date, d_to: date, setting: str | None = None, exact: bool = False, label: str = "Événements",
                 var: str = "EVENT_PLAN") -> dict:
        """Résultat par événement : lignes analytiques ventilées sur l'axe « Événements » (MEETING), classées par compte comptable.

        IMPORTANT : une ligne ventilée sur plusieurs axes (BU, MEETING…) ne porte qu'un compte « principal » ; chaque axe a sa
        propre colonne (x_plan<id>_id). On filtre donc sur la colonne de l'axe MEETING, pas sur account_id.
        Montants signés (positif = produit, négatif = charge). Produits = comptes 7xx ; charges = comptes 6xx, dont « frais
        directs » (602/603/604).
        Rattachement à XC ou CARS : uniquement d'après l'axe analytique BU (obligatoire à la saisie). Une ligne sans compte BU
        est comptée dans « bu_missing » (anomalie de saisie à corriger), jamais devinée ; un événement sans BU exploitable : « NONE »."""
        from ..bu import classify
        plans, all_plans = self._event_plans(setting, exact, label, var)
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
        missing_detail: list[dict] = []
        for col in columns:
            rows = self._call("account.analytic.line", "formatted_read_group",
                              domain=[(col, "!=", False), ("date", ">=", d_from.isoformat()), ("date", "<=", d_to.isoformat())],
                              groupby=[col, "general_account_id", bu_col], aggregates=["amount:sum", "__count"])
            for r in rows:
                if not r.get(col):
                    continue
                aid, aname = r[col]
                code, name = self._code_name((r.get("general_account_id") or [0, ""])[1])
                if not code or code[0] not in "267":
                    continue
                amount = float(r["amount:sum"] or 0.0)
                if code[0] == "2" and amount >= 0:       # classe 2 au crédit/positif = contrepartie d'amortissement : ignorée
                    continue
                m = self._bu_of_axis_account(r[bu_col][1]) if r.get(bu_col) else None
                if m and m[0] == "OLD":                    # compte « OLD … » de l'axe BU : ligne écartée (montants compris)
                    continue
                e = ev.setdefault((col, aid), {"id": aid, "name": aname, "plan": col, "ca": 0.0, "direct_costs": 0.0, "other_costs": 0.0,
                                               "capex": 0.0, "amort": 0.0, "axis": {}})
                c = classify(code, name) if len(code) == 6 else None
                if code[0] == "2":                       # dépense immobilisée (compte INVEST) : sortie de cash, amortie ensuite
                    e["capex"] += -amount
                    continue
                if code[0] == "7":
                    e["ca"] += amount
                elif code.startswith("630"):             # dotations aux amortissements : non cash
                    e["amort"] += -amount
                elif c and c.kind == "direct_cost":
                    e["direct_costs"] += -amount
                else:
                    e["other_costs"] += -amount
                if not r.get(bu_col):
                    missing += 1
                    missing_detail.append({"item": aname, "account": f"{code} {name}".strip(), "amount": round(amount, 2), "lines": int(r.get("__count") or 0)})
                    continue
                if m is None:
                    unmapped.add(r[bu_col][1])
                else:
                    e["axis"][m] = e["axis"].get(m, 0.0) + abs(amount)
        monthly: dict[tuple[str, int], float] = {}                 # dotation du dernier mois, par événement
        for col in columns:
            ids = [aid for (c, aid), e in ev.items() if c == col and e["amort"] and e["capex"]]
            if not ids:
                continue
            lines = self._call("account.analytic.line", "search_read",
                               domain=[(col, "in", ids), ("general_account_id.code", "=like", "630%"),
                                       ("date", ">=", d_from.isoformat()), ("date", "<=", d_to.isoformat())],
                               fields=["date", col, "amount"])
            per: dict[int, dict[str, float]] = {}
            for l in lines:
                if l.get(col):
                    month = str(l["date"])[:7]
                    d = per.setdefault(l[col][0] if isinstance(l[col], (list, tuple)) else l[col], {})
                    d[month] = d.get(month, 0.0) - float(l["amount"] or 0.0)
            for aid, d in per.items():
                monthly[(col, aid)] = d[max(d)]
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
            e["result"] = e["ca"] - e["direct_costs"] - e["other_costs"] - e["capex"]      # résultat cash : hors dotations, investissements inclus
            e["result_accounting"] = e["ca"] - e["direct_costs"] - e["other_costs"] - e["amort"]
            e["amort_monthly"], e["amort_months"] = monthly.get((e["plan"], e["id"]), 0.0), 0
            if e["capex"] and e["amort_monthly"]:
                e["amort_months"] = round(e["capex"] / e["amort_monthly"])             # durée implicite (investi ÷ dotation mensuelle)
            for k in ("ca", "direct_costs", "other_costs", "capex", "amort", "amort_monthly", "result", "result_accounting"):
                e[k] = round(e[k])
            if e["ca"] or e["direct_costs"] or e["other_costs"] or e["capex"] or e["amort"]:
                out.append(e)
        out.sort(key=lambda e: (-e["ca"], e["name"]))
        return {"items": out, "plans": [p["name"] for p in plans], "bu_axis": bu_plan["name"],
                "bu_unmapped": sorted(unmapped), "bu_missing": missing,
                "bu_missing_detail": sorted(missing_detail, key=lambda m: -abs(m["amount"]))[:20]}

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

    @staticmethod
    def _buckets(d_from: date, d_to: date, weekly: bool | None = None) -> tuple[str, list[tuple[date, str]]]:
        """Découpage de la période : par semaine (lundi) si elle ne dépasse pas 45 jours, sinon par mois (ou selon `weekly`)."""
        mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
        if (weekly if weekly is not None else (d_to - d_from).days <= 45):
            d, out = d_from - timedelta(days=d_from.weekday()), []
            while d <= d_to:
                out.append((d, f"{d.day} {mois[d.month - 1]}"))
                d += timedelta(days=7)
            return "week", out
        y, m, out = d_from.year, d_from.month, []
        while (y, m) <= (d_to.year, d_to.month):
            out.append((date(y, m, 1), f"{mois[m - 1]} {y}"))
            y, m = (y + 1, 1) if m == 12 else (y, m + 1)
        return "month", out

    @staticmethod
    def _shop_pages(wid: int) -> list:
        """Domaine des pages vues du webshop `wid` : visiteurs de ce site, chemin WEBSHOP_PATH, et — pour les pages produit — produit
        rattaché à CE site (champ « Site web » de la fiche produit). Odoo attribue parfois à un site des visites de produits d'un
        autre site ; une page sans produit (accueil du shop) est conservée. Un produit sans site précis (publié partout) est gardé
        sauf si WEBSHOP_STRICT_SITE est activé."""
        product = [("product_id", "=", False), ("product_id.website_id", "=", wid)] + ([] if settings.WEBSHOP_STRICT_SITE else [("product_id.website_id", "=", False)])
        return [("visitor_id.website_id", "=", wid), ("url", "like", f"%{settings.WEBSHOP_PATH}%")] + ["|"] * (len(product) - 1) + product

    def _visits(self, wid: int, d_from: date, d_to: date) -> dict:
        """Visites du webshop d'après le suivi des pages d'Odoo (website.track), limité aux pages du chemin WEBSHOP_PATH.
        Pages vues et visiteurs uniques par semaine/mois, et totaux de la période. Odoo ne suit que certaines pages
        (produits, pages marquées « suivre ») : ce sont des ordres de grandeur, pas une mesure d'audience exhaustive."""
        gran, buckets = self._buckets(d_from, d_to, weekly=True)
        shop = self._shop_pages(wid)

        def span(a: date, b: date) -> list:
            return shop + [("visit_datetime", ">=", a.isoformat()), ("visit_datetime", "<", (b + timedelta(days=1)).isoformat())]

        def count(a: date, b: date) -> tuple[int, int | None]:
            try:
                r = self._call("website.track", "formatted_read_group", domain=span(a, b), groupby=[],
                               aggregates=["__count", "visitor_id:count_distinct"])
                return (int(r[0]["__count"]), int(r[0]["visitor_id:count_distinct"])) if r else (0, 0)
            except httpx.HTTPStatusError as e:
                if e.response.status_code in (401, 403):
                    raise
                return self._call("website.track", "search_count", domain=span(a, b)), None     # repli : sans visiteurs uniques

        ranges = []
        for i, (st, lbl) in enumerate(buckets):
            end = (buckets[i + 1][0] - timedelta(days=1)) if i + 1 < len(buckets) else d_to
            ranges.append((max(st, d_from), min(end, d_to), lbl))
        with ThreadPoolExecutor(max_workers=5) as pool:
            res = list(pool.map(lambda r: count(r[0], r[1]), ranges + [(d_from, d_to, "")]))
        # Odoo supprime les visiteurs anonymes inactifs depuis ~60 jours (et leurs pages vues) : avant la plus ancienne visite
        # anonyme encore présente, l'historique est incomplet (il ne reste que des visiteurs identifiés). On ne trace pas cette partie.
        first = None
        try:
            f = self._call("website.track", "search_read", domain=shop + [("visitor_id.partner_id", "=", False)],
                           fields=["visit_datetime"], order="visit_datetime asc", limit=1)
            first = date.fromisoformat(str(f[0]["visit_datetime"])[:10]) if f else None
        except Exception:
            first = None
        pts = [{"label": r[2], "views": v, "visitors": u, "avg": None if first and r[1] < first else float(v)}
               for r, (v, u) in zip(ranges, res[:-1])]
        views, visitors = res[-1]
        orders = self._call("sale.order", "search_count", domain=[("website_id", "=", wid), ("state", "in", ["sale", "done"]),
                                                                  ("date_order", ">=", d_from.isoformat()), ("date_order", "<", (d_to + timedelta(days=1)).isoformat())])
        return {"granularity": gran, "points": pts, "views": views, "visitors": visitors, "orders": orders, "path": settings.WEBSHOP_PATH,
                "from": d_from.isoformat(), "to": d_to.isoformat(),
                "complete_from": first.isoformat() if first else None,
                "incomplete": bool(first and first > d_from + timedelta(days=7))}

    @staticmethod
    def _page_label(url: str) -> tuple[str, str]:
        """(libellé lisible, chemin) d'une URL suivie : « /shop/pneu-cross-car-1234?x=1 » -> (« Pneu cross car », « /shop/pneu-cross-car-1234 »)."""
        path = unquote(urlsplit(url or "").path) or "/"
        slug = path.rstrip("/").rsplit("/", 1)[-1]
        slug = re.sub(r"-\d+$", "", slug)                       # Odoo suffixe le slug avec l'identifiant du produit
        label = slug.replace("-", " ").strip().capitalize() if slug and slug.lower() != settings.WEBSHOP_PATH.strip("/").lower() else "Page d'accueil du shop"
        return label or path, path

    def _top_pages(self, wid: int, d_from: date, d_to: date, top: int = 15) -> list[dict]:
        """Pages les plus vues du webshop (adresses regroupées sans leurs paramètres)."""
        dom = self._shop_pages(wid) + [("visit_datetime", ">=", d_from.isoformat()), ("visit_datetime", "<", (d_to + timedelta(days=1)).isoformat())]
        rows = self._call("website.track", "formatted_read_group", domain=dom, groupby=["url"], aggregates=["__count"],
                          order="__count desc", limit=300)
        merged: dict[str, dict] = {}
        for r in rows:
            if not r.get("url"):
                continue
            label, path = self._page_label(r["url"])
            m = merged.setdefault(path, {"label": label, "path": path, "views": 0})
            m["views"] += int(r["__count"])
        pages = sorted(merged.values(), key=lambda m: -m["views"])[:top]
        total = sum(m["views"] for m in merged.values())
        for m in pages:
            m["share"] = m["views"] / total if total else 0.0
        return pages

    def _basket_series(self, d_from: date, d_to: date, base: list) -> dict[int, dict]:
        """Panier moyen (HT) par semaine/mois et par site web : {website_id: {granularity, points[{label, orders, revenue, avg}]}}."""
        gran, buckets = self._buckets(d_from, d_to)
        starts = [b[0] for b in buckets]
        acc: dict[int, dict[date, list[float]]] = {}
        orders = self._call("sale.order", "search_read", domain=base + [("website_id", "!=", False)],
                            fields=["website_id", "date_order", "amount_untaxed"])
        for o in orders:
            if not o.get("website_id") or not o.get("date_order"):
                continue
            d = date.fromisoformat(str(o["date_order"])[:10])
            key = max((st for st in starts if st <= d), default=None)
            if key is None:
                continue
            c = acc.setdefault(o["website_id"][0], {}).setdefault(key, [0, 0.0])
            c[0] += 1
            c[1] += float(o["amount_untaxed"] or 0.0)
        return {wid: {"granularity": gran,
                      "points": [{"label": lbl, "orders": int(by.get(st, [0, 0.0])[0]), "revenue": round(by.get(st, [0, 0.0])[1]),
                                  "avg": round(by[st][1] / by[st][0], 2) if st in by and by[st][0] else None} for st, lbl in buckets]}
                for wid, by in acc.items()}

    @staticmethod
    def _why(e: Exception) -> str:
        """Motif court d'un échec Odoo (message d'erreur renvoyé par l'API, sans données sensibles)."""
        r = getattr(e, "response", None)
        if r is not None:
            try:
                j = r.json()
                return f"HTTP {r.status_code} — {str(j.get('message') or j.get('name') or '')[:300]}".strip(" —")
            except Exception:
                return f"HTTP {r.status_code}"
        return f"{type(e).__name__}: {str(e)[:200]}"

    def _payments(self, wid: int, order_dom: list) -> list[dict]:
        """Méthodes de paiement des commandes confirmées d'un site web (transactions réussies, en attente ou autorisées)."""
        dom = [("sale_order_ids.website_id", "=", wid), ("sale_order_ids.state", "in", ["sale", "done"]),
               ("state", "in", ["done", "authorized", "pending"])] + [("sale_order_ids." + f, op, v) for f, op, v in order_dom]
        try:
            rows = self._call("payment.transaction", "formatted_read_group", domain=dom, groupby=["payment_method_id"],
                              aggregates=["amount:sum", "__count"])
            key = "payment_method_id"
        except Exception:                                      # anciennes versions / droits : repli sur le fournisseur de paiement
            rows = self._call("payment.transaction", "formatted_read_group", domain=dom, groupby=["provider_id"],
                              aggregates=["amount:sum", "__count"])
            key = "provider_id"
        out = [{"name": (r[key][1] if r.get(key) else "Non renseigné"), "count": r["__count"], "amount": round(r["amount:sum"] or 0)} for r in rows]
        total = sum(x["count"] for x in out)
        for x in out:
            x["share"] = x["count"] / total if total else 0.0
        return sorted(out, key=lambda x: -x["count"])

    def _deliveries(self, wid: int, order_dom: list) -> list[dict]:
        """Modes de livraison des commandes confirmées d'un site web (sans transporteur = retrait, produit virtuel…)."""
        rows = self._call("sale.order", "formatted_read_group", domain=[("website_id", "=", wid)] + order_dom,
                          groupby=["carrier_id"], aggregates=["amount_untaxed:sum", "__count"])
        out = [{"name": (r["carrier_id"][1] if r.get("carrier_id") else "Sans livraison (retrait, service…)"), "count": r["__count"],
                "amount": round(r["amount_untaxed:sum"] or 0)} for r in rows]
        total = sum(x["count"] for x in out)
        for x in out:
            x["share"] = x["count"] / total if total else 0.0
        return sorted(out, key=lambda x: -x["count"])

    def _abandoned(self, wid: int, d_from: date, d_to: date, confirmed: dict | None) -> dict:
        """Paniers abandonnés d'un site web : devis web non confirmés, contenant au moins un article, plus anciens que le délai
        d'abandon du site. « Identifiés » = notion d'Odoo (menu Paniers abandonnés : client connecté) ; « anonymes » = visiteurs
        non connectés. Évolution du taux d'abandon = abandonnés ÷ (abandonnés + commandes confirmées)."""
        gran, buckets = self._buckets(d_from, d_to)
        starts = [b[0] for b in buckets]
        try:
            delay = float(self._call("website", "read", ids=[wid], fields=["cart_abandoned_delay"])[0]["cart_abandoned_delay"] or 1.0)
        except Exception:
            delay = 1.0                                              # délai par défaut d'Odoo : 1 heure
        limit = min(datetime.utcnow() - timedelta(hours=delay), datetime.combine(d_to + timedelta(days=1), datetime.min.time()))
        dom = [("website_id", "=", wid), ("state", "=", "draft"), ("order_line", "!=", False), ("date_order", ">=", d_from.isoformat()),
               ("date_order", "<", limit.strftime("%Y-%m-%d %H:%M:%S"))]
        rows = self._call("sale.order", "search_read", domain=dom, fields=["date_order", "amount_untaxed"])
        known = {r["id"] for r in self._call("sale.order", "search_read", domain=dom + [("is_abandoned_cart", "=", True)], fields=["id"])}
        by: dict[date, list[float]] = {}
        for o in rows:
            if not o.get("date_order"):
                continue
            d = date.fromisoformat(str(o["date_order"])[:10])
            key = max((st for st in starts if st <= d), default=None)
            if key is not None:
                c = by.setdefault(key, [0, 0.0, 0])
                c[0] += 1
                c[1] += float(o["amount_untaxed"] or 0.0)
                c[2] += 1 if o.get("id") in known else 0
        # Odoo semble purger les anciens paniers non confirmés : avant le plus ancien panier encore présent, le taux serait
        # faussé (aucun abandon pour de vraies commandes). On ne calcule le taux que sur les périodes entièrement couvertes.
        first = None
        try:
            f = self._call("sale.order", "search_read", domain=[("website_id", "=", wid), ("state", "=", "draft"), ("order_line", "!=", False)],
                           fields=["date_order"], order="date_order asc", limit=1)
            first = date.fromisoformat(str(f[0]["date_order"])[:10]) if f else None
        except Exception:
            first = None
        conf = {pt["label"]: pt["orders"] for pt in (confirmed or {}).get("points", [])}
        pts, cov_ab, cov_ok, rate_from = [], 0, 0, None
        for st, lbl in buckets:
            n, amt, ident = by.get(st, [0, 0.0, 0])
            ok = conf.get(lbl, 0)
            covered = first is None or st >= first      # un mois/une semaine commençant avant le plus ancien panier est partiel : écarté
            if covered:
                cov_ab, cov_ok = cov_ab + n, cov_ok + ok
                rate_from = rate_from or st
            pts.append({"label": lbl, "orders": ok, "abandoned": int(n), "identified": int(ident), "amount": round(amt),
                        "avg": round(n / (n + ok), 4) if covered and n + ok else None})
        n_ab, amt = len(rows), sum(float(o["amount_untaxed"] or 0.0) for o in rows)
        return {"count": n_ab, "identified": len(known), "anonymous": n_ab - len(known), "amount": round(amt),
                "rate": cov_ab / (cov_ab + cov_ok) if cov_ab + cov_ok else 0.0, "series": {"granularity": gran, "points": pts},
                "incomplete": bool(first and first > d_from + timedelta(days=7)),
                "complete_from": first.isoformat() if first else None, "rate_from": rate_from.isoformat() if rate_from else None}

    def _top_customers(self, wid: int, base: list, top: int = 15) -> dict:
        """Meilleurs clients d'un webshop sur la période : CA HT, commandes, panier moyen, part du CA du webshop, méthodes de paiement
        et de livraison utilisées, pays, dernière commande. Regroupements comme ailleurs (société mère, étiquettes regroup_client=)."""
        orders = self._call("sale.order", "search_read", domain=base + [("website_id", "=", wid)],
                            fields=["partner_id", "amount_untaxed", "date_order", "carrier_id"])
        orders = [o for o in orders if o.get("partner_id")]
        if not orders:
            return {"customers": [], "total_ca": 0, "total_orders": 0, "count": 0, "repeat": 0, "top_ca": 0}
        groups = self._client_groups({o["partner_id"][0] for o in orders})
        pay: dict[int, str] = {}
        try:                                                           # facultatif : nécessite l'accès aux transactions de paiement
            for t in self._call("payment.transaction", "search_read",
                                domain=[("sale_order_ids", "in", [o["id"] for o in orders]), ("state", "in", ["done", "authorized", "pending"])],
                                fields=["sale_order_ids", "payment_method_id", "provider_id"]):
                name = (t.get("payment_method_id") or t.get("provider_id") or [0, ""])[1] or "Non renseigné"
                for oid in t.get("sale_order_ids") or []:
                    pay.setdefault(oid, name)
        except Exception:
            pay = {}
        agg: dict[str, dict] = {}
        for o in orders:
            key, label = groups.get(o["partner_id"][0], (f"p:{o['partner_id'][0]}", o["partner_id"][1]))
            c = agg.setdefault(key, {"key": key, "name": normalize_name(label), "ca": 0.0, "orders": 0, "last": "", "pay": {}, "ship": {}})
            c["ca"] += float(o["amount_untaxed"] or 0.0)
            c["orders"] += 1
            c["last"] = max(c["last"], str(o.get("date_order") or "")[:10])
            if o["id"] in pay:
                c["pay"][pay[o["id"]]] = c["pay"].get(pay[o["id"]], 0) + 1
            ship = o["carrier_id"][1] if o.get("carrier_id") else "Sans livraison"
            c["ship"][ship] = c["ship"].get(ship, 0) + 1
        total_ca = sum(c["ca"] for c in agg.values())
        best = sorted(agg.values(), key=lambda c: -c["ca"])[:top]
        com_ids = [int(c["key"][2:]) for c in best if c["key"].startswith("c:")]
        country: dict[str, str] = {}
        if com_ids:
            try:
                for r in self._call("res.partner", "read", ids=com_ids, fields=["country_id"]):
                    if r.get("country_id"):
                        country[f"c:{r['id']}"] = r["country_id"][1]
            except Exception:
                pass
        rank = lambda d: [{"name": k, "count": v} for k, v in sorted(d.items(), key=lambda kv: -kv[1])][:3]   # noqa: E731
        customers = [{"name": c["name"], "ca": round(c["ca"]), "orders": c["orders"], "avg_basket": round(c["ca"] / c["orders"], 2),
                      "share": c["ca"] / total_ca if total_ca else 0.0, "country": country.get(c["key"], ""), "last_order": c["last"],
                      "payments": rank(c["pay"]), "deliveries": rank(c["ship"])} for c in best]
        return {"customers": customers, "total_ca": round(total_ca), "total_orders": sum(c["orders"] for c in agg.values()),
                "count": len(agg), "repeat": sum(1 for c in agg.values() if c["orders"] >= 2), "top_ca": round(sum(c["ca"] for c in best))}

    def _pickings(self, wid: int | None, weeks: int, exclude_sites: list[int] | None = None) -> dict:
        """Bons de livraison validés par semaine (= commandes préparées au magasin) et nombre de produits expédiés.

        `wid` : limiter aux commandes de ce site web ; None = tous les bons de livraison sortants, sauf ceux des commandes des sites
        de `exclude_sites` (webshop Goldspeed : livré par le Race Team, pas par le magasinier). Semaines commençant le lundi,
        la semaine en cours comprise. Les produits = quantités des mouvements de stock terminés de ces bons."""
        today = date.today()
        first = today - timedelta(days=today.weekday() + 7 * (weeks - 1))
        starts = [first + timedelta(days=7 * i) for i in range(weeks)]
        mois = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]
        dom = [("picking_type_code", "=", "outgoing"), ("state", "=", "done"), ("date_done", ">=", first.isoformat()),
               ("date_done", "<", (today + timedelta(days=1)).isoformat())]
        if wid is not None:
            dom.append(("sale_id.website_id", "=", wid))
        elif exclude_sites:
            dom += ["|", ("sale_id", "=", False), ("sale_id.website_id", "not in", exclude_sites)]
        picks = self._call("stock.picking", "search_read", domain=dom, fields=["date_done"])
        week_of: dict[int, date] = {}
        for pk in picks:
            if pk.get("date_done"):
                d = date.fromisoformat(str(pk["date_done"])[:10])
                week_of[pk["id"]] = max(st for st in starts if st <= d)
        orders = {st: 0 for st in starts}
        units = {st: 0.0 for st in starts}
        for st in week_of.values():
            orders[st] += 1
        ids = list(week_of)
        for k in range(0, len(ids), 400):
            for r in self._call("stock.move", "formatted_read_group", domain=[("picking_id", "in", ids[k:k + 400]), ("state", "=", "done")],
                                groupby=["picking_id"], aggregates=["quantity:sum"]):
                if r.get("picking_id") and r["picking_id"][0] in week_of:
                    units[week_of[r["picking_id"][0]]] += float(r["quantity:sum"] or 0.0)
        pts = [{"label": f"{st.day} {mois[st.month - 1]}", "orders": orders[st], "units": round(units[st]),
                "per_order": round(units[st] / orders[st], 1) if orders[st] else None} for st in starts]
        n, u = sum(orders.values()), sum(units.values())
        return {"weeks": weeks, "points": pts, "orders": n, "units": round(u), "per_order": round(u / n, 1) if n else None}

    def webshops(self, d_from: date, d_to: date, top: int = 15) -> list[dict]:
        """Ventes des sites web (commandes confirmées, HT) et top produits (valeur, unités, % du total)."""
        base = [("state", "in", ["sale", "done"]), ("date_order", ">=", d_from.isoformat()),
                ("date_order", "<", (d_to + timedelta(days=1)).isoformat())]
        out = []
        vt = date.today()
        vf = vt - timedelta(days=settings.VISITS_DAYS - 1)      # visites : fenêtre fixe (Odoo n'en garde que ~60 jours), indépendante de la période
        try:
            series = self._basket_series(d_from, d_to, base)
        except Exception:                                      # le graphique est un plus : ne bloque pas le reste de la page
            series = {}
        try:                                                   # sites « Goldspeed » : leurs livraisons ne passent pas par le magasinier
            gold = {w["id"] for w in self._call("website", "search_read", domain=[], fields=["name"])
                    if re.search("goldspeed", f"{w['name']} {settings.WEBSHOP_LABELS.get(w['name'], '')}", re.I)}
        except Exception:
            gold = set()
        groups = self._call("sale.order", "formatted_read_group", domain=base + [("website_id", "!=", False)],
                            groupby=["website_id"], aggregates=["amount_untaxed:sum", "__count"])
        for g in groups:
            wid, wname = g["website_id"]
            n, revenue = g["__count"], g["amount_untaxed:sum"]
            order_dom = [("date_order", ">=", d_from.isoformat()), ("date_order", "<", (d_to + timedelta(days=1)).isoformat())]

            errors: dict[str, str] = {}

            def safe(name, fn, *a):                            # chaque vue est facultative : une erreur n'empêche pas les autres
                try:
                    return fn(*a)
                except Exception as e:
                    errors[name] = self._why(e)
                    return None
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
                        "avg_basket": round(revenue / n, 2) if n else 0.0, "basket_series": series.get(wid),
                        "payments": safe("payments", self._payments, wid, order_dom),
                        "deliveries": safe("deliveries", self._deliveries, wid, [("state", "in", ["sale", "done"])] + order_dom),
                        "abandoned": safe("abandoned", self._abandoned, wid, d_from, d_to, series.get(wid)),
                        "visits": safe("visits", self._visits, wid, vf, vt), "top_pages": safe("top_pages", self._top_pages, wid, vf, vt),
                        "customers": safe("customers", self._top_customers, wid, base),
                        "pickings": None if wid in gold else safe("pickings", lambda w=wid: {"web": self._pickings(w, settings.PICKING_WEEKS),
                                                                                   "all": self._pickings(None, settings.PICKING_WEEKS, sorted(gold))}), "errors": errors,
                        "products": [{"name": names[l["product_id"][0]], "value": round(l["price_subtotal:sum"]),
                                      "units": round(l["product_uom_qty:sum"], 2),
                                      "share": l["price_subtotal:sum"] / total_value if total_value else 0.0} for l in best],
                        "products_total": {"value": round(total_value), "units": round(total_units, 2), "count": len(prods)}})
        return sorted(out, key=lambda w: -w["revenue"])
