"""Roulages › Garage : informations permanentes et documents d'une voiture, chacun avec une date limite de validité.

Une alerte apparaît sur la fiche de la voiture et sur l'accueil (Super User et chef d'atelier de la BU) à `weeks` semaines de l'échéance (3 par défaut, réglable
par élément) ; un e-mail leur est envoyé la veille de l'expiration (`send_expiry_mails`, appelé chaque jour par Cloud Scheduler).
Données : dans le document de la voiture (`ride_cars`, champ `docs`) ; fichiers dans le bucket des pointages, préfixe `rides/docs/`."""
import re
import uuid
from datetime import date, datetime, timedelta, timezone

from pydantic import BaseModel, field_validator

from . import rides, timesheets
from . import settings

DEFAULT_WEEKS = 3
MAX_FILE = 10 * 1024 * 1024
MAX_FILES = 10
TYPES = {"application/pdf": "pdf", "image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}

# (clé, libellé, voitures concernées : rally, circuit ou all)
ITEMS = [
    ("conformity", "Certificat de conformité", "rally"),
    ("insurance", "Assurance", "rally"),
    ("inspection", "Contrôle technique autosécurité", "rally"),
    ("fia", "Passeport FIA", "all"),
    ("asn", "Passeport ASN", "all"),
    ("fuel_tank", "Certificat réservoir essence", "all"),
    ("extinguisher", "Validité extincteur", "all"),
    ("harness", "Validité harnais", "all"),
    ("seat", "Validité siège", "all"),
    ("other_safety", "Validité autres éléments de sécurité", "all"),
    ("transponder", "Transpondeur", "circuit"),
]
LABEL = {k: l for k, l, _ in ITEMS}


class DocIn(BaseModel):
    expires: str | None = None                  # AAAA-MM-JJ ; chaîne vide = pas de date
    note: str | None = None
    weeks: int | None = None                    # alerte à x semaines de l'échéance ; 0 ou vide = 3 par défaut

    @field_validator("expires")
    @classmethod
    def _exp(cls, v):
        if v:
            try:
                date.fromisoformat(v)
            except ValueError:
                raise ValueError("Date limite invalide")
        return v

    @field_validator("weeks")
    @classmethod
    def _w(cls, v):
        if v is not None and not 0 <= v <= 52:
            raise ValueError("Délai d'alerte : de 1 à 52 semaines")
        return v


def today() -> date:
    from . import presence
    return presence.local_now().date()


def applies(item: tuple, category: str) -> bool:
    return item[2] in ("all", category)


def status(expires: str | None, weeks: int, now: date) -> str:
    """none (pas de date) | ok | warn (dans le délai d'alerte) | over (échu)."""
    if not expires:
        return "none"
    d = date.fromisoformat(expires)
    if d < now:
        return "over"
    return "warn" if d <= now + timedelta(weeks=weeks) else "ok"


def _public_file(f: dict) -> dict:
    return {k: v for k, v in f.items() if k != "key"}


def view(key: str, now: date | None = None) -> list[dict]:
    c = rides.car_of(key)
    if not c:
        raise LookupError("Voiture introuvable")
    now = now or today()
    docs = (rides.cars_coll().get(key) or {}).get("docs", {})
    out = []
    for it in ITEMS:
        if not applies(it, c["category"]):
            continue
        d = docs.get(it[0], {})
        w = d.get("weeks") or DEFAULT_WEEKS
        exp = d.get("expires") or ""
        out.append({"item": it[0], "label": it[1], "expires": exp, "note": d.get("note", ""), "weeks": w, "custom_weeks": bool(d.get("weeks")),
                    "state": status(exp, w, now), "days": (date.fromisoformat(exp) - now).days if exp else None,
                    "files": [_public_file(f) for f in d.get("files", [])]})
    return out


def alerts_of(key: str, now: date | None = None) -> list[dict]:
    return [d for d in view(key, now) if d["state"] in ("warn", "over")]


def _item(item: str, category: str) -> tuple:
    it = next((i for i in ITEMS if i[0] == item), None)
    if not it or not applies(it, category):
        raise LookupError("Élément inconnu pour cette voiture")
    return it


def set_doc(key: str, item: str, data: DocIn) -> list[dict]:
    c = rides.car_of(key)
    if not c:
        raise LookupError("Voiture introuvable")
    _item(item, c["category"])
    meta = rides.cars_coll().get(key) or {"id": key}
    d = meta.setdefault("docs", {}).setdefault(item, {})
    if data.expires is not None:
        d["expires"] = data.expires
    if data.note is not None:
        d["note"] = data.note.strip()[:1000]
    if data.weeks is not None:
        d["weeks"] = data.weeks or 0
    rides.cars_coll().put(key, meta)
    return view(key)


def add_file(key: str, item: str, name: str, ctype: str, data: bytes) -> list[dict]:
    c = rides.car_of(key)
    if not c:
        raise LookupError("Voiture introuvable")
    _item(item, c["category"])
    ctype = ctype.split(";")[0].strip().lower()
    if ctype not in TYPES:
        raise ValueError("Documents : PDF, JPEG, PNG ou WebP seulement")
    if not data or len(data) > MAX_FILE:
        raise ValueError("Fichier vide ou trop volumineux (10 Mo maximum)")
    meta = rides.cars_coll().get(key) or {"id": key}
    d = meta.setdefault("docs", {}).setdefault(item, {})
    if len(d.get("files", [])) >= MAX_FILES:
        raise ValueError(f"{MAX_FILES} fichiers au maximum par élément")
    fid = uuid.uuid4().hex[:10]
    k = f"rides/docs/{key}/{item}/{fid}.{TYPES[ctype]}"
    timesheets.blobs().put(k, data, ctype)
    d.setdefault("files", []).append({"id": fid, "name": re.sub(r"[^\w .()\-]", "_", name or "document")[:80], "ctype": ctype, "size": len(data), "key": k,
                                      "created_at": datetime.now(timezone.utc).isoformat()})
    rides.cars_coll().put(key, meta)
    return view(key)


def _file(key: str, item: str, fid: str) -> tuple[dict, dict, dict]:
    meta = rides.cars_coll().get(key) or {}
    d = (meta.get("docs") or {}).get(item) or {}
    f = next((f for f in d.get("files", []) if f["id"] == fid), None)
    if not f:
        raise LookupError("Fichier introuvable")
    return meta, d, f


def get_file(key: str, item: str, fid: str) -> tuple[bytes, str, str]:
    _, _, f = _file(key, item, fid)
    got = timesheets.blobs().get(f["key"])
    if not got:
        raise LookupError("Fichier introuvable")
    return got[0], f["ctype"], f["name"]


def delete_file(key: str, item: str, fid: str) -> list[dict]:
    meta, d, f = _file(key, item, fid)
    timesheets.blobs().delete(f["key"])
    d["files"] = [x for x in d["files"] if x["id"] != fid]
    rides.cars_coll().put(key, meta)
    return view(key)


def purge(key: str) -> None:
    """Suppression définitive d'une voiture : ses fichiers partent aussi."""
    for d in ((rides.cars_coll().get(key) or {}).get("docs") or {}).values():
        for f in d.get("files", []):
            timesheets.blobs().delete(f["key"])


# ---- Alertes (accueil, e-mail) ----------------------------------------------------------------------------------------------------------

def viewer(email: str) -> dict | None:
    """Qui voit les alertes : le Super User (toutes les voitures) et le chef d'atelier (celles de sa BU) ; sinon None."""
    r = timesheets.role_of(email)
    return r if r["role"] == "chef" else None


def visible(r: dict, bu: str) -> bool:
    return r["super"] or timesheets.bu_group(bu or "CARS") in r["bus"]


def all_alerts(r: dict, now: date | None = None) -> list[dict]:
    out = []
    for c in rides.race_cars():
        meta = rides.cars_coll().get(c["key"]) or {}
        if meta.get("archived") or not visible(r, meta.get("bu", "")):
            continue
        for a in alerts_of(c["key"], now):
            out.append({"car": c["key"], "car_name": c["name"], "bu": meta.get("bu", ""), **{k: a[k] for k in ("item", "label", "expires", "state", "days")}})
    return sorted(out, key=lambda a: (a["expires"], a["car_name"]))


def recipients() -> list[tuple[str, dict]]:
    from . import users
    seen, out = set(), []
    for e in users.supers():
        e = e.lower()
        if e not in seen:
            seen.add(e); out.append((e, timesheets.role_of(e)))
    for p in timesheets.workshop_people():
        e = p["google_email"].lower()
        r = timesheets.role_of(e)
        if r["role"] == "chef" and e not in seen:
            seen.add(e); out.append((e, r))
    return out


_sent = None


def _sent_coll():
    global _sent
    from . import timesheets as ts
    _sent = _sent or ts._alerts()                            # même stockage que les rappels de pointage, clés distinctes
    return _sent


def send_expiry_mails(now: date | None = None) -> dict:
    """La veille de l'échéance : e-mail au Super User et au chef d'atelier de la BU ; une seule fois par élément, échéance et destinataire."""
    from . import mailer
    now = now or today()
    tomorrow = (now + timedelta(days=1)).isoformat()
    sent = []
    for em, r in recipients():
        for a in all_alerts(r, now):
            if a["expires"] != tomorrow:
                continue
            k = f"vdoc:{a['car']}:{a['item']}:{a['expires']}:{em}"
            if _sent_coll().get(k):
                continue
            link = f"\n\nFiche de la voiture : {settings.PUBLIC_URL}/#/consigner/rides" if settings.PUBLIC_URL else ""
            mailer.send(em, f"Logbook — « {a['label']} » expire demain ({a['car_name']})",
                        f"Bonjour,\n\n« {a['label']} » de la voiture {a['car_name']} expire demain ({date.fromisoformat(a['expires']).strftime('%d/%m/%Y')}).\n\nPensez à le renouveler et à déposer le nouveau document dans la fiche de la voiture (Roulages › Garage).{link}\n\nLogbook — Lifelive Motorsport")
            _sent_coll().put(k, {"id": k, "at": datetime.now(timezone.utc).isoformat()})
            sent.append({"to": em, "car": a["car_name"], "item": a["item"]})
    return {"date": now.isoformat(), "sent": sent}
