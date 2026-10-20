"""Pointages › Jobs : formulaires techniques rattachés à un job (phase 5). Premier type : mesure d'embrayage (4 ou 6 patins), d'après les fiches Excel
« Mesure_Embrayage_4patins / 6patins ». Un formulaire = un document `timesheet_forms` (job, type, valeurs saisies) ; les calculs (épaisseur moyenne, usure, usure aux
1 000 km, kilométrage restant estimé, conicité) sont refaits côté serveur à chaque lecture, jamais stockés. Le mécanicien saisit, le chef d'atelier valide (le formulaire
est alors verrouillé) ; une feuille imprimable aux couleurs de Lifelive (GET .../print, « Enregistrer en PDF » du navigateur) reprend la fiche."""
from __future__ import annotations

import html
import uuid
from datetime import date
from pathlib import Path

from . import rides, tcheck, timesheets, tmodels, tsheet
from .timesheets import Coll

CLUTCH_SET = "Embrayage"   # ensemble du Garage dont les pièces peuvent être liées à la mesure
EP0 = 6.0          # épaisseur d'un disque neuf (mm), d'après l'intitulé des fiches
MINI = 4.6         # épaisseur minimale (mm), idem

# Les fiches 4 et 6 patins partagent l'en-tête et les plateaux ; seuls les disques changent (4 patins : 2 mesures, en haut et en bas, par patin ; 6 patins : 1 mesure par patin).
FORM_TYPES = {
    "clutch4": {"label": "Mesure d'embrayage — 4 patins", "pads_per_measure": 2, "measure_names": ["Haut", "Bas"],
                "discs": [{"id": "motor", "label": "Disque côté moteur", "pads": 4}, {"id": "gearbox", "label": "Disque côté BV", "pads": 4}],
                "plates": [{"id": "pressure", "label": "Presseur"}, {"id": "inter", "label": "Intermédiaire"}], "spring_fingers": False},
    "clutch6": {"label": "Mesure d'embrayage — 6 patins", "pads_per_measure": 1, "measure_names": [""],
                "discs": [{"id": "motor", "label": "Disque côté moteur", "pads": 6}, {"id": "central", "label": "Disque central", "pads": 6}, {"id": "gearbox", "label": "Disque côté BV", "pads": 6}],
                "plates": [{"id": "pressure", "label": "Presseur"}, {"id": "inter1", "label": "Intermédiaire 1"}, {"id": "inter2", "label": "Intermédiaire 2"}], "spring_fingers": True},
}
PLATE_POINTS = 6   # « prendre 6 mesures » par plateau
HEADER = ("after", "mechanism", "gearbox", "chassis", "km", "date", "mechanic")

_forms: Coll | None = None


def forms() -> Coll:
    global _forms
    _forms = _forms or Coll("timesheet_forms")
    return _forms


def types() -> list[dict]:
    clutch = [{"id": k, "kind": "clutch", **{f: v[f] for f in ("label", "pads_per_measure", "measure_names", "discs", "plates", "spring_fingers")}, "ep0": EP0, "mini": MINI, "plate_points": PLATE_POINTS}
              for k, v in FORM_TYPES.items()]
    return clutch + tmodels.effective_types()


def label_of(ftype: str) -> str:
    if ftype in FORM_TYPES:
        return FORM_TYPES[ftype]["label"]
    m = tmodels.spec_of(ftype)
    return m[1]["label"] if m else ftype


def is_clutch(ftype: str) -> bool:
    return ftype in FORM_TYPES


def _num(v, lo: float, hi: float) -> float | None:
    if v is None or v == "":
        return None
    try:
        x = float(str(v).replace(",", "."))
    except ValueError:
        raise ValueError(f"Valeur invalide : {v}")
    if not lo <= x <= hi:
        raise ValueError(f"Valeur hors limites ({lo} à {hi}) : {v}")
    return round(x, 2)


