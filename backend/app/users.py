"""Utilisateurs et rôles, gérés par le « Super User » dans Settings › Utilisateurs (document Firestore `dashboard/users`).

Rôles : « admin » (saisit les ajustements, voit les données du personnel), « standard » (lecture de tout le reste), « xc » (uniquement les pages XC listées dans auth.XC_PATHS).
Le Super User vient de SUPER_USERS (à défaut REFERENCE_EDITORS, puis ADMIN_EMAILS) : il ne peut pas être retiré depuis l'écran. Les variables ADMIN_EMAILS / XC_ONLY_EMAILS
restent valables ; une adresse enregistrée dans l'écran l'emporte sur elles. Une adresse enregistrée peut se connecter même hors du domaine Workspace."""
from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import settings

ROLES = ("admin", "standard", "xc")
TTL = 20.0
EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


class Entry(BaseModel):
    email: str = Field(max_length=120)
    role: Literal["admin", "standard", "xc"]
    note: str = Field(default="", max_length=120)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = v.strip().lower()
        if not EMAIL.match(v):
            raise ValueError("adresse e-mail invalide")
        return v


class Payload(BaseModel):
    users: list[Entry] = Field(max_length=200)


class MemoryStore:
    def __init__(self):
        self._doc = {"users": [], "updated_at": None, "updated_by": None}
        self._lock = threading.Lock()

    def get(self) -> dict:
        with self._lock:
            return dict(self._doc)

    def put(self, users: list[dict], user: str) -> dict:
        with self._lock:
            self._doc = {"users": users, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
            return dict(self._doc)


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore
        self._ref = firestore.Client().collection("dashboard").document("users")

    def get(self) -> dict:
        snap = self._ref.get()
        d = snap.to_dict() if snap.exists else {}
        return {"users": d.get("users", []), "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}

    def put(self, users: list[dict], user: str) -> dict:
        doc = {"users": users, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
        self._ref.set(doc)
        return doc


_store = None
_cache: dict = {"t": 0.0, "map": {}}


def store():
    global _store
    if _store is None:
        _store = FirestoreStore() if settings.ADJUSTMENTS_STORE == "firestore" else MemoryStore()
    return _store


def supers() -> list[str]:
    return list(settings.SUPER_USERS or settings.REFERENCE_EDITORS or settings.ADMIN_EMAILS)


def registry() -> dict[str, str]:
    """adresse -> rôle enregistré (mis en cache quelques secondes ; en cas d'indisponibilité du stockage, on garde le dernier état connu)."""
    if time.time() - _cache["t"] > TTL:
        try:
            _cache["map"] = {u["email"].lower(): u["role"] for u in store().get().get("users", []) if u.get("role") in ROLES}
        except Exception:
            pass
        _cache["t"] = time.time()
    return _cache["map"]


def invalidate() -> None:
    _cache["t"] = 0.0


def is_super(email: str) -> bool:
    return (not settings.AUTH_ENABLED) or (email or "").lower() in supers()


def role_of(email: str) -> str:
    """« super », « admin », « standard » ou « xc »."""
    email = (email or "").lower()
    if email in supers():
        return "super"
    if email in registry():
        return registry()[email]
    if email in settings.XC_ONLY_EMAILS:
        return "xc"
    return "admin" if email in settings.ADMIN_EMAILS else "standard"


def is_admin(email: str) -> bool:
    return (not settings.AUTH_ENABLED) or role_of(email) in ("super", "admin")


def is_registered(email: str) -> bool:
    return (email or "").lower() in registry()
