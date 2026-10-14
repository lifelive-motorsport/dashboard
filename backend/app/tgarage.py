"""Pointages › Jobs → Garage : mises à jour des pièces PROPOSÉES à partir des lignes de liste de contrôle cochées et des formulaires validés.
Principe : rien n'est écrit dans le Garage sans confirmation (chef d'atelier, Super User, ingénieur / coordinateur), sauf la mesure d'embrayage (voir `tforms.py`, la mesure vaut preuve).
Une ligne ou un formulaire vise une FONCTION de pièce (`rides.FUNCTIONS`) et un type de maintenance ; la pièce de la voiture est retrouvée par sa fonction (ou par le choix mémorisé
`fn_map` de la voiture), sinon le confirmateur la choisit une fois. Chaque confirmation garde sa source : même ligne = une seule maintenance, et on peut l'annuler.
Le texte libre d'un pointage ne propose jamais rien. Un remplacement n'est jamais appliqué ici : il est seulement signalé (⟳ Remplacer se fait dans le Garage)."""
from __future__ import annotations

import re
from datetime import date

from . import rides, tforms, timesheets, tmodels
from .timesheets import Coll

_coll: Coll | None = None

# Liens par défaut d'après le texte d'une ligne (modèles créés avant l'existence des liens) ; un lien explicite de la ligne (`fn` / `mt`) prime.
DEFAULT_LINKS = [(re.compile(r"^vidange moteur", re.I), "engine", "fluids"), (re.compile(r"^vidange (de la )?bv|^vidange boite", re.I), "gearbox", "fluids"),
                 (re.compile(r"^vidange du pont", re.I), "rear_axle", "fluids"), (re.compile(r"^purger? les freins", re.I), "brakes", "fluids")]


def coll() -> Coll:
    global _coll
    _coll = _coll or Coll("timesheet_garage")
    return _coll


def can_confirm(r: dict, job: dict | None) -> bool:
    if r.get("role") == "coordinator":
        return True
    return timesheets.chef_for(r, job)


