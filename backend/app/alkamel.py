"""Roulage Al Kamel : lecture des PDF du chronométreur (classements, analyse des secteurs) et création des roulages.

Les PDF sont lus avec PyMuPDF (mots positionnés) : chaque page est découpée en lignes, les colonnes d'un classement sont repérées par
la position de leur titre, l'analyse des secteurs (deux voitures côte à côte) est lue colonne par colonne. Les fonctions `parse_*`
travaillent sur du texte / des lignes déjà extraits, pour être testables sans PDF."""
from __future__ import annotations

import re
import statistics
import uuid
from datetime import date, datetime
from typing import Any

from . import rides

TIME = re.compile(r"^(?:\d+:)?\d{1,2}:\d{2}\.\d{3}$|^\d{1,2}\.\d{3}$")
LAPTIME = re.compile(r"^\d{1,2}:\d{2}\.\d{3}$")
SESSION_KINDS = {"RACE": "race", "QUALIFYING": "qualifying", "PRIVATE PRACTICE": "practice", "FREE PRACTICE": "practice", "PRACTICE": "practice", "WARM UP": "practice", "WARM-UP": "practice"}
MAX_FILES, MAX_BYTES = 40, 12 * 1024 * 1024


def secs(t: str | None) -> float | None:
    """« 1:02:03.456 » / « 2:12.829 » / « 29.551 » -> secondes."""
    if not t or not TIME.match(t):
        return None
    parts = t.split(":")
    return round(sum(float(p) * 60 ** i for i, p in enumerate(reversed(parts))), 3)


def fmt(s: float | None) -> str:
    if s is None:
        return ""
    m, r = divmod(s, 60)
    return f"{int(m)}:{r:06.3f}" if m else f"{r:.3f}"


# ---- Extraction des PDF --------------------------------------------------------------------------------------------------------------------

def _pages(data: bytes) -> list[list[tuple[float, float, str]]]:
    import pymupdf  # PyMuPDF
    doc = pymupdf.open(stream=data, filetype="pdf")
    return [[(w[0], w[1], w[4]) for w in p.get_text("words")] for p in doc]


def _rows(words: list[tuple[float, float, str]], tol: float = 3.0) -> list[list[tuple[float, str]]]:
    """Mots -> lignes (y croissant), chaque ligne triée par x."""
    out: list[tuple[float, list[tuple[float, str]]]] = []
    for x, y, w in sorted(words, key=lambda t: (t[1], t[0])):
        if out and abs(out[-1][0] - y) <= tol:
            out[-1][1].append((x, w))
        else:
            out.append((y, [(x, w)]))
    return [sorted(r) for _, r in out]


def _text(row: list[tuple[float, str]]) -> str:
    return " ".join(w for _, w in row)


def _num(v: str) -> float | None:
    try:
        return float(v.replace(",", "."))
    except (ValueError, AttributeError):
        return None


# ---- Titres, conditions ---------------------------------------------------------------------------------------------------------------------

def parse_head(rows: list[list[tuple[float, str]]], name: str = "") -> dict:
    """Série, épreuve et session d'après les premières lignes du PDF ; la session se déduit au besoin du nom du fichier."""
    lines = [_text(r) for r in rows[:6]]
    session = kind = ""
    event = series = ""
    for i, ln in enumerate(lines):
        up = re.sub(r"\s*\(\d+'?\)\s*$", "", ln.strip()).upper()
        if up in SESSION_KINDS:
            session, kind = ln.strip(), SESSION_KINDS[up]
            event = lines[i - 1].strip() if i >= 1 else ""
            series = lines[i - 2].strip() if i >= 2 else ""
            break
    if not kind:
        up = name.upper()
        for k, v in SESSION_KINDS.items():
            if k in up:
                session, kind = k.title(), v
                break
    return {"series": series, "event": event, "session": session or kind, "kind": kind}


def parse_conditions(text: str) -> dict:
    out: dict[str, Any] = {}
    m = re.search(r"Track Temp:\s*([\d.,]+)", text)
    if m:
        out["track_c"] = _num(m.group(1))
    m = re.search(r"Air Temp:\s*([\d.,]+)", text)
    if m:
        out["air_c"] = _num(m.group(1))
    m = re.search(r"Track Status:\s*([A-Za-z]+)", text)
    if m:
        out["status"] = m.group(1).upper()
    pen = [ln.strip() for ln in text.splitlines() if re.match(r"\s*CAR \d+ -", ln)]
    if pen:
        out["notes"] = pen
    m = re.search(r"(\d{2})/(\d{2})/(\d{4})\s+Page", text)
    if m:
        out["date"] = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return out


