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
def is_labour(product: dict, patterns: list[str]) -> str | None:
    """Raison pour laquelle un article est de la main-d'œuvre (ou None) : article de type service, ou catégorie / nom correspondant aux motifs configurés (MO, main-d'œuvre, montage…)."""
    if product.get("type") == "service":
        return "article de type service"
    hay = f"{product.get('name', '')} {product.get('categ', '')}".lower()
    for p in patterns:
        if p and p.lower() in hay:
            return f"correspond à « {p} »"
    return None


def explode(prod_id: int, qty: float, boms: dict[int, dict], info: dict[int, dict], depth: int = 0, path: tuple = ()) -> list[dict]:
    """Composants (feuilles) d'un article à la quantité `qty`, en descendant dans les nomenclatures des sous-ensembles (profondeur 5 max).
    Retourne [{product, qty, depth}] ; un article sans nomenclature est une feuille. Les opérations (temps de poste de travail) sont retournées avec product=None."""
    bom = boms.get(prod_id)
    if not bom or depth >= 5 or prod_id in path:
        return [{"product": prod_id, "qty": qty, "depth": depth}]
    out = []
    base = bom["qty"] or 1.0
    for ln in bom["lines"]:
        sub = explode(ln["product"], qty * ln["qty"] / base, boms, info, depth + 1, path + (prod_id,))
        out.extend(sub)
    for op in bom["operations"]:
        out.append({"product": None, "op": op, "qty": qty / base, "depth": depth + 1})
    return out


def line_costs(prod_id: int, qty: float, boms, info, unit_real) -> dict:
    """Coût d'une ligne vendue : coût Odoo (standard_price), coût réel estimé par la nomenclature, et main-d'œuvre repérée.

    unit_real(prod_id) -> coût réel unitaire d'un composant (achat réel + transport), ou None s'il est inconnu (on retombe alors sur le coût Odoo)."""
    p = info.get(prod_id, {})
    parts = explode(prod_id, qty, boms, info)
    comp_real, labour, flags = 0.0, [], set()
    has_bom = prod_id in boms
    for part in parts:
        if part["product"] is None:                                          # opération de la nomenclature : temps × coût horaire du poste
            op = part["op"]
            minutes = op["minutes"] * part["qty"]
            cost = minutes / 60 * op["cost_hour"]
            labour.append({"kind": "operation", "label": f"{op['name']} ({op['workcenter']})", "minutes": round(minutes, 1), "cost": round(cost, 2)})
            comp_real += cost
            continue
        ci = info.get(part["product"], {})
        unit = unit_real(part["product"])
        if unit is None:
            unit = ci.get("cost", 0.0)
            flags.add("coût Odoo utilisé pour au moins un composant")
        cost = unit * part["qty"]
        reason = is_labour(ci, margins_labour_patterns())
        if reason:
            labour.append({"kind": "article", "label": f"[{ci.get('ref', '')}] {ci.get('name', '')}", "minutes": None, "cost": round(cost, 2), "reason": reason})
        comp_real += cost
    own_labour = is_labour(p, margins_labour_patterns())
    return {"has_bom": has_bom, "real": round(comp_real, 2), "labour": labour, "labour_cost": round(sum(l["cost"] for l in labour), 2),
            "labour_minutes": round(sum(l["minutes"] or 0 for l in labour), 1), "self_labour": own_labour, "flags": sorted(flags), "components": len(parts)}


def margins_labour_patterns() -> list[str]:
    from . import settings
    return [x.strip() for x in settings.TN11_LABOUR_LIKE.split(",") if x.strip()]


def build_report(parsed: dict, products: dict[str, dict], boms: dict[int, dict], info: dict[int, dict], unit_real, freight_rate: float = 0.0) -> dict:
    """Assemble le contrôle : une ligne par article vendu avec prix de vente, coûts, marges, main-d'œuvre ; totaux et points d'attention."""
    rows, unmatched = [], []
    for ln in parsed["lines"]:
        if not ln["included"]:
            continue
        p = products.get(ln["ref"]) if ln["ref"] else None
        if p is None:
            unmatched.append(ln)
            rows.append({**ln, "found": False, "sale": None, "sale_total": None, "odoo": None, "real": None, "margin": {"theoretical": None, "real": None}, "rate": {"theoretical": None, "real": None},
                         "has_bom": False, "labour": [], "labour_cost": 0.0, "labour_minutes": 0.0, "self_labour": None, "flags": ["article introuvable dans Odoo"], "components": 0})
            continue
        c = line_costs(p["id"], ln["qty"], boms, info, unit_real)
        sale_total = p["sale"] * ln["qty"]
        odoo_total = p["cost"] * ln["qty"]
        real_total = c["real"] if c["has_bom"] else (unit_real(p["id"]) if unit_real(p["id"]) is not None else p["cost"]) * ln["qty"]
        if not c["has_bom"] and unit_real(p["id"]) is None:
            c["flags"].append("coût Odoo utilisé (pas d'achat récent ni de nomenclature)")
        m_theo, m_real = margins.margin_pct(sale_total, odoo_total), margins.margin_pct(sale_total, real_total)
        rows.append({**ln, "found": True, "id": p["id"], "name_odoo": p["name"], "sale": round(p["sale"], 4), "sale_total": round(sale_total, 2), "odoo": round(odoo_total, 2), "real": round(real_total, 2),
                     "margin": {"theoretical": m_theo, "real": m_real}, "rate": {"theoretical": margins.rate(m_theo), "real": margins.rate(m_real)},
                     "has_bom": c["has_bom"], "labour": c["labour"], "labour_cost": c["labour_cost"], "labour_minutes": c["labour_minutes"], "self_labour": c["self_labour"], "flags": c["flags"], "components": c["components"]})
    sold = [r for r in rows if r["found"]]
    sale, odoo, real = (sum(r[k] for r in sold) for k in ("sale_total", "odoo", "real"))
    lab = sum(r["real"] if r["self_labour"] else r["labour_cost"] for r in sold)          # une ligne vendue qui est elle-même de la main-d'œuvre compte en entier
    return {"client": parsed["client"], "pdf_total": parsed["total_ht"], "rows": rows, "unmatched": len(unmatched),
            "totals": {"sale": round(sale, 2), "odoo": round(odoo, 2), "real": round(real, 2), "labour_cost": round(lab, 2), "labour_minutes": round(sum(r["labour_minutes"] for r in sold), 1),
                       "margin": {"theoretical": margins.margin_pct(sale, odoo), "real": margins.margin_pct(sale, real)},
                       "rate": {"theoretical": margins.rate(margins.margin_pct(sale, odoo)), "real": margins.rate(margins.margin_pct(sale, real))},
                       "gap_pdf": round(sale - parsed["total_ht"], 2) if parsed["total_ht"] is not None else None},
            "freight_rate": freight_rate}
