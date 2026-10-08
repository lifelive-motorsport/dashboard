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


TOL = 0.10          # écart toléré entre le montant facturé et (quantité × prix de la commande) avant de juger la facture « globale »


def allocate_orders(orders: dict[int, dict]) -> dict[int, dict]:
    """Coût d'achat réel par article d'après les commandes d'achat et leurs factures.

    orders : id commande -> {"lines": {id ligne: {product, qty, received, price}}, "bills": {id ligne: {amount, qty}}} (montants en euros ; avoirs en négatif).
    - facture cohérente (montant ≈ quantité facturée × prix de la commande) : on prend le montant réellement facturé ;
    - facture « globale » (ex. 1 pièce facturée pour 30 reçues, ou facture qui couvre aussi d'autres lignes de la commande) : quantité = quantité reçue, la ligne
      reçoit au plus son prix de commande × quantité, et l'excédent est réparti sur les autres lignes reçues non facturées de la même commande, au prorata de leur valeur.
    Retourne article -> {amount, qty, flags} avec flags ⊂ {« globale »}."""
    out: dict[int, dict] = {}

    def add(pid, amount, qty, flag=None):
        d = out.setdefault(pid, {"amount": 0.0, "qty": 0.0, "flags": set(), "lines": 0})
        d["amount"] += amount
        d["qty"] += qty
        d["lines"] += 1
        if flag:
            d["flags"].add(flag)

    for o in orders.values():
        lines, bills = o["lines"], o["bills"]
        excess = 0.0
        for lid, b in bills.items():
            ln = lines.get(lid)
            if ln is None or not ln.get("product"):
                continue
            price, nb = ln["price"], b["qty"]
            if nb > 0 and price > 0 and abs(b["amount"] - price * nb) <= TOL * price * nb:
                add(ln["product"], b["amount"], nb)                                  # facture cohérente
                continue
            basis = ln["received"] if ln["received"] > 0 else ln["qty"]
            value = price * basis
            if basis <= 0 or value <= 0:
                if nb > 0:
                    add(ln["product"], b["amount"], nb)
                continue
            if b["amount"] <= value * (1 + TOL):
                add(ln["product"], b["amount"], basis, "globale")                       # facturé moins cher que commandé, ou à peine plus
            else:
                add(ln["product"], value, basis, "globale")
                excess += b["amount"] - value
        if excess > 0.005:
            pending = {lid: ln for lid, ln in lines.items() if lid not in bills and ln.get("product") and ln["received"] > 0 and ln["price"] > 0}
            weight = sum(ln["price"] * ln["received"] for ln in pending.values())
            for lid, ln in pending.items():
                add(ln["product"], excess * ln["price"] * ln["received"] / weight, ln["received"], "globale")
    return out


def freight_rate(pool: float, products: list[dict], real: dict[int, dict]) -> float:
    """Transport : `pool` (euros, comptes de frais de transport) réparti au prorata du prix de vente des unités achetées. Retourne la part du prix de vente (ex. 0,031 = 3,1 %)."""
    base = sum(p["sale"] * real[p["id"]]["qty"] for p in products if p["id"] in real and real[p["id"]]["qty"] > 0 and p["sale"] > 0)
    return pool / base if base > 0 and pool > 0 else 0.0


def build_rows(products: list[dict], real: dict[int, dict], freight: float = 0.0) -> list[dict]:
    """products : {id, ref, name, pif, sale, cost} ; real : id article -> {total, qty, source, lines}.
    `gap` = marge réelle − marge théorique, en points (négatif : l'article rapporte moins que ce que son coût Odoo laisse croire)."""
    rows = []
    for p in products:
        r = real.get(p["id"])
        buy = r["total"] / r["qty"] if r and r["qty"] > 0 and r["total"] > 0 else None
        fr = round(freight * p["sale"], 4) if buy is not None else 0.0                      # transport : part du prix de vente
        est = round(buy + fr, 4) if buy is not None else None
        m_theo, m_real = margin_pct(p["sale"], p["cost"]), margin_pct(p["sale"], est)
        rows.append({"id": p["id"], "ref": p["ref"], "name": p["name"], "pif": p["pif"], "sale": round(p["sale"], 4), "cost": round(p["cost"], 4),
                     "real": ({"unit": est, "buy": round(buy, 4), "freight": fr, "qty": round(r["qty"], 2), "source": r["source"], "lines": r.get("lines", 0), "flags": sorted(r.get("flags", []))} if est is not None else None),
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