def clean(ftype: str, data: dict) -> dict:
    """Normalise ce que le mécanicien a saisi : le gabarit du type fixe le nombre de disques, de patins et de mesures."""
    m = tmodels.spec_of(ftype) if ftype not in FORM_TYPES else None
    if m:
        out = (tcheck if m[0] == "checklist" else tsheet).clean(m[1], data, _num)
        d = out["header"]["date"]
        try:
            out["header"]["date"] = date.fromisoformat(d).isoformat() if d else ""
        except ValueError:
            raise ValueError("Date invalide")
        return out
    spec = FORM_TYPES.get(ftype)
    if not spec:
        raise ValueError("Type de formulaire inconnu")
    h = data.get("header") or {}
    header = {k: str(h.get(k) or "").strip()[:120] for k in HEADER if k not in ("km", "date")}
    header["km"] = _num(h.get("km"), 0, 1_000_000)
    d = str(h.get("date") or "").strip()
    try:
        header["date"] = date.fromisoformat(d).isoformat() if d else ""
    except ValueError:
        raise ValueError("Date invalide")
    n = spec["pads_per_measure"]
    discs = {}
    for disc in spec["discs"]:
        raw = (data.get("discs") or {}).get(disc["id"]) or []
        rows = []
        for i in range(disc["pads"]):
            r = raw[i] if i < len(raw) and isinstance(raw[i], list) else []
            rows.append([_num(r[j] if j < len(r) else None, 0, 30) for j in range(n)])
        discs[disc["id"]] = rows
    plates = {}
    for p in spec["plates"]:
        raw = (data.get("plates") or {}).get(p["id"]) or []
        plates[p["id"]] = [_num(raw[i] if i < len(raw) else None, 0, 30) for i in range(PLATE_POINTS)]
    return {"header": header, "discs": discs, "plates": plates, "spring_fingers": _num(data.get("spring_fingers"), 0, 30) if spec["spring_fingers"] else None,
            "notes": str(data.get("notes") or "").strip()[:1000]}


def compute(ftype: str, data: dict) -> dict:
    """Épaisseur moyenne par disque, usure par rapport au neuf, usure aux 1 000 km, kilométrage restant avant l'épaisseur minimale, conicité des plateaux.
    Remarque : les formules des fiches Excel d'origine (somme de 6 cellules divisée par 4, patin du bas ignoré, 6,9 mm au lieu de 6 mm) étaient incohérentes ; la moyenne
    porte ici sur toutes les mesures saisies."""
    m = tmodels.spec_of(ftype) if ftype not in FORM_TYPES else None
    if m:
        return (tcheck if m[0] == "checklist" else tsheet).compute(m[1], data)
    spec = FORM_TYPES[ftype]
    km = (data.get("header") or {}).get("km")
    out_d = {}
    for disc in spec["discs"]:
        vals = [v for row in data["discs"][disc["id"]] for v in row if v is not None]
        r = {"count": len(vals), "mean": None, "min": None, "wear": None, "wear_per_1000km": None, "remaining_km": None, "state": None}
        if vals:
            mean = sum(vals) / len(vals)
            r.update(mean=round(mean, 2), min=min(vals), wear=round(EP0 - mean, 2), state="replace" if min(vals) <= MINI else "ok")
            if km and r["wear"] > 0:
                per_km = r["wear"] / km
                r["wear_per_1000km"] = round(per_km * 1000, 3)
                r["remaining_km"] = max(0, round((mean - MINI) / per_km))
        out_d[disc["id"]] = r
    out_p = {}
    for p in spec["plates"]:
        vals = [v for v in data["plates"][p["id"]] if v is not None]
        out_p[p["id"]] = {"count": len(vals), "taper": round(max(vals) - min(vals), 2) if len(vals) >= 2 else None}
    tapers = [p["taper"] for p in out_p.values() if p["taper"] is not None]
    states = [d["state"] for d in out_d.values() if d["state"]]
    return {"discs": out_d, "plates": out_p, "taper_max": max(tapers) if tapers else None, "state": "replace" if "replace" in states else ("ok" if states else None)}


def view(f: dict) -> dict:
    return {**f, "calc": compute(f["type"], f["data"]), "label": label_of(f["type"])}


# ---- Lien avec le Garage : la mesure se rattache à l'embrayage de la voiture (pièce de l'ensemble « Embrayage ») ---------------------------------

def car_key_of(job: dict | None) -> str | None:
    """Voiture du Garage correspondant au véhicule du job : compte analytique Odoo, à défaut égalité EXACTE du nom (même règle que l'espace client)."""
    from . import clients
    for c in rides.race_cars():
        meta = rides.cars_coll().get(c["key"]) or {}
        if job and clients._job_matches(job, c["key"], meta, c["name"]):
            return c["key"]
    return None