# ---- Classements ----------------------------------------------------------------------------------------------------------------------------

def _drivers(txt: str) -> list[str]:
    return [d.strip() for d in re.split(r"\s*/\s*", txt) if d.strip()]


def parse_classification(rows: list[list[tuple[float, str]]], kind: str) -> list[dict]:
    """Lignes d'un classement (course, essais, qualifications) : colonnes repérées par l'abscisse des titres « Drivers », « Car » et « Class »."""
    head = next((r for r in rows if any(w == "Drivers" for _, w in r) and any(w == "Car" for _, w in r)), None)
    if not head:
        return []
    hx = {w: x for x, w in head if w in ("Drivers", "Car", "Class")}
    dx, cx, kx = hx["Drivers"] - 4, hx["Car"] - 4, hx["Class"] - 4
    has_total_time = any(w == "Total" for _, w in head) and kind == "race"
    out = []
    for r in rows:
        toks = [w for _, w in r]
        if len(toks) < 4 or not toks[0].isdigit():
            continue
        left = [(x, w) for x, w in r if x < dx]                      # « pos nr » (course : Pos Nr) ou « nr » seul (non classé)
        if not left or any(not w.isdigit() for _, w in left) or len(left) > 2:
            continue
        pos, no = (int(left[0][1]), int(left[1][1])) if len(left) == 2 else (None, int(left[0][1]))
        drivers = " ".join(w for x, w in r if dx <= x < cx)
        car = " ".join(w for x, w in r if cx <= x < kx)
        rest = [w for x, w in r if x >= kx]
        while rest and re.fullmatch(r"(19|20)\d\d", rest[0]):          # l'année de la voiture (« … RS 1600 1972 ») déborde parfois dans la colonne suivante : elle reste dans le nom
            car += " " + rest.pop(0)
        if not drivers or not car or not rest:
            continue
        e: dict[str, Any] = {"pos": pos, "no": no, "drivers": _drivers(drivers), "car": car, "class": rest[0], "classified": pos is not None}
        t = rest[1:]
        if kind == "race" or has_total_time:
            if len(t) >= 2:
                e["laps"] = int(t[0]) if t[0].isdigit() else None
                e["total_time"] = t[1] if TIME.match(t[1]) else ""
            if len(t) >= 3 and LAPTIME.match(t[-2]) and t[-3].isdigit():   # … n° du meilleur tour, temps, vitesse
                e["best_lap_no"], e["best"], e["best_kph"] = int(t[-3]), t[-2], _num(t[-1])
                mid = t[2:-3]
                if mid and mid[0] not in ("-",) and not mid[0].startswith("+") and len(mid) > 1 and mid[1].lower().startswith("lap"):
                    e["gap"], mid = f"{mid[0]} {mid[1]}", mid[2:]
                elif mid:
                    e["gap"], mid = mid[0], mid[1:]
                if mid:
                    e["kph"] = _num(mid[0])
        elif kind == "qualifying":
            times = [x for x in t if LAPTIME.match(x)]
            # pilote 1, pilote 2, tours, moyenne, écart
            i = next((k for k, x in enumerate(t) if x.isdigit()), None)
            if i is not None:
                dt = t[:i]
                e["driver_times"] = [x for x in dt if LAPTIME.match(x)]
                e["laps"] = int(t[i])
                if i + 1 < len(t) and LAPTIME.match(t[i + 1]):
                    e["average"] = t[i + 1]
                if i + 2 < len(t):
                    e["gap"] = t[i + 2]
            if times:
                e["best"] = min(times, key=lambda x: secs(x) or 1e9)
        else:   # essais : meilleur temps, n° du tour, total des tours, écarts, vitesse
            if t and LAPTIME.match(t[0]):
                e["best"] = t[0]
                nums = [x for x in t[1:] if x.isdigit()]
                if nums:
                    e["best_lap_no"] = int(nums[0])
                if len(nums) > 1:
                    e["laps"] = int(nums[1])
                if len(t) > 3 and _num(t[-1]) is not None and "." in t[-1]:
                    e["kph"] = _num(t[-1])
        out.append(e)
    return out


# ---- Analyse des secteurs ------------------------------------------------------------------------------------------------------------------

