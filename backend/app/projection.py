"""Projection annualisée : CA espéré des mois à venir (montant encodé par mois), séparément pour XC et CARS.

Même principe que les autres hypothèses de référence : un document partagé (Firestore) que seuls les propriétaires enregistrent ; les autres simulent dans leur navigateur."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator

from . import settings

SCOPES = ("XC", "CARS")


class Payload(BaseModel):
    year: int = Field(ge=2000, le=2100)
    expected: dict[str, dict[str, float]]

    @field_validator("expected")
    @classmethod
    def _expected(cls, v):
        out = {}
        for sc in SCOPES:
            row = {}
            for m, amount in (v.get(sc) or {}).items():
                if not (m.isdigit() and 1 <= int(m) <= 12):
                    raise ValueError("mois invalide")
                if not 0 <= amount <= 1e9:
                    raise ValueError("montant hors limites")
                row[str(int(m))] = round(amount, 2)
            out[sc] = row
        return out


class MemoryStore:
    def __init__(self):
        self._doc: dict = {"years": {}, "updated_at": None, "updated_by": None}
        self._lock = threading.Lock()

    def get(self) -> dict:
        with self._lock:
            return dict(self._doc)

    def put(self, year: int, expected: dict, user: str) -> dict:
        with self._lock:
            self._doc = {"years": {**self._doc["years"], str(year): expected}, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
            return dict(self._doc)


class FirestoreStore:
    def __init__(self):
        from google.cloud import firestore
        self._ref = firestore.Client().collection("dashboard").document("projection")

    def get(self) -> dict:
        snap = self._ref.get()
        d = snap.to_dict() if snap.exists else {}
        return {"years": d.get("years", {}), "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}

    def put(self, year: int, expected: dict, user: str) -> dict:
        doc = self.get()
        doc = {"years": {**doc["years"], str(year): expected}, "updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": user}
        self._ref.set(doc)
        return doc


_store = None


def store():
    global _store
    if _store is None:
        _store = FirestoreStore() if settings.ADJUSTMENTS_STORE == "firestore" else MemoryStore()
    return _store


def monthly(provider, aggregate, year: int, today) -> list[dict]:
    """CA et marge brute par mois et par périmètre (XC, CARS, autres) du 1er janvier à aujourd'hui ; le mois en cours est partiel."""
    import calendar
    from datetime import date
    out = []
    last = today.month if today.year == year else 12 if today.year > year else 0
    for m in range(1, last + 1):
        first, end = date(year, m, 1), date(year, m, calendar.monthrange(year, m)[1])
        partial = today < end
        agg = aggregate(provider.pnl_balances(first, min(end, today)))
        g = {x["key"]: x for x in agg["groups"]}
        row = {"month": m, "partial": partial, "to": min(end, today).isoformat()}
        for key, label in (("XC", "XC"), ("CARS", "CARS")):
            row[label] = {"ca": round(g.get(key, {}).get("ca", 0.0), 2), "margin": round(g.get(key, {}).get("margin", 0.0), 2)}
        row["OTHER"] = {"ca": round(agg["total"]["ca"] - row["XC"]["ca"] - row["CARS"]["ca"], 2), "margin": round(agg["total"]["margin"] - row["XC"]["margin"] - row["CARS"]["margin"], 2)}
        out.append(row)
    return out


def previous_year(provider, aggregate, year: int) -> list[dict]:
    """CA total (sans distinction XC / CARS : le plan comptable de l'époque ne le permettait pas) de chaque mois de l'année précédente, ancien plan comptable compris."""
    import calendar
    from datetime import date
    out = []
    for m in range(1, 13):
        first, end = date(year, m, 1), date(year, m, calendar.monthrange(year, m)[1])
        ca = aggregate(provider.pnl_balances(first, end))["total"]["ca"] + float(provider.old_plan_revenue(first, end))
        out.append({"month": m, "ca": round(ca, 2)})
    return out
