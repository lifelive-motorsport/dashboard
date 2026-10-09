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

from . import access, settings

ROLES = ("admin", "standard", "xc")           # « xc » : ancien nom de la catégorie par défaut (équivaut à cat:xc)
TTL = 20.0
EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")


class Category(BaseModel):
    id: str = Field(pattern=r"^[a-z0-9_-]{1,30}$")
    name: str = Field(min_length=1, max_length=60)
    pages: list[str] = Field(max_length=80)

    @field_validator("pages")
    @classmethod
    def _pages(cls, v):
        bad = [p for p in v if p not in access.PAGES]
        if bad:
            raise ValueError("page inconnue : " + bad[0])
        return sorted(set(v))


class Entry(BaseModel):
    email: str = Field(max_length=120)
    role: str = Field(pattern=r"^(admin|standard|xc|cat:[a-z0-9_-]{1,30})$")
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
    categories: list[Category] = Field(default_factory=list, max_length=30)


class MemoryStore:
    def __init__(self):
        self._doc = {"users": [], "categories": [], "updated_at": None, "updated_by": None}
        self._lock = threading.Lock()

    def get(self) -> dict:
        with self._lock:
            return dict(self._doc)

    def put(self, users: list[dict], user: str, categories: list[dict] | None = None) -> dict:
        with self._lock:
            self._doc = {"users": users, "categories": categories or [], "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
            return dict(self._doc)


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore
        self._ref = firestore.Client().collection("dashboard").document("users")

    def get(self) -> dict:
        snap = self._ref.get()
        d = snap.to_dict() if snap.exists else {}
        return {"users": d.get("users", []), "categories": d.get("categories", []), "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}

    def put(self, users: list[dict], user: str, categories: list[dict] | None = None) -> dict:
        doc = {"users": users, "categories": categories or [], "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
        self._ref.set(doc)
        return doc


_store = None
_cache: dict = {"t": 0.0, "map": {}, "cats": {}, "notes": {}}


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
            doc = store().get()
            _cache["map"] = {u["email"].lower(): u["role"] for u in doc.get("users", []) if u.get("role")}
            _cache["cats"] = {c["id"]: c for c in doc.get("categories", [])}
            _cache["notes"] = {u["email"].lower(): (u.get("note") or "").strip() for u in doc.get("users", [])}
        except Exception:
            pass
        _cache["t"] = time.time()
    return _cache["map"]


def invalidate() -> None:
    _cache["t"] = 0.0


def is_super(email: str) -> bool:
    return (not settings.AUTH_ENABLED) or (email or "").lower() in supers()


def categories(cats: list[dict] | None = None) -> list[dict]:
    """Catégories enregistrées ; la catégorie « XC » par défaut existe toujours tant qu'elle n'a pas été enregistrée autrement."""
    cats = list(cats if cats is not None else _cache["cats"].values())
    if not any(c["id"] == "xc" for c in cats):
        cats.insert(0, {"id": "xc", "name": "XC", "pages": list(access.XC_PAGES)})
    return cats


def role_of(email: str) -> str:
    """« super », « admin », « standard » ou « cat:<id> »."""
    email = (email or "").lower()
    if email in supers():
        return "super"
    r = registry().get(email)
    if r:
        return "cat:xc" if r == "xc" else r
    if email in settings.XC_ONLY_EMAILS:
        return "cat:xc"
    return "admin" if email in settings.ADMIN_EMAILS else "standard"


def pages_of(email: str) -> set[str] | None:
    """Pages accessibles ; None = toutes (Standard, Administrateur, Super User). Une catégorie supprimée ou inconnue ne donne accès à rien."""
    r = role_of(email)
    if not r.startswith("cat:"):
        return None
    registry()
    c = next((c for c in categories() if c["id"] == r[4:]), None)
    return set(c["pages"]) if c else set()


def is_admin(email: str) -> bool:
    return (not settings.AUTH_ENABLED) or role_of(email) in ("super", "admin")


def restricted(email: str) -> bool:
    return pages_of(email) is not None


def is_registered(email: str) -> bool:
    return (email or "").lower() in registry()


def identity(email: str) -> dict:
    """Nom, prénom et type de profil affichés sur la page d'accueil. Le nom vient de la note saisie dans Settings › Utilisateurs, à défaut de l'adresse (prenom.nom@…)."""
    email = (email or "").lower()
    registry()
    note = _cache["notes"].get(email, "")
    local = email.split("@")[0]
    name = note or " ".join(w.capitalize() for w in re.split(r"[._-]+", local) if w) or email
    r = role_of(email)
    if r.startswith("cat:"):
        cat = next((c for c in categories() if c["id"] == r[4:]), None)
        profile = "Catégorie : " + (cat["name"] if cat else r[4:])
    else:
        profile = {"super": "Super User", "admin": "Administrateur", "standard": "Standard"}.get(r, r)
    return {"name": name, "first": name.split()[0] if name.split() else name, "profile": profile}
