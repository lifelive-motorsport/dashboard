"""Vérifie (lecture seule) qu'aucun document Firestore `dashboard/*` ne contient l'ancien identifiant de BU « groupe ».
Avec --apply, remplace « groupe » par « lifelive » (valeurs de texte exactes et clés) ; relançable sans effet de bord.
Usage (Cloud Shell, projet lifelive-dashboard-app) :  python backend/scripts/check_groupe_bu.py [--apply]
"""
import sys
from google.cloud import firestore

OLD, NEW = "groupe", "lifelive"


def walk(o, path=""):
    """Rend (chemin, 'clé'|'valeur') pour chaque occurrence exacte de OLD."""
    if isinstance(o, dict):
        for k, v in o.items():
            if k == OLD:
                yield f"{path}/{k}", "clé"
            yield from walk(v, f"{path}/{k}")
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from walk(v, f"{path}[{i}]")
    elif o == OLD:
        yield path, "valeur"


def fix(o):
    if isinstance(o, dict):
        return {(NEW if k == OLD else k): fix(v) for k, v in o.items()}
    if isinstance(o, list):
        return [fix(v) for v in o]
    return NEW if o == OLD else o


def main():
    apply = "--apply" in sys.argv
    db, found = firestore.Client(), 0
    for doc in db.collection("dashboard").stream():
        hits = list(walk(doc.to_dict()))
        for p, kind in hits:
            print(f"dashboard/{doc.id}{p}  ({kind})")
        found += len(hits)
        if hits and apply:
            doc.reference.set(fix(doc.to_dict()))
            print(f"  -> dashboard/{doc.id} migré")
    print(f"{found} occurrence(s) trouvée(s)." + ("" if apply or not found else " Relancez avec --apply pour migrer."))


if __name__ == "__main__":
    main()
