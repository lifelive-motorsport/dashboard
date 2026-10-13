"""Présence à l'atelier : jours ouvrés, jours fériés belges, absences connues (événements du planning, congés) et pointages manquants.

Un mécanicien « doit » pointer un jour ouvré de sa fiche (work_days, lundi à vendredi par défaut), hors jours fériés, hors congé approuvé et hors événement où il est invité. Le pointage du
jour est attendu à partir de 17 h (15 h le vendredi) ; avant, le jour n'est pas encore « dû »."""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

log = logging.getLogger("logbook")
TZ = ZoneInfo("Europe/Brussels")
DEFAULT_DAYS = [0, 1, 2, 3, 4]


def local_now() -> datetime:
    return datetime.now(TZ)


def cutoff(d: date) -> time:
    return time(15, 0) if d.weekday() == 4 else time(17, 0)


def easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = b // 4, b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = c // 4, c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mo, da = divmod(h + l - 7 * m + 114, 31)
    return date(y, mo, da + 1)


def holidays_be(y: int) -> dict[date, str]:
    e = easter(y)
    return {date(y, 1, 1): "Nouvel An", e + timedelta(days=1): "Lundi de Pâques", date(y, 5, 1): "Fête du Travail", e + timedelta(days=39): "Ascension", e + timedelta(days=50): "Lundi de Pentecôte",
            date(y, 7, 21): "Fête nationale", date(y, 8, 15): "Assomption", date(y, 11, 1): "Toussaint", date(y, 11, 11): "Armistice", date(y, 12, 25): "Noël"}


def is_workday(d: date, person: dict | None) -> bool:
    days = (person or {}).get("work_days") or DEFAULT_DAYS
    return d.weekday() in days and d not in holidays_be(d.year)


def event_absences(emails: set[str], d_from: date, d_to: date) -> dict[str, dict[date, str]]:
    """Jours passés sur un événement (invitation dans les agendas Google des BU) : {adresse: {jour: titre}}. Calendrier indisponible : aucune absence connue."""
    out: dict[str, dict[date, str]] = {}
    try:
        from . import planning
        for ev in planning.listing(d_from, d_to):
            a, b = date.fromisoformat(ev["start"]), date.fromisoformat(ev["end"])
            for em in ev["staff_and_external"]:
                em = em.lower()
                if em in emails:
                    d = a
                    while d <= b:
                        out.setdefault(em, {})[d] = ev["title"]
                        d += timedelta(days=1)
    except Exception:
        log.exception("Événements du planning indisponibles pour les alertes de pointage")
    return out


def leave_absences(emails: set[str], d_from: date, d_to: date) -> dict[str, dict[date, str]]:
    try:
        from . import leaves
        return leaves.absences(emails, d_from, d_to)
    except ImportError:
        return {}


def excused(emails: set[str], d_from: date, d_to: date) -> dict[str, dict[date, str]]:
    out = event_absences(emails, d_from, d_to)
    for em, days in leave_absences(emails, d_from, d_to).items():
        out.setdefault(em, {}).update(days)
    return out


def due_days(person: dict | None, d_from: date, d_to: date, now: datetime | None = None) -> list[date]:
    """Jours à pointer dans [d_from, d_to] : ouvrés, passés (ou d'aujourd'hui une fois l'heure limite atteinte)."""
    now = now or local_now()
    out, d = [], d_from
    while d <= min(d_to, now.date()):
        if is_workday(d, person) and (d < now.date() or now.time() >= cutoff(d)):
            out.append(d)
        d += timedelta(days=1)
    return out


def missing(people: list[dict], entries_by_user: dict[str, set[str]], d_from: date, d_to: date, now: datetime | None = None) -> dict[str, list[date]]:
    """{adresse du mécanicien: jours dus sans aucun pointage, ni absence connue}."""
    emails = {p["google_email"].lower() for p in people if p.get("google_email")}
    exc = excused(emails, d_from, d_to) if emails else {}
    out: dict[str, list[date]] = {}
    for p in people:
        em = (p.get("google_email") or "").lower()
        if not em:
            continue
        done = entries_by_user.get(em, set())
        out[em] = [d for d in due_days(p, d_from, d_to, now) if d.isoformat() not in done and d not in exc.get(em, {})]
    return out
