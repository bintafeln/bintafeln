"""Frei auf der Seite gesetzte Grafiken einer Serienbrief-Vorlage (ADR 0166).

Neben den Grafiken im Text (ADR 0138) kann eine Vorlage Grafiken an eine feste Stelle der Seite
setzen, z. B. mehrere Unterschriften nebeneinander oder übereinander. ``Vorlage.freie_grafiken``
ist eine Liste aus ``{"grafik": <pk>, "x": mm von links, "y": mm von oben, "breite": mm,
"seite": "erste" | "letzte"}``. Im Brief liegen sie über dem Text und wandern nicht mit ihm; in
einer Mail gibt es keine Seite, dort stehen sie nebeneinander unter dem Text.
"""

import io
import json

from django.utils.html import format_html, format_html_join
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable

ERSTE, LETZTE = "erste", "letzte"
MAX_ANZAHL = 20
SEITE_MM = (210, 297)
MIN_BREITE, MAX_BREITE = 5, 210
PX_JE_MM = 3.78  # Breite in einer Mail (96 Punkte je Zoll)


def _zahl(wert, unten, oben, vorgabe):
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        return vorgabe
    if zahl != zahl:  # NaN
        return vorgabe
    return round(min(max(zahl, unten), oben), 1)


def lesen(roh) -> list[dict]:
    """Die Liste aus dem Formular (JSON-Text) oder der Datenbank, geprüft und begrenzt: nur
    vorhandene Grafiken, Maße innerhalb der Seite, höchstens ``MAX_ANZAHL``. Unlesbares fällt
    weg – eine verschobene Grafik soll nie das Speichern der Vorlage verhindern."""
    from apps.serienbriefe.models import Grafik

    if isinstance(roh, str):
        try:
            roh = json.loads(roh or "[]")
        except ValueError:
            return []
    if not isinstance(roh, list):
        return []
    eintraege = [e for e in roh if isinstance(e, dict)][:MAX_ANZAHL]
    kennungen = {e.get("grafik") for e in eintraege if isinstance(e.get("grafik"), int)}
    vorhanden = set(Grafik.objects.filter(pk__in=kennungen).values_list("pk", flat=True))
    ergebnis = []
    for e in eintraege:
        if e.get("grafik") not in vorhanden:
            continue
        breite = _zahl(e.get("breite"), MIN_BREITE, MAX_BREITE, 40)
        ergebnis.append({
            "grafik": e["grafik"],
            "x": _zahl(e.get("x"), 0, SEITE_MM[0] - MIN_BREITE, 25),
            "y": _zahl(e.get("y"), 0, SEITE_MM[1] - MIN_BREITE, 200),
            "breite": breite,
            "seite": ERSTE if e.get("seite") == ERSTE else LETZTE,
        })  # fmt: skip
    return ergebnis


def _mit_grafik(eintraege):
    """(Eintrag, Grafik) für alle Einträge, deren Grafik es noch gibt (sonst bleibt die Stelle
    leer, wie bei Grafiken im Text)."""
    from apps.serienbriefe.models import Grafik

    grafiken = Grafik.objects.in_bulk([e["grafik"] for e in eintraege])
    return [(e, grafiken[e["grafik"]]) for e in eintraege if e["grafik"] in grafiken]


class Zeichnung(Flowable):
    """Zeichnet die frei gesetzten Grafiken einer Seite an ihre feste Stelle. Braucht selbst
    keinen Platz: Am Anfang des Briefs landet sie auf dessen erster, am Ende auf dessen letzter
    Seite."""

    def __init__(self, eintraege):
        super().__init__()
        self.width = self.height = 0
        self.bilder = []
        for e, g in _mit_grafik(eintraege):
            if not g.breite or not g.hoehe:
                continue
            try:
                with g.bild.open("rb") as f:
                    daten = ImageReader(io.BytesIO(f.read()))
            except (OSError, ValueError):  # Datei fehlt oder ist nicht lesbar
                continue
            breite = e["breite"] * mm
            self.bilder.append((daten, e["x"] * mm, e["y"] * mm, breite,
                                breite * g.hoehe / g.breite))  # fmt: skip

    def wrap(self, *_):
        return 0, 0

    def drawOn(self, canvas, x, y, _sW=0):  # noqa: N802 (Name aus ReportLab)
        canvas.saveState()
        for daten, links, oben, breite, hoehe in self.bilder:
            canvas.drawImage(daten, links, A4[1] - oben - hoehe, width=breite, height=hoehe,
                             mask="auto")  # fmt: skip
        canvas.restoreState()

    def draw(self):  # pragma: no cover - drawOn zeichnet alles
        pass


def zeichnung(vorlage, seite: str):
    """Die ``Zeichnung`` für die erste bzw. letzte Seite eines Briefs, oder ``None``."""
    eintraege = [e for e in lesen(getattr(vorlage, "freie_grafiken", None) or [])
                 if e["seite"] == seite]  # fmt: skip
    z = Zeichnung(eintraege) if eintraege else None
    return z if z and z.bilder else None


def fuer_mail(vorlage) -> str:
    """Die frei gesetzten Grafiken als Zeile unter dem Mailtext (in der Reihenfolge von links
    nach rechts, oben vor unten); leer, wenn es keine gibt."""
    from apps.serienbriefe import grafiken

    paare = _mit_grafik(lesen(getattr(vorlage, "freie_grafiken", None) or []))
    if not paare:
        return ""
    paare.sort(key=lambda p: (round(p[0]["y"] / 15), p[0]["x"]))
    bilder = format_html_join(
        " ", '<img src="{}" alt="{}" width="{}">',
        ((grafiken.adresse(g), g.name, round(e["breite"] * PX_JE_MM)) for e, g in paare),
    )  # fmt: skip
    return format_html("<p>{}</p>", bilder)
