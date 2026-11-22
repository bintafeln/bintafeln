"""Einen ganzen Tourtag zurücksetzen (ADR 0162): alles, was an einem Tag auf einer Tour passiert
ist – Fahrt mit Kilometerständen, Lieferscheine, „Hier waren wir“, Zusatzstopps, Meldungen zum
Fahrzeug, die bestätigte Besetzung. Gedacht für Testtouren und versehentlich Eingetragenes.

Alles kommt als **ein** Eintrag in den Papierkorb und lässt sich von dort gemeinsam
wiederherstellen. Weil Lieferscheine Belege sind, braucht es beide Rechte: Fahrtenbuch
(``touren.fahrten``) und alle Lieferscheine (``touren.lieferscheine``). Die Statistik rechnet aus
Lieferscheinen und Fahrten; sie stimmt danach von selbst."""

import datetime as dt

from apps.core import papierkorb
from apps.konten import rollen
from apps.touren import fahrten
from apps.touren.models import (
    Anfahrt,
    Fahrt,
    Fahrzeugmeldung,
    Lieferschein,
    Tour,
    Tourstart,
    Zusatzstopp,
)

RECHTE = ("touren.fahrten", "touren.lieferscheine")
MELDUNG = "Meldung zum Fahrzeug"


def darf(benutzer) -> bool:
    return all(rollen.hat_recht(benutzer, recht) for recht in RECHTE)


def _mengen(tour: Tour, datum: dt.date) -> dict:
    eigene = Fahrt.objects.filter(tour=tour, datum=datum)
    return {
        "Fahrt": eigene,
        "Lieferschein": Lieferschein.objects.filter(tour=tour, datum=datum),
        "„Hier waren wir“": Anfahrt.objects.filter(tour=tour, datum=datum),
        "Zusatzstopp": Zusatzstopp.objects.filter(tour=tour, datum=datum),
        MELDUNG: Fahrzeugmeldung.objects.filter(fahrt__in=eigene),
        "bestätigte Besetzung": Tourstart.objects.filter(tour=tour, datum=datum),
    }


def inhalt(tour: Tour, datum: dt.date) -> list[tuple[str, int]]:
    """Was an dem Tag zu dieser Tour eingetragen ist: [(Bezeichnung, Anzahl)], nur Vorhandenes."""
    return [(name, qs.count()) for name, qs in _mengen(tour, datum).items() if qs.exists()]


def zuruecksetzen(tour: Tour, datum: dt.date, benutzer) -> list[tuple[str, int]]:
    """Legt alles vom Tag in den Papierkorb und stellt die Kilometerstände der Fahrzeuge zurück.
    Ergebnis wie ``inhalt()`` vor dem Löschen; leer, wenn nichts da war."""
    mengen = _mengen(tour, datum)
    da = [(name, qs.count()) for name, qs in mengen.items() if qs.exists()]
    if not da:
        return []
    zurueck = [fahrten.stand_zurueck(f) for f in mengen["Fahrt"].select_related("fahrzeug")]
    # Meldungen zuerst: Mit der Fahrt verlören sie sonst nur den Bezug und blieben stehen
    rest = [qs for name, qs in mengen.items() if name != MELDUNG]
    papierkorb.loeschen(benutzer, "Tourtag", f"{tour.name} am {datum:%d.%m.%Y}",
                        mengen[MELDUNG], *rest, recht="touren.lieferscheine")  # fmt: skip
    for stellen in zurueck:
        stellen()
    return da
