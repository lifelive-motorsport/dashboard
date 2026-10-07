"""Frais généraux : choix des comptes comptables retenus (« Données source ») et calculs d'affichage.

La configuration est un petit document Firestore partagé (lecture pour tous, écriture pour les administrateurs). Rien n'est écrit dans Odoo.
Un compte de charges (classe 6) est : traité ailleurs (achats 60x par BU, personnel 62x et 618, marketing), ignoré (compte « old »),
ou candidat : à ranger en « frais généraux », en « véhicules de service » (menu dédié) ou à laisser de côté."""
from __future__ import annotations

import calendar
import re
import threading
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import settings
from .bu import is_old

KINDS = ("general", "vehicle")
CODE = re.compile(r"^\d{3,10}$")


class Config(BaseModel):
    selected: dict[str, Literal["general", "vehicle", "partners"]] = Field(default_factory=dict)   # compte -> rubrique ; « partners » : selon le fournisseur ; absent = laissé de côté
    partners: dict[str, dict[str, Literal["general", "vehicle"]]] = Field(default_factory=dict)    # compte « partners » -> {id fournisseur -> rubrique} ; les autres fournisseurs sont laissés de côté
    saved: bool = False
    plates: dict[str, str] = Field(default_factory=dict)                                           # plaque (sans tiret, majuscules) -> libellé du véhicule de service (carte carburant)
    links: dict[str, str] = Field(default_factory=dict)                                            # véhicule tel que nommé dans Odoo (compte 615) -> ressource de l'agenda Google
    split: dict[str, dict[str, float]] = Field(default_factory=dict)                               # véhicule -> {XC|MODERN_RALLY|HISTORIC_RALLY|HISTORIC_RACING|GENERAL: % retenu} ; absent = proposition indicative
    general_vehicles: list[str] = Field(default_factory=list)                                      # « véhicules » des comptes 615 qui sont en fait des frais généraux (BMW X5, machines…)
    key_mode: Literal["revenue", "pct"] = "revenue"                                                # clé d'imputation XC / CARS : prorata du CA, ou % encodé
    xc_pct: float = Field(default=50.0, ge=0, le=100)                                              # part XC en % pour la clé « pct » (CARS = le reste)

    @field_validator("selected")
    @classmethod
    def _codes(cls, v):
        for k in v:
            if not CODE.match(k):
                raise ValueError(f"code de compte invalide : {k}")
        return v

    @field_validator("plates")
    @classmethod
    def _plates(cls, v):
        out = {}
        for k, name in v.items():
            k2 = re.sub(r"[\s-]+", "", k).upper()
            if not re.fullmatch(r"[A-Z0-9]{2,14}", k2) or len(name) > 80:
                raise ValueError(f"plaque invalide : {k}")
            if name.strip():
                out[k2] = name.strip()
        return out

    @field_validator("partners")
    @classmethod
    def _partners(cls, v):
        for k, d in v.items():
            if not CODE.match(k) or any(not re.match(r"^\d{1,12}$", pid) for pid in d):
                raise ValueError("fournisseur ou compte invalide")
        return v


    @field_validator("general_vehicles")
    @classmethod
    def _general(cls, v):
        if len(v) > 200 or any(not n.strip() or len(n) > 120 for n in v):
            raise ValueError("véhicule invalide")
        return sorted({n.strip() for n in v})

    @field_validator("split")
    @classmethod
    def _split(cls, v):
        out = {}
        for veh, d in v.items():
            if not veh.strip() or len(veh) > 120 or any(k not in SPLIT_KEYS or not (0 <= x <= 100) for k, x in d.items()):
                raise ValueError("imputation invalide")
            if d:
                out[veh.strip()] = {k: round(x, 2) for k, x in d.items()}
        return out

    @field_validator("links")
    @classmethod
    def _links(cls, v):
        out = {}
        for k, name in v.items():
            if not k.strip() or len(k) > 120 or len(name) > 160:
                raise ValueError("véhicule invalide")
            if name.strip():
                out[k.strip()] = name.strip()
        return out


