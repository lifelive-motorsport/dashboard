"""Planifier › Événements : création, modification et suppression des événements dans les agendas Google des BU (agenda « Libellé=adresse » de CALENDAR_IDS).

Un événement Logbook = un événement « principal » (dates de l'événement ; staff et, une fois confirmé, prestataires invités) et, si les dates d'immobilisation
diffèrent, un événement « Immobilisation » lié (véhicules invités comme ressources). Tout est reconnu par des propriétés partagées (logbook, kind, lbid) :
Google Agenda reste la seule source de vérité. Accès Google : délégation à l'échelle du domaine (gauth). En démo : mémoire."""
from __future__ import annotations

import re
import threading
import uuid
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator, model_validator

from . import gauth, gcal, maps, settings
from .staff import EMAIL

API = "https://www.googleapis.com/calendar/v3"
SEP = "\n\n— Logbook —\n"
TBC = "[TBC] "
TRANSPORT = "[transport] "
# BU proposées pour un événement : identifiant -> (libellé, couleur Google Agenda de la charte, clé de BU de gcal.calendars())
BUS = {"XC": ("XC", "11"), "MODERN_RALLY": ("Modern Rally", "9"), "HISTORIC_RALLY": ("Historic Rally", "5"), "HISTORIC_RACING": ("Historic Racing", "10"),
       "OTHERS": ("Others", "8")}     # Others : transports privés (actionnaires, MD, enlèvements pour le stock…), hors BU


class Place(BaseModel):
    id: str = Field(min_length=1, max_length=300)                      # identifiant de lieu Google : obligatoire (le lieu doit être choisi dans la recherche)
    name: str = Field(default="", max_length=200)
    address: str = Field(default="", max_length=300)
    lat: float | None = None
    lng: float | None = None
    country: str = Field(default="", max_length=3)


