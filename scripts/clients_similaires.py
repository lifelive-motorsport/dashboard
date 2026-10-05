"""Propose des regroupements de clients (noms proches) à valider, LECTURE SEULE.

Usage (Cloud Shell) :
  cd ~/dashboard && pip install --user -q httpx
  ODOO_URL=https://lifelive.odoo.com ODOO_DB=<base> ODOO_API_KEY="$(gcloud secrets versions access latest --secret=ODOO_API_KEY)" \
    python3 scripts/clients_similaires.py [--depuis 2025-01-01] [--min-ca 1000]

Rien n'est modifié dans Odoo : pour regrouper, posez vous-même l'étiquette « regroup_client=Nom du groupe » sur les contacts.
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
from app.similar_clients import find_candidates  # noqa: E402


def build_items(provider, since: date, min_ca: float) -> list[dict]:
    rows = provider._grouped([("parent_state", "=", "posted"), ("date", ">=", since.isoformat()),
                              ("account_id.code", "=like", "700%"), ("partner_id", "!=", False)], ["partner_id"])
    ca, names = {}, {}
    for r in rows:
        pid, name = r["partner_id"]
        ca[pid], names[pid] = -r["balance:sum"], name
    try:
        groups = provider._client_groups(set(ca))               # regroupements déjà posés + fusion des contacts d'une société
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
    ap.add_argument("--min-ca", type=float, default=1000.0, help="ignore les clients sous ce CA (défaut 1000 €)")
    a = ap.parse_args()
    from app.providers.odoo import OdooProvider
    items = build_items(OdooProvider(), date.fromisoformat(a.depuis), a.min_ca)
    fams = find_candidates(items)
    print(f"{len(items)} clients/groupes analysés depuis le {a.depuis} — {len(fams)} regroupement(s) possible(s)\n")
    for n, f in enumerate(fams, 1):
        print(f"[{n}] {f['total']:>12,.0f} €  — {'; '.join(f['why'])}")
        print(f"    Étiquette proposée :  regroup_client={f['suggested']}")
        for m in f["members"]:
            print(f"      · {m['label']:<55} {m['ca']:>12,.0f} €")
        print()
    if not fams:
        print("Aucun rapprochement évident.")


if __name__ == "__main__":
    main()