def clutch_parts(job: dict | None) -> list[dict]:
    """Pièces montées de l'ensemble « Embrayage » de la voiture du job, avec leurs kilomètres calculés par le Garage."""
    key = car_key_of(job)
    if not key:
        return []
    nodes = rides.tree(key, rides._runs_of(key))
    out: list[dict] = []

    def walk(ns, inside):
        for n in ns:
            if n.get("removed_at"):
                continue
            here = inside or rides._fold(n["name"]) == rides._fold(CLUTCH_SET)
            if here and not n.get("group"):
                out.append({"id": n["id"], "name": n["name"], "km": n.get("km"), "tracks_inspection": "inspection" in rides.types_of(n)})
            walk(n.get("children", []), here)
    walk(nodes, False)
    return out


def measures_by_part(part_ids: set[str]) -> dict[str, list[dict]]:
    """Historique des mesures VALIDÉES liées à des pièces du Garage (courbe d'usure) : [{date, km, state, discs: {id: {label, mean}}}], du plus ancien au plus récent."""
    out: dict[str, list[dict]] = {}
    for f in forms().all():
        if not f.get("validated") or f.get("part_id") not in part_ids or not is_clutch(f["type"]):
            continue
        c = compute(f["type"], f["data"])
        labels = {d["id"]: d["label"] for d in FORM_TYPES[f["type"]]["discs"]}
        out.setdefault(f["part_id"], []).append({"form_id": f["id"], "date": f["data"]["header"].get("date", ""), "km": f["data"]["header"].get("km"), "state": c["state"],
                                                 "discs": {k: {"label": labels[k], "mean": v["mean"]} for k, v in c["discs"].items() if v["mean"] is not None}})
    for v in out.values():
        v.sort(key=lambda m: (m["date"], m["km"] or 0, m["form_id"]))
    return out


def _part_of(f: dict, job: dict | None) -> dict | None:
    return next((p for p in clutch_parts(job) if p["id"] == f.get("part_id")), None)


def _check_part(part_id: str, job: dict | None) -> str:
    if not part_id:
        return ""
    if not any(p["id"] == part_id for p in clutch_parts(job)):
        raise ValueError("Cette pièce n'est pas un embrayage monté sur la voiture du job")
    return part_id


def garage_note(f: dict) -> str:
    c = compute(f["type"], f["data"])
    spec = FORM_TYPES[f["type"]]
    bits = [f"{d['label']} {_n(c['discs'][d['id']]['mean'], 'mm')}" for d in spec["discs"] if c["discs"][d["id"]]["mean"] is not None]
    verdict = {"ok": "OK", "replace": "À remplacer", None: ""}[c["state"]]
    return ("Mesure d'embrayage : " + " ; ".join(bits) + (f" — {verdict}" if verdict else ""))[:300]


# ---- Accès --------------------------------------------------------------------------------------------------------------------------------

def _job(jid: str) -> dict:
    j = timesheets.jobs().get(jid)
    if not j:
        raise LookupError("Job introuvable")
    return j


def list_for_job(jid: str) -> dict:
    job = _job(jid)
    return {"forms": [view(f) for f in sorted(forms().all(), key=lambda f: f["created_at"]) if f["job_id"] == jid], "parts": clutch_parts(job), "car_key": car_key_of(job)}


def create(jid: str, ftype: str, data: dict, part_id: str, user: str, r: dict) -> dict:
    job = _job(jid)
    if job.get("kind") != "atelier":
        raise ValueError("Les formulaires techniques se rattachent à un job d'atelier")
    spec_data = clean(ftype, data)
    h = spec_data["header"]
    p = r.get("person") or {}
    h["mechanic"] = h["mechanic"] or p.get("name", "")
    h["date"] = h["date"] or date.today().isoformat()
    h["chassis"] = _car_name(job)
    if is_clutch(ftype):
        part_id = _check_part(part_id, job) or (lambda ps: ps[0]["id"] if len(ps) == 1 else "")(clutch_parts(job))        # un seul embrayage sur la voiture : lié d'office
        _fill_km(spec_data, part_id, job)
    else:
        part_id = ""                                                 # révisions de boîte et de pont, setup : pas encore reliés au Garage
        m = tmodels.spec_of(ftype)
        if m and m[0] == "sheet" and m[1].get("weighing"):
            _prefill_crew(spec_data, jid)
    fid = "f-" + uuid.uuid4().hex[:10]
    doc = {"id": fid, "job_id": jid, "type": ftype, "part_id": part_id, "data": spec_data, "validated": False, "created_by": user.lower(), "created_at": timesheets.now().isoformat(), "updated_at": timesheets.now().isoformat()}
    forms().put(fid, doc)
    return view(doc)


