"""Roulages (Consigner › Roulages) : kilométrage et temps de roulage des voitures de course (circuit, rallye) et de leurs pièces, en remplacement de RPM.

- Voitures : les véhicules de course de Planifier › Ressources › Véhicules (catégories Rally et Circuit) ; une photo d'identification par voiture.
- Pièces : arborescence Voiture › Groupe (ex. Motorisation) › Pièce (ex. Moteur, Turbo) › sous-pièce ; une pièce suit des kilomètres et / ou des heures, avec une limite et un seuil d'alerte (75 % par défaut, réglable par pièce).
- Runs : une sortie d'une voiture ; circuit = tours × longueur du circuit, rallye = somme des spéciales × nombre de passages ; les kilomètres d'une pièce sont CALCULÉS (départ + runs de la voiture pendant son montage), jamais incrémentés : modifier ou supprimer un run corrige tout.
Données dans Firestore (ride_parts, ride_runs, ride_circuits, ride_cars, ride_catalog) ; photos dans le bucket des pointages (préfixe rides/)."""
from __future__ import annotations

import difflib
import re
import time
import unicodedata
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


_cars = _parts = _runs = _circuits = _catalog = _maint = _templates = _sessions = None


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


def maint_coll() -> Coll:
    global _maint
    _maint = _maint or Coll("ride_maint")
    return _maint


def templates_coll() -> Coll:
    global _templates
    _templates = _templates or Coll("ride_templates")
    return _templates


def sessions_coll() -> Coll:
    global _sessions
    _sessions = _sessions or Coll("ride_sessions")
    return _sessions


def catalog_coll() -> Coll:
    global _catalog
    _catalog = _catalog or Coll("ride_catalog")
    return _catalog


# ---- Modèles ----------------------------------------------------------------------------------------------------------------------------

# Fonction normalisée d'une pièce : relie les jobs (lignes de liste de contrôle, formulaires) aux pièces du Garage sans dépendre de leur nom ; choisie dans la fiche de la pièce ou dans le modèle du Magasin.
FUNCTIONS = {"engine": "Moteur", "gearbox": "Boîte de vitesses", "rear_axle": "Pont arrière", "front_axle": "Pont avant", "clutch": "Embrayage", "brakes": "Freins (circuit hydraulique)", "steering": "Direction", "cooling": "Refroidissement"}
MAINT_TYPES = ("inspection", "fluids", "revision", "revision2", "replace")          # ordre chronologique logique : contrôle, vidange, révisions, remplacement
MAINT_LABEL = {"replace": "Remplacement", "revision": "Révision 1", "revision2": "Révision 2", "fluids": "Vidange et nouveaux fluides", "inspection": "Contrôle"}
LOGGED = ("revision", "revision2", "fluids", "inspection")          # maintenances qui s'enregistrent avec 🛠 (le remplacement se fait par « Remplacer »)

# Premier niveau de l'arborescence : liste verrouillée (Super User : à modifier dans ce fichier), pour que les états et coûts soient comparables d'une voiture à l'autre.
ENSEMBLES = ["Moteur", "Refroidissement", "Embrayage", "Transmission", "Freins", "Suspension et amortisseurs", "Direction", "Carburant", "Électrique et capteurs", "Châssis et carrosserie", "Sécurité"]


def _fold(s: str) -> str:
    import unicodedata
    return unicodedata.normalize("NFD", s or "").encode("ascii", "ignore").decode().lower().strip()


def canon_ensemble(name: str) -> str | None:
    return next((e for e in ENSEMBLES if _fold(e) == _fold(name)), None)


class MaintLimit(BaseModel):
    limit_km: float | None = Field(default=None, gt=0, le=1e7)
    limit_hours: float | None = Field(default=None, gt=0, le=1e6)
    limit_events: int | None = Field(default=None, gt=0, le=1000)     # tous les N roulages (ex. contrôle après chaque rallye : 1)
    warn_pct: float = Field(default=75.0, gt=0, le=100)
    note: str = Field(default="", max_length=160)                     # critère « sur condition » (ex. « quand abîmé ») ou précision


def _clean_types(v):
    return [t for t in MAINT_TYPES if t in (v or [])]


class PartIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    parent_id: str | None = None
    group: bool = False                                              # simple regroupement (ex. Motorisation) : pas de compteur propre, l'état est celui du pire de ses pièces
    limit_km: float | None = Field(default=None, gt=0, le=1e7)
    limit_hours: float | None = Field(default=None, gt=0, le=1e6)
    limit_note: str = Field(default="", max_length=160)
    reference: str = Field(default="", max_length=60)                # référence constructeur
    fn: str = Field(default="", max_length=20)                       # fonction normalisée (FUNCTIONS) : vide = non reliée aux jobs
    warn_pct: float = Field(default=75.0, gt=0, le=100)
    km_start: float = Field(default=0.0, ge=0, le=1e7)               # kilomètres déjà parcourus au montage (pièce d'occasion, reprise de RPM)
    hours_start: float = Field(default=0.0, ge=0, le=1e6)
    mounted_from: date | None = None                                 # vide = depuis toujours : tous les runs de la voiture comptent
    serial: str = Field(default="", max_length=60)
    notes: str = Field(default="", max_length=500)
    types: list[str] = Field(default_factory=list, max_length=5)      # maintenances suivies : replace (limites ci-dessus), revision, fluids (limites dans `maint`)
    maint: dict[str, MaintLimit] = Field(default_factory=dict)        # intervalles de la révision et de la vidange : {"revision": {...}, "fluids": {...}}

    @field_validator("fn")
    @classmethod
    def _fn(cls, v):
        if v and v not in FUNCTIONS:
            raise ValueError("fonction inconnue")
        return v

    @field_validator("types")
    @classmethod
    def _types(cls, v):
        return _clean_types(v)

    @field_validator("maint")
    @classmethod
    def _maint(cls, v):
        return {k: m for k, m in v.items() if k in LOGGED}

    @model_validator(mode="after")
    def _chk(self):
        if self.group:
            self.limit_km = self.limit_hours = None
            self.km_start = self.hours_start = 0.0
            self.types, self.maint = [], {}
        return self


