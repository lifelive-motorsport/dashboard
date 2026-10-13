"""Roulages (Consigner › Roulages) : kilométrage et temps de roulage des voitures de course (circuit, rallye) et de leurs pièces, en remplacement de RPM.

- Voitures : les véhicules de course de Planifier › Ressources › Véhicules (catégories Rally et Circuit) ; une photo d'identification par voiture.
- Pièces : arborescence Voiture › Groupe (ex. Motorisation) › Pièce (ex. Moteur, Turbo) › sous-pièce ; une pièce suit des kilomètres et / ou des heures, avec une limite et un seuil d'alerte (75 % par défaut, réglable par pièce).
- Runs : une sortie d'une voiture ; circuit = tours × longueur du circuit, rallye = somme des spéciales × nombre de passages ; les kilomètres d'une pièce sont CALCULÉS (départ + runs de la voiture pendant son montage), jamais incrémentés : modifier ou supprimer un run corrige tout.
Données dans Firestore (ride_parts, ride_runs, ride_circuits, ride_cars, ride_catalog) ; photos dans le bucket des pointages (préfixe rides/)."""
from __future__ import annotations

import re
import uuid
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from . import resources, timesheets
from .timesheets import Coll

RACE = ("rally", "circuit")
MAX_DEPTH = 3                       # Voiture › Groupe › Pièce › Sous-pièce (la voiture n'est pas un nœud)
PHOTO_MAX = 4 * 1024 * 1024
PHOTO_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}


def now() -> datetime:
    return datetime.now(timezone.utc)


_cars = _parts = _runs = _circuits = _catalog = None


def cars_coll() -> Coll:
    global _cars
    _cars = _cars or Coll("ride_cars")
    return _cars


def parts_coll() -> Coll:
    global _parts
    _parts = _parts or Coll("ride_parts")
    return _parts


def runs_coll() -> Coll:
    global _runs
    _runs = _runs or Coll("ride_runs")
    return _runs


def circuits_coll() -> Coll:
    global _circuits
    _circuits = _circuits or Coll("ride_circuits")
    return _circuits


def catalog_coll() -> Coll:
    global _catalog
    _catalog = _catalog or Coll("ride_catalog")
    return _catalog


# ---- Modèles ----------------------------------------------------------------------------------------------------------------------------

class PartIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: str | None = None
    group: bool = False                                              # simple regroupement (ex. Motorisation) : pas de compteur propre, l'état est celui du pire de ses pièces
    limit_km: float | None = Field(default=None, gt=0, le=1e7)
    limit_hours: float | None = Field(default=None, gt=0, le=1e6)
    warn_pct: float = Field(default=75.0, gt=0, le=100)
    km_start: float = Field(default=0.0, ge=0, le=1e7)               # kilomètres déjà parcourus au montage (pièce d'occasion, reprise de RPM)
    hours_start: float = Field(default=0.0, ge=0, le=1e6)
    mounted_from: date | None = None                                 # vide = depuis toujours : tous les runs de la voiture comptent
    serial: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=500)

    @model_validator(mode="after")
    def _chk(self):
        if self.group:
            self.limit_km = self.limit_hours = None
            self.km_start = self.hours_start = 0.0
        return self


class ReplaceIn(BaseModel):
    on: date
    serial: str = Field(default="", max_length=60)
    km_start: float = Field(default=0.0, ge=0, le=1e7)
    hours_start: float = Field(default=0.0, ge=0, le=1e6)


