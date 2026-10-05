"""Normalisation de l'affichage des noms de clients (sans jamais modifier Odoo).

Règles :
- les mots de 4 lettres et plus ÉCRITS EN MAJUSCULES passent en « Majuscule initiale » (CONCEPT -> Concept) ;
- les sigles de 1 à 3 lettres restent en majuscules (TN, EMO) ; les mots de liaison passent en minuscules (de, van, du) ;
- les formes juridiques sont uniformisées (sl/SL -> SL, GMBH -> GmbH, s.r.o -> s.r.o.) ;
- ce qui est entre parenthèses est conservé tel quel ((TOSFED), (privé)) ;
- un mot déjà en casse mixte (LifeLive, Sport) n'est jamais modifié ; les chiffres sont conservés.
"""
from __future__ import annotations

import re

LEGAL = {  # clé = sans point, en minuscules
    "sl": "SL", "slu": "SLU", "sa": "SA", "sarl": "SARL", "srl": "SRL", "sas": "SAS", "sasu": "SASU", "bv": "BV", "bvba": "BVBA",
    "nv": "NV", "ag": "AG", "kg": "KG", "llc": "LLC", "ltd": "Ltd", "inc": "Inc", "gmbh": "GmbH", "sro": "s.r.o.",
    "asbl": "ASBL", "vzw": "VZW", "sprl": "SPRL", "scrl": "SCRL", "cvba": "CVBA", "eurl": "EURL", "snc": "SNC",
}
LINKING = {"de", "du", "des", "la", "le", "les", "van", "von", "der", "den", "of", "the", "and", "et", "di", "da"}
_SPLIT = re.compile(r"([/\-–])")


def _title(word: str) -> str:
    w = word.replace("İ", "i").lower()   # évite le « i » + point combinant de Python sur le İ turc
    return re.sub(r"(^|['’.])([^\W\d_])", lambda m: m.group(1) + m.group(2).upper(), w)   # O'Brien, C.Dumolin


def _part(s: str, first: bool, inside: bool, force: bool = False) -> str:
    letters = "".join(re.findall(r"[^\W\d_]", s))
    if not letters or inside:
        return s
    legal = LEGAL.get(s.replace(".", "").lower())
    if legal and (s.isupper() or s.islower() or s == legal):
        return legal                        # forme juridique : écriture uniforme
    if not s.isupper() or len(letters) < 2 or any(c.isdigit() for c in s):
        return s                            # casse mixte, minuscule, lettre seule ou mot avec chiffres : inchangé
    if force:                               # prénom composé tout en majuscules (JEAN-LUC)
        return _title(s)
    if len(letters) <= 3:                   # sigle (TN, EMO) ou mot de liaison (DU -> du)
        return s.lower() if (s.lower() in LINKING and not first) else s
    return _title(s)


def normalize_name(name: str) -> str:
    out, depth, first = [], 0, True
    for tok in re.split(r"(\s+)", name or ""):
        if not tok or tok.isspace():
            out.append(tok)
            continue
        lead = re.match(r"^[\(\[«\"']*", tok).group(0)
        trail = re.search(r"[\)\]»\",;:]*$", tok).group(0)
        core = tok[len(lead): len(tok) - len(trail)] if trail else tok[len(lead):]
        inside = depth > 0 or "(" in lead
        force = "-" in core and core.isupper() and len(re.findall(r"[^\W\d_]", core)) >= 5
        parts = [p if _SPLIT.fullmatch(p) or p == "" else _part(p, first, inside, force) for p in _SPLIT.split(core)]
        out.append(lead + "".join(parts) + trail)
        depth += tok.count("(") - tok.count(")")
        if re.search(r"[^\W\d_]", core):
            first = False
    return "".join(out)