def _prefill_crew(data: dict, jid: str) -> None:
    """Relevé de setup / setdown : poids du pilote et du co-pilote repris de la demande de setup du même job (la plus récente), s'ils ne sont pas saisis."""
    reqs = sorted((f for f in forms().all() if f["job_id"] == jid and (tmodels.spec_of(f["type"]) or ("", {}))[1].get("kind_of") == "request"), key=lambda f: f["created_at"], reverse=True)
    for f in reqs[:1]:
        for k in ("pilot_kg", "copilot_kg"):
            if "inputs" in data and data["inputs"].get(k) is None and f["data"]["inputs"].get(k) is not None:
                data["inputs"][k] = f["data"]["inputs"][k]


def _car_name(job: dict | None) -> str:
    """Le champ « Voiture » n'est pas éditable : il vient toujours du véhicule lié au job."""
    return ((job or {}).get("vehicle") or {}).get("name", "")[:120]


def _fill_km(data: dict, part_id: str, job: dict | None) -> None:
    """Kilométrage vide : repris de la pièce du Garage (kilomètres calculés depuis son montage)."""
    if part_id and data["header"].get("km") is None:
        km = next((p["km"] for p in clutch_parts(job) if p["id"] == part_id), None)
        if km is not None:
            data["header"]["km"] = round(km)


def _get(fid: str) -> dict:
    f = forms().get(fid)
    if not f:
        raise LookupError("Formulaire introuvable")
    return f


def update(fid: str, data: dict, part_id: str | None, user: str, r: dict) -> dict:
    f = _get(fid)
    if f.get("validated"):
        raise PermissionError("Formulaire validé : le chef d'atelier doit le rouvrir pour le modifier")
    if f["created_by"] != user.lower() and not timesheets.chef_for(r, timesheets.jobs().get(f["job_id"])):
        raise PermissionError("Seul son auteur ou le chef d'atelier peut le modifier")
    f["data"] = clean(f["type"], data)
    job = timesheets.jobs().get(f["job_id"])
    f["data"]["header"]["chassis"] = _car_name(job)
    if is_clutch(f["type"]):
        if part_id is not None:
            f["part_id"] = _check_part(part_id, job)
        _fill_km(f["data"], f.get("part_id", ""), job)
    f["updated_at"] = timesheets.now().isoformat()
    forms().put(fid, f)
    return view(f)


def validate(fid: str, validated: bool, user: str, r: dict) -> dict:
    f = _get(fid)
    if not timesheets.chef_for(r, timesheets.jobs().get(f["job_id"])):
        raise PermissionError("Réservé au chef d'atelier")
    job = timesheets.jobs().get(f["job_id"])
    f.update(validated=bool(validated), validated_by=user.lower() if validated else None, validated_at=timesheets.now().isoformat() if validated else None)
    f["garage"] = _sync_garage(f, job, bool(validated), user)
    forms().put(fid, f)
    return view(f)


def _sync_garage(f: dict, job: dict | None, validated: bool, user: str) -> dict:
    """Validé : un « Contrôle » est enregistré sur la pièce du Garage (le compteur de contrôle repart de la date de la mesure) ; rouvert : ce contrôle est retiré.
    Rien n'est jamais remplacé automatiquement : « À remplacer » reste une proposition, le remplacement se fait par ⟳ Remplacer dans le Garage."""
    if not is_clutch(f["type"]):
        return {}
    mid = (f.get("garage") or {}).get("maint_id")
    if mid:
        try:
            rides.delete_maint(mid)
        except LookupError:
            pass
    if not validated:
        return {}
    part = _part_of(f, job)
    if not part:
        return {"logged": False, "reason": "no_part"}
    if not part["tracks_inspection"]:
        return {"logged": False, "reason": "not_tracked", "part_id": part["id"]}
    d = rides.log_maint(part["id"], rides.MaintIn(type="inspection", date=date.fromisoformat(f["data"]["header"]["date"]), notes=garage_note(f)), user)
    return {"logged": True, "maint_id": d["id"], "part_id": part["id"]}


