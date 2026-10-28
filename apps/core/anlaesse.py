"""Kleine Überraschungen auf der Anmeldeseite an Festtagen (ADR 0079).

``anlass(tag)`` sagt, ob an einem Tag etwas über den Bildschirm zieht; ``szene()`` liefert die
Zufallswerte (Höhen, Verzögerungen, Farben) für die Vorlage ``includes/anlass.html``. Alles ist
reines CSS mit gezeichneten SVG-Figuren, läuft einmal je Aufruf und bleibt bei „Bewegung
reduzieren“ aus. Abschaltbar in den Anmelde-Einstellungen.
"""

import datetime as dt
import random

from apps.core.feiertage import ostersonntag

ANLAESSE = {
    "halloween": "Halloween: Fledermäuse",
    "karneval": "Karneval: Luftschlangen und Konfetti",
    "ostern": "Ostern: der Osterhase",
    "nikolaus": "Nikolaus: der Nikolaus im Schlitten",
    "weihnachten": "Weihnachten: der Nikolaus im Schlitten",
}
FARBEN = ["#e63946", "#f4a261", "#2a9d8f", "#457b9d", "#e9c46a", "#9b5de5", "#f15bb5", "#00bbf9"]


def anlass(tag: dt.date) -> str | None:
    """Kennung des Anlasses an ``tag`` oder None."""
    if tag.month == 10 and 24 <= tag.day <= 31:
        return "halloween"
    if tag.month == 12 and tag.day in (5, 6):
        return "nikolaus"
    if tag.month == 12 and 20 <= tag.day <= 26:
        return "weihnachten"
    ostern = ostersonntag(tag.year)
    if ostern - dt.timedelta(days=7) <= tag <= ostern + dt.timedelta(days=1):
        return "ostern"  # Palmsonntag bis Ostermontag
    if ostern - dt.timedelta(days=52) <= tag <= ostern - dt.timedelta(days=47):
        return "karneval"  # Weiberfastnacht bis Veilchendienstag
    return None


def szene(name: str, zufall: random.Random | None = None) -> dict:
    """Werte für die Animation: jede Figur etwas anders, damit es lebendig aussieht."""
    z = zufall or random.Random()  # noqa: S311 – Dekoration, kein Geheimnis

    def teile(anzahl, **bereiche):
        # als Text mit Punkt: die deutsche Zahlenformatierung der Vorlagen schriebe ein Komma
        return [
            {k: f"{z.uniform(*b):.2f}" for k, b in bereiche.items()} | {"farbe": z.choice(FARBEN)}
            for _ in range(anzahl)
        ]

    if name == "halloween":
        return {"figuren": teile(5, hoehe=(8, 60), verz=(0, 2.5), dauer=(5, 8), groesse=(70, 140))}
    if name == "karneval":
        return {
            "figuren": teile(6, hoehe=(20, 70), verz=(0, 1.5), dauer=(3, 5), groesse=(90, 160)),
            "konfetti": teile(45, links=(0, 100), verz=(0, 3), dauer=(3, 6), dreh=(180, 900)),
        }
    if name in ("nikolaus", "weihnachten"):
        return {
            "figuren": teile(1, hoehe=(8, 18), verz=(0.3, 0.6), dauer=(9, 10), groesse=(1, 1)),
            "flocken": teile(30, links=(0, 100), verz=(0, 6), dauer=(5, 9), groesse=(10, 24)),
        }
    if name == "ostern":
        return {"figuren": teile(1, hoehe=(0, 0), verz=(0.3, 0.6), dauer=(8, 9), groesse=(1, 1))}
    return {}


def fuer_anmeldung(request) -> dict:
    """Kontext für die Anmeldeseite: {"anlass": name, "szene": …} oder leer.
    ``?anlass=halloween`` zeigt einen Anlass zur Vorschau, unabhängig vom Datum."""
    from django.utils import timezone

    from apps.konten.models import AnmeldeEinstellungen

    vorschau = request.GET.get("anlass", "")
    if vorschau in ANLAESSE:
        name = vorschau
    elif AnmeldeEinstellungen.laden().ueberraschungen:
        name = anlass(timezone.localdate())
    else:
        name = None
    return {"anlass": name, "szene": szene(name)} if name else {}
