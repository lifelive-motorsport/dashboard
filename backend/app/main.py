from __future__ import annotations

import copy
import re
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, Response as RawResponse
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field

from . import speech, leaves, scheduler
from . import adjustments, dkv, expenses, ga, gauth, gcal, maps, planning, resources, settings, staff, stockvar, timesheets, tn11
from . import access, projection, users
from .auth import COOKIE, VIEWAS, audit_viewas, is_allowed, real_user, require_user, role, set_session_cookie, set_viewas_cookie, verify_google
from .bu import aggregate
from .providers.demo import DemoProvider

log = logging.getLogger("dashboard")
app = FastAPI(title="Lifelive Motorsport — Logbook")
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
async def legacy_host_redirect(request, call_next):
    """Ancien nom d'hôte (dashboard-app…) -> 301 vers le nouveau (logbook…), une fois CANONICAL_HOST défini."""
    host = (request.headers.get("host") or "").split(":")[0].lower()
    if settings.CANONICAL_HOST and host in settings.LEGACY_HOSTS and host != settings.CANONICAL_HOST and request.url.path != "/api/health":
        from fastapi.responses import RedirectResponse
        url = f"https://{settings.CANONICAL_HOST}{request.url.path}" + (f"?{request.url.query}" if request.url.query else "")
        return RedirectResponse(url, status_code=301)
    return await call_next(request)


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
        return {"email": email, "session": False, "role": role(email), "super": users.is_super(email), **users.identity(email), "pages": sorted(p) if (p := users.pages_of(email)) is not None else None}            # non configuré : on reste sur le jeton Google
    set_session_cookie(response, request, email)
    return {"email": email, "session": True, "role": role(email), "super": users.is_super(email), **users.identity(email), "pages": sorted(p) if (p := users.pages_of(email)) is not None else None}


@app.get("/api/session")
def current_session(request: Request, user: str = Depends(require_user)):
    return {"viewing_as": getattr(request.state, "viewing_as", None), "email": user, "session": True, "role": role(user), "super": users.is_super(user), **users.identity(user), "pages": sorted(p) if (p := users.pages_of(user)) is not None else None}


class ViewAsBody(BaseModel):
    email: str = Field(min_length=3, max_length=120)
    write: bool = False


@app.get("/api/session/view-as/candidates")
def viewas_candidates(real: str = Depends(real_user)):
    if not users.is_super(real):
        raise HTTPException(403, "Réservé au Super User")
    out: dict[str, dict] = {}
    for p in staff.store().get()["data"]["people"]:
        if p.get("google_email") and p.get("active", True):
            out[p["google_email"].lower()] = {"email": p["google_email"].lower(), "name": p["name"], "info": p.get("function", "") or ""}
    for e, r in users.registry().items():
        out.setdefault(e.lower(), {"email": e.lower(), "name": e, "info": r})
    return {"candidates": sorted(out.values(), key=lambda c: c["name"].lower())}


@app.post("/api/session/view-as")
def viewas_start(body: ViewAsBody, request: Request, response: Response, real: str = Depends(real_user)):
    """Super User : ouvre Logbook avec les droits d'un autre utilisateur pendant deux heures (lecture seule, sauf si les modifications sont autorisées ; elles sont alors journalisées)."""
    if not users.is_super(real):
        raise HTTPException(403, "Réservé au Super User")
    target = body.email.strip().lower()
    if not is_allowed(target):
        raise HTTPException(422, "Adresse inconnue ou non autorisée")
    if target == real.lower():
        raise HTTPException(422, "Vous êtes déjà cet utilisateur")
    set_viewas_cookie(response, request, real, target, body.write)
    if body.write:
        audit_viewas(real, target, "START", "view-as with write")
    return {"viewing_as": {"real": real, "as": target, "write": body.write}}


@app.delete("/api/session/view-as")
def viewas_stop(response: Response):
    response.delete_cookie(VIEWAS, path="/")
    return {"viewing_as": None}


@app.delete("/api/session")
def close_session(response: Response):
    response.delete_cookie(COOKIE, path="/")
    return {"session": False}


def super_user(user: str = Depends(require_user)) -> str:
    if not users.is_super(user):
        raise HTTPException(403, "Réservé au Super User")
    return user


@app.get("/api/admin/alerts-status")
def alerts_status(_user: str = Depends(super_user)):
    """Super User : état des déclencheurs des rappels de pointage (active, en pause…), pour le bandeau d'information."""
    return scheduler.alerts_status()


def granted(*pages: str):
    """Super User, ou membre d'une catégorie à laquelle l'une de ces pages est cochée (le rôle « Administrateur » n'y donne pas accès)."""
    def dep(user: str = Depends(require_user)) -> str:
        if users.is_super(user):
            return user
        p = users.pages_of(user)
        if p is not None and any(x in p for x in pages):
            return user
        raise HTTPException(403, "Page réservée au Super User ou aux catégories autorisées")
    return dep


def _bu_ok(user: str, bu: str | None) -> bool:
    """Un utilisateur limité à une BU ne gère que les événements de cette BU (XC, ou toutes les BU CARS)."""
    if users.is_super(user):
        return True
    lock = access.bu_lock(users.pages_of(user))
    return lock is None or bu is None or (lock == "XC") == (bu == "XC")


def _users_view(doc: dict) -> dict:
    fixed = [{"email": e, "role": "super", "source": "SUPER_USERS"} for e in users.supers()]
    fixed += [{"email": e, "role": "admin", "source": "ADMIN_EMAILS"} for e in settings.ADMIN_EMAILS if e not in users.supers()]
    fixed += [{"email": e, "role": "cat:xc", "source": "XC_ONLY_EMAILS"} for e in settings.XC_ONLY_EMAILS]
    known = {u["email"].lower() for u in doc.get("users", [])} | {e.lower() for e in users.supers()}
    try:
        suggested = sorted(({"email": p["google_email"].lower(), "name": p["name"], "function": p.get("function", "")} for p in staff.store().get()["data"]["people"]
                            if p.get("google_email") and p.get("active", True) and p["google_email"].lower() not in known), key=lambda s: s["name"].lower())
    except Exception:
        suggested = []
    return {**doc, "categories": users.categories(doc.get("categories") or []), "fixed": fixed, "domain": settings.ALLOWED_DOMAIN, "suggested": suggested}


@app.get("/api/users")
def get_users(user: str = Depends(super_user)):
    """Utilisateurs enregistrés, catégories (pages cochées) et comptes « fixes » venus de la configuration du serveur (lecture seule)."""
    try:
        doc = users.store().get()
    except Exception:
        log.exception("Lecture des utilisateurs impossible")
        raise HTTPException(503, "Utilisateurs indisponibles (stockage non configuré ou inaccessible)")
    return _users_view(doc)