def delete(fid: str, user: str, r: dict) -> None:
    f = _get(fid)
    chef = timesheets.chef_for(r, timesheets.jobs().get(f["job_id"]))
    if f.get("validated") and not chef:
        raise PermissionError("Formulaire validé")
    if not chef and f["created_by"] != user.lower():
        raise PermissionError("Seul son auteur ou le chef d'atelier peut le supprimer")
    if (f.get("garage") or {}).get("maint_id"):
        _sync_garage({**f, "garage": f["garage"]}, timesheets.jobs().get(f["job_id"]), False, user)
    forms().delete(fid)


# ---- Feuille imprimable --------------------------------------------------------------------------------------------------------------------

def _logo() -> str:
    p = Path(__file__).resolve().parents[2] / "frontend" / "brand" / "LOGO_LIFELIVE_Black.svg"
    try:
        return p.read_text(encoding="utf-8")
    except OSError:
        return "<b>LIFELIVE</b>"


def _d(iso: str) -> str:
    try:
        return date.fromisoformat(iso).strftime("%d/%m/%Y")
    except ValueError:
        return iso or ""


def _n(v, unit: str = "", digits: int = 2) -> str:
    if v is None:
        return "—"
    txt = f"{v:.{digits}f}"
    if "." in txt:
        txt = txt.rstrip("0").rstrip(".")
    return txt + (f" {unit}" if unit else "")


def _shell(title: str, lang: str, content: str, f: dict, valid: str | None = None) -> str:
    """Coque commune des feuilles imprimables : en-tête Lifelive, styles de la charte, pied de page (validation et identifiant)."""
    e = html.escape
    T = (lambda fr, eng: eng if lang == "en" else fr)
    valid = valid or (T("Validé par le chef d'atelier", "Approved by the workshop manager") if f.get("validated") else T("Non validé", "Not approved"))
    return f"""<!doctype html><html lang="{lang}"><head><meta charset="utf-8"><title>{e(title)}</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="preconnect" href="https://fonts.googleapis.com"><link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{{--noir:#000;--graphite:#2B2B2B;--papier:#F4F4F2;--border:#DCDCD8;--muted:#5C6167;--display:'Barlow Condensed','Arial Narrow',sans-serif;--ui:'IBM Plex Sans','Helvetica Neue',sans-serif;--mono:'IBM Plex Mono',ui-monospace,monospace}}
@page{{size:A4;margin:14mm}}*{{box-sizing:border-box}}body{{margin:0;background:var(--papier);color:var(--graphite);font:13px/1.45 var(--ui)}}
.sheet{{max-width:190mm;margin:0 auto;padding:10mm;background:#fff}}.bar{{max-width:190mm;margin:10px auto;text-align:right}}.bar button{{font:inherit;padding:8px 16px;border:0;border-radius:8px;background:var(--graphite);color:#fff;cursor:pointer}}
header{{display:flex;justify-content:space-between;align-items:center;border-bottom:3px solid var(--noir);padding-bottom:8px;margin-bottom:12px}}header svg{{height:34px;width:auto}}
h1{{font:700 26px var(--display);text-transform:uppercase;letter-spacing:.02em;margin:0}}h3{{font:700 17px var(--display);text-transform:uppercase;margin:14px 0 6px}}h3 small{{font:400 11px var(--ui);text-transform:none;color:var(--muted);margin-left:8px}}
.head{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px 14px;margin-bottom:6px}}.head div{{border-bottom:1px solid var(--border);padding-bottom:3px}}.head span{{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}
table{{border-collapse:collapse;width:100%}}th,td{{border:1px solid var(--border);padding:4px 8px;text-align:left}}thead th{{background:var(--graphite);color:#fff;font-weight:500}}td{{font-family:var(--mono)}}td.k{{font-weight:600}}table.m{{max-width:100mm}}
dl{{display:flex;gap:18px;margin:8px 0 0}}dt{{font-size:10px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted)}}dd{{margin:0;font:600 15px var(--mono)}}
.state{{margin:16px 0;padding:10px 14px;border:2px solid var(--graphite);font:700 18px var(--display);text-transform:uppercase}}.notes{{border-left:3px solid var(--graphite);padding-left:8px}}
footer{{margin-top:18px;padding-top:6px;border-top:1px solid var(--border);display:flex;justify-content:space-between;color:var(--muted);font-size:11px}}
@media print{{body{{background:#fff}}.bar{{display:none}}.sheet{{padding:0;max-width:none}}section{{break-inside:avoid}}}}
</style></head><body><div class="bar"><button onclick="window.print()">{T('Imprimer / Enregistrer en PDF', 'Print / Save as PDF')}</button></div>
<div class="sheet"><header><div><h1>{e(title)}</h1></div><div>{_logo()}</div></header>
{content}
<footer><span>Lifelive Motorsport — Logbook · {e(valid)}</span><span>{e(f['id'])}</span></footer></div></body></html>"""


