"""Google Analytics 4 (API de données, lecture seule) : trafic des webshops XC et Goldspeed et du site vitrine.

Authentification : compte de service du dashboard (Cloud Run), à ajouter comme « Lecteur » dans Google Analytics. Sur Cloud Run, le jeton par
défaut n'a pas la portée analytics.readonly : si GA_SERVICE_ACCOUNT est renseigné, on s'identifie par usurpation du compte de service
(rôle « Créateur de jetons de compte de service » sur lui-même). Aucune clé n'est stockée."""
from __future__ import annotations

import json
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta

from . import settings

SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
URL = "https://analyticsdata.googleapis.com/v1beta/properties/{}:runReport"
_cache: dict[str, tuple[float, dict]] = {}
_lock = threading.Lock()
_session = None


def configured() -> bool:
    return bool(settings.GA_PROPERTY_ID or settings.GA_PROPERTY_XC or settings.GA_PROPERTY_GS or settings.GA_PROPERTY_SITE)


def sites() -> dict[str, dict]:
    """Sites suivis : propriété (numérique), nom d'hôte et chemin. Un seul identifiant de propriété suffit si les sites partagent la propriété."""
    s = settings
    return {
        "xc": {"property": s.GA_PROPERTY_XC or s.GA_PROPERTY_ID, "host": s.GA_HOST_XC, "path": s.GA_SHOP_PATH},
        "gs": {"property": s.GA_PROPERTY_GS or s.GA_PROPERTY_ID, "host": s.GA_HOST_GS, "path": s.GA_SHOP_PATH},
        "site": {"property": s.GA_PROPERTY_SITE or s.GA_PROPERTY_ID, "host": s.GA_HOST_SITE or s.GA_HOST_XC, "path": ""},
    }


def _authed_session():
    global _session
    if _session is None:
        import google.auth
        from google.auth import impersonated_credentials
        from google.auth.transport.requests import AuthorizedSession, Request
        creds, _ = google.auth.default(scopes=[SCOPE])
        if settings.GA_SERVICE_ACCOUNT:
            creds = impersonated_credentials.Credentials(source_credentials=creds, target_principal=settings.GA_SERVICE_ACCOUNT, target_scopes=[SCOPE])
        creds.refresh(Request())
        _session = AuthorizedSession(creds)
    return _session


def _post(prop: str, body: dict) -> dict:
    """Appel brut à l'API ; une erreur renvoie un message court (jamais de jeton)."""
    r = _authed_session().post(URL.format(prop), json=body, timeout=30)
    if r.status_code != 200:
        try:
            msg = r.json().get("error", {}).get("message", "")
        except ValueError:
            msg = ""
        raise RuntimeError(f"Google Analytics HTTP {r.status_code} — {msg[:300]}".strip(" —"))
    return r.json()


def run(prop: str, body: dict) -> dict:
    key = prop + json.dumps(body, sort_keys=True)
    with _lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < 600:
            return hit[1]
    out = _post(prop, body)
    with _lock:
        _cache[key] = (time.time(), out)
    return out


def _filter(host: str, path: str) -> dict | None:
    ex = []
    if host:
        ex.append({"filter": {"fieldName": "hostName", "stringFilter": {"matchType": "EXACT", "value": host}}})
    if path:
        ex.append({"filter": {"fieldName": "pagePath", "stringFilter": {"matchType": "CONTAINS", "value": path}}})
    return {"andGroup": {"expressions": ex}} if ex else None


def _rows(resp: dict) -> list[tuple[list[str], list[float]]]:
    return [([d["value"] for d in r.get("dimensionValues", [])], [float(m["value"] or 0) for m in r.get("metricValues", [])])
            for r in resp.get("rows", [])]


def _body(d_from: date, d_to: date, metrics: list[str], dims: list[str], flt: dict | None, **extra) -> dict:
    b = {"dateRanges": [{"startDate": d_from.isoformat(), "endDate": d_to.isoformat()}], "metrics": [{"name": m} for m in metrics],
         "dimensions": [{"name": d} for d in dims], **extra}
    if flt:
        b["dimensionFilter"] = flt
    return b


TOTAL_METRICS = ["sessions", "totalUsers", "newUsers", "screenPageViews", "engagementRate", "averageSessionDuration",
                 "addToCarts", "checkouts", "ecommercePurchases"]