class MaintIn(BaseModel):
    type: Literal["replace", "revision", "revision2", "fluids", "inspection"]
    date: date
    notes: str = Field(default="", max_length=300)


class TNode(BaseModel):
    id: str = Field(min_length=1, max_length=24)
    parent_id: str | None = None
    name: str = Field(min_length=1, max_length=80)
    group: bool = False                                              # Ensemble (ex. Motorisation) ; sinon sous-ensemble (Moteur, Turbo…)
    types: list[str] = Field(default_factory=list, max_length=5)
    reference: str = Field(default="", max_length=60)                # référence constructeur
    fn: str = Field(default="", max_length=20)                       # fonction normalisée (FUNCTIONS)
    replace: MaintLimit = Field(default_factory=MaintLimit)
    revision: MaintLimit = Field(default_factory=MaintLimit)
    revision2: MaintLimit = Field(default_factory=MaintLimit)
    fluids: MaintLimit = Field(default_factory=MaintLimit)
    inspection: MaintLimit = Field(default_factory=MaintLimit)

    @field_validator("types")
    @classmethod
    def _types(cls, v):
        return _clean_types(v)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(default="", max_length=300)
    nodes: list[TNode] = Field(default_factory=list, max_length=200)

    @model_validator(mode="after")
    def _tree(self):
        ids = [n.id for n in self.nodes]
        if len(set(ids)) != len(ids):
            raise ValueError("identifiants en double")
        by = {n.id: n for n in self.nodes}
        for n in self.nodes:
            if not n.parent_id:                                       # premier niveau : un ensemble de la liste verrouillée
                e = canon_ensemble(n.name)
                if not n.group or not e:
                    raise ValueError("Le premier niveau est un ensemble de la liste : " + ", ".join(ENSEMBLES))
                n.name = e
            depth, p = 1, n.parent_id
            while p:
                if p not in by:
                    raise ValueError("ensemble parent introuvable")
                depth += 1
                p = by[p].parent_id
                if depth > MAX_DEPTH + 1:
                    raise ValueError("arborescence trop profonde ou circulaire")
            if depth > MAX_DEPTH:
                raise ValueError("Trois niveaux au maximum (ensemble, sous-ensemble, composant)")
            if n.group:
                n.types = []
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


class SessionIn(BaseModel):
    """Un roulage : une sortie commune à une ou plusieurs voitures (essais, meeting, rallye). Chaque voiture y est ensuite associée avec ses propres tours / kilomètres."""
    date: date
    name: str = Field(min_length=1, max_length=120)
    kind: Literal["circuit", "rally"] = "circuit"
    circuit: str = Field(default="", max_length=80)                  # circuit enregistré (kind = circuit)
    stages: list[Stage] = Field(default_factory=list, max_length=80)  # spéciales (kind = rally), recopiées dans l'association de chaque voiture
    event_id: str = Field(default="", max_length=40)                 # événement du Planning, s'il y en a un
    notes: str = Field(default="", max_length=1000)


class AssocIn(BaseModel):
    """Participation d'une voiture à un roulage."""
    laps: int = Field(default=0, ge=0, le=5000)
    stages: list[Stage] | None = None                                # rallye : par défaut les spéciales du roulage
    km: float | None = Field(default=None, ge=0, le=100000)
    hours: float | None = Field(default=None, ge=0, le=500)
    drivers: list[str] = Field(default_factory=list, max_length=6)
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


def types_of(p: dict) -> list[str]:
    """Maintenances suivies d'une pièce : le choix explicite ; à défaut (anciennes fiches) le remplacement si une limite est définie."""
    return list(p.get("types") or (["replace"] if p.get("limit_km") or p.get("limit_hours") else []))


def _meter(km: float, hours: float, events: int, lim: dict) -> tuple[float | None, str]:
    ratios = []
    if lim.get("limit_km"):
        ratios.append(km / lim["limit_km"])
    if lim.get("limit_hours"):
        ratios.append(hours / lim["limit_hours"])
    if lim.get("limit_events"):
        ratios.append(events / lim["limit_events"])
    ratio = max(ratios) if ratios else None
    warn = (lim.get("warn_pct") or 75.0) / 100
    return ratio, ("none" if ratio is None else "over" if ratio >= 1 else "warn" if ratio >= warn else "ok")


