"""Consigner › Pointages : jobs d'atelier et heures passées par les mécaniciens.

Un pointage = une durée sur un job, avec affectation (Prépa, Révision…), système (Moteur…), texte, photos et mémo vocal. Le mécanicien (identifié par son compte Google, lié à sa fiche du
staff) modifie ses pointages jusqu'à 24 h après leur création ; ensuite, ou une fois validés, seul le chef d'atelier peut les modifier. Le rôle à l'atelier (mécanicien, chef d'atelier CARS / XC / les deux) est un champ de la fiche staff (`workshop`), choisi dans Planifier › Ressources ; le Super User a les mêmes droits sur tout. Données dans Firestore (collections timesheet_jobs et timesheet_entries) ; photos et
mémos vocaux dans le bucket privé TIMESHEETS_BUCKET (préfixe timesheets/). Rien n'est écrit dans Odoo à ce stade."""
from __future__ import annotations

import re
import threading
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from . import settings

ASSIGNMENTS = [("prepa", "Prépa"), ("revision", "Révision"), ("labo", "Labo"), ("setup", "Setup"), ("chargement", "Chargement"), ("crash", "Crash"), ("autre", "Autre")]
SYSTEMS = [("moteur", "Moteur"), ("transmission", "Transmission"), ("suspension", "Suspension"), ("direction", "Direction"), ("freins", "Freins"), ("electricite", "Électricité"),
           ("carrosserie", "Châssis / Carrosserie"), ("habitacle", "Habitacle"), ("autre", "Autre")]
A_IDS, S_IDS = {a for a, _ in ASSIGNMENTS}, {s for s, _ in SYSTEMS}
EDIT_HOURS = 24
EVENT_NATURES = [("reassort", "Réassort camion(s)"), ("chargement", "Chargement camion(s) et/ou camionnette(s)"), ("dechargement", "Déchargement camion(s) et/ou camionnette(s)"),
                 ("nettoyage_equip", "Nettoyage équipements et/ou outillage"), ("nettoyage_veh", "Nettoyage camion(s) et/ou camionnette(s)")]
ATELIER_NATURES = [("pre_event", "Pre-event"), ("post_event", "Post-event"), ("custom", "Autre intervention")]
N_IDS = {**dict(EVENT_NATURES), **dict(ATELIER_NATURES)}
N_ASSIGN = {"pre_event": "prepa", "post_event": "revision"}
DEFAULT_BACKGROUND = ["Nettoyage atelier", "Rangement atelier", "Inventaire stock", "Réunion / briefing", "Formation", "Autre tâche de fond"]
AUDIO_DAYS = 90                                                          # conservation des mémos vocaux (le texte transcrit reste) ; photos : 10 ans ; la règle de cycle de vie du bucket supprime à AUDIO_DAYS + 1 jours
MAX_PHOTO, MAX_AUDIO = 8 * 1024 * 1024, 12 * 1024 * 1024


class VehicleRef(BaseModel):
    id: str = Field(default="", max_length=60)                          # compte analytique CARS d'Odoo (imputation ultérieure)
    name: str = Field(min_length=1, max_length=160)


class EventRef(BaseModel):
    id: str = Field(default="", max_length=40)                          # identifiant Logbook de l'événement (planning)
    title: str = Field(min_length=1, max_length=160)