def _prev_range(d_from: date, d_to: date) -> tuple[date, date]:
    def back(d: date) -> date:
        try:
            return d.replace(year=d.year - 1)
        except ValueError:
            return d.replace(year=d.year - 1, day=28)
    return back(d_from), back(d_to)


def _totals(prop: str, flt, d_from: date, d_to: date) -> dict:
    pf, pt = _prev_range(d_from, d_to)
    body = _body(d_from, d_to, TOTAL_METRICS, [], flt)
    body["dateRanges"].append({"startDate": pf.isoformat(), "endDate": pt.isoformat()})
    resp = run(prop, body)
    cur, prev = {}, {}
    for dims, vals in _rows(resp):          # sans dimension, GA ajoute « dateRange » ; une ligne par plage
        target = prev if dims and dims[0].endswith("1") else cur
        target.update(dict(zip(TOTAL_METRICS, vals)))
    if not resp.get("rows") or not any(cur.values()):
        cur = cur or dict.fromkeys(TOTAL_METRICS, 0.0)
    return {"current": cur, "previous": prev, "previous_period": {"from": pf.isoformat(), "to": pt.isoformat()}}


def _series(prop: str, flt, d_from: date, d_to: date) -> dict:
    from .providers.odoo import OdooProvider
    gran, buckets = OdooProvider._buckets(d_from, d_to)
    dim = "isoYearIsoWeek" if gran == "week" else "yearMonth"
    resp = run(prop, _body(d_from, d_to, ["sessions", "totalUsers", "screenPageViews", "ecommercePurchases"], [dim], flt, limit=200))
    by: dict[date, list[float]] = {}
    for dims, vals in _rows(resp):
        k = dims[0]
        try:
            start = date.fromisocalendar(int(k[:4]), int(k[4:]), 1) if gran == "week" else date(int(k[:4]), int(k[4:6]), 1)
        except ValueError:
            continue
        a = by.setdefault(start, [0.0] * 4)
        for i, v in enumerate(vals):
            a[i] += v
    pts = []
    for st, lbl in buckets:
        a = by.get(st, [0.0] * 4)
        pts.append({"label": lbl, "sessions": round(a[0]), "users": round(a[1]), "views": round(a[2]), "purchases": round(a[3])})
    return {"granularity": gran, "points": pts}


def _channels(prop: str, flt, d_from: date, d_to: date) -> list[dict]:
    resp = run(prop, _body(d_from, d_to, ["sessions", "totalUsers", "ecommercePurchases"], ["sessionDefaultChannelGroup"], flt,
                           orderBys=[{"metric": {"metricName": "sessions"}, "desc": True}], limit=12))
    tot = sum(v[0] for _, v in _rows(resp)) or 1.0
    return [{"name": d[0] or "(non attribué)", "sessions": round(v[0]), "users": round(v[1]), "purchases": round(v[2]), "share": v[0] / tot} for d, v in _rows(resp)]


def _pages(prop: str, flt, d_from: date, d_to: date, top: int = 15) -> list[dict]:
    resp = run(prop, _body(d_from, d_to, ["screenPageViews", "totalUsers"], ["pagePath", "pageTitle"], flt,
                           orderBys=[{"metric": {"metricName": "screenPageViews"}, "desc": True}], limit=top))
    rows = _rows(resp)
    tot = sum(v[0] for _, v in rows) or 1.0
    return [{"path": d[0], "title": d[1] if d[1] not in ("(not set)", "") else d[0], "views": round(v[0]), "users": round(v[1]), "share": v[0] / tot} for d, v in rows]


def _countries(prop: str, flt, d_from: date, d_to: date) -> list[dict]:
    resp = run(prop, _body(d_from, d_to, ["sessions"], ["country"], flt, orderBys=[{"metric": {"metricName": "sessions"}, "desc": True}], limit=8))
    tot = sum(v[0] for _, v in _rows(resp)) or 1.0
    return [{"name": d[0], "sessions": round(v[0]), "share": v[0] / tot} for d, v in _rows(resp)]


def _devices(prop: str, flt, d_from: date, d_to: date) -> list[dict]:
    resp = run(prop, _body(d_from, d_to, ["sessions"], ["deviceCategory"], flt, orderBys=[{"metric": {"metricName": "sessions"}, "desc": True}], limit=5))
    tot = sum(v[0] for _, v in _rows(resp)) or 1.0
    return [{"name": d[0], "sessions": round(v[0]), "share": v[0] / tot} for d, v in _rows(resp)]


