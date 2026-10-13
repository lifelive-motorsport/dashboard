"""État des déclencheurs Cloud Scheduler des rappels de pointage, pour informer le Super User quand ils sont en pause.

Lecture seule via l'API Cloud Scheduler (rôle « Lecteur Cloud Scheduler » du compte de service de l'application). Si l'état ne peut pas être lu, rien n'est affiché."""
from __future__ import annotations

import logging
import threading
import time

from . import settings

log = logging.getLogger("logbook")
_lock = threading.Lock()
_cache: dict = {"t": 0.0, "v": None}
TTL = 300.0
MARK = "/api/cron/timesheet-alerts"


def _list_jobs() -> list[dict]:
    import google.auth
    from google.auth.transport.requests import AuthorizedSession
    creds, project = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    project = settings.SPEECH_PROJECT or project
    r = AuthorizedSession(creds).get(f"https://cloudscheduler.googleapis.com/v1/projects/{project}/locations/{settings.SCHEDULER_LOCATION}/jobs", timeout=20)
    if r.status_code != 200:
        try:
            msg = r.json()["error"]["message"]
        except Exception:
            msg = f"HTTP {r.status_code}"
        raise RuntimeError(msg)
    return r.json().get("jobs", [])


def alerts_status(force: bool = False) -> dict:
    """{state: active | paused | mixed | none | unknown, jobs: [{name, state, schedule}]} ; mis en cache 5 minutes."""
    with _lock:
        if not force and _cache["v"] and time.time() - _cache["t"] < TTL:
            return _cache["v"]
    if settings.PROVIDER == "demo" or not settings.CRON_AUDIENCE:
        v = {"state": "unknown", "jobs": [], "location": settings.SCHEDULER_LOCATION}
    else:
        try:
            jobs = [{"name": j["name"].rsplit("/", 1)[-1], "state": j.get("state", ""), "schedule": j.get("schedule", "")} for j in _list_jobs() if MARK in (j.get("httpTarget") or {}).get("uri", "")]
            states = {j["state"] for j in jobs}
            v = {"state": "none" if not jobs else "active" if states == {"ENABLED"} else "paused" if "ENABLED" not in states else "mixed", "jobs": jobs, "location": settings.SCHEDULER_LOCATION}
        except Exception as e:
            log.warning("État des déclencheurs Cloud Scheduler illisible : %s", e)
            v = {"state": "unknown", "jobs": [], "error": str(e)[:200]}
    with _lock:
        _cache.update(t=time.time(), v=v)
    return v