def parse_analysis(pages: list[list[list[tuple[float, str]]]]) -> dict[int, dict]:
    """Analyse des secteurs : deux voitures côte à côte sur chaque page, chaque colonne se lit indépendamment et continue sur la page suivante.
    Retourne {n° de course: {car, drivers, laps: [{n, d, time, s1, s2, s3, top, elapsed, flags}]}}."""
    cars: dict[int, dict] = {}
    cur: dict[int, dict | None] = {0: None}                          # une seule voiture « en cours » : la lecture suit la colonne de gauche, puis celle de droite, puis la page suivante
    for rows in pages:
        mid = 310.0
        for col in (0, 1):
            crow = [[(x, w) for x, w in r if (x < mid) == (col == 0)] for r in rows]
            crow = [r for r in crow if r]
            for r in crow:
                toks = [w for _, w in r]
                body = [w for w in toks if w != "B"]
                flags = ["pit"] if "B" in toks else []
                if len(body) >= 6 and body[0].isdigit() and body[1].isdigit() and LAPTIME.match(body[2]) and cur[0] is not None:
                    prev = cur[0]["laps"][-1]["n"] if cur[0]["laps"] else 0
                    if int(body[0]) <= prev:                         # numérotation qui recule : ligne d'une autre voiture, on détache la colonne
                        cur[0] = None
                        continue
                    elapsed = body[-1]
                    mids = body[3:-1]
                    top = None
                    if len(mids) >= 4:
                        top = _num(mids[3])
                    cur[0]["laps"].append({"n": int(body[0]), "d": int(body[1]), "time": body[2], "s1": mids[0] if len(mids) > 0 else "", "s2": mids[1] if len(mids) > 1 else "", "s3": mids[2] if len(mids) > 2 else "",
                                             "top": top, "elapsed": elapsed, "flags": flags})
                    continue
                m = re.match(r"^(\d+) (.+)$", _text(r))
                if m and len(r) >= 3 and r[0][1].isdigit() and r[1][0] - r[0][0] > 10 and not LAPTIME.match(r[1][1]) and not r[1][1].isdigit():
                    no = int(m.group(1))
                    cur[0] = cars.setdefault(no, {"no": no, "car": re.sub(r"\s+[+-]\d?L$", "", m.group(2)).strip(), "drivers": [], "laps": []})
                    continue
                m = re.match(r"^(\d)\.\s*(.+?)(?:\s+[+-]\d?L)?$", _text(r))
                if m and cur[0] is not None and not cur[0]["laps"]:
                    cur[0]["drivers"].append(m.group(2).strip())
    return cars


def run_hours(lap_list: list[dict], laps: int) -> float | None:
    """Temps de roulage (heures) = somme des temps au tour. Un tour avec passage par les stands (« B ») dure plus que la normale (arrêt) : il compte pour un tour moyen
    (médiane des autres tours), l'arrêt lui-même est exclu ; les tours absents de l'analyse comptent aussi pour un tour moyen."""
    normal = [t for t in (secs(x["time"]) for x in lap_list if "pit" not in x.get("flags", [])) if t]
    if not normal:
        return None
    med = statistics.median(normal)
    total = sum(normal) + med * sum(1 for x in lap_list if "pit" in x.get("flags", []))
    known = len(lap_list)
    total += med * max(laps - known, 0)
    return round(total / 3600, 2)


def best_summary(laps: list[dict], official_best: str = "") -> dict:
    """Meilleur tour, meilleurs secteurs, vitesse de pointe et meilleur tour théorique d'une voiture. Les tours plus rapides que le meilleur tour officiel
    sont des tours invalidés (drapeau rouge, pit lane) : ils sont écartés."""
    floor = (secs(official_best) or 0) - 0.0005
    ok = [lap for lap in laps if "pit" not in lap["flags"] and (secs(lap["time"]) or 0) >= floor]
    times = [(secs(lap["time"]), lap) for lap in ok if secs(lap["time"])]
    if not times:
        return {}
    best_t, best_lap = min(times, key=lambda t: t[0])
    sect = {}
    for k in ("s1", "s2", "s3"):
        v = [secs(lap[k]) for lap in ok if secs(lap[k])]
        sect[k] = min(v) if v else None
    top = [lap["top"] for lap in laps if lap.get("top")]
    ideal = round(sum(sect.values()), 3) if all(sect.values()) else None
    return {"best": fmt(best_t), "best_lap_no": best_lap["n"], "sectors": {k: fmt(v) for k, v in sect.items()}, "ideal": fmt(ideal), "top_speed": max(top) if top else None}


