"""Planifier › Événements : création, modification et suppression des événements dans les agendas Google des BU (agenda « Libellé=adresse » de CALENDAR_IDS).

Un événement Logbook = un événement « principal » (dates de l'événement ; staff et, une fois confirmé, prestataires invités) et, si les dates d'immobilisation
diffèrent, un événement « Immobilisation » lié (véhicules invités comme ressources). Tout est reconnu par des propriétés partagées (logbook, kind, lbid) :
Google Agenda reste la seule source de vérité. Accès Google : délégation à l'échelle du domaine (gauth). En démo : mémoire."""
from __future__ import annotations

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
# BU proposées pour un événement : identifiant -> (libellé, couleur Google Agenda de la charte, clé de BU de gcal.calendars())
BUS = {"XC": ("XC", "11"), "MODERN_RALLY": ("Modern Rally", "9"), "HISTORIC_RALLY": ("Historic Rally", "5"), "HISTORIC_RACING": ("Historic Racing", "10")}


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
    start: date
    end: date
    immo_start: date
    immo_end: date
    place: Place
    origin: Place | None = None                                        # lieu de départ (sinon Lifelive, LIFELIVE_ORIGIN)
    notes: str = Field(default="", max_length=2000)
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
                raise ValueError("adresse e-mail invalide")
            if x not in out:
                out.append(x)
        return out

    @model_validator(mode="after")
    def _dates(self):
        if self.end < self.start:
            raise ValueError("la fin de l'événement précède son début")
        if self.immo_start > self.start or self.immo_end < self.end:
            raise ValueError("l'immobilisation doit couvrir l'événement")
        if not self.confirmed and len(",".join(self.externals)) > 900:
            raise ValueError("trop de prestataires pour un événement non confirmé")
        return self


class BusyBody(BaseModel):
    emails: list[str] = Field(max_length=40)
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
        j = self._chk(self._s().post(f"{API}/freeBusy", json={"timeMin": t0, "timeMax": t1, "timeZone": "Europe/Brussels", "items": [{"id": e} for e in emails]}, timeout=30)).json()
        return {e: (c.get("busy") or []) for e, c in (j.get("calendars") or {}).items()}


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
            e.update(body)
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
            s, en = date.fromisoformat(e["start"]["date"]), date.fromisoformat(e["end"]["date"]) - timedelta(days=1)
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
    return {bu: cid for cid, _label, bu in gcal.calendars() if bu in BUS}


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
    return e.title.strip() if e.confirmed else TBC + e.title.strip()


def _shared(e: EventIn, lbid: str, kind: str, route: dict | None) -> dict:
    sh = {"logbook": "1", "kind": kind, "lbid": lbid, "bu": e.bu, "confirmed": "1" if e.confirmed else "0", "place": e.place.id,
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


def build_main(e: EventIn, lbid: str, route: dict | None) -> dict:
    single = e.vehicles and (e.immo_start, e.immo_end) == (e.start, e.end)
    att = [{"email": x} for x in e.staff] + ([{"email": x} for x in e.externals] if e.confirmed else [])
    att += [{"email": x, "resource": True} for x in e.vehicles] if single else []
    return {"summary": _title(e), "description": _description(e.notes, e.place, route, e.origin), "location": e.place.address or e.place.name, "colorId": BUS[e.bu][1],
            "start": _day(e.start), "end": _day(e.end + timedelta(days=1)), "attendees": att,
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
    backend().insert(cal, main, notify=bool(main["attendees"]))
    if wants_vehicle_event(e):
        backend().insert(cal, build_vehicles(e, lbid), notify=False)
    return {"id": lbid, "route": route}


def update(lbid: str, e: EventIn) -> dict:
    main, veh, cal_main = _find(lbid)
    if main is None:
        raise KeyError(lbid)
    if cal_main != _cal(e.bu):                                         # changement de BU = autre agenda : on supprime puis on recrée (même identifiant Logbook)
        remove(lbid)
        return create(e, lbid)
    route = _route(e.place, e.origin)
    body = build_main(e, lbid, route)
    backend().patch(cal_main, main["id"], body, notify=True)
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
        att = ev.get("attendees", [])
        vehicles = [a["email"] for a in att if a.get("resource")] + [a["email"] for a in (vehs[lbid].get("attendees", []) if lbid in vehs else []) if a.get("resource")]
        imm = sh.get("immo", "").split("/")
        out.append({"id": lbid, "bu": sh.get("bu", ""), "title": title[len(TBC):] if title.startswith(TBC) else title, "confirmed": sh.get("confirmed") == "1",
                    "start": _start(ev), "end": _inc_end(ev), "immo_start": imm[0] if len(imm) == 2 else _start(ev), "immo_end": imm[1] if len(imm) == 2 else _inc_end(ev),
                    "place": {"id": sh.get("place", ""), "address": ev.get("location", "")}, "origin": {"id": sh["origin"], "address": sh.get("origin_addr", "")} if sh.get("origin") else None, "notes": notes, "km": int(sh["km"]) if sh.get("km", "").isdigit() else None,
                    "via": [x for x in sh.get("via", "").split(",") if x], "staff_and_external": [a["email"] for a in att if not a.get("resource")], "externals_pending": [x for x in sh.get("pending", "").split(",") if x], "vehicles": vehicles})
    return sorted(out, key=lambda x: (x["start"], x["title"]))


def busy(emails: list[str], d_from: date, d_to: date) -> dict[str, list[dict]]:
    return backend().busy(emails, d_from, d_to)
