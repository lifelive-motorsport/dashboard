"""Administrer › Historique des modifications (Super User) : relevé de chaque écriture sur les données sensibles (modèles de jobs, de formulaires et d'architecture, roulages, pièces,
maintenances, fiches voiture, accès clients, jobs…) avec l'état AVANT et APRÈS, pour remettre un objet modifié ou supprimé par erreur dans son état initial.
Branché dans `Coll.put` / `Coll.delete` (timesheets.py) : aucune route n'a à y penser. L'auteur vient d'une variable de contexte posée à chaque requête (`set_actor`, main.py).
Conservation : `HISTORY_DAYS` jours (30 par défaut), purge au fil de l'eau. Les fichiers (photos, PDF) ne sont pas versionnés : seules les fiches le sont.
Une restauration est elle-même enregistrée (donc annulable)."""
from __future__ import annotations

import json
import time
import uuid
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone

from . import settings

# collection -> libellé de l'objet dans le relevé
TRACKED = {"timesheet_templates": "Modèle de job", "timesheet_form_models": "Modèle de formulaire", "ride_templates": "Modèle d'architecture voiture", "ride_sessions": "Roulage",
           "ride_runs": "Participation à un roulage", "ride_circuits": "Circuit", "ride_parts": "Pièce du Garage", "ride_maint": "Maintenance d'une pièce", "ride_cars": "Fiche voiture",
           "clients": "Client", "timesheet_jobs": "Job", "timesheet_garage": "Mise à jour du Garage", "run_reports": "Run report"}
_actor: ContextVar[str] = ContextVar("history_actor", default="")
_muted: ContextVar[bool] = ContextVar("history_muted", default=False)
_coll = None
_last_purge = 0.0
SKIP_KEYS = {"updated_at", "last_login"}    # un changement qui ne touche que ces champs n'est pas une modification
ONLY_CREATE_DELETE = {"timesheet_jobs"}      # un job change à chaque ligne cochée : seuls sa création et sa suppression sont relevées


def days() -> int:
    return max(1, int(getattr(settings, "HISTORY_DAYS", 30) or 30))


class mute:
    """`with history.mute():` — écritures de démarrage (modèles d'origine créés au premier accès) qui ne sont pas des modifications d'un utilisateur."""
    def __enter__(self):
        self._t = _muted.set(True)

    def __exit__(self, *a):
        _muted.reset(self._t)


def set_actor(user: str) -> None:
    _actor.set(user or "")


def coll():
    global _coll
    if _coll is None:
        from .timesheets import Coll
        _coll = Coll("data_history")
    return _coll


def _clean(doc: dict | None) -> dict | None:
    return None if doc is None else json.loads(json.dumps(doc, default=str))


def _same(a: dict | None, b: dict | None) -> bool:
    if a is None or b is None:
        return a is b
    strip = lambda d: {k: v for k, v in d.items() if k not in SKIP_KEYS}
    return strip(a) == strip(b)


def record(name: str, id_: str, before: dict | None, after: dict | None, restored_from: str = "") -> None:
    """Inscrit une écriture ; silencieux en cas d'échec (le journal ne doit jamais empêcher d'enregistrer)."""
    if name not in TRACKED or _muted.get() or _same(_clean(before), _clean(after)) or (name in ONLY_CREATE_DELETE and before is not None and after is not None):
        return
    try:
        b, a = _clean(before), _clean(after)
        hid = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f") + "-" + uuid.uuid4().hex[:4]
        coll().put(hid, {"id": hid, "at": datetime.now(timezone.utc).isoformat(), "by": _actor.get() or "système", "coll": name, "kind": TRACKED[name], "doc_id": id_,
                         "action": "create" if b is None else "delete" if a is None else "update", "label": label_of(a or b or {}, id_), "before": b, "after": a, "restored_from": restored_from})
        _purge()
    except Exception:
        import logging
        logging.getLogger("logbook").exception("Historique des modifications indisponible")


