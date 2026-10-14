"""Formulaires techniques de type « liste de contrôle » (Pointages › Jobs) : révisions de boîte de vitesses (M3, Z4 GT3, avec différentiel) et de pont arrière, d'après les fiches
Excel « REV-BV_… » (rapport d'ouverture : chaque élément est OK ou NOK avec un commentaire, plus une demande de réglage). Chaque type fixe ses sections et ses éléments ;
l'identifiant d'un élément vient de son libellé (stable si la liste évolue). Le calcul (OK / NOK / non contrôlés) est refait à chaque lecture. Utilisé par `tforms.py`."""
from __future__ import annotations

import re
import unicodedata

STATUS = ("ok", "nok", "")


def _slug(s: str) -> str:
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def _sec(title: str, items: list[str]) -> dict:
    return {"id": _slug(title), "title": title, "items": [{"id": _slug(i), "label": i} for i in items]}


_GEARS = ["Rapport de 1ère", "Roue de 1ère", "Rapport de 2ème", "Roue de 2ème", "Rapport de 3ème", "Roue de 3ème", "Rapport de 4ème", "Roue de 4ème", "Rapport de 5ème", "Roue de 5ème"]
_GEARS6 = _GEARS + ["Rapport de 6ème", "Roue de 6ème"]
_STAGING = [{"id": "staging_short", "label": "Étagement court"}, {"id": "staging_long", "label": "Étagement long"}]
_DIFF_REQ = [{"id": "ramp", "label": "Rampe de diff"}, {"id": "faces", "label": "Nombre de faces"}, {"id": "preload", "label": "Précharge établie"}]
_DIFF = ["Roulements de différentiel", "Coquilles", "Planétaires", "Axe de planétaires", "Roulements", "Clips", "Satellites", "Axes de satellites", "Disques de friction", "Disques lisses", "Ressorts", "Crosspin"]

TYPES = {
    "gearbox_m3": {"label": "Révision de boîte de vitesses — M3", "header": ["after", "gearbox_no", "km"], "requests": [],
                   "sections": [_sec("Boîte de vitesses", _GEARS6 + ["Rapport de MAR", "Baladeur MAR", "Baladeur 1/2", "Baladeur 3/4", "Baladeur 5/6", "Arbre d'embrayage", "Arbre primaire", "Frein arbre primaire",
                                                                    "Clips arbre primaire", "Arbre secondaire", "Frein arbre secondaire", "Clips arbre secondaire"]),
                                _sec("Commande", ["Joint", "Ressorts", "Billes", "Axe de commande A", "Axe de commande B", "Axe de commande C", "Plain bearing", "Goupilles de commande"])]},
    "gearbox_z4": {"label": "Révision de boîte de vitesses — Z4 GT3", "header": ["after", "gearbox_no", "km"], "requests": _STAGING,
                   "sections": [_sec("Boîte de vitesses", _GEARS6 + ["Arbre d'embrayage", "Arbre primaire", "Écrou arbre primaire", "Arbre secondaire", "Écrou arbre secondaire", "Baladeur MA", "Baladeur 1ère", "Baladeur 2ème",
                                                                    "Baladeur 3ème", "Baladeur 4ème", "Baladeur 5ème", "Baladeur 6ème", "Barillet", "Axe de fourchettes", "Fourchettes"])]},
    "gearbox_diff": {"label": "Révision de boîte de vitesses avec différentiel", "header": ["after", "gearbox_no", "diff_no", "km"], "requests": _STAGING + _DIFF_REQ,
                     "sections": [_sec("Boîte de vitesses", _GEARS + ["Rapport de MAR", "Arbre d'embrayage", "Arbre primaire", "Clips arbre primaire", "Arbre secondaire", "Clips arbre secondaire", "Couple final",
                                                                      "Couronne de diff", "Baladeur MA", "Baladeur 1ère", "Baladeur 2ème", "Baladeur 3ème", "Baladeur 4ème", "Baladeur 5ème", "Barillet", "Fourchettes"]),
                                  _sec("Différentiel", _DIFF)]},
    "rear_axle": {"label": "Révision de pont arrière", "header": ["after", "axle_no", "diff_no", "km"], "requests": _DIFF_REQ,
                  "sections": [_sec("Pont arrière", ["Couple conique", "Roulements d'arbre", "Pompe à huile", "Roulement de pompe à huile"]),
                               _sec("Différentiel", ["Roulements de différentiel", "Coquilles", "Planétaires", "Axe de planétaires", "Cale d'épaisseur", "Écrou", "Clips", "Satellites", "Axes de satellites",
                                                      "Disques de friction", "Disques lisses", "Ressorts", "Crosspin"])]},
}
HEADER_LABELS = {"after": "Après (événement)", "gearbox_no": "Boîte n°", "diff_no": "Diff n°", "axle_no": "Pont n°", "km": "Kilométrage (km)"}


def clean(spec: dict, data: dict, num) -> dict:
    h = data.get("header") or {}
    header = {k: str(h.get(k) or "").strip()[:120] for k in spec["header"] if k != "km"}
    header["km"] = num(h.get("km"), 0, 1_000_000)
    header["date"] = str(h.get("date") or "").strip()
    header["mechanic"] = str(h.get("mechanic") or "").strip()[:120]
    req = data.get("requests") or {}
    requests = {r["id"]: str(req.get(r["id"]) or "").strip()[:120] for r in spec["requests"]}
    raw = data.get("items") or {}
    items = {}
    for sec in spec["sections"]:
        for it in sec["items"]:
            v = raw.get(it["id"]) or {}
            st = v.get("status") or ""
            if st not in STATUS:
                raise ValueError("Statut invalide : " + str(st))
            items[it["id"]] = {"status": st, "comment": str(v.get("comment") or "").strip()[:200]}
    return {"header": header, "requests": requests, "items": items, "notes": str(data.get("notes") or "").strip()[:1500]}


def compute(spec: dict, data: dict) -> dict:
    secs, tot = [], {"ok": 0, "nok": 0, "open": 0}
    for sec in spec["sections"]:
        c = {"ok": 0, "nok": 0, "open": 0}
        for it in sec["items"]:
            st = (data["items"].get(it["id"]) or {}).get("status", "")
            c[st or "open"] += 1
        secs.append({"id": sec["id"], "title": sec["title"], **c})
        for k in tot:
            tot[k] += c[k]
    state = "nok" if tot["nok"] else ("ok" if tot["open"] == 0 and tot["ok"] else None)
    return {"sections": secs, **tot, "total": tot["ok"] + tot["nok"] + tot["open"], "state": state}
