"""Ajustements de marge brute saisis par la direction (reclassements, investissements long terme…).

Stockés dans Firestore (un seul document partagé par tous les utilisateurs). Rien n'est écrit dans Odoo.
Chaque ajustement a un EFFET sur la marge brute d'une BU (positif = la MB augmente) :
  - « manual »  : montant saisi à la main, daté ;
  - « meeting » / « car » : on retire la balance des événements (axe MEETING) / véhicules (axe CARS) sélectionnés ;
    le calcul se fait à l'affichage, d'après les chiffres de la période affichée."""
from __future__ import annotations

import re
import threading
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import settings

BU_KEYS = ("XC", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING", "CARS_OTHERS")


class Selected(BaseModel):
    id: int
    name: str = Field(max_length=160)


class Adjustment(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=120)
    bu: Literal["XC", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING", "CARS_OTHERS"]
    kind: Literal["manual", "meeting", "car"]
    enabled: bool = True
    amount: float = Field(default=0.0, ge=-1e8, le=1e8)                    # kind = manual : effet sur la MB (+ = MB plus haute)
    date: str | None = None                                                 # kind = manual : date d'effet (AAAA-MM-JJ)
    measure: Literal["result", "margin"] = "result"                       # selection : résultat après amortissement | CA − frais directs
    sel: list[Selected] = Field(default_factory=list, max_length=200)
    note: str = Field(default="", max_length=300)

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        if v in (None, ""):
            return None
        date.fromisoformat(v)
        return v


class Payload(BaseModel):
    items: list[Adjustment] = Field(max_length=60)


class MemoryStore:
    def __init__(self):
        self._doc = {"items": [], "updated_at": None, "updated_by": None}
        self._lock = threading.Lock()

    def get(self) -> dict:
        with self._lock:
            return dict(self._doc)

    def put(self, items: list[dict], user: str) -> dict:
        with self._lock:
            self._doc = {"items": items, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
            return dict(self._doc)


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore                        # import tardif : inutile en démo
        self._ref = firestore.Client().collection("dashboard").document("adjustments")

    def get(self) -> dict:
        snap = self._ref.get()
        d = snap.to_dict() if snap.exists else {}
        return {"items": d.get("items", []), "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}

    def put(self, items: list[dict], user: str) -> dict:
        doc = {"items": items, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
        self._ref.set(doc)
        return doc


_store = None


def store():
    global _store
    if _store is None:
        _store = FirestoreStore() if settings.ADJUSTMENTS_STORE == "firestore" else MemoryStore()
    return _store


def can_edit(user: str) -> bool:
    """Sans authentification (démo / essai local) tout le monde peut éditer ; sinon seules les adresses ADMIN_EMAILS."""
    from . import users
    return users.is_admin(user)


def can_reference(user: str) -> bool:
    """Peut enregistrer les hypothèses de référence (imputations du personnel, des véhicules, clé des frais généraux) : REFERENCE_EDITORS, ou tous les administrateurs s'il est vide.
    Les autres administrateurs peuvent simuler dans leur navigateur, sans rien enregistrer."""
    from . import users
    return can_edit(user) and (not settings.AUTH_ENABLED or not settings.REFERENCE_EDITORS or user in settings.REFERENCE_EDITORS or users.is_super(user))