class EventIn(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    bu: str
    confirmed: bool = False
    transport: bool = False                                            # simple mission logistique : « [transport] » est ajouté au titre ; pas de job proposé
    start: date
    end: date
    start_time: str = ""                                               # « HH:MM », transports seulement (sinon l'événement dure des journées entières)
    end_time: str = ""
    immo_start: date
    immo_end: date
    place: Place
    origin: Place | None = None                                        # lieu de départ (sinon Lifelive, LIFELIVE_ORIGIN)
    notes: str = Field(default="", max_length=2000)
    notify: bool = True                                                # prévenir les invités par Google Agenda (invitation ou mise à jour) ; non conservé
    staff: list[str] = Field(default_factory=list, max_length=60)
    externals: list[str] = Field(default_factory=list, max_length=60)
    vehicles: list[str] = Field(default_factory=list, max_length=30)

    @field_validator("bu")
    @classmethod
    def _bu(cls, v):
        if v not in BUS:
            raise ValueError("BU inconnue")
        return v

    @field_validator("staff", "externals", "vehicles")
    @classmethod
    def _emails(cls, v):
        out = []
        for x in v:
            x = x.strip().lower()
            if not EMAIL.match(x):
                raise ValueError(f"adresse e-mail invalide : {x}")
            if x not in out:
                out.append(x)
        return out

    @field_validator("start_time", "end_time")
    @classmethod
    def _time(cls, v):
        v = (v or "").strip()
        if v and not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", v):
            raise ValueError("heure invalide (HH:MM)")
        return v

    @model_validator(mode="after")
    def _dates(self):
        if not self.transport:
            self.start_time = self.end_time = ""
        elif bool(self.start_time) != bool(self.end_time):
            raise ValueError("indiquez l'heure de début et l'heure de fin")
        elif self.start_time and (self.end, self.end_time) <= (self.start, self.start_time):
            raise ValueError("la fin du transport doit suivre son début")
        if self.end < self.start:
            raise ValueError("la fin de l'événement précède son début")
        if self.immo_start > self.start or self.immo_end < self.end:
            raise ValueError("l'immobilisation doit couvrir l'événement")
        if not self.confirmed and len(",".join(self.externals)) > 900:
            raise ValueError("trop de prestataires pour un événement non confirmé")
        return self


class BusyBody(BaseModel):
    emails: list[str] = Field(max_length=300)
    start: date
    end: date


# ---- Accès aux agendas : Google ou mémoire (démo) --------------------------------------------------------------------------------------

class Google:
    def _s(self):
        return gauth.session((gauth.SCOPE_CALENDAR,))

    @staticmethod
    def _chk(r):
        if r.status_code not in (200, 204):
            try:
                msg = r.json().get("error", {}).get("message", "")
            except ValueError:
                msg = ""
            raise RuntimeError(f"Google Agenda HTTP {r.status_code} — {msg[:300]}".strip(" —"))
        return r

    @staticmethod
    def _cal(cid: str) -> str:
        return cid.replace("@", "%40")

    def insert(self, cal: str, body: dict, notify: bool) -> dict:
        return self._chk(self._s().post(f"{API}/calendars/{self._cal(cal)}/events", params={"sendUpdates": "all" if notify else "none"}, json=body, timeout=30)).json()

    def patch(self, cal: str, eid: str, body: dict, notify: bool) -> dict:
        return self._chk(self._s().patch(f"{API}/calendars/{self._cal(cal)}/events/{eid}", params={"sendUpdates": "all" if notify else "none"}, json=body, timeout=30)).json()

    def delete(self, cal: str, eid: str, notify: bool) -> None:
        r = self._s().delete(f"{API}/calendars/{self._cal(cal)}/events/{eid}", params={"sendUpdates": "all" if notify else "none"}, timeout=30)
        if r.status_code not in (200, 204, 404, 410):
            self._chk(r)

    def list(self, cal: str, d_from: date, d_to: date, lbid: str | None = None) -> list[dict]:
        items, token = [], None
        while True:
            params = {"singleEvents": "true", "maxResults": 2500, "sharedExtendedProperty": ["logbook=1"] + ([f"lbid={lbid}"] if lbid else []),
                      "timeMin": f"{d_from.isoformat()}T00:00:00Z", "timeMax": f"{(d_to + timedelta(days=1)).isoformat()}T00:00:00Z"}
            if token:
                params["pageToken"] = token
            j = self._chk(self._s().get(f"{API}/calendars/{self._cal(cal)}/events", params=params, timeout=30)).json()
            items += j.get("items", [])
            token = j.get("nextPageToken")
            if not token:
                return [e for e in items if e.get("status") != "cancelled"]

    def busy(self, emails: list[str], d_from: date, d_to: date) -> dict[str, list[dict]]:
        tz = ZoneInfo("Europe/Brussels")
        t0 = datetime.combine(d_from, datetime.min.time(), tz).isoformat()
        t1 = datetime.combine(d_to + timedelta(days=1), datetime.min.time(), tz).isoformat()
        out: dict[str, list[dict]] = {}
        for i in range(0, len(emails), 50):                            # l'API freeBusy accepte au plus 50 agendas par demande
            j = self._chk(self._s().post(f"{API}/freeBusy", json={"timeMin": t0, "timeMax": t1, "timeZone": "Europe/Brussels", "items": [{"id": e} for e in emails[i:i + 50]]}, timeout=30)).json()
            out.update({e: (c.get("busy") or []) for e, c in (j.get("calendars") or {}).items()})
        return out


class Memory:
    """Agendas en mémoire (démo et essais), même comportement que Google pour les besoins ci-dessus."""
    def __init__(self):
        self._lock = threading.Lock()
        self.events: dict[str, dict[str, dict]] = {}
        self.sent: list[tuple[str, str, bool]] = []

    def insert(self, cal, body, notify):
        e = {**body, "id": uuid.uuid4().hex[:16], "status": "confirmed"}
        with self._lock:
            self.events.setdefault(cal, {})[e["id"]] = e
            self.sent.append(("insert", e["id"], notify))
        return e

    def patch(self, cal, eid, body, notify):
        with self._lock:
            e = self.events[cal][eid]
            for k, v in body.items():  # comme Google : fusion, et null efface la clé
                if isinstance(v, dict) and isinstance(e.get(k), dict):
                    e[k] = {a: b for a, b in {**e[k], **v}.items() if b is not None}
                else:
                    e[k] = v
            self.sent.append(("patch", eid, notify))
            return e

    def delete(self, cal, eid, notify):
        with self._lock:
            self.events.get(cal, {}).pop(eid, None)
            self.sent.append(("delete", eid, notify))

    def list(self, cal, d_from, d_to, lbid=None):
        out = []
        for e in list(self.events.get(cal, {}).values()):
            sh = (e.get("extendedProperties") or {}).get("shared", {})
            if sh.get("logbook") != "1" or (lbid and sh.get("lbid") != lbid):
                continue
            s, en = date.fromisoformat(_start(e)), date.fromisoformat(_inc_end(e))
            if s <= d_to and en >= d_from:
                out.append(e)
        return out

    def busy(self, emails, d_from, d_to):
        demo = {"sprinter@resource.calendar.google.com": [{"start": "2026-06-18T00:00:00+02:00", "end": "2026-06-25T00:00:00+02:00"}]}
        return {e: [b for b in demo.get(e, []) if date.fromisoformat(b["start"][:10]) <= d_to and date.fromisoformat(b["end"][:10]) > d_from] for e in emails}


_backend = None


def backend():
    global _backend
    if _backend is None:
        _backend = Memory() if settings.PROVIDER == "demo" else Google()
    return _backend


# ---- Construction des événements ------------------------------------------------------------------------------------------------------

def calendars_by_bu() -> dict[str, str]:
    """BU de l'application -> adresse de l'agenda. En démo : adresses fictives."""
    if settings.PROVIDER == "demo":
        return {k: f"demo-{k.lower()}@group.calendar.google.com" for k in BUS}
    cals = {bu: cid for cid, _label, bu in gcal.calendars() if bu in BUS}
    if "OTHERS" not in cals:                                           # pas d'agenda « Others » : repli sur l'ancien agenda « Logistics »
        old = next((cid for cid, _l, bu in gcal.calendars() if bu == "LOGISTICS"), None)
        if old:
            cals["OTHERS"] = old
    return cals


def _day(d: date) -> dict:
    return {"date": d.isoformat()}


def _description(notes: str, place: Place, route: dict | None, origin: Place | None = None) -> str:
    lines = [f"Lieu : {place.name + ', ' if place.name else ''}{place.address}".strip()]
    if origin:
        lines.append(f"Départ : {origin.name + ', ' if origin.name else ''}{origin.address}".strip())
    if route and route.get("km") is not None:
        h, m = divmod(route["minutes"], 60)
        lines.append(f"Distance depuis {route.get('origin_label', 'Lifelive')} : {route['km']} km ({h} h {m:02d}) à l’aller")
    if route:
        lines += [f"⚠ {a}" for a in route["alerts"]]
    return (notes.strip() + SEP if notes.strip() else SEP.lstrip("\n")) + "\n".join(lines)


def _title(e: EventIn) -> str:
    return ("" if e.confirmed else TBC) + (TRANSPORT if e.transport else "") + e.title.strip()


def _shared(e: EventIn, lbid: str, kind: str, route: dict | None) -> dict:
    sh = {"logbook": "1", "kind": kind, "lbid": lbid, "bu": e.bu, "confirmed": "1" if e.confirmed else "0", "transport": "1" if e.transport else "0", "place": e.place.id,
          "immo": f"{e.immo_start.isoformat()}/{e.immo_end.isoformat()}"}
    if not e.confirmed and e.externals:                                # prestataires prévus mais pas encore invités (événement TBC) : gardés ici pour la modification
        sh["pending"] = ",".join(e.externals)
    if e.origin:
        sh["origin"] = e.origin.id
        sh["origin_addr"] = (e.origin.name + ", " if e.origin.name else "") + e.origin.address
    if route:
        sh["km"] = str(route["km"])
        sh["via"] = ",".join(route["via"])
    return sh


def _span(e: EventIn) -> dict:
    """Début / fin de l'événement principal : journées entières, ou plage horaire (transport) à l'heure de Bruxelles."""
    if e.start_time:
        tz = "Europe/Brussels"
        return {"start": {"dateTime": f"{e.start.isoformat()}T{e.start_time}:00", "timeZone": tz}, "end": {"dateTime": f"{e.end.isoformat()}T{e.end_time}:00", "timeZone": tz}}
    return {"start": _day(e.start), "end": _day(e.end + timedelta(days=1))}


def build_main(e: EventIn, lbid: str, route: dict | None) -> dict:
    single = e.vehicles and (e.immo_start, e.immo_end) == (e.start, e.end)
    att = [{"email": x} for x in e.staff] + ([{"email": x} for x in e.externals] if e.confirmed else [])
    att += [{"email": x, "resource": True} for x in e.vehicles] if single else []
    return {"summary": _title(e), "description": _description(e.notes, e.place, route, e.origin), "location": e.place.address or e.place.name, "colorId": BUS[e.bu][1],
            **_span(e), "attendees": att,
            "extendedProperties": {"shared": _shared(e, lbid, "main", route)}}


def wants_vehicle_event(e: EventIn) -> bool:
    return bool(e.vehicles) and (e.immo_start, e.immo_end) != (e.start, e.end)


def build_vehicles(e: EventIn, lbid: str) -> dict:
    return {"summary": "Immobilisation véhicules — " + _title(e), "description": f"Véhicules immobilisés pour : {e.title.strip()}\n{e.place.address}".strip(), "colorId": BUS[e.bu][1],
            "start": _day(e.immo_start), "end": _day(e.immo_end + timedelta(days=1)), "transparency": "opaque",
            "attendees": [{"email": x, "resource": True} for x in e.vehicles], "extendedProperties": {"shared": _shared(e, lbid, "vehicles", None)}}


def _route(place: Place, origin: Place | None = None) -> dict | None:
    try:
        return maps.route(place.model_dump(), origin.model_dump() if origin else None)
    except Exception:
        return None


def _cal(bu: str) -> str:
    cal = calendars_by_bu().get(bu)
    if not cal:
        raise LookupError(f"Aucun agenda n’est configuré pour la BU {BUS[bu][0]} (variable CALENDAR_IDS).")
    return cal


def _find(lbid: str) -> tuple[dict | None, dict | None, str | None]:
    """(événement principal, événement véhicules, agenda de l'événement principal)"""
    today = date.today()
    main = veh = cal_main = None
    for cal in calendars_by_bu().values():
        for ev in backend().list(cal, today - timedelta(days=730), today + timedelta(days=1095), lbid):
            kind = (ev.get("extendedProperties") or {}).get("shared", {}).get("kind")
            if kind == "main":
                main, cal_main = ev, cal
            elif kind == "vehicles":
                veh = ev
    return main, veh, cal_main


def create(e: EventIn, lbid: str | None = None) -> dict:
    cal = _cal(e.bu)
    lbid = lbid or uuid.uuid4().hex[:12]
    route = _route(e.place, e.origin)
    main = build_main(e, lbid, route)
    backend().insert(cal, main, notify=e.notify and bool(main["attendees"]))
    if wants_vehicle_event(e):
        backend().insert(cal, build_vehicles(e, lbid), notify=False)
    return {"id": lbid, "route": route}


def event_bu(lbid: str) -> str | None:
    """BU (clé de l'application) d'un événement existant, d'après son agenda ; None s'il est introuvable."""
    main, _veh, _cal = _find(lbid)
    return None if main is None else ((main.get("extendedProperties") or {}).get("shared", {}).get("bu") or None)


def update(lbid: str, e: EventIn) -> dict:
    main, veh, cal_main = _find(lbid)
    if main is None:
        raise KeyError(lbid)
    if cal_main != _cal(e.bu):                                         # changement de BU = autre agenda : on supprime puis on recrée (même identifiant Logbook)
        remove(lbid)
        return create(e, lbid)
    route = _route(e.place, e.origin)
    body = build_main(e, lbid, route)
    for k in ("start", "end"):  # patch fusionne : on efface l'autre forme (date / dateTime) sinon Google refuse « Invalid start time »
        body[k] = {**body[k], **({"date": None} if "dateTime" in body[k] else {"dateTime": None, "timeZone": None})}
    backend().patch(cal_main, main["id"], body, notify=e.notify)
    if wants_vehicle_event(e):
        vb = build_vehicles(e, lbid)
        if veh:
            backend().patch(cal_main, veh["id"], vb, notify=False)
        else:
            backend().insert(cal_main, vb, notify=False)
    elif veh:
        backend().delete(cal_main, veh["id"], notify=False)
    return {"id": lbid, "route": route}


def remove(lbid: str) -> bool:
    main, veh, cal = _find(lbid)
    if main is None and veh is None:
        return False
    if veh:
        backend().delete(cal, veh["id"], notify=False)
    if main:
        backend().delete(cal, main["id"], notify=True)
    return True


# ---- Lecture ------------------------------------------------------------------------------------------------------------------------

def _inc_end(ev: dict) -> str:
    return (date.fromisoformat(ev["end"]["date"]) - timedelta(days=1)).isoformat() if "date" in ev.get("end", {}) else ev["end"]["dateTime"][:10]


def _start(ev: dict) -> str:
    return ev["start"].get("date") or ev["start"]["dateTime"][:10]


def listing(d_from: date, d_to: date) -> list[dict]:
    mains: dict[str, dict] = {}
    vehs: dict[str, dict] = {}
    for bu, cal in calendars_by_bu().items():
        for ev in backend().list(cal, d_from, d_to):
            sh = (ev.get("extendedProperties") or {}).get("shared", {})
            if sh.get("kind") == "main":
                mains[sh["lbid"]] = {**ev, "_cal": cal}
            elif sh.get("kind") == "vehicles":
                vehs[sh["lbid"]] = ev
    out = []
    for lbid, ev in mains.items():
        sh = ev["extendedProperties"]["shared"]
        desc = ev.get("description", "")
        notes = desc.split(SEP)[0] if SEP in desc else ("" if desc.startswith(SEP.lstrip("\n")) else desc)
        title = ev.get("summary", "")
        if title.startswith(TBC):
            title = title[len(TBC):]
        if sh.get("transport") == "1" and title.lower().startswith(TRANSPORT):
            title = title[len(TRANSPORT):]
        att = ev.get("attendees", [])
        vehicles = [a["email"] for a in att if a.get("resource")] + [a["email"] for a in (vehs[lbid].get("attendees", []) if lbid in vehs else []) if a.get("resource")]
        responses = {a["email"]: a.get("responseStatus", "needsAction") for a in att}          # accepted | needsAction | declined | tentative
        if lbid in vehs:
            responses.update({a["email"]: a.get("responseStatus", "needsAction") for a in vehs[lbid].get("attendees", [])})
        imm = sh.get("immo", "").split("/")
        out.append({"id": lbid, "bu": sh.get("bu", ""), "title": title, "confirmed": sh.get("confirmed") == "1", "transport": sh.get("transport") == "1",
                    "start_time": ev["start"]["dateTime"][11:16] if "dateTime" in ev["start"] else "", "end_time": ev["end"]["dateTime"][11:16] if "dateTime" in ev["end"] else "",
                    "start": _start(ev), "end": _inc_end(ev), "immo_start": imm[0] if len(imm) == 2 else _start(ev), "immo_end": imm[1] if len(imm) == 2 else _inc_end(ev),
                    "place": {"id": sh.get("place", ""), "address": ev.get("location", "")}, "origin": {"id": sh["origin"], "address": sh.get("origin_addr", "")} if sh.get("origin") else None, "notes": notes, "km": int(sh["km"]) if sh.get("km", "").isdigit() else None,
                    "via": [x for x in sh.get("via", "").split(",") if x], "staff_and_external": [a["email"] for a in att if not a.get("resource")], "externals_pending": [x for x in sh.get("pending", "").split(",") if x], "responses": responses, "vehicles": vehicles})
    return sorted(out, key=lambda x: (x["start"], x["title"]))


def busy(emails: list[str], d_from: date, d_to: date) -> dict[str, list[dict]]:
    return backend().busy(emails, d_from, d_to)


# ---- Vue Planning (lecture seule, tous les utilisateurs) -----------------------------------------------------------------------------------

BU_KEYS = tuple(BUS)


RACE_CATEGORIES = {"rally", "circuit"}      # voitures de course : ressources de la BU CARS


def restrict_to_bu(view: dict, lock: str | None) -> dict:
    """Utilisateur dont les droits se limitent à une BU : il ne voit ni les événements des autres BU, ni (pour XC) les voitures de course Rally / Circuit."""
    if not lock:
        return view
    ev = [e for e in view["events"] if e["bu"] != "OTHERS" and (e["bu"] == "XC") == (lock == "XC")]     # Others (transports privés) : réservé aux utilisateurs non limités à une BU
    res = [r for r in view["resources"] if not (lock == "XC" and r["kind"] == "vehicle" and r.get("category") in RACE_CATEGORIES)]
    cats = [c for c in view.get("categories", []) if not (lock == "XC" and c["id"] in RACE_CATEGORIES)]
    return {**view, "events": ev, "resources": res, "categories": cats}


def planning_view(d_from: date, d_to: date) -> dict:
    """Événements de la période et ressources, sans adresses e-mail ni données de paie : les invités sont désignés par un identifiant de ressource
    (`s:` staff interne, `x:` staff externe, `v:` véhicule) ; {resources, events, categories}."""
    from . import resources, staff
    res, by_email = [], {}
    for p in staff.store().get()["data"]["people"]:
        if not p.get("active", True):
            continue
        rid = "s:" + p["id"]
        res.append({"id": rid, "kind": "staff", "name": p["name"], "bus": staff.resource_bus(p), "all_bus": bool(p.get("all_bus")), "function": p.get("function", "")})
        if p.get("google_email"):
            by_email[p["google_email"].lower()] = rid
    for x in resources.store().get()["data"]["externals"]:
        rid = "x:" + str(x["partner_id"])
        res.append({"id": rid, "kind": "external", "name": x["name"], "bus": list(x.get("bus") or []), "all_bus": False, "company": x.get("company", "")})
        if x.get("email"):
            by_email[x["email"].lower()] = rid
    veh = resources.vehicles()
    for i, v in enumerate(veh.get("items", [])):
        rid = f"v:{i}"
        res.append({"id": rid, "kind": "vehicle", "name": v["name"], "category": v.get("category", "other"), "type": v.get("type", ""), "bus": [], "all_bus": False})
        if v.get("email"):
            by_email[v["email"].lower()] = rid
    events = []
    for e in listing(d_from, d_to):
        people, vehicles, other = [], [], 0
        resp = e.get("responses", {})
        for email in e["staff_and_external"]:
            rid = by_email.get(email.lower())
            if rid:
                people.append({"rid": rid, "status": resp.get(email, "needsAction")})
            else:
                other += 1
        for email in e["vehicles"]:
            rid = by_email.get(email.lower())
            if rid:
                vehicles.append({"rid": rid, "status": resp.get(email, "needsAction")})
        pending = [by_email.get(x.lower()) for x in e.get("externals_pending", [])]
        events.append({"id": e["id"], "bu": e["bu"], "title": e["title"], "confirmed": e["confirmed"], "transport": e.get("transport", False), "start_time": e.get("start_time", ""), "end_time": e.get("end_time", ""), "start": e["start"], "end": e["end"], "immo_start": e["immo_start"], "immo_end": e["immo_end"],
                       "place": e["place"]["address"], "km": e["km"], "via": e["via"], "notes": e["notes"], "people": people, "vehicles": vehicles,
                       "pending": [r for r in pending if r], "other_guests": other})
    from . import leaves
    try:
        lv = leaves.planning_leaves(d_from, d_to)
    except Exception:
        lv = []
    return {"resources": res, "events": events, "leaves": lv, "categories": veh.get("categories", []), "vehicles_message": veh.get("message")}
