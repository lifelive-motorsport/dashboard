"""Propose des regroupements de clients OU de fournisseurs (noms proches) à valider, LECTURE SEULE.

Usage (Cloud Shell) :
  cd ~/dashboard && pip install --user -q httpx
  ODOO_URL=https://lifelive.odoo.com ODOO_DB=<base> ODOO_API_KEY="$(gcloud secrets versions access latest --secret=ODOO_API_KEY)" \
    python3 scripts/clients_similaires.py [--fournisseurs] [--depuis 2025-01-01] [--min-ca 1000]

Rien n'est modifié dans Odoo : pour regrouper, posez vous-même l'étiquette « regroup_client=Nom du groupe » (clients) ou
« regroup_fournisseur=Nom du groupe » (fournisseurs) sur les contacts.
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.similar_clients import find_candidates  # noqa: E402


def build_items(provider, since: date, min_ca: float, suppliers: bool = False) -> list[dict]:
    if suppliers:   # achats : lignes de factures fournisseurs sur comptes de charges (classe 6), débit = achat
        domain = [("parent_state", "=", "posted"), ("move_id.move_type", "in", ["in_invoice", "in_refund"]), ("display_type", "=", "product"),
                  ("date", ">=", since.isoformat()), ("account_id.code", "=like", "6%"), ("partner_id", "!=", False)]
        sign, prefix = 1, "regroup_fournisseur"
    else:           # ventes : comptes de CA 700
        domain = [("parent_state", "=", "posted"), ("date", ">=", since.isoformat()),
                  ("account_id.code", "=like", "700%"), ("partner_id", "!=", False)]
        sign, prefix = -1, "regroup_client"
    ca, names = {}, {}
    for r in provider._grouped(domain, ["partner_id"]):
        pid, name = r["partner_id"]
        ca[pid], names[pid] = sign * r["balance:sum"], name
    try:
        groups = provider._client_groups(set(ca), prefix)       # regroupements déjà posés + fusion des contacts d'une société
    except Exception as e:
        print("Avertissement : lecture des contacts impossible, regroupements existants ignorés :", type(e).__name__)
        groups = {}
    agg: dict[str, dict] = {}
    for pid, v in ca.items():
        key, label = groups.get(pid, (f"p:{pid}", names[pid]))
        item = agg.setdefault(key, {"key": key, "label": label, "ca": 0.0})
        item["ca"] += v
    return [i for i in agg.values() if i["ca"] >= min_ca]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depuis", default=f"{date.today().year - 1}-01-01")
    ap.add_argument("--min-ca", type=float, default=1000.0, help="ignore les tiers sous ce montant (défaut 1000 €)")
    ap.add_argument("--fournisseurs", action="store_true", help="analyser les fournisseurs (achats) au lieu des clients (CA)")
    a = ap.parse_args()
    from app.providers.odoo import OdooProvider
    items = build_items(OdooProvider(), date.fromisoformat(a.depuis), a.min_ca, a.fournisseurs)
    fams = find_candidates(items)
    print(f"{len(items)} {'fournisseurs' if a.fournisseurs else 'clients'}/groupes analysés depuis le {a.depuis} — {len(fams)} regroupement(s) possible(s)\n")
    for n, f in enumerate(fams, 1):
        print(f"[{n}] {f['total']:>12,.0f} €  — {'; '.join(f['why'])}")
        print(f"    Étiquette proposée :  {'regroup_fournisseur' if a.fournisseurs else 'regroup_client'}={f['suggested']}")
        for m in f["members"]:
            print(f"      · {m['label']:<55} {m['ca']:>12,.0f} €")
        print()
    if not fams:
        print("Aucun rapprochement évident.")


if __name__ == "__main__":
    main()