def _hosts(prop: str, d_from: date, d_to: date) -> list[dict]:
    """Noms de domaine vus par la propriété (diagnostic quand un site n'a aucune session : nom d'hôte mal renseigné)."""
    resp = run(prop, _body(d_from, d_to, ["sessions"], ["hostName"], None, orderBys=[{"metric": {"metricName": "sessions"}, "desc": True}], limit=6))
    return [{"name": d[0], "sessions": round(v[0])} for d, v in _rows(resp)]


def site_report(key: str, d_from: date, d_to: date) -> dict:
    cfg = sites()[key]
    if not cfg["property"]:
        return {"error": "Propriété Google Analytics non renseignée."}
    prop, flt = cfg["property"], _filter(cfg["host"], cfg["path"])
    jobs = {"totals": _totals, "series": _series, "channels": _channels, "pages": _pages, "countries": _countries, "devices": _devices}
    out: dict = {"host": cfg["host"], "path": cfg["path"]}
    errors: dict[str, str] = {}

    def one(name):
        try:
            return name, jobs[name](prop, flt, d_from, d_to)
        except Exception as e:
            return name, RuntimeError(str(e)[:400])
    with ThreadPoolExecutor(max_workers=6) as pool:
        for name, res in pool.map(one, jobs):
            if isinstance(res, RuntimeError):
                errors[name] = str(res)
            else:
                out[name] = res
    if errors:
        out["errors"] = errors
    if "totals" in out and not out["totals"]["current"].get("sessions"):
        try:
            out["hosts"] = _hosts(prop, d_from, d_to)
        except Exception:
            pass
    return out


def report(d_from: date, d_to: date) -> dict:
    """Trafic des trois sites pour la période : {xc, gs, site} ; une erreur n'affecte que le site concerné."""
    if not configured():
        return {"unconfigured": True}
    out = {}
    for key in sites():
        try:
            out[key] = site_report(key, d_from, d_to)
        except Exception as e:
            out[key] = {"error": str(e)[:400]}
    return out


def demo(d_from: date, d_to: date) -> dict:
    """Données fictives (mode démo)."""
    from .providers.odoo import OdooProvider
    gran, buckets = OdooProvider._buckets(d_from, d_to)

    def site(scale: float, shop: bool) -> dict:
        pts = [{"label": lbl, "sessions": round(scale * (900 + 80 * ((i * 5) % 7))), "users": round(scale * (640 + 50 * ((i * 3) % 6))),
                "views": round(scale * (2600 + 150 * ((i * 4) % 5))), "purchases": round(scale * (14 + (i * 3) % 6)) if shop else 0} for i, (_, lbl) in enumerate(buckets)]
        cur = {"sessions": sum(p["sessions"] for p in pts), "totalUsers": sum(p["users"] for p in pts), "newUsers": round(sum(p["users"] for p in pts) * .7),
               "screenPageViews": sum(p["views"] for p in pts), "engagementRate": 0.62, "averageSessionDuration": 94.0,
               "addToCarts": round(scale * 400) if shop else 0, "checkouts": round(scale * 210) if shop else 0, "ecommercePurchases": sum(p["purchases"] for p in pts)}
        prev = {k: v * 0.9 for k, v in cur.items()}
        ch = [("Organic Search", .46), ("Direct", .24), ("Referral", .12), ("Organic Social", .1), ("Email", .05), ("Paid Search", .03)]
        return {"host": "www.exemple.com", "path": "/shop" if shop else "", "totals": {"current": cur, "previous": prev, "previous_period": {"from": d_from.isoformat(), "to": d_to.isoformat()}},
                "series": {"granularity": gran, "points": pts},
                "channels": [{"name": n, "sessions": round(cur["sessions"] * s), "users": round(cur["totalUsers"] * s), "purchases": round(cur["ecommercePurchases"] * s), "share": s} for n, s in ch],
                "pages": [{"path": f"/shop/produit-{i}", "title": f"Produit exemple {i}", "views": 1500 // i, "users": 900 // i, "share": (1500 // i) / 4000} for i in range(1, 16)],
                "countries": [{"name": n, "sessions": round(cur["sessions"] * s), "share": s} for n, s in (("Belgium", .4), ("France", .25), ("Germany", .15), ("Netherlands", .1))],
                "devices": [{"name": n, "sessions": round(cur["sessions"] * s), "share": s} for n, s in (("mobile", .58), ("desktop", .38), ("tablet", .04))]}
    return {"xc": site(1.0, True), "gs": site(0.2, True), "site": site(1.6, False)}