def label_of(doc: dict, fallback: str = "") -> str:
    for k in ("name", "title", "label"):
        if doc.get(k):
            return str(doc[k])[:120]
    if (doc.get("spec") or {}).get("label"):
        return str(doc["spec"]["label"])[:120]
    if doc.get("date"):
        return f"{doc['date']} · {doc.get('name') or doc.get('type') or ''}".strip(" ·")[:120]
    return fallback


def _purge() -> None:
    global _last_purge
    if time.time() - _last_purge < 3600:
        return
    _last_purge = time.time()
    limit = (datetime.now(timezone.utc) - timedelta(days=days())).isoformat()
    for h in coll().all():
        if h["at"] < limit:
            coll().delete(h["id"])


def changed_fields(h: dict) -> list[str]:
    b, a = h.get("before") or {}, h.get("after") or {}
    return sorted(k for k in set(b) | set(a) if k not in SKIP_KEYS and b.get(k) != a.get(k))


def list_entries(since_days: int = 7, kind: str = "", by: str = "", q: str = "", limit: int = 300) -> list[dict]:
    limit_at = (datetime.now(timezone.utc) - timedelta(days=min(since_days, days()))).isoformat()
    qq = q.strip().lower()
    out = []
    for h in sorted(coll().all(), key=lambda h: h["id"], reverse=True):
        if h["at"] < limit_at or (kind and h["coll"] != kind) or (by and h["by"].lower() != by.lower()) or (qq and qq not in (h["label"] + " " + h["kind"] + " " + h["by"]).lower()):
            continue
        out.append({k: h[k] for k in ("id", "at", "by", "coll", "kind", "doc_id", "action", "label", "restored_from")} | {"fields": changed_fields(h)})
        if len(out) >= limit:
            break
    return out


def detail(hid: str) -> dict:
    h = coll().get(hid)
    if not h:
        raise LookupError("Entrée introuvable")
    from .timesheets import Coll  # noqa: F401
    cur = collection(h["coll"]).get(h["doc_id"])
    return {**h, "fields": changed_fields(h), "current": _clean(cur), "stale": not _same(_clean(cur), h.get("after"))}


# Accès à la collection réelle d'un nom suivi (pour restaurer) : chaque module garde sa propre instance
def collection(name: str):
    from . import clients, rides, tgarage, timesheets, tmodels
    return {"timesheet_templates": timesheets.templates, "timesheet_form_models": tmodels.coll, "ride_templates": rides.templates_coll,
            "ride_sessions": rides.sessions_coll, "ride_runs": rides.runs_coll, "ride_circuits": rides.circuits_coll, "ride_parts": rides.parts_coll, "ride_maint": rides.maint_coll,
            "ride_cars": rides.cars_coll, "clients": clients.clients_coll, "timesheet_jobs": timesheets.jobs, "timesheet_garage": tgarage.coll}[name]()


def restore(hid: str, user: str) -> dict:
    """Remet l'objet dans son état AVANT la modification (recrée s'il a été supprimé, supprime s'il a été créé). Enregistré à son tour dans l'historique."""
    h = coll().get(hid)
    if not h:
        raise LookupError("Entrée introuvable")
    c = collection(h["coll"])
    cur = c.get(h["doc_id"])
    set_actor(user)
    if h["before"] is None:
        c.delete(h["doc_id"])
        record(h["coll"], h["doc_id"], cur, None, restored_from=hid)
        _invalidate(h["coll"])
        return {"restored": "deleted"}
    c.put(h["doc_id"], h["before"])
    record(h["coll"], h["doc_id"], cur, h["before"], restored_from=hid)
    _invalidate(h["coll"])
    return {"restored": "updated" if cur else "recreated"}


def _invalidate(name: str) -> None:
    """Caches en mémoire à vider après une restauration."""
    if name == "timesheet_form_models":
        from . import tmodels
        tmodels.invalidate()
