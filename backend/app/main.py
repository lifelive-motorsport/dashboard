from __future__ import annotations

import re
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, Response as RawResponse
from fastapi.staticfiles import StaticFiles

from . import adjustments, ga, settings, staff
from .auth import COOKIE, require_user, set_session_cookie, verify_google
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
    link = settings.ODOO_ANALYTIC_LINK.replace("{base}", settings.ODOO_PUBLIC_URL.rstrip("/")) if settings.PROVIDER == "odoo" and settings.ODOO_PUBLIC_URL else ""
    return {"auth": settings.AUTH_ENABLED, "google_client_id": settings.GOOGLE_CLIENT_ID,
            "source": settings.PROVIDER, "analytic_link": link,
            "ga": ga.configured() or settings.PROVIDER == "demo",
            "hosts": {"xc": settings.GA_HOST_XC, "gs": settings.GA_HOST_GS, "site": settings.GA_HOST_SITE or settings.GA_HOST_XC}}


@app.post("/api/session")
def open_session(request: Request, response: Response, authorization: str | None = Header(default=None)):
    """Échange le jeton Google (≈ 1 h) contre un cookie de session du dashboard (SESSION_DAYS jours, glissant)."""
    email = verify_google(authorization)
    if not settings.SESSION_SECRET:
        return {"email": email, "session": False}            # non configuré : on reste sur le jeton Google
    set_session_cookie(response, request, email)
    return {"email": email, "session": True}


@app.get("/api/session")
def current_session(user: str = Depends(require_user)):
    return {"email": user, "session": True}


@app.delete("/api/session")
def close_session(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"session": False}


@app.get("/api/tags")
def tags(_user: str = Depends(require_user)):
    """Étiquettes Odoo utilisées par le dashboard et leur présence (page Settings › Tags Odoo)."""
    try:
        return provider().tags_overview()
    except Exception:
        log.exception("Étiquettes indisponibles")
        return {"tags": [], "unavailable": "Liste des étiquettes momentanément indisponible."}


_stock_cache: dict[str, tuple[float, dict]] = {}


@app.get("/api/stock")
def stock(refresh: bool = False, _user: str = Depends(require_user)):
    """Valorisation du stock XC (indépendante de la période) ; mise en cache 10 min."""
    hit = _stock_cache.get("s")
    if hit and time.time() - hit[0] < (30 if refresh else 600):
        return hit[1]
    try:
        data = {**provider().stock_report(), "as_of": date.today().isoformat(), "source": provider().name}
    except (NotImplementedError, LookupError) as e:
        return {"unavailable": str(e)}
    except Exception:
        log.exception("Stock indisponible")
        if hit:
            return hit[1]
        raise HTTPException(502, "Stock momentanément indisponible")
    _stock_cache["s"] = (time.time(), data)
    return data


def admin(user: str = Depends(require_user)) -> str:
    """Données du personnel : réservées aux administrateurs (ADMIN_EMAILS)."""
    if not adjustments.can_edit(user):
        raise HTTPException(403, "Réservé aux administrateurs du dashboard")
    return user


@app.get("/api/staff")
def get_staff(user: str = Depends(require_user)):
    if not adjustments.can_edit(user):
        return {"restricted": True, "can_edit": False}
    try:
        doc = staff.store().get()
    except Exception:
        log.exception("Lecture des données du personnel impossible")
        raise HTTPException(503, "Stockage des données du personnel inaccessible")
    return {**doc, "can_edit": True, "upload": staff.files().enabled, "pay_prefixes": settings.STAFF_PAY_PREFIXES}