class CatalogItem(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    group: str = Field(default="", max_length=80)                    # groupe habituel (ex. Motorisation)
    limit_km: float | None = Field(default=None, gt=0, le=1e7)
    limit_hours: float | None = Field(default=None, gt=0, le=1e6)
    warn_pct: float = Field(default=75.0, gt=0, le=100)


class CatalogIn(BaseModel):
    items: list[CatalogItem] = Field(max_length=300)


class CircuitIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    length_km: float = Field(gt=0, lt=100)


class Stage(BaseModel):
    name: str = Field(default="", max_length=80)
    length_km: float = Field(gt=0, lt=1000)
    passes: int = Field(default=1, ge=1, le=50)


class RunIn(BaseModel):
    date: date
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["circuit", "rally"] = "circuit"
    circuit: str = Field(default="", max_length=80)                  # nom d'un circuit enregistré
    laps: int = Field(default=0, ge=0, le=5000)
    stages: list[Stage] = Field(default_factory=list, max_length=80)
    km: float | None = Field(default=None, ge=0, le=100000)          # kilomètres saisis à la main : prioritaires sur le calcul
    hours: float | None = Field(default=None, ge=0, le=500)
    drivers: list[str] = Field(default_factory=list, max_length=6)
    event_id: str = Field(default="", max_length=40)
    notes: str = Field(default="", max_length=1000)


# ---- Voitures ---------------------------------------------------------------------------------------------------------------------------

def vkey(item: dict) -> str:
    return re.sub(r"[^a-z0-9]+", "-", (item.get("email") or item["name"]).lower()).strip("-")[:80]


def clean_name(name: str) -> str:
    return re.sub(r"^\s*[(\[][^)\]]*[)\]]\s*[-:]?\s*", "", name).strip() or name


def race_cars() -> list[dict]:
    items = resources.vehicles().get("items", [])
    return [{"key": vkey(v), "name": clean_name(v["name"]), "category": v.get("category", "")} for v in items if v.get("category") in RACE]


def car_of(key: str) -> dict | None:
    return next((c for c in race_cars() if c["key"] == key), None)


# ---- Calculs ----------------------------------------------------------------------------------------------------------------------------

def _runs_of(vehicle: str) -> list[dict]:
    return sorted([r for r in runs_coll().all() if r["vehicle"] == vehicle], key=lambda r: (r["date"], r["id"]))


def part_counters(p: dict, runs: list[dict]) -> dict:
    a, b = p.get("mounted_from") or "", p.get("removed_at") or "9999"
    mine = [r for r in runs if a <= r["date"] < b]
    km = p.get("km_start", 0.0) + sum(r.get("km") or 0.0 for r in mine)
    hours = p.get("hours_start", 0.0) + sum(r.get("hours") or 0.0 for r in mine)
    ratios = []
    if p.get("limit_km"):
        ratios.append(km / p["limit_km"])
    if p.get("limit_hours"):
        ratios.append(hours / p["limit_hours"])
    ratio = max(ratios) if ratios else None
    warn = (p.get("warn_pct") or 75.0) / 100
    state = "none" if ratio is None else "over" if ratio >= 1 else "warn" if ratio >= warn else "ok"
    return {"km": round(km, 1), "hours": round(hours, 2), "ratio": None if ratio is None else round(ratio, 4), "state": state, "runs": len(mine)}


RANK = {"none": 0, "ok": 1, "warn": 2, "over": 3}


def tree(vehicle: str, runs: list[dict]) -> list[dict]:
    parts = [p for p in parts_coll().all() if p["vehicle"] == vehicle]
    by_parent: dict[str | None, list[dict]] = {}
    for p in parts:
        by_parent.setdefault(p.get("parent_id"), []).append(p)

    def build(p: dict) -> dict:
        node = {k: v for k, v in p.items() if k not in ("created_by",)}
        kids = sorted(by_parent.get(p["id"], []), key=lambda x: (x.get("removed_at") is not None, x["name"].lower()))
        node["children"] = [build(k) for k in kids]
        if p.get("group"):
            live = [c for c in node["children"] if not c.get("removed_at")]
            worst = max((c["state"] for c in live), key=lambda s: RANK[s], default="none")
            node.update({"km": None, "hours": None, "ratio": None, "state": worst, "runs": 0})
        else:
            node.update(part_counters(p, runs))
            live = [c for c in node["children"] if not c.get("removed_at")]
            node["state"] = max([node["state"]] + [c["state"] for c in live], key=lambda s: RANK[s])
        return node

    return [build(p) for p in sorted(by_parent.get(None, []), key=lambda x: x["name"].lower())]


def alerts(nodes: list[dict], path: str = "") -> list[dict]:
    out = []
    for n in nodes:
        here = f"{path} › {n['name']}" if path else n["name"]
        if not n.get("removed_at") and not n.get("group") and n["state"] in ("warn", "over") and n.get("ratio") is not None:
            out.append({"id": n["id"], "path": here, "state": n["state"], "ratio": n["ratio"], "km": n["km"], "hours": n["hours"], "limit_km": n.get("limit_km"), "limit_hours": n.get("limit_hours")})
        out += alerts(n["children"], here)
    return out


class CarIn(BaseModel):
    bu: str | None = None                                            # BU de la voiture : XC, MODERN_RALLY, HISTORIC_RALLY ou HISTORIC_RACING (vide = pas encore définie) ; None = inchangée
    archived: bool | None = None                                     # archivée : cachée du Garage (données conservées) ; None = inchangé

    @field_validator("bu")
    @classmethod
    def _bu(cls, v):
        if v and v not in ("XC", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING"):
            raise ValueError("BU inconnue")
        return v


def set_car(key: str, data: CarIn) -> dict:
    if not car_of(key):
        raise LookupError("Voiture introuvable")
    meta = cars_coll().get(key) or {"id": key}
    if data.bu is not None:
        meta["bu"] = data.bu
    if data.archived is not None:
        meta["archived"] = data.archived
    cars_coll().put(key, meta)
    return {"bu": meta.get("bu", ""), "archived": bool(meta.get("archived"))}


def delete_car(key: str) -> dict:
    """Suppression définitive des données de roulage d'une voiture (pièces, runs, photo, BU) ; la voiture doit d'abord être archivée.
    Le véhicule lui-même reste une ressource de Planifier › Ressources : sans données, il réapparaîtrait vide tant qu'il y figure (le laisser archivé)."""
    meta = cars_coll().get(key) or {}
    if not meta.get("archived"):
        raise ValueError("Archivez d'abord la voiture avant de supprimer ses données")
    n = {"parts": 0, "runs": 0}
    for p in [p for p in parts_coll().all() if p["vehicle"] == key]:
        parts_coll().delete(p["id"]); n["parts"] += 1
    for r in [r for r in runs_coll().all() if r["vehicle"] == key]:
        runs_coll().delete(r["id"]); n["runs"] += 1
    if meta.get("photo"):
        timesheets.blobs().delete(meta["photo"]["key"])
    cars_coll().delete(key)
    return n


def car_overview(c: dict) -> dict:
    runs = _runs_of(c["key"])
    nodes = tree(c["key"], runs)
    al = alerts(nodes)
    meta = cars_coll().get(c["key"]) or {}
    state = max([a["state"] for a in al] + ["ok" if nodes else "none"], key=lambda s: RANK[s])
    return {**c, "bu": meta.get("bu", ""), "archived": bool(meta.get("archived")), "photo": bool(meta.get("photo")), "state": state, "alerts": len(al), "over": sum(1 for a in al if a["state"] == "over"),
            "km_total": round(sum(r.get("km") or 0 for r in runs), 1), "hours_total": round(sum(r.get("hours") or 0 for r in runs), 1),
            "runs": len(runs), "last_run": runs[-1]["date"] if runs else None, "parts": sum(1 for p in parts_coll().all() if p["vehicle"] == c["key"] and not p.get("removed_at") and not p.get("group"))}


def cars() -> list[dict]:
    return sorted((car_overview(c) for c in race_cars()), key=lambda c: c["name"].lower())


def car_detail(key: str) -> dict:
    c = car_of(key)
    if not c:
        raise LookupError("Voiture introuvable")
    runs = _runs_of(key)
    nodes = tree(key, runs)
    return {**car_overview(c), "tree": nodes, "alerts_list": alerts(nodes), "runs_list": sorted(runs, key=lambda r: (r["date"], r["id"]), reverse=True)[:200]}


# ---- Pièces -----------------------------------------------------------------------------------------------------------------------------

def _depth(parent_id: str | None) -> int:
    d = 1
    while parent_id:
        p = parts_coll().get(parent_id)
        if not p:
            raise LookupError("Élément parent introuvable")
        d += 1
        parent_id = p.get("parent_id")
    return d


def add_part(vehicle: str, data: PartIn, user: str) -> dict:
    if not car_of(vehicle):
        raise LookupError("Voiture introuvable")
    if data.parent_id:
        par = parts_coll().get(data.parent_id)
        if not par or par["vehicle"] != vehicle:
            raise LookupError("Élément parent introuvable")
    if _depth(data.parent_id) > MAX_DEPTH:
        raise ValueError("Trois niveaux au maximum sous la voiture (groupe, pièce, sous-pièce)")
    pid = "p-" + uuid.uuid4().hex[:10]
    doc = {"id": pid, "vehicle": vehicle, **data.model_dump(mode="json"), "removed_at": None, "created_by": user.lower(), "created_at": now().isoformat()}
    parts_coll().put(pid, doc)
    return doc


def update_part(pid: str, data: PartIn) -> dict:
    cur = parts_coll().get(pid)
    if not cur:
        raise LookupError("Élément introuvable")
    new = {**cur, **data.model_dump(mode="json"), "id": pid, "vehicle": cur["vehicle"], "parent_id": cur.get("parent_id"), "removed_at": cur.get("removed_at")}
    if cur.get("group") != new["group"]:
        raise ValueError("Un groupe ne devient pas une pièce (ni l'inverse) : créez-en un nouveau")
    parts_coll().put(pid, new)
    return new


def delete_part(pid: str) -> None:
    cur = parts_coll().get(pid)
    if not cur:
        raise LookupError("Élément introuvable")
    for p in parts_coll().all():
        if p.get("parent_id") == pid:
            delete_part(p["id"])
    parts_coll().delete(pid)


def replace_part(pid: str, data: ReplaceIn, user: str) -> dict:
    """Démonte la pièce (elle garde son historique) et en monte une neuve au même endroit, compteurs repartis de km_start / hours_start."""
    cur = parts_coll().get(pid)
    if not cur or cur.get("group") or cur.get("removed_at"):
        raise LookupError("Pièce introuvable ou déjà démontée")
    cur["removed_at"] = data.on.isoformat()
    parts_coll().put(pid, cur)
    nid = "p-" + uuid.uuid4().hex[:10]
    new = {**cur, "id": nid, "mounted_from": data.on.isoformat(), "removed_at": None, "serial": data.serial, "km_start": data.km_start, "hours_start": data.hours_start,
           "replaces": pid, "created_by": user.lower(), "created_at": now().isoformat()}
    parts_coll().put(nid, new)
    for ch in [p for p in parts_coll().all() if p.get("parent_id") == pid and not p.get("removed_at")]:
        parts_coll().put(ch["id"], {**ch, "parent_id": nid})                       # les sous-pièces suivent le nouvel emplacement
    return new


# ---- Circuits et runs -------------------------------------------------------------------------------------------------------------------

def circuit_id(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:60]


def list_circuits() -> list[dict]:
    return sorted(circuits_coll().all(), key=lambda c: c["name"].lower())


def save_circuit(data: CircuitIn) -> dict:
    doc = {"id": circuit_id(data.name), "name": data.name.strip(), "length_km": round(data.length_km, 3)}
    circuits_coll().put(doc["id"], doc)
    return doc


def compute_km(data: RunIn) -> float:
    if data.km is not None:
        return round(data.km, 2)
    if data.kind == "rally":
        return round(sum(s.length_km * s.passes for s in data.stages), 2)
    c = circuits_coll().get(circuit_id(data.circuit)) if data.circuit else None
    if data.laps and not c:
        raise ValueError("Longueur du circuit inconnue : enregistrez le circuit ou saisissez les kilomètres")
    return round(data.laps * c["length_km"], 2) if c else 0.0


def _run_doc(vehicle: str, data: RunIn, rid: str, user: str, created: str | None = None, source: str = "manual") -> dict:
    km = compute_km(data)
    if not km and data.hours is None:
        raise ValueError("Indiquez des tours, des spéciales, des kilomètres ou une durée")
    return {"id": rid, "vehicle": vehicle, **data.model_dump(mode="json"), "km": km, "created_by": user.lower(), "created_at": created or now().isoformat(), "source": source}


def add_run(vehicle: str, data: RunIn, user: str, source: str = "manual") -> dict:
    if not car_of(vehicle):
        raise LookupError("Voiture introuvable")
    doc = _run_doc(vehicle, data, "r-" + uuid.uuid4().hex[:10], user, source=source)
    runs_coll().put(doc["id"], doc)
    return doc


def update_run(rid: str, data: RunIn, user: str) -> dict:
    cur = runs_coll().get(rid)
    if not cur:
        raise LookupError("Run introuvable")
    doc = _run_doc(cur["vehicle"], data, rid, cur.get("created_by", user), cur.get("created_at"), cur.get("source", "manual"))
    runs_coll().put(rid, doc)
    return doc


def delete_run(rid: str) -> None:
    if not runs_coll().get(rid):
        raise LookupError("Run introuvable")
    runs_coll().delete(rid)


# ---- Catalogue de pièces (modèles à réutiliser) -------------------------------------------------------------------------------------------

def get_catalog() -> list[dict]:
    d = catalog_coll().get("catalog")
    return d["items"] if d else []


def put_catalog(data: CatalogIn) -> list[dict]:
    items = [i.model_dump(mode="json") for i in data.items]
    catalog_coll().put("catalog", {"id": "catalog", "items": items})
    return items


# ---- Photo ------------------------------------------------------------------------------------------------------------------------------

def set_photo(key: str, data: bytes, ctype: str) -> dict:
    ctype = ctype.split(";")[0].strip().lower()
    if ctype not in PHOTO_TYPES:
        raise ValueError("Photo : JPEG, PNG ou WebP seulement")
    if not data or len(data) > PHOTO_MAX:
        raise ValueError("Photo vide ou trop volumineuse (4 Mo maximum)")
    if not car_of(key):
        raise LookupError("Voiture introuvable")
    meta = cars_coll().get(key) or {"id": key}
    if meta.get("photo"):
        timesheets.blobs().delete(meta["photo"]["key"])
    k = f"rides/{key}-{uuid.uuid4().hex[:6]}.{PHOTO_TYPES[ctype]}"
    timesheets.blobs().put(k, data, ctype)
    meta["photo"] = {"key": k, "ctype": ctype}
    cars_coll().put(key, meta)
    return {"ok": True}


def get_photo(key: str) -> tuple[bytes, str] | None:
    meta = cars_coll().get(key)
    if not meta or not meta.get("photo"):
        return None
    got = timesheets.blobs().get(meta["photo"]["key"])
    return (got[0], meta["photo"]["ctype"]) if got else None
