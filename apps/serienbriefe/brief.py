"""Serienbriefe als ein PDF (ADR 0047), Anschrift im Fenster nach DIN 5008 Form B.

Jeder Brief beginnt auf einer neuen Seite; lange Briefe laufen auf Folgeseiten weiter.
"""

import io

from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from apps.core.models import TafelEinstellungen
from apps.core.pdf import TEXT, text

RAND_LINKS = 25 * mm
RAND_RECHTS = 20 * mm
OBEN = 20 * mm
TEXT_BEGINN = 98 * mm  # Betreff unterhalb von Anschriftfeld und Datum


class Briefkopf(Flowable):
    """Zeichnet Kopf, Rücksendeangabe, Anschrift und Datum an feste Stellen der ersten Seite."""

    def __init__(self, tafel, anschrift: list[str], datum: str):
        super().__init__()
        self.tafel, self.anschrift, self.datum = tafel, anschrift, datum
        self.width = self.height = 0

    def drawOn(self, canvas, x, y, _sW=0):  # noqa: N802 (Name aus ReportLab)
        breite, hoehe = A4
        canvas.saveState()
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawRightString(breite - RAND_RECHTS, hoehe - 20 * mm, self.tafel.name or "")
        canvas.setFont("Helvetica", 8.5)
        zeile = hoehe - 25 * mm
        for teil in (self.tafel.strasse, f"{self.tafel.plz} {self.tafel.ort}".strip(),
                     self.tafel.telefon, self.tafel.email):  # fmt: skip
            if teil:
                canvas.drawRightString(breite - RAND_RECHTS, zeile, teil)
                zeile -= 4 * mm
        # Anschriftfeld: 45 mm von oben, 20 mm von links, 85 x 45 mm
        absender = " · ".join(t for t in (self.tafel.name, self.tafel.anschrift) if t)
        canvas.setFont("Helvetica", 7)
        canvas.drawString(20 * mm + 5 * mm, hoehe - 50 * mm, absender[:95])
        canvas.setFont("Helvetica", 10.5)
        zeile = hoehe - 60 * mm
        for teil in self.anschrift[:6]:
            canvas.drawString(20 * mm + 5 * mm, zeile, teil)
            zeile -= 5 * mm
        canvas.drawRightString(breite - RAND_RECHTS, hoehe - 90 * mm, self.datum)
        # Faltmarken
        canvas.setLineWidth(0.3)
        for marke in (105 * mm, 210 * mm):
            canvas.line(5 * mm, hoehe - marke, 9 * mm, hoehe - marke)
        canvas.restoreState()

    def draw(self):  # pragma: no cover - drawOn zeichnet alles
        pass


def briefe_pdf(briefe) -> bytes:
    """``briefe`` = [(Anschriftzeilen, Betreff, Text)]."""
    tafel = TafelEinstellungen.laden()
    datum = f"{tafel.ort + ', ' if tafel.ort else ''}{timezone.localdate():%d.%m.%Y}"
    inhalt = []
    for nummer, (anschrift, betreff, brieftext) in enumerate(briefe):
        if nummer:
            inhalt.append(PageBreak())
        inhalt.append(Briefkopf(tafel, anschrift, datum))
        inhalt.append(Spacer(1, TEXT_BEGINN - OBEN))
        inhalt.append(Paragraph(f"<b>{text(betreff)}</b>", TEXT))
        inhalt.append(Spacer(1, 6 * mm))
        for absatz in [a.strip() for a in brieftext.replace("\r\n", "\n").split("\n\n")]:
            if absatz:
                inhalt.append(Paragraph(text(absatz), TEXT))
                inhalt.append(Spacer(1, 3 * mm))
    puffer = io.BytesIO()
    doc = SimpleDocTemplate(puffer, pagesize=A4, leftMargin=RAND_LINKS, rightMargin=RAND_RECHTS,
                            topMargin=OBEN, bottomMargin=20 * mm, title="Serienbrief",
                            author=tafel.name or "bintafeln", creator="bintafeln")  # fmt: skip
    doc.build(inhalt)
    return puffer.getvalue()
