import pytest
from app.names import normalize_name


@pytest.mark.parametrize("raw,expected", [
    ("TÜRKİYE OTOMOBİL SPORLARI FEDERASYONU (TOSFED)", "Türkiye Otomobil Sporlari Federasyonu (TOSFED)"),
    ("ALU - CONCEPT SARL / EMO Sport", "ALU - Concept SARL / EMO Sport"),
    ("TN MANAGEMENT / T. NEUVILLE (privé)", "TN Management / T. Neuville (privé)"),
    ("Eduardo Salorio Instalaciones sl", "Eduardo Salorio Instalaciones SL"),
    ("Xtremetech SL", "Xtremetech SL"),
    ("LIFELIVE GERMANY GMBH / XC", "Lifelive Germany GmbH / XC"),
    ("Gorin s.r.o", "Gorin s.r.o."),
    ("NV KOREAN MOTOR COMPANY", "NV Korean Motor Company"),
    ("JEAN-LUC O'BRIEN", "Jean-Luc O'Brien"),
    ("JLB 23 / WHITEHAND EVENT / J-L BLANCHEMAIN", "JLB 23 / Whitehand Event / J-L Blanchemain"),
    ("KORAMIC/C.DUMOLIN (PRIVÉ)", "Koramic/C.Dumolin (PRIVÉ)"),
    ("GARAGE DU PORT", "Garage du Port"),
    ("LifeLive Germany GmbH / XC", "LifeLive Germany GmbH / XC"),     # casse mixte : intacte
    ("", ""),
])
def test_normalize(raw, expected):
    assert normalize_name(raw) == expected


def test_idempotent():
    for n in ("ALU - CONCEPT SARL / EMO Sport", "TÜRKİYE OTOMOBİL SPORLARI FEDERASYONU (TOSFED)", "Eduardo Salorio Instalaciones sl"):
        once = normalize_name(n)
        assert normalize_name(once) == once