def pace(laps: list[dict], n: int = 5) -> str:
    """Moyenne des n meilleurs tours (hors tours d'entrée / sortie des stands) : mesure de régularité."""
    v = sorted(s for s in (secs(lap["time"]) for lap in laps if "pit" not in lap["flags"]) if s)[:n]
    return fmt(round(statistics.mean(v), 3)) if v else ""



# ---- Grille de départ, lap chart, rangs sur le plateau -------------------------------------------------------------------------------------

def parse_grid(rows: list[list[tuple[float, str]]]) -> dict[int, int]:
    """Grille de départ : sous la ligne des numéros, « -N- » au centre ; la voiture de droite est en position 2N-1 et celle de gauche en 2N."""
    out: dict[int, int] = {}
    for i, r in enumerate(rows):
        t = [w for _, w in r]
        if i == 0 or len(t) != 3 or t[0] != "-" or t[2] != "-" or not t[1].isdigit():
            continue
        n, mid = int(t[1]), r[1][0]
        nums = [(x, int(w)) for x, w in rows[i - 1] if w.isdigit() and len(w) <= 3]
        left = [no for x, no in nums if x < mid]
        right = [no for x, no in nums if x > mid]
        if right:
            out[right[0]] = 2 * n - 1
        if left:
            out[left[-1]] = 2 * n
    return out


def parse_lapchart(rows: list[list[tuple[float, str]]]) -> dict[int, list[int | None]]:
    """Lap chart : une ligne par position (n° de position à gauche), une colonne par tour ; retourne {n° de voiture: [position à la grille, après le tour 1, 2, …]}."""
    heads = sorted((x, int(w)) for r in rows for x, w in r if w.isdigit() and 100 < x < 520 and any(t == "Grid" for _, t in r) is False and False)
    del heads
    lapx: dict[int, float] = {}
    grid_x = None
    for r in rows:
        if any(w == "Grid" for _, w in r):
            grid_x = next(x for x, w in r if w == "Grid")
        if any(w in ("Nr", "Pos") for _, w in r) and grid_x is not None:
            for x, w in r:
                if w.isdigit():
                    lapx[int(w)] = x
        elif grid_x is not None and r and all(w.isdigit() for _, w in r) and all(x > 105 for x, _ in r) and r[0][1] == "1" and not lapx.get(1):
            for x, w in r:
                lapx[int(w)] = x
    if not lapx or grid_x is None:
        return {}
    lapx = dict(sorted(lapx.items()))
    cols = [(grid_x, 0)] + [(x, n) for n, x in lapx.items()]
    out: dict[int, dict[int, int]] = {}
    for r in rows:
        lab = next(((x, int(w)) for x, w in r if 78 <= x <= 95 and w.isdigit()), None)
        if lab is None:
            continue
        pos = lab[1]
        for x, w in r:
            if x < 100 or not w.isdigit():
                continue
            cx, n = min(cols, key=lambda c: abs(c[0] - x))
            if abs(cx - x) <= 7:
                out.setdefault(int(w), {})[n] = pos
    nmax = max(lapx) if lapx else 0
    return {no: [d.get(n) for n in range(0, nmax + 1)] for no, d in out.items()}


def add_field_ranks(classification: list[dict]) -> None:
    """Rang de chaque voiture sur le plateau (meilleurs secteurs, vitesse de pointe, meilleur tour théorique) et écart au meilleur du plateau."""
    cars = [c for c in classification if c.get("summary")]
    for key in ("s1", "s2", "s3"):
        vals = {c["no"]: secs(c["summary"]["sectors"].get(key)) for c in cars}
        vals = {no: v for no, v in vals.items() if v}
        order = sorted(vals, key=lambda no: vals[no])
        best = vals[order[0]] if order else None
        for c in cars:
            if c["no"] in vals:
                c["summary"].setdefault("rank", {})[key] = order.index(c["no"]) + 1
                c["summary"].setdefault("gap", {})[key] = round(vals[c["no"]] - best, 3)
    for key, get, rev in (("top", lambda c: c["summary"].get("top_speed"), True), ("ideal", lambda c: secs(c["summary"].get("ideal")), False)):
        vals = {c["no"]: get(c) for c in cars if get(c)}
        order = sorted(vals, key=lambda no: vals[no], reverse=rev)
        for c in cars:
            if c["no"] in vals:
                c["summary"].setdefault("rank", {})[key] = order.index(c["no"]) + 1
    for c in cars:
        c["summary"]["field"] = len(cars)


