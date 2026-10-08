from __future__ import annotations

import re
import logging
import time
from datetime import date, datetime, timezone
from pathlib import Path

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.responses import FileResponse, Response as RawResponse
from fastapi.staticfiles import StaticFiles

from . import adjustments, dkv, expenses, ga, gcal, settings, staff, stockvar, tn11
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
        raise HTTPException(403, "Réservé aux administrateurs du dashboard")
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