def _rid(key: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", key)


def _line_link(line: dict) -> tuple[str, str] | None:
    if line.get("fn") in rides.FUNCTIONS and line.get("mt") in rides.LOGGED:
        return line["fn"], line["mt"]
    for rx, fn, mt in DEFAULT_LINKS:
        if rx.search(line.get("text", "").strip()):
            return fn, mt
    return None


def _form_link(ftype: str) -> tuple[str, str] | None:
    """Maintenance proposée à la validation d'un formulaire : lien porté par son modèle (modifiable dans Modèles › Modèles de formulaires)."""
    m = tmodels.spec_of(ftype)
    g = (m[1].get("garage") if m else None) or {}
    return (g["fn"], g["mt"]) if g.get("fn") in rides.FUNCTIONS and g.get("mt") in rides.LOGGED else None


def _parts_of(car_key: str) -> list[dict]:
    allp = [p for p in rides.parts_coll().all() if p["vehicle"] == car_key and not p.get("removed_at")]
    byid = {p["id"]: p for p in allp}

    def path(p):
        out = [p["name"]]
        while p.get("parent_id") and p["parent_id"] in byid:
            p = byid[p["parent_id"]]
            out.append(p["name"])
        return " › ".join(reversed(out))
    return [{"id": p["id"], "name": p["name"], "path": path(p), "fn": p.get("fn", ""), "types": rides.types_of(p)} for p in allp if not p.get("group")]


def _resolve(car_key: str, fn: str, parts: list[dict]) -> str:
    meta = rides.cars_coll().get(car_key) or {}
    mapped = (meta.get("fn_map") or {}).get(fn)
    if mapped and any(p["id"] == mapped for p in parts):
        return mapped
    cands = [p for p in parts if p["fn"] == fn]
    return cands[0]["id"] if len(cands) == 1 else ""


def _status(key: str) -> dict:
    return coll().get(_rid(key)) or {}


def proposals(job: dict) -> dict:
    key_car = tforms.car_key_of(job)
    parts = _parts_of(key_car) if key_car else []
    out = []
    tpl = timesheets.templates().get((job.get("checklist") or {}).get("template_id", "")) if job.get("checklist") else None
    tpl_lines = {ln["id"]: ln for s in (tpl or {}).get("sections", []) for ln in s["lines"]}
    for sec in (job.get("checklist") or {}).get("sections", []):
        for ln in sec["lines"]:
            if not ln.get("done"):
                continue
            link = _line_link(ln) or _line_link(tpl_lines.get(ln["id"], {}))
            if not link:
                continue
            out.append(_item(f"line:{job['id']}:{ln['id']}", "line", ln["text"], link, (ln.get("done_at") or "")[:10], key_car, parts))
    for f in sorted(tforms.forms().all(), key=lambda f: f["created_at"]):
        if f["job_id"] != job["id"] or not f.get("validated"):
            continue
        link = _form_link(f["type"])
        if link:
            out.append(_item(f"form:{f['id']}", "form", tforms.label_of(f["type"]), link, f["data"]["header"].get("date", ""), key_car, parts))
        elif tforms.is_clutch(f["type"]) and tforms.compute(f["type"], f["data"])["state"] == "replace" and f.get("part_id"):
            out.append({"key": f"replace:{f['id']}", "kind": "replace", "source": "form", "label": "Remplacer l'embrayage", "part_id": f["part_id"], "status": "pending", "fn": "clutch", "fn_label": rides.FUNCTIONS["clutch"],
                        "type": "replace", "type_label": rides.MAINT_LABEL["replace"], "date": f["data"]["header"].get("date", ""), "part_name": next((p["name"] for p in parts if p["id"] == f["part_id"]), ""), "tracked": True})
    return {"car_key": key_car, "proposals": out, "parts": parts}


def _item(key: str, source: str, label: str, link: tuple[str, str], when: str, car_key: str | None, parts: list[dict]) -> dict:
    fn, mt = link
    st = _status(key)
    pid = st.get("part_id") or (_resolve(car_key, fn, parts) if car_key else "")
    part = next((p for p in parts if p["id"] == pid), None)
    return {"key": key, "kind": "maint", "source": source, "label": label, "fn": fn, "fn_label": rides.FUNCTIONS[fn], "type": mt, "type_label": rides.MAINT_LABEL[mt], "date": when or date.today().isoformat(),
            "part_id": pid, "part_name": part["path"] if part else "", "tracked": bool(part and mt in part["types"]), "status": st.get("status", "pending"), "maint_id": st.get("maint_id")}


def apply(job: dict, items: list[dict], user: str) -> list[dict]:
    """Applique les propositions choisies (clé + pièce) ; l'identité de la maintenance (type, date) vient du serveur, jamais du client."""
    cur = proposals(job)
    by = {p["key"]: p for p in cur["proposals"] if p["kind"] == "maint"}
    parts = {p["id"]: p for p in cur["parts"]}
    results = []
    for it in items:
        p = by.get(it.get("key"))
        if not p:
            results.append({"key": it.get("key"), "ok": False, "error": "Proposition introuvable"})
            continue
        if p["status"] == "applied":
            results.append({"key": p["key"], "ok": True, "already": True})
            continue
        pid = it.get("part_id") or p["part_id"]
        if pid not in parts:
            results.append({"key": p["key"], "ok": False, "error": "Choisissez la pièce de la voiture"})
            continue
        try:
            d = rides.log_maint(pid, rides.MaintIn(type=p["type"], date=date.fromisoformat(p["date"]), notes=f"{p['label']} — {job.get('title', '')}"[:300]), user)
        except (ValueError, LookupError) as e:
            results.append({"key": p["key"], "ok": False, "error": str(e)})
            continue
        coll().put(_rid(p["key"]), {"id": _rid(p["key"]), "key": p["key"], "job_id": job["id"], "status": "applied", "maint_id": d["id"], "part_id": pid, "by": user.lower(), "at": timesheets.now().isoformat()})
        if parts[pid]["fn"] != p["fn"]:                               # choix manuel : mémorisé pour cette voiture (fonction -> pièce)
            meta = rides.cars_coll().get(cur["car_key"]) or {"id": cur["car_key"]}
            meta.setdefault("fn_map", {})[p["fn"]] = pid
            rides.cars_coll().put(cur["car_key"], meta)
        results.append({"key": p["key"], "ok": True, "maint_id": d["id"]})
    return results


def ignore(job: dict, key: str, user: str) -> None:
    if not any(p["key"] == key for p in proposals(job)["proposals"]):
        raise LookupError("Proposition introuvable")
    coll().put(_rid(key), {"id": _rid(key), "key": key, "job_id": job["id"], "status": "ignored", "by": user.lower(), "at": timesheets.now().isoformat()})


def restore(job: dict, key: str) -> None:
    """Annule une confirmation (la maintenance est retirée de la pièce) ou remet une proposition ignorée."""
    st = _status(key)
    if not st or st.get("job_id") != job["id"]:
        raise LookupError("Proposition introuvable")
    if st.get("maint_id"):
        try:
            rides.delete_maint(st["maint_id"])
        except LookupError:
            pass
    coll().delete(_rid(key))