@app.put("/api/users")
def put_users(payload: users.Payload, user: str = Depends(super_user)):
    cats, ids = [], set()
    for c in payload.categories:
        if c.id in ids:
            raise HTTPException(422, f"Catégorie en double : {c.id}")
        ids.add(c.id)
        cats.append(c.model_dump())
    ids.add("xc") if not any(c["id"] == "xc" for c in cats) else None          # la catégorie XC par défaut existe toujours
    seen, rows = set(), []
    for u in payload.users:
        if u.email in seen:
            raise HTTPException(422, f"Adresse en double : {u.email}")
        seen.add(u.email)
        cat = u.role[4:] if u.role.startswith("cat:") else "xc" if u.role == "xc" else None
        if cat and cat not in ids:
            raise HTTPException(422, f"Catégorie inconnue pour {u.email}")
        rows.append(u.model_dump())                            # pour un Super User, seuls le nom et le surnom comptent (son rôle vient de SUPER_USERS)
    try:
        doc = users.store().put(rows, user, cats)
    except Exception:
        log.exception("Enregistrement des utilisateurs impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    users.invalidate()
    return _users_view(doc)


@app.get("/api/tags")
def tags(_user: str = Depends(require_user)):
    """Étiquettes Odoo utilisées par le dashboard et leur présence (page Settings › Tags Odoo)."""
    try:
        return provider().tags_overview()
    except Exception:
        log.exception("Étiquettes indisponibles")
        return {"tags": [], "unavailable": "Liste des étiquettes momentanément indisponible."}


_stock_cache: dict[str, tuple[float, dict]] = {}


_margins_cache: dict = {}


@app.get("/api/xc/margins")
def xc_margins(refresh: bool = False, _user: str = Depends(require_user)):
    """Contrôle des marges XC (articles à code PIF) ; mise en cache 15 min."""
    hit = _margins_cache.get("m")
    if hit and time.time() - hit[0] < (30 if refresh else 900):
        return hit[1]
    try:
        data = {**provider().margin_products(), "as_of": date.today().isoformat(), "source": provider().name}
    except (NotImplementedError, LookupError) as e:
        return {"unavailable": str(e)}
    except Exception:
        log.exception("Contrôle des marges indisponible")
        if hit:
            return hit[1]
        raise HTTPException(502, "Contrôle des marges momentanément indisponible")
    _margins_cache["m"] = (time.time(), data)
    return data


def _freight_rate() -> float:
    """Taux de transport (part du prix de vente) utilisé pour le coût réel des articles : celui du contrôle des marges s/ produits."""
    hit = _margins_cache.get("m")
    if not hit:
        try:
            data = {**provider().margin_products(), "as_of": date.today().isoformat(), "source": provider().name}
            _margins_cache["m"] = hit = (time.time(), data)
        except Exception:
            log.exception("Taux de transport indisponible pour le contrôle TN11")
            return 0.0
    return float(((hit[1] or {}).get("freight") or {}).get("rate") or 0.0)


def _tn11_report(text: str) -> dict:
    parsed = tn11.parse_quote(text)
    sold = [l for l in parsed["lines"] if l["included"]]
    if not sold:
        raise HTTPException(422, "Aucune ligne vendue (colonne « INCLUS (X) ») dans ce document : est-ce bien un devis TN11 ?")
    rate = _freight_rate()
    try:
        data = provider().tn11_data(sorted({l["ref"] for l in sold if l["ref"]}), rate)
    except Exception:
        log.exception("Données Odoo du devis TN11 indisponibles")
        raise HTTPException(502, "Odoo est momentanément injoignable")
    rep = tn11.build_report(parsed, data["products"], data["boms"], data["info"], data["unit_real"].get, rate, data.get("unit_info"))
    return {**rep, "bom_error": data.get("bom_error"), "labour_like": [x.strip() for x in settings.TN11_LABOUR_LIKE.split(",") if x.strip()], "outlier_factor": settings.TN11_OUTLIER_FACTOR, "as_of": date.today().isoformat(),
            "lines_total": len(parsed["lines"])}


@app.post("/api/xc/tn11/check")
async def tn11_check(request: Request, _user: str = Depends(require_user)):
    """Contrôle d'un devis TN11 (PDF envoyé tel quel dans le corps de la requête) : prix de vente, coût Odoo, coût réel estimé, main-d'œuvre. Le PDF n'est pas conservé."""
    body = await request.body()
    if not body.startswith(b"%PDF"):
        raise HTTPException(422, "Envoyez le PDF du devis")
    if len(body) > 8_000_000:
        raise HTTPException(413, "PDF trop volumineux (8 Mo maximum)")
    return _tn11_report(dkv.extract_text(body, "application/pdf", "devis.pdf"))


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


def reference(user: str = Depends(require_user)) -> str:
    """Enregistrement des hypothèses de référence : propriétaires uniquement (REFERENCE_EDITORS)."""
    if not adjustments.can_reference(user):
        raise HTTPException(403, "Ces valeurs de référence ne peuvent être enregistrées que par leur propriétaire : vos modifications restent des simulations dans votre navigateur.")
    return user


def admin(user: str = Depends(require_user)) -> str:
    """Données du personnel : réservées aux administrateurs (ADMIN_EMAILS)."""
    if not adjustments.can_edit(user):
        raise HTTPException(403, "Réservé aux administrateurs de Logbook")
    return user


def _expense_lines(year: int) -> list[dict]:
    try:
        return provider().expenses_lines(year)
    except Exception:
        log.exception("Lecture des frais généraux impossible")
        raise HTTPException(503, "Frais généraux indisponibles pour le moment")


@app.get("/api/expenses/accounts")
def expenses_accounts(year: int = Query(..., ge=2000, le=2100), user: str = Depends(require_user)):
    cfg = expenses.store().get()
    return {**expenses.accounts_view(_expense_lines(year), cfg["data"], year), "updated_at": cfg["updated_at"], "updated_by": cfg["updated_by"], "can_edit": adjustments.can_edit(user), "can_save": adjustments.can_reference(user)}


@app.put("/api/expenses/config")
def put_expenses_config(body: expenses.SaveBody, user: str = Depends(reference)):
    cur = expenses.Config.model_validate(expenses.store().get()["data"])
    data = body.data.model_copy(update={"saved": True, "key_mode": cur.key_mode, "xc_pct": cur.xc_pct, "plates": cur.plates, "links": cur.links, "split": cur.split, "general_vehicles": cur.general_vehicles}).model_dump()      # la clé d'imputation a son propre enregistrement
    doc = expenses.store().put(data, user, body.base)
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    return {**doc, "can_edit": True}


@app.get("/api/expenses/general")
def expenses_general(year: int = Query(..., ge=2000, le=2100), kind: str = Query("general", pattern="^(general|vehicle)$"), _user: str = Depends(require_user)):
    cfg = expenses.store().get()["data"]
    out = expenses.kind_view(_expense_lines(year), cfg, year, kind)
    try:
        out["excluded"] = expenses.excluded_view(provider().expenses_excluded(year)) if kind == "general" else {"total": 0.0, "moves": []}
    except Exception:
        log.exception("Écritures exclues indisponibles")
        out["excluded"] = {"total": 0.0, "moves": [], "error": True}
    return out


def _calendar(d_from: date, d_to: date) -> dict:
    """Réservations de véhicules de l'agenda Google, ou la raison pour laquelle elles manquent."""
    if settings.PROVIDER == "demo":
        evs = gcal.demo(d_from, d_to)
    elif not gcal.configured():
        return {"configured": False, "note": "Agenda non configuré (variable CALENDAR_IDS) : voir la marche à suivre dans infra/README_DEPLOY.md."}
    else:
        try:
            evs = gcal.events(d_from, d_to)
        except Exception as e:
            log.exception("Google Agenda indisponible")
            return {"configured": True, "error": str(e)[:300]}
    return {"configured": True, "buffer_days": settings.FUEL_BUFFER_DAYS, "events": len(evs), "usage": gcal.usage(evs, settings.FUEL_BUFFER_DAYS), "calendars": [{"label": l or c[:12], "bu": b} for c, l, b in gcal.calendars()] if settings.PROVIDER != "demo" else []}


@app.get("/api/vehicles/usage")
def vehicles_usage(year: int = Query(..., ge=2000, le=2100), _user: str = Depends(require_user)):
    today = date.today()
    return _calendar(date(year, 1, 1), today if year == today.year else date(year, 12, 31))


_fuel_inv_cache: dict[int, tuple[float, list]] = {}
_dkv_cache: dict[int, dict] = {}


def _fuel_invoices(year: int) -> list[dict]:
    hit = _fuel_inv_cache.get(year)
    if hit and time.time() - hit[0] < 300:
        return hit[1]
    inv = provider().fuel_invoices(year)
    _fuel_inv_cache[year] = (time.time(), inv)
    return inv


@app.get("/api/fuel/parse")
def fuel_parse(att: int, year: int = Query(..., ge=2000, le=2100), _user: str = Depends(require_user)):
    """Analyse d'une facture de la carte carburant : transactions par plaque (litres, montant HT, kilométrage), péages et frais ; résultat mis en cache."""
    if att in _dkv_cache:
        return _dkv_cache[att]
    try:
        allowed = {a["id"] for i in _fuel_invoices(year) for a in i["attachments"]}
        got = provider().fuel_attachment(att, year, allowed)
    except Exception:
        log.exception("Pièce jointe indisponible")
        raise HTTPException(503, "Pièce jointe indisponible pour le moment")
    if got is None:
        raise HTTPException(404, "Pièce jointe introuvable")
    content, mime, name = got
    parsed = dkv.parse_transactions(dkv.extract_text(content, mime, name))
    out = {"att": att, "name": name, "summary": dkv.summarize(parsed),
           "transactions": [{k: t[k] for k in ("date", "vehicle", "quantity", "total_ht", "km", "category", "currency")} for t in parsed["transactions"] if t["currency"] == "EUR"]}
    if len(_dkv_cache) > 400:
        _dkv_cache.clear()
    _dkv_cache[att] = out
    return out


@app.put("/api/expenses/plates")
def put_plates(body: expenses.PlatesBody, user: str = Depends(reference)):
    """Correspondance plaque de la carte carburant -> véhicule de service (sans toucher au reste de la configuration)."""
    cur = expenses.store().get()
    try:
        data = expenses.Config.model_validate({**expenses.Config.model_validate(cur["data"]).model_dump(), "plates": body.plates}).model_dump()
    except ValueError as e:
        raise HTTPException(422, f"Plaque ou véhicule invalide : {str(e)[:200]}")
    doc = expenses.store().put(data, user, body.base if body.base is not None else cur["updated_at"])
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    return {**doc, "can_edit": True, "plates": data["plates"]}


@app.put("/api/expenses/split")
def put_split(body: expenses.SplitBody, user: str = Depends(reference)):
    """Imputation retenue (en %) du coût de chaque véhicule aux BU et aux frais généraux (sans toucher au reste de la configuration)."""
    cur = expenses.store().get()
    try:
        data = expenses.Config.model_validate({**expenses.Config.model_validate(cur["data"]).model_dump(), "split": body.split, **({"general_vehicles": body.general} if body.general is not None else {})}).model_dump()
    except ValueError as e:
        raise HTTPException(422, f"Pourcentage invalide : {str(e)[:200]}")
    doc = expenses.store().put(data, user, body.base if body.base is not None else cur["updated_at"])
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    return {**doc, "can_edit": True, "split": data["split"], "general_vehicles": data["general_vehicles"]}


@app.get("/api/fuel")
def fuel(year: int = Query(..., ge=2000, le=2100), _user: str = Depends(require_user)):
    """Carburant : imputation encodée dans Odoo, factures de la carte carburant et réservations de véhicules dans l'agenda."""
    try:
        invoices = _fuel_invoices(year)
    except Exception:
        log.exception("Factures de la carte carburant indisponibles")
        raise HTTPException(503, "Factures de la carte carburant indisponibles pour le moment")
    today = date.today()
    cfg = expenses.store().get()
    return {"year": year, "supplier": settings.FUEL_SUPPLIER_NAME, "invoices": invoices, "plates": cfg["data"].get("plates") or {}, "plates_base": cfg["updated_at"], "can_edit": adjustments.can_reference(_user),
            "calendar": _calendar(date(year, 1, 1), today if year == today.year else date(year, 12, 31))}


@app.get("/api/fuel/attachment")
def fuel_attachment(att: int, year: int = Query(..., ge=2000, le=2100), text: bool = True, _user: str = Depends(admin)):
    """Texte extrait d'une pièce jointe d'une facture de la carte carburant (diagnostic de l'analyse)."""
    try:
        got = provider().fuel_attachment(att, year)
    except Exception:
        log.exception("Pièce jointe indisponible")
        raise HTTPException(503, "Pièce jointe indisponible pour le moment")
    if got is None:
        raise HTTPException(404, "Pièce jointe introuvable")
    content, mime, name = got
    t = dkv.extract_text(content, mime, name)
    return {"name": name, "mimetype": mime, "size": len(content), "chars": len(t), "text": t[:60000], "candidate_lines": dkv.candidate_lines(t)[:300]}


@app.get("/api/expenses/vehicles")
def expenses_vehicles(year: int = Query(..., ge=2000, le=2100), scope: str = Query("config", pattern="^(config|all615)$"), _user: str = Depends(require_user)):
    cfg = expenses.store().get()
    return {**expenses.vehicles_view(_expense_lines(year), cfg["data"], year, scope), "links": cfg["data"].get("links") or {}, "split": cfg["data"].get("split") or {}, "general_vehicles": cfg["data"].get("general_vehicles") or [], "links_base": cfg["updated_at"], "can_edit": adjustments.can_edit(_user), "can_save": adjustments.can_reference(_user)}


@app.put("/api/expenses/links")
def put_links(body: expenses.LinksBody, user: str = Depends(reference)):
    """Correspondance véhicule Odoo (compte 615) -> ressource de l'agenda Google (sans toucher au reste de la configuration)."""
    cur = expenses.store().get()
    try:
        data = expenses.Config.model_validate({**expenses.Config.model_validate(cur["data"]).model_dump(), "links": body.links}).model_dump()
    except ValueError as e:
        raise HTTPException(422, f"Véhicule ou ressource invalide : {str(e)[:200]}")
    doc = expenses.store().put(data, user, body.base if body.base is not None else cur["updated_at"])
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    return {**doc, "can_edit": True, "links": data["links"]}


@app.get("/api/expenses/month")
def expenses_month(month: str = Query(..., pattern=r"^\d{4}-(0[1-9]|1[0-2])$"), kind: str = Query("general", pattern="^(general|vehicle)$"), _user: str = Depends(require_user)):
    """Plus grosses écritures d'un mois pour les comptes retenus (pour comprendre un pic mensuel)."""
    try:
        raw = provider().expenses_month(month)
    except Exception:
        log.exception("Détail mensuel des frais généraux indisponible")
        raise HTTPException(503, "Détail du mois indisponible pour le moment")
    return expenses.month_lines(raw, expenses.store().get()["data"], kind, month)


@app.get("/api/pnl/unassigned")
def pnl_unassigned(year: int = Query(..., ge=2000, le=2100), _user: str = Depends(require_user)):
    """Comptes de CA et de coûts directs sans BU reconnue (colonne « Non affecté »), du 1er janvier à aujourd'hui."""
    today = date.today()
    try:
        accounts = provider().unassigned_accounts(date(year, 1, 1), today if year == today.year else date(year, 12, 31))
    except Exception:
        log.exception("Comptes non affectés indisponibles")
        raise HTTPException(503, "Comptes non affectés indisponibles pour le moment")
    return {"accounts": accounts, "revenue": round(sum(a["amount"] for a in accounts if a["kind"] == "revenue"), 2), "costs": round(sum(a["amount"] for a in accounts if a["kind"] != "revenue"), 2)}


@app.get("/api/expenses/marketing")
def expenses_marketing(year: int = Query(..., ge=2000, le=2100), _user: str = Depends(require_user)):
    """Marketing commun (hors comptes déjà rattachés à une BU) pour la marge nette."""
    return expenses.marketing_view(_expense_lines(year))


@app.get("/api/expenses/allocation")
def expenses_allocation(year: int = Query(..., ge=2000, le=2100), user: str = Depends(require_user)):
    """Frais généraux (rubrique « general ») imputés à XC et CARS selon les deux clés ; le CA est celui du 1er janvier à aujourd'hui."""
    cfg = expenses.store().get()
    general = expenses.kind_view(_expense_lines(year), cfg["data"], year, "general")
    try:
        today = date.today()
        to = today if year == today.year else date(year, 12, 31)
        groups = {g["key"]: g for g in aggregate(provider().pnl_balances(date(year, 1, 1), to))["groups"]}
    except Exception:
        log.exception("CA indisponible pour la clé d'imputation")
        raise HTTPException(503, "Chiffre d'affaires indisponible pour le moment")
    out = expenses.allocation_view(general, groups.get("XC", {}).get("ca", 0.0), groups.get("CARS", {}).get("ca", 0.0), cfg["data"])
    return {**out, "updated_at": cfg["updated_at"], "updated_by": cfg["updated_by"], "can_edit": adjustments.can_edit(user), "can_save": adjustments.can_reference(user)}


@app.put("/api/expenses/key")
def put_expenses_key(body: expenses.KeyBody, user: str = Depends(reference)):
    """Enregistre la clé d'imputation (prorata du CA ou % encodé) sans toucher aux comptes retenus."""
    cur = expenses.store().get()
    data = {**expenses.Config.model_validate(cur["data"]).model_dump(), "key_mode": body.key_mode, "xc_pct": body.xc_pct}
    doc = expenses.store().put(data, user, body.base if body.base is not None else cur["updated_at"])
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    return {**doc, "can_edit": True}


@app.get("/api/staff")
def get_staff(user: str = Depends(require_user)):
    if not adjustments.can_edit(user):
        return {"restricted": True, "can_edit": False}
    try:
        doc = staff.store().get()
    except Exception:
        log.exception("Lecture des données du personnel impossible")
        raise HTTPException(503, "Stockage des données du personnel inaccessible")
    return {**doc, "can_edit": True, "can_save": adjustments.can_reference(user), "upload": staff.files().enabled, "pay_prefixes": settings.STAFF_PAY_PREFIXES}


@app.put("/api/staff")
def put_staff(body: staff.SaveBody, user: str = Depends(reference)):
    try:
        doc = staff.store().put(body.data.model_dump(), user, body.base)
    except Exception:
        log.exception("Enregistrement des données du personnel impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    return {**doc, "can_edit": True}


@app.put("/api/staff/payslip")
async def put_payslip(request: Request, person: str, month: str, _user: str = Depends(reference)):
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
async def import_staff(request: Request, user: str = Depends(reference)):
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


@app.get("/api/resources")
def get_resources(user: str = Depends(granted("planifier/res_staff", "planifier/res_ext", "planifier/res_veh"))):
    """Ressources mobilisables sur un événement (Super User) : staff et leur compte Google, prestataires externes, véhicules de service."""
    try:
        people = [{"id": p["id"], "name": p["name"], "kind": p["kind"], "function": p.get("function", ""), "active": p.get("active", True), "email": p.get("google_email", ""), "alloc": p.get("alloc", {}), "all_bus": bool(p.get("all_bus", False)), "workshop": p.get("workshop", ""), "work_days": p.get("work_days", [0, 1, 2, 3, 4])}
                  for p in staff.store().get()["data"]["people"]]
        res = copy.deepcopy(resources.store().get())
    except Exception:
        log.exception("Lecture des ressources impossible")
        raise HTTPException(503, "Stockage des ressources inaccessible")
    roles_ok = True
    ext = res["data"]["externals"]
    if ext:                                                    # Odoo reste la référence : fonction (Job Position), e-mail et téléphone sont relus à chaque ouverture et écrasent la copie enregistrée
        try:
            infos = provider().partner_infos([e["partner_id"] for e in ext])
            for e in ext:
                i = infos.get(e["partner_id"])
                if i:
                    e["role"], e["email"], e["phone"] = i["function"], i["email"], i["phone"]
        except Exception:
            log.exception("Job Position des prestataires illisible dans Odoo")
            roles_ok = False
    try:
        veh = resources.vehicles()
    except Exception:
        log.exception("Véhicules de service (ressources Google) indisponibles")
        veh = {"configured": False, "source": "none", "items": [], "message": "Liste des véhicules momentanément indisponible."}
    return {"staff": people, "externals": res, "roles_from_odoo": roles_ok, "vehicles": veh, "delegation": gauth.configured() or settings.PROVIDER == "demo"}


@app.put("/api/resources/externals")
def put_resource_externals(body: resources.SaveBody, user: str = Depends(granted("planifier/res_ext"))):
    try:
        doc = resources.store().put(body.data.model_dump(), user, body.base)
    except Exception:
        log.exception("Enregistrement des prestataires impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    return doc


class StaffEmailBody(BaseModel):
    email: str | None = Field(default=None, max_length=120)         # seuls les champs fournis sont modifiés
    all_bus: bool | None = None
    workshop: str | None = None
    work_days: list[int] | None = None


@app.put("/api/resources/staff/{pid}")
def put_resource_staff(pid: str, body: StaffEmailBody, user: str = Depends(super_user)):
    """Compte Google d'une personne du staff : enregistré dans sa fiche (le reste de la fiche est conservé)."""
    try:
        cur = staff.store().get()
        data = copy.deepcopy(cur["data"])                 # on modifie une copie : un refus de validation ne doit rien changer
        person = next((p for p in data["people"] if p["id"] == pid), None)
        if person is None:
            raise HTTPException(404, "Personne introuvable")
        if body.email is not None:
            person["google_email"] = body.email
        if body.all_bus is not None:
            person["all_bus"] = body.all_bus
        if body.workshop is not None:
            person["workshop"] = body.workshop
        if body.work_days is not None:
            person["work_days"] = body.work_days
        data = staff.StaffDoc.model_validate(data).model_dump()
        doc = staff.store().put(data, user, cur["updated_at"])
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(422, "Valeur invalide (adresse e-mail ou rôle d'atelier)") from e
    except Exception:
        log.exception("Enregistrement du compte Google impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    if doc is None:
        raise HTTPException(409, "Quelqu'un a enregistré entre-temps : rechargez la page avant de modifier.")
    saved = next(p for p in doc["data"]["people"] if p["id"] == pid)
    return {"id": pid, "email": saved["google_email"], "all_bus": saved["all_bus"], "workshop": saved.get("workshop", ""), "work_days": saved.get("work_days", [0, 1, 2, 3, 4])}


@app.get("/api/resources/directory-users")
def resource_directory_users(_user: str = Depends(super_user)):
    return resources.directory_users()


@app.get("/api/planning")
def planning_page(date_from: date = Query(..., alias="from"), date_to: date = Query(..., alias="to"), _user: str = Depends(require_user)):
    """Vue Planning (tous les utilisateurs, lecture seule) : événements de la période et ressources, sans adresse e-mail ni donnée de paie."""
    if date_to < date_from or (date_to - date_from).days > 130:
        raise HTTPException(422, "Période invalide (130 jours au maximum)")
    try:
        return planning.restrict_to_bu(planning.planning_view(date_from, date_to), access.bu_lock(users.pages_of(_user)))
    except Exception as e:
        log.exception("Planning indisponible")
        raise HTTPException(503, f"Planning momentanément indisponible : {e}")


# ---- Consigner › Pointages ----------------------------------------------------------------------------------------------------------------

def _ts_ctx(user: str) -> dict:
    r = timesheets.role_of(user)
    if r["role"] is None:
        raise HTTPException(403, "Vous n'êtes pas inscrit à l'atelier : le Super User doit renseigner votre compte Google et votre rôle (Planifier › Ressources › Staff interne › Atelier).")
    return r


def _ts_chef(user: str) -> dict:
    r = _ts_ctx(user)
    if r["role"] != "chef":
        raise HTTPException(403, "Réservé au chef d'atelier")
    return r


def _ts_err(e: Exception):
    if isinstance(e, PermissionError):
        raise HTTPException(403, str(e))
    if isinstance(e, KeyError):
        raise HTTPException(404, "Pointage introuvable")
    if isinstance(e, (LookupError, ValueError)):
        raise HTTPException(422, str(e))
    raise e


@app.get("/api/timesheets/me")
def ts_me(user: str = Depends(require_user)):
    r = timesheets.role_of(user)
    p = r["person"] or {}
    return {"role": r["role"], "bus": r["bus"], "super": r["super"], "name": p.get("name", ""), "theoretical": timesheets.theoretical_minutes(r["person"]),
            "assignments": [{"id": a, "label": l} for a, l in timesheets.ASSIGNMENTS], "natures": [{"id": a, "label": l} for a, l in timesheets.EVENT_NATURES], "atelier_natures": [{"id": a, "label": l} for a, l in timesheets.ATELIER_NATURES], "systems": [{"id": a, "label": l} for a, l in timesheets.SYSTEMS], "edit_hours": timesheets.EDIT_HOURS,
            "attachments": timesheets.blobs().enabled, "transcribe": settings.TRANSCRIBE}


@app.get("/api/timesheets/jobs")
def ts_jobs(all: bool = False, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    return {"jobs": timesheets.list_jobs(open_only=not (all and r["role"] == "chef")), "recent": timesheets.recent_job_ids(user)}


@app.post("/api/timesheets/jobs")
def ts_create_job(body: timesheets.JobIn, user: str = Depends(require_user)):
    r = _ts_chef(user)
    if not r["super"] and body.bu != "ALL" and timesheets.bu_group(body.bu) not in r["bus"]:
        raise HTTPException(403, f"Vous gérez les jobs de la BU {', '.join(r['bus'])}")
    try:
        return timesheets.create_job(body, user)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.put("/api/timesheets/jobs/{jid}")
def ts_update_job(jid: str, body: timesheets.JobIn, user: str = Depends(require_user)):
    r = _ts_chef(user)
    old = timesheets.jobs().get(jid)
    if not old:
        raise HTTPException(404, "Job introuvable")
    if not timesheets.chef_for(r, old):
        raise HTTPException(403, "Ce job est géré par l'autre chef d'atelier")
    if not r["super"] and body.bu != "ALL" and timesheets.bu_group(body.bu) not in r["bus"]:
        raise HTTPException(403, f"Vous gérez les jobs de la BU {', '.join(r['bus'])}")
    new = body.model_dump()
    if all(new[k] == old.get(k, "" if k == "nature" else None) for k in ("kind", "nature", "vehicle", "event")) and body.title in ("", old["title"]):
        title = old["title"]                                              # simple clôture / réouverture ou changement de BU : l'intitulé ne change pas
    else:
        try:
            title = timesheets.job_title(body)
        except ValueError as e:
            raise HTTPException(422, str(e))
        if any(j["id"] != jid and j["title"].lower() == title.lower() for j in timesheets.jobs().all()):
            raise HTTPException(422, "Ce job existe déjà")
    doc = {**old, **new, "title": title, "assignment": timesheets.N_ASSIGN.get(body.nature, body.assignment)}
    doc.pop("template_id", None)
    if body.kind == "atelier" and body.template_id and not old.get("checklist"):         # une liste de contrôle peut être ajoutée, pas remplacée (les cases déjà cochées sont conservées)
        t = timesheets.templates().get(body.template_id)
        if not t:
            raise HTTPException(422, "Modèle introuvable")
        doc["checklist"] = timesheets.make_checklist(t)
    timesheets.jobs().put(jid, doc)
    return timesheets.job_view(doc)


def _ts_tpl_rights(r: dict, bu: str):
    if not r["super"] and bu != "ALL" and timesheets.bu_group(bu) not in r["bus"]:
        raise HTTPException(403, f"Vous gérez les modèles de la BU {', '.join(r['bus'])}")


@app.get("/api/timesheets/templates")
def ts_templates(user: str = Depends(require_user)):
    _ts_chef(user)
    return {"templates": timesheets.list_templates()}


@app.post("/api/timesheets/templates")
def ts_create_template(body: timesheets.TemplateIn, user: str = Depends(require_user)):
    r = _ts_chef(user)
    _ts_tpl_rights(r, body.bu)
    try:
        return timesheets.save_template(body, user)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.put("/api/timesheets/templates/{tid}")
def ts_update_template(tid: str, body: timesheets.TemplateIn, user: str = Depends(require_user)):
    r = _ts_chef(user)
    old = timesheets.templates().get(tid)
    if not old:
        raise HTTPException(404, "Modèle introuvable")
    _ts_tpl_rights(r, old["bu"])
    _ts_tpl_rights(r, body.bu)
    try:
        return timesheets.save_template(body, user, tid)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.delete("/api/timesheets/templates/{tid}")
def ts_delete_template(tid: str, user: str = Depends(require_user)):
    """Supprime le modèle ; les jobs déjà créés gardent leur copie de la liste."""
    r = _ts_chef(user)
    old = timesheets.templates().get(tid)
    if not old:
        raise HTTPException(404, "Modèle introuvable")
    _ts_tpl_rights(r, old["bu"])
    timesheets.templates().delete(tid)
    return {"deleted": tid}


@app.delete("/api/timesheets/jobs/{jid}")
def ts_delete_job(jid: str, user: str = Depends(require_user)):
    """Suppression d'un job sans aucun pointage (sinon : le clôturer, pour garder l'historique)."""
    r = _ts_chef(user)
    job = timesheets.jobs().get(jid)
    if not job:
        raise HTTPException(404, "Job introuvable")
    if not timesheets.chef_for(r, job):
        raise HTTPException(403, "Ce job est géré par l'autre chef d'atelier")
    if any(e["job_id"] == jid for e in timesheets.entries().all()):
        raise HTTPException(409, "Ce job a déjà des pointages : clôturez-le plutôt que de le supprimer.")
    timesheets.jobs().delete(jid)
    return {"deleted": jid}


@app.get("/api/timesheets/suggestions")
def ts_suggestions(user: str = Depends(require_user)):
    _ts_chef(user)
    try:
        return {"suggestions": timesheets.suggestions(date.today())}
    except Exception as e:
        log.exception("Propositions de jobs indisponibles")
        return {"suggestions": [], "unavailable": f"Planning momentanément indisponible : {e}"}


@app.get("/api/timesheets/vehicles")
def ts_vehicles(user: str = Depends(require_user)):
    """Voitures (comptes analytiques CARS d'Odoo) proposées à la création d'un job d'atelier."""
    _ts_chef(user)
    try:
        today = date.today()
        v = provider().vehicles(date(today.year - 3, 1, 1), today)["vehicles"]
        return {"vehicles": sorted(({"id": str(x["id"]), "name": x["name"], "bu": _ts_bu_of(x)} for x in v if x.get("group", "CARS") == "CARS"), key=lambda x: x["name"].lower())}
    except Exception as e:
        log.exception("Liste des véhicules indisponible")
        return {"vehicles": [], "unavailable": f"Véhicules Odoo momentanément indisponibles : {e}"}


def _ts_bu_of(x: dict) -> str:
    """BU principale d'un événement ou d'un véhicule d'après l'axe BU d'Odoo ; vide si inconnue."""
    to_bu = {"XC": "XC", "Modern Rally": "MODERN_RALLY", "Historic Rally": "HISTORIC_RALLY", "Historic Racing": "HISTORIC_RACING"}
    bus = sorted(x.get("bus") or [], key=lambda b: -b.get("share", 0))
    return to_bu.get(bus[0]["bu"], "") if bus else ""


@app.get("/api/timesheets/events")
def ts_events(user: str = Depends(require_user)):
    """Événements (comptes analytiques de l'axe MEETING / EVENTS d'Odoo) proposés à la création d'un job événement."""
    _ts_chef(user)
    try:
        today = date.today()
        v = provider().events(date(today.year - 3, 1, 1), today + timedelta(days=366))["events"]
        return {"events": sorted(({"id": str(x["id"]), "name": x["name"], "bu": _ts_bu_of(x)} for x in v), key=lambda x: x["name"].lower())}
    except Exception as e:
        log.exception("Liste des événements indisponible")
        return {"events": [], "unavailable": f"Événements Odoo momentanément indisponibles : {e}"}


def _ts_week(user_email: str, start: date, viewer: str, r: dict) -> dict:
    jm = {j["id"]: j for j in timesheets.jobs().all()}
    ents = timesheets.week_entries(user_email, start)
    person = timesheets.person_of(user_email)
    return {"start": start.isoformat(), "user": user_email, "name": (person or {}).get("name", user_email), "missing": timesheets.missing_for(person, user_email) if user_email == viewer.lower() and (person or {}).get("workshop") == "mechanic" else [],
            "entries": [timesheets.entry_view(timesheets.public_attachments(e), viewer, r, jm) for e in ents], "summary": timesheets.summary(ents, person, jm)}


@app.get("/api/timesheets/week")
def ts_week(start: date, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    return _ts_week(user.lower(), timesheets.monday(start), user, r)


@app.get("/api/timesheets/cockpit")
def ts_cockpit(user: str = Depends(require_user)):
    """Chef d'atelier : l'atelier aujourd'hui (absents, pointés, en retard) et les jours manquants de chacun."""
    _ts_chef(user)
    return timesheets.cockpit()


@app.post("/api/cron/timesheet-alerts")
def cron_timesheet_alerts(request: Request):
    """Appelé par Cloud Scheduler (jeton OIDC du compte CRON_SERVICE_ACCOUNT) à 17 h du lundi au jeudi et 15 h le vendredi : rappelle aux mécaniciens leurs pointages manquants."""
    _cron_auth(request)
    try:
        return timesheets.send_alerts()
    except Exception as e:
        log.exception("Alertes de pointage impossibles")
        raise HTTPException(503, f"Alertes impossibles : {e}")


def _cron_auth(request: Request) -> None:
    if not settings.CRON_AUDIENCE or not settings.CRON_SERVICE_ACCOUNT:
        raise HTTPException(503, "Tâches planifiées non configurées (CRON_AUDIENCE, CRON_SERVICE_ACCOUNT)")
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer "):
        raise HTTPException(401, "Authentification requise")
    from google.auth.transport import requests as g_requests
    from google.oauth2 import id_token
    try:
        info = id_token.verify_oauth2_token(h[7:], g_requests.Request(), settings.CRON_AUDIENCE)
    except ValueError:
        raise HTTPException(401, "Jeton invalide")
    if (info.get("email") or "").lower() != settings.CRON_SERVICE_ACCOUNT.lower() or not info.get("email_verified"):
        raise HTTPException(403, "Compte non autorisé")


@app.get("/api/timesheets/team")
def ts_team(start: date, bu: str = "all", user: str = Depends(require_user)):
    """Chef d'atelier : heures de chaque mécanicien sur la semaine (taux d'occupation et taux facturable), pointages à valider."""
    r = _ts_chef(user)
    start = timesheets.monday(start)
    a, b = start.isoformat(), (start + timedelta(days=6)).isoformat()
    jm = {j["id"]: j for j in timesheets.jobs().all()}
    all_ents = [e for e in timesheets.entries().between("date", a, b) if timesheets.job_in_bu(jm.get(e["job_id"]), bu)]
    people = [p for p in staff.store().get()["data"]["people"] if p.get("google_email") and p.get("active", True)
              and p.get("workshop")]
    rows = []
    for p in sorted(people, key=lambda p: p["name"].lower()):
        ents = [e for e in all_ents if e["user"] == p["google_email"].lower() and timesheets.chef_for(r, jm.get(e["job_id"]))]
        rows.append({"name": p["name"], "alloc": p.get("alloc", {}), "all_bus": bool(p.get("all_bus")), "workshop": p["workshop"], "user": p["google_email"].lower(), "summary": timesheets.summary(ents, p, jm),
                     "entries": [timesheets.entry_view(timesheets.public_attachments(e), user, r, jm) for e in sorted(ents, key=lambda e: (e["date"], e["created_at"]))]})
    return {"start": a, "rows": rows}


@app.post("/api/timesheets/entries")
def ts_create_entry(body: timesheets.EntryIn, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    try:
        e = timesheets.create_entry(body, user, r)
    except Exception as ex:
        _ts_err(ex)
    return timesheets.entry_view(timesheets.public_attachments(e), user, r, {j["id"]: j for j in timesheets.jobs().all()})


@app.put("/api/timesheets/entries/{eid}")
def ts_update_entry(eid: str, body: timesheets.EntryIn, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    try:
        e = timesheets.update_entry(eid, body, user, r)
    except Exception as ex:
        _ts_err(ex)
    return timesheets.entry_view(timesheets.public_attachments(e), user, r, {j["id"]: j for j in timesheets.jobs().all()})


@app.delete("/api/timesheets/entries/{eid}")
def ts_delete_entry(eid: str, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    try:
        timesheets.delete_entry(eid, user, r)
    except Exception as ex:
        _ts_err(ex)
    return {"deleted": eid}


@app.post("/api/timesheets/entries/{eid}/validate")
def ts_validate_entry(eid: str, validated: bool = True, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    try:
        e = timesheets.validate_entry(eid, validated, user, r)
    except Exception as ex:
        _ts_err(ex)
    return timesheets.entry_view(timesheets.public_attachments(e), user, r, {j["id"]: j for j in timesheets.jobs().all()})


@app.post("/api/timesheets/transcribe")
async def ts_transcribe(request: Request, user: str = Depends(require_user)):
    """Mémo vocal (WAV 16 kHz mono) -> texte, pour pré-remplir l'intervention ; rien n'est enregistré."""
    _ts_ctx(user)
    if not settings.TRANSCRIBE:
        raise HTTPException(503, "Transcription désactivée")
    data = await request.body()
    if not data or len(data) > 7 * 1024 * 1024:
        raise HTTPException(413, "Mémo vide ou trop long")
    try:
        from starlette.concurrency import run_in_threadpool
        return {"text": await run_in_threadpool(speech.transcribe_wav, data)}
    except speech.SpeechError as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        log.exception("Transcription indisponible")
        raise HTTPException(503, f"Transcription indisponible : {e}")


class RejectBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@app.post("/api/timesheets/entries/{eid}/reject")
def ts_reject_entry(eid: str, body: RejectBody, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    try:
        e = timesheets.reject_entry(eid, body.reason, user, r)
    except Exception as ex:
        _ts_err(ex)
    return timesheets.entry_view(timesheets.public_attachments(e), user, r, {j["id"]: j for j in timesheets.jobs().all()})


@app.post("/api/timesheets/entries/{eid}/attachments")
async def ts_add_attachment(eid: str, request: Request, filename: str = Query("fichier", max_length=120), user: str = Depends(require_user)):
    r = _ts_ctx(user)
    if not timesheets.blobs().enabled:
        raise HTTPException(503, "Stockage des photos et mémos non configuré (variable STAFF_BUCKET)")
    data = await request.body()
    try:
        return timesheets.add_attachment(eid, filename, (request.headers.get("content-type") or "").lower(), data, user, r)
    except Exception as ex:
        _ts_err(ex)


@app.delete("/api/timesheets/entries/{eid}/attachments/{aid}")
def ts_remove_attachment(eid: str, aid: str, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    try:
        timesheets.remove_attachment(eid, aid, user, r)
    except Exception as ex:
        _ts_err(ex)
    return {"deleted": aid}


@app.get("/api/timesheets/entries/{eid}/attachments/{aid}")
def ts_get_attachment(eid: str, aid: str, user: str = Depends(require_user)):
    r = _ts_ctx(user)
    e = timesheets.entries().get(eid)
    att = next((a for a in (e or {}).get("attachments", []) if a["id"] == aid), None)
    if not e or not att:
        raise HTTPException(404, "Pièce jointe introuvable")
    if e["user"] != user.lower() and not timesheets.chef_for(r, timesheets.jobs().get(e["job_id"])):
        raise HTTPException(403, "Accès refusé")
    got = timesheets.blobs().get(att["key"])
    if not got:
        raise HTTPException(404, "Fichier introuvable")
    return RawResponse(got[0], media_type=got[1], headers={"Cache-Control": "private, max-age=3600"})


# ---- Consigner › Congés ---------------------------------------------------------------------------------------------------------------------

def _lv_err(e: Exception):
    if isinstance(e, PermissionError):
        raise HTTPException(403, str(e))
    if isinstance(e, KeyError):
        raise HTTPException(404, "Demande introuvable")
    if isinstance(e, ValueError):
        raise HTTPException(422, str(e))
    raise e


@app.get("/api/leaves/me")
def lv_me(year: int | None = None, user: str = Depends(require_user)):
    y = year or date.today().year
    p = timesheets.person_of(user)
    mine = sorted((leaves.view(r, user) for r in leaves.requests().all() if r["user"] == user.lower()), key=lambda r: r["start"], reverse=True)
    deciding = sorted((leaves.view(r, user) for r in leaves.requests().all() if r["status"] == "pending" and leaves.can_decide(user, r)), key=lambda r: r["start"])
    today = date.today().isoformat()
    upcoming = []
    if deciding or users.is_super(user) or (timesheets.role_of(user)["role"] == "chef"):
        upcoming = sorted((leaves.view(r, user) for r in leaves.requests().all() if r["status"] == "approved" and r["end"] >= today and leaves.can_decide(user, r)), key=lambda r: r["start"])[:30]
    return {"year": y, "person": {"name": (p or {}).get("name", ""), "linked": bool(p)}, "types": [{"id": t[0], "label": t[1], "balance": t[2], "proof_over_one_day": t[3]} for t in leaves.TYPES],
            "balances": leaves.balances(p, user, y) if p else [], "requests": mine, "to_decide": deciding, "upcoming": upcoming}


@app.get("/api/leaves/preview")
def lv_preview(start: date, end: date, start_half: str = "full", end_half: str = "full", user: str = Depends(require_user)):
    if end < start or (end - start).days > 366 or start_half not in ("full", "pm") or end_half not in ("full", "am"):
        raise HTTPException(422, "Période invalide")
    return {"days": sum(leaves.day_values(timesheets.person_of(user), start, end, start_half, end_half).values())}


@app.post("/api/leaves")
def lv_create(body: leaves.LeaveIn, user: str = Depends(require_user)):
    try:
        return leaves.view(leaves.create(body, user), user)
    except Exception as e:
        _lv_err(e)


@app.put("/api/leaves/{rid}")
def lv_update(rid: str, body: leaves.LeaveIn, user: str = Depends(require_user)):
    try:
        return leaves.view(leaves.update(rid, body, user), user)
    except Exception as e:
        _lv_err(e)


@app.delete("/api/leaves/{rid}")
def lv_cancel(rid: str, user: str = Depends(require_user)):
    try:
        return leaves.view(leaves.cancel(rid, user), user)
    except Exception as e:
        _lv_err(e)


@app.post("/api/leaves/{rid}/approve")
def lv_approve(rid: str, user: str = Depends(require_user)):
    try:
        return leaves.view(leaves.decide(rid, True, "", user), user)
    except Exception as e:
        _lv_err(e)


class RefuseBody(BaseModel):
    reason: str = Field(min_length=1, max_length=500)


@app.post("/api/leaves/{rid}/refuse")
def lv_refuse(rid: str, body: RefuseBody, user: str = Depends(require_user)):
    try:
        return leaves.view(leaves.decide(rid, False, body.reason, user), user)
    except Exception as e:
        _lv_err(e)


@app.post("/api/leaves-proofs")
async def lv_add_proof(request: Request, filename: str = Query("justificatif", max_length=120), user: str = Depends(require_user)):
    if not timesheets.blobs().enabled:
        raise HTTPException(503, "Stockage des justificatifs non configuré (variable TIMESHEETS_BUCKET)")
    data = await request.body()
    try:
        return leaves.add_proof(user, filename, request.headers.get("content-type") or "", data)
    except Exception as e:
        _lv_err(e)


@app.get("/api/leaves-proofs/{pid}")
def lv_get_proof(pid: str, user: str = Depends(require_user)):
    d = leaves.proofs().get(pid)
    if not d:
        raise HTTPException(404, "Justificatif introuvable")
    req = next((r for r in leaves.requests().all() if pid in r.get("proofs", [])), None)
    if d["user"] != user.lower() and not users.is_super(user) and not (req and leaves.can_decide(user, req)):
        raise HTTPException(403, "Accès refusé")
    got = timesheets.blobs().get(d["key"])
    if not got:
        raise HTTPException(404, "Fichier introuvable")
    return RawResponse(got[0], media_type=d["ctype"], headers={"Cache-Control": "private, max-age=600"})


@app.get("/api/events/config")
def events_config(_user: str = Depends(granted("planifier/events"))):
    cals = planning.calendars_by_bu()
    return {"bus": [{"id": k, "label": v[0], "calendar": k in cals} for k, v in planning.BUS.items() if _bu_ok(_user, k)], "travel_days": settings.EVENT_TRAVEL_DAYS,
            "maps": maps.configured(), "origin": settings.LIFELIVE_ORIGIN, "calendar": gcal.configured() or settings.PROVIDER == "demo", "delegation": gauth.configured() or settings.PROVIDER == "demo"}


@app.get("/api/events")
def list_planned_events(date_from: date = Query(..., alias="from"), date_to: date = Query(..., alias="to"), _user: str = Depends(granted("planifier/events"))):
    try:
        return {"events": [e for e in planning.listing(date_from, date_to) if _bu_ok(_user, e["bu"])]}
    except Exception as e:
        log.exception("Lecture des événements impossible")
        return {"events": [], "unavailable": f"Agendas Google momentanément indisponibles : {e}"}


def _plan_error(e: Exception):
    if isinstance(e, KeyError):
        raise HTTPException(404, "Événement introuvable")
    if isinstance(e, LookupError):
        raise HTTPException(422, str(e))
    log.exception("Écriture dans Google Agenda impossible")
    raise HTTPException(503, f"Google Agenda indisponible : {e}")


@app.post("/api/events")
def create_planned_event(body: planning.EventIn, _user: str = Depends(granted("planifier/events"))):
    if not _bu_ok(_user, body.bu):
        raise HTTPException(403, "Vous ne gérez pas les événements de cette BU")
    try:
        return planning.create(body)
    except Exception as e:
        _plan_error(e)


@app.put("/api/events/{lbid}")
def update_planned_event(lbid: str, body: planning.EventIn, _user: str = Depends(granted("planifier/events"))):
    try:
        if not (_bu_ok(_user, body.bu) and _bu_ok(_user, planning.event_bu(lbid))):
            raise HTTPException(403, "Vous ne gérez pas les événements de cette BU")
        return planning.update(lbid, body)
    except HTTPException:
        raise
    except Exception as e:
        _plan_error(e)


@app.delete("/api/events/{lbid}")
def delete_planned_event(lbid: str, _user: str = Depends(granted("planifier/events"))):
    try:
        if not _bu_ok(_user, planning.event_bu(lbid)):
            raise HTTPException(403, "Vous ne gérez pas les événements de cette BU")
        if not planning.remove(lbid):
            raise KeyError(lbid)
        return {"deleted": lbid}
    except HTTPException:
        raise
    except Exception as e:
        _plan_error(e)


@app.post("/api/events/busy")
def events_busy(body: planning.BusyBody, _user: str = Depends(granted("planifier/events"))):
    """Réservations existantes des ressources sur la période : {adresse: [{start, end}]}"""
    try:
        return {"busy": planning.busy(body.emails, body.start, body.end)}
    except Exception as e:
        log.exception("Disponibilité des ressources indisponible")
        return {"busy": {}, "unavailable": f"Disponibilité momentanément indisponible : {e}"}


@app.get("/api/places/autocomplete")
def places_autocomplete(q: str = Query(..., min_length=3, max_length=100), _user: str = Depends(granted("planifier/events"))):
    if not maps.configured():
        raise HTTPException(503, "La recherche de lieux n’est pas configurée (clé GOOGLE_MAPS_API_KEY).")
    try:
        return {"suggestions": maps.autocomplete(q)}
    except Exception as e:
        log.exception("Recherche de lieux impossible")
        raise HTTPException(503, f"Recherche de lieux indisponible : {e}")


@app.get("/api/places/{place_id}")
def place_details(place_id: str, origin: str | None = Query(None, max_length=300), route: bool = True, _user: str = Depends(granted("planifier/events"))):
    """Lieu choisi + trajet (distance, durée, alertes Suisse / Royaume-Uni) depuis `origin` (identifiant de lieu Google) ou, par défaut, depuis Lifelive. `route=false` : le lieu seul."""
    try:
        place = maps.details(place_id)
    except KeyError:
        raise HTTPException(404, "Lieu introuvable")
    except Exception as e:
        log.exception("Détail du lieu impossible")
        raise HTTPException(503, f"Lieu indisponible : {e}")
    if not route:
        return {"place": place, "route": None}
    try:
        start = maps.details(origin) if origin else None
        rt = maps.route(place, start)
    except KeyError:
        raise HTTPException(404, "Lieu de départ introuvable")
    except Exception as e:
        log.exception("Calcul de l'itinéraire impossible")
        rt = {"km": None, "minutes": None, "via": [], "alerts": [], "unavailable": f"Itinéraire non calculé : {e}"}
    return {"place": place, "route": rt}


@app.get("/api/resources/contacts")
def resource_contacts(q: str = Query(..., min_length=2, max_length=60), _user: str = Depends(granted("planifier/res_ext"))):
    try:
        return {"contacts": provider().contacts(q)}
    except Exception as e:
        log.exception("Recherche de contacts impossible")
        return {"contacts": [], "unavailable": f"Recherche momentanément indisponible : {e}"}


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
        raise HTTPException(403, "Modification réservée aux administrateurs de Logbook")
    ids = [i.id for i in payload.items]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Identifiants d'ajustement en double")
    try:
        doc = adjustments.store().put([i.model_dump() for i in payload.items], user)
    except Exception:
        log.exception("Enregistrement des ajustements impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    return {**doc, "can_edit": True}


_proj_cache: dict = {}


@app.get("/api/projection")
def get_projection(year: int = Query(..., ge=2000, le=2100), refresh: bool = False, user: str = Depends(require_user)):
    """CA espéré des mois à venir (XC et CARS) et CA / marge brute mensuels réalisés."""
    try:
        doc = projection.store().get()
    except Exception:
        log.exception("Lecture des hypothèses de projection impossible")
        doc = {"years": {}, "updated_at": None, "updated_by": None}
    hit = _proj_cache.get(year)
    if not hit or refresh or time.time() - hit[0] > 900:
        try:
            try:
                prev = projection.previous_year(provider(), aggregate, year - 1)
            except Exception:
                log.exception("CA mensuel de l'année précédente indisponible")
                prev = []
            hit = (time.time(), projection.monthly(provider(), aggregate, year, date.today()), prev)
        except Exception:
            log.exception("CA mensuel indisponible")
            raise HTTPException(502, "CA mensuel indisponible pour le moment")
        _proj_cache[year] = hit
    return {"year": year, "months": hit[1], "prev_months": hit[2], "expected": doc["years"].get(str(year), {"XC": {}, "CARS": {}}), "updated_at": doc.get("updated_at"), "updated_by": doc.get("updated_by"),
            "can_edit": adjustments.can_edit(user), "can_save": adjustments.can_reference(user)}


@app.put("/api/projection")
def put_projection(payload: projection.Payload, user: str = Depends(reference)):
    try:
        doc = projection.store().put(payload.year, payload.expected, user)
    except Exception:
        log.exception("Enregistrement des hypothèses de projection impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    return {"year": payload.year, "expected": payload.expected, "updated_at": doc["updated_at"], "updated_by": doc["updated_by"], "can_edit": True, "can_save": True}


@app.get("/api/stockvar")
def get_stockvar(user: str = Depends(require_user)):
    """Variations de stock saisies à la main (lisibles par tous ; modifiables par les propriétaires des hypothèses)."""
    try:
        doc = stockvar.store().get()
    except Exception:
        log.exception("Lecture des variations de stock impossible")
        return {"items": [], "updated_at": None, "updated_by": None, "can_edit": adjustments.can_edit(user), "can_save": adjustments.can_reference(user),
                "error": "Variations de stock indisponibles (stockage non configuré ou inaccessible)."}
    return {**doc, "can_edit": adjustments.can_edit(user), "can_save": adjustments.can_reference(user)}


@app.put("/api/stockvar")
def put_stockvar(payload: stockvar.Payload, user: str = Depends(reference)):
    ids = [i.id for i in payload.items]
    if len(set(ids)) != len(ids):
        raise HTTPException(422, "Identifiants en double")
    try:
        doc = stockvar.store().put([i.model_dump() for i in payload.items], user)
    except Exception:
        log.exception("Enregistrement des variations de stock impossible")
        raise HTTPException(503, "Enregistrement impossible (stockage non configuré ou inaccessible)")
    return {**doc, "can_edit": True, "can_save": True}


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
    data = _dashboard(date_from, date_to, refresh)
    return data if users.pages_of(_user) is None else _scoped(data, _user)


def _scoped(d: dict, user: str) -> dict:
    return access.scope_view(d, users.pages_of(user), aggregate({}))


def _dashboard(date_from, date_to, refresh):
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
