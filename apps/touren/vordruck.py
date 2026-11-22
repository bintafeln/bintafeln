"""Der Lieferschein als PDF im Aussehen des Vordrucks, den die Tafeln kennen (ADR 0149):
vereinfachtes Dokumentationsverfahren nach der Verordnung (EG) Nr. 178/2002.

Gezeichnet mit festen Maßen wie die Zuwendungsbestätigung (``apps/spenden/vordruck.py``), nicht
über den ``Pdf``-Rahmen: oben das Logo der Tafel, darunter Spender und Empfänger in einem Kasten,
rechts Datum und Nummer, die Tabelle der Warengruppen mit vier Spalten und rechts unten die
Unterschrift. Keine Kopf- und keine Fußzeile.
"""

import io

from PIL import Image as PilImage
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph

from apps.core.pdf import text

BREITE, HOEHE = A4
LINKS, RECHTS = 57, 539  # Punkte vom linken Blattrand
SPALTEN = [LINKS, 177, 322, 442, RECHTS]  # Tabelle: Menge, Produkt, Bemerkungen, Abgabe an
KOPF = ["Kg / Liter / Kiste / Palette", "Produktbezeichnung", "Bemerkungen", "ggf. Abgabe an:"]
SCHRIFT, FETT = "Times-Roman", "Times-Bold"
NORMAL = ParagraphStyle("schein", fontName=SCHRIFT, fontSize=10, leading=13)
MITTE = ParagraphStyle("schein_mitte", parent=NORMAL, alignment=TA_CENTER)
MITTE_FETT = ParagraphStyle("schein_kopf", parent=MITTE, fontName=FETT)
KLEIN_MITTE = ParagraphStyle("schein_klein", parent=MITTE, fontSize=8.5, leading=10.5)


def _logo(tafel):
    """Das Logo der Tafel als Bild fürs PDF – oder ``None``, wenn keins hinterlegt ist (dann steht
    dort der Name der Tafel) oder es sich nicht lesen lässt."""
    if not tafel.logo:
        return None
    try:
        with tafel.logo.open("rb") as datei:
            bild = PilImage.open(io.BytesIO(datei.read()))
            bild.load()
    except (OSError, ValueError):
        return None
    puffer = io.BytesIO()
    bild.convert("RGBA").save(puffer, format="PNG")  # auch WebP; Durchsichtiges bleibt
    puffer.seek(0)
    return ImageReader(puffer)


class _Blatt:
    """Zeichnet mit Abständen vom oberen Blattrand (wie man den Vordruck ausmisst)."""

    def __init__(self, titel: str, autor: str):
        self.puffer = io.BytesIO()
        self.c = canvas.Canvas(self.puffer, pagesize=A4)
        self.c.setTitle(titel)
        self.c.setAuthor(autor)
        self.c.setCreator("bintafeln")
        self.c.setLineWidth(0.8)

    def y(self, von_oben: float) -> float:
        return HOEHE - von_oben

    def zeile(self, x, von_oben, wert, schrift=SCHRIFT, groesse=10):
        self.c.setFont(schrift, groesse)
        self.c.drawString(x, self.y(von_oben), text(wert))

    def kasten(self, x, oben, bis_x, unten):
        self.c.rect(x, self.y(unten), bis_x - x, unten - oben)

    def linie(self, x, von_oben, bis_x, bis_oben=None):
        self.c.line(x, self.y(von_oben), bis_x, self.y(von_oben if bis_oben is None else bis_oben))

    def absatz(self, html: str, x, oben, breite, hoehe, stil=NORMAL, mittig=True):
        """Text in ein Feld setzen (umbrochen); mittig = senkrecht in der Mitte des Feldes."""
        p = Paragraph(html, stil)
        _, h = p.wrap(breite, hoehe)
        versatz = max((hoehe - h) / 2, 0) if mittig else 2
        p.drawOn(self.c, x, self.y(oben + versatz) - h)

    def fertig(self) -> bytes:
        self.c.showPage()
        self.c.save()
        return self.puffer.getvalue()


