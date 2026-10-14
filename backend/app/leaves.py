"""Consigner › Congés et Absences : demandes de congé, déclarations d'absence, soldes, validation, agenda Google « warnings » et rappel par e-mail.

Deux familles : les CONGÉS (congés payés, compensation, extra-légal, récupération de jour férié, congé sans solde) se demandent à l'avance et se font approuver ; les ABSENCES justifiées
(maladie, congé de circonstance, autre absence justifiée) se DÉCLARENT : elles prennent effet aussitôt (agenda, Planning, alertes) et le chef d'atelier ou le Managing Director « prend acte »
(accusé de réception) ; justificatif obligatoire pour une maladie de plus d'un jour. Le motif d'une absence n'est visible que de la personne, de son validateur et du Super User : le Planning, le
Cockpit et l'agenda partagé n'affichent que « Absent(e) ». Un congé sans solde reste un congé (demande à l'avance, approbation) mais n'entame aucun solde et n'est pas rémunéré.

Une demande est approuvée par le chef d'atelier pour les mécaniciens de son équipe (même BU), par le Managing Director (Super User) pour les chefs d'atelier et le reste du personnel. Une fois
approuvée, elle apparaît dans le Planning et dans l'agenda Google « warnings » (Google Agenda reste la référence des absences) ; elle est écrite dans Odoo plus tard (phase 4, champ odoo_id).
Les soldes de départ se saisissent dans Coûts du personnel › Données source (champ leave_alloc de la fiche). Données : Firestore (collections leave_requests et leave_proofs)."""
from __future__ import annotations

import logging
import re
import uuid
from datetime import date, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from . import settings, users
from .timesheets import Coll, blobs, person_of, now

log = logging.getLogger("logbook")

# (identifiant, libellé, a un solde, justificatif obligatoire au-delà d'un jour, famille « leave » / « absence », rémunéré)
TYPES = [("paid", "Congés payés", True, False, "leave", True), ("comp", "Jours de compensation", True, False, "leave", True), ("extra", "Congé extra-légal", True, False, "leave", True),
         ("recup", "Récupération de jour férié", True, False, "leave", True), ("other", "Congé sans solde", False, False, "leave", False),
         ("sick", "Maladie", False, True, "absence", True), ("circ", "Congé de circonstance", False, False, "absence", True), ("misc", "Autre absence justifiée", False, False, "absence", True)]
T = {t[0]: t for t in TYPES}
EFFECTIVE = ("approved", "declared", "acknowledged")                     # statuts qui comptent : agenda, Planning, alertes de pointage
AWAIT = ("pending", "declared")                                           # en attente d'une décision (congé) ou d'une prise d'acte (absence)


def kind_of(t: str) -> str:
    return T[t][4]
PROOF_MAX = 8 * 1024 * 1024
PROOF_DAYS = 90                                                        # conservation d'un justificatif après son dépôt (règle de cycle de vie du bucket : 91 jours, préfixe leaves/)
PROOF_TYPES = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


class LeaveIn(BaseModel):
    type: str
    start: date
    end: date
    start_half: Literal["full", "pm"] = "full"           # « pm » : le congé commence l'après-midi
    end_half: Literal["full", "am"] = "full"             # « am » : le congé se termine à midi
    comment: str = Field(default="", max_length=500)
    proofs: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _check(self):
        if self.type not in T:
            raise ValueError("type de congé inconnu")
        if self.end < self.start:
            raise ValueError("la fin précède le début")
        if (self.end - self.start).days > 366:
            raise ValueError("période trop longue")
        if self.start < date.today() - timedelta(days=62):
            raise ValueError("une demande ne peut pas remonter à plus de deux mois")
        return self


_reqs = _proofs = None


def requests() -> Coll:
    global _reqs
    _reqs = _reqs or Coll("leave_requests")
    return _reqs


def proofs() -> Coll:
    global _proofs
    _proofs = _proofs or Coll("leave_proofs")
    return _proofs


# ---- Jours et soldes ------------------------------------------------------------------------------------------------------------------------

