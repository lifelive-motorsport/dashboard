"""Contrôle des marges sur un devis TN11 : lecture du PDF de devis et calcul du prix de vente, du coût Odoo, du coût réel estimé et de la main-d'œuvre.

Le PDF de devis liste la nomenclature d'une configuration (références Lifelive, quantités) ; les lignes vendues portent un « x » dans la colonne « INCLUS ».
Chaque ligne vendue est un article Odoo (ensemble ou pièce) avec son prix de vente propre et, pour les ensembles, une nomenclature (BOM) Odoo.
Rien n'est écrit dans Odoo ; le PDF n'est pas conservé."""
from __future__ import annotations

import re

from . import margins

ROW = re.compile(r"^(?P<lead>\s*)(?:(?P<ref>[A-Za-z0-9][A-Za-z0-9\-]{2,19})\s{2,})?(?P<name>\S.*?)\s{2,}(?P<qty>\d+(?:[.,]\d+)?)(?:\s+(?P<x>[xX]))?\s*$")
SECTION = re.compile(r"^\s{4,}(SUBSET|SOUS[- ]ENSEMBLE)\s+(.+?)\s*$", re.I)
TOTAL = re.compile(r"TOTAL\s+HT\s+([\d\s  .]+[,.]\d{2})", re.I)
MONEY = lambda s: float(re.sub(r"[\s  ]", "", s).replace(".", "").replace(",", ".")) if "," in s else float(re.sub(r"[\s  ]", "", s))  # noqa: E731


def parse_quote(text: str) -> dict:
    """Texte (pdftotext -layout) d'un devis -> {client, lines, total_ht}. `lines` = toutes les lignes de la nomenclature, avec `included` = marquée « x » (vendue)."""
    client, section, option, lines = "", "", False, []
    total = None
    for raw in text.splitlines():
        if not raw.strip():
            continue
        m = re.match(r"\s*Nom du client\s*:\s*(.+)", raw, re.I)
        if m:
            client = client or m.group(1).strip()
            continue
        t = TOTAL.search(raw)
        if t:
            total = MONEY(t.group(1))
            continue
        s = SECTION.match(raw)
        if s:
            section, option = s.group(2).strip().title(), False
            continue
        if re.match(r"^\s{4,}OPTIONS\s*$", raw, re.I):
            option = True
            continue
        if re.search(r"Ref LL|DESIGNATION|TVA\s+\d|TOTAL TTC", raw):
            continue
        r = ROW.match(raw)
        if not r:
            continue
        lines.append({"ref": (r["ref"] or "").strip(), "name": r["name"].strip(), "qty": float(r["qty"].replace(",", ".")), "included": bool(r["x"]),
                      "section": section, "option": option})
    return {"client": client, "lines": lines, "total_ht": total}


# ---- Main-d'œuvre : où elle apparaît ------------------------------------------------------------------------------------
def is_labour(product: dict, patterns: list[str], uom: str = "") -> str | None:
    """Raison pour laquelle un article est de la main-d'œuvre (ou None) : article de type service, ligne de nomenclature en heures, ou nom / catégorie correspondant aux motifs configurés."""
    if product.get("type") == "service":
        return "article de type service"
    if re.search(r"\b(hours?|heures?|h)\b", uom or "", re.I):
        return "quantité en heures"
    hay = f"{product.get('name', '')} {product.get('categ', '')}".lower()
    for p in patterns:
        if p and p.lower() in hay:
            return f"correspond à « {p} »"
    return None


def explode(prod_id: int, qty: float, boms: dict[int, dict], info: dict[int, dict], depth: int = 0, path: tuple = (), uom: str = "") -> list[dict]:
    """Composants (feuilles) d'un article à la quantité `qty`, en descendant dans les nomenclatures des sous-ensembles (profondeur 5 max).
    Retourne [{product, qty, depth, uom}] ; un article sans nomenclature est une feuille. Les opérations (temps de poste de travail) sont retournées avec product=None."""
    bom = boms.get(prod_id)
    if not bom or depth >= 5 or prod_id in path:
        return [{"product": prod_id, "qty": qty, "depth": depth, "uom": uom}]
    out = []
    base = bom["qty"] or 1.0
    for ln in bom["lines"]:
        out.extend(explode(ln["product"], qty * ln["qty"] / base, boms, info, depth + 1, path + (prod_id,), ln.get("uom", "")))
    for op in bom["operations"]:
        out.append({"product": None, "op": op, "qty": qty / base, "depth": depth + 1})
    return out


