"""Factures de la carte carburant (DKV) : extraction du texte des pièces jointes Odoo (lecture seule) et analyse des transactions.

Chaque facture DKV est un PDF qui liste, par véhicule (plaque) et par carte, les transactions : date, station, heure, kilométrage saisi au passage à la pompe
(souvent vide ou factice : « 1 »), produit, quantité et montants. Les lignes sans véhicule (cotisation de carte, péages…) sont classées à part."""
from __future__ import annotations

import io
import re
from datetime import date

DATE = re.compile(r"\b(\d{2})[./](\d{2})[./](\d{4}|\d{2})\b")
DECIMAL = re.compile(r"(?<![\d.,])-?\d{1,3}(?:[.\s]\d{3})*,\d{1,3}(?![\d])|(?<![\d.,])-?\d+\.\d{2}(?![\d])")
NUM = re.compile(r"^-?\d{1,3}(?:\.\d{3})*,\d+$|^-?\d+,\d+$")
VEHICLE = re.compile(r"VEHICLE:\s*(?P<veh>.*?)\s+CARD NO\.?:\s*(?P<card>[\d.]+)", re.I)
ROW = re.compile(r"^\s*(?P<d>\d{2}\.\d{2}\.\d{4})\s+(?P<rest>.+)$")
TIME = re.compile(r"^\d{1,2}:\d{2}$")
UNITS = {"LTR", "KWH", "KG", "PC", "L", "M3"}
FUELS = ("GAZOLE", "DIESEL", "EURO 95", "SUPER", "ESSENCE", "SP95", "SP98", "GPL", "LPG", "CNG", "GNV", "ELECTR", "BENZIN", "PREMIUM")


def _pdftotext(content: bytes) -> str | None:
    """Texte d'un PDF en conservant les colonnes (« pdftotext -layout », paquet poppler-utils). None si l'outil est absent."""
    import os
    import shutil
    import subprocess
    import tempfile
    exe = shutil.which("pdftotext")
    if not exe:
        return None
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(content)
        path = f.name
    try:
        r = subprocess.run([exe, "-layout", path, "-"], capture_output=True, timeout=45)
        return r.stdout.decode("utf-8", "replace") if r.returncode == 0 else None
    except Exception:
        return None
    finally:
        os.unlink(path)


def extract_text(content: bytes, mimetype: str = "", name: str = "") -> str:
    """Texte d'une pièce jointe PDF (colonnes conservées) ou CSV / texte. Chaîne vide si rien n'est lisible (PDF scanné par exemple)."""
    if content[:4] == b"%PDF" or "pdf" in (mimetype or "").lower() or (name or "").lower().endswith(".pdf"):
        t = _pdftotext(content)
        if t is not None:
            return t
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        try:
            return "\n\f".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(content)).pages)     # secours : mise en page moins fidèle
        except Exception:
            return ""
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return content.decode(enc)
        except UnicodeDecodeError:
            continue
    return ""


def candidate_lines(text: str) -> list[str]:
    """Lignes qui ressemblent à une transaction : une date et au moins un montant décimal."""
    return [ln.strip() for ln in text.splitlines() if DATE.search(ln) and DECIMAL.search(ln)]


def _num(t: str) -> float:
    return float(t.replace(".", "").replace(",", "."))


def _is_fuel(product: str, unit: str = "") -> bool:
    """Carburant : produit connu (gazole, euro 95…) ou, à l'étranger, tout produit livré en litres à la pompe (« DIZEL », « ON »…) hors AdBlue et huiles."""
    p = product.upper()
    if "ADBLUE" in p or any(k in p for k in ("OIL", "HUILE", "WASH", "LAVE", "ADDITIV")):
        return False
    return any(k in p for k in FUELS) or unit in {"LTR", "L", "KG", "KWH"}


KFZ = re.compile(r"KFZ-KZ\s+([A-Z0-9-]+)")
CURRENCY = re.compile(r"(?:Monnaie|Währung|Currency)\s*:?\s*([A-Z]{3})\b")
ALL_UNITS = UNITS | {"ST", "DB", "PCS", "EUR", "CZK", "PLN", "HUF"}


def _category(product: str, fuel: bool) -> str:
    p = product.upper()
    if fuel:
        return "carburant"
    if "ADBLUE" in p:
        return "adblue"
    if any(k in p for k in ("PÉAGE", "PEAGE", "MAUT", "TOLL", "DKV BOX", "ÚTDÍJ", "ÚTHASZN", "VIGNETTE", "TUNNEL")):
        return "peage"
    if any(k in p for k in ("COTISATION", "GESTION", "FRAIS")):
        return "frais_dkv"
    return "autre"