def day_values(person: dict | None, start: date, end: date, sh: str, eh: str) -> dict[date, float]:
    """Valeur de chaque jour ouvré de la période (1, ou 0,5 pour une demi-journée)."""
    from . import presence
    out: dict[date, float] = {}
    d = start
    while d <= end:
        if presence.is_workday(d, person):
            v = 1.0
            if start == end:
                v = 0.5 if (sh == "pm" or eh == "am") else 1.0
            elif d == start and sh == "pm":
                v = 0.5
            elif d == end and eh == "am":
                v = 0.5
            out[d] = v
        d += timedelta(days=1)
    return out


def days_of(person: dict | None, r: dict) -> float:
    return sum(day_values(person, date.fromisoformat(r["start"]), date.fromisoformat(r["end"]), r["start_half"], r["end_half"]).values())


def balances(person: dict | None, email: str, year: int) -> list[dict]:
    """Par type à solde : alloué, pris (approuvé), en attente, restant."""
    alloc = ((person or {}).get("leave_alloc") or {}).get(str(year), {})
    used: dict[str, float] = {}
    pend: dict[str, float] = {}
    for r in requests().all():
        if r["user"] != email.lower() or r["status"] not in ("approved", "pending"):
            continue
        dv = day_values(person, date.fromisoformat(r["start"]), date.fromisoformat(r["end"]), r["start_half"], r["end_half"])
        n = sum(v for d, v in dv.items() if d.year == year)
        (used if r["status"] == "approved" else pend)[r["type"]] = (used if r["status"] == "approved" else pend).get(r["type"], 0) + n
    return [{"type": t[0], "label": t[1], "allocated": alloc.get(t[0], 0), "used": used.get(t[0], 0), "pending": pend.get(t[0], 0), "remaining": alloc.get(t[0], 0) - used.get(t[0], 0)} for t in TYPES if t[2]]


# ---- Qui valide ---------------------------------------------------------------------------------------------------------------------------

def _groups(person: dict | None) -> set[str]:
    """BU de l'équipe d'un mécanicien : XC et / ou CARS, d'après ses BU de ressource (toutes les BU si aucune ou « toutes »)."""
    from . import staff
    if not person or person.get("all_bus"):
        return {"XC", "CARS"}
    out = {"XC" if k == "XC" else "CARS" for k in staff.resource_bus(person)}
    return out or {"XC", "CARS"}


def can_decide(approver: str, req: dict) -> bool:
    from . import timesheets
    if users.is_super(approver):
        return True
    p = person_of(req["user"])
    if (p or {}).get("workshop") != "mechanic" or approver.lower() == req["user"]:
        return False                                              # chefs d'atelier et autres : Managing Director seulement
    r = timesheets.role_of(approver)
    return r["role"] == "chef" and bool(set(r["bus"]) & _groups(p))


def approvers_of(req: dict) -> list[str]:
    from . import staff, timesheets
    out = [e.lower() for e in users.supers()]
    p = person_of(req["user"])
    if (p or {}).get("workshop") == "mechanic":
        out = [x["google_email"].lower() for x in staff.store().get()["data"]["people"] if x.get("google_email") and x.get("active", True) and x.get("workshop", "").startswith("chef_")
               and can_decide(x["google_email"], req)] or out
    return [e for e in dict.fromkeys(out) if e != req["user"]]


# ---- Agenda Google « warnings » -----------------------------------------------------------------------------------------------------------

_cal_id = None


def calendar_id() -> str:
    global _cal_id
    if settings.LEAVE_CALENDAR_ID:
        return settings.LEAVE_CALENDAR_ID
    if settings.PROVIDER == "demo":
        return "demo-warnings@group.calendar.google.com"
    if _cal_id is None:
        from . import gauth
        r = gauth.session((gauth.SCOPE_CALENDAR,)).get("https://www.googleapis.com/calendar/v3/users/me/calendarList", params={"minAccessRole": "writer", "maxResults": 250}, timeout=30)
        if r.status_code != 200:
            raise RuntimeError(f"Liste des agendas indisponible (HTTP {r.status_code})")
        found = [c["id"] for c in r.json().get("items", []) if c.get("summary", "").strip().lower() == "warnings"]
        if not found:
            raise RuntimeError("Agenda « warnings » introuvable : partagez-le en modification avec le compte Logbook ou renseignez LEAVE_CALENDAR_ID")
        _cal_id = found[0]
    return _cal_id


