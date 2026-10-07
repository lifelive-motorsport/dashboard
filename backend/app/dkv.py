"""Factures de la carte carburant (DKV) : extraction du texte des pièces jointes Odoo (lecture seule) pour contrôler le carburant imputé par véhicule.

Le texte brut est exposé tel quel pour vérification : l'analyse des lignes de transaction (date, carte ou plaque, litres, montant) se calibre sur une
facture réelle. En attendant, `candidate_lines` repère les lignes qui contiennent une date et des montants."""
from __future__ import annotations

import io
import re

DATE = re.compile(r"\b(\d{2})[./](\d{2})[./](\d{4}|\d{2})\b")
DECIMAL = re.compile(r"(?<![\d.,])-?\d{1,3}(?:[.\s]\d{3})*,\d{1,3}(?![\d])|(?<![\d.,])-?\d+\.\d{2}(?![\d])")


def extract_text(content: bytes, mimetype: str = "", name: str = "") -> str:
    """Texte d'une pièce jointe PDF (par page) ou CSV / texte. Chaîne vide si rien n'est lisible (PDF scanné par exemple)."""
    if content[:4] == b"%PDF" or "pdf" in (mimetype or "").lower() or (name or "").lower().endswith(".pdf"):
        try:
            from pypdf import PdfReader
        except ImportError:
            return ""
        try:
            reader = PdfReader(io.BytesIO(content))
            return "\n\f".join((p.extract_text() or "") for p in reader.pages)
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
