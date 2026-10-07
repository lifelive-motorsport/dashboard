"""Données source du personnel (salariés et indépendants) : fiches, coûts hors salaire, imputation sur les BU.

Données SENSIBLES (rémunérations) : lecture et écriture réservées aux administrateurs (ADMIN_EMAILS). Un seul document partagé,
stocké dans Firestore ; les fiches de paie (PDF) sont gardées dans un bucket Cloud Storage privé (STAFF_BUCKET). Rien n'est écrit dans Odoo."""
from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from . import settings

SHARES = ("XC", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING", "SHARED")     # les 4 BU + Shared Services (support, management)
MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
SAFE_ID = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


class Extra(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,40}$")
    label: str = Field(max_length=120)
    kind: Literal["vehicule", "carte_essence", "telephone", "autre"] = "autre"
    monthly: float = Field(default=0.0, ge=0, le=1e6)                  # coût mensuel pour la société (hors salaire / hors facture)
    note: str = Field(default="", max_length=300)


class FileMeta(BaseModel):
    name: str = Field(max_length=200)
    size: int = Field(ge=0)
    uploaded_at: str


class Payslip(BaseModel):
    month: str
    brut: float = Field(default=0.0, ge=0, le=1e7)
    patronal: float | None = Field(default=None, ge=0, le=1e7)          # cotisations patronales réelles du mois, si connues
    net: float | None = Field(default=None, ge=0, le=1e7)
    other: float = Field(default=0.0, ge=0, le=1e7)                     # autres coûts société du mois (chèques-repas, assurance groupe…)
    days: float | None = Field(default=None, ge=0, le=31)              # jours prestés dans le mois (fiche de paie) : utile pour le travail ponctuel
    note: str = Field(default="", max_length=300)
    file: FileMeta | None = None

    @field_validator("month")
    @classmethod
    def _month(cls, v):
        if not MONTH.match(v):
            raise ValueError("mois attendu : AAAA-MM")
        return v


class Partner(BaseModel):
    id: int
    name: str = Field(max_length=160)


class Person(BaseModel):
    id: str
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["salarie", "independant"]
    function: str = Field(default="", max_length=120)
    active: bool = True
    in_payroll: bool = True                                             # rémunération comptabilisée en 620/621 (faux pour un gérant payé via un autre compte)
    start: str | None = None
    end: str | None = None
    fte: float = Field(default=100.0, gt=0, le=100)                     # temps de travail en % (le brut des fiches en tient déjà compte)
    hours_week: float = Field(default=38.0, gt=0, le=80)
    billable_pct: float = Field(default=100.0, gt=0, le=100)            # part des heures facturables à des clients externes (coût ajusté = coût ÷ taux)
    hours_pct: float = Field(default=100.0, gt=0, le=300)               # temps réellement presté par rapport à l'horaire de base (120 = 20 % de dépassement)
    patronal_pct: float = Field(default=25.0, ge=0, le=100)             # cotisations patronales estimées quand elles ne sont pas sur la fiche
    factor: float | None = Field(default=None, gt=0, le=20)            # coefficient d'annualisation propre à la personne (sinon celui des paramètres) : 13,92 employé, 12 ouvrier / gérant
    active_months: float | None = Field(default=None, gt=0, le=12)       # indépendant : nombre de mois d'activité pris en compte pour la projection (sinon : mois ayant une facture d'honoraires)
    brut_override: float | None = Field(default=None, ge=0, le=1e7)    # brut mensuel de référence (sinon dernière fiche)
    monthly_other: float = Field(default=0.0, ge=0, le=1e6)             # autres coûts société mensuels récurrents (chèques-repas…)
    payslips: list[Payslip] = Field(default_factory=list, max_length=240)
    extras: list[Extra] = Field(default_factory=list, max_length=30)
    partners: list[Partner] = Field(default_factory=list, max_length=20)   # indépendants : sociétés Odoo dont on remonte les factures
    alloc: dict[str, float] = Field(default_factory=dict)               # % d'imputation : XC, MODERN_RALLY, HISTORIC_RALLY, HISTORIC_RACING, SHARED
    note: str = Field(default="", max_length=500)

    @field_validator("id")
    @classmethod
    def _id(cls, v):
        if not SAFE_ID.match(v):
            raise ValueError("identifiant invalide")
        return v

    @model_validator(mode="after")
    def _check(self):
        for k, v in self.alloc.items():
            if k not in SHARES or not (0 <= v <= 100):
                raise ValueError(f"imputation invalide : {k}")
        if sum(self.alloc.values()) > 100.0001:
            raise ValueError("l'imputation dépasse 100 %")
        months = [p.month for p in self.payslips]
        if len(set(months)) != len(months):
            raise ValueError("deux fiches pour le même mois")
        return self


class Params(BaseModel):
    annual_factor: float = Field(default=13.92, gt=0, le=20)            # 12 mois + 13e mois + double pécule : coût annualisé = mensuel × ce facteur
    days_per_year: float = Field(default=220.0, gt=0, le=366)           # jours prestés par an pour le coût journalier (temps plein)


class StaffDoc(BaseModel):
    params: Params = Field(default_factory=Params)
    people: list[Person] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def _unique(self):
        ids = [p.id for p in self.people]
        if len(set(ids)) != len(ids):
            raise ValueError("identifiants de personnes en double")
        return self


class SaveBody(BaseModel):
    data: StaffDoc
    base: str | None = None             # date de la version éditée : refusée si quelqu'un a enregistré entre-temps


class Store:
    """Document unique (Firestore en production, mémoire en démo / essais)."""
    def __init__(self):
        self._lock = threading.Lock()
        self._doc = {"data": StaffDoc().model_dump(), "updated_at": None, "updated_by": None}
        self._ref = None
        if settings.ADJUSTMENTS_STORE == "firestore":
            from google.cloud import firestore                       # import tardif : inutile en démo
            self._ref = firestore.Client().collection("dashboard").document("staff")

    def get(self) -> dict:
        if self._ref is not None:
            snap = self._ref.get()
            d = snap.to_dict() if snap.exists else {}
            return {"data": d.get("data") or StaffDoc().model_dump(), "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}
        with self._lock:
            return dict(self._doc)

    def put(self, data: dict, user: str, base: str | None) -> dict | None:
        """None si la version éditée n'est plus la dernière (conflit)."""
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


class Files:
    """Fiches de paie : Cloud Storage privé (STAFF_BUCKET) ; en démo / essais, mémoire."""
    def __init__(self):
        self._mem: dict[str, bytes] = {}
        self._bucket = None
        if settings.STAFF_BUCKET:
            from google.cloud import storage                         # import tardif
            self._bucket = storage.Client().bucket(settings.STAFF_BUCKET)

    @property
    def enabled(self) -> bool:
        return self._bucket is not None or settings.PROVIDER == "demo"

    @staticmethod
    def key(person: str, month: str) -> str:
        if not SAFE_ID.match(person) or not MONTH.match(month):
            raise ValueError("identifiant ou mois invalide")
        return f"payslips/{person}/{month}.pdf"

    def put(self, person: str, month: str, content: bytes) -> None:
        k = self.key(person, month)
        if self._bucket is not None:
            self._bucket.blob(k).upload_from_string(content, content_type="application/pdf")
        else:
            self._mem[k] = content

    def get(self, person: str, month: str) -> bytes | None:
        k = self.key(person, month)
        if self._bucket is not None:
            b = self._bucket.blob(k)
            return b.download_as_bytes() if b.exists() else None
        return self._mem.get(k)


_store = None
_files = None


def store() -> Store:
    global _store
    if _store is None:
        _store = Store()
    return _store


def files() -> Files:
    global _files
    if _files is None:
        _files = Files()
    return _files


class ImportError_(ValueError):
    pass


def merge_import(current: dict, imported: dict) -> tuple[dict, dict]:
    """Fusionne un import (staff.json) dans le document courant : nouvelles personnes ajoutées ; pour une personne existante
    (même id), seules les fiches sont fusionnées (l'import l'emporte pour un même mois), le reste n'est pas touché."""
    doc = StaffDoc.model_validate(imported).model_dump()
    cur = StaffDoc.model_validate(current).model_dump()
    by_id = {p["id"]: p for p in cur["people"]}
    added, merged = [], []
    for p in doc["people"]:
        if p["id"] not in by_id:
            cur["people"].append(p)
            added.append(p["id"])
            continue
        slips = {s["month"]: s for s in by_id[p["id"]]["payslips"]}
        slips.update({s["month"]: s for s in p["payslips"]})
        by_id[p["id"]]["payslips"] = [slips[m] for m in sorted(slips)]
        merged.append(p["id"])
    return StaffDoc.model_validate(cur).model_dump(), {"added": added, "merged": merged}
