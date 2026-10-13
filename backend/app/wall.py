"""Écran mural de l'atelier (Piloter › Cockpit) : instantané en lecture seule, sans aucun montant financier.

Jobs ouverts (avec heures de la semaine et personnes qui ont pointé aujourd'hui), présence du jour (cockpit des pointages) et indicateurs globaux de la semaine.
Le planning des événements vient de GET /api/planning (même source, mêmes règles de BU)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import timesheets


def _bu_group(bu: str) -> str:
    return "XC" if bu == "XC" else "CARS" if bu != "ALL" else "ALL"


def snapshot(now: datetime | None = None) -> dict:
    from . import presence
    now = now or presence.local_now()
    today = now.date()
    mon = timesheets.monday(today)
    jobs = {j["id"]: j for j in timesheets.jobs().all()}
    week = timesheets.entries().between("date", mon.isoformat(), today.isoformat())
    by_job: dict[str, dict] = {}
    from . import staff, users
    names = {p["google_email"].lower(): p["name"] for p in staff.store().get()["data"]["people"] if p.get("google_email")}
    total = billable = 0
    for e in week:
        j = jobs.get(e["job_id"])
        m = e.get("minutes", 0)
        total += m
        if j and timesheets.billable(j):
            billable += m
        d = by_job.setdefault(e["job_id"], {"minutes": 0, "today": set(), "last": ""})
        d["minutes"] += m
        d["last"] = max(d["last"], e["date"])
        if e["date"] == today.isoformat():
            d["today"].add(names.get(e["user"]) or users.identity(e["user"])["name"])
    open_jobs = []
    for j in jobs.values():
        if not j.get("open", True) or j.get("kind") == "background":
            continue
        d = by_job.get(j["id"], {"minutes": 0, "today": set(), "last": ""})
        open_jobs.append({"id": j["id"], "title": j["title"], "kind": j["kind"], "bu": j.get("bu", "CARS"), "group": _bu_group(j.get("bu", "CARS")),
                          "vehicle": (j.get("vehicle") or {}).get("name", ""), "event": (j.get("event") or {}).get("title", ""),
                          "progress": timesheets.progress(j), "minutes_week": d["minutes"], "today": sorted(d["today"]), "last": d["last"]})
    open_jobs.sort(key=lambda x: (not x["today"], -x["minutes_week"], x["title"].lower()))
    closed_week = sum(1 for j in jobs.values() if j.get("closed_at") and j["closed_at"][:10] >= mon.isoformat())
    ck = timesheets.cockpit(now)
    rows = [{"name": r["name"], "alloc": r["alloc"], "all_bus": r["all_bus"], "workshop": r["workshop"], "state": r["state"], "reason": r["reason"], "minutes": r["minutes"]} for r in ck["rows"]]
    expected = [r for r in rows if r["state"] not in ("absent", "off")]
    return {"now": now.isoformat(timespec="minutes"), "date": today.isoformat(), "week_from": mon.isoformat(),
            "indicators": {"jobs_open": len(open_jobs), "jobs_closed_week": closed_week, "hours_week": round(total / 60, 1), "billable_pct": round(100 * billable / total) if total else None,
                           "present": sum(1 for r in expected if r["state"] == "done"), "expected": len(expected), "absent": sum(1 for r in rows if r["state"] == "absent")},
            "jobs": open_jobs, "people": rows}
