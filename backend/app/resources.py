"""Ressources mobilisables sur un événement : staff (compte Google), prestataires externes (contacts Odoo) et véhicules de service (ressources Google Agenda).

Page réservée au Super User. Rien n'est écrit dans Odoo ; les prestataires choisis et les comptes Google du staff sont gardés dans Logbook (Firestore)."""
from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator

from . import gauth, gcal, settings
from .staff import EMAIL

DIRECTORY_URL = "https://admin.googleapis.com/admin/directory/v1/customer/my_customer/resources/calendars"


class External(BaseModel):
    partner_id: int
    name: str = Field(min_length=1, max_length=160)
    email: str = Field(default="", max_length=120)                      # adresse utilisée pour l'invitation (reprise d'Odoo, modifiable)
    company: str = Field(default="", max_length=160)
    phone: str = Field(default="", max_length=60)
    role: str = Field(default="", max_length=120)                       # fonction ou spécialité (ex. mécanicien, chauffeur)

    @field_validator("email")
    @classmethod
    def _email(cls, v):
        v = (v or "").strip().lower()
        if v and not EMAIL.match(v):
            raise ValueError("adresse e-mail invalide")
        return v


class ResDoc(BaseModel):
    externals: list[External] = Field(default_factory=list, max_length=300)

    @field_validator("externals")
    @classmethod
    def _unique(cls, v):
        ids = [e.partner_id for e in v]
        if len(set(ids)) != len(ids):
            raise ValueError("prestataire en double")
        return v


class SaveBody(BaseModel):
    data: ResDoc
    base: str | None = None


class Store:
    """Document unique (Firestore en production, mémoire en démo / essais)."""
    def __init__(self):
        self._lock = threading.Lock()
        self._doc = {"data": ResDoc().model_dump(), "updated_at": None, "updated_by": None}
        self._ref = None
        if settings.ADJUSTMENTS_STORE == "firestore":
            from google.cloud import firestore
            self._ref = firestore.Client().collection("dashboard").document("resources")

    def get(self) -> dict:
        if self._ref is not None:
            snap = self._ref.get()
            d = snap.to_dict() if snap.exists else {}
            return {"data": d.get("data") or ResDoc().model_dump(), "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}
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


# ---- Véhicules : ressources du module « Ressources » de Google Agenda ----------------------------------------------------------------

_cache: tuple[float, dict] | None = None
_lock = threading.Lock()


def _filtered(rows: list[dict]) -> list[dict]:
    pat = re.compile(settings.CALENDAR_VEHICLE_REGEX, re.I) if settings.CALENDAR_VEHICLE_REGEX else None
    excl = re.compile(settings.CALENDAR_EXCLUDE_REGEX, re.I) if settings.CALENDAR_EXCLUDE_REGEX else None
    out = [r for r in rows if (not pat or pat.search(r["name"])) and (not excl or not excl.search(r["name"]))]
    return sorted(out, key=lambda r: r["name"].lower())


def _directory() -> list[dict]:
    rows, token = [], None
    sess = gauth.session((gauth.SCOPE_DIRECTORY,))
    while True:
        params = {"maxResults": 500}
        if token:
            params["pageToken"] = token
        r = sess.get(DIRECTORY_URL, params=params, timeout=30)
        if r.status_code != 200:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                msg = ""
            raise RuntimeError(f"Google Workspace HTTP {r.status_code} — {msg[:300]}".strip(" —"))
        j = r.json()
        for it in j.get("items", []):
            rows.append({"name": it.get("resourceName", ""), "email": it.get("resourceEmail", ""), "type": it.get("resourceType") or it.get("resourceCategory", ""),
                         "description": it.get("userVisibleDescription", ""), "capacity": it.get("capacity")})
        token = j.get("nextPageToken")
        if not token:
            return rows


def _from_events() -> list[dict]:
    """Repli sans délégation : noms des ressources vues dans les événements des agendas (l'adresse de la ressource n'est pas connue)."""
    today = date.today()
    names = sorted({r for e in gcal.events(today - timedelta(days=365), today + timedelta(days=365)) for r in e["resources"]}, key=str.lower)
    return [{"name": n, "email": "", "type": "", "description": "", "capacity": None} for n in names]


def vehicles() -> dict:
    """{configured, source: 'directory' | 'events' | 'demo', items, message?}"""
    global _cache
    if settings.PROVIDER == "demo":
        return {"configured": True, "source": "demo", "items": [
            {"name": "Sprinter", "email": "sprinter@resource.calendar.google.com", "type": "Véhicule", "description": "Utilitaire atelier", "capacity": 3},
            {"name": "Citan", "email": "citan@resource.calendar.google.com", "type": "Véhicule", "description": "", "capacity": 2},
            {"name": "Remorque 1", "email": "remorque1@resource.calendar.google.com", "type": "Remorque", "description": "Remorque plateau", "capacity": None}]}
    with _lock:
        if _cache and time.time() - _cache[0] < 600:
            return _cache[1]
    if gauth.configured():
        try:
            out = {"configured": True, "source": "directory", "items": _filtered(_directory())}
        except Exception as e:
            out = {"configured": True, "source": "directory", "items": [], "message": f"Liste des ressources indisponible : {e}"}
    elif gcal.configured():
        try:
            out = {"configured": False, "source": "events", "items": _filtered(_from_events()),
                   "message": "Délégation Google non activée : seules les ressources déjà réservées dans les agendas sont listées, sans leur adresse."}
        except Exception as e:
            out = {"configured": False, "source": "events", "items": [], "message": f"Agendas indisponibles : {e}"}
    else:
        out = {"configured": False, "source": "none", "items": [], "message": "Google Agenda n’est pas encore relié à Logbook."}
    if out["items"]:
        with _lock:
            _cache = (time.time(), out)
    return out
