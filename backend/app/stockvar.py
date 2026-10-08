"""Variations de stock saisies par la direction (positives ou négatives), qui s'ajoutent à la marge brute de XC quand l'option est activée.

Même principe que les ajustements de marge brute : liste partagée enregistrée dans Firestore, rien n'est écrit dans Odoo.
`amount` = effet sur la marge brute de XC (positif = la marge augmente : le stock a augmenté ; négatif : le stock a diminué, dépréciation, casse…)."""
from __future__ import annotations

import threading
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field, field_validator

from . import settings


class Item(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[A-Za-z0-9_-]+$")
    label: str = Field(min_length=1, max_length=160)
    amount: float = Field(default=0.0, ge=-1e8, le=1e8)
    date: str | None = None
    enabled: bool = True
    note: str = Field(default="", max_length=300)

    @field_validator("date")
    @classmethod
    def _date(cls, v):
        if v in (None, ""):
            return None
        date.fromisoformat(v)
        return v


class Payload(BaseModel):
    items: list[Item] = Field(max_length=100)


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
        from google.cloud import firestore
        self._ref = firestore.Client().collection("dashboard").document("stockvar")

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
