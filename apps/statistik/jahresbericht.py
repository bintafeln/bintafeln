"""Jahresbericht als PDF (ADR 0036, Ergänzung): Kennzahlen und alle Abschnitte der Statistik.

Diagramme zeichnet ReportLab selbst (keine SVG-Umwandlung): Abschnitte mit genau einer Zahlenreihe
als Säulen, alle Abschnitte zusätzlich als Tabelle. Nur Summen, keine Personendaten.
"""

import datetime as dt

from reportlab.graphics.charts.barcharts import VerticalBarChart
from reportlab.graphics.shapes import Drawing
from reportlab.lib import colors
from reportlab.lib.units import mm

from apps.core.pdf import RAND, Pdf
from apps.statistik import auswertung as aw

# Erste Farbe der festen Reihenfolge in bintafeln.css (reihe-0 … reihe-2)
FARBEN = ["#2a78d6", "#eb6834", "#1baf7a"]


def zeitraum(jahr: int, heute: dt.date) -> aw.Zeitraum:
    """Das Kalenderjahr; im laufenden Jahr bis heute."""
    bis = min(dt.date(jahr, 12, 31), heute)
    return aw.Zeitraum(dt.date(jahr, 1, 1), bis, f"Jahr {jahr}")


def _zahl(wert) -> float | None:
    """„1.234,50“ oder 3 → Zahl; sonst None."""
    if isinstance(wert, int | float):
        return float(wert)
    try:
        return float(str(wert).replace(".", "").replace(",", ".").replace("%", "").strip())
    except ValueError:
        return None


def saeulen(daten: list[tuple[str, float]], breite: float, farbe: str) -> Drawing | None:
    """Einfaches Säulendiagramm mit einer Achse; None, wenn nichts darzustellen ist."""
    if not daten or not any(w for _, w in daten):
        return None
    hoehe = 55 * mm
    zeichnung = Drawing(breite, hoehe)
    d = VerticalBarChart()
    d.x, d.y, d.width, d.height = 12 * mm, 10 * mm, breite - 14 * mm, hoehe - 14 * mm
    d.data = [[w for _, w in daten]]
    d.categoryAxis.categoryNames = [n for n, _ in daten]
    d.categoryAxis.labels.fontSize = 6.5 if len(daten) > 12 else 7.5
    d.categoryAxis.labels.angle = 45 if len(daten) > 12 else 0
    d.categoryAxis.labels.boxAnchor = "ne" if len(daten) > 12 else "n"
    d.valueAxis.valueMin = 0
    werte = [w for _, w in daten]
    if all(float(w).is_integer() for w in werte) and max(werte) < 5:
        d.valueAxis.valueStep = 1  # Anzahlen ohne halbe Schritte
    d.valueAxis.labelTextFormat = lambda v: (
        f"{v:,.10g}".replace(",", "X").replace(".", ",").replace("X", ".")
    )
    d.categoryAxis.labels.fontName = d.valueAxis.labels.fontName = "Helvetica"
    d.valueAxis.labels.fontSize = 7
    d.valueAxis.gridStrokeColor = colors.HexColor("#dddddd")
    d.valueAxis.visibleGrid = True
    d.bars[0].fillColor = colors.HexColor(farbe)
    d.bars[0].strokeColor = None
    d.barSpacing = 1
    zeichnung.add(d)
    return zeichnung


def erzeugen(jahr: int, z: aw.Zeitraum, kacheln, teile, stelle: str = "") -> bytes:
    untertitel = f"{z.von:%d.%m.%Y} bis {z.bis:%d.%m.%Y}"
    if stelle:
        untertitel += f" · Ausgabestelle {stelle}"
    doc = Pdf(f"Jahresbericht {jahr}", untertitel)
    doc.absatz("Alle Zahlen sind Summen ohne Personenbezug.", klein=True)
    doc.ueberschrift("Kennzahlen")
    doc.tabelle(["Kennzahl", "Wert", "Erläuterung"], [list(k) for k in kacheln],
                breiten=[0.3, 0.2, 0.5], rechts=(1,))  # fmt: skip
    breite = doc.seitengroesse[0] - 2 * RAND
    for i, teil in enumerate(teile):
        doc.ueberschrift(teil["titel"])
        if teil["text"]:
            doc.absatz(teil["text"], klein=True)
        if len(teil["kopf"]) == 2 and teil["zeilen"]:
            daten = [(str(n), _zahl(w)) for n, w in teil["zeilen"]]
            if all(w is not None for _, w in daten):
                zeichnung = saeulen(daten, breite, FARBEN[i % len(FARBEN)])
                if zeichnung is not None:
                    doc.element(zeichnung)
        rechts = tuple(range(1, len(teil["kopf"])))
        doc.tabelle(teil["kopf"], teil["zeilen"], rechts=rechts)
    return doc.erzeugen()
