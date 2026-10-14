"""Pointages › Modèles › Modèles de formulaires : les listes de contrôle (révisions de boîte et de pont…) et les feuilles de relevés (setup, setdown) sont des MODÈLES stockés
(`timesheet_form_models`) que le chef d'atelier, l'ingénieur / coordinateur et le Super User modifient (sections, éléments, lignes, demande de réglage, maintenance proposée au Garage).
Les modèles d'origine (`tcheck.TYPES`, `tsheet.TYPES`) sont créés au premier accès puis gérés ici ; on peut en dupliquer un pour créer un nouveau formulaire. La mesure d'embrayage
(calcul d'usure) reste définie dans le code : elle s'affiche en consultation. Un formulaire déjà rempli garde ses valeurs même si un élément est retiré du modèle (il n'est plus affiché).
L'identifiant d'un élément ne change jamais quand on renomme son libellé ; un nouvel élément reçoit un identifiant neuf."""
from __future__ import annotations

import copy
import re
import time
import unicodedata
import uuid

from . import history, rides, tcheck, tsheet
from .timesheets import Coll, now

_coll: Coll | None = None
_cache: dict = {"at": 0.0, "data": None}
TTL = 30.0
MAX_ITEMS = 120
LAYOUTS = tuple(tsheet.COLS)


def coll() -> Coll:
    global _coll
    _coll = _coll or Coll("timesheet_form_models")
    return _coll


def _seed_docs() -> dict[str, dict]:
    docs = {}
    for k, v in tcheck.TYPES.items():
        spec = copy.deepcopy(v)
        spec["garage"] = _link(k)
        docs[k] = {"id": k, "kind": "checklist", "builtin": True, "spec": spec}
    for k, v in tsheet.TYPES.items():
        docs[k] = {"id": k, "kind": "sheet", "builtin": True, "spec": copy.deepcopy(v)}
    return docs


def _link(k: str) -> dict | None:
    fn_mt = {"gearbox_m3": ("gearbox", "revision"), "gearbox_z4": ("gearbox", "revision"), "gearbox_diff": ("gearbox", "revision"), "rear_axle": ("rear_axle", "revision")}.get(k)
    return {"fn": fn_mt[0], "mt": fn_mt[1]} if fn_mt else None


def ensure_seed() -> None:
    have = {d["id"] for d in coll().all()}
    with history.mute():
        for k, d in _seed_docs().items():
            if k not in have:
                coll().put(k, {**d, "created_at": now().isoformat(), "created_by": "system", "updated_at": now().isoformat(), "updated_by": "system"})
    _cache["data"] = None


def _models() -> dict[str, dict]:
    if _cache["data"] is None or time.time() - _cache["at"] > TTL:
        ensure_seed()
        _cache["data"] = {d["id"]: d for d in coll().all()}
        _cache["at"] = time.time()
    return _cache["data"]


def invalidate() -> None:
    _cache["data"] = None


def spec_of(ftype: str) -> tuple[str, dict] | None:
    """(genre, spécification) d'un formulaire non-embrayage : modèle stocké, à défaut modèle d'origine du code."""
    d = _models().get(ftype)
    if d:
        return d["kind"], d["spec"]
    code = tcheck.TYPES.get(ftype)
    if code:
        return "checklist", code
    code = tsheet.TYPES.get(ftype)
    return ("sheet", code) if code else None


def used_counts() -> dict[str, int]:
    from . import tforms
    out: dict[str, int] = {}
    for f in tforms.forms().all():
        out[f["type"]] = out.get(f["type"], 0) + 1
    return out


def effective_types() -> list[dict]:
    out = []
    for k, d in sorted(_models().items(), key=lambda kv: (not kv[1].get("builtin"), kv[1]["spec"]["label"].lower())):
        spec = d["spec"]
        if d["kind"] == "checklist":
            out.append({"id": k, "kind": "checklist", "label": spec["label"], "header": spec["header"], "header_labels": {h: tcheck.HEADER_LABELS[h] for h in spec["header"]}, "requests": spec["requests"],
                        "sections": spec["sections"], "garage": spec.get("garage")})
        else:
            out.append(tsheet.describe(k, spec))
    return out


def admin_view() -> list[dict]:
    from . import tforms
    used = used_counts()
    models = [{**{f: d[f] for f in ("id", "kind", "builtin")}, "label": d["spec"]["label"], "spec": d["spec"], "used": used.get(d["id"], 0), "updated_at": d.get("updated_at"), "updated_by": d.get("updated_by")}
              for d in _models().values()]
    models.sort(key=lambda m: (not m["builtin"], m["label"].lower()))
    clutch = [{"id": k, "kind": "clutch", "builtin": True, "readonly": True, "label": v["label"], "used": used.get(k, 0)} for k, v in tforms.FORM_TYPES.items()]
    return clutch + models


# ---- Édition -------------------------------------------------------------------------------------------------------------------------------

def _slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40] or "x"


