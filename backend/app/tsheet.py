"""Formulaires techniques de type « feuille de relevés » (Pointages › Jobs) : demande de setup (rallye et circuit), relevé de setup, relevé de setdown, d'après les fiches Excel
« SET-CAR-EVENT-DRIVER » (onglets Demande, Setup, Setdown). Chaque feuille est faite de groupes de lignes ; une ligne a 1, 2 ou 4 valeurs (une, AV / AR, G / D, ou les quatre roues).
Les valeurs sont du texte libre (des mesures, mais aussi « 3 clics », « cale 0,5 »…) ; seule la pesée est numérique : pesée totale, centrage AV, centrage en croix, pesée sans essence,
sans équipage et à vide (0,75 kg par litre d'essence) sont refaits à chaque lecture. Utilisé par `tforms.py`."""
from __future__ import annotations

import html
import re
import unicodedata

COLS = {"axle": [("av", "AV"), ("ar", "AR")], "wheel4": [("av_g", "AV G"), ("av_d", "AV D"), ("ar_g", "AR G"), ("ar_d", "AR D")], "side": [("g", "G"), ("d", "D")], "one": [("v", "")]}
FUEL_KG_PER_L = 0.75
WEIGHT_ROW = "wheel_weights"


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")[:40]


def _grp(title: str, layout: str, rows: list[str]) -> dict:
    return {"id": _slug(title), "title": title, "layout": layout, "rows": [{"id": _slug(r) if r != "Poids par roue (avec équipage, équipement, essence, lot de bord)" else WEIGHT_ROW, "label": r} for r in rows]}


_GEOM_RELEVE = ["Hauteur de caisse", "Hauteur sous coupelle", "Hauteur entre coupelles sur chandelle", "Garde au sol", "Hauteur d'aile (sans équipage)", "Carrossage", "Cale de carrossage",
                "Parallélisme / roue (- : OUT / + : IN)", "Cale de parallélisme / longueur de bras de pince", "Longueur de bras de carrossage (bout de rotule à bord de contre-écrou)", "Longueur de bras de chasse"]
_WEIGHT = "Poids par roue (avec équipage, équipement, essence, lot de bord)"
_GEOM_REQ = ["Hauteur de caisse", "Hauteur sous coupelle (théorique)", "Carrossage (degrés, centièmes) / roue", "Cale de carrossage (théorique)", "Parallélisme total (mm) (- : OUT / + : IN)",
             "Parallélisme / roue (mm) (- : OUT / + : IN)", "Cale de parallélisme (théorique)"]
_REQ_SUSP = ["Ressort | Compensateur", "Amortisseur", "Clics (Bv / Hv / D / Butée)", "Spécificité (butée mousse, RCV, Cale)", "Barre anti-roulis (diamètre | position)"]
_BRAKES = ["Maître-cylindre", "Répartition", "Plaquettes"]