def parse_row(line: str, vehicle: str = "", card: str = "", currency: str = "EUR") -> dict | None:
    """Une ligne de transaction ou de prestation : « 15.07.2026 SHELL ST. VITH 1098661 6535520024 07:15 75000 GAZOLE 0009 LTR 34,330 … 66,10 0,00 66,10 »
    (carburant, avec heure et kilométrage éventuel) ou « 01.09.2026 DKV BOX EUROPE BE 1000099 2026-SFC-… Péage BE 0901 PC 1 2,31 2,31 2,31 » (prestation). None sinon."""
    m = ROW.match(line)
    if not m:
        return None
    tk = m["rest"].split()
    ui = next((i for i in range(1, len(tk) - 1) if re.fullmatch(r"(?=.*\d)[0-9A-Z]{4}", tk[i]) and tk[i + 1] in ALL_UNITS), None)
    if ui is None:
        return None
    ti = next((i for i in range(ui) if TIME.match(tk[i])), None)
    km = None
    if ti is not None:                                                      # ligne de carburant : station, heure, kilométrage éventuel, produit
        if ti < 2:
            return None
        pre = tk[:ti]
        tx = pre[-1] if pre[-1].isdigit() else ""
        st_no = pre[-2] if len(pre) >= 2 and pre[-2].isdigit() else ""
        station = " ".join(pre[: len(pre) - (2 if st_no else 1 if tx else 0)])
        mid = tk[ti + 1:ui]
        if mid and mid[0].isdigit() and len(mid) > 1:
            km = int(mid[0])
            mid = mid[1:]
        time = tk[ti]
    else:                                                                   # prestation sans heure : péage, cotisation…
        first_num = next((i for i in range(ui) if tk[i].isdigit()), None)
        station = " ".join(tk[:first_num]) if first_num else ""
        j = first_num if first_num is not None else 0
        while j < ui and (tk[j].isdigit() or re.fullmatch(r"[\d-]{6,}", tk[j]) or re.fullmatch(r"\d{4}-[A-Z]+-\d+", tk[j])):
            j += 1
        mid = tk[j:ui]
        time = ""
    after = tk[ui + 2:]
    if after and after[0] in ALL_UNITS:                                      # « 0CGF EUR PC 1 … » : devise puis unité
        after = after[1:]
    if not after:
        return None
    try:
        qty = _num(after[0]) if "," in after[0] else float(after[0])
    except ValueError:
        return None
    nums = [_num(t) for t in after[1:] if NUM.match(t)]
    if not nums:
        return None
    d, mo, y = (int(x) for x in m["d"].split("."))
    product = " ".join(mid)
    fuel = ti is not None and _is_fuel(product, tk[ui + 1])
    total = nums[-3] if len(nums) >= 7 else nums[-1]
    return {"date": date(y, mo, d).isoformat(), "time": time, "vehicle": vehicle, "card": card, "station": station, "km": km, "product": product, "fuel": fuel,
            "category": _category(product, fuel), "unit": tk[ui + 1], "quantity": qty, "total_ht": total, "currency": currency}


def parse_transactions(text: str) -> dict:
    """{transactions: [carburant, AdBlue, péages, cotisations… par véhicule], ignored: nombre de lignes de détail non reprises (détail des péages en monnaie locale)}."""
    tx, ignored = [], 0
    veh, card, cur = "", "", "EUR"
    for ln in text.splitlines():
        c = CURRENCY.search(ln)
        if c:
            cur = c[1]
        v = VEHICLE.search(ln)
        if v:
            veh, card = re.sub(r"[\s-]+", "", v["veh"]).upper(), v["card"]
            continue
        k = KFZ.search(ln)
        if k:
            veh, card = re.sub(r"[\s-]+", "", k[1]).upper(), ""
            continue
        if not ROW.match(ln):
            continue
        r = parse_row(ln, veh, card, cur)
        if r:
            tx.append(r)
        else:
            ignored += 1
    return {"transactions": tx, "ignored": ignored}


def summarize(parsed: dict) -> dict:
    """Totaux d'une facture en EUR : par véhicule (litres et montant HT de carburant, AdBlue, péages, frais), kilométrages relevés, et lignes en autre monnaie à part."""
    veh: dict[str, dict] = {}
    foreign: dict[str, float] = {}
    for t in parsed["transactions"]:
        if t["currency"] != "EUR":
            foreign[t["currency"]] = foreign.get(t["currency"], 0.0) + t["total_ht"]
            continue
        d = veh.setdefault(t["vehicle"] or "(sans véhicule)", {"vehicle": t["vehicle"] or "(sans véhicule)", "card": t["card"], "fuel_litres": 0.0, "fuel_ht": 0.0, "adblue_ht": 0.0,
                                                               "toll_ht": 0.0, "other_ht": 0.0, "n": 0, "dates": [], "km": []})
        d["n"] += 1
        d["dates"].append(t["date"])
        cat = t["category"]
        if cat == "carburant":
            d["fuel_litres"] += t["quantity"]
            d["fuel_ht"] += t["total_ht"]
            if t["km"] and t["km"] > 100:               # un compteur à « 1 » ou à quelques unités n'est pas un relevé
                d["km"].append({"date": t["date"], "km": t["km"]})
        elif cat == "adblue":
            d["adblue_ht"] += t["total_ht"]
        elif cat == "peage":
            d["toll_ht"] += t["total_ht"]
        else:
            d["other_ht"] += t["total_ht"]
    rows = sorted(veh.values(), key=lambda d: -d["fuel_ht"])
    r2 = lambda x: round(x, 2)
    return {"vehicles": [{**d, "fuel_litres": r2(d["fuel_litres"]), "fuel_ht": r2(d["fuel_ht"]), "adblue_ht": r2(d["adblue_ht"]), "toll_ht": r2(d["toll_ht"]), "other_ht": r2(d["other_ht"])} for d in rows],
            "fuel_ht": r2(sum(d["fuel_ht"] for d in rows)), "adblue_ht": r2(sum(d["adblue_ht"] for d in rows)), "toll_ht": r2(sum(d["toll_ht"] for d in rows)),
            "other_ht": r2(sum(d["other_ht"] for d in rows)), "foreign": {k: r2(v) for k, v in foreign.items()}, "lines": len(parsed["transactions"]), "ignored": parsed["ignored"]}