def _ids(items: list[dict], old_ids: set[str], taken: set[str]) -> list[dict]:
    """Conserve l'identifiant d'un élément existant ; en donne un neuf aux autres (jamais deux fois le même)."""
    out = []
    for it in items:
        label = str(it.get("label") or it.get("title") or "").strip()
        if not label:
            continue
        iid = str(it.get("id") or "")
        if not (iid in old_ids and iid not in taken):
            base = _slug(label)
            iid = base
            while iid in taken or iid in old_ids:
                iid = f"{base}_{uuid.uuid4().hex[:4]}"
        taken.add(iid)
        out.append({"id": iid, "label": label[:300]})
    return out


def _old_ids(spec: dict, key: str) -> set[str]:
    return {i["id"] for g in spec.get(key, []) for i in g.get("items", g.get("rows", []))}


def validate(kind: str, payload: dict, old: dict) -> dict:
    """Nouvelle spécification : seuls le libellé, la structure et la maintenance proposée au Garage se modifient ; les indicateurs de calcul (pesée, équipage…) viennent du modèle d'origine."""
    spec = copy.deepcopy(old)
    label = str(payload.get("label") or "").strip()
    if not label:
        raise ValueError("Donnez un nom au formulaire")
    spec["label"] = label[:100]
    g = payload.get("garage") or {}
    spec["garage"] = {"fn": g["fn"], "mt": g["mt"]} if g.get("fn") in rides.FUNCTIONS and g.get("mt") in rides.LOGGED else None
    if kind == "checklist":
        spec["requests"] = _ids(payload.get("requests") or [], {r["id"] for r in old.get("requests", [])}, set())[:12]
        secs, taken = [], set()
        old_items = _old_ids(old, "sections")
        for s in (payload.get("sections") or [])[:30]:
            title = str(s.get("title") or "").strip()
            items = _ids(s.get("items") or [], old_items, taken)[:MAX_ITEMS]
            if title and items:
                secs.append({"id": str(s.get("id") or _slug(title)), "title": title[:100], "items": items})
        if not secs:
            raise ValueError("Une liste a besoin d'au moins une section avec un élément")
        ids = [s["id"] for s in secs]
        for i, sid in enumerate(ids):
            if ids.count(sid) > 1:
                secs[i]["id"] = f"{sid}_{i}"
        spec["sections"] = secs
    else:
        groups, taken = [], set()
        old_rows = _old_ids(old, "groups")
        for gr in (payload.get("groups") or [])[:30]:
            title = str(gr.get("title") or "").strip()
            layout = gr.get("layout")
            rows = _ids(gr.get("rows") or [], old_rows, taken)[:MAX_ITEMS]
            if layout not in LAYOUTS:
                raise ValueError("Disposition inconnue : " + str(layout))
            if title and rows:
                groups.append({"id": str(gr.get("id") or _slug(title)), "title": title[:100], "layout": layout, "rows": rows})
        if not groups:
            raise ValueError("Une feuille a besoin d'au moins un groupe avec une ligne")
        if old.get("weighing") and not any(r["id"] == tsheet.WEIGHT_ROW and g["layout"] == "wheel4" for g in groups for r in g["rows"]):
            raise ValueError("La ligne « Poids par roue » (quatre roues) est obligatoire : le calcul de la pesée en dépend")
        gids = [g["id"] for g in groups]
        for i, gid in enumerate(gids):
            if gids.count(gid) > 1:
                groups[i]["id"] = f"{gid}_{i}"
        spec["groups"] = groups
    return spec


def save(mid: str, payload: dict, user: str) -> dict:
    d = coll().get(mid) if mid in _models() else None
    if not d:
        raise LookupError("Modèle introuvable")
    d["spec"] = validate(d["kind"], payload, d["spec"])
    d.update(updated_at=now().isoformat(), updated_by=user.lower())
    coll().put(mid, d)
    invalidate()
    return d


def duplicate(mid: str, label: str, user: str) -> dict:
    src = _models().get(mid)
    if not src:
        raise LookupError("Modèle introuvable")
    label = (label or "").strip() or src["spec"]["label"] + " (copie)"
    if any(m["spec"]["label"].lower() == label.lower() for m in _models().values()):
        raise ValueError("Un formulaire porte déjà ce nom")
    new_id = "m-" + uuid.uuid4().hex[:8]
    spec = copy.deepcopy(src["spec"])
    spec["label"] = label[:100]
    doc = {"id": new_id, "kind": src["kind"], "builtin": False, "spec": spec, "created_at": now().isoformat(), "created_by": user.lower(), "updated_at": now().isoformat(), "updated_by": user.lower()}
    coll().put(new_id, doc)
    invalidate()
    return doc


def delete(mid: str) -> None:
    d = _models().get(mid)
    if not d:
        raise LookupError("Modèle introuvable")
    if d.get("builtin"):
        raise ValueError("Un modèle d'origine ne se supprime pas (modifiez-le ou dupliquez-le)")
    if used_counts().get(mid):
        raise ValueError("Des formulaires remplis utilisent ce modèle : il ne peut pas être supprimé")
    coll().delete(mid)
    invalidate()