TYPES = {
    "setup_request": {"label": "Demande de setup — rallye", "kind_of": "request", "header_after": "Rallye", "crew": ["pilot", "copilot"],
                      "groups": [_grp("Suspension", "axle", ["Définition de berceau", "Position sur berceau"] + _REQ_SUSP), _grp("Géométrie", "axle", _GEOM_REQ),
                                 _grp("Équipement", "axle", ["Pneus | Pression", "Position roue de secours | Qté essence"]), _grp("Équipement (suite)", "one", ["Ski (Av | Central | Ar)", "Trousse à outils (définition | Poids)", "Lot de bord (définition | Poids)"]),
                                 _grp("Transmission", "one", ["Étagement boîte de vitesses / Diff av (rampe | faces | précharge)", "Diff ar (rampe | faces | précharge)"]), _grp("Freins", "axle", _BRAKES)]},
    "setup_request_circuit": {"label": "Demande de setup — circuit", "kind_of": "request", "header_after": "Événement", "crew": ["pilot"],
                              "groups": [_grp("Suspension", "axle", _REQ_SUSP), _grp("Géométrie", "axle", _GEOM_REQ), _grp("Équipement", "axle", ["Pneus | Pression", "Position roue de secours | Qté essence"]),
                                         _grp("Équipement (suite)", "one", ["Ski (Av | Central | Ar)"]), _grp("Transmission", "one", ["Étagement boîte de vitesses", "Diff ar (rampe | faces | précharge)"]), _grp("Freins", "axle", _BRAKES)]},
    "setup_reading": {"label": "Relevé de setup", "kind_of": "reading", "header_after": "Après (événement)", "crew": [], "weighing": True, "min_label": "Poids mini (kg)",
                      "groups": [_grp("Géométrie", "wheel4", _GEOM_RELEVE), _grp("Pesée", "wheel4", [_WEIGHT]),
                                 _grp("Mesure de caisse", "side", ["Empattement (cible)"]), _grp("Mesure de caisse (suite)", "axle", ["Porte-à-faux"]),
                                 _grp("Dimensions", "one", ["Longueur", "Largeur", "Mesure d'aileron"]), _grp("Dimensions (suite)", "wheel4", ["Recouvrement (< 0 mm)", "Hauteur de bavettes", "Pince-ficelle sur chandelles"])]},
    "setdown_reading": {"label": "Relevé de setdown", "kind_of": "reading", "header_after": "Après (événement)", "crew": [], "weighing": True, "drained": True,
                        "groups": [_grp("Géométrie", "wheel4", [r for r in _GEOM_RELEVE if r != "Hauteur entre coupelles sur chandelle"]), _grp("Pesée", "wheel4", [_WEIGHT]), _grp("Mesure de caisse", "side", ["Empattement"])]},
}
INPUT_LABELS = {"pilot_name": "Pilote", "pilot_kg": "Poids pilote équipé (kg)", "copilot_name": "Co-pilote", "copilot_kg": "Poids co-pilote équipé (kg)", "fuel_l": "Quantité d'essence (L)",
                "min_weight": "Poids minimum (kg)", "drained_l": "Essence vidangée avant refuel pour setdown (L)"}


def input_keys(spec: dict) -> list[str]:
    ks = []
    for who in spec["crew"]:
        ks += [f"{who}_name", f"{who}_kg"]
    if spec.get("weighing"):
        ks += ["pilot_kg", "copilot_kg", "fuel_l"] + (["min_weight"] if spec.get("min_label") else [])
    if spec.get("drained"):
        ks.append("drained_l")
    return list(dict.fromkeys(ks))


def types() -> list[dict]:
    out = []
    for k, v in TYPES.items():
        out.append({"id": k, "kind": "sheet", "label": v["label"], "sheet": v["kind_of"], "header_after": v["header_after"], "weighing": bool(v.get("weighing")),
                    "inputs": [{"id": i, "label": INPUT_LABELS[i], "text": i.endswith("_name")} for i in input_keys(v)],
                    "groups": [{**g, "cols": [{"id": c, "label": l} for c, l in COLS[g["layout"]]]} for g in v["groups"]]})
    return out


def clean(ftype: str, data: dict, num) -> dict:
    spec = TYPES[ftype]
    h = data.get("header") or {}
    header = {"after": str(h.get("after") or "").strip()[:120], "mechanic": str(h.get("mechanic") or "").strip()[:120], "date": str(h.get("date") or "").strip()}
    inp = data.get("inputs") or {}
    inputs = {}
    for k in input_keys(spec):
        inputs[k] = str(inp.get(k) or "").strip()[:80] if k.endswith("_name") else num(inp.get(k), 0, 5000)
    raw = data.get("rows") or {}
    rows = {}
    for g in spec["groups"]:
        for r in g["rows"]:
            cells = (raw.get(r["id"]) or {})
            rows[r["id"]] = {c: str(cells.get(c) or "").strip()[:60] for c, _ in COLS[g["layout"]]}
    return {"header": header, "inputs": inputs, "rows": rows, "notes": str(data.get("notes") or "").strip()[:1500]}


def _f(v) -> float | None:
    try:
        return float(str(v).replace(",", ".").strip())
    except (TypeError, ValueError):
        return None


