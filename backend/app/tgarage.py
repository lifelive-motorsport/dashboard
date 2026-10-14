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
            pre = next((p for p in parts if p["id"] == ln.get("part_id")), None) if ln.get("mt") in rides.LOGGED else None      # ligne ajoutée depuis « Maintenances à prévoir » : pièce précise
            link = (pre["fn"], ln["mt"]) if pre else (_line_link(ln) or _line_link(tpl_lines.get(ln["id"], {})))
            if not link:
                continue
            out.append(_item(f"line:{job['id']}:{ln['id']}", "line", ln["text"], link, (ln.get("done_at") or "")[:10], key_car, parts, pre["id"] if pre else ""))
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


def _item(key: str, source: str, label: str, link: tuple[str, str], when: str, car_key: str | None, parts: list[dict], force_part: str = "") -> dict:
    fn, mt = link
    st = _status(key)
    pid = st.get("part_id") or force_part or (_resolve(car_key, fn, parts) if fn and car_key else "")
    part = next((p for p in parts if p["id"] == pid), None)
    return {"key": key, "kind": "maint", "source": source, "label": label, "fn": fn, "fn_label": rides.FUNCTIONS.get(fn) or (part["name"] if part else ""), "type": mt, "type_label": rides.MAINT_LABEL[mt], "date": when or date.today().isoformat(),
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
        if p["fn"] and parts[pid]["fn"] != p["fn"]:                   # choix manuel : mémorisé pour cette voiture (fonction -> pièce)
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


# ---- Maintenances à prévoir (Garage → job) ----------------------------------------------------------------------------------------------------

ADDED_SECTION = "garage"
STATE_LABEL = {"warn": "À surveiller", "over": "Dépassé"}


def _line_id(part_id: str, mt: str) -> str:
    return f"g-{part_id}-{mt}"


def due(job: dict) -> dict:
    """Maintenances de la voiture du job en alerte MAINTENANT (« à surveiller » ou « dépassé ») : contrôle, vidange, révisions ; le remplacement n'est que signalé (jamais ajouté ni appliqué).
    Chaque maintenance peut être ajoutée à la liste du job (ligne liée à sa pièce) : cochée par le mécanicien, elle propose ensuite la mise à jour du Garage, confirmée par le chef."""
    key = tforms.car_key_of(job)
    if not key:
        return {"car_key": None, "maint": [], "replace": []}
    existing = {ln["id"] for s in (job.get("checklist") or {}).get("sections", []) for ln in s["lines"]}
    by_id = {p["id"]: p["path"] for p in _parts_of(key)}
    maint, replace = [], []

    def walk(nodes):
        for n in nodes:
            if n.get("removed_at"):
                continue
            for m in n.get("meters", []):
                if m["state"] not in ("warn", "over"):
                    continue
                row = {"part_id": n["id"], "part": by_id.get(n["id"], n["name"]), "type": m["type"], "type_label": m["label"], "state": m["state"], "state_label": STATE_LABEL[m["state"]], "ratio": m.get("ratio")}
                if m["type"] == "replace":
                    replace.append(row)
                elif m["type"] in rides.LOGGED:
                    maint.append({**row, "line_id": _line_id(n["id"], m["type"]), "added": _line_id(n["id"], m["type"]) in existing})
            walk(n.get("children", []))
    walk(rides.tree(key, rides._runs_of(key)))
    rank = {"over": 0, "warn": 1}
    maint.sort(key=lambda r: (rank[r["state"]], r["part"]))
    replace.sort(key=lambda r: (rank[r["state"]], r["part"]))
    return {"car_key": key, "maint": maint, "replace": replace}


def add_lines(job: dict, items: list[dict]) -> list[dict]:
    """Ajoute à la liste de contrôle du job (section « Maintenances Garage ») les maintenances choisies ; sans doublon ; crée la liste si le job n'en avait pas."""
    cur = due(job)
    ok = {(m["part_id"], m["type"]): m for m in cur["maint"]}
    cl = job.get("checklist")
    if not cl:
        cl = job["checklist"] = {"template_id": "", "template_name": "", "sections": []}
    sec = next((s for s in cl["sections"] if s["id"] == ADDED_SECTION), None)
    if not sec:
        sec = {"id": ADDED_SECTION, "title": "Maintenances Garage", "lines": []}
        cl["sections"].append(sec)
    have = {ln["id"] for ln in sec["lines"]}
    results = []
    for it in items:
        m = ok.get((it.get("part_id"), it.get("type")))
        if not m:
            results.append({"part_id": it.get("part_id"), "ok": False, "error": "Cette maintenance n'est plus à prévoir"})
            continue
        if m["line_id"] not in have:
            sec["lines"].append({"id": m["line_id"], "text": f"{m['type_label']} — {m['part']}", "note": "", "mt": m["type"], "part_id": m["part_id"], "done": False, "done_by": None, "done_at": None, "entry_id": None})
            have.add(m["line_id"])
        results.append({"part_id": m["part_id"], "ok": True})
    if not sec["lines"]:
        cl["sections"].remove(sec)
    timesheets.jobs().put(job["id"], job)
    return results
