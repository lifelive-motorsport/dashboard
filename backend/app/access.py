"""Pages du dashboard et ce que chacune exige du serveur : routes de l'API et jeux de données du tableau de bord.

Une catégorie d'utilisateurs (Settings › Utilisateurs) est un nom + une liste de pages cochées. Le serveur n'ouvre à ses membres que les routes et les données de ces pages :
tout le reste est refusé (403) ou neutralisé dans /api/dashboard. La page « Settings › Utilisateurs » n'est jamais attribuable (Super User uniquement)."""
from __future__ import annotations

ADJ = ("/api/adjustments", "/api/stockvar")
NM = ADJ + ("/api/staff", "/api/expenses", "/api/vehicles", "/api/pnl/unassigned")      # marge nette : personnel, frais généraux, véhicules
FIN = {"fin", "events_xc", "events_cars", "veh", "web"}                                   # P&L, clients, fournisseurs, événements, véhicules, webshops
ALWAYS = ("/api/session", "/api/dashboard")

# page -> (routes d'API, jeux de données du tableau de bord)
PAGES: dict[str, tuple[tuple[str, ...], set[str]]] = {
    "overview/ca": ((), FIN), "overview/mb": (ADJ, FIN), "overview/nm": (NM, FIN), "overview/xcvscars": (ADJ, FIN),
    "overview/clients": ((), FIN), "overview/suppliers": ((), FIN), "overview/adjustments": (ADJ, FIN),
    "xc/general": (NM, FIN), "xc/lignes": (ADJ, FIN), "xc/webshop_xc": ((), {"web"}), "xc/webshop_gs": ((), {"web"}), "xc/events": ((), {"events_xc"}),
    "xc/inventory": (("/api/stock",), set()), "xc/margins": (("/api/xc/margins",), set()), "xc/tn11": (("/api/xc/tn11",), set()),
    "cars/general": (NM, FIN), "cars/bu": (NM, FIN), "cars/events": ((), {"events_cars"}), "cars/vehicles": ((), {"veh"}),
    "staff/source": (("/api/staff",), set()), "staff/people": (("/api/staff",), set()), "staff/general": (("/api/staff", "/api/pnl/unassigned"), set()),
    "staff/xc": (("/api/staff",), set()), "staff/cars": (("/api/staff",), set()), "staff/shared": (("/api/staff",), set()), "staff/management": (("/api/staff",), set()),
    "expenses/source": (("/api/expenses",), set()), "expenses/general": (("/api/expenses",), set()), "expenses/rules": (("/api/expenses", "/api/staff"), set()),
    "vehicles/source": (("/api/expenses", "/api/vehicles"), set()), "vehicles/general": (("/api/expenses", "/api/vehicles"), set()),
    "vehicles/byvehicle": (("/api/expenses", "/api/vehicles"), set()), "vehicles/fuel": (("/api/expenses", "/api/vehicles", "/api/fuel"), set()),
    "vehicles/usage": (("/api/expenses", "/api/vehicles", "/api/fuel"), set()),
    "marketing/site": ((), {"mkt_site"}), "marketing/expenses": (("/api/expenses",), {"mkt"}),
    "others/tags": (("/api/tags",), set()),
}
XC_PAGES = ["xc/webshop_xc", "xc/webshop_gs", "xc/events", "xc/inventory", "xc/margins", "xc/tn11"]       # catégorie « XC » proposée par défaut


def allowed_prefixes(pages: set[str]) -> tuple[str, ...]:
    out = list(ALWAYS)
    for p in pages:
        out.extend(PAGES.get(p, ((), set()))[0])
    return tuple(out)


def path_ok(path: str, pages: set[str]) -> bool:
    return any(path == pre or path.startswith(pre + "/") for pre in allowed_prefixes(pages))


def scopes(pages: set[str]) -> set[str]:
    s: set[str] = set()
    for p in pages:
        s |= PAGES.get(p, ((), set()))[1]
    return s


def scope_view(d: dict, pages: set[str], neutral_pnl: dict) -> dict:
    """Tableau de bord limité aux données des pages autorisées ; le reste est neutralisé côté serveur."""
    sc = scopes(pages)
    full = "fin" in sc
    na = {"unavailable": "Réservé"}
    ev = d.get("events")
    if isinstance(ev, dict) and "events" in ev and not full:
        keep_cars, keep_xc = "events_cars" in sc, "events_xc" in sc
        ev = {**ev, "events": [e for e in ev["events"] if (e.get("group") == "CARS" and keep_cars) or (e.get("group") != "CARS" and keep_xc)]}
    if not (full or sc & {"events_xc", "events_cars"}):
        ev = na
    ana = d.get("analytics")
    if isinstance(ana, dict):
        ana = {k: v for k, v in ana.items() if (k in ("xc", "gs") and ("web" in sc or full)) or (k == "site" and ("mkt_site" in sc or "mkt" in sc))}
    bs = d.get("balance_sheet") if full else {"cash": 0, "receivables": 0, "payables": 0, "year": d["period"]["to"][:4]}
    if not full:
        bs["year"] = int(bs["year"])
    return {"source": d["source"], "period": d["period"], "generated_at": d["generated_at"],
            "pnl": d["pnl"] if full else neutral_pnl, "pnl_prev": d.get("pnl_prev") if full else None, "balance_sheet": bs,
            "top_clients": d.get("top_clients") if full else na, "top_suppliers": d.get("top_suppliers") if full else na,
            "events": ev, "vehicles": d.get("vehicles") if (full or "veh" in sc) else na,
            "webshops": d.get("webshops") if (full or "web" in sc) else na,
            "marketing": d.get("marketing") if ("mkt" in sc or "mkt_site" in sc) else na, "analytics": ana}
