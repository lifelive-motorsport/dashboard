"""Pneus : stock de trains de pneus par voiture, kilométrage / tours / cycles de chauffe CALCULÉS d'après les roulages (comme les pièces du Garage).

Un train (`ride_tyres`) = une référence (ex. « S9 »), une marque et un modèle, des dimensions, une gomme, un état (neuf, utilisé, en réserve, rebut), des limites de vie
(km, tours, cycles) et un point de départ (ce qu'il avait déjà roulé à son encodage). Une participation à un roulage indique le(s) train(s) utilisé(s) (`tyres` de `ride_runs`) ;
les compteurs ne sont jamais incrémentés : ils sont recalculés depuis les participations."""
from __future__ import annotations

import uuid
from datetime import date
from typing import Literal

from pydantic import BaseModel, Field

from . import rides
from .timesheets import Coll

_coll = None
STATUS = ("new", "used", "reserve", "scrap")


def coll() -> Coll:
    global _coll
    _coll = _coll or Coll("ride_tyres")
    return _coll


class TyreIn(BaseModel):
    car: str = Field(default="", max_length=80)
    ref: str = Field(min_length=1, max_length=40)
    brand: str = Field(default="", max_length=60)
    model: str = Field(default="", max_length=60)
    size: str = Field(default="", max_length=60)
    compound: str = Field(default="", max_length=40)
    bought: date | None = None
    status: Literal["new", "used", "reserve", "scrap"] = "new"
    limit_km: float | None = Field(default=None, gt=0, le=100000)
    limit_laps: int | None = Field(default=None, gt=0, le=100000)
    limit_cycles: int | None = Field(default=None, gt=0, le=1000)
    alert_pct: float = Field(default=75.0, ge=10, le=100)
    start_km: float = Field(default=0, ge=0, le=100000)
    start_laps: int = Field(default=0, ge=0, le=100000)
    start_cycles: int = Field(default=0, ge=0, le=1000)
    notes: str = Field(default="", max_length=500)


def check_uses(car: str, uses: list) -> None:
    """Les trains cités par une participation existent, appartiennent à la voiture et ne sont pas au rebut."""
    seen = set()
    for u in uses:
        sid = u.set_id if hasattr(u, "set_id") else u.get("set_id")
        t = coll().get(sid)
        if not t or t["car"] != car:
            raise ValueError("Train de pneus introuvable pour cette voiture")
        if sid in seen:
            raise ValueError("Le même train est cité deux fois")
        seen.add(sid)


def _shares(run: dict) -> list[dict]:
    """Part de chaque train dans une participation : tours, kilomètres, cycles."""
    uses = run.get("tyres") or []
    if not uses:
        return []
    total_laps, km = run.get("laps") or 0, run.get("km") or 0
    fixed = sum(u.get("laps") or 0 for u in uses if u.get("laps") is not None)
    free = [u for u in uses if u.get("laps") is None]
    out = []
    for u in uses:
        if u.get("laps") is not None:
            laps = u["laps"]
        elif len(uses) == 1:
            laps = total_laps
        else:
            laps = round(max(total_laps - fixed, 0) / len(free)) if total_laps else 0
        k = round(km * laps / total_laps, 2) if total_laps else round(km / len(uses), 2)
        out.append({"set_id": u["set_id"], "laps": laps, "km": k, "cycles": u.get("cycles", 1)})
    return out


def _ratio(t: dict, km: float, laps: int, cycles: int) -> tuple[float | None, str]:
    rs = []
    if t.get("limit_km"):
        rs.append(km / t["limit_km"])
    if t.get("limit_laps"):
        rs.append(laps / t["limit_laps"])
    if t.get("limit_cycles"):
        rs.append(cycles / t["limit_cycles"])
    if not rs:
        return None, "none"
    r = max(rs)
    return r, "over" if r >= 1 else "warn" if r >= (t.get("alert_pct") or 75) / 100 else "ok"


