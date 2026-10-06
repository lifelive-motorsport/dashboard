"""Valorisation du stock XC : calcul pur (testable) à partir d'une liste d'articles.

Article = {ref, name, pif, cost, qty, uom}. Valeur = quantité × coût moyen (standard_price Odoo). Les quantités négatives
(sorties enregistrées sans réception) sont conservées dans la valeur nette et isolées dans les « points d'attention »."""
from __future__ import annotations

import re

TOP = 25
VOLUME_QTY = 500                  # une référence du top 10 en valeur avec au moins autant de pièces : volume à vérifier
UNIT_UOMS = {"units", "unit", "unité(s)", "unités", "unité", "pièce(s)", "pièces", "pcs"}
_SIDE = re.compile(r"\b(left|right|gauche|droit|droite|lh|rh)\b", re.IGNORECASE)
_OPPOSITE = {"left": "right", "right": "left", "gauche": "droite", "droite": "gauche", "droit": "gauche", "lh": "rh", "rh": "lh"}


def _r(x: float) -> int:
    return int(round(x))


def _row(a: dict) -> dict:
    return {"ref": a["ref"], "name": a["name"], "pif": a["pif"], "cost": round(a["cost"], 2), "qty": round(a["qty"], 2), "value": _r(a["value"])}


def _pairs(items: list[dict]) -> list[dict]:
    """Références « gauche / droite » (ou left / right) dont les quantités diffèrent : stock déséquilibré d'une paire."""
    by_key: dict[str, dict[str, dict]] = {}
    for a in items:
        m = _SIDE.search(a["name"])
        if not m or a["qty"] <= 0:
            continue
        side = m.group(1).lower()
        key = (a["name"][:m.start()] + "#" + a["name"][m.end():]).lower()
        by_key.setdefault(key, {})[side] = a
    out = []
    for sides in by_key.values():
        for side, a in sides.items():
            opp = sides.get(_OPPOSITE.get(side, ""))
            if opp and side < _OPPOSITE[side] and abs(a["qty"] - opp["qty"]) >= 1:         # chaque paire une seule fois
                out.append({"a": a["name"], "a_qty": round(a["qty"], 2), "b": opp["name"], "b_qty": round(opp["qty"], 2),
                            "gap": _r(abs(a["qty"] - opp["qty"]) * max(a["cost"], opp["cost"]))})
    return sorted(out, key=lambda p: -p["gap"])[:6]


def build_report(items: list[dict], pif_field: str | None) -> dict:
    for a in items:
        a["value"] = a["qty"] * a["cost"]
    total = sum(a["value"] for a in items)
    positive = sum(a["value"] for a in items if a["qty"] > 0)
    negative = sum(a["value"] for a in items if a["qty"] < 0)
    with_pif = [a for a in items if a["pif"]]
    pif_value = sum(a["value"] for a in with_pif)
    ranked = sorted(with_pif, key=lambda a: -a["value"])
    top, cum = [], 0.0
    for a in ranked[:TOP]:
        cum += a["value"]
        top.append({**_row(a), "cum": cum / pif_value if pif_value else 0.0})
    by_code: dict[str, dict] = {}
    for a in items:
        c = by_code.setdefault(a["pif"] or "", {"code": a["pif"] or "", "refs": 0, "value": 0.0, "positive": 0.0, "negative": 0.0})
        c["refs"] += 1
        c["value"] += a["value"]
        if a["qty"] > 0:
            c["positive"] += a["value"]
        elif a["qty"] < 0:
            c["negative"] += a["value"]
    fmt = lambda c: {**c, "value": _r(c["value"]), "positive": _r(c["positive"]), "negative": _r(c["negative"])}      # noqa: E731
    codes = sorted((c for c in by_code.values() if c["code"]), key=lambda c: -c["value"])
    empty = by_code.get("", {"code": "", "refs": 0, "value": 0.0, "positive": 0.0, "negative": 0.0})
    neg_items = sorted((a for a in items if a["qty"] < 0), key=lambda a: a["value"])
    zero = [a for a in items if a["qty"] > 0 and a["cost"] <= 0]
    decimals = [a for a in items if (a.get("uom") or "").lower() in UNIT_UOMS and abs(a["qty"] - round(a["qty"])) > 1e-6]
    no_pif = sorted(((a for a in items if not a["pif"] and a["value"] > 0)), key=lambda a: -a["value"])
    return {
        "pif_field": pif_field,
        "total": {"value": _r(total), "refs": len(items), "positive": _r(positive), "negative": _r(negative)},
        "pif": {"value": _r(pif_value), "refs": len(with_pif), "share": pif_value / total if total else 0.0},
        "top": top, "top_value": _r(sum(t["value"] for t in top)), "top_share": sum(t["value"] for t in top) / pif_value if pif_value else 0.0,
        "by_pif": [fmt(c) for c in codes], "pif_empty": fmt(empty),
        "attention": {
            "negatives": {"refs": len(neg_items), "value": _r(negative), "top": [_row(a) for a in neg_items[:5]]},
            "zero_cost": {"refs": len(zero), "units": round(sum(a["qty"] for a in zero), 2)},
            "volumes": [_row(a) for a in ranked[:10] if a["qty"] >= VOLUME_QTY],
            "decimals": [_row(a) for a in sorted(decimals, key=lambda a: -a["value"])[:5]],
            "pairs": _pairs(items),
            "no_pif": {"refs": empty["refs"], "value": _r(empty["value"]), "share": empty["value"] / total if total else 0.0,
                       "top": [_row(a) for a in no_pif[:6]]},
        },
    }