def compute(ftype: str, data: dict) -> dict:
    spec = TYPES[ftype]
    filled = sum(1 for r in data["rows"].values() for v in r.values() if v)
    total_cells = sum(len(r) for r in data["rows"].values())
    out = {"filled": filled, "cells": total_cells, "state": None, "weights": None}
    if not spec.get("weighing"):
        out["state"] = "ok" if filled else None
        return out
    w = data["rows"].get(WEIGHT_ROW) or {}
    vals = {k: _f(w.get(k)) for k in ("av_g", "av_d", "ar_g", "ar_d")}
    inp = data["inputs"]
    if all(v is not None for v in vals.values()) and sum(vals.values()) > 0:
        tot = sum(vals.values())
        fuel_kg = (inp.get("fuel_l") or 0) * FUEL_KG_PER_L
        crew = (inp.get("pilot_kg") or 0) + (inp.get("copilot_kg") or 0)
        no_fuel = tot - fuel_kg
        wt = {"total": round(tot, 1), "front_pct": round(100 * (vals["av_g"] + vals["av_d"]) / tot, 2), "cross_pct": round(100 * (vals["av_g"] + vals["ar_d"]) / tot, 2),
              "no_fuel": round(no_fuel, 1), "no_crew": round(tot - crew, 1), "empty": round(tot - crew - fuel_kg, 1)}
        mn = inp.get("min_weight")
        wt["min_ok"] = None if not mn else no_fuel >= mn
        out["weights"] = wt
        out["state"] = "nok" if wt["min_ok"] is False else "ok"
    else:
        out["state"] = None
    return out


def _n(v, unit="") -> str:
    if v is None:
        return "—"
    return f"{v:g}".replace(".", ",") + (f" {unit}" if unit else "")


def print_body(f: dict, job: dict, lang: str, d_fmt) -> str:
    e = html.escape
    T = (lambda fr, eng: eng if lang == "en" else fr)
    spec = TYPES[f["type"]]
    d, c = f["data"], compute(f["type"], f["data"])
    h = d["header"]
    head = [(T("Date", "Date"), d_fmt(h.get("date", ""))), (T("Voiture", "Car"), (job.get("vehicle") or {}).get("name", "")), (T(spec["header_after"], spec["header_after"]), h.get("after") or (job.get("event") or {}).get("title", "")),
            (T("Mécanicien", "Mechanic"), h.get("mechanic", ""))]
    for k, v in d["inputs"].items():
        head.append((T(INPUT_LABELS[k], INPUT_LABELS[k]), v if isinstance(v, str) else _n(v)))
    groups = []
    for g in spec["groups"]:
        cols = COLS[g["layout"]]
        th = "<th></th>" + "".join(f"<th>{e(l)}</th>" for _, l in cols if l) + ("" if any(l for _, l in cols) else "<th></th>")
        body = "".join(f"<tr><th>{e(r['label'])}</th>" + "".join(f"<td>{e(d['rows'][r['id']].get(cid, ''))}</td>" for cid, _ in cols) + "</tr>" for r in g["rows"])
        groups.append(f"<section><h3>{e(g['title'])}</h3><table class='sh'><thead><tr>{th}</tr></thead><tbody>{body}</tbody></table></section>")
    wt = c["weights"]
    wtxt = ""
    if wt:
        items = [(T("Pesée totale", "Total weight"), _n(wt["total"], "kg")), (T("Centrage AV", "Front weight"), _n(wt["front_pct"], "%")), (T("Centrage en croix", "Cross weight"), _n(wt["cross_pct"], "%")),
                 (T("Sans essence", "Without fuel"), _n(wt["no_fuel"], "kg")), (T("Sans équipage", "Without crew"), _n(wt["no_crew"], "kg")), (T("À vide", "Empty"), _n(wt["empty"], "kg"))]
        wtxt = "<dl class='wt'>" + "".join(f"<div><dt>{e(k)}</dt><dd>{e(v)}</dd></div>" for k, v in items) + "</dl>"
        if wt["min_ok"] is False:
            wtxt += f"<div class='state'>{e(T('Poids sous le minimum', 'Below minimum weight'))}</div>"
    notes = f"<p class='notes'><b>{T('Remarques', 'Notes')} :</b> {e(d.get('notes') or '')}</p>" if d.get("notes") else ""
    extra = "<style>table.sh{table-layout:fixed}table.sh th:first-child{width:38%;font-weight:500}table.sh td{font-family:var(--ui)}dl.wt{display:flex;flex-wrap:wrap;gap:12px 22px;margin:10px 0}</style>"
    return f"""{extra}<div class="head">{''.join(f'<div><span>{e(k)}</span>{e(v)}</div>' for k, v in head)}</div>{''.join(groups)}{wtxt}{notes}"""
