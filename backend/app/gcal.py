"""Google Agenda (API calendar v3, lecture seule) : réservations des véhicules, qui sont des ressources invitées aux événements.

Authentification : compte de service du dashboard à inviter en lecture sur les agendas (CALENDAR_IDS). Par usurpation du compte de service
(CALENDAR_SERVICE_ACCOUNT ou GA_SERVICE_ACCOUNT, rôle « Créateur de jetons de compte de service » sur lui-même) : aucune clé n'est stockée."""
from __future__ import annotations

import re
import threading
import time
from datetime import date, datetime, timedelta

from . import settings

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
URL = "https://www.googleapis.com/calendar/v3/calendars/{}/events"
_cache: dict[str, tuple[float, list]] = {}
_lock = threading.Lock()
_session = None


def configured() -> bool:
    return bool(settings.CALENDAR_IDS)


def _authed_session():
    global _session
    if _session is None:
        import google.auth
        from google.auth import impersonated_credentials
        from google.auth.transport.requests import AuthorizedSession, Request
        creds, _ = google.auth.default(scopes=[SCOPE])
        if settings.CALENDAR_SERVICE_ACCOUNT:
            creds = impersonated_credentials.Credentials(source_credentials=creds, target_principal=settings.CALENDAR_SERVICE_ACCOUNT, target_scopes=[SCOPE])
        creds.refresh(Request())
        _session = AuthorizedSession(creds)
    return _session


def _fetch(calendar_id: str, d_from: date, d_to: date) -> list[dict]:
    items: list[dict] = []
    token = None
    while True:
        params = {"singleEvents": "true", "orderBy": "startTime", "maxResults": 2500, "timeMin": f"{d_from.isoformat()}T00:00:00Z", "timeMax": f"{(d_to + timedelta(days=1)).isoformat()}T00:00:00Z"}
        if token:
            params["pageToken"] = token
        r = _authed_session().get(URL.format(calendar_id.replace("@", "%40")), params=params, timeout=30)
        if r.status_code != 200:
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                msg = ""
            raise RuntimeError(f"Google Agenda HTTP {r.status_code} — {msg[:300]}".strip(" —"))
        j = r.json()
        items += j.get("items", [])
        token = j.get("nextPageToken")
        if not token:
            return items


def _day(v: dict | None, end: bool) -> date | None:
    """Jour d'une borne d'événement. Un événement sur la journée entière se termine « exclusivement » le lendemain de son dernier jour."""
    if not v:
        return None
    if "date" in v:
        d = date.fromisoformat(v["date"])
        return d - timedelta(days=1) if end else d
    d = date.fromisoformat(v["dateTime"][:10])
    if end and v["dateTime"][11:16] == "00:00":                     # fin à minuit pile : le dernier jour est la veille
        return d - timedelta(days=1)
    return d


def normalize(items: list[dict], calendar_id: str = "") -> list[dict]:
    """Événements (hors annulés) avec leurs ressources invitées : [{id, title, start, end, calendar, resources}]."""
    pat = re.compile(settings.CALENDAR_VEHICLE_REGEX, re.I) if settings.CALENDAR_VEHICLE_REGEX else None
    out = []
    for e in items:
        if e.get("status") == "cancelled":
            continue
        res = [a.get("displayName") or a.get("email", "") for a in e.get("attendees", []) if a.get("resource") and a.get("responseStatus") != "declined"]
        if pat:
            res = [r for r in res if pat.search(r)]
        s, en = _day(e.get("start"), False), _day(e.get("end"), True)
        if not res or not s:
            continue
        out.append({"id": e.get("id", ""), "title": e.get("summary", "(sans titre)"), "start": s.isoformat(), "end": max(s, en or s).isoformat(), "calendar": calendar_id, "resources": res})
    return out


def events(d_from: date, d_to: date) -> list[dict]:
    key = f"{d_from}|{d_to}|{','.join(settings.CALENDAR_IDS)}"
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
    out: list[dict] = []
    for cid in settings.CALENDAR_IDS:
        out += normalize(_fetch(cid, d_from, d_to), cid)
    out.sort(key=lambda e: e["start"])
    with _lock:
        _cache[key] = (time.time(), out)
    return out


def usage(evs: list[dict], buffer_days: int) -> list[dict]:
    """Par véhicule : nombre de réservations, jours réservés et jours « en déplacement » (réservation élargie de `buffer_days` avant et après)."""
    by: dict[str, dict] = {}
    for e in evs:
        s, en = date.fromisoformat(e["start"]), date.fromisoformat(e["end"])
        for r in e["resources"]:
            v = by.setdefault(r, {"vehicle": r, "events": [], "booked": set(), "away": set()})
            v["events"].append({"title": e["title"], "start": e["start"], "end": e["end"]})
            d = s
            while d <= en:
                v["booked"].add(d)
                d += timedelta(days=1)
            d = s - timedelta(days=buffer_days)
            while d <= en + timedelta(days=buffer_days):
                v["away"].add(d)
                d += timedelta(days=1)
    return [{"vehicle": v["vehicle"], "events": len(v["events"]), "booked_days": len(v["booked"]), "away_days": len(v["away"]), "list": v["events"][-12:]}
            for v in sorted(by.values(), key=lambda x: -len(x["booked"]))]


def demo(d_from: date, d_to: date) -> list[dict]:
    y = d_from.year
    return [{"id": "d1", "title": "Rallye du Portugal", "start": f"{y}-05-10", "end": f"{y}-05-12", "calendar": "demo", "resources": ["Sprinter", "Remorque 1"]},
            {"id": "d2", "title": "Spa Classic", "start": f"{y}-06-20", "end": f"{y}-06-22", "calendar": "demo", "resources": ["Citan"]},
            {"id": "d3", "title": "Ypres Rally", "start": f"{y}-06-24", "end": f"{y}-06-26", "calendar": "demo", "resources": ["Sprinter"]}]
