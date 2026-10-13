"""Écran mural de l'atelier (Piloter › Cockpit) : instantané en lecture seule, sans aucun montant financier.

Jobs ouverts (avec heures de la semaine et personnes qui ont pointé aujourd'hui), présence du jour (cockpit des pointages) et indicateurs globaux de la semaine.
Le planning des événements vient de GET /api/planning (même source, mêmes règles de BU)."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from . import timesheets


def _bu_group(bu: str) -> str:
    return "XC" if bu == "XC" else "CARS" if bu != "ALL" else "ALL"


CARS_KEYS = ("MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING", "CARS_OTHERS", "CARS")


VIEWS = ("all", "xc", "cars")


def _job_in(group: str, view: str) -> bool:
    return view == "all" or group == "ALL" or (group == "XC") == (view == "xc")      # même règle que le filtre d'écran : les jobs « ALL » comptent partout


def _person_in(p: dict, view: str) -> bool:
    a = p.get("alloc") or {}
    return view == "all" or bool(p.get("all_bus")) or (a.get("XC", 0) > 0 if view == "xc" else any(a.get(k, 0) > 0 for k in CARS_KEYS))


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
    mins = {v: [0, 0] for v in VIEWS}          # vue -> [minutes, dont facturables]
    for e in week:
        j = jobs.get(e["job_id"])
        m = e.get("minutes", 0)
        for v in VIEWS:
            if j and _job_in(_bu_group(j.get("bu", "CARS")), v):
                mins[v][0] += m
                if timesheets.billable(j):
                    mins[v][1] += m
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
    closed = [j for j in jobs.values() if j.get("closed_at") and j["closed_at"][:10] >= mon.isoformat()]
    ck = timesheets.cockpit(now)
    rows = [{"name": r["name"], "alloc": r["alloc"], "all_bus": r["all_bus"], "workshop": r["workshop"], "state": r["state"], "reason": r["reason"], "minutes": r["minutes"]} for r in ck["rows"]]
    ind = {}
    for v in VIEWS:
        mine = [r for r in rows if _person_in(r, v)]
        expected = [r for r in mine if r["state"] not in ("absent", "off")]
        tot, bil = mins[v]
        ind[v] = {"jobs_open": sum(1 for j in open_jobs if _job_in(j["group"], v)), "jobs_closed_week": sum(1 for j in closed if _job_in(_bu_group(j.get("bu", "CARS")), v)),
                  "hours_week": round(tot / 60, 1), "billable_pct": round(100 * bil / tot) if tot else None,
                  "present": sum(1 for r in expected if r["state"] == "done"), "expected": len(expected), "absent": sum(1 for r in mine if r["state"] == "absent")}
    return {"now": now.isoformat(timespec="minutes"), "date": today.isoformat(), "week_from": mon.isoformat(), "indicators": ind,
            "jobs": open_jobs, "people": rows}
