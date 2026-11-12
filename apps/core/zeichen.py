"""Zeichen, die in Daten aus anderen Programmen stecken und im Druck als schwarzer Block
erscheinen: Ligaturen aus PDF-Text (ein Zeichen für „ff“, „fi“ …) und unsichtbare Zeichen
(Breite null, Schreibrichtung, Byte-Reihenfolge). Die Schrift der PDFs kennt sie nicht.

``bereinigen()`` gehört an zwei Stellen: dort, wo fremder Text hereinkommt (PDF auslesen,
Adresse speichern), und als Netz darunter dort, wo gedruckt wird (``apps.core.pdf``)."""

LIGATUREN = {
    "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "ﬅ": "st", "ﬆ": "st",
}  # fmt: skip
# Breite null, Schreibrichtung, Wortverbinder, Byte-Reihenfolge, Objekt-/Ersatzzeichen
UNSICHTBAR = "​‌‍‎‏‪‫‬‭‮⁠⁡⁢⁣⁦⁧⁨⁩﻿￼�"
# besondere Leerzeichen (schmal, geschützt schmal, Ziffernbreite …) → gewöhnliches Leerzeichen
LEERZEICHEN = "             　"

_TABELLE = str.maketrans(
    LIGATUREN | dict.fromkeys(UNSICHTBAR, "") | dict.fromkeys(LEERZEICHEN, " ")
)


def bereinigen(text: str) -> str:
    """Ligaturen ausschreiben, unsichtbare Zeichen entfernen, besondere Leerzeichen ersetzen."""
    return text.translate(_TABELLE) if text else text