def race_story(c: dict, chart: dict[int, list]) -> dict | None:
    """Départ -> arrivée, meilleure position, tours en tête, d'après le lap chart."""
    ps = chart.get(c["no"])
    if not ps:
        return None
    laps = [p for p in ps[1:] if p]
    if not laps:
        return None
    return {"start": ps[0], "finish": laps[-1], "best": min(laps), "led": sum(1 for p in laps if p == 1), "positions": ps[1:]}


# ---- Lecture d'un lot de fichiers ---------------------------------------------------------------------------------------------------------

def _read_file(name: str, data: bytes, sessions: dict, ignored: list) -> None:
    """Lit un PDF et l'ajoute à sa session ; lève ValueError pour un fichier inutilisable."""
    if len(data) > MAX_BYTES:
        raise ValueError(f"{name} : fichier trop volumineux")
    if not data.startswith(b"%PDF"):
        raise ValueError(f"{name} : ce n'est pas un PDF")
    try:
        pages = _pages(data)
    except Exception:
        raise ValueError(f"{name} : PDF illisible")
    prow = [_rows(p) for p in pages]
    if not prow or not prow[0]:
        ignored.append(name)
        return
    head = parse_head(prow[0], name)
    full = "\n".join(_text(r) for p in prow for r in p)
    low = full.lower()
    if not head["kind"]:
        ignored.append(name)
        return
    key = head["kind"] + "|" + re.sub(r"\s*\(.*?\)\s*", "", head["session"]).upper()
    s = sessions.setdefault(key, {**head, "classification": [], "analysis": {}, "conditions": {}, "files": [], "grid": {}, "lapchart": {}, "dates": {}})
    s["files"].append(name)
    role = "lapchart" if "lap chart" in low[:200] else "grid" if "starting grid" in low[:200] else "analysis" if "sector analysis" in low else "weather" if "weather report" in low else "sectors" if "best sector" in low else "speed" if "best top speed" in low else "classification"
    fdate = parse_conditions(full).get("date")
    if fdate:
        s["dates"].setdefault(role, fdate)
    if "lap chart" in low[:200]:
        s["lapchart"] = parse_lapchart([r for p in prow for r in p])
        return
    if "starting grid" in low[:200]:
        s["grid"] = parse_grid([r for p in prow for r in p])
        return
    if "sector analysis" in low:
        for no, c in parse_analysis(prow).items():
            if no not in s["analysis"] or len(c["laps"]) > len(s["analysis"][no]["laps"]):
                s["analysis"][no] = c
        return
    cl = parse_classification([r for p in prow for r in p], head["kind"])
    if not cl:
        ignored.append(name)
        return
    if not s["classification"] or "revised" in low or len(cl) > len(s["classification"]):
        s["classification"] = cl
    s["conditions"].update({k: v for k, v in parse_conditions(full).items() if v})