def zeichnen(*, tafel, nummer, datum, station_name, station_anschrift, zeilen, anmerkung,
             unterschrift: bytes, unterschrieben_von: str) -> bytes:  # fmt: skip
    """``zeilen``: [(Mengentext oder "", Warengruppe)] in der Reihenfolge der Tabelle."""
    b = _Blatt(f"Lieferschein Nr. {nummer}", tafel.name or "bintafeln")
    # --- Kopf: Logo der Tafel (ersatzweise ihr Name) ------------------------------------------
    logo = _logo(tafel)
    if logo is not None:
        breite, hoehe = logo.getSize()
        faktor = min(200 / breite, 55 / hoehe)
        b.c.drawImage(logo, LINKS, b.y(62), width=breite * faktor, height=hoehe * faktor,
                      mask="auto")  # fmt: skip
    else:
        b.zeile(LINKS, 48, tafel.name or "", FETT, 20)
    b.zeile(LINKS, 83, "Vereinfachtes Dokumentationsverfahren | Verordnung (EG) Nr. 178/2002")
    b.zeile(LINKS, 141, "Lieferschein", FETT, 25)
    b.zeile(LINKS, 189, "für die Tafeln in Deutschland", groesse=12.5)
    # --- Spender/in und Empfänger/in, rechts Datum und Nummer ---------------------------------
    b.kasten(LINKS, 212, 298, 280)
    b.linie(LINKS, 246, 298)
    spender = ", ".join(t for t in (station_name, station_anschrift) if t)
    empfaenger = ", ".join(t for t in (tafel.name, tafel.anschrift) if t)
    b.absatz(f"<b>Spender/in:</b> {text(spender)}", LINKS + 3, 212, 235, 34)
    b.absatz(f"<b>Empfänger/in:</b> {text(empfaenger)}", LINKS + 3, 246, 235, 34)
    b.kasten(418, 212, RECHTS, 280)
    b.linie(418, 246, RECHTS)
    b.absatz(f"<b>Datum:</b> {datum:%d.%m.%Y}", 421, 212, 115, 34)
    b.absatz(f"<b>Nr:</b> {nummer}", 421, 246, 115, 34)
    # --- Tabelle -------------------------------------------------------------------------------
    oben, kopf_hoehe = 303, 26
    zeilenhoehe = min(26, max(14, 286 / max(len(zeilen), 1)))  # viele Warengruppen: enger
    unten = oben + kopf_hoehe + zeilenhoehe * len(zeilen)
    b.kasten(LINKS, oben, RECHTS, unten)
    for x in SPALTEN[1:-1]:
        b.linie(x, oben, x, unten)
    for i, titel in enumerate(KOPF):
        b.absatz(titel, SPALTEN[i] + 2, oben, SPALTEN[i + 1] - SPALTEN[i] - 4, kopf_hoehe,
                 MITTE_FETT)  # fmt: skip
    for nr, (menge, gruppe) in enumerate(zeilen):
        y = oben + kopf_hoehe + nr * zeilenhoehe
        b.linie(LINKS, y, RECHTS)
        b.absatz(text(menge or "-"), SPALTEN[0] + 2, y, SPALTEN[1] - SPALTEN[0] - 4, zeilenhoehe,
                 MITTE)  # fmt: skip
        b.absatz(text(gruppe), SPALTEN[1] + 2, y, SPALTEN[2] - SPALTEN[1] - 4, zeilenhoehe, MITTE)
    # --- Bemerkung (links) und Unterschrift (rechts) unter der Tabelle ------------------------
    if anmerkung:
        b.absatz(f"<b>Bemerkungen:</b> {text(anmerkung)}", LINKS, unten + 12, 265, 110,
                 mittig=False)  # fmt: skip
    strich = unten + 74
    bild = ImageReader(io.BytesIO(unterschrift))
    breite, hoehe = bild.getSize()
    faktor = min(180 / breite, 52 / hoehe)
    b.c.drawImage(bild, 340 + (199 - breite * faktor) / 2, b.y(strich) + 2,
                  width=breite * faktor, height=hoehe * faktor, mask="auto")  # fmt: skip
    b.linie(340, strich, RECHTS)
    b.absatz("Unterschrift Empfänger/in", 340, strich + 6, 199, 14, MITTE, mittig=False)
    if unterschrieben_von:
        b.absatz(text(unterschrieben_von), 340, strich + 20, 199, 12, KLEIN_MITTE, mittig=False)
    return b.fertig()
