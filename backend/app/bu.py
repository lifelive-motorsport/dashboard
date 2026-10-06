"""Correspondance compte comptable -> Business Unit, et agrégation du P&L.

Le plan comptable Lifelive encode la BU dans les 3 derniers chiffres des comptes
à 6 chiffres 602 (frais), 603 (sous-traitance), 604 (achats de marchandises)
et 700 (chiffre d'affaires). Les comptes « old - ... » sont ignorés.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# suffixe -> (clé BU, libellé BU, ligne d'activité, groupe)
_SUFFIXES: dict[str, tuple[str, str, str, str]] = {
    "010": ("XC", "XC", "Manufacturer", "XC"),
    "011": ("XC", "XC", "Workshop", "XC"),
    "012": ("XC", "XC", "Race team", "XC"),
    "013": ("XC", "XC", "Goldspeed EAX", "XC"),
    "014": ("XC", "XC", "Events", "XC"),
    "015": ("XC", "XC", "Webshop", "XC"),
    "016": ("XC", "XC", "Others", "XC"),
    "019": ("XC", "XC", "Sales & Marketing", "XC"),
    "020": ("MODERN_RALLY", "Modern Rally", "Modern Rally", "CARS"),
    "030": ("HISTORIC_RALLY", "Historic Rally", "Historic Rally", "CARS"),
    "040": ("HISTORIC_RACING", "Historic Racing", "Historic Racing", "CARS"),
    "050": ("CARS_OTHERS", "CARS Others", "CARS Others", "CARS"),
    "059": ("CARS_OTHERS", "CARS Others", "CARS Sales & Marketing", "CARS"),
}

UNASSIGNED = ("UNASSIGNED", "Non affecté", "Non affecté", "OTHER")

BU_ORDER = ["XC", "MODERN_RALLY", "HISTORIC_RALLY", "HISTORIC_RACING", "CARS_OTHERS", "UNASSIGNED"]
BU_LABELS = {"XC": "XC", "MODERN_RALLY": "Modern Rally", "HISTORIC_RALLY": "Historic Rally",
             "HISTORIC_RACING": "Historic Racing", "CARS_OTHERS": "CARS Others", "UNASSIGNED": "Non affecté"}
BU_GROUP = {"XC": "XC", "MODERN_RALLY": "CARS", "HISTORIC_RALLY": "CARS",
            "HISTORIC_RACING": "CARS", "CARS_OTHERS": "CARS", "UNASSIGNED": "OTHER"}

_CODE = re.compile(r"^(602|603|604|700)(\d{3})$")
_OLD = re.compile(r"^\s*old\b", re.IGNORECASE)  # préfixe « old - », pas « Goldspeed »


@dataclass(frozen=True)
class Classified:
    kind: str  # "revenue" | "direct_cost"
    bu: str
    line: str


def is_old(account_name: str) -> bool:
    return bool(_OLD.match(account_name or ""))


def classify(code: str, name: str = "") -> Classified | None:
    """Renvoie la nature et la BU d'un compte, ou None s'il n'entre pas dans la marge brute."""
    if is_old(name):
        return None
    m = _CODE.match(code.strip())
    if not m:
        return None
    prefix, suffix = m.groups()
    kind = "revenue" if prefix == "700" else "direct_cost"
    info = _SUFFIXES.get(suffix)
    bu, _, line, _ = info if info else UNASSIGNED
    return Classified(kind, bu, line)


def aggregate(balances: dict[str, float], names: dict[str, str] | None = None) -> dict:
    """balances: code -> solde comptable (débit - crédit) sur la période.

    CA = -solde des 700 ; frais directs = +solde des 602/603/604 ;
    marge brute = CA - frais directs. Personnel (62) et véhicules (615) exclus.
    """
    names = names or {}
    bus = {k: {"key": k, "label": BU_LABELS[k], "group": BU_GROUP[k], "ca": 0.0, "direct_costs": 0.0,
               "costs": {"604": 0.0, "603": 0.0, "602": 0.0}, "lines": {}} for k in BU_ORDER}
    for code, bal in balances.items():
        c = classify(code, names.get(code, ""))
        if not c:
            continue
        b = bus[c.bu]
        line = b["lines"].setdefault(c.line, {"line": c.line, "ca": 0.0, "direct_costs": 0.0})
        if c.kind == "revenue":
            b["ca"] += -bal
            line["ca"] += -bal
        else:
            b["direct_costs"] += bal
            line["direct_costs"] += bal
            b["costs"][code.strip()[:3]] = b["costs"].get(code.strip()[:3], 0.0) + bal      # 604 achats de marchandises, 603 sous-traitance, 602 frais
    out_bus = []
    for k in BU_ORDER:
        b = bus[k]
        b["margin"] = b["ca"] - b["direct_costs"]
        b["lines"] = [dict(l, margin=l["ca"] - l["direct_costs"]) for l in b["lines"].values()]
        out_bus.append(b)

    groups = {}
    for g in ("XC", "CARS", "OTHER"):
        members = [b for b in out_bus if b["group"] == g]
        ca = sum(b["ca"] for b in members)
        dc = sum(b["direct_costs"] for b in members)
        groups[g] = {"key": g, "ca": ca, "direct_costs": dc, "margin": ca - dc,
                     "costs": {k: sum(b["costs"].get(k, 0.0) for b in members) for k in ("604", "603", "602")}}
    ca = sum(b["ca"] for b in out_bus)
    dc = sum(b["direct_costs"] for b in out_bus)
    return {"bus": out_bus, "groups": list(groups.values()),
            "total": {"ca": ca, "direct_costs": dc, "margin": ca - dc, "costs": {k: sum(b["costs"].get(k, 0.0) for b in out_bus) for k in ("604", "603", "602")},
                      "margin_pct": (ca - dc) / ca if ca else 0.0}}
