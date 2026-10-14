"""Administrer › Accès clients : espace réservé aux clients de Lifelive Motorsport (lecture seule).

Un client = un nom, des adresses e-mail autorisées et des voitures du Garage (`clients`, géré par le Super User). Il ouvre l'espace avec un lien magique envoyé par e-mail
(valable 15 minutes, à usage unique, stocké sous forme d'empreinte) puis un cookie de session propre (`lm_client`, signé, HttpOnly) : ce cookie n'ouvre AUCUNE route
interne (`require_user` ne le lit pas) et les routes `/api/client/*` ne lisent que lui. Chaque requête revérifie que l'adresse est toujours autorisée, donc un retrait
est immédiat. Le client ne voit que ses voitures : identité, documents (sans les notes internes), roulages, et les jobs de ces voitures avec leurs pointages VALIDÉS
(sans nom de mécanicien, sans durée facturée ni coût, sans mémo vocal)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field, field_validator

from . import rides, settings, timesheets, vdocs
from .timesheets import Coll

COOKIE = "lm_client"
LINK_MINUTES = 15
SESSION_DAYS = 14
MAX_LINKS_PER_HOUR = 5
EMAIL = re.compile(r"^[^@\s,;]+@[^@\s,;]+\.[^@\s,;]+$")
_FALLBACK = secrets.token_hex(16)                                    # démo / essais sans SESSION_SECRET : les sessions ne survivent pas à un redémarrage

_clients = _links = _audit = None


def clients_coll() -> Coll:
    global _clients
    _clients = _clients or Coll("clients")
    return _clients


def links_coll() -> Coll:
    global _links
    _links = _links or Coll("client_links")
    return _links


def audit_coll() -> Coll:
    global _audit
    _audit = _audit or Coll("client_audit")
    return _audit


def now() -> datetime:
    return datetime.now(timezone.utc)


def _log(email: str, action: str, detail: str = "") -> None:
    i = uuid.uuid4().hex[:12]
    audit_coll().put(i, {"id": i, "at": now().isoformat(), "email": email, "action": action, "detail": detail[:200]})


# ---- Fiches clients (Super User) -----------------------------------------------------------------------------------------------------------

class ClientIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    emails: list[str] = Field(default_factory=list, max_length=10)
    cars: list[str] = Field(default_factory=list, max_length=60)      # clés des voitures du Garage
    active: bool = True
    note: str = Field(default="", max_length=300)

    @field_validator("emails")
    @classmethod
    def _emails(cls, v):
        out = []
        for e in v:
            e = e.strip().lower()
            if not EMAIL.match(e):
                raise ValueError(f"adresse e-mail invalide : {e}")
            if e not in out:
                out.append(e)
        return out


def _car_label(key: str) -> dict:
    c = rides.car_of(key)
    meta = rides.cars_coll().get(key) or {}
    return {"key": key, "name": c["name"] if c else key, "exists": bool(c), "odoo": bool(meta.get("odoo_id")), "archived": bool(meta.get("archived"))}


def view(c: dict) -> dict:
    return {"id": c["id"], "name": c["name"], "emails": c.get("emails", []), "active": c.get("active", True), "note": c.get("note", ""), "cars": [_car_label(k) for k in c.get("cars", [])],
            "last_login": c.get("last_login", {}), "created_at": c.get("created_at")}


def list_clients() -> list[dict]:
    return [view(c) for c in sorted(clients_coll().all(), key=lambda c: c["name"].lower())]


def save_client(cid: str | None, data: ClientIn, user: str) -> dict:
    cur = clients_coll().get(cid) if cid else None
    if cid and not cur:
        raise LookupError("Client introuvable")
    known = {c["key"] for c in rides.race_cars()}
    bad = [k for k in data.cars if k not in known]
    if bad:
        raise ValueError("Voiture inconnue : " + bad[0])
    if any(c["id"] != cid and c["name"].strip().lower() == data.name.strip().lower() for c in clients_coll().all()):
        raise ValueError("Un client porte déjà ce nom")
    cid = cid or "c-" + uuid.uuid4().hex[:8]
    doc = {"id": cid, "name": data.name.strip(), "emails": data.emails, "cars": sorted(set(data.cars)), "active": data.active, "note": data.note.strip(),
           "last_login": (cur or {}).get("last_login", {}), "created_at": (cur or {}).get("created_at", now().isoformat()), "created_by": (cur or {}).get("created_by", user.lower()),
           "updated_at": now().isoformat(), "updated_by": user.lower()}
    clients_coll().put(cid, doc)
    return view(doc)


def delete_client(cid: str) -> None:
    if not clients_coll().get(cid):
        raise LookupError("Client introuvable")
    clients_coll().delete(cid)


PREVIEW = "preview:"
PREVIEW_HOURS = 2


def clients_of(email: str) -> list[dict]:
    e = (email or "").strip().lower()
    if e.startswith(PREVIEW):                                        # aperçu du Super User : « voir comme ce client » (aucune adresse réelle)
        c = clients_coll().get(e[len(PREVIEW):])
        return [c] if c else []
    return [c for c in clients_coll().all() if c.get("active", True) and e in c.get("emails", [])]


def audit_list(limit: int = 60) -> list[dict]:
    return sorted(audit_coll().all(), key=lambda a: a["at"], reverse=True)[:limit]


# ---- Lien magique et session ----------------------------------------------------------------------------------------------------------------

def _h(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def request_link(email: str, ip: str = "") -> bool:
    """Envoie un lien de connexion si l'adresse est celle d'un client actif. La réponse de l'API est toujours la même (on ne révèle pas quelles adresses existent) ;
    au plus 5 liens par heure et par adresse."""
    e = (email or "").strip().lower()
    if not EMAIL.match(e) or not clients_of(e):
        _log(e[:120], "link_refused", ip)
        return False
    since = (now() - timedelta(hours=1)).isoformat()
    if sum(1 for l in links_coll().all() if l["email"] == e and l["created_at"] >= since) >= MAX_LINKS_PER_HOUR:
        _log(e, "link_throttled", ip)
        return False
    token = secrets.token_urlsafe(32)
    links_coll().put(_h(token), {"id": _h(token), "email": e, "created_at": now().isoformat(), "exp": (now() + timedelta(minutes=LINK_MINUTES)).isoformat(), "used": False})
    from . import mailer
    base = settings.PUBLIC_URL.rstrip("/") if settings.PUBLIC_URL else ""
    url = f"{base}/client.html#t={token}"
    mailer.send(e, "Logbook — votre lien de connexion / your sign-in link",
                f"Bonjour,\n\nVoici votre lien de connexion à l'espace client Lifelive Motorsport (valable {LINK_MINUTES} minutes, utilisable une seule fois) :\n{url}\n\n"
                f"Si vous n'êtes pas à l'origine de cette demande, ignorez ce message.\n\n"
                f"Hello,\n\nHere is your sign-in link to the Lifelive Motorsport client area (valid for {LINK_MINUTES} minutes, single use):\n{url}\n\nIf you did not request it, please ignore this message.\n\nLifelive Motorsport — Logbook")
    _log(e, "link_sent", ip)
    return True


def consume_token(token: str, ip: str = "") -> str:
    """Valide un lien (existant, non utilisé, non expiré, adresse toujours cliente) et le brûle ; renvoie l'adresse."""
    doc = links_coll().get(_h(token or "")) if token else None
    if not doc or doc.get("used") or doc["exp"] < now().isoformat() or not clients_of(doc["email"]):
        _log((doc or {}).get("email", "?"), "login_refused", ip)
        raise ValueError("Lien invalide ou expiré : demandez-en un nouveau.")
    doc["used"] = True
    links_coll().put(doc["id"], doc)
    for c in clients_of(doc["email"]):
        c.setdefault("last_login", {})[doc["email"]] = now().isoformat()
        clients_coll().put(c["id"], c)
    _log(doc["email"], "login", ip)
    return doc["email"]


