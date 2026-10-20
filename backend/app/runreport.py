"""Run reports : le rapport remis au client après un meeting (une épreuve, une voiture).

Les chiffres viennent des roulages (chronométrage Al Kamel : meilleur tour, position, secteurs, vitesse de pointe, météo ; sessions non chronométrées saisies à la main) ;
l'ingénieur ajoute par run les objectifs, le setup, les pressions de pneus, ses observations et le retour du pilote, puis les pneus et les actions. Le rapport est
validé (verrouillé) par le chef d'atelier, l'ingénieur / coordinateur ou le Super User, puis visible dans l'accès client (sans la rubrique logistique, interne)."""
from __future__ import annotations

import html
import re
from datetime import date, datetime, timezone

from pydantic import BaseModel, Field

from . import alkamel, rides, tyres
from .timesheets import Coll

_coll = None
KINDS = {"practice": "FP", "qualifying": "Q", "race": "R"}
KIND_LABEL = {"practice": ("Essais libres", "Free practice"), "qualifying": ("Qualifications", "Qualifying"), "race": ("Course", "Race")}


def coll() -> Coll:
    global _coll
    _coll = _coll or Coll("run_reports")
    return _coll


def rid(meeting: str, car: str) -> str:
    return f"{meeting}__{car}"[:200]


class RunNote(BaseModel):
    objective: str = Field(default="", max_length=600)
    setup: str = Field(default="", max_length=600)
    tyres_start: list[str] = Field(default_factory=lambda: ["", "", "", ""], max_length=4)        # AV G, AV D, AR G, AR D (bar)
    tyres_end: list[str] = Field(default_factory=lambda: ["", "", "", ""], max_length=4)
    tyre_temp: str = Field(default="", max_length=30)
    observations: str = Field(default="", max_length=3000)
    driver_feedback: str = Field(default="", max_length=3000)
    fuel_l: float | None = Field(default=None, ge=0, le=2000)
    fuel_note: str = Field(default="", max_length=120)


class TyreSet(BaseModel):
    set: str = Field(default="", max_length=40)
    model: str = Field(default="", max_length=60)
    laps: int | None = Field(default=None, ge=0, le=5000)
    km: float | None = Field(default=None, ge=0, le=100000)


class ReportIn(BaseModel):
    header: dict[str, str] = Field(default_factory=dict)                                              # type_of_event, car_chief, engineer, driver, codriver
    general: str = Field(default="", max_length=6000)
    runs: dict[str, RunNote] = Field(default_factory=dict)
    tyre_sets: list[TyreSet] = Field(default_factory=list, max_length=20)
    pressure_base: str = Field(default="", max_length=1500)
    actions_car: str = Field(default="", max_length=4000)
    actions_logistics: str = Field(default="", max_length=4000)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---- Données du meeting -------------------------------------------------------------------------------------------------------------------

def _event_of(s: dict) -> str:
    return s.get("event") or (s.get("alkamel") or {}).get("event") or s["name"].split(" — ")[0]


def meetings() -> list[dict]:
    """Épreuves (regroupement `meeting` des roulages) avec leurs voitures et l'état de leur rapport."""
    out: dict[str, dict] = {}
    runs = rides.runs_coll().all()
    names = {c["key"]: c["name"] for c in rides.race_cars()}
    saved = {r["id"]: r for r in coll().all()}
    for s in rides.sessions_coll().all():
        m = s.get("meeting")
        if not m:
            continue
        e = out.setdefault(m, {"meeting": m, "event": _event_of(s), "from": s["date"], "to": s["date"], "circuit": s.get("circuit", ""), "cars": {}})
        e["from"], e["to"] = min(e["from"], s["date"]), max(e["to"], s["date"])
        for r in runs:
            if r.get("session_id") == s["id"] and r["vehicle"] in names:
                c = e["cars"].setdefault(r["vehicle"], {"key": r["vehicle"], "name": names[r["vehicle"]], "sessions": 0, "km": 0.0})
                c["sessions"] += 1
                c["km"] = round(c["km"] + (r.get("km") or 0), 1)
    res = []
    for e in out.values():
        for c in e["cars"].values():
            d = saved.get(rid(e["meeting"], c["key"]))
            c["status"] = (d or {}).get("status", "none")
        e["cars"] = sorted(e["cars"].values(), key=lambda c: c["name"].lower())
        res.append(e)
    return sorted(res, key=lambda e: (e["to"], e["event"]), reverse=True)