def _event_body(req: dict, name: str) -> dict:
    label = "Absence" if kind_of(req["type"]) == "absence" else T[req["type"]][1]                  # le motif d'une absence n'apparaît jamais dans l'agenda partagé
    half = " (après-midi)" if req["start_half"] == "pm" and req["start"] == req["end"] else " (matin)" if req["end_half"] == "am" and req["start"] == req["end"] else ""
    return {"summary": f"{name} — {label}{half}", "start": {"date": req["start"]}, "end": {"date": (date.fromisoformat(req["end"]) + timedelta(days=1)).isoformat()}, "transparency": "transparent",
            "extendedProperties": {"shared": {"logbook": "1", "kind": "leave", "lbid": req["id"]}}}


def sync_calendar(req: dict, create: bool) -> None:
    """Crée (approbation) ou supprime (annulation) l'événement d'absence ; une erreur est mémorisée sur la demande sans bloquer la décision."""
    from . import planning
    try:
        b, cal = planning.backend(), calendar_id()
        if create:
            name = (person_of(req["user"]) or {}).get("name") or req["user"]
            req["event_id"] = b.insert(cal, _event_body(req, name), False)["id"]
        elif req.get("event_id"):
            b.delete(cal, req["event_id"], False)
            req["event_id"] = None
        req["calendar_error"] = None
    except Exception as e:
        log.exception("Agenda des absences indisponible")
        req["calendar_error"] = str(e)[:300]


def absences(emails: set[str], d_from: date, d_to: date) -> dict[str, dict[date, str]]:
    """Journées entières de congé approuvé, pour les alertes d'oubli de pointage."""
    out: dict[str, dict[date, str]] = {}
    for r in requests().all():
        if r["status"] not in EFFECTIVE or r["user"] not in emails:
            continue
        p = person_of(r["user"])
        for d, v in day_values(p, date.fromisoformat(r["start"]), date.fromisoformat(r["end"]), r["start_half"], r["end_half"]).items():
            if v == 1.0 and d_from <= d <= d_to:
                out.setdefault(r["user"], {})[d] = "Absence" if kind_of(r["type"]) == "absence" else "Congé"
    return out


def planning_leaves(d_from: date, d_to: date) -> list[dict]:
    """Congés approuvés visibles dans le Planning (sans type ni motif) : [{rid, start, end}]."""
    from . import staff
    by_email = {(p.get("google_email") or "").lower(): "s:" + p["id"] for p in staff.store().get()["data"]["people"] if p.get("google_email")}
    return [{"rid": by_email[r["user"]], "start": r["start"], "end": r["end"], "half": r["start_half"] == "pm" or r["end_half"] == "am"} for r in requests().all()
            if r["status"] in EFFECTIVE and r["user"] in by_email and date.fromisoformat(r["start"]) <= d_to and date.fromisoformat(r["end"]) >= d_from]


# ---- Demandes ----------------------------------------------------------------------------------------------------------------------------

def proof_expired(d: dict | None) -> bool:
    return bool(d) and now() - datetime.fromisoformat(d["created_at"]) > timedelta(days=PROOF_DAYS)


def view(r: dict, viewer: str, with_proofs: bool = True) -> dict:
    p = person_of(r["user"])
    mine = r["user"] == viewer.lower()
    validator = users.is_super(viewer) or can_decide(viewer, r)
    kind = kind_of(r["type"])
    secret = kind == "absence" and not (mine or validator)                    # le motif d'une absence ne sort pas du cercle personne / validateur / Super User
    files = [] if secret else [{"id": i, "expired": proof_expired(proofs().get(i))} for i in r.get("proofs", [])]
    base = {k: v for k, v in r.items() if k not in ("proof_keys", "comment", "proofs")} | ({"comment": "", "proofs": []} if secret else {"comment": r.get("comment", ""), "proofs": r.get("proofs", [])})
    return {**base, "proof_files": files, "name": (p or {}).get("name", r["user"]), "days": days_of(p, r), "type_label": "Absence" if secret else T[r["type"]][1], "kind": kind, "paid": T[r["type"]][5],
            "can_decide": kind == "leave" and r["status"] == "pending" and can_decide(viewer, r), "can_ack": kind == "absence" and r["status"] in AWAIT and can_decide(viewer, r), "mine": mine,
            "can_cancel": r["status"] in ("approved", "declared", "acknowledged") and (validator or (mine and (r["status"] == "declared" or (r["status"] == "approved" and date.fromisoformat(r["start"]) > date.today()))))}


