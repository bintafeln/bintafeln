"""Serienbriefe als ein PDF (ADR 0047), Anschrift im Fenster nach DIN 5008 Form B.

Jeder Brief beginnt auf einer neuen Seite; lange Briefe laufen auf Folgeseiten weiter. Der Text
ist gestaltetes HTML aus der Vorlage (ADR 0088, Umsetzung in ``gestaltung.flowables``);
Briefkopf mit Logo und Fußzeile stellt die Vorlage ein.
"""

import io

from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Flowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer

from apps.core.models import TafelEinstellungen
from apps.core.pdf import text
from apps.serienbriefe import gestaltung

RAND_LINKS = 25 * mm
RAND_RECHTS = 20 * mm
OBEN = 20 * mm
UNTEN = 20 * mm
TEXT_BEGINN = 98 * mm  # Betreff unterhalb von Anschriftfeld und Datum
RAHMEN = 6  # Innenabstand des ReportLab-Rahmens (Punkte) links und rechts
BREITE = A4[0] - RAND_LINKS - RAND_RECHTS - 2 * RAHMEN  # nutzbare Textbreite
BETREFF = ParagraphStyle("betreff", parent=gestaltung.BRIEF, fontName="Helvetica-Bold")
FUSS = ParagraphStyle("fuss", parent=gestaltung.BRIEF, fontSize=7.5, leading=9.5, spaceAfter=0,
                      textColor="#555555")  # fmt: skip
LOGO_HOEHE, LOGO_BREITE = 18 * mm, 55 * mm


def _logo(tafel):
    """Logo der Tafel als Bild für ReportLab, sonst None (fehlt, kaputt, nicht lesbar)."""
    if not tafel.logo:
        return None
    try:
        return ImageReader(tafel.logo.path)
    except (OSError, ValueError):
        return None


class Briefkopf(Flowable):
    """Zeichnet Kopf, Rücksendeangabe, Anschrift und Datum an feste Stellen der ersten Seite."""

    def __init__(self, tafel, anschrift: list[str], datum: str, mit_kopf=True, logo=None):
        super().__init__()
        self.tafel, self.anschrift, self.datum = tafel, anschrift, datum
        self.mit_kopf, self.logo = mit_kopf, logo
        self.width = self.height = 0

    def kopf(self, canvas, breite, hoehe):
        """Logo (falls vorhanden) und Name, Anschrift, Kontakt der Tafel oben rechts."""
        oben = hoehe - 20 * mm
        if self.logo:
            b, h = self.logo.getSize()
            faktor = min(LOGO_BREITE / b, LOGO_HOEHE / h)
            canvas.drawImage(self.logo, breite - RAND_RECHTS - b * faktor,
                             hoehe - 10 * mm - h * faktor, width=b * faktor, height=h * faktor,
                             mask="auto")  # fmt: skip
            oben = hoehe - 10 * mm - h * faktor - 5 * mm
        canvas.setFont("Helvetica-Bold", 11)
        canvas.drawRightString(breite - RAND_RECHTS, oben, self.tafel.name or "")
        canvas.setFont("Helvetica", 8.5)
        zeile = oben - 5 * mm
        for teil in (self.tafel.strasse, f"{self.tafel.plz} {self.tafel.ort}".strip(),
                     self.tafel.telefon, self.tafel.email):  # fmt: skip
            if teil:
                canvas.drawRightString(breite - RAND_RECHTS, zeile, teil)
                zeile -= 4 * mm

    def drawOn(self, canvas, x, y, _sW=0):  # noqa: N802 (Name aus ReportLab)
        breite, hoehe = A4
        canvas.saveState()
        if self.mit_kopf:
            self.kopf(canvas, breite, hoehe)
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


class _Fusszeile:
    """Zeichnet die Fußzeile der Vorlage unten auf jede Seite."""

    def __init__(self, html: str):
        self.teile = gestaltung.flowables(html, BREITE, FUSS) if html else []
        self.hoehe = sum(t.wrap(BREITE, A4[1])[1] for t in self.teile)

    def __call__(self, canvas, doc):
        if not self.teile:
            return
        canvas.saveState()
        y = UNTEN - 8 * mm + self.hoehe
        canvas.setLineWidth(0.3)
        canvas.setStrokeColor("#999999")
        canvas.line(RAND_LINKS + RAHMEN, y + 2 * mm, A4[0] - RAND_RECHTS - RAHMEN, y + 2 * mm)
        for teil in self.teile:
            _, h = teil.wrap(BREITE, A4[1])
            y -= h
            teil.drawOn(canvas, RAND_LINKS + RAHMEN, y)
        canvas.restoreState()


def briefe_pdf(briefe, vorlage=None) -> bytes:
    """``briefe`` = [(Anschriftzeilen, Betreff, Text)]; der Text ist HTML mit eingesetzten Werten
    (siehe ``gestaltung.einsetzen``) oder älterer reiner Text. ``vorlage`` stellt Briefkopf und
    Fußzeile ein (ohne Vorlage: Briefkopf ohne Fußzeile)."""
    tafel = TafelEinstellungen.laden()
    datum = f"{tafel.ort + ', ' if tafel.ort else ''}{timezone.localdate():%d.%m.%Y}"
    mit_kopf = vorlage.briefkopf if vorlage is not None else True
    logo = _logo(tafel) if mit_kopf else None
    fuss = _Fusszeile(vorlage.fusszeile if vorlage is not None else "")
    inhalt = []
    for nummer, (anschrift, betreff, brieftext) in enumerate(briefe):
        if nummer:
            inhalt.append(PageBreak())
        inhalt.append(Briefkopf(tafel, anschrift, datum, mit_kopf, logo))
        inhalt.append(Spacer(1, TEXT_BEGINN - OBEN))
        inhalt.append(Paragraph(text(betreff), BETREFF))
        inhalt.append(Spacer(1, 3 * mm))
        inhalt.extend(gestaltung.flowables(brieftext, BREITE))
    puffer = io.BytesIO()
    unten = UNTEN + fuss.hoehe if fuss.teile else UNTEN
    doc = SimpleDocTemplate(puffer, pagesize=A4, leftMargin=RAND_LINKS, rightMargin=RAND_RECHTS,
                            topMargin=OBEN, bottomMargin=unten, title="Serienbrief",
                            author=tafel.name or "bintafeln", creator="bintafeln")  # fmt: skip
    doc.build(inhalt, onFirstPage=fuss, onLaterPages=fuss)
    return puffer.getvalue()