def _entries(meeting: str, car: str) -> list[dict]:
    """Les participations de la voiture au meeting, par date puis par ordre de session (essais, qualifications, course)."""
    order = {"practice": 0, "qualifying": 1, "race": 2}
    sess = {s["id"]: s for s in rides.sessions_coll().all() if s.get("meeting") == meeting}
    out = []
    for r in rides.runs_coll().all():
        s = sess.get(r.get("session_id"))
        if not s or r["vehicle"] != car:
            continue
        alk = s.get("alkamel") or {}
        out.append({"run_id": r["id"], "session_id": s["id"], "name": s["name"], "date": s["date"], "kind": alk.get("kind") or "", "session": alk.get("session") or s["name"].split(" — ")[-1],
                    "laps": r.get("laps", 0), "km": r.get("km"), "hours": r.get("hours"), "drivers": r.get("drivers", []), "conditions": alk.get("conditions") or {}, "timing": r.get("timing")})
    out.sort(key=lambda x: (x["date"], order.get(x["kind"], 3), x["name"]))
    for i, e in enumerate(out, 1):
        e["n"] = i
    return out


def _days(entries: list[dict], notes: dict) -> list[dict]:
    days: dict[str, dict] = {}
    for e in entries:
        d = days.setdefault(e["date"], {"date": e["date"], "best": None, "runs": 0, "laps": 0, "km": 0.0, "fuel": 0.0, "fuel_known": False})
        d["runs"] += 1
        d["laps"] += e["laps"] or 0
        d["km"] = round(d["km"] + (e["km"] or 0), 1)
        t = alkamel.secs(((e["timing"] or {}).get("best")) or "")
        if t and (d["best"] is None or t < d["best"]):
            d["best"] = t
        f = (notes.get(e["run_id"]) or {}).get("fuel_l")
        if f:
            d["fuel"] += f
            d["fuel_known"] = True
    return [{**d, "best": alkamel.fmt(d["best"]) if d["best"] else "", "fuel": round(d["fuel"], 1) if d["fuel_known"] else None} for d in sorted(days.values(), key=lambda x: x["date"])]


def view(meeting: str, car: str) -> dict:
    c = rides.car_of(car)
    if not c:
        raise LookupError("Voiture introuvable")
    entries = _entries(meeting, car)
    if not entries:
        raise LookupError("Aucun roulage de cette voiture pour cette épreuve")
    doc = coll().get(rid(meeting, car)) or {}
    meta = rides.cars_coll().get(car) or {}
    sessions = [s for s in rides.sessions_coll().all() if s.get("meeting") == meeting]
    first = sessions[0]
    drivers: list[str] = []
    for e in entries:
        for d in e["drivers"]:
            if d not in drivers:
                drivers.append(d)
    header = {"type_of_event": "", "car_chief": "", "engineer": "", "driver": ", ".join(drivers[:2]), "codriver": ""} | (doc.get("header") or {})
    notes = doc.get("runs") or {}
    circ = rides.circuits_coll().get(rides.circuit_id(first.get("circuit", ""))) if first.get("circuit") else None
    return {"id": rid(meeting, car), "meeting": meeting, "car": car, "car_name": c["name"], "race_number": meta.get("race_number", ""), "chassis": meta.get("chassis", ""),
            "event": _event_of(first), "series": ((first.get("alkamel") or {}).get("series") or ""), "circuit": first.get("circuit", ""), "length_km": (circ or {}).get("length_km"),
            "from": min(e["date"] for e in entries), "to": max(e["date"] for e in entries), "header": header,
            "general": doc.get("general", ""), "runs": notes, "tyre_sets": doc.get("tyre_sets", []), "pressure_base": doc.get("pressure_base", ""),
            "actions_car": doc.get("actions_car", ""), "actions_logistics": doc.get("actions_logistics", ""),
            "status": doc.get("status", "draft") if doc else "draft", "validated_by": doc.get("validated_by", ""), "validated_at": doc.get("validated_at", ""),
            "entries": entries, "tyres_auto": tyres.for_meeting(meeting, car), "days": _days(entries, notes), "km_total": round(sum(e["km"] or 0 for e in entries), 1)}


