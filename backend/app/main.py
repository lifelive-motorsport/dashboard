from __future__ import annotations

import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from . import adjustments, settings
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


def _year_back(d: date) -> date:
    """Même jour un an plus tôt (le 29 février devient le 28)."""
    try:
        return d.replace(year=d.year - 1)
    except ValueError:
        return d.replace(year=d.year - 1, day=28)


def _safe(fn, *a):
    """Un bloc secondaire (clients, fournisseurs, webshops) qui échoue ne doit pas empêcher d'afficher le reste."""
    try:
        return fn(*a)
    except (NotImplementedError, LookupError) as e:        # messages écrits pour l'utilisateur
        return {"unavailable": str(e)}
    except Exception:
        log.exception("Bloc indisponible : %s", getattr(fn, "__name__", fn))
        return {"unavailable": "Données momentanément indisponibles (voir les journaux du service)."}


@app.middleware("http")
async def security_headers(request, call_next):
    resp = await call_next(request)
    resp.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "same-origin",
                         "X-Frame-Options": "DENY"})
    if request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.get("/api/health")
def healthz():
    return {"ok": True}


@app.get("/api/config")
def config():
    return {"auth": settings.AUTH_ENABLED, "google_client_id": settings.GOOGLE_CLIENT_ID,
            "source": settings.PROVIDER}


@app.get("/api/adjustments")
def get_adjustments(user: str = Depends(require_user)):
    try:
        doc = adjustments.store().get()
    except Exception:
        log.exception("Lecture des ajustements impossible")
        return {"items": [], "updated_at": None, "updated_by": None, "can_edit": adjustments.can_edit(user),
                "error": "Ajustements indisponibles (stockage non configuré ou inaccessible)."}
    return {**doc, "can_edit": adjustments.can_edit(user)}


@app.put("/api/adjustments")
def put_adjustments(payload: adjustments.Payload, user: str = Depends(require_user)):
    if not adjustments.can_edit(user):
        raise HTTPException(403, "Modification réservée aux administrateurs du dashboard")
    ids = [i.id for i in payload.items]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Identifiants d'ajustement en double")
    try:
        doc = adjustments.store().put([i.model_dump() for i in payload.items], user)
    except Exception:
        log.exception("Enregistrement des ajustements impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    return {**doc, "can_edit": True}


def _prev_pnl(p, d_from: date, d_to: date) -> dict | None:
    """P&L de la même période un an plus tôt (None si indisponible : la comparaison est un plus)."""
    pf, pt = _year_back(d_from), _year_back(d_to)
    try:
        pnl = aggregate(p.pnl_balances(pf, pt))
        old = float(p.old_plan_revenue(pf, pt))            # l'ancien plan comptable (comptes « OLD ») portait le CA de 2025
        pnl["total"]["ca"] += old
        return {**pnl, "old_plan_ca": old, "period": {"from": pf.isoformat(), "to": pt.isoformat()}}
    except Exception:
        log.exception("P&L de l'année précédente indisponible")
        return None


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
            "pnl_prev": _prev_pnl(p, d_from, d_to),
            "balance_sheet": p.balance_sheet(d_to.year),
            "top_clients": _safe(p.top_clients, d_from, d_to),
            "top_suppliers": _safe(p.top_suppliers, d_from, d_to),
            "events": _safe(p.events, d_from, d_to),
            "vehicles": _safe(p.vehicles, d_from, d_to),
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
