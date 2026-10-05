"""Contrôle de l'axe analytique « MEETING » (LECTURE SEULE) : plans, événements et couverture analytique.

Usage (Cloud Shell) :
  cd ~/dashboard && pip install --user -q httpx
  ODOO_URL=https://lifelive.odoo.com ODOO_DB=tsc-be-lifelive-main-17241795 \
  ODOO_API_KEY="$(gcloud secrets versions access latest --secret=ODOO_API_KEY)" \
  python3 scripts/odoo_analytique.py [--depuis 2026-01-01]
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def report(p, since: date, until: date) -> None:
    plans = p._call("account.analytic.plan", "search_read", domain=[], fields=["name", "parent_id"])
    print("Plans analytiques :")
    for pl in sorted(plans, key=lambda x: x["name"]):
        n = p._call("account.analytic.account", "search_count", domain=[("plan_id", "=", pl["id"])], context={"active_test": False})
        print(f"  - {pl['name']:<30} {n:>4} compte(s) analytique(s)" + (f"  (sous-plan de {pl['parent_id'][1]})" if pl.get("parent_id") else ""))
    chosen, _ = p._event_plans()
    print(f"\nPlan(s) retenu(s) pour les événements : {', '.join(c['name'] for c in chosen)}")
    ev = p.events(since, until)["events"]
    print(f"{len(ev)} événement(s) avec mouvements du {since} au {until} :")
    for e in ev[:25]:
        print(f"  {e['group']:<5} {e['name'][:40]:<40} CA {e['ca']:>10,.0f}  frais directs {e['direct_costs']:>10,.0f}  autres {e['other_costs']:>9,.0f}  résultat {e['result']:>10,.0f}")
    # Couverture : quelle part du CA et des frais directs est ventilée sur l'axe ?
    dom = [("parent_state", "=", "posted"), ("date", ">=", since.isoformat()), ("date", "<=", until.isoformat())]
    ca = -sum(r["balance:sum"] for r in p._grouped(dom + [("account_id.code", "=like", "700%")], []))
    direct = ["|", "|", ("account_id.code", "=like", "602%"), ("account_id.code", "=like", "603%"), ("account_id.code", "=like", "604%")]
    dc = sum(r["balance:sum"] for r in p._grouped(dom + direct, []))
    ev_ca, ev_dc = sum(e["ca"] for e in ev), sum(e["direct_costs"] for e in ev)
    print(f"\nCouverture analytique (période) :\n  CA (700) : {ca:>12,.0f} €  dont sur l'axe : {ev_ca:>12,.0f} € ({(ev_ca / ca if ca else 0):.0%})")
    print(f"  Achats/frais directs (60x) : {dc:>12,.0f} €  dont sur l'axe : {ev_dc:>12,.0f} € ({(ev_dc / dc if dc else 0):.0%})")
    print("  (le reste n'est pas rattaché à un meeting : il n'apparaît pas dans les pages « Par événement »)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depuis", default=f"{date.today().year}-01-01")
    a = ap.parse_args()
    from app.providers.odoo import OdooProvider
    report(OdooProvider(), date.fromisoformat(a.depuis), date.today())


if __name__ == "__main__":
    main()