def part_counters(p: dict, runs: list[dict], logs: list[dict] | None = None) -> dict:
    """Compteurs d'une pièce : total depuis le montage + un compteur par maintenance suivie (remplacement : depuis le montage ; révisions, vidange, contrôle : depuis la dernière
    maintenance enregistrée, à défaut depuis le montage). Chaque compteur suit les km, les heures et / ou le nombre de roulages selon les limites définies.
    Les runs du jour d'une maintenance comptent après elle. Un contrôle en retard reste un avertissement (jamais « dépassé »)."""
    a, b = p.get("mounted_from") or "", p.get("removed_at") or "9999"
    mine = [r for r in runs if a <= r["date"] < b]
    km = p.get("km_start", 0.0) + sum(r.get("km") or 0.0 for r in mine)
    hours = p.get("hours_start", 0.0) + sum(r.get("hours") or 0.0 for r in mine)
    meters = []
    for t in [x for x in MAINT_TYPES if x in types_of(p)]:
        if t == "replace":
            lim = {"limit_km": p.get("limit_km"), "limit_hours": p.get("limit_hours"), "warn_pct": p.get("warn_pct"), "note": p.get("limit_note", "")}
            mk, mh, ev, last = km, hours, len(mine), None
        else:
            lim = (p.get("maint") or {}).get(t) or {}
            done = sorted(l["date"] for l in (logs or []) if l["part_id"] == p["id"] and l["type"] == t)
            last = done[-1] if done else None
            since = max(last or "", a)
            seg = [r for r in runs if since <= r["date"] < b]
            mk, mh, ev = sum(r.get("km") or 0.0 for r in seg), sum(r.get("hours") or 0.0 for r in seg), len(seg)
        ratio, state = _meter(mk, mh, ev, lim)
        if t == "inspection" and state == "over":
            state = "warn"
        if ratio is not None or t != "replace" or lim.get("note"):
            meters.append({"type": t, "label": MAINT_LABEL[t], "km": round(mk, 1), "hours": round(mh, 2), "events": ev,
                           "limit_km": lim.get("limit_km"), "limit_hours": lim.get("limit_hours"), "limit_events": lim.get("limit_events"),
                           "note": lim.get("note") or "", "warn_pct": lim.get("warn_pct") or 75.0, "ratio": None if ratio is None else round(ratio, 4), "state": state, "last": last})
    ratios = [m["ratio"] for m in meters if m["ratio"] is not None]
    state = max((m["state"] for m in meters), key=lambda s: RANK[s], default="none")
    return {"km": round(km, 1), "hours": round(hours, 2), "ratio": max(ratios) if ratios else None, "state": state, "runs": len(mine), "meters": meters}


RANK = {"none": 0, "ok": 1, "warn": 2, "over": 3}


def tree(vehicle: str, runs: list[dict], parts: list[dict] | None = None, logs: list[dict] | None = None) -> list[dict]:
    if parts is None:
        parts = [p for p in parts_coll().all() if p["vehicle"] == vehicle]
    if logs is None:
        logs = [l for l in maint_coll().all() if l["vehicle"] == vehicle]
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
            node.update(part_counters(p, runs, logs))
            node["history"] = sorted((l for l in logs if l["part_id"] == p["id"]), key=lambda l: (l["date"], l["id"]), reverse=True)[:12]
            live = [c for c in node["children"] if not c.get("removed_at")]
            node["state"] = max([node["state"]] + [c["state"] for c in live], key=lambda s: RANK[s])
        return node

    order = {_fold(e): i for i, e in enumerate(ENSEMBLES)}
    return [build(p) for p in sorted(by_parent.get(None, []), key=lambda x: (order.get(_fold(x["name"]), 99), x["name"].lower()))]       # ensembles dans l'ordre de la liste


def _alerts_rec(nodes: list[dict], path: str, out: list[dict], checks: list[str]) -> None:
    for n in nodes:
        here = f"{path} › {n['name']}" if path else n["name"]
        if not n.get("removed_at") and not n.get("group"):
            for m in n.get("meters", []):
                if m["state"] in ("warn", "over") and m["ratio"] is not None:
                    if m["type"] == "inspection":
                        checks.append(here)                                # les contrôles se regroupent : une seule alerte par voiture
                        continue
                    out.append({"id": n["id"], "path": here, "type": m["type"], "label": m["label"], "state": m["state"], "ratio": m["ratio"], "km": m["km"], "hours": m["hours"], "limit_km": m["limit_km"], "limit_hours": m["limit_hours"]})
        _alerts_rec(n["children"], here, out, checks)


def alerts(nodes: list[dict], path: str = "") -> list[dict]:
    out: list[dict] = []
    checks: list[str] = []
    _alerts_rec(nodes, path, out, checks)
    if checks:
        out.append({"id": None, "path": "Contrôles", "type": "inspection", "label": f"{len(checks)} élément{'s' if len(checks) > 1 else ''} à contrôler", "state": "warn", "ratio": 1.0, "km": 0, "hours": 0,
                    "limit_km": None, "limit_hours": None, "count": len(checks), "items": checks[:40]})
    return out


# ---- Lien avec les comptes analytiques Odoo (axe CARS) -------------------------------------------------------------------------------------

NOISE = {"gdm", "hrs", "cd", "tn", "jlb", "demo", "rented", "from", "mats", "original", "teile", "the", "de", "le", "la"}
_acc_cache: tuple[float, list[dict]] | None = None