def outlier_factor() -> float:
    from . import settings
    return float(settings.TN11_OUTLIER_FACTOR)


def line_costs(prod_id: int, qty: float, boms, info, unit_real, unit_info=None) -> dict:
    """Coût d'une ligne vendue : coût réel estimé par la nomenclature, main-d'œuvre repérée et détail composant par composant (`parts`).

    unit_real(prod_id) -> coût réel unitaire d'un composant (achat réel + transport), ou None s'il est inconnu (on retombe alors sur le coût Odoo).
    Un coût réel unitaire plus de `TN11_OUTLIER_FACTOR` fois supérieur au coût Odoo est jugé aberrant (souvent une facture ou une unité mal rapprochée) : on garde le coût Odoo et on le signale."""
    p = info.get(prod_id, {})
    parts = explode(prod_id, qty, boms, info)
    comp_real, labour, flags, detail = 0.0, [], set(), []
    has_bom = prod_id in boms
    pats, fx = margins_labour_patterns(), outlier_factor()
    for part in parts:
        if part["product"] is None:                                          # opération de la nomenclature : temps × coût horaire du poste
            op = part["op"]
            minutes = op["minutes"] * part["qty"]
            cost = minutes / 60 * op["cost_hour"]
            counted = op["cost_hour"] > 0          # opération à coût horaire nul : temps indicatif, non compté (souvent doublon d'une ligne « Heure … » de la nomenclature)
            labour.append({"kind": "operation", "label": f"{op['name']} ({op['workcenter']})", "minutes": round(minutes, 1) if counted else 0.0, "cost": round(cost, 2),
                           "reason": "" if counted else f"coût horaire nul : {round(minutes, 1)} min indicatives, non comptées"})
            detail.append({"ref": "", "name": f"Opération : {op['name']} ({op['workcenter']})", "qty": round(minutes / 60, 3), "uom": "h", "odoo": op["cost_hour"], "unit": op["cost_hour"], "cost": round(cost, 2), "source": "opération", "labour": True, "warn": False})
            comp_real += cost
            continue
        ci = info.get(part["product"], {})
        odoo_unit = ci.get("cost", 0.0)
        real_unit = unit_real(part["product"])
        source, warn = "achats réels", False
        if real_unit is None:
            unit, source = odoo_unit, "coût Odoo"
            flags.add("coût Odoo utilisé pour au moins un composant")
        elif odoo_unit > 0 and real_unit > fx * odoo_unit:
            unit, source, warn = odoo_unit, "aberrant : coût Odoo conservé", True
            flags.add("coût réel aberrant écarté pour au moins un composant")
        else:
            unit = real_unit
        cost = unit * part["qty"]
        reason = is_labour(ci, pats, part.get("uom", ""))
        if reason:
            hours = bool(re.search(r"\b(hours?|heures?|h)\b", part.get("uom", "") or "", re.I))
            labour.append({"kind": "article", "label": f"[{ci.get('ref', '')}] {ci.get('name', '')}", "minutes": round(part["qty"] * 60, 1) if hours else None, "cost": round(cost, 2), "reason": reason})
        inf = (unit_info or {}).get(part["product"]) or {}
        detail.append({"ref": ci.get("ref", ""), "name": ci.get("name", ""), "qty": round(part["qty"], 4), "uom": part.get("uom", ""), "odoo": round(odoo_unit, 4), "real_unit": None if real_unit is None else round(real_unit, 4), "unit": round(unit, 4),
                       "cost": round(cost, 2), "source": source, "labour": bool(reason), "warn": warn, "purchased_qty": inf.get("qty"), "buy_source": inf.get("source"), "buy_flags": inf.get("flags", [])})
        comp_real += cost
    own_labour = is_labour(p, pats)
    return {"has_bom": has_bom, "real": round(comp_real, 2), "labour": labour, "labour_cost": round(sum(l["cost"] for l in labour), 2),
            "labour_minutes": round(sum(l["minutes"] or 0 for l in labour), 1), "self_labour": own_labour, "flags": sorted(flags), "components": len(parts), "parts": detail[:120]}