def _print_clutch(f: dict, job: dict, lang: str = "fr") -> str:
    """Feuille A4 aux couleurs de Lifelive (Barlow Condensed / IBM Plex, graphite, noir réservé à l'impression)."""
    e = html.escape
    en = lang == "en"
    spec = FORM_TYPES[f["type"]]
    c = compute(f["type"], f["data"])
    h = f["data"]["header"]
    T = (lambda fr, eng: eng if en else fr)
    state = {"ok": T("OK pour la prochaine course", "OK for the next event"), "replace": T("À REMPLACER", "REPLACE"), None: "—"}[c["state"]]
    head = [(T("Date", "Date"), _d(h.get("date", ""))), (T("Voiture", "Car"), (job.get("vehicle") or {}).get("name", "")), (T("Événement / après", "Event / after"), h.get("after") or (job.get("event") or {}).get("title", "")),
            (T("Mécanicien", "Mechanic"), h.get("mechanic", "")), (T("Boîte de vitesses", "Gearbox"), h.get("gearbox", "")), (T("Mécanisme", "Mechanism"), h.get("mechanism", "")),
            (T("Kilométrage", "Mileage"), _n(h.get("km"), "km", 0))]
    parts = []
    for disc in spec["discs"]:
        rows = f["data"]["discs"][disc["id"]]
        cc = c["discs"][disc["id"]]
        cells = "".join(f"<tr><th>{T('Patin', 'Pad')} {i + 1}</th>" + "".join(f"<td>{_n(v, '', 2)}</td>" for v in row) + "</tr>" for i, row in enumerate(rows))
        names = "".join(f"<th>{e(n)} (mm)</th>" for n in spec["measure_names"]) if spec["pads_per_measure"] > 1 else f"<th>{T('Épaisseur (mm)', 'Thickness (mm)')}</th>"
        parts.append(f"<section><h3>{e(disc['label'])} <small>ep0 {EP0:g} mm · mini {MINI:g} mm</small></h3><table class='m'><thead><tr><th></th>{names}</tr></thead><tbody>{cells}</tbody></table>"
                     f"<dl><div><dt>{T('Épaisseur moyenne', 'Mean thickness')}</dt><dd>{_n(cc['mean'], 'mm')}</dd></div><div><dt>{T('Usure', 'Wear')}</dt><dd>{_n(cc['wear'], 'mm')}</dd></div>"
                     f"<div><dt>{T('Usure / 1 000 km', 'Wear / 1,000 km')}</dt><dd>{_n(cc['wear_per_1000km'], 'mm', 3)}</dd></div><div><dt>{T('Restant estimé', 'Estimated remaining')}</dt><dd>{_n(cc['remaining_km'], 'km', 0)}</dd></div></dl></section>")
    plates = "".join(f"<tr><th>{e(p['label'])}</th>" + "".join(f"<td>{_n(v)}</td>" for v in f["data"]["plates"][p["id"]]) + f"<td class='k'>{_n(c['plates'][p['id']]['taper'], 'mm')}</td></tr>" for p in spec["plates"])
    sf = f"<p><b>Spring fingers :</b> {_n(f['data'].get('spring_fingers'), 'mm')}</p>" if spec["spring_fingers"] else ""
    notes = f"<p class='notes'><b>{T('Remarques', 'Notes')} :</b> {e(f['data'].get('notes') or '')}</p>" if f["data"].get("notes") else ""
    valid = T("Validé par le chef d'atelier", "Approved by the workshop manager") if f.get("validated") else T("Non validé", "Not approved")
    return _shell(spec["label"], lang, f"""<div class="head">{''.join(f'<div><span>{e(k)}</span>{e(v)}</div>' for k, v in head)}</div>
{''.join(parts)}
<h3>{T('Conicité des plateaux', 'Plate taper')} <small>{PLATE_POINTS} {T('mesures par plateau (mm) · conicité = écart maxi', 'readings per plate (mm) · taper = max spread')}</small></h3>
<table><thead><tr><th></th>{''.join(f'<th>{i}</th>' for i in range(1, PLATE_POINTS + 1))}<th>{T('Conicité', 'Taper')}</th></tr></thead><tbody>{plates}</tbody></table>
<p><b>{T('Conicité max', 'Max taper')} :</b> {_n(c['taper_max'], 'mm')}</p>{sf}
<div class="state">{e(state)}</div>{notes}
<p class="notes">{T("Contrôler la planéité des disques ainsi que le libre coulissement des plateaux / mécanisme. Un jeu de disques est prévu pour environ 1 000 km. À contrôler après chaque rallye.", "Check disc flatness and free movement of the plates / mechanism. A set of discs is meant for about 1,000 km. Check after each rally.")}</p>
""", f)