def odoo_accounts(force: bool = False) -> list[dict]:
    """Comptes analytiques de l'axe véhicules d'Odoo (mis en cache 10 minutes)."""
    global _acc_cache
    if not force and _acc_cache and time.time() - _acc_cache[0] < 600:
        return _acc_cache[1]
    from .main import provider
    accts = provider().vehicle_accounts()
    _acc_cache = (time.time(), accts)
    return accts


def _tokens(name: str) -> set[str]:
    s = unicodedata.normalize("NFKD", name.lower())
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"#\s*\d+|\([^)]*\)", " ", s)
    return {t for t in re.split(r"[^a-z0-9]+", s) if t and t not in NOISE}


def name_score(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    ratio = difflib.SequenceMatcher(None, " ".join(sorted(ta)), " ".join(sorted(tb))).ratio()
    return round(max(ratio, (inter / min(len(ta), len(tb)) + inter / len(ta | tb)) / 2), 3)


def suggestions(accts: list[dict] | None = None) -> dict[str, dict]:
    """Pour chaque voiture non reliée : le compte Odoo le plus proche (>= 0,6) non encore pris par une autre voiture ; {clé: {id, name, score, sure}}."""
    accts = odoo_accounts() if accts is None else accts
    metas = {c["key"]: cars_coll().get(c["key"]) or {} for c in race_cars()}
    taken = {m.get("odoo_id") for m in metas.values() if m.get("odoo_id")}
    free = [a for a in accts if a["id"] not in taken]
    out = {}
    for c in race_cars():
        if metas[c["key"]].get("odoo_id") or metas[c["key"]].get("archived"):
            continue
        scored = sorted(((name_score(c["name"], a["name"]) + (0.0 if a["active"] else -0.05), a) for a in free), key=lambda x: -x[0])
        if scored and scored[0][0] >= 0.6:
            best = scored[0]
            sure = best[0] >= 0.85 and (len(scored) == 1 or scored[1][0] <= best[0] - 0.1)
            out[c["key"]] = {"id": best[1]["id"], "name": best[1]["name"], "score": round(best[0], 3), "sure": sure}
    return out


def link_odoo(key: str, odoo_id: int) -> dict:
    """Relie la voiture à un compte analytique Odoo (0 = délier) ; un compte ne sert qu'à une voiture."""
    if not car_of(key):
        raise LookupError("Voiture introuvable")
    meta = cars_coll().get(key) or {"id": key}
    if odoo_id == 0:
        meta.pop("odoo_id", None); meta.pop("odoo_name", None)
        cars_coll().put(key, meta)
        return {"odoo": None}
    acc = next((a for a in odoo_accounts() if a["id"] == odoo_id), None)
    if not acc:
        raise LookupError("Compte analytique Odoo introuvable")
    for c in race_cars():
        if c["key"] != key and (cars_coll().get(c["key"]) or {}).get("odoo_id") == odoo_id:
            raise ValueError(f"Ce compte Odoo est déjà relié à « {c['name']} »")
    meta["odoo_id"], meta["odoo_name"] = odoo_id, acc["name"]
    cars_coll().put(key, meta)
    return {"odoo": {"id": odoo_id, "name": acc["name"]}}


def auto_link() -> list[dict]:
    """Relie d'un coup les voitures dont la correspondance est sûre (score >= 0,85 et sans concurrent proche) ; renvoie ce qui a été fait."""
    done = []
    for key, s in suggestions().items():
        if s["sure"]:
            try:
                link_odoo(key, s["id"])
                done.append({"key": key, "name": (car_of(key) or {}).get("name", key), "odoo": s["name"], "score": s["score"]})
            except (ValueError, LookupError):
                continue
    return done


IDENTITY = ("chassis", "engine_no", "gearbox_no", "livery", "race_number")


class CarIn(BaseModel):
    bu: str | None = None                                            # BU de la voiture : XC, MODERN_RALLY, HISTORIC_RALLY ou HISTORIC_RACING (vide = pas encore définie) ; None = inchangée
    archived: bool | None = None                                     # archivée : cachée du Garage (données conservées) ; None = inchangé
    odoo_id: int | None = None                                       # compte analytique Odoo (axe CARS) ; 0 = délier ; None = inchangé
    chassis: str | None = None                                       # identité permanente : n° de châssis, de moteur, de boîte, livrée, n° de course habituel ; None = inchangé, vide = effacé
    engine_no: str | None = None
    gearbox_no: str | None = None
    livery: str | None = None
    race_number: str | None = None

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
    for f in IDENTITY:
        v = getattr(data, f)
        if v is not None:
            meta[f] = v.strip()[:80]
    cars_coll().put(key, meta)
    if data.odoo_id is not None:
        link_odoo(key, data.odoo_id)
        meta = cars_coll().get(key) or meta
    return {"bu": meta.get("bu", ""), "archived": bool(meta.get("archived")), "odoo": ({"id": meta["odoo_id"], "name": meta.get("odoo_name", "")} if meta.get("odoo_id") else None)}


MODERN_RALLY_RE = re.compile(r"\b(wrc|rally[ -]?[1-5]|r5|fabia|yaris|i20|puma|ds ?3|c3 rally|focus rs|evo ?x|impreza|992|gr ?yaris)\b", re.I)


def guess_bu(c: dict) -> str:
    """BU probable d'après la catégorie de la ressource (Rally / Circuit) et le nom : rallye moderne (WRC, Rally1…) sinon rallye historique ; circuit = Historic Racing.
    Une proposition à vérifier, pas une certitude."""
    if c.get("category") == "rally":
        return "MODERN_RALLY" if MODERN_RALLY_RE.search(c["name"]) else "HISTORIC_RALLY"
    return "HISTORIC_RACING"


def guess_missing_bus() -> list[dict]:
    """Range les voitures sans BU (non archivées) selon guess_bu ; renvoie [{key, name, bu}] pour que l'écran montre ce qui a été fait."""
    out = []
    for c in race_cars():
        meta = cars_coll().get(c["key"]) or {"id": c["key"]}
        if meta.get("bu") or meta.get("archived"):
            continue
        meta["bu"] = guess_bu(c)
        cars_coll().put(c["key"], meta)
        out.append({"key": c["key"], "name": c["name"], "bu": meta["bu"]})
    return out


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
    from . import vdocs
    vdocs.purge(key)
    cars_coll().delete(key)
    return n


def _snapshot() -> dict:
    """Une seule lecture de chaque collection pour toutes les voitures (la liste du Garage relisait toute la base une fois par voiture)."""
    parts: dict[str, list] = {}
    runs: dict[str, list] = {}
    logs: dict[str, list] = {}
    for p in parts_coll().all():
        parts.setdefault(p["vehicle"], []).append(p)
    for r in runs_coll().all():
        runs.setdefault(r["vehicle"], []).append(r)
    for l in maint_coll().all():
        logs.setdefault(l["vehicle"], []).append(l)
    return {"parts": parts, "runs": {k: sorted(v, key=lambda r: (r["date"], r["id"])) for k, v in runs.items()}, "logs": logs, "meta": {m.get("id"): m for m in cars_coll().all()}}


def car_overview(c: dict, snap: dict | None = None, keep: dict | None = None) -> dict:
    """Résumé d'une voiture. `snap` : lecture groupée de la base (liste) ; `keep` : reçoit l'arbre, les alertes et les runs déjà calculés (fiche détaillée)."""
    from . import vdocs
    key = c["key"]
    if snap is None:
        runs = _runs_of(key)
        parts = [p for p in parts_coll().all() if p["vehicle"] == key]
        logs = [l for l in maint_coll().all() if l["vehicle"] == key]
        meta = cars_coll().get(key) or {}
    else:
        runs, parts, logs, meta = snap["runs"].get(key, []), snap["parts"].get(key, []), snap["logs"].get(key, []), snap["meta"].get(key, {})
    nodes = tree(key, runs, parts, logs)
    al = alerts(nodes)
    dal = vdocs.alerts_of(key, meta=meta, car=c)
    if keep is not None:
        keep.update(nodes=nodes, alerts=al, runs=runs, meta=meta)
    state = max([a["state"] for a in al] + ["ok" if nodes else "none"], key=lambda s: RANK[s])
    return {**c, **{f: meta.get(f, "") for f in IDENTITY}, "bu": meta.get("bu", ""), "archived": bool(meta.get("archived")), "template": ({"id": meta["template_id"], "name": meta.get("template_name", "")} if meta.get("template_id") else None), "odoo": ({"id": meta["odoo_id"], "name": meta.get("odoo_name", "")} if meta.get("odoo_id") else None), "photo": bool(meta.get("photo")), "state": state, "alerts": len(al), "over": sum(1 for a in al if a["state"] == "over"),
            "doc_alerts": len(dal), "doc_over": sum(1 for a in dal if a["state"] == "over"),
            "km_total": round(sum(r.get("km") or 0 for r in runs), 1), "hours_total": round(sum(r.get("hours") or 0 for r in runs), 1),
            "runs": len(runs), "last_run": runs[-1]["date"] if runs else None, "parts": sum(1 for p in parts if not p.get("removed_at") and not p.get("group"))}


def cars() -> list[dict]:
    snap = _snapshot()
    return sorted((car_overview(c, snap) for c in race_cars()), key=lambda c: c["name"].lower())


def car_detail(key: str) -> dict:
    c = car_of(key)
    if not c:
        raise LookupError("Voiture introuvable")
    from . import vdocs
    keep: dict = {}
    ov = car_overview(c, keep=keep)
    from . import tforms
    ids = {p["id"] for p in parts_coll().all() if p["vehicle"] == key}
    return {**ov, "clutch_measures": tforms.measures_by_part(ids), "ep0": tforms.EP0, "mini": tforms.MINI, "docs": vdocs.view(key, meta=keep["meta"], car=c), "tree": keep["nodes"], "alerts_list": keep["alerts"], "runs_list": sorted(keep["runs"], key=lambda r: (r["date"], r["id"]), reverse=True)[:200]}


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
        raise ValueError("Trois niveaux au maximum sous la voiture (ensemble, sous-ensemble, composant)")
    dump = data.model_dump(mode="json")
    if not data.parent_id:                                           # premier niveau : un ensemble de la liste verrouillée, une seule fois par voiture
        e = canon_ensemble(data.name)
        if not data.group or not e:
            raise ValueError("Le premier niveau est un ensemble de la liste : " + ", ".join(ENSEMBLES))
        if any(p["vehicle"] == vehicle and not p.get("parent_id") and not p.get("removed_at") and p["name"] == e for p in parts_coll().all()):
            raise ValueError(f"L'ensemble « {e} » existe déjà sur cette voiture")
        dump["name"] = e
    pid = "p-" + uuid.uuid4().hex[:10]
    doc = {"id": pid, "vehicle": vehicle, **dump, "removed_at": None, "created_by": user.lower(), "created_at": now().isoformat()}
    parts_coll().put(pid, doc)
    return doc


def update_part(pid: str, data: PartIn) -> dict:
    cur = parts_coll().get(pid)
    if not cur:
        raise LookupError("Élément introuvable")
    new = {**cur, **data.model_dump(mode="json"), "id": pid, "vehicle": cur["vehicle"], "parent_id": cur.get("parent_id"), "removed_at": cur.get("removed_at")}
    if cur.get("group") != new["group"]:
        raise ValueError("Un groupe ne devient pas une pièce (ni l'inverse) : créez-en un nouveau")
    if not cur.get("parent_id") and new["name"] != cur["name"]:
        e = canon_ensemble(new["name"])
        if not e:
            raise ValueError("Le premier niveau est un ensemble de la liste : " + ", ".join(ENSEMBLES))
        new["name"] = e
    parts_coll().put(pid, new)
    return new


def delete_part(pid: str) -> None:
    cur = parts_coll().get(pid)
    if not cur:
        raise LookupError("Élément introuvable")
    for p in parts_coll().all():
        if p.get("parent_id") == pid:
            delete_part(p["id"])
    for l in [l for l in maint_coll().all() if l["part_id"] == pid]:
        maint_coll().delete(l["id"])
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


def log_maint(pid: str, data: MaintIn, user: str) -> dict:
    """Enregistre une maintenance (révision, vidange…) : le compteur de ce type repart de cette date. Un remplacement se fait par « Remplacer »."""
    p = parts_coll().get(pid)
    if not p or p.get("group") or p.get("removed_at"):
        raise LookupError("Pièce introuvable ou démontée")
    if data.type == "replace":
        raise ValueError("Un remplacement s'enregistre avec « Remplacer » : la pièce démontée garde son historique")
    if data.type not in LOGGED or data.type not in types_of(p):
        raise ValueError("Cette maintenance n'est pas suivie sur cette pièce")
    mid = "m-" + uuid.uuid4().hex[:10]
    doc = {"id": mid, "part_id": pid, "vehicle": p["vehicle"], "type": data.type, "date": data.date.isoformat(), "notes": data.notes.strip(), "by": user.lower(), "created_at": now().isoformat()}
    maint_coll().put(mid, doc)
    return doc


def delete_maint(mid: str) -> None:
    if not maint_coll().get(mid):
        raise LookupError("Maintenance introuvable")
    maint_coll().delete(mid)


# ---- Magasin de pièces : modèles d'architecture (Ensemble › Sous-ensemble) ---------------------------------------------------------------------

def _seed_templates(user: str = "logbook") -> None:
    """Crée chaque modèle de départ une seule fois (marqueur « _seed:nom ») : ensuite il se modifie ou se supprime, il ne revient pas."""
    from . import history
    from .rides_seed import SEED_TEMPLATES
    for t in SEED_TEMPLATES:
        key = "_seed:" + t["name"]
        if templates_coll().get(key):
            continue
        with history.mute():
            templates_coll().put(key, {"id": key})
            if not any(x.get("name", "").lower() == t["name"].lower() for x in templates_coll().all()):
                save_template(None, TemplateIn(**t), user)


def list_templates() -> list[dict]:
    _seed_templates()
    return sorted((t for t in templates_coll().all() if not t.get("id", "").startswith("_seed")), key=lambda t: t["name"].lower())


def save_template(tid: str | None, data: TemplateIn, user: str) -> dict:
    cur = templates_coll().get(tid) if tid else None
    if tid and not cur:
        raise LookupError("Modèle introuvable")
    if any(t["id"] != tid and t.get("name", "").lower() == data.name.strip().lower() for t in templates_coll().all()):
        raise ValueError("Un modèle porte déjà ce nom")
    tid = tid or "t-" + uuid.uuid4().hex[:8]
    doc = {"id": tid, **data.model_dump(mode="json"), "name": data.name.strip(), "created_by": (cur or {}).get("created_by", user.lower()), "created_at": (cur or {}).get("created_at", now().isoformat()),
           "updated_at": now().isoformat(), "updated_by": user.lower()}
    templates_coll().put(tid, doc)
    return doc


def delete_template(tid: str) -> None:
    if not templates_coll().get(tid):
        raise LookupError("Modèle introuvable")
    templates_coll().delete(tid)                                     # les voitures déjà construites sur ce modèle gardent leurs pièces


def _node_part(n: dict, vehicle: str, parent: str | None, user: str) -> dict:
    types = [t for t in MAINT_TYPES if t in n.get("types", [])]
    rep = n.get("replace") or {}
    doc = {"id": "p-" + uuid.uuid4().hex[:10], "vehicle": vehicle, "name": n["name"], "parent_id": parent, "group": bool(n.get("group")), "serial": "", "notes": "", "reference": n.get("reference", ""), "fn": n.get("fn") if n.get("fn") in FUNCTIONS else "", "km_start": 0.0, "hours_start": 0.0, "mounted_from": None,
           "limit_km": None, "limit_hours": None, "limit_note": "", "warn_pct": 75.0, "types": types, "maint": {}, "removed_at": None, "created_by": user.lower(), "created_at": now().isoformat()}
    if not n.get("group"):
        if "replace" in types:
            doc.update(limit_km=rep.get("limit_km"), limit_hours=rep.get("limit_hours"), limit_note=rep.get("note") or "", warn_pct=rep.get("warn_pct") or 75.0)
        doc["maint"] = {t: {k: (n.get(t) or {}).get(k) for k in ("limit_km", "limit_hours", "limit_events", "warn_pct", "note")} for t in LOGGED if t in types}
    return doc


def apply_template(vehicle: str, tid: str, user: str) -> dict:
    """Construit l'arborescence du modèle sur la voiture. Non destructif : un élément qui existe déjà (même nom au même endroit, non démonté) est conservé tel quel."""
    if not car_of(vehicle):
        raise LookupError("Voiture introuvable")
    t = templates_coll().get(tid)
    if not t:
        raise LookupError("Modèle introuvable")
    existing = [p for p in parts_coll().all() if p["vehicle"] == vehicle and not p.get("removed_at")]
    mapping: dict[str, str] = {}                                      # id du nœud du modèle -> id de la pièce de la voiture
    created = kept = 0
    pending = list(t["nodes"])
    guard = 0
    while pending and guard < 500:
        guard += 1
        n = pending.pop(0)
        if n.get("parent_id") and n["parent_id"] not in mapping:
            pending.append(n)                                         # le parent n'est pas encore traité
            continue
        parent = mapping.get(n.get("parent_id")) if n.get("parent_id") else None
        same = next((p for p in existing if p.get("parent_id") == parent and p["name"].lower() == n["name"].lower()), None)
        if same:
            if not same.get("fn") and n.get("fn") in FUNCTIONS and not same.get("group"):
                same["fn"] = n["fn"]                                 # une pièce déjà là reçoit la fonction du modèle (rien d'autre n'est modifié)
                parts_coll().put(same["id"], same)
            mapping[n["id"]] = same["id"]
            kept += 1
            continue
        doc = _node_part(n, vehicle, parent, user)
        parts_coll().put(doc["id"], doc)
        existing.append(doc)
        mapping[n["id"]] = doc["id"]
        created += 1
    meta = cars_coll().get(vehicle) or {"id": vehicle}
    meta["template_id"], meta["template_name"] = tid, t["name"]
    cars_coll().put(vehicle, meta)
    return {"created": created, "kept": kept, "template": {"id": tid, "name": t["name"]}}


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


def _run_doc(vehicle: str, data: RunIn, rid: str, user: str, created: str | None = None, source: str = "manual", session_id: str = "") -> dict:
    km = compute_km(data)
    if not km and data.hours is None:
        raise ValueError("Indiquez des tours, des spéciales, des kilomètres ou une durée")
    return {"id": rid, "vehicle": vehicle, **data.model_dump(mode="json"), "km": km, "km_manual": data.km is not None, "session_id": session_id, "created_by": user.lower(), "created_at": created or now().isoformat(), "source": source}


def _session_key(d: dict) -> tuple:
    return (d["date"], d["name"].strip().lower(), d.get("kind", "circuit"), (d.get("circuit") or "").strip().lower())


def _find_or_create_session(data: RunIn, user: str) -> dict:
    """Retrouve le roulage (même date, nom, type et circuit) ou le crée : toute voiture associée passe par un roulage."""
    k = _session_key({**data.model_dump(mode="json")})
    for s in sessions_coll().all():
        if _session_key(s) == k:
            return s
    sid = "s-" + uuid.uuid4().hex[:10]
    doc = {"id": sid, "date": data.date.isoformat(), "name": data.name.strip(), "kind": data.kind, "circuit": data.circuit.strip(), "stages": [s.model_dump(mode="json") for s in data.stages],
           "event_id": data.event_id, "notes": "", "created_by": user.lower(), "created_at": now().isoformat()}
    sessions_coll().put(sid, doc)
    return doc


def _ensure_sessions() -> None:
    """Rattache à un roulage les anciens runs saisis voiture par voiture (une seule fois, sans rien perdre)."""
    legacy = [r for r in runs_coll().all() if not r.get("session_id")]
    for run in legacy:
        data = RunIn(**{k: run[k] for k in ("date", "name", "kind", "circuit", "laps", "stages", "hours", "drivers", "event_id", "notes") if k in run})
        s = _find_or_create_session(data, run.get("created_by", "logbook"))
        run["session_id"] = s["id"]
        run["km_manual"] = bool(run.get("km_manual", not (run.get("laps") or run.get("stages"))))
        runs_coll().put(run["id"], run)


def add_run(vehicle: str, data: RunIn, user: str, source: str = "manual") -> dict:
    """Saisie directe d'un run pour une voiture (imports, interface technique) : il est rattaché au roulage correspondant, créé au besoin."""
    if not car_of(vehicle):
        raise LookupError("Voiture introuvable")
    s = _find_or_create_session(data, user)
    doc = _run_doc(vehicle, data, "r-" + uuid.uuid4().hex[:10], user, source=source, session_id=s["id"])
    runs_coll().put(doc["id"], doc)
    return doc


def update_run(rid: str, data: RunIn, user: str) -> dict:
    cur = runs_coll().get(rid)
    if not cur:
        raise LookupError("Run introuvable")
    if cur.get("session_id"):
        s = sessions_coll().get(cur["session_id"])
        if s:                                                        # le roulage décide de la date, du nom et du circuit ; ici on ne change que la part de la voiture
            data = data.model_copy(update={"date": date.fromisoformat(s["date"]), "name": s["name"], "kind": s["kind"], "circuit": s.get("circuit", ""), "event_id": s.get("event_id", "")})
    doc = _run_doc(cur["vehicle"], data, rid, cur.get("created_by", user), cur.get("created_at"), cur.get("source", "manual"), cur.get("session_id", ""))
    runs_coll().put(rid, doc)
    return doc


def delete_run(rid: str) -> None:
    if not runs_coll().get(rid):
        raise LookupError("Run introuvable")
    runs_coll().delete(rid)


# ---- Roulages (sessions) ---------------------------------------------------------------------------------------------------------------------

def _session_view(s: dict, runs: list[dict], names: dict[str, str]) -> dict:
    mine = sorted((r for r in runs if r.get("session_id") == s["id"]), key=lambda r: names.get(r["vehicle"], r["vehicle"]).lower())
    return {**s, "cars": [{"run_id": r["id"], "key": r["vehicle"], "name": names.get(r["vehicle"], r["vehicle"]), "km": r.get("km"), "hours": r.get("hours"), "laps": r.get("laps", 0), "drivers": r.get("drivers", []), "notes": r.get("notes", "")} for r in mine],
            "km_total": round(sum(r.get("km") or 0 for r in mine), 1)}


def list_sessions() -> list[dict]:
    _ensure_sessions()
    runs = runs_coll().all()
    names = {c["key"]: c["name"] for c in race_cars()}
    return sorted((_session_view(s, runs, names) for s in sessions_coll().all()), key=lambda s: (s["date"], s["name"].lower()), reverse=True)


def save_session(sid: str | None, data: SessionIn, user: str) -> dict:
    cur = sessions_coll().get(sid) if sid else None
    if sid and not cur:
        raise LookupError("Roulage introuvable")
    if data.kind == "circuit" and data.circuit.strip() and not circuits_coll().get(circuit_id(data.circuit)):
        raise ValueError("Circuit inconnu : enregistrez-le d'abord (nom et longueur du tour)")
    sid = sid or "s-" + uuid.uuid4().hex[:10]
    doc = {"id": sid, **data.model_dump(mode="json"), "name": data.name.strip(), "circuit": data.circuit.strip() if data.kind == "circuit" else "", "stages": [s.model_dump(mode="json") for s in data.stages] if data.kind == "rally" else [],
           "created_by": (cur or {}).get("created_by", user.lower()), "created_at": (cur or {}).get("created_at", now().isoformat()), "updated_at": now().isoformat()}
    sessions_coll().put(sid, doc)
    if cur:                                                          # les voitures associées suivent la date, le nom, le type et le circuit ; leurs kilomètres se recalculent (sauf ceux saisis à la main)
        for run in [r for r in runs_coll().all() if r.get("session_id") == sid]:
            rin = RunIn(date=data.date, name=doc["name"], kind=doc["kind"], circuit=doc["circuit"], laps=run.get("laps", 0), stages=run.get("stages", []) if doc["kind"] == "rally" else [],
                        km=run["km"] if run.get("km_manual") else None, hours=run.get("hours"), drivers=run.get("drivers", []), event_id=doc["event_id"], notes=run.get("notes", ""))
            try:
                runs_coll().put(run["id"], _run_doc(run["vehicle"], rin, run["id"], run.get("created_by", user), run.get("created_at"), run.get("source", "manual"), sid))
            except ValueError:
                run.update(date=data.date.isoformat(), name=doc["name"], kind=doc["kind"], circuit=doc["circuit"])
                runs_coll().put(run["id"], run)
    return doc


def delete_session(sid: str) -> dict:
    if not sessions_coll().get(sid):
        raise LookupError("Roulage introuvable")
    n = 0
    for run in [r for r in runs_coll().all() if r.get("session_id") == sid]:
        runs_coll().delete(run["id"])
        n += 1
    sessions_coll().delete(sid)
    return {"cars": n}


def associate(sid: str, vehicle: str, data: AssocIn, user: str) -> dict:
    """Associe une voiture à un roulage (une seule fois par roulage) avec ses tours, ses spéciales ou ses kilomètres."""
    s = sessions_coll().get(sid)
    if not s:
        raise LookupError("Roulage introuvable")
    if not car_of(vehicle):
        raise LookupError("Voiture introuvable")
    if any(r.get("session_id") == sid and r["vehicle"] == vehicle for r in runs_coll().all()):
        raise ValueError("Cette voiture est déjà associée à ce roulage")
    stages = data.stages if data.stages is not None else [Stage(**x) for x in s.get("stages", [])]
    rin = RunIn(date=date.fromisoformat(s["date"]), name=s["name"], kind=s["kind"], circuit=s.get("circuit", ""), laps=data.laps, stages=stages if s["kind"] == "rally" else [], km=data.km, hours=data.hours,
                drivers=data.drivers, event_id=s.get("event_id", ""), notes=data.notes)
    doc = _run_doc(vehicle, rin, "r-" + uuid.uuid4().hex[:10], user, session_id=sid)
    runs_coll().put(doc["id"], doc)
    return doc


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
