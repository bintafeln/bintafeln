"""Namen für Vergleiche vereinheitlichen.

Dieselbe Normalisierung nutzen der genaue Namensvergleich (``apps.antraege.aufnahme``) und der
Suchname ``Person.such_name``. Über ``such_name`` läuft ein Trigramm-Index (pg_trgm), damit der
Abgleich mit dem Kundenstamm nur noch ähnliche Personen aus der Datenbank holt, statt jeden mit
jedem in Python zu vergleichen (sonst bricht der Abgleich beim großen Kundenstamm ab).
"""

import re
import unicodedata

UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normal(text: str) -> str:
    """Für Vergleiche: klein, Umlaute ausgeschrieben, ohne Akzente und Satzzeichen."""
    text = (text or "").lower().translate(UMLAUTE)
    text = "".join(z for z in unicodedata.normalize("NFKD", text) if not unicodedata.combining(z))
    return " ".join(re.sub(r"[^a-z ]+", " ", text).split())


def such_name(vorname: str, nachname: str) -> str:
    """Normalisierter „vorname nachname“ für den Trigramm-Index (``Person.such_name``)."""
    return f"{normal(vorname)} {normal(nachname)}".strip()
