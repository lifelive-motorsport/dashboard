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
    if cost is None or sale is None or sale <= 0 or cost <= 0:          # coût nul ou absent : la marge n'est pas calculable (et non 100 %)
        return None
    return round((sale - cost) / sale * 100, 2)


def build_rows(products: list[dict], real: dict[int, dict]) -> list[dict]:
    """products : {id, ref, name, pif, sale, cost} ; real : id article -> {total, qty, source, lines}.
    `gap` = marge réelle − marge théorique, en points (négatif : l'article rapporte moins que ce que son coût Odoo laisse croire)."""
    rows = []
    for p in products:
        r = real.get(p["id"])
        est = round(r["total"] / r["qty"], 4) if r and r["qty"] > 0 and r["total"] > 0 else None
        m_theo, m_real = margin_pct(p["sale"], p["cost"]), margin_pct(p["sale"], est)
        rows.append({"id": p["id"], "ref": p["ref"], "name": p["name"], "pif": p["pif"], "sale": round(p["sale"], 4), "cost": round(p["cost"], 4),
                     "real": ({"unit": est, "qty": round(r["qty"], 2), "source": r["source"], "lines": r.get("lines", 0)} if est is not None else None),
                     "margin": {"theoretical": m_theo, "real": m_real}, "rate": {"theoretical": rate(m_theo), "real": rate(m_real)},
                     "gap": round(m_real - m_theo, 2) if m_theo is not None and m_real is not None else None})
    return sorted(rows, key=lambda x: (x["ref"] or "", x["name"]))


GAP_BUCKETS = ((-1e9, -20, "plus de 20 pts en dessous"), (-20, -10, "10 à 20 pts en dessous"), (-10, -5, "5 à 10 pts en dessous"), (-5, 5, "écart de moins de 5 pts"), (5, 1e9, "plus de 5 pts au-dessus"))


def summary(rows: list[dict]) -> dict:
    out = {"count": len(rows)}
    for k in ("theoretical", "real"):
        c = {"green": 0, "orange": 0, "red": 0, "unknown": 0}
        for r in rows:
            c[r["rate"][k] or "unknown"] += 1
        out[k] = c
    both = [r for r in rows if r["gap"] is not None]
    out["compared"] = len(both)
    out["avg_theoretical"] = round(sum(r["margin"]["theoretical"] for r in both) / len(both), 2) if both else None
    out["avg_real"] = round(sum(r["margin"]["real"] for r in both) / len(both), 2) if both else None
    out["buckets"] = [{"label": lab, "count": sum(1 for r in both if lo <= r["gap"] < hi)} for lo, hi, lab in GAP_BUCKETS]
    return out