@app.put("/api/staff")
def put_staff(body: staff.SaveBody, user: str = Depends(admin)):
    try:
        doc = staff.store().put(body.data.model_dump(), user, body.base)
    except Exception:
        log.exception("Enregistrement des données du personnel impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    return {**doc, "can_edit": True}


@app.put("/api/staff/payslip")
async def put_payslip(request: Request, person: str, month: str, _user: str = Depends(admin)):
    if not staff.files().enabled:
        raise HTTPException(503, "Dépôt de fiches de paie non configuré (variable STAFF_BUCKET)")
    content = await request.body()
    if len(content) > 8 * 1024 * 1024:
        raise HTTPException(413, "Fichier trop volumineux (8 Mo maximum)")
    if not content.startswith(b"%PDF"):
        raise HTTPException(415, "Seuls les fichiers PDF sont acceptés")
    try:
        staff.files().put(person, month, content)
    except ValueError:
        raise HTTPException(422, "Personne ou mois invalide")
    return {"size": len(content), "uploaded_at": datetime.now(timezone.utc).isoformat()}


@app.post("/api/staff/import")
async def import_staff(request: Request, user: str = Depends(admin)):
    """Import initial : archive ZIP contenant staff.json et payslips/{personne}/{AAAA-MM}.pdf (voir scripts d'import)."""
    import io
    import json as _json
    import zipfile
    raw = await request.body()
    if len(raw) > 30 * 1024 * 1024:
        raise HTTPException(413, "Archive trop volumineuse (30 Mo maximum)")
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
        infos = z.infolist()
        if len(infos) > 800 or sum(i.file_size for i in infos) > 120 * 1024 * 1024:
            raise HTTPException(413, "Archive trop volumineuse")
        imported = _json.loads(z.read("staff.json"))
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(422, "Archive invalide : staff.json introuvable ou illisible")
    pdfs = {}
    for i in infos:
        m = re.fullmatch(r"payslips/([A-Za-z0-9_-]{1,40})/(\d{4}-(?:0[1-9]|1[0-2]))\.pdf", i.filename)
        if m and i.file_size <= 8 * 1024 * 1024:
            content = z.read(i)
            if content.startswith(b"%PDF"):
                pdfs[(m.group(1), m.group(2))] = content
    try:
        cur = staff.store().get()
        data, report = staff.merge_import(cur["data"], imported)
    except Exception as e:
        raise HTTPException(422, f"Import refusé : {str(e)[:300]}")
    stored = 0
    if staff.files().enabled:
        for (pid, month), content in pdfs.items():
            staff.files().put(pid, month, content)
            stored += 1
    else:                                                    # sans stockage de PDF, on n'annonce pas de fichier fantôme
        for p in data["people"]:
            for s in p["payslips"]:
                s["file"] = None
    doc = staff.store().put(data, user, cur["updated_at"])
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : réessayez.")
    return {**doc, "can_edit": True, **report, "pdfs": stored}


@app.get("/api/staff/payslip")
def get_payslip(person: str, month: str, _user: str = Depends(admin)):
    try:
        content = staff.files().get(person, month)
    except ValueError:
        raise HTTPException(422, "Personne ou mois invalide")
    if content is None:
        raise HTTPException(404, "Fiche introuvable")
    return RawResponse(content, media_type="application/pdf", headers={"Content-Disposition": f'inline; filename="fiche-{month}.pdf"', "Cache-Control": "no-store"})


@app.get("/api/staff/accounting")
def staff_accounting(year: int = Query(..., ge=2000, le=2100), _user: str = Depends(admin)):
    try:
        return provider().staff_accounting(year)
    except Exception:
        log.exception("Charges de personnel indisponibles")
        return {"unavailable": "Données comptables momentanément indisponibles."}


@app.get("/api/staff/partners")
def staff_partners(q: str = Query(..., min_length=2, max_length=60), _user: str = Depends(admin)):
    try:
        return {"partners": provider().staff_partners(q)}
    except Exception:
        log.exception("Recherche de sociétés impossible")
        return {"partners": [], "unavailable": "Recherche momentanément indisponible."}


@app.get("/api/staff/invoices")
def staff_invoices(ids: str = Query(..., max_length=200), year: int = Query(..., ge=2000, le=2100), _user: str = Depends(admin)):
    try:
        pids = [int(x) for x in ids.split(",") if x.strip()][:20]
    except ValueError:
        raise HTTPException(422, "Identifiants invalides")
    try:
        return {"invoices": provider().staff_invoices(pids, year)}
    except Exception:
        log.exception("Factures des indépendants indisponibles")
        return {"invoices": [], "unavailable": "Factures momentanément indisponibles."}


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
            "marketing": _safe(p.marketing, d_from, d_to),
            "analytics": ga.demo(d_from, d_to) if settings.PROVIDER == "demo" else _safe(ga.report, d_from, d_to),
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
