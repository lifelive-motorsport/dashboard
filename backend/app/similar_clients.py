"""Repère des clients dont les noms se ressemblent et qui pourraient être regroupés (étiquette regroup_client=…).

Aucune décision automatique : l'outil PROPOSE, c'est vous qui posez (ou non) l'étiquette dans Odoo.
"""
from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from .names import LEGAL, normalize_name

# Mots trop généraux pour rapprocher deux clients (« Racing », « Event », « Motors »…)
GENERIC = {"sport", "sports", "motorsport", "motorsports", "racing", "team", "teams", "management", "event", "events", "rental",
           "motors", "motor", "group", "groupe", "holding", "international", "company", "garage", "auto", "autos", "cars", "car",
           "service", "services", "the", "de", "du", "des", "la", "le", "les", "van", "von", "der", "den", "and", "et", "prive",
           "privee", "privé", "club", "ecurie", "equipe", "engineering", "trading", "invest", "investments", "investment", "distribution"}
_LEGAL_KEYS = set(LEGAL) | {"co", "ltd", "inc", "llc", "gmbh"}


def tokens(name: str) -> list[str]:
    """Mots significatifs : sans accents, sans forme juridique ni mot général, en minuscules."""
    s = unicodedata.normalize("NFKD", name.replace("İ", "i")).encode("ascii", "ignore").decode().lower()
    s = re.sub(r"\([^)]*\)", " ", s)                     # (privé), (TOSFED)…
    out = []
    for w in re.findall(r"[a-z0-9]+(?:\.[a-z0-9]+)*", s):
        w = w.replace(".", "")
        if w and w not in _LEGAL_KEYS and w not in GENERIC and len(w) > 1:
            out.append(w)
    return out


def find_candidates(items: list[dict], min_ratio: float = 0.88) -> list[dict]:
    """items : [{"key": identifiant du client/groupe, "label": nom, "ca": CA}]. Renvoie des familles de ≥ 2 clients."""
    n = len(items)
    toks = [tokens(i["label"]) for i in items]
    parent = list(range(n))
    why: dict[int, set[str]] = {}

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int, reason: str) -> None:
        if items[a]["key"] == items[b]["key"]:
            return                                          # déjà regroupés ensemble
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
        why.setdefault(find(a), set()).add(reason)

    by_first: dict[str, list[int]] = {}
    for i, t in enumerate(toks):
        if t and len(t[0]) >= 4:
            by_first.setdefault(t[0], []).append(i)
    for word, idx in by_first.items():
        for k in idx[1:]:
            union(idx[0], k, f"même premier mot « {word} »")
    keys = [" ".join(t) for t in toks]
    for i in range(n):
        for j in range(i + 1, n):
            if keys[i] and keys[j] and keys[i][:2] == keys[j][:2] and SequenceMatcher(None, keys[i], keys[j]).ratio() >= min_ratio:
                union(i, j, "noms très proches")

    fam: dict[int, list[int]] = {}
    for i in range(n):
        fam.setdefault(find(i), []).append(i)
    out = []
    for root, members in fam.items():
        if len({items[m]["key"] for m in members}) < 2:
            continue
        members.sort(key=lambda m: -items[m]["ca"])
        reasons = set()
        for m in members:
            reasons |= why.get(find(m), set())
        out.append({"suggested": normalize_name(items[members[0]]["label"]), "total": sum(items[m]["ca"] for m in members),
                    "why": sorted(reasons), "members": [{"label": normalize_name(items[m]["label"]), "ca": items[m]["ca"]} for m in members]})
    return sorted(out, key=lambda f: -f["total"])