def margins_labour_patterns() -> list[str]:
    from . import settings
    return [x.strip() for x in settings.TN11_LABOUR_LIKE.split(",") if x.strip()]


def build_report(parsed: dict, products: dict[str, dict], boms: dict[int, dict], info: dict[int, dict], unit_real, freight_rate: float = 0.0, unit_info: dict | None = None) -> dict:
    """Assemble le contrôle : une ligne par article vendu avec prix de vente, coûts, marges, main-d'œuvre ; totaux et points d'attention."""
    rows, unmatched = [], []
    for ln in parsed["lines"]:
        if not ln["included"]:
            continue
        p = products.get(ln["ref"]) if ln["ref"] else None
        if p is None:
            unmatched.append(ln)
            rows.append({**ln, "found": False, "sale": None, "sale_total": None, "odoo": None, "real": None, "margin": {"theoretical": None, "real": None}, "rate": {"theoretical": None, "real": None},
                         "has_bom": False, "parts": [], "labour": [], "labour_cost": 0.0, "labour_minutes": 0.0, "self_labour": None, "flags": ["article introuvable dans Odoo"], "components": 0})
            continue
        c = line_costs(p["id"], ln["qty"], boms, info, unit_real, unit_info)
        sale_total = p["sale"] * ln["qty"]
        odoo_total = p["cost"] * ln["qty"]
        real_total = c["real"] if c["has_bom"] else (unit_real(p["id"]) if unit_real(p["id"]) is not None else p["cost"]) * ln["qty"]
        if not c["has_bom"] and unit_real(p["id"]) is None:
            c["flags"].append("coût Odoo utilisé (pas d'achat récent ni de nomenclature)")
        m_theo, m_real = margins.margin_pct(sale_total, odoo_total), margins.margin_pct(sale_total, real_total)
        rows.append({**ln, "found": True, "id": p["id"], "name_odoo": p["name"], "sale": round(p["sale"], 4), "sale_total": round(sale_total, 2), "odoo": round(odoo_total, 2), "real": round(real_total, 2),
                     "margin": {"theoretical": m_theo, "real": m_real}, "rate": {"theoretical": margins.rate(m_theo), "real": margins.rate(m_real)},
                     "has_bom": c["has_bom"], "parts": c["parts"], "labour": c["labour"], "labour_cost": c["labour_cost"], "labour_minutes": c["labour_minutes"], "self_labour": c["self_labour"], "flags": c["flags"], "components": c["components"]})
    sold = [r for r in rows if r["found"]]
    sale, odoo, real = (sum(r[k] for r in sold) for k in ("sale_total", "odoo", "real"))
    lab = sum(r["real"] if r["self_labour"] else r["labour_cost"] for r in sold)          # une ligne vendue qui est elle-même de la main-d'œuvre compte en entier
    outliers: dict[str, dict] = {}
    for r in sold:
        for part in r["parts"]:
            if part["warn"]:
                o = outliers.setdefault(part["ref"], {"ref": part["ref"], "name": part["name"], "odoo": part["odoo"], "real_unit": part["real_unit"], "purchased_qty": part.get("purchased_qty"), "buy_source": part.get("buy_source"),
                                                      "buy_flags": part.get("buy_flags", []), "lines": []})
                o["lines"].append(r["ref"])
    return {"client": parsed["client"], "pdf_total": parsed["total_ht"], "rows": rows, "unmatched": len(unmatched), "outliers": sorted(outliers.values(), key=lambda o: -(o["real_unit"] or 0) / (o["odoo"] or 1)),
            "totals": {"sale": round(sale, 2), "odoo": round(odoo, 2), "real": round(real, 2), "labour_cost": round(lab, 2), "labour_minutes": round(sum(r["labour_minutes"] for r in sold), 1),
                       "margin": {"theoretical": margins.margin_pct(sale, odoo), "real": margins.margin_pct(sale, real)},
                       "rate": {"theoretical": margins.rate(margins.margin_pct(sale, odoo)), "real": margins.rate(margins.margin_pct(sale, real))},
                       "gap_pdf": round(sale - parsed["total_ht"], 2) if parsed["total_ht"] is not None else None},
            "freight_rate": freight_rate}
