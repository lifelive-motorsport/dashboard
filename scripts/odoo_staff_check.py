"""Contrôle des coûts de personnel (comptes 62…) : LECTURE SEULE, aucune donnée nominative affichée par défaut.

Montre comment les charges de personnel sont comptabilisées : comptes, mois, journaux, tiers et ventilation analytique, pour décider
comment bâtir la section STAFF costs.

Usage (Cloud Shell) :
  cd ~/dashboard && git pull && pip install --user -q httpx
  ODOO_URL=https://lifelive.odoo.com ODOO_DB=tsc-be-lifelive-main-17241795 \
  ODOO_API_KEY="$(gcloud secrets versions access latest --secret=ODOO_API_KEY)" \
  python3 scripts/odoo_staff_check.py [--depuis 2026-01-01] [--partenaires]
"""
import argparse
import os
import sys
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--depuis", default=f"{date.today().year}-01-01")
    ap.add_argument("--partenaires", action="store_true", help="liste aussi les noms des tiers (données nominatives !)")
    a = ap.parse_args()
    since, until = date.fromisoformat(a.depuis), date.today()
    from app.providers.odoo import OdooProvider
    p = OdooProvider()
    dom = [("parent_state", "=", "posted"), ("date", ">=", since.isoformat()), ("date", "<=", until.isoformat()), ("account_id.code", "=like", "62%")]

    def grp(groupby, extra=None):
        return p._call("account.move.line", "formatted_read_group", domain=dom + (extra or []), groupby=groupby, aggregates=["balance:sum", "__count"])

    print(f"=== Charges 62… du {since} au {until} ===\n")
    rows = sorted(grp(["account_id"]), key=lambda r: r["account_id"][1])
    tot = sum(r["balance:sum"] for r in rows)
    print("1) Comptes :")
    for r in rows:
        print(f"  {r['account_id'][1][:58]:<58} {r['balance:sum']:>13,.0f} €  ({r['__count']} lignes)")
    print(f"  {'TOTAL':<58} {tot:>13,.0f} €\n")

    print("2) Par mois (total classe 62) :")
    by_month: dict[str, float] = {}
    for ln in p._call("account.move.line", "search_read", domain=dom, fields=["date", "balance"]):
        by_month[str(ln["date"])[:7]] = by_month.get(str(ln["date"])[:7], 0.0) + float(ln["balance"] or 0.0)
    for m in sorted(by_month):
        print(f"  {m}  {by_month[m]:>13,.0f} €")

    print("\n3) Journaux :")
    for r in sorted(grp(["journal_id"]), key=lambda r: -abs(r["balance:sum"])):
        print(f"  {(r['journal_id'][1] if r.get('journal_id') else '(aucun)'):<40} {r['balance:sum']:>13,.0f} €  ({r['__count']} lignes)")

    print("\n4) Tiers (partenaires) sur ces lignes :")
    pr = grp(["partner_id"])
    none = sum(r["balance:sum"] for r in pr if not r.get("partner_id"))
    named = [r for r in pr if r.get("partner_id")]
    print(f"  {len(named)} tiers distinct(s) ; montant sans tiers : {none:,.0f} € ({(none / tot if tot else 0):.0%})")
    if a.partenaires:
        for r in sorted(named, key=lambda r: -abs(r["balance:sum"]))[:30]:
            print(f"    {r['partner_id'][1][:40]:<40} {r['balance:sum']:>12,.0f} €")

    print("\n5) Ventilation analytique des lignes 62… (par axe) :")
    plans = p._call("account.analytic.plan", "search_read", domain=[], fields=["name", "parent_id"])
    adom = [("date", ">=", since.isoformat()), ("date", "<=", until.isoformat()), ("general_account_id.code", "=like", "62%")]
    total_an = sum(r["amount:sum"] for r in p._call("account.analytic.line", "formatted_read_group", domain=adom, groupby=[], aggregates=["amount:sum"]))
    print(f"  Montant analytique total sur 62… : {-total_an:,.0f} € (comptable : {tot:,.0f} €)")
    for pl in plans:
        if pl.get("parent_id"):
            continue
        col = p._plan_column(pl, plans)
        try:
            rs = p._call("account.analytic.line", "formatted_read_group", domain=adom + [(col, "!=", False)], groupby=[col], aggregates=["amount:sum", "__count"])
        except Exception as e:  # noqa: BLE001
            print(f"  [{pl['name']}] illisible : {e}")
            continue
        if not rs:
            continue
        s = -sum(r["amount:sum"] for r in rs)
        print(f"  Axe « {pl['name']} » : {s:,.0f} € ventilés")
        for r in sorted(rs, key=lambda r: r["amount:sum"])[:8]:
            print(f"      {r[col][1][:45]:<45} {-r['amount:sum']:>12,.0f} €")


if __name__ == "__main__":
    main()
