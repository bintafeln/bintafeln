"""Kundenausweis als PDF: Karte im Scheckkartenformat auf A4 mit Schnittmarken (ADR 0021).

Der Barcode (Code 128) enthält nur die Kundennummer. Ein Scanner am Einlass, der als Tastatur
arbeitet, tippt sie ins Suchfeld.
"""

import io

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen.canvas import Canvas

from apps.core.models import TafelEinstellungen
from apps.kunden.models import Haushalt

BREITE, HOEHE = 85.6 * mm, 54 * mm  # ISO/IEC 7810 ID-1
RAND = 4 * mm


def _schnittmarken(c: Canvas, x, y) -> None:
    c.setStrokeColor(colors.grey)
    c.setLineWidth(0.3)
    for px in (x, x + BREITE):
        c.line(px, y - 8 * mm, px, y - 2 * mm)
        c.line(px, y + HOEHE + 2 * mm, px, y + HOEHE + 8 * mm)
    for py in (y, y + HOEHE):
        c.line(x - 8 * mm, py, x - 2 * mm, py)
        c.line(x + BREITE + 2 * mm, py, x + BREITE + 8 * mm, py)


def _logo(c: Canvas, tafel, x, y) -> float:
    """Zeichnet das Logo oben links; liefert die belegte Breite."""
    if not tafel.logo:
        return 0
    try:
        bild = ImageReader(tafel.logo.path)
    except (OSError, ValueError):
        return 0
    breite, hoehe = bild.getSize()
    h = 9 * mm
    b = h * breite / hoehe
    c.drawImage(bild, x, y - h, width=b, height=h, mask="auto")
    return b + 2 * mm


def _karte(c: Canvas, h: Haushalt, tafel, x, y) -> None:
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.5)
    c.roundRect(x, y, BREITE, HOEHE, 3 * mm)
    oben = y + HOEHE - RAND
    links = x + RAND + _logo(c, tafel, x + RAND, oben)
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(links, oben - 3.5 * mm, (tafel.name or "Tafel")[:40])
    c.setFont("Helvetica", 7)
    c.drawString(links, oben - 7.5 * mm, "Kundenausweis")

    c.setFont("Helvetica-Bold", 15)
    c.drawRightString(x + BREITE - RAND, oben - 5 * mm, h.kundennummer)

    hp = h.hauptperson
    zeilen = []
    if hp:
        zeilen.append(("Helvetica-Bold", 10, f"{hp.vorname} {hp.nachname}"[:42]))
    g = h.kundengruppe
    if g:
        termin = ", ".join(t for t in (g.wochentage, f"{g.uhrzeit:%H:%M} Uhr" if g.uhrzeit else "")
                           if t)  # fmt: skip
        zeilen.append(("Helvetica", 8, f"Gruppe {g.name}{f' · {termin}' if termin else ''}"[:55]))
    if h.ausweis_gueltig_bis:
        zeilen.append(("Helvetica", 8, f"Gültig bis {h.ausweis_gueltig_bis:%d.%m.%Y}"))
    zeile_y = oben - 15 * mm
    for schrift, groesse, inhalt in zeilen:
        c.setFont(schrift, groesse)
        c.drawString(x + RAND, zeile_y, inhalt)
        zeile_y -= groesse * 0.45 * mm

    code = Code128(h.kundennummer, barHeight=11 * mm, barWidth=0.33 * mm, humanReadable=False)
    breite = min(code.width, BREITE - 2 * RAND)
    if code.width > breite:  # sehr lange Kundennummer: schmaler zeichnen
        code = Code128(
            h.kundennummer, barHeight=11 * mm, barWidth=0.33 * mm * breite / code.width,
            humanReadable=False,
        )  # fmt: skip
    code.drawOn(c, x + (BREITE - code.width) / 2, y + RAND)


def ausweis_pdf(h: Haushalt) -> bytes:
    tafel = TafelEinstellungen.laden()
    puffer = io.BytesIO()
    c = Canvas(puffer, pagesize=A4)
    c.setTitle(f"Kundenausweis {h.kundennummer}")
    c.setAuthor(tafel.name or "bintafeln")
    seite_b, seite_h = A4
    x, y = (seite_b - BREITE) / 2, seite_h - 40 * mm - HOEHE
    _karte(c, h, tafel, x, y)
    _schnittmarken(c, x, y)
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawCentredString(
        seite_b / 2, y - 14 * mm, "Entlang der Marken ausschneiden. In 100 % Größe drucken."
    )
    c.showPage()
    c.save()
    return puffer.getvalue()