def _mail(to: list[str], subject: str, body: str) -> None:
    from . import mailer
    for t in to:
        try:
            mailer.send(t, subject, body)
        except Exception:
            log.exception("E-mail de congé non envoyé à %s", t)


def _link(page: str = "leaves") -> str:
    return f"\n\n{settings.PUBLIC_URL}/#/consigner/{page}" if settings.PUBLIC_URL else ""


def create(data: LeaveIn, user: str) -> dict:
    p = person_of(user)
    if not p:
        raise PermissionError("Votre adresse Google n'est liée à aucune fiche du staff : le Super User doit la renseigner (Planifier › Ressources › Staff interne).")
    dv = day_values(p, data.start, data.end, data.start_half, data.end_half)
    if not dv:
        raise ValueError("Cette période ne contient aucun jour ouvré")
    n = sum(dv.values())
    if T[data.type][3] and n > 1 and not data.proofs:
        raise ValueError("Un justificatif (certificat médical) est obligatoire pour une maladie de plus d'un jour")
    keys = []
    for pid in data.proofs:
        d = proofs().get(pid)
        if not d or d["user"] != user.lower():
            raise ValueError("Justificatif introuvable")
        keys.append(pid)
    rid = "l-" + uuid.uuid4().hex[:10]
    doc = {"id": rid, "user": user.lower(), "type": data.type, "start": data.start.isoformat(), "end": data.end.isoformat(), "start_half": data.start_half, "end_half": data.end_half,
           "comment": data.comment.strip(), "proofs": keys, "status": "pending", "created_at": now().isoformat(), "event_id": None, "odoo_id": None}
    absence = kind_of(data.type) == "absence"
    if absence:                                                    # une absence se déclare : effective tout de suite, le validateur en prend acte
        doc["status"] = "declared"
        sync_calendar(doc, True)
    requests().put(rid, doc)
    to = approvers_of(doc)
    if absence:
        _mail(to, f"Logbook — absence déclarée par {p['name']}", f"{p['name']} déclare une absence de {n:g} jour(s) du {data.start.strftime('%d/%m/%Y')} au {data.end.strftime('%d/%m/%Y')}.\n\nÀ prendre en compte dans Logbook › Consigner › Absences.{_link('absences')}")
    else:
        _mail(to, f"Logbook — demande de congé de {p['name']}", f"{p['name']} demande {n:g} jour(s) de congé ({T[data.type][1]}) du {data.start.strftime('%d/%m/%Y')} au {data.end.strftime('%d/%m/%Y')}.\n\nÀ valider dans Logbook › Consigner › Congés.{_link()}")
    return doc


def update(rid: str, data: LeaveIn, user: str) -> dict:
    r = requests().get(rid)
    if not r:
        raise KeyError(rid)
    if r["user"] != user.lower() or r["status"] not in AWAIT:
        raise PermissionError("Seule une demande en attente (ou une absence pas encore prise en compte) peut être modifiée par son auteur")
    if kind_of(data.type) != kind_of(r["type"]):
        raise ValueError("Un congé ne devient pas une absence (ni l'inverse) : supprimez la demande et refaites-la")
    p = person_of(user)
    n = sum(day_values(p, data.start, data.end, data.start_half, data.end_half).values())
    if not n:
        raise ValueError("Cette période ne contient aucun jour ouvré")
    if T[data.type][3] and n > 1 and not (data.proofs or r.get("proofs")):
        raise ValueError("Un justificatif (certificat médical) est obligatoire pour une maladie de plus d'un jour")
    r.update(type=data.type, start=data.start.isoformat(), end=data.end.isoformat(), start_half=data.start_half, end_half=data.end_half, comment=data.comment.strip(), proofs=list(dict.fromkeys(r.get("proofs", []) + data.proofs)))
    if r["status"] == "declared":                                  # absence déjà dans l'agenda : on la reporte aux nouvelles dates
        sync_calendar(r, False)
        sync_calendar(r, True)
    requests().put(rid, r)
    return r