SPLIT_KEYS = ("XC", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING", "GENERAL")
_NOT_A_VEHICLE = re.compile(r"lou[ée]s?\b|location|divers|autres?\b|non class|g[ée]n[ée]ra|flotte", re.I)


def is_identified(vehicle: str) -> bool:
    """Un véhicule identifié a un nom propre ; « véhicules loués », « divers », « (non classé) »… sont des frais non liés à un véhicule précis."""
    return not _NOT_A_VEHICLE.search(vehicle or "")


class SplitBody(BaseModel):
    split: dict[str, dict[str, float]]
    general: list[str] | None = None
    base: str | None = None


class LinksBody(BaseModel):
    links: dict[str, str]
    base: str | None = None


class PlatesBody(BaseModel):
    plates: dict[str, str]
    base: str | None = None


class KeyBody(BaseModel):
    key_mode: Literal["revenue", "pct"]
    xc_pct: float = Field(ge=0, le=100)
    base: str | None = None


class SaveBody(BaseModel):
    data: Config
    base: str | None = None


class Store:
    """Document unique (Firestore en production, mémoire en démo / essais)."""
    def __init__(self):
        self._lock = threading.Lock()
        self._doc = {"data": Config().model_dump(), "updated_at": None, "updated_by": None}
        self._ref = None
        if settings.ADJUSTMENTS_STORE == "firestore":
            from google.cloud import firestore
            self._ref = firestore.Client().collection("dashboard").document("expenses")

    def get(self) -> dict:
        if self._ref is not None:
            snap = self._ref.get()
            d = snap.to_dict() if snap.exists else {}
            return {"data": d.get("data") or Config().model_dump(), "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}
        with self._lock:
            return dict(self._doc)

    def put(self, data: dict, user: str, base: str | None) -> dict | None:
        cur = self.get()
        if (cur["updated_at"] or None) != (base or None):
            return None
        doc = {"data": data, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
        if self._ref is not None:
            self._ref.set(doc)
        else:
            with self._lock:
                self._doc = doc
        return doc


_store = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def family(code: str, name: str) -> str:
    """« old » (ancien plan, ignoré) | « bu » (achats et sous-traitance par BU) | « staff » | « marketing » | « candidate »."""
    if is_old(name):
        return "old"
    if code in settings.EXPENSES_EXCLUDED_ACCOUNTS:
        return "excluded"
    if code in settings.MARKETING_ACCOUNTS:
        return "marketing"
    if code.startswith("62") or code in settings.STAFF_DIRECTOR_PAY or code in settings.STAFF_DIRECTOR_SOCIAL:
        return "staff"
    if code.startswith("60"):
        return "bu"
    return "candidate"


def suggestion(code: str) -> str | None:
    """Proposition de départ (avant tout enregistrement) : les comptes dont le code commence par EXPENSES_DEFAULT_PREFIXES."""
    if any(code.startswith(p) for p in settings.EXPENSES_DEFAULT_PREFIXES):
        return "general"
    return "vehicle" if any(code.startswith(p) for p in settings.EXPENSES_VEHICLE_PREFIXES) else None


def effective(config: dict, codes) -> dict[str, str]:  # noqa: D401
    """Rubrique retenue par compte : la configuration enregistrée, ou, tant que rien n'est enregistré, la proposition de départ."""
    if config.get("saved"):
        return dict(config.get("selected") or {})
    return {c: s for c in codes if (s := suggestion(c))}


def closed_months(year: int, today: date | None = None) -> tuple[float, str | None]:
    """(nombre de mois entièrement écoulés, dernier mois clos « AAAA-MM »). Le mois en cours est incomplet : on ne le compte pas et on ne le trace pas
    (sinon la courbe semble descendre). 7 octobre : 9 mois, jusqu'à 2026-09. Dans le premier mois de l'année : la fraction écoulée, sans mois clos."""
    t = today or date.today()
    if year < t.year:
        return 12.0, f"{year}-12"
    if year > t.year:
        return 1.0, None
    last_day = calendar.monthrange(t.year, t.month)[1]
    closed = t.month if t.day == last_day else t.month - 1
    if closed < 1:
        return max(t.day / last_day, 0.05), None
    return float(closed), f"{t.year}-{closed:02d}"


def months_elapsed(year: int, today: date | None = None) -> float:
    return closed_months(year, today)[0]


def _month_series(accounts: list[dict]) -> list[dict]:
    m: dict[str, float] = {}
    for a in accounts:
        for k, v in a["by_month"].items():
            m[k] = m.get(k, 0.0) + v
    return [{"month": k, "amount": round(v, 2)} for k, v in sorted(m.items())]


def _for_kind(a: dict, sel: dict, config: dict, kind: str) -> dict | None:
    """Part d'un compte qui revient à la rubrique `kind` : le compte entier, ou seulement les fournisseurs choisis pour ce compte."""
    mode = sel.get(a["code"])
    if mode == kind:
        return a
    if mode != "partners":
        return None
    rules = (config.get("partners") or {}).get(a["code"], {})
    ps = {pid: p for pid, p in a["partners"].items() if rules.get(str(pid)) == kind}
    if not ps:
        return None
    by_month: dict[str, float] = {}
    for p in ps.values():
        for m, v in p.get("by_month", {}).items():
            by_month[m] = by_month.get(m, 0.0) + v
    return {"code": a["code"], "name": a["name"], "total": sum(p["amount"] for p in ps.values()), "by_month": by_month, "partners": ps}


def accounts_view(lines: list[dict], config: dict, year: int, today: date | None = None) -> dict:
    """Page « Données source » : comptes candidats avec leur rubrique, fournisseurs des comptes « selon le fournisseur » et totaux des familles traitées ailleurs."""
    cand = [a for a in lines if family(a["code"], a["name"]) == "candidate"]
    sel = effective(config, [a["code"] for a in cand])
    elsewhere: dict[str, float] = {}
    for a in lines:
        f = family(a["code"], a["name"])
        if f in ("bu", "staff", "marketing", "excluded"):
            elsewhere[f] = elsewhere.get(f, 0.0) + a["total"]
    accounts = []
    last = closed_months(year, today)[1]
    for a in sorted(cand, key=lambda a: a["code"]):
        row = {"code": a["code"], "name": a["name"], "total": round(a["total"], 2), "closed_total": round(sum(v for m, v in a["by_month"].items() if last is None or m <= last), 2),
               "months": len(a["by_month"]), "kind": sel.get(a["code"]), "suggested": suggestion(a["code"])}
        rules = (config.get("partners") or {}).get(a["code"], {})                                  # fournisseurs toujours fournis : on peut passer un compte en « selon le fournisseur » avant d'enregistrer
        row["partners"] = [{"id": str(pid), "name": p["name"], "total": round(p["amount"], 2), "kind": rules.get(str(pid))}
                           for pid, p in sorted(a["partners"].items(), key=lambda kv: -abs(kv[1]["amount"]))[:80]]
        accounts.append(row)
    return {"year": year, "saved": bool(config.get("saved")), "accounts": accounts, "months_elapsed": round(months_elapsed(year, today), 2),
            "elsewhere": {k: round(v) for k, v in elsewhere.items()}, "marketing_accounts": settings.MARKETING_ACCOUNTS, "excluded_accounts": settings.EXPENSES_EXCLUDED_ACCOUNTS, "vehicle_prefixes": settings.EXPENSES_VEHICLE_PREFIXES,
            "partner_rules": config.get("partners") or {}}


def kind_view(lines: list[dict], config: dict, year: int, kind: str, today: date | None = None) -> dict:
    """Résultat pour une rubrique (« general » ou « vehicle ») : total, évolution mensuelle, comptes, principaux fournisseurs."""
    cand = [a for a in lines if family(a["code"], a["name"]) == "candidate"]
    sel = effective(config, [a["code"] for a in cand])
    mine = [x for a in cand if (x := _for_kind(a, sel, config, kind))]
    months, last = closed_months(year, today)
    all_months = _month_series(mine)
    series = [x for x in all_months if last is None or x["month"] <= last]                           # le mois en cours (incomplet) n'est pas tracé
    total = sum(a["total"] for a in mine)
    closed_total = sum(x["amount"] for x in series) if last else total
    partners: dict[str, dict] = {}
    for a in mine:
        for pid, p in a["partners"].items():
            d = partners.setdefault(str(pid), {"name": p["name"], "amount": 0.0})
            d["amount"] += p["amount"]
    sup = sorted(partners.values(), key=lambda x: -x["amount"])[:15]
    return {"year": year, "kind": kind, "total": round(total, 2), "months": round(months, 2), "last_closed": last, "monthly_avg": round(closed_total / months, 2), "projected": round(closed_total / months * 12, 2),
            "series": series, "all_months": all_months,
            "accounts": [{"code": a["code"], "name": a["name"] + (" (fournisseurs choisis)" if sel.get(a["code"]) == "partners" else ""), "total": round(a["total"], 2), "share": (a["total"] / total) if total else 0.0}
                         for a in sorted(mine, key=lambda a: -a["total"])],
            "suppliers": [{"name": s["name"], "amount": round(s["amount"], 2), "share": (s["amount"] / total) if total else 0.0} for s in sup],
            "configured": bool(config.get("saved")), "empty": not mine}


def allocation_view(general: dict, ca_xc: float, ca_cars: float, config: dict) -> dict:
    """Imputation des frais généraux entre XC et CARS selon les deux clés possibles ; la clé active est celle de la configuration."""
    cfg = Config.model_validate({**config})
    ca = max(ca_xc, 0.0) + max(ca_cars, 0.0)
    rev_xc = (max(ca_xc, 0.0) / ca) if ca else 0.5
    pct_xc = cfg.xc_pct / 100
    keys = {"revenue": {"XC": rev_xc, "CARS": 1 - rev_xc}, "pct": {"XC": pct_xc, "CARS": 1 - pct_xc}}
    total = general["total"]
    amounts = {k: {g: round(total * v, 2) for g, v in sh.items()} for k, sh in keys.items()}
    return {"key_mode": cfg.key_mode, "xc_pct": cfg.xc_pct, "ca": {"XC": round(ca_xc, 2), "CARS": round(ca_cars, 2)}, "shares": keys, "amounts": amounts,
            "total": general["total"], "monthly_avg": general["monthly_avg"], "projected": general["projected"], "months": general["months"], "empty": general["empty"],
            "series": general["series"], "accounts": general["accounts"], "configured": general["configured"]}


def month_lines(raw: list[dict], config: dict, kind: str, month: str, limit: int = 15) -> dict:
    """Plus grosses écritures d'un mois sur les comptes retenus pour la rubrique `kind` (comptes entiers ou fournisseurs choisis)."""
    sel = effective(config, sorted({r["code"] for r in raw if family(r["code"], r["name"]) == "candidate"}))
    rules = config.get("partners") or {}
    keep = []
    for r in raw:
        if family(r["code"], r["name"]) != "candidate":
            continue
        mode = sel.get(r["code"])
        if mode == kind or (mode == "partners" and (rules.get(r["code"]) or {}).get(str(r.get("partner_id") or 0)) == kind):
            keep.append(r)
    total = sum(r["amount"] for r in keep)
    top = sorted(keep, key=lambda r: -abs(r["amount"]))[:limit]
    return {"month": month, "total": round(total, 2), "count": len(keep), "lines": [{k: (round(v, 2) if k == "amount" else v) for k, v in r.items() if k != "partner_id"} for r in top]}


_VEHICLE_NAME = re.compile(r"^(?P<type>.+?)\s+(?:util\.?|utilitaire|véhicule|veh\.?)\s+(?P<veh>.+)$", re.I)


# Natures connues, pour les comptes sans « Util. » : « Assurance Quad Kodiak », « Entr. et repar. Semi PAC »…
_NATURE_FIRST = re.compile(r"^(?P<type>carburants?|entr\.?\s+et\s+r[ée]p\w*\.?|entretiens?(?:\s+et\s+r[ée]parations?)?|r[ée]parations?|assurances?|taxes?|autres\s+frais|frais\s+divers|leasing|location|amortissements?|p[ée]ages?)\s+(?P<veh>.+)$", re.I)


def split_vehicle_account(name: str) -> tuple[str, str]:
    """Libellé de compte 615 « Carburant Util. CITAN » ou « Assurance Quad Kodiak » -> (véhicule, nature). Sans motif reconnu : véhicule « (non classé) »."""
    n = (name or "").strip()
    m = _VEHICLE_NAME.match(n) or _NATURE_FIRST.match(n)
    if not m:
        return "(non classé)", n
    return m["veh"].strip(), m["type"].strip().capitalize()


def vehicles_view(lines: list[dict], config: dict, year: int, scope: str = "config") -> dict:
    """Coût par véhicule et par nature (carburant, entretien, assurance…) d'après les comptes rangés en « véhicules de service ».
    scope = « all615 » : tous les comptes de la classe 615 (EXPENSES_VEHICLE_PREFIXES), quelle que soit leur rubrique (contrôle du carburant)."""
    cand = [a for a in lines if family(a["code"], a["name"]) == "candidate"]
    if scope == "all615":
        mine = [a for a in cand if any(a["code"].startswith(p) for p in settings.EXPENSES_VEHICLE_PREFIXES)]
    else:
        sel = effective(config, [a["code"] for a in cand])
        mine = [x for a in cand if (x := _for_kind(a, sel, config, "vehicle"))]
    veh: dict[str, dict] = {}
    types: dict[str, float] = {}
    for a in mine:
        v, t = split_vehicle_account(a["name"])
        d = veh.setdefault(v.casefold(), {"vehicle": v, "total": 0.0, "types": {}, "accounts": [], "by_month": {}})
        for m, amt in a["by_month"].items():
            bm = d["by_month"].setdefault(t, {})
            bm[m] = bm.get(m, 0.0) + amt
        d["total"] += a["total"]
        d["types"][t] = d["types"].get(t, 0.0) + a["total"]
        d["accounts"].append(a["code"])
        types[t] = types.get(t, 0.0) + a["total"]
    # Deux comptes pour un même véhicule (« Quad Kodiak » / « YAMAHA/KODIAK 700 ») : la correspondance « A -> B » où B est un autre véhicule des comptes les fusionne en B.
    for src, dst in (config.get("links") or {}).items():
        a, b = veh.get(src.casefold()), veh.get(dst.casefold())
        if a is None or b is None or a is b:
            continue
        for t, bm in a["by_month"].items():
            for m, amt in bm.items():
                b["by_month"].setdefault(t, {})[m] = b["by_month"].setdefault(t, {}).get(m, 0.0) + amt
        for t, amt in a["types"].items():
            b["types"][t] = b["types"].get(t, 0.0) + amt
        b["total"] += a["total"]
        b["accounts"] += a["accounts"]
        b.setdefault("merged", []).append(a["vehicle"])
        del veh[src.casefold()]
    total = sum(d["total"] for d in veh.values())
    order = [t for t, _ in sorted(types.items(), key=lambda kv: -kv[1])]
    return {"year": year, "total": round(total, 2), "types": order, "type_totals": {t: round(types[t], 2) for t in order},
            "vehicles": [{"vehicle": d["vehicle"], "total": round(d["total"], 2), "share": (d["total"] / total) if total else 0.0,
                          "types": {t: round(v, 2) for t, v in d["types"].items()}, "accounts": d["accounts"], "merged": d.get("merged", []), "identified": is_identified(d["vehicle"]) and d["vehicle"].casefold() not in {n.casefold() for n in config.get("general_vehicles") or []},
                          "forced_general": d["vehicle"].casefold() in {n.casefold() for n in config.get("general_vehicles") or []},
                          "by_month": {t: {m: round(x, 2) for m, x in bm.items()} for t, bm in d["by_month"].items()}} for d in sorted(veh.values(), key=lambda d: -d["total"])],
            "unclassified": [d["accounts"] for d in veh.values() if d["vehicle"] == "(non classé)"], "empty": not mine, "configured": bool(config.get("saved")),
            "reconciliation": vehicle_reconciliation(lines, config, total) if scope == "all615" else None}


def vehicle_reconciliation(lines: list[dict], config: dict, included_total: float) -> dict:
    """Contrôle comptable de la classe 615 : total des écritures, part ignorée (comptes « old »), part reprise dans l'imputation, écart,
    et comptes 615 qui seraient aussi comptés dans les frais généraux (double emploi)."""
    mine = [a for a in lines if any(a["code"].startswith(p) for p in settings.EXPENSES_VEHICLE_PREFIXES)]
    total = sum(a["total"] for a in mine)
    old = [a for a in mine if family(a["code"], a["name"]) == "old"]
    other = [a for a in mine if family(a["code"], a["name"]) not in ("old", "candidate")]
    sel = effective(config, [a["code"] for a in mine if family(a["code"], a["name"]) == "candidate"])
    both = [a for a in mine if family(a["code"], a["name"]) == "candidate" and sel.get(a["code"]) in ("general", "partners")]
    row = lambda a: {"code": a["code"], "name": a["name"], "total": round(a["total"], 2)}  # noqa: E731
    return {"total": round(total, 2), "old": round(sum(a["total"] for a in old), 2), "old_accounts": [row(a) for a in old],
            "other": round(sum(a["total"] for a in other), 2), "other_accounts": [row(a) for a in other], "included": round(included_total, 2),
            "gap": round(total - sum(a["total"] for a in old) - sum(a["total"] for a in other) - included_total, 2),
            "also_general": [row(a) for a in both]}


def excluded_view(lines: list[dict]) -> dict:
    """Écritures des comptes exclus des frais généraux (le loyer) : total et liste, à mentionner sous le graphique."""
    mv = sorted(lines, key=lambda o: (o["date"], o["move"]))
    return {"total": round(sum(o["amount"] for o in mv), 2), "moves": [{**o, "amount": round(o["amount"], 2)} for o in mv]}
