"""Erzeugte PDFs: einheitlicher Kopf mit Tafel, Fuß mit Seitenzahl (ADR 0021).

Gedruckt wird in bintafeln nur über PDFs. Ein Dokument baut man mit ``Pdf``::

    doc = Pdf("Kassenabschluss", "Mi 21.10.2026")
    doc.ueberschrift("Summen")
    doc.tabelle(["Was", "Betrag"], [["Bar", "12,00 €"]])
    return pdf_antwort(doc.erzeugen(), "kassenabschluss-2026-10-21.pdf")
"""

import io
from html import escape

from django.http import HttpResponse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.models import TafelEinstellungen

RAND = 18 * mm
_STILE = getSampleStyleSheet()
TEXT = ParagraphStyle(
    "text", parent=_STILE["Normal"], fontName="Helvetica", fontSize=9.5, leading=12.5
)
KLEIN = ParagraphStyle("klein", parent=TEXT, fontSize=8, leading=10, textColor=colors.grey)
TITEL = ParagraphStyle(
    "titel", parent=TEXT, fontName="Helvetica-Bold", fontSize=16, leading=20, spaceAfter=2 * mm
)
UEBERSCHRIFT = ParagraphStyle(
    "ueberschrift",
    parent=TEXT,
    fontName="Helvetica-Bold",
    fontSize=11.5,
    leading=15,
    spaceBefore=5 * mm,
    spaceAfter=2 * mm,
)
ZELLE = ParagraphStyle("zelle", parent=TEXT, fontSize=8.5, leading=10.5)
ZELLE_KOPF = ParagraphStyle("zelle_kopf", parent=ZELLE, fontName="Helvetica-Bold")


def text(wert) -> str:
    """Wert als sicherer Absatztext (ReportLab liest eine Untermenge von HTML)."""
    if wert is None or wert == "":
        return "–"
    return escape(str(wert)).replace("\n", "<br/>")


class Pdf:
    def __init__(self, titel: str, untertitel: str = "", seitengroesse=A4):
        self.titel, self.untertitel, self.seitengroesse = titel, untertitel, seitengroesse
        self.tafel = TafelEinstellungen.laden()
        self.erstellt = timezone.localtime()
        self.inhalt: list[Flowable] = [Paragraph(text(titel), TITEL)]
        if untertitel:
            self.inhalt.append(Paragraph(text(untertitel), TEXT))

    # --- Bausteine ---

    def ueberschrift(self, titel: str) -> None:
        self.inhalt.append(Paragraph(text(titel), UEBERSCHRIFT))

    def absatz(self, inhalt: str, klein=False) -> None:
        self.inhalt.append(Paragraph(text(inhalt), KLEIN if klein else TEXT))

    def abstand(self, hoehe=4 * mm) -> None:
        self.inhalt.append(Spacer(1, hoehe))

    def element(self, flowable: Flowable) -> None:
        self.inhalt.append(flowable)

    def angaben(self, paare) -> None:
        """Bezeichnung und Wert untereinander, zweispaltig."""
        zeilen = [[Paragraph(text(k), ZELLE_KOPF), Paragraph(text(v), ZELLE)] for k, v in paare]
        if not zeilen:
            return self.absatz("Keine Angaben.")
        breite = self.seitengroesse[0] - 2 * RAND
        tabelle = Table(zeilen, colWidths=[0.32 * breite, 0.68 * breite], hAlign="LEFT")
        tabelle.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                                     ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]))  # fmt: skip
        self.inhalt.append(tabelle)

    def tabelle(self, kopf, zeilen, breiten=None, rechts=(), summe=False) -> None:
        """Tabelle mit Kopfzeile; ``rechts`` = Spaltennummern rechtsbündig (Beträge)."""
        if not zeilen:
            return self.absatz("Keine Einträge.")
        daten = [[Paragraph(text(k), ZELLE_KOPF) for k in kopf]]
        for zeile in zeilen:
            daten.append([Paragraph(text(w), ZELLE) for w in zeile])
        breite = self.seitengroesse[0] - 2 * RAND
        spalten = [b * breite for b in breiten] if breiten else None
        tabelle = Table(daten, colWidths=spalten, repeatRows=1, hAlign="LEFT")
        stil = [
            ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
            ("LINEBELOW", (0, 1), (-1, -1), 0.25, colors.lightgrey),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ]
        for spalte in rechts:
            for zeile in daten:
                zeile[spalte].style = ParagraphStyle("r", parent=zeile[spalte].style, alignment=2)
        if summe:
            stil.append(("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black))
            for zelle in daten[-1]:
                zelle.style = ParagraphStyle("s", parent=zelle.style, fontName="Helvetica-Bold")
        tabelle.setStyle(TableStyle(stil))
        self.inhalt.append(tabelle)

    def unterschriften(self, felder) -> None:
        """Leere Linien zum Ausfüllen von Hand, darunter die Bezeichnung."""
        luecke = 10 * mm
        breite = (self.seitengroesse[0] - 2 * RAND - luecke * (len(felder) - 1)) / len(felder)
        spalten = [i for i in range(len(felder) * 2 - 1)]
        unten = [Paragraph(text(felder[i // 2]), KLEIN) if i % 2 == 0 else "" for i in spalten]
        tabelle = Table(
            [["" for _ in spalten], unten],
            colWidths=[breite if i % 2 == 0 else luecke for i in spalten],
            rowHeights=[12 * mm, None],
            hAlign="LEFT",
        )
        tabelle.setStyle(
            TableStyle([("LINEBELOW", (i, 0), (i, 0), 0.5, colors.black) for i in spalten[::2]])
        )
        self.inhalt.append(tabelle)

    # --- Ausgabe ---

    def _seite(self, leinwand, doc) -> None:
        breite, hoehe = self.seitengroesse
        leinwand.saveState()
        leinwand.setFont("Helvetica-Bold", 9)
        leinwand.drawString(RAND, hoehe - 11 * mm, self.tafel.name or "bintafeln")
        leinwand.setFont("Helvetica", 8)
        if self.tafel.anschrift:
            leinwand.drawString(RAND, hoehe - 14.5 * mm, self.tafel.anschrift)
        leinwand.drawRightString(breite - RAND, hoehe - 11 * mm, self.titel)
        leinwand.setStrokeColor(colors.lightgrey)
        leinwand.line(RAND, hoehe - 16.5 * mm, breite - RAND, hoehe - 16.5 * mm)
        leinwand.setFillColor(colors.grey)
        leinwand.drawString(RAND, 10 * mm, f"Erstellt am {self.erstellt:%d.%m.%Y um %H:%M} Uhr")
        leinwand.drawRightString(breite - RAND, 10 * mm, f"Seite {doc.page}")
        leinwand.restoreState()

    def erzeugen(self) -> bytes:
        puffer = io.BytesIO()
        doc = SimpleDocTemplate(
            puffer,
            pagesize=self.seitengroesse,
            leftMargin=RAND,
            rightMargin=RAND,
            topMargin=24 * mm,
            bottomMargin=18 * mm,
            title=self.titel,
            author=self.tafel.name or "bintafeln",
            creator="bintafeln",
        )
        doc.build(self.inhalt, onFirstPage=self._seite, onLaterPages=self._seite)
        return puffer.getvalue()


def pdf_antwort(inhalt: bytes, dateiname: str) -> HttpResponse:
    """PDF zum Ansehen im Browser; nie zwischenspeichern (oft Personendaten)."""
    antwort = HttpResponse(inhalt, content_type="application/pdf")
    antwort["Content-Disposition"] = f'inline; filename="{dateiname}"'
    add_never_cache_headers(antwort)
    return antwort