def decide(rid: str, approve: bool, reason: str, user: str) -> dict:
    r = requests().get(rid)
    if not r:
        raise KeyError(rid)
    if kind_of(r["type"]) == "absence":
        raise ValueError("Une absence ne s'approuve pas : le validateur en prend acte")
    if r["status"] != "pending":
        raise ValueError("Cette demande a déjà été traitée")
    if not can_decide(user, r):
        raise PermissionError("Vous n'êtes pas le validateur de cette demande")
    if not approve and len((reason or "").strip()) < 3:
        raise ValueError("Indiquez le motif du refus")
    r.update(status="approved" if approve else "refused", decided_by=user.lower(), decided_at=now().isoformat(), reason=(reason or "").strip())
    if approve:
        sync_calendar(r, True)
    requests().put(rid, r)
    p = person_of(r["user"]) or {}
    n = days_of(p, r)
    _mail([r["user"]], f"Logbook — congé {'approuvé' if approve else 'refusé'}", f"Votre demande de {n:g} jour(s) ({T[r['type']][1]}) du {date.fromisoformat(r['start']).strftime('%d/%m/%Y')} au {date.fromisoformat(r['end']).strftime('%d/%m/%Y')} est "
          + ("approuvée." if approve else f"refusée.\nMotif : {r['reason']}") + _link())
    return r


def acknowledge(rid: str, user: str) -> dict:
    """Prise d'acte d'une absence déclarée (accusé de réception du chef d'atelier ou du Managing Director) ; l'absence est déjà effective depuis sa déclaration."""
    r = requests().get(rid)
    if not r:
        raise KeyError(rid)
    if kind_of(r["type"]) != "absence":
        raise ValueError("Seules les absences se prennent en compte ; un congé s'approuve")
    if r["status"] not in AWAIT:
        raise ValueError("Cette absence a déjà été prise en compte")
    if not can_decide(user, r):
        raise PermissionError("Vous n'êtes pas le validateur de cette absence")
    if r["status"] == "pending":                                   # anciennes demandes de maladie en attente : l'événement n'existait pas encore
        sync_calendar(r, True)
    r.update(status="acknowledged", decided_by=user.lower(), decided_at=now().isoformat())
    requests().put(rid, r)
    _mail([r["user"]], "Logbook — absence prise en compte", f"Votre absence du {date.fromisoformat(r['start']).strftime('%d/%m/%Y')} au {date.fromisoformat(r['end']).strftime('%d/%m/%Y')} a été prise en compte.{_link('absences')}")
    return r


def cancel(rid: str, user: str) -> dict:
    """Annulation : en attente -> supprimée ; approuvée -> annulée (événement de l'agenda retiré, solde rendu), par son auteur avant le début, ou par un validateur."""
    r = requests().get(rid)
    if not r:
        raise KeyError(rid)
    own = r["user"] == user.lower()
    if r["status"] == "pending" and own:
        requests().delete(rid)
        return {**r, "status": "deleted"}
    if r["status"] == "declared" and own:
        sync_calendar(r, False)
        r.update(status="cancelled", cancelled_by=user.lower(), cancelled_at=now().isoformat())
        requests().put(rid, r)
        return r
    if r["status"] in ("approved", "declared", "acknowledged") and ((own and r["status"] == "approved" and date.fromisoformat(r["start"]) > date.today()) or can_decide(user, r)):
        sync_calendar(r, False)
        r.update(status="cancelled", cancelled_by=user.lower(), cancelled_at=now().isoformat())
        requests().put(rid, r)
        return r
    raise PermissionError("Cette demande ne peut plus être annulée par vous")


def add_proof(user: str, name: str, ctype: str, data: bytes) -> dict:
    ctype = ctype.split(";")[0].strip().lower()
    if ctype not in PROOF_TYPES:
        raise ValueError("Justificatif : photo (JPEG, PNG, WebP) ou PDF seulement")
    if not data or len(data) > PROOF_MAX:
        raise ValueError("Fichier vide ou trop volumineux (8 Mo maximum)")
    pid = uuid.uuid4().hex[:10]
    key = f"leaves/{pid}.{PROOF_TYPES[ctype]}"
    blobs().put(key, data, ctype)
    doc = {"id": pid, "user": user.lower(), "key": key, "ctype": ctype, "name": re.sub(r"[^\w .()\-]", "_", name)[:80], "created_at": now().isoformat()}
    proofs().put(pid, doc)
    return {"id": pid, "name": doc["name"], "ctype": ctype}
