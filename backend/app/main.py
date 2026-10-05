from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import settings
from .auth import require_user
from .bu import aggregate
from .providers.demo import DemoProvider

log = logging.getLogger("dashboard")
app = FastAPI(title="Lifelive Motorsport — Dashboard")
_provider = None
_cache: dict[tuple, tuple[float, dict]] = {}


def provider():
    global _provider
    if _provider is None:
        if settings.PROVIDER == "odoo":
            from .providers.odoo import OdooProvider
            _provider = OdooProvider()
        else:
            _provider = DemoProvider()
    return _provider


def _safe(fn, *a):
    try:
        return fn(*a)
    except NotImplementedError as e:
        return {"unavailable": str(e)}


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin",
                         "X-Frame-Options": "DENY"})
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.get("/api/config")
def config():
    return {"auth": settings.AUTH_ENABLED, "google_client_id": settings.GOOGLE_CLIENT_ID,
            "source": settings.PROVIDER}


@app.get("/api/dashboard")
def dashboard(date_from: date | None = Query(None, alias="from"), date_to: date | None = Query(None, alias="to"),
              refresh: bool = False, _user: str = Depends(require_user)):
    today = date.today()
    d_from, d_to = date_from or date(today.year, 1, 1), date_to or today
    key = (d_from, d_to)
    hit = _cache.get(key)
    age = time.time() - hit[0] if hit else None
    # « refresh » est limité à 1 appel / 30 s par période pour ne pas surcharger Odoo
    if hit and age < (30 if refresh else settings.CACHE_TTL):
        return hit[1]
    try:
        p = provider()
        result = {
            "source": p.name, "period": {"from": d_from.isoformat(), "to": d_to.isoformat()},
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "pnl": aggregate(p.pnl_balances(d_from, d_to)),
            "balance_sheet": p.balance_sheet(),
            "top_clients": _safe(p.top_clients, d_from, d_to),
            "webshops": _safe(p.webshops, d_from, d_to),
        }
    except Exception as e:  # le détail va dans les journaux, jamais vers le navigateur
        log.exception("Échec de la lecture de la source de données")
        if hit:  # dernières données connues plutôt qu'une page vide
            return hit[1]
        raise HTTPException(502, f"Source de données indisponible ({type(e).__name__})")
    _cache[key] = (time.time(), result)
    return result


FRONTEND = Path(__file__).resolve().parents[2] / "frontend"
if FRONTEND.is_dir():
    app.mount("/static", StaticFiles(directory=FRONTEND), name="static")

    @app.get("/")
    def index():
        return FileResponse(FRONTEND / "index.html")

    @app.get("/{name:path}")
    def assets(name: str):
        f = (FRONTEND / name).resolve()
        if FRONTEND in f.parents and f.is_file():
            return FileResponse(f)
        return FileResponse(FRONTEND / "index.html")