def _mac(body: str) -> str:
    key = (settings.SESSION_SECRET or _FALLBACK).encode()
    return base64.urlsafe_b64encode(hmac.new(key, b"client." + body.encode(), hashlib.sha256).digest()).rstrip(b"=").decode()


def make_session(email: str, t: float | None = None) -> str:
    t = int(t or time.time())
    life = PREVIEW_HOURS * 3600 if email.startswith(PREVIEW) else SESSION_DAYS * 86400
    body = base64.urlsafe_b64encode(json.dumps({"t": "client", "e": email, "exp": t + life}, separators=(",", ":")).encode()).rstrip(b"=").decode()
    return f"{body}.{_mac(body)}"


def read_session(value: str, t: float | None = None) -> str | None:
    """Adresse du client si le cookie est authentique, non expiré et que l'adresse est toujours celle d'un client actif."""
    if not value or "." not in value:
        return None
    body, mac = value.rsplit(".", 1)
    if not hmac.compare_digest(mac, _mac(body)):
        return None
    try:
        p = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if p.get("t") != "client" or p.get("exp", 0) < (t or time.time()) or not clients_of(p.get("e", "")):
        return None
    return p["e"]


# ---- Ce que voit un client ------------------------------------------------------------------------------------------------------------------

def car_keys(email: str) -> list[str]:
    keys: list[str] = []
    for c in clients_of(email):
        for k in c.get("cars", []):
            if k not in keys:
                keys.append(k)
    live = {c["key"] for c in rides.race_cars() if not (rides.cars_coll().get(c["key"]) or {}).get("archived")}
    return [k for k in keys if k in live]


def own(email: str, key: str) -> None:
    if key not in car_keys(email):
        raise LookupError("Voiture introuvable")


def me(email: str) -> dict:
    cs = clients_of(email)
    preview = email.startswith(PREVIEW)
    cars = []
    for k in car_keys(email):
        c = rides.car_of(k)
        meta = rides.cars_coll().get(k) or {}
        cars.append({"key": k, "name": c["name"], "category": c["category"], "photo": bool(meta.get("photo")), "race_number": meta.get("race_number", ""), "livery": meta.get("livery", "")})
    return {"email": "" if preview else email, "preview": preview, "clients": [{"id": c["id"], "name": c["name"]} for c in cs], "cars": sorted(cars, key=lambda c: c["name"].lower())}