# ---- Enregistrement -----------------------------------------------------------------------------------------------------------------------

def save(meeting: str, car: str, data: ReportIn, user: str) -> dict:
    v = view(meeting, car)
    cur = coll().get(v["id"]) or {}
    if cur.get("status") == "validated":
        raise ValueError("Rapport validé : rouvrez-le pour le modifier")
    valid_runs = {e["run_id"] for e in v["entries"]}
    doc = {"id": v["id"], "meeting": meeting, "car": car, "header": {k: str(x)[:120] for k, x in data.header.items() if k in ("type_of_event", "car_chief", "engineer", "driver", "codriver")},
           "general": data.general, "runs": {k: n.model_dump() for k, n in data.runs.items() if k in valid_runs}, "tyre_sets": [t.model_dump() for t in data.tyre_sets if t.set.strip() or t.model.strip()],
           "pressure_base": data.pressure_base, "actions_car": data.actions_car, "actions_logistics": data.actions_logistics, "status": "draft",
           "created_by": cur.get("created_by", user.lower()), "created_at": cur.get("created_at", _now()), "updated_by": user.lower(), "updated_at": _now()}
    coll().put(v["id"], doc)
    return view(meeting, car)


def set_status(meeting: str, car: str, validated: bool, user: str) -> dict:
    v = view(meeting, car)
    cur = coll().get(v["id"])
    if not cur:
        raise ValueError("Enregistrez d'abord le rapport")
    if validated:
        cur.update(status="validated", validated_by=user.lower(), validated_at=_now())
    else:
        cur.update(status="draft", validated_by="", validated_at="")
    coll().put(v["id"], cur)
    return view(meeting, car)


def delete(meeting: str, car: str) -> None:
    coll().delete(rid(meeting, car))


def validated_for_car(car: str) -> list[dict]:
    """Rapports validés d'une voiture (accès client)."""
    out = []
    for d in coll().all():
        if d.get("car") == car and d.get("status") == "validated":
            try:
                v = view(d["meeting"], car)
            except LookupError:
                continue
            out.append({"meeting": d["meeting"], "event": v["event"], "from": v["from"], "to": v["to"], "circuit": v["circuit"], "km_total": v["km_total"]})
    return sorted(out, key=lambda x: x["to"], reverse=True)


# ---- Feuille imprimable --------------------------------------------------------------------------------------------------------------------

def _bullets(text: str) -> list[str]:
    return [re.sub(r"^\s*[-•●*]\s*", "", ln).strip() for ln in (text or "").splitlines() if ln.strip()]


def _laps_svg(laps: list[dict], best: str) -> str:
    """Temps au tour d'un run (hors tours de stands et tours très lents)."""
    b = alkamel.secs(best)
    pts = [(lap["n"], alkamel.secs(lap["time"])) for lap in laps if "pit" not in lap.get("flags", []) and alkamel.secs(lap["time"])]
    if b:                                                                   # sans les tours invalidés (plus rapides que le meilleur officiel) ni les tours très lents
        pts = [p for p in pts if b - 0.0005 <= p[1] <= b * 1.2]
    if len(pts) < 3:
        return ""
    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
    w, h, pl, pb = 520, 150, 46, 22
    X = lambda x: pl + (x - x0) / ((x1 - x0) or 1) * (w - pl - 8)
    Y = lambda y: 8 + (y - y0) / ((y1 - y0) or 1) * (h - pb - 12)
    line = " ".join(f"{X(x):.1f},{Y(y):.1f}" for x, y in pts)
    dots = "".join(f'<circle cx="{X(x):.1f}" cy="{Y(y):.1f}" r="2.2" fill="#2B2B2B"/>' for x, y in pts)
    grid = "".join(f'<line x1="{pl}" x2="{w - 8}" y1="{Y(v):.1f}" y2="{Y(v):.1f}" stroke="#DCDCD8"/><text x="{pl - 4}" y="{Y(v) + 3:.1f}" text-anchor="end" font-size="9" fill="#5C6167">{alkamel.fmt(v)}</text>' for v in (y0, (y0 + y1) / 2, y1))
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" style="max-width:520px" role="img" aria-label="lap times">{grid}<polyline points="{line}" fill="none" stroke="#2B2B2B" stroke-width="1.4"/>{dots}'
            f'<text x="{pl}" y="{h - 6}" font-size="9" fill="#5C6167">{x0}</text><text x="{w - 8}" y="{h - 6}" text-anchor="end" font-size="9" fill="#5C6167">{x1}</text></svg>')