def parse_files(files: list[tuple[str, bytes]]) -> dict:
    """Classements + analyses regroupés par session. Retourne {series, event, date, sessions: [...]} ; les fichiers inutilisés sont listés dans `ignored`."""
    if len(files) > MAX_FILES:
        raise ValueError("Trop de fichiers")
    sessions: dict[str, dict] = {}
    ignored: list[str] = []
    errors: list[str] = []
    for name, data in files:
        try:
            _read_file(name, data, sessions, ignored)
        except ValueError:
            raise
        except Exception:                                            # un PDF d'un format inattendu ne fait pas échouer tout l'import
            import logging
            logging.getLogger("logbook").exception("Al Kamel : lecture impossible de %s", name)
            errors.append(name)
    out_sessions = []
    for s in sessions.values():
        ana = s.pop("analysis")
        by_no = {c["no"]: c for c in s["classification"]}
        for no, a in ana.items():
            c = by_no.get(no)
            a["summary"] = best_summary(a["laps"], (c or {}).get("best", "") if c else "")
            a["pace5"] = pace(a["laps"])
            if c is not None:
                c["summary"] = a["summary"]
                c["pace5"] = a["pace5"]
                c["lap_list"] = a["laps"]
                if not c.get("drivers") and a["drivers"]:
                    c["drivers"] = a["drivers"]
                if not c.get("laps"):
                    c["laps"] = len(a["laps"])
        if not s["classification"] and ana:                          # pas de classement fourni : une entrée par voiture de l'analyse
            s["classification"] = [{"pos": None, "no": no, "drivers": a["drivers"], "car": a["car"], "class": "", "classified": True, "laps": len(a["laps"]), "best": a["summary"].get("best", ""), "summary": a["summary"], "pace5": a["pace5"], "lap_list": a["laps"]} for no, a in sorted(ana.items())]
        grid, chart = s.pop("grid", {}), s.pop("lapchart", {})
        for c in s["classification"]:
            if c["no"] in grid:
                c["grid"] = grid[c["no"]]
            if s["kind"] == "race":
                st = race_story(c, chart)
                if st:
                    c["story"] = st
                    c.setdefault("grid", st["start"])
        add_field_ranks(s["classification"])
        # jour de la session : la date des fichiers propres à la session (analyse, météo, secteurs, vitesses, lap chart) ; le classement est parfois republié le lendemain, la grille la veille
        dates = s.pop("dates", {})
        s["date"] = next((dates[r] for r in ("analysis", "weather", "sectors", "speed", "lapchart", "classification", "grid") if dates.get(r)), "")
        s["laps_max"] = max((c.get("laps") or 0 for c in s["classification"]), default=0)
        out_sessions.append(s)
    order = {"practice": 0, "qualifying": 1, "race": 2}
    out_sessions.sort(key=lambda s: (order.get(s["kind"], 9), s["session"]))
    first = out_sessions[0] if out_sessions else {}
    d = min((s["date"] for s in out_sessions if s.get("date")), default="")
    return {"series": first.get("series", ""), "event": title_case(first.get("event", "")), "date": d, "date_to": max((s["date"] for s in out_sessions if s.get("date")), default=""), "sessions": out_sessions, "ignored": ignored, "errors": errors,
            "circuit_km": estimate_length(out_sessions)}


def title_case(t: str) -> str:
    return " ".join(w.capitalize() if w.isupper() and len(w) > 2 else w for w in t.split()) if t and t.upper() == t else t


_EVENT_WORDS = {"classic", "historic", "festival", "trophy", "revival", "meeting", "series", "cup", "challenge", "grand", "prix", "gp", "international", "historique", "days", "legends", "endurance"}


def suggest_circuit(event: str, circuits: list[dict]) -> dict:
    """Circuit proposé d'après le nom de l'épreuve : un circuit enregistré dont le nom figure dans l'épreuve, sinon le nom de l'épreuve dépouillé de « Classic », « Historic »…"""
    import unicodedata
    norm = lambda x: re.sub(r"[^a-z0-9 ]", "", unicodedata.normalize("NFD", x.lower()).encode("ascii", "ignore").decode()).strip()
    ev = norm(event)
    for c in sorted(circuits, key=lambda c: -len(c["name"])):
        if norm(c["name"]) and norm(c["name"]) in ev:
            return {"name": c["name"], "existing": True}
    words = [w for w in event.split() if norm(w) not in _EVENT_WORDS]
    return {"name": " ".join(words) or event, "existing": False}


def suggest_event(events: list[dict], event: str, circuit: str) -> str:
    """Événement du Planning correspondant à l'épreuve : celui dont le titre ou le lieu contient le circuit ou un mot de l'épreuve ; à défaut le seul événement de la période."""
    import unicodedata
    norm = lambda x: re.sub(r"[^a-z0-9 ]", "", unicodedata.normalize("NFD", (x or "").lower()).encode("ascii", "ignore").decode())
    keys = [w for w in norm(circuit).split() + norm(event).split() if len(w) > 3 and w not in _EVENT_WORDS]
    for e in events:
        hay = norm(e.get("title", "")) + " " + norm((e.get("place") or {}).get("address", ""))
        if any(k in hay for k in keys):
            return e["id"]
    return events[0]["id"] if len(events) == 1 else ""


def estimate_length(sessions: list[dict]) -> float | None:
    """Longueur du tour = vitesse moyenne × durée / nombre de tours (classement de course ; médiane sur les voitures qui ont fini à plein tour)."""
    est = []
    for s in sessions:
        for c in s["classification"]:
            t, kph, laps = secs(c.get("total_time")), c.get("kph"), c.get("laps")
            if t and kph and laps and laps >= 5:
                est.append(kph * t / 3600 / laps)
    return round(statistics.median(est), 3) if est else None


# ---- Création des roulages -----------------------------------------------------------------------------------------------------------------

