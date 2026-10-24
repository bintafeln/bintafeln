"""Feste Auswahllisten für Eingabefelder (Regel in CLAUDE.md: Auswahl statt Freitext).

Gespeichert wird der angezeigte Text, damit vorhandene und importierte Werte lesbar bleiben.
"""

ANREDEN = [("", "keine Angabe"), ("Frau", "Frau"), ("Herr", "Herr"), ("Divers", "Divers")]

FAMILIENSTAENDE = [
    "ledig", "verheiratet", "eingetragene Lebenspartnerschaft", "getrennt lebend", "geschieden",
    "verwitwet",
]  # fmt: skip

# Führerscheinklassen nach Fahrerlaubnis-Verordnung, dazu die alte Klasse 3 (bis 7,5 t).
FUEHRERSCHEINKLASSEN = [
    "AM", "A1", "A2", "A", "B", "BE", "C1", "C1E", "C", "CE",
    "D1", "D1E", "D", "DE", "L", "T", "3 (alt)",
]  # fmt: skip


def mit_vorhandenem(auswahl: list[tuple[str, str]], wert: str) -> list[tuple[str, str]]:
    """Ein gespeicherter Wert, der nicht (mehr) in der Liste steht, bleibt wählbar."""
    if wert and wert not in {schluessel for schluessel, _ in auswahl}:
        return [*auswahl, (wert, wert)]
    return auswahl
