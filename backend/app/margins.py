"""Contrôle des marges XC : pour chaque article à code PIF renseigné, prix de vente, coût renseigné dans Odoo et prix d'achat.

- coût renseigné : `standard_price` de la fiche article ;
- prix d'achat « worst case » : 1 unité chez le fournisseur le plus cher (pour chaque fournisseur, le prix du palier de plus petite quantité) ;
- coût réel estimé : prix unitaire moyen pondéré des factures d'achat comptabilisées (avoirs déduits) des derniers mois, à défaut des commandes d'achat confirmées.
Marge = (prix de vente − coût) / prix de vente. Rien n'est écrit dans Odoo."""
from __future__ import annotations

GREEN, ORANGE = 25.0, 15.0           # vert > 25 %, orange > 15 % et ≤ 25 %, rouge ≤ 15 %


def rate(margin_pct: float | None) -> str | None:
    """Code couleur d'un taux de marge (en %) : « green », « orange » ou « red » ; None si le taux est inconnu."""
    if margin_pct is None:
        return None
    return "green" if margin_pct > GREEN else "orange" if margin_pct > ORANGE else "red"


def margin_pct(sale: float, cost: float | None) -> float | None:
    if cost is None or sale is None or sale <= 0:
        return None
    return round((sale - cost) / sale * 100, 2)


def worst_case(lines: list[dict]) -> dict | None:
    """Prix d'achat le plus défavorable pour 1 unité : pour chaque fournisseur, le prix de son palier de plus petite quantité ; on garde le plus cher."""
    best: dict[str, dict] = {}
    for ln in lines:
        p = ln.get("partner") or ""
        cur = best.get(p)
        if cur is None or ln["min_qty"] < cur["min_qty"]:
            best[p] = ln
    if not best:
        return None
    top = max(best.values(), key=lambda x: x["price"])
    return {"price": round(top["price"], 4), "partner": top.get("partner") or "", "min_qty": top["min_qty"]}


def build_rows(products: list[dict], suppliers: dict[int, list[dict]], real: dict[int, dict]) -> list[dict]:
    """products : {id, ref, name, pif, sale, cost, tmpl} ; suppliers : tmpl -> lignes {partner, min_qty, price} ; real : id article -> {total, qty, source, lines}."""
    rows = []
    for p in products:
        lines = suppliers.get(p["tmpl"], [])
        w = worst_case(lines)
        r = real.get(p["id"])
        est = round(r["total"] / r["qty"], 4) if r and r["qty"] > 0 and r["total"] > 0 else None
        m_theo, m_worst, m_est = margin_pct(p["sale"], p["cost"]), margin_pct(p["sale"], w["price"] if w else None), margin_pct(p["sale"], est)
        rows.append({"id": p["id"], "ref": p["ref"], "name": p["name"], "pif": p["pif"], "sale": round(p["sale"], 4), "cost": round(p["cost"], 4),
                     "worst": w, "tiers": sorted(lines, key=lambda x: (x.get("partner") or "", x["min_qty"]))[:12],
                     "real": ({"unit": est, "qty": round(r["qty"], 2), "source": r["source"], "lines": r.get("lines", 0)} if est is not None else None),
                     "margin": {"theoretical": m_theo, "worst": m_worst, "real": m_est},
                     "rate": {"theoretical": rate(m_theo), "worst": rate(m_worst), "real": rate(m_est)}})
    return sorted(rows, key=lambda x: (x["ref"] or "", x["name"]))


def summary(rows: list[dict]) -> dict:
    out = {"count": len(rows)}
    for k in ("theoretical", "worst", "real"):
        c = {"green": 0, "orange": 0, "red": 0, "unknown": 0}
        for r in rows:
            c[r["rate"][k] or "unknown"] += 1
        out[k] = c
    return out