class JobIn(BaseModel):
    kind: Literal["atelier", "event", "background"]
    title: str = Field(default="", max_length=140)                       # job événement : composé « nature — événement »
    nature: str = ""                                                     # job événement : une des EVENT_NATURES
    bu: Literal["XC", "CARS", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING", "ALL"] = "CARS"       # CARS = toutes les BU CARS
    vehicle: VehicleRef | None = None
    event: EventRef | None = None
    open: bool = True
    @field_validator("nature")
    @classmethod
    def _n(cls, v):
        if v and v not in N_IDS:
            raise ValueError("nature de job inconnue")
        return v

    template_id: str = ""                                                # job atelier : liste de contrôle copiée depuis ce modèle
    assignment: str = "autre"                                           # Prépa, Révision, Setup… : propre au job, reprise par chaque pointage

    @field_validator("assignment")
    @classmethod
    def _a(cls, v):
        if v not in A_IDS:
            raise ValueError("affectation inconnue")
        return v


class EntryIn(BaseModel):
    job_id: str = Field(min_length=1, max_length=60)
    date: date
    minutes: int = Field(ge=5, le=16 * 60)
    assignment: str = "autre"
    system: str = "autre"
    text: str = Field(default="", max_length=3000)
    user: str | None = None                                              # pointage pour un autre mécanicien : chef d'atelier seulement
    lines: list[str] = Field(default_factory=list, max_length=200)       # lignes de la liste de contrôle du job faites pendant ce pointage

    @field_validator("assignment")
    @classmethod
    def _a(cls, v):
        if v not in A_IDS:
            raise ValueError("affectation inconnue")
        return v

    @field_validator("system")
    @classmethod
    def _s(cls, v):
        if v not in S_IDS:
            raise ValueError("système inconnu")
        return v

    @field_validator("minutes")
    @classmethod
    def _m(cls, v):
        if v % 5:
            raise ValueError("la durée doit être un multiple de 5 minutes")
        return v


class LineIn(BaseModel):
    text: str = Field(min_length=1, max_length=300)
    note: str = Field(default="", max_length=200)


class SectionIn(BaseModel):
    title: str = Field(min_length=1, max_length=80)
    lines: list[LineIn] = Field(default_factory=list, max_length=100)


class TemplateIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    bu: Literal["XC", "CARS", "ALL"] = "CARS"
    natures: list[Literal["pre_event", "post_event", "custom"]] = Field(default_factory=list)       # natures de job pour lesquelles ce modèle est proposé
    sections: list[SectionIn] = Field(default_factory=list, max_length=30)


# ---- Stockage : Firestore (production) ou mémoire (démo / essais) ---------------------------------------------------------------------

class Coll:
    def __init__(self, name: str):
        self._lock = threading.Lock()
        self._mem: dict[str, dict] = {}
        self._c = None
        if settings.ADJUSTMENTS_STORE == "firestore":
            from google.cloud import firestore
            self._c = firestore.Client().collection(name)

    def get(self, id_: str) -> dict | None:
        if self._c is not None:
            s = self._c.document(id_).get()
            return s.to_dict() if s.exists else None
        with self._lock:
            d = self._mem.get(id_)
            return dict(d) if d else None

    def put(self, id_: str, doc: dict) -> None:
        if self._c is not None:
            self._c.document(id_).set(doc)
        else:
            with self._lock:
                self._mem[id_] = dict(doc)

    def delete(self, id_: str) -> None:
        if self._c is not None:
            self._c.document(id_).delete()
        else:
            with self._lock:
                self._mem.pop(id_, None)

    def all(self) -> list[dict]:
        if self._c is not None:
            return [d.to_dict() for d in self._c.stream()]
        with self._lock:
            return [dict(v) for v in self._mem.values()]

    def between(self, field: str, a: str, b: str) -> list[dict]:
        if self._c is not None:
            return [d.to_dict() for d in self._c.where(field, ">=", a).where(field, "<=", b).stream()]
        with self._lock:
            return [dict(v) for v in self._mem.values() if a <= v.get(field, "") <= b]


class Blobs:
    """Photos et mémos vocaux : Cloud Storage privé (TIMESHEETS_BUCKET, préfixe timesheets/) ; en démo / essais, mémoire."""
    def __init__(self):
        self._mem: dict[str, tuple[bytes, str]] = {}
        self._bucket = None
        if settings.TIMESHEETS_BUCKET:
            from google.cloud import storage
            self._bucket = storage.Client().bucket(settings.TIMESHEETS_BUCKET)

    @property
    def enabled(self) -> bool:
        return self._bucket is not None or settings.PROVIDER == "demo" or settings.ADJUSTMENTS_STORE != "firestore"

    def put(self, key: str, data: bytes, ctype: str) -> None:
        if self._bucket is not None:
            self._bucket.blob(key).upload_from_string(data, content_type=ctype)
        else:
            self._mem[key] = (data, ctype)

    def get(self, key: str) -> tuple[bytes, str] | None:
        if self._bucket is not None:
            b = self._bucket.blob(key)
            return (b.download_as_bytes(), b.content_type or "application/octet-stream") if b.exists() else None
        return self._mem.get(key)

    def delete(self, key: str) -> None:
        if self._bucket is not None:
            b = self._bucket.blob(key)
            if b.exists():
                b.delete()
        else:
            self._mem.pop(key, None)


_jobs = _entries = _blobs = _templates = None


def jobs() -> Coll:
    global _jobs
    _jobs = _jobs or Coll("timesheet_jobs")
    return _jobs


def templates() -> Coll:
    global _templates
    _templates = _templates or Coll("timesheet_templates")
    return _templates


def entries() -> Coll:
    global _entries
    _entries = _entries or Coll("timesheet_entries")
    return _entries


def blobs() -> Blobs:
    global _blobs
    _blobs = _blobs or Blobs()
    return _blobs


# ---- Identité et droits ----------------------------------------------------------------------------------------------------------------

def person_of(email: str) -> dict | None:
    from . import staff
    e = (email or "").lower()
    return next((p for p in staff.store().get()["data"]["people"] if (p.get("google_email") or "").lower() == e), None)


def role_of(email: str) -> dict:
    """{role: 'chef' | 'mechanic' | None, bus: ['XC', 'CARS'], person, super}"""
    from . import users
    p = person_of(email)
    if users.is_super(email):
        return {"role": "chef", "bus": ["XC", "CARS"], "person": p, "super": True}
    if not p:
        return {"role": None, "bus": [], "person": None, "super": False}
    w = p.get("workshop") or ""
    if w.startswith("chef_"):
        bus = {"chef_cars": ["CARS"], "chef_xc": ["XC"]}.get(w, ["XC", "CARS"])
        return {"role": "chef", "bus": bus, "person": p, "super": False}
    if w != "mechanic":
        return {"role": None, "bus": [], "person": p, "super": False}
    return {"role": "mechanic", "bus": [], "person": p, "super": False}


def bu_group(bu: str) -> str:
    """Chef d'atelier CARS : gère CARS et ses sous-BU (Modern Rally, Historic Rally, Historic Racing)."""
    return bu if bu in ("XC", "ALL") else "CARS"


BU_FILTER = {"xc": ("XC",), "cars": ("CARS", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING"), "mr": ("MODERN_RALLY",), "hrc": ("HISTORIC_RACING",), "hrl": ("HISTORIC_RALLY",)}


def job_in_bu(job: dict | None, sel: str) -> bool:
    """Filtre BU de la page Équipe : « all » garde tout ; sinon seuls les jobs rattachés à cette BU (les jobs « Toutes » n'appartiennent à aucune BU en particulier)."""
    if sel == "all" or sel not in BU_FILTER:
        return True
    return bool(job) and job.get("bu") in BU_FILTER[sel]


def chef_for(r: dict, job: dict | None) -> bool:
    """Le chef d'atelier gère les jobs de sa BU (et ceux « ALL ») ; le Super User, tous."""
    if r["role"] != "chef":
        return False
    return r["super"] or not job or job.get("bu") == "ALL" or bu_group(job.get("bu", "CARS")) in r["bus"]


def now() -> datetime:
    return datetime.now(timezone.utc)


def editable_until(entry: dict) -> str:
    return (datetime.fromisoformat(entry["created_at"]) + timedelta(hours=EDIT_HOURS)).isoformat()


def can_edit(entry: dict, user: str, r: dict, job: dict | None) -> bool:
    if chef_for(r, job):
        return True
    return entry["user"] == user.lower() and not entry.get("validated") and now() <= datetime.fromisoformat(editable_until(entry))


# ---- Jobs ---------------------------------------------------------------------------------------------------------------------------------

def billable(job: dict) -> bool:
    """Facturable : job lié à un véhicule (axe analytique CARS) ou à un événement (axe MEETING) ; les tâches de fond ne le sont pas."""
    return job.get("kind") != "background" and bool(job.get("vehicle") or job.get("event"))


def progress(j: dict) -> dict | None:
    cl = j.get("checklist")
    if not cl:
        return None
    lines = [ln for s in cl["sections"] for ln in s["lines"]]
    return {"done": sum(1 for ln in lines if ln.get("done")), "total": len(lines)}


def job_view(j: dict) -> dict:
    return {**j, "billable": billable(j), "progress": progress(j)}


# ---- Modèles de jobs et listes de contrôle ------------------------------------------------------------------------------------------------

def _template_doc(data: TemplateIn, tid: str, user: str, created: str | None = None) -> dict:
    secs = [{"id": f"s{i}", "title": s.title.strip(), "lines": [{"id": f"l{i}-{j}", "text": ln.text.strip(), "note": ln.note.strip()} for j, ln in enumerate(s.lines) if ln.text.strip()]}
            for i, s in enumerate(data.sections)]
    return {"id": tid, "name": data.name.strip(), "bu": data.bu, "natures": list(data.natures), "sections": [s for s in secs if s["lines"]],
            "created_by": user.lower(), "created_at": created or now().isoformat(), "updated_at": now().isoformat()}


def ensure_templates() -> None:
    """Crée une seule fois le modèle de départ (ensuite, le chef d'atelier le modifie ou le supprime à sa guise)."""
    if templates().get("_seeded"):
        return
    from .ts_seed import SEED_TEMPLATES
    if not [t for t in templates().all() if t.get("id") != "_seeded"]:
        for t in SEED_TEMPLATES:
            tid = "t-" + uuid.uuid4().hex[:8]
            templates().put(tid, _template_doc(TemplateIn.model_validate(t), tid, "system"))
    templates().put("_seeded", {"id": "_seeded"})


def list_templates() -> list[dict]:
    ensure_templates()
    return sorted((t for t in templates().all() if t.get("id") != "_seeded"), key=lambda t: t["name"].lower())


def save_template(data: TemplateIn, user: str, tid: str | None = None) -> dict:
    if not data.sections or not any(s.lines for s in data.sections):
        raise ValueError("Le modèle doit contenir au moins une ligne de travail")
    old = templates().get(tid) if tid else None
    if tid and not old:
        raise KeyError(tid)
    if any(t["id"] != tid and t["name"].lower() == data.name.strip().lower() for t in list_templates()):
        raise ValueError("Un modèle porte déjà ce nom")
    doc = _template_doc(data, tid or "t-" + uuid.uuid4().hex[:8], user, (old or {}).get("created_at"))
    templates().put(doc["id"], doc)
    return doc


def make_checklist(t: dict) -> dict:
    """Copie du modèle dans le job : modifier le modèle plus tard ne change pas les jobs déjà créés."""
    return {"template_id": t["id"], "template_name": t["name"], "sections": [{"id": s["id"], "title": s["title"], "lines": [
        {"id": ln["id"], "text": ln["text"], "note": ln.get("note", ""), "done": False, "done_by": None, "done_at": None, "entry_id": None} for ln in s["lines"]]} for s in t["sections"]]}


def person_name(email: str) -> str:
    p = person_of(email)
    return (p or {}).get("name") or email


def sync_lines(job: dict | None, eid: str, user: str, ids: list[str]) -> None:
    """Coche sur le job les lignes faites pendant ce pointage (et décoche celles que ce pointage ne revendique plus)."""
    if not job or not job.get("checklist"):
        return
    want, known = set(ids), set()
    for s in job["checklist"]["sections"]:
        for ln in s["lines"]:
            known.add(ln["id"])
            if ln["id"] in want:
                if ln.get("done") and ln.get("entry_id") != eid:
                    raise ValueError(f"« {ln['text'][:60]} » est déjà faite par {ln.get('done_by') or 'un collègue'}")
                if not ln.get("done"):
                    ln.update(done=True, done_by=person_name(user), done_at=now().isoformat(), entry_id=eid)
            elif ln.get("done") and ln.get("entry_id") == eid:
                ln.update(done=False, done_by=None, done_at=None, entry_id=None)
    if want - known:
        raise ValueError("Ligne inconnue pour ce job")
    jobs().put(job["id"], job)


def ensure_defaults() -> None:
    if any(j.get("kind") == "background" for j in jobs().all()):
        return
    for t in DEFAULT_BACKGROUND:
        jid = "bg-" + uuid.uuid4().hex[:8]
        jobs().put(jid, {"id": jid, "kind": "background", "title": t, "bu": "ALL", "vehicle": None, "event": None, "open": True, "created_by": "system", "created_at": now().isoformat()})


def list_jobs(open_only: bool = True) -> list[dict]:
    ensure_defaults()
    out = [job_view(j) for j in jobs().all() if (j.get("open", True) or not open_only)]
    order = {"atelier": 0, "event": 1, "background": 2}
    return sorted(out, key=lambda j: (order.get(j["kind"], 9), j["title"].lower()))


def job_title(data: JobIn) -> str:
    if data.kind == "event":
        if not (data.event and data.nature):
            raise ValueError("Choisissez l'événement et la nature du job")
        return f"{N_IDS[data.nature]} — {data.event.title}"
    if data.kind == "atelier" and data.nature:
        if not data.vehicle:
            raise ValueError("Choisissez la voiture")
        if data.nature == "custom":
            if not data.title.strip():
                raise ValueError("Indiquez l'intervention")
            return f"{data.title.strip()} / {data.vehicle.name}"
        if not data.event:
            raise ValueError("Choisissez l'événement")
        return f"{N_IDS[data.nature]} {data.event.title} / {data.vehicle.name}"
    if not data.title.strip():
        raise ValueError("L'intitulé est obligatoire")
    return data.title.strip()


def create_job(data: JobIn, user: str) -> dict:
    data = data.model_copy(update={"title": job_title(data), "assignment": N_ASSIGN.get(data.nature, data.assignment)})
    if any(j["title"].lower() == data.title.lower() for j in jobs().all()):
        raise ValueError("Ce job existe déjà")
    jid = "j-" + uuid.uuid4().hex[:10]
    doc = {"id": jid, **data.model_dump(), "created_by": user.lower(), "created_at": now().isoformat()}
    doc.pop("template_id", None)
    if data.kind == "atelier" and data.template_id:
        t = templates().get(data.template_id)
        if not t:
            raise ValueError("Modèle introuvable")
        doc["checklist"] = make_checklist(t)
    jobs().put(jid, doc)
    return job_view(doc)


# ---- Pointages -----------------------------------------------------------------------------------------------------------------------------

def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def entry_view(e: dict, user: str, r: dict, jmap: dict) -> dict:
    job = jmap.get(e["job_id"])
    lines = []
    if job and job.get("checklist"):
        by = {ln["id"]: (s["title"], ln["text"]) for s in job["checklist"]["sections"] for ln in s["lines"]}
        lines = [{"id": i, "section": by[i][0], "text": by[i][1]} for i in e.get("lines", []) if i in by]
    return {**e, "lines": lines, "line_ids": e.get("lines", []), "job": job_view(job) if job else {"id": e["job_id"], "title": "(job supprimé)", "kind": "atelier", "billable": False},
            "can_edit": can_edit(e, user, r, job), "editable_until": editable_until(e)}


def week_entries(user_email: str, start: date) -> list[dict]:
    a, b = start.isoformat(), (start + timedelta(days=6)).isoformat()
    return sorted([e for e in entries().between("date", a, b) if e["user"] == user_email.lower()], key=lambda e: (e["date"], e["created_at"]))


def theoretical_minutes(person: dict | None) -> int:
    """Horaire hebdomadaire théorique : heures par semaine (temps plein) × temps de travail de la fiche."""
    if not person:
        return 0
    return round(float(person.get("hours_week", 38.0)) * float(person.get("fte", 100.0)) / 100.0 * 60)


def summary(ents: list[dict], person: dict | None, jmap: dict) -> dict:
    total = sum(e["minutes"] for e in ents)
    bill = sum(e["minutes"] for e in ents if billable(jmap.get(e["job_id"]) or {}))
    theo = theoretical_minutes(person)
    by_day: dict[str, int] = {}
    by_job: dict[str, int] = {}
    for e in ents:
        by_day[e["date"]] = by_day.get(e["date"], 0) + e["minutes"]
        by_job[e["job_id"]] = by_job.get(e["job_id"], 0) + e["minutes"]
    return {"total": total, "billable": bill, "theoretical": theo, "occupancy": round(total / theo, 3) if theo else None, "billable_rate": round(bill / theo, 3) if theo else None,
            "by_day": by_day, "by_job": [{"job_id": k, "minutes": v, "title": (jmap.get(k) or {}).get("title", "(job supprimé)")} for k, v in sorted(by_job.items(), key=lambda kv: -kv[1])],
            "validated": sum(1 for e in ents if e.get("validated")), "count": len(ents)}


def create_entry(data: EntryIn, user: str, r: dict) -> dict:
    job = jobs().get(data.job_id)
    if not job or not job.get("open", True):
        raise LookupError("Job introuvable ou clôturé")
    target = (data.user or user).lower()
    if target != user.lower() and not chef_for(r, job):
        raise PermissionError("Seul le chef d'atelier peut pointer pour un autre mécanicien")
    eid = "e-" + uuid.uuid4().hex[:12]
    doc = {"id": eid, "user": target, "job_id": data.job_id, "date": data.date.isoformat(), "minutes": data.minutes, "assignment": job.get("assignment", "autre"), "system": data.system if job.get("kind") == "atelier" else "autre", "text": data.text.strip(),
           "attachments": [], "validated": False, "created_at": now().isoformat(), "updated_at": now().isoformat(), "created_by": user.lower()}
    sync_lines(job, eid, target, data.lines)
    doc["lines"] = list(data.lines)
    if job.get("checklist"):
        doc["system"] = "autre"
    entries().put(eid, doc)
    return doc


def update_entry(eid: str, data: EntryIn, user: str, r: dict) -> dict:
    e = entries().get(eid)
    if not e:
        raise KeyError(eid)
    old_job = jobs().get(e["job_id"])
    if not can_edit(e, user, r, old_job):
        raise PermissionError("Ce pointage n'est plus modifiable (24 h écoulées ou validé) : voyez le chef d'atelier")
    job = jobs().get(data.job_id)
    if not job:
        raise LookupError("Job introuvable")
    if data.job_id != e["job_id"] and not job.get("open", True):
        raise LookupError("Job clôturé")
    prev_job = e["job_id"]
    e.update({"job_id": data.job_id, "date": data.date.isoformat(), "minutes": data.minutes, "assignment": job.get("assignment", "autre"), "system": data.system if job.get("kind") == "atelier" else "autre", "text": data.text.strip(), "updated_at": now().isoformat()})
    if data.job_id != prev_job:
        sync_lines(old_job, eid, e["user"], [])                       # on quitte l'ancien job : ses lignes redeviennent à faire
    sync_lines(job, eid, e["user"], data.lines)
    e["lines"] = list(data.lines)
    if job.get("checklist"):
        e["system"] = "autre"
    entries().put(eid, e)
    return e


def delete_entry(eid: str, user: str, r: dict) -> None:
    e = entries().get(eid)
    if not e:
        raise KeyError(eid)
    if not can_edit(e, user, r, jobs().get(e["job_id"])):
        raise PermissionError("Ce pointage n'est plus modifiable (24 h écoulées ou validé) : voyez le chef d'atelier")
    for a in e.get("attachments", []):
        blobs().delete(a["key"])
    sync_lines(jobs().get(e["job_id"]), eid, e["user"], [])
    entries().delete(eid)


def validate_entry(eid: str, validated: bool, user: str, r: dict) -> dict:
    e = entries().get(eid)
    if not e:
        raise KeyError(eid)
    if not chef_for(r, jobs().get(e["job_id"])):
        raise PermissionError("Réservé au chef d'atelier")
    e["validated"] = validated
    e["validated_by"] = user.lower() if validated else None
    e["validated_at"] = now().isoformat() if validated else None
    entries().put(eid, e)
    return e


def add_attachment(eid: str, name: str, ctype: str, data: bytes, user: str, r: dict) -> dict:
    e = entries().get(eid)
    if not e:
        raise KeyError(eid)
    if not can_edit(e, user, r, jobs().get(e["job_id"])):
        raise PermissionError("Ce pointage n'est plus modifiable")
    kind = "photo" if ctype.startswith("image/") else "audio" if ctype.startswith("audio/") else None
    if not kind:
        raise ValueError("Seules les photos et les mémos vocaux sont acceptés")
    if len(data) == 0 or len(data) > (MAX_PHOTO if kind == "photo" else MAX_AUDIO):
        raise ValueError("Fichier vide ou trop volumineux")
    if len(e.get("attachments", [])) >= 12:
        raise ValueError("12 pièces jointes au maximum par pointage")
    aid = uuid.uuid4().hex[:10]
    ext = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "audio/webm": "webm", "audio/mp4": "m4a", "audio/wav": "wav", "audio/x-wav": "wav", "audio/ogg": "ogg", "audio/mpeg": "mp3"}.get(ctype.split(";")[0], "bin")
    key = f"timesheets/{eid}/{aid}.{ext}"
    blobs().put(key, data, ctype.split(";")[0] if kind == "photo" else ctype)
    att = {"id": aid, "kind": kind, "name": re.sub(r"[^\w .()\-]", "_", name)[:80], "content_type": ctype, "size": len(data), "key": key, "created_at": now().isoformat()}
    e.setdefault("attachments", []).append(att)
    e["updated_at"] = now().isoformat()
    entries().put(eid, e)
    return {k: v for k, v in att.items() if k != "key"}


def _expired(a: dict) -> bool:
    """Mémo vocal au-delà de sa durée de conservation (la règle de cycle de vie du bucket supprime le fichier) ; les photos sont gardées 10 ans."""
    return a.get("kind") == "audio" and now() - datetime.fromisoformat(a["created_at"]) > timedelta(days=AUDIO_DAYS)


def public_attachments(e: dict) -> dict:
    return {**e, "attachments": [{**{k: v for k, v in a.items() if k != "key"}, "expired": _expired(a)} for a in e.get("attachments", [])]}


# ---- Propositions de jobs d'après le planning --------------------------------------------------------------------------------------------

RACE = {"rally", "circuit"}


def suggestions(today: date, days: int = 60) -> list[dict]:
    """Jobs que le chef d'atelier peut créer en un clic : pour chaque événement à venir, un job « événement » et, par voiture de course (ressource Rally / Circuit)
    réservée sur l'événement, « Pre-event … » et « Post-event … ». Les jobs déjà créés (même titre) ne sont plus proposés."""
    from . import planning
    view = planning.planning_view(today, today + timedelta(days=days))
    res = {r["id"]: r for r in view["resources"]}
    have = {j["title"].lower() for j in jobs().all()}
    out: list[dict] = []
    for ev in view["events"]:
        bu = ev["bu"] if ev["bu"] in ("XC", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING") else "CARS"
        eref = {"id": ev["id"], "title": ev["title"]}
        todo = [n for n, label in EVENT_NATURES if f"{label} — {ev['title']}".lower() not in have]
        if todo:
            out.append({"kind": "event", "title": ev["title"], "bu": bu, "vehicle": None, "event": eref, "natures": todo, "when": ev["start"]})
        for v in ev["vehicles"]:
            r = res.get(v["rid"]) or {}
            if r.get("category") not in RACE:
                continue
            vname = re.sub(r"^\s*[(\[][^)\]]*[)\]]\s*[-:]?\s*", "", r["name"]) or r["name"]
            for prefix, nat in (("Pre-event", "pre_event"), ("Post-event", "post_event")):
                out.append({"kind": "atelier", "title": f"{prefix} {ev['title']} / {vname}", "nature": nat, "bu": bu, "vehicle": {"id": "", "name": vname}, "event": eref, "when": ev["start"]})
    return [s for s in out if s.get("natures") or s["title"].lower() not in have]


def remove_attachment(eid: str, aid: str, user: str, r: dict) -> None:
    e = entries().get(eid)
    if not e:
        raise KeyError(eid)
    if not can_edit(e, user, r, jobs().get(e["job_id"])):
        raise PermissionError("Ce pointage n'est plus modifiable")
    att = next((a for a in e.get("attachments", []) if a["id"] == aid), None)
    if not att:
        raise KeyError(aid)
    blobs().delete(att["key"])
    e["attachments"] = [a for a in e["attachments"] if a["id"] != aid]
    e["updated_at"] = now().isoformat()
    entries().put(eid, e)