def _slim(c: dict) -> dict:
    """Classement conservé dans le roulage : une ligne par voiture, sans le détail des tours (gardé seulement pour nos voitures)."""
    keep = ("pos", "no", "drivers", "car", "class", "classified", "laps", "total_time", "gap", "kph", "best", "best_lap_no", "best_kph", "driver_times", "average", "summary", "pace5", "grid", "story")
    return {k: c[k] for k in keep if k in c}


def import_batch(body: dict, user: str) -> dict:
    """Crée un roulage par session choisie et y associe les voitures indiquées (n° de course -> clé de voiture du Garage)."""
    try:
        d = date.fromisoformat(str(body.get("date") or ""))
    except ValueError:
        raise ValueError("Date de l'épreuve invalide")
    event = str(body.get("event") or "").strip()[:100]
    circuit = str(body.get("circuit") or "").strip()[:80]
    event_id = str(body.get("event_id") or "").strip()[:40]
    length = body.get("circuit_km")
    if not event:
        raise ValueError("Indiquez le nom de l'épreuve")
    if not circuit:
        raise ValueError("Indiquez le circuit")
    if not rides.circuits_coll().get(rides.circuit_id(circuit)):
        try:
            length = float(length)
        except (TypeError, ValueError):
            length = 0
        rides.save_circuit(rides.CircuitIn(name=circuit, length_km=length))
    sessions = body.get("sessions") or []
    if not isinstance(sessions, list) or len(sessions) > 12 or (not sessions and not body.get("manual")):
        raise ValueError("Aucune session à importer")
    created, runs_n = [], 0
    for s in sessions:
        mapping = {int(k): v for k, v in (s.get("cars") or {}).items() if v}
        if not mapping:
            continue
        name = f"{event} — {str(s.get('session') or s.get('kind') or '').strip()}"[:120]
        try:
            sd = date.fromisoformat(str(s.get("date") or "")) if s.get("date") else d      # chaque session a son jour (essais, qualifications, course)
        except ValueError:
            raise ValueError("Date invalide pour une session")
        sin = rides.SessionIn(date=sd, name=name, kind="circuit", circuit=circuit, event_id=event_id, notes=str(s.get("notes") or "")[:1000])
        # un roulage Al Kamel est retrouvé s'il existe déjà (même date, nom, circuit) : on le complète au lieu de le doubler
        sdoc = next((x for x in rides.sessions_coll().all() if rides._session_key(x) == rides._session_key({**sin.model_dump(mode="json")})), None)
        sid = sdoc["id"] if sdoc else "s-" + uuid.uuid4().hex[:10]
        classification = [_slim(c) for c in (s.get("classification") or [])][:80]
        alk = {"series": str(body.get("series") or "")[:100], "event": event, "session": str(s.get("session") or ""), "kind": s.get("kind"), "conditions": s.get("conditions") or {}, "classification": classification, "imported_at": rides.now().isoformat(), "imported_by": user.lower()}
        doc = {**(sdoc or {}), "id": sid, **sin.model_dump(mode="json"), "stages": [], "alkamel": alk, "created_by": (sdoc or {}).get("created_by", user.lower()), "created_at": (sdoc or {}).get("created_at", rides.now().isoformat())}
        rides.sessions_coll().put(sid, doc)
        by_no = {c["no"]: c for c in (s.get("classification") or []) if isinstance(c, dict)}
        for no, key in mapping.items():
            c = by_no.get(no)
            if not c or not rides.car_of(key):
                continue
            last = max((x["n"] for x in c.get("lap_list") or []), default=0)
            official = int(c.get("laps") or 0)
            laps = last if last and official > 3 * last + 5 else max(official, last)               # un total aberrant du classement (mauvaise colonne) est écarté au profit de l'analyse
            for old in [r for r in rides.runs_coll().all() if r.get("session_id") == sid and r["vehicle"] == key]:
                rides.runs_coll().delete(old["id"])                  # ré-import : la participation est remplacée
            uses = [rides.TyreUse(**{k: u[k] for k in ("set_id", "laps", "cycles") if k in u and u[k] not in (None, "")}) for u in ((s.get("tyres") or {}).get(key) or []) if u.get("set_id")]
            hours = run_hours(c.get("lap_list") or [], laps)
            rin = rides.RunIn(date=sd, name=name, kind="circuit", circuit=circuit, laps=laps, hours=hours, drivers=[str(x)[:60] for x in (c.get("drivers") or [])][:6], tyres=uses, notes="")
            run = rides._run_doc(key, rin, "r-" + uuid.uuid4().hex[:10], user, source="alkamel", session_id=sid)
            run["timing"] = {"no": no, "class": c.get("class", ""), "pos": c.get("pos"), "laps": c.get("laps"), "total_time": c.get("total_time", ""), "gap": c.get("gap", ""), "kph": c.get("kph"), "best": c.get("best", ""), "best_lap_no": c.get("best_lap_no"),
                             "summary": c.get("summary") or {}, "pace5": c.get("pace5", ""), "grid": c.get("grid"), "story": c.get("story"), "lap_list": (c.get("lap_list") or [])[:400]}
            rides.runs_coll().put(run["id"], run)
            runs_n += 1
        created.append({"id": sid, "name": name})
    meeting = re.sub(r"[^a-z0-9]+", "-", f"{event}-{d.isoformat()[:7]}".lower()).strip("-")[:60]
    for sid in [c["id"] for c in created]:
        doc = rides.sessions_coll().get(sid)
        rides.sessions_coll().put(sid, {**doc, "meeting": meeting})
    # sessions non chronométrées (essais de la veille, shakedown) saisies à la main : mêmes événement et circuit, aucun temps
    for m in body.get("manual") or []:
        try:
            md = date.fromisoformat(str(m.get("date") or ""))
        except ValueError:
            raise ValueError("Date invalide pour une session manuelle")
        mname = str(m.get("name") or "").strip()
        if not mname:
            raise ValueError("Nom manquant pour une session manuelle")
        cars = [c for c in (m.get("cars") or []) if c.get("key") and rides.car_of(c["key"]) and (c.get("laps") or c.get("km"))]      # une voiture sans tour ni km n'a pas roulé
        if not cars:
            continue
        sname = f"{event} — {mname}"[:120]
        sin = rides.SessionIn(date=md, name=sname, kind="circuit", circuit=circuit, event_id=event_id, notes=str(m.get("notes") or "")[:1000])
        sdoc = next((x for x in rides.sessions_coll().all() if rides._session_key(x) == rides._session_key({**sin.model_dump(mode="json")})), None)
        sid = sdoc["id"] if sdoc else "s-" + uuid.uuid4().hex[:10]
        rides.sessions_coll().put(sid, {**(sdoc or {}), "id": sid, **sin.model_dump(mode="json"), "stages": [], "meeting": meeting, "untimed": True,
                                       "created_by": (sdoc or {}).get("created_by", user.lower()), "created_at": (sdoc or {}).get("created_at", rides.now().isoformat())})
        for c in cars:
            laps = max(0, min(int(c.get("laps") or 0), 5000))
            km = c.get("km")
            uses = [rides.TyreUse(**{k: u[k] for k in ("set_id", "laps", "cycles") if k in u and u[k] not in (None, "")}) for u in (c.get("tyres") or []) if u.get("set_id")]
            rin = rides.RunIn(date=md, name=sname, kind="circuit", circuit=circuit, laps=laps, km=float(km) if km not in (None, "") else None, drivers=[str(x)[:60] for x in (c.get("drivers") or [])][:6], tyres=uses)
            for old in [r for r in rides.runs_coll().all() if r.get("session_id") == sid and r["vehicle"] == c["key"]]:
                rides.runs_coll().delete(old["id"])
            run = rides._run_doc(c["key"], rin, "r-" + uuid.uuid4().hex[:10], user, source="manual", session_id=sid)
            rides.runs_coll().put(run["id"], run)
            runs_n += 1
        created.append({"id": sid, "name": sname})
    if not created:
        raise ValueError("Associez au moins une voiture du Garage à un numéro de course")
    return {"sessions": created, "runs": runs_n}


def suggest_cars(parsed: dict) -> list[dict]:
    """Voitures du Garage proposées pour chaque numéro de course de l'épreuve : le n° de course enregistré dans la fiche (s'il figure dans les PDF), sinon rien (choix manuel)."""
    by_no: dict[int, str] = {}
    for c in rides.race_cars():
        rn = (rides.cars_coll().get(c["key"]) or {}).get("race_number")
        if rn and str(rn).strip().isdigit():
            by_no[int(str(rn).strip())] = c["key"]
    present = {c["no"] for s in parsed.get("sessions", []) for c in s["classification"]}                 # seulement les numéros réellement engagés dans l'épreuve
    return [{"no": no, "key": key} for no, key in by_no.items() if no in present]


def now_iso() -> str:
    return datetime.now().isoformat()
