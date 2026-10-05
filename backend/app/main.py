from __future__ import annotations

import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import settings
from .auth import require_user
from .bu import aggregate
from .providers.demo import DemoProvider

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
    if hit and not refresh and time.time() - hit[0] < settings.CACHE_TTL:
        return hit[1]
    p = provider()
    result = {
        "source": p.name, "period": {"from": d_from.isoformat(), "to": d_to.isoformat()},
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pnl": aggregate(p.pnl_balances(d_from, d_to)),
        "balance_sheet": p.balance_sheet(),
        "top_clients": _safe(p.top_clients, d_from, d_to),
        "webshops": _safe(p.webshops, d_from, d_to),
    }
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
