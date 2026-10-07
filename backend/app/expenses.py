"""Frais généraux : choix des comptes comptables retenus (« Données source ») et calculs d'affichage.

La configuration est un petit document Firestore partagé (lecture pour tous, écriture pour les administrateurs). Rien n'est écrit dans Odoo.
Un compte de charges (classe 6) est : traité ailleurs (achats 60x par BU, personnel 62x et 618, marketing), ignoré (compte « old »),
ou candidat : à ranger en « frais généraux », en « véhicules de service » (menu dédié) ou à laisser de côté."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import settings
from .bu import is_old

KINDS = ("general", "vehicle")
CODE = re.compile(r"^\d{3,10}$")


class Config(BaseModel):
    selected: dict[str, Literal["general", "vehicle"]] = Field(default_factory=dict)       # code de compte -> rubrique ; absent = laissé de côté
    saved: bool = False

    @field_validator("selected")
    @classmethod
    def _codes(cls, v):
        for k in v:
            if not CODE.match(k):
                raise ValueError(f"code de compte invalide : {k}")
        return v


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
    if code in settings.MARKETING_ACCOUNTS:
        return "marketing"
    if code.startswith("62") or code in settings.STAFF_DIRECTOR_PAY or code in settings.STAFF_DIRECTOR_SOCIAL:
        return "staff"
    if code.startswith("60"):
        return "bu"
    return "candidate"


def suggestion(code: str) -> str | None:
    """Proposition de départ (avant tout enregistrement) : les comptes dont le code commence par EXPENSES_DEFAULT_PREFIXES."""
    return "general" if any(code.startswith(p) for p in settings.EXPENSES_DEFAULT_PREFIXES) else None


def effective(config: dict, codes) -> dict[str, str]:
    """Rubrique retenue par compte : la configuration enregistrée, ou, tant que rien n'est enregistré, la proposition de départ."""
    if config.get("saved"):
        return dict(config.get("selected") or {})
    return {c: s for c in codes if (s := suggestion(c))}


def _month_series(accounts: list[dict]) -> list[dict]:
    m: dict[str, float] = {}
    for a in accounts:
        for k, v in a["by_month"].items():
            m[k] = m.get(k, 0.0) + v
    return [{"month": k, "amount": round(v, 2)} for k, v in sorted(m.items())]


def accounts_view(lines: list[dict], config: dict, year: int) -> dict:
    """Page « Données source » : comptes candidats avec leur rubrique, et totaux des familles traitées ailleurs."""
    cand = [a for a in lines if family(a["code"], a["name"]) == "candidate"]
    sel = effective(config, [a["code"] for a in cand])
    elsewhere: dict[str, float] = {}
    for a in lines:
        f = family(a["code"], a["name"])
        if f in ("bu", "staff", "marketing"):
            elsewhere[f] = elsewhere.get(f, 0.0) + a["total"]
    return {"year": year, "saved": bool(config.get("saved")),
            "accounts": [{"code": a["code"], "name": a["name"], "total": round(a["total"], 2), "months": len(a["by_month"]),
                          "kind": sel.get(a["code"]), "suggested": suggestion(a["code"])} for a in sorted(cand, key=lambda a: a["code"])],
            "elsewhere": {k: round(v) for k, v in elsewhere.items()}, "marketing_accounts": settings.MARKETING_ACCOUNTS}


def kind_view(lines: list[dict], config: dict, year: int, kind: str) -> dict:
    """Résultat pour une rubrique (« general » ou « vehicle ») : total, évolution mensuelle, comptes, principaux fournisseurs."""
    cand = [a for a in lines if family(a["code"], a["name"]) == "candidate"]
    sel = effective(config, [a["code"] for a in cand])
    mine = [a for a in cand if sel.get(a["code"]) == kind]
    series = _month_series(mine)
    total = sum(a["total"] for a in mine)
    months = max(1, len([s for s in series if abs(s["amount"]) > 0.5])) if series else 1
    partners: dict[str, dict] = {}
    for a in mine:
        for pid, p in a["partners"].items():
            d = partners.setdefault(str(pid), {"name": p["name"], "amount": 0.0})
            d["amount"] += p["amount"]
    sup = sorted(partners.values(), key=lambda x: -x["amount"])[:15]
    return {"year": year, "kind": kind, "total": round(total, 2), "months": months, "monthly_avg": round(total / months, 2), "projected": round(total / months * 12, 2),
            "series": series,
            "accounts": [{"code": a["code"], "name": a["name"], "total": round(a["total"], 2), "share": (a["total"] / total) if total else 0.0}
                         for a in sorted(mine, key=lambda a: -a["total"])],
            "suppliers": [{"name": s["name"], "amount": round(s["amount"], 2), "share": (s["amount"] / total) if total else 0.0} for s in sup],
            "configured": bool(config.get("saved")), "empty": not mine}