def _gap(g: str, en: bool) -> str:
    m = re.fullmatch(r"(\d+) Laps?", g.strip())
    return g if not m or en else f"{m.group(1)} tour{'s' if int(m.group(1)) > 1 else ''}"


def _d(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso or ""


def print_page(v: dict, lang: str = "fr", client: bool = False) -> str:
    from . import tforms
    e = html.escape
    en = lang == "en"
    T = lambda fr, eng: eng if en else fr
    h = v["header"]
    title = f"{(h.get('driver') or '').upper()} / {v['car_name']}".strip(" /") + (f" #{v['race_number']}" if v["race_number"] else "")
    rows = [(T("Date", "Date"), f"{_d(v['from'])} → {_d(v['to'])}" if v["from"] != v["to"] else _d(v["from"])), (T("Circuit", "Track"), v["circuit"]), (T("Type d'épreuve", "Type of event"), h.get("type_of_event") or v["series"]),
            (T("Longueur du tour (km)", "Length / lap (km)"), f"{v['length_km']:g}" if v["length_km"] else ""), (T("Voiture (châssis)", "Car (chassis)"), (v["car_name"] + (f" #{v['race_number']}" if v["race_number"] else ""))),
            (T("Pilote (D1)", "Driver (D1)"), h.get("driver", "")), (T("Co-pilote (D2)", "Co-driver (D2)"), h.get("codriver", "")), (T("Chef mécanicien", "Car chief"), h.get("car_chief", "")), (T("Ingénieur", "Engineer"), h.get("engineer", ""))]
    cover = f'<div class="head" style="grid-template-columns:1fr 1fr">{"".join(f"<div><span>{e(k)}</span>{e(str(x))}</div>" for k, x in rows if x)}</div>'
    notes = v["runs"]
    # 1. synthèse par jour
    syn = "".join(f"<tr><td>{_d(d['date'])}</td><td class='k'>{e(d['best'] or '–')}</td><td>{d['runs']}</td><td>{d['laps']}</td><td>{d['km']:g}</td><td>{'' if d['fuel'] is None else str(d['fuel']) + ' L'}</td></tr>" for d in v["days"])
    out = [f"<h3>1. {T('Synthèse générale', 'General summary')}</h3><table><thead><tr><th>{T('Jour', 'Day')}</th><th>{T('Meilleur tour', 'Best lap')}</th><th>{T('Runs', 'Runs')}</th><th>{T('Tours', 'Laps')}</th><th>{T('Km', 'Km')}</th><th>{T('Carburant', 'Fuel')}</th></tr></thead><tbody>{syn}</tbody></table>"
           f"<p><b>{T('Kilométrage total', 'Total mileage')} : {v['km_total']:g} km</b></p>"]
    gen = _bullets(v["general"])
    if gen:
        out.append(f"<h3>2. {T('Observations générales', 'General observations')}</h3><ul>{''.join(f'<li>{e(x)}</li>' for x in gen)}</ul>")
    # 3. détail par run
    out.append(f"<h3>3. {T('Détail par run', 'Detail by run')}</h3>")
    for ent in v["entries"]:
        n = notes.get(ent["run_id"]) or {}
        tm = ent["timing"] or {}
        sm = tm.get("summary") or {}
        kind = KINDS.get(ent["kind"], "")
        lab = T(*KIND_LABEL[ent["kind"]]) if ent["kind"] in KIND_LABEL else ent["session"]
        drv = ", ".join(ent["drivers"])
        cond = ent["conditions"]
        cl = ", ".join(x for x in (f"{cond['track_c']:g}°C track" if en and cond.get("track_c") is not None else f"{cond['track_c']:g}°C piste" if cond.get("track_c") is not None else "",
                                   f"{cond['air_c']:g}°C air" if cond.get("air_c") is not None else "", (cond.get("status") or "").lower()) if x)
        blk = [f"<section><h3>RUN {ent['n']} — {e(lab)}{' (' + kind + ')' if kind else ''} <small>{_d(ent['date'])}{' · ' + e(drv) if drv else ''}</small></h3>"]
        meta = []
        if cl:
            meta.append(f"<b>{T('Conditions', 'Conditions')}</b> : {e(cl)}")
        if n.get("objective"):
            meta.append(f"<b>{T('Objectifs', 'Objectives')}</b> : {e(n['objective'])}")
        if n.get("setup"):
            meta.append(f"<b>Setup</b> : {e(n['setup'])}")
        if meta:
            blk.append("<p>" + "<br>".join(meta) + "</p>")
        if tm:
            gap = f", {T('écart', 'gap')} {e(_gap(str(tm['gap']), en))}" if tm.get("gap") and tm.get("gap") != "-" else ""
            line = [f"{T('Tours', 'Laps')} : {ent['laps']}", f"{T('Meilleur tour', 'Best lap')} : {e(tm.get('best') or '–')}"]
            if tm.get("pos"):
                line.append(f"{T('Classement', 'Position')} : {tm['pos']}{gap}")
            if tm.get("grid") is not None:
                pass
            blk.append(f"<p><b>Al Kamel</b> — {' · '.join(line)}</p>")
            rk, gp = sm.get("rank") or {}, sm.get("gap") or {}
            if rk:
                srow = "".join(f"<tr><td>{lbl}</td><td class='k'>{e(str((sm.get('sectors') or {}).get(k, '')))}</td><td>{rk.get(k, '')}/{sm.get('field', '')}</td><td>{('+%.3f' % gp[k]) if gp.get(k) else '–'}</td></tr>" for k, lbl in (("s1", "S1"), ("s2", "S2"), ("s3", "S3")))
                top = f"<tr><td>{T('Vitesse de pointe', 'Top speed')}</td><td class='k'>{sm.get('top_speed') or ''} km/h</td><td>{rk.get('top', '')}/{sm.get('field', '')}</td><td></td></tr>" if sm.get("top_speed") else ""
                ideal = f"<tr><td>{T('Tour théorique', 'Ideal lap')}</td><td class='k'>{e(sm.get('ideal') or '')}</td><td>{rk.get('ideal', '')}/{sm.get('field', '')}</td><td></td></tr>" if sm.get("ideal") else ""
                blk.append(f"<table class='m'><thead><tr><th></th><th>{T('Meilleur', 'Best')}</th><th>{T('Rang', 'Rank')}</th><th>{T('Écart au meilleur', 'Gap to best')}</th></tr></thead><tbody>{srow}{top}{ideal}</tbody></table>")
            st = tm.get("story")
            if st:
                blk.append(f"<p>{T('Départ', 'Start')} : P{tm.get('grid') or st['start']} → {T('arrivée', 'finish')} : P{st['finish']} · {T('meilleure position', 'best position')} P{st['best']}" + (f" · {T('tours en tête', 'laps led')} : {st['led']}" if st.get("led") else "") + "</p>")
            svg = _laps_svg(tm.get("lap_list") or [], tm.get("best") or "")
            if svg:
                blk.append(f"<div class='chart'>{svg}</div>")
        ts, te = [x for x in n.get("tyres_start", [])], [x for x in n.get("tyres_end", [])]

        def pr(lst):
            lst = (lst + ["", "", "", ""])[:4]
            return f"<table class='m'><tbody><tr><td>{e(lst[0])}</td><td>{e(lst[1])}</td></tr><tr><td>{e(lst[2])}</td><td>{e(lst[3])}</td></tr></tbody></table>"
        if any(ts):
            blk.append(f"<p><b>{T('Pneus départ', 'Start tyres')}</b>{' : ' + e(n['tyre_temp']) if n.get('tyre_temp') else ''}</p>{pr(ts)}")
        if n.get("observations"):
            blk.append(f"<p><b>{T('Observations', 'Observations')}</b></p><ul>{''.join(f'<li>{e(x)}</li>' for x in _bullets(n['observations']))}</ul>")
        if n.get("driver_feedback"):
            blk.append(f"<p><b>{T('Retour pilote', 'Driver feedback')}</b></p><ul>{''.join(f'<li>{e(x)}</li>' for x in _bullets(n['driver_feedback']))}</ul>")
        if any(te):
            blk.append(f"<p><b>{T('Pneus fin', 'End tyres')}</b></p>{pr(te)}")
        if n.get("fuel_l"):
            blk.append(f"<p>{T('Carburant', 'Fuel')} : {n['fuel_l']:g} L{' — ' + e(n['fuel_note']) if n.get('fuel_note') else ''}</p>")
        blk.append("</section>")
        out.append("".join(blk))
    # 4. pneus
    auto = v.get("tyres_auto") or []
    rows_a = "".join(f"<tr><td>{e(t['ref'])}</td><td>{e((t['brand'] + ' ' + t['model']).strip() + (' · ' + t['compound'] if t.get('compound') else ''))}</td><td>{t['laps']}</td><td>{t['km']:g}</td><td>{t['total_km']:g}</td></tr>" for t in auto)
    auto_html = f"<table><thead><tr><th>Set</th><th>{T('Modèle', 'Model')}</th><th>{T('Tours', 'Laps')}</th><th>{T('Km (meeting)', 'Km (meeting)')}</th><th>{T('Km (total du set)', 'Km (set total)')}</th></tr></thead><tbody>{rows_a}</tbody></table>" if auto else ""
    if v["tyre_sets"] or v["pressure_base"] or auto:
        rows_t = "".join(f"<tr><td>{e(t['set'])}</td><td>{e(t['model'])}</td><td>{t['laps'] if t.get('laps') is not None else ''}</td><td>{t['km'] if t.get('km') is not None else ''}</td></tr>" for t in v["tyre_sets"])
        out.append(f"<h3>4. {T('Pneumatiques', 'Tyres')}</h3>" + auto_html + (f"<table><thead><tr><th>Set</th><th>{T('Modèle', 'Model')}</th><th>{T('Tours', 'Laps')}</th><th>{T('Kilométrage', 'Mileage')}</th></tr></thead><tbody>{rows_t}</tbody></table>" if rows_t else "")
                   + (f"<p><b>{T('Base de pression', 'Pressure base')}</b></p><ul>{''.join(f'<li>{e(x)}</li>' for x in _bullets(v['pressure_base']))}</ul>" if v["pressure_base"] else ""))
    ac = _bullets(v["actions_car"])
    if ac:
        out.append(f"<h3>5. {T('Actions à améliorer pour le prochain meeting (voiture)', 'Actions to improve for the next meeting (car)')}</h3><ul>{''.join(f'<li>{e(x)}</li>' for x in ac)}</ul>")
    al = _bullets(v["actions_logistics"])
    if al and not client:
        out.append(f"<h3>6. {T('Actions à améliorer pour le prochain meeting (logistique)', 'Actions to improve for the next meeting (logistics)')}</h3><ul>{''.join(f'<li>{e(x)}</li>' for x in al)}</ul>")
    f = {"id": v["id"], "validated": v["status"] == "validated"}
    body = f"<style>ul{{margin:4px 0 8px 18px;padding:0}}.chart{{margin:6px 0}}section{{margin-bottom:10px}}</style>{cover}{''.join(out)}"
    page = tforms._shell(title or v["car_name"], lang, body, f, valid=T("Rapport validé", "Approved report") if f["validated"] else T("Brouillon", "Draft"))
    return page
