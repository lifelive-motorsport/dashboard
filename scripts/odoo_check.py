"""Test de connexion Odoo en LECTURE SEULE (aucune écriture n'est jamais tentée). Usage :
  ODOO_URL=https://xxx.odoo.com ODOO_DB=xxx ODOO_API_KEY=xxx python scripts/odoo_check.py
Ne contient ni n'affiche aucun secret.
"""
import os
import sys
from datetime import date

import httpx

url, db, key = (os.environ.get(k, "") for k in ("ODOO_URL", "ODOO_DB", "ODOO_API_KEY"))
if not (url and db and key):
    sys.exit("Définir ODOO_URL, ODOO_DB et ODOO_API_KEY")
h = httpx.Client(base_url=url.rstrip("/"), headers={"Authorization": f"bearer {key}", "X-Odoo-Database": db}, timeout=30)


def call(model, method, **kw):
    r = h.post(f"/json/2/{model}/{method}", json=kw)
    if r.status_code >= 400:
        return None, f"HTTP {r.status_code}: {r.text[:200]}"
    return r.json(), None


checks = [
    ("Authentification (utilisateur)", "res.users", "search_read", dict(domain=[], fields=["login"], limit=1)),
    ("Comptes P&L", "account.account", "search_count", dict(domain=[("code", "=like", "700%")])),
    ("Écritures validées", "account.move.line", "search_count", dict(domain=[("parent_state", "=", "posted")])),
    ("Groupement formatted_read_group", "account.move.line", "formatted_read_group", dict(
        domain=[("parent_state", "=", "posted"), ("date", ">=", f"{date.today().year}-01-01"),
                ("account_id.code", "=like", "700%")], groupby=["account_id"], aggregates=["balance:sum"])),
    ("Commandes website", "sale.order", "search_count", dict(domain=[("website_id", "!=", False)])),
    ("Sites web", "website", "search_read", dict(domain=[], fields=["name"])),
    ("Lecture des contacts (société, étiquettes)", "res.partner", "search_read",
     dict(domain=[], fields=["commercial_partner_id", "category_id"], limit=1)),
    ("Étiquettes de regroupement clients", "res.partner.category", "search_read",
     dict(domain=[("name", "=ilike", "regroup_client%")], fields=["name"])),
]
ok = True
for label, model, method, kw in checks:
    res, err = call(model, method, **kw)
    ok &= err is None
    detail = err or (f"{len(res)} lignes" if isinstance(res, list) else res)
    print(f"{'OK ' if not err else 'KO '} {label}: {detail}")
    if label == "Sites web" and res:
        print("    sites :", [w["name"] for w in res])
    if label.startswith("Étiquettes de regroupement") and res:
        print("    étiquettes :", sorted(t["name"] for t in res))
# Droits d'écriture : vérification SANS écrire (has_access ne modifie rien).
writable = []
for model in ("res.partner", "account.move", "account.move.line", "account.account", "sale.order", "product.product"):
    res, err = call(model, "has_access", operation="write")
    if res is True:
        writable.append(model)
if writable:
    print("KO  ATTENTION : la clé a un droit d'ÉCRITURE sur :", ", ".join(writable))
else:
    print("OK  Aucun droit d'écriture (lecture seule)")
sys.exit(0 if ok and not writable else 1)