def view(car: str | None = None) -> list[dict]:
    """Trains (d'une voiture, ou de toutes) avec leurs compteurs et leur historique d'utilisation."""
    sets = [t for t in coll().all() if not car or t["car"] == car]
    runs = rides.runs_coll().all()
    sess = {s["id"]: s for s in rides.sessions_coll().all()}
    use: dict[str, list[dict]] = {}
    for r in runs:
        for sh in _shares(r):
            s = sess.get(r.get("session_id")) or {}
            use.setdefault(sh["set_id"], []).append({**sh, "run_id": r["id"], "date": r["date"], "name": r["name"], "circuit": r.get("circuit", ""), "event": (s.get("meeting") or "")})
    out = []
    for t in sets:
        hist = sorted(use.get(t["id"], []), key=lambda x: (x["date"], x["run_id"]), reverse=True)
        km = round(t.get("start_km", 0) + sum(h["km"] for h in hist), 1)
        laps = t.get("start_laps", 0) + sum(h["laps"] for h in hist)
        cycles = t.get("start_cycles", 0) + sum(h["cycles"] for h in hist)
        ratio, state = _ratio(t, km, laps, cycles)
        out.append({**t, "km": km, "laps": laps, "cycles": cycles, "runs": len(hist), "ratio": ratio, "state": "scrap" if t["status"] == "scrap" else state, "history": hist})
    return sorted(out, key=lambda t: (t["car"], t["status"] == "scrap", t["ref"].lower()))


def options(car: str | None = None) -> list[dict]:
    """Trains d'une voiture (ou de toutes) pour les menus d'une participation ; l'écran n'y propose pas ceux au rebut, mais reconnaît ceux déjà utilisés."""
    return [{"id": t["id"], "car": t["car"], "ref": t["ref"], "label": " · ".join(x for x in (t["ref"], t.get("brand", ""), t.get("model", "")) if x), "status": t["status"]}
            for t in coll().all() if not car or t["car"] == car]


def save(tid: str | None, data: TyreIn, user: str) -> dict:
    cur = coll().get(tid) if tid else None
    if tid and not cur:
        raise LookupError("Train de pneus introuvable")
    car = cur["car"] if cur else data.car
    if not rides.car_of(car):
        raise LookupError("Voiture introuvable")
    ref = data.ref.strip()
    if any(t["car"] == car and t["ref"].strip().lower() == ref.lower() and t["id"] != tid for t in coll().all()):
        raise ValueError(f"Un train « {ref} » existe déjà pour cette voiture")
    tid = tid or "ty-" + uuid.uuid4().hex[:10]
    doc = {**(cur or {}), "id": tid, **data.model_dump(mode="json"), "car": car, "ref": ref,
           "scrapped_at": (cur or {}).get("scrapped_at") if data.status == "scrap" and (cur or {}).get("status") == "scrap" else date.today().isoformat() if data.status == "scrap" else "",
           "created_by": (cur or {}).get("created_by", user.lower()), "created_at": (cur or {}).get("created_at", rides.now().isoformat()), "updated_at": rides.now().isoformat()}
    coll().put(tid, doc)
    return doc


def delete(tid: str) -> None:
    if not coll().get(tid):
        raise LookupError("Train de pneus introuvable")
    if any(sh["set_id"] == tid for r in rides.runs_coll().all() for sh in _shares(r)):
        raise ValueError("Ce train a déjà roulé : mettez-le au rebut plutôt que de le supprimer")
    coll().delete(tid)


def for_meeting(meeting: str, car: str) -> list[dict]:
    """Trains utilisés par la voiture pendant l'épreuve, avec leur kilométrage de l'épreuve et leur total (run report)."""
    sess = {s["id"] for s in rides.sessions_coll().all() if s.get("meeting") == meeting}
    mine: dict[str, dict] = {}
    for r in rides.runs_coll().all():
        if r["vehicle"] != car or r.get("session_id") not in sess:
            continue
        for sh in _shares(r):
            m = mine.setdefault(sh["set_id"], {"laps": 0, "km": 0.0, "cycles": 0})
            m["laps"] += sh["laps"]
            m["km"] = round(m["km"] + sh["km"], 1)
            m["cycles"] += sh["cycles"]
    total = {t["id"]: t for t in view(car)}
    return [{"id": sid, "ref": total[sid]["ref"], "brand": total[sid].get("brand", ""), "model": total[sid].get("model", ""), "compound": total[sid].get("compound", ""), **m, "total_km": total[sid]["km"], "total_laps": total[sid]["laps"], "total_cycles": total[sid]["cycles"]}
            for sid, m in mine.items() if sid in total]