def _print_check(f: dict, job: dict, lang: str) -> str:
    e = html.escape
    T = (lambda fr, eng: eng if lang == "en" else fr)
    spec = tmodels.spec_of(f["type"])[1]
    d = f["data"]
    h = d["header"]
    c = compute(f["type"], d)
    head = [(T("Date", "Date"), _d(h.get("date", ""))), (T("Voiture", "Car"), (job.get("vehicle") or {}).get("name", "")), (T("Événement / après", "Event / after"), h.get("after") or (job.get("event") or {}).get("title", "")),
            (T("Mécanicien", "Mechanic"), h.get("mechanic", ""))]
    labels = {"gearbox_no": T("Boîte n°", "Gearbox no."), "diff_no": T("Diff n°", "Diff no."), "axle_no": T("Pont n°", "Axle no.")}
    head += [(labels[k], h.get(k, "")) for k in spec["header"] if k in labels] + [(T("Kilométrage", "Mileage"), _n(h.get("km"), "km", 0))]
    req = "".join(f"<div><span>{e(T(r['label'], r['label']))}</span>{e(d['requests'].get(r['id'], ''))}</div>" for r in spec["requests"])
    mark = {"ok": "✓", "nok": "✗", "": ""}
    secs = "".join(f"<section><h3>{e(T(s['title'], s['title']))}</h3><table class='ck'><thead><tr><th></th><th>OK</th><th>NOK</th><th>{T('Commentaire', 'Comment')}</th></tr></thead><tbody>"
                   + "".join(f"<tr class='{(d['items'].get(i['id']) or {}).get('status', '')}'><th>{e(i['label'])}</th><td>{mark['ok'] if d['items'][i['id']]['status'] == 'ok' else ''}</td><td>{mark['nok'] if d['items'][i['id']]['status'] == 'nok' else ''}</td><td>{e((d['items'].get(i['id']) or {}).get('comment', ''))}</td></tr>" for i in s["items"])
                   + "</tbody></table></section>" for s in spec["sections"])
    state = (T("%d NOK à traiter", "%d NOK to handle") % c["nok"]) if c["nok"] else (T("Tout est OK", "All OK") if c["state"] == "ok" else T("%d élément(s) non contrôlé(s)", "%d item(s) not checked") % c["open"])
    notes = f"<p class='notes'><b>{T('Commentaires', 'Comments')} :</b> {e(d.get('notes') or '')}</p>" if d.get("notes") else ""
    extra = "<style>table.ck th{font-weight:500;width:46%}table.ck td{text-align:center;font-family:var(--ui)}table.ck td:last-child{text-align:left}table.ck tr.nok{background:#f1f1ef;font-weight:600}.ck thead th:nth-child(2),.ck thead th:nth-child(3){width:42px}</style>"
    body = f"""{extra}<div class="head">{''.join(f'<div><span>{e(k)}</span>{e(v)}</div>' for k, v in head)}{req}</div>{secs}<div class="state">{e(state)}</div>{notes}"""
    return _shell(spec["label"], lang, body, f)


def print_page(f: dict, job: dict, lang: str = "fr") -> str:
    """Feuille A4 aux couleurs de Lifelive (Barlow Condensed / IBM Plex, graphite, noir réservé à l'impression)."""
    if is_clutch(f["type"]):
        return _print_clutch(f, job, lang)
    m = tmodels.spec_of(f["type"])
    if m and m[0] == "sheet":
        return _shell(label_of(f["type"]), lang, tsheet.print_body(f, job, lang, _d, m[1]), f)
    return _print_check(f, job, lang)