def car_view(email: str, key: str) -> dict:
    own(email, key)
    c = rides.car_of(key)
    meta = rides.cars_coll().get(key) or {}
    runs = sorted(rides._runs_of(key), key=lambda r: r["date"], reverse=True)
    docs = [{k: d[k] for k in ("item", "label", "expires", "state", "days")} | {"files": [{"id": f["id"], "name": f["name"], "ctype": f["ctype"], "size": f["size"]} for f in d["files"]]} for d in vdocs.view(key)]
    return {"key": key, "name": c["name"], "category": c["category"], "photo": bool(meta.get("photo")), **{f: meta.get(f, "") for f in rides.IDENTITY}, "docs": docs,
            "runs": [{"id": r["id"], "date": r["date"], "name": r["name"], "kind": r.get("kind", "circuit"), "circuit": r.get("circuit", ""), "km": r.get("km"), "hours": r.get("hours")} for r in runs[:100]],
            "km_total": round(sum(r.get("km") or 0 for r in runs), 1)}


def _job_matches(job: dict, key: str, meta: dict, car_name: str) -> bool:
    v = job.get("vehicle")
    if not v:
        return False
    oid = str(meta.get("odoo_id") or "")
    if oid and str(v.get("id") or "") == oid:
        return True
    if not v.get("id"):                                              # job créé d'après le planning : rattaché au nom exact de la voiture
        norm = lambda x: re.sub(r"[^a-z0-9]+", "", rides._fold(x))          # égalité exacte du nom (jamais « proche ») : un job ne doit jamais aller chez un autre client
        names = [norm(n) for n in (car_name, meta.get("odoo_name", "")) if n]
        return bool(v.get("name")) and norm(v["name"]) in names
    return False


def jobs_of_car(email: str, key: str) -> list[dict]:
    own(email, key)
    c = rides.car_of(key)
    meta = rides.cars_coll().get(key) or {}
    ents_by_job: dict[str, list] = {}
    for e in timesheets.entries().all():
        if e.get("validated"):
            ents_by_job.setdefault(e["job_id"], []).append(e)
    sysl, asl = dict(timesheets.SYSTEMS), dict(timesheets.ASSIGNMENTS)
    out = []
    for j in timesheets.jobs().all():
        if not _job_matches(j, key, meta, c["name"]):
            continue
        lines = {ln["id"]: ln["text"] for s in (j.get("checklist") or {}).get("sections", []) for ln in s["lines"]}
        ents = []
        for e in sorted(ents_by_job.get(j["id"], []), key=lambda e: (e["date"], e.get("created_at", ""))):
            ents.append({"id": e["id"], "date": e["date"], "minutes": e["minutes"], "system": sysl.get(e.get("system"), ""), "assignment": asl.get(e.get("assignment"), ""), "text": "" if e.get("client_hidden") else e.get("text", ""), "text_hidden": bool(e.get("client_hidden") and e.get("text")),
                         "lines": [lines[i] for i in e.get("lines", []) if i in lines], "photos": [{"id": a["id"], "name": a.get("name", "")} for a in e.get("attachments", []) if a.get("kind") == "photo"]})
        checklist = [{"title": s["title"], "lines": [{"text": ln["text"], "done": bool(ln.get("done")), "done_at": (ln.get("done_at") or "")[:10]} for ln in s["lines"]]} for s in (j.get("checklist") or {}).get("sections", [])]
        out.append({"id": j["id"], "title": j.get("title", ""), "nature": timesheets.N_IDS.get(j.get("nature", ""), ""), "open": bool(j.get("open", True)), "created": (j.get("created_at") or "")[:10],
                    "event": (j.get("event") or {}).get("title", ""), "progress": timesheets.progress(j), "checklist": checklist, "entries": ents, "minutes": sum(x["minutes"] for x in ents)})
    return sorted(out, key=lambda j: j["created"], reverse=True)


def entry_photo(email: str, key: str, eid: str, aid: str) -> tuple[bytes, str]:
    own(email, key)
    e = timesheets.entries().get(eid)
    j = timesheets.jobs().get(e["job_id"]) if e else None
    c = rides.car_of(key)
    meta = rides.cars_coll().get(key) or {}
    att = next((a for a in (e or {}).get("attachments", []) if a["id"] == aid and a.get("kind") == "photo"), None)
    if not e or not e.get("validated") or not j or not att or not _job_matches(j, key, meta, c["name"]):
        raise LookupError("Photo introuvable")
    got = timesheets.blobs().get(att["key"])
    if not got:
        raise LookupError("Photo introuvable")
    return got[0], got[1]


def start_preview(cid: str, user: str) -> str:
    """Cookie d'aperçu (2 h) : le Super User voit exactement l'espace de ce client, même désactivé n'est pas permis (comme pour lui)."""
    c = clients_coll().get(cid)
    if not c:
        raise LookupError("Client introuvable")
    _log(user.lower(), "preview", c["name"])
    return make_session(PREVIEW + cid)
