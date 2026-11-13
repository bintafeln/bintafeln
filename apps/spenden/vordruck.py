"""Zuwendungsbestätigung als Vordruck nach den amtlichen Mustern (ADR 0136).

Gezeichnet wie der bekannte Vordruck: gerahmte Kästen für Aussteller, Zuwendenden und Betrag,
Ankreuzkästchen für die Grundlage der Steuerbegünstigung, Linie für Ort, Datum und Unterschrift,
darunter der Hinweis. Ohne den Kopf und Fuß der übrigen bintafeln-PDFs (``apps.core.pdf``), damit
die Bestätigung genauso aussieht wie die Vordrucke, die Spender und Finanzämter kennen. Unten
rechts steht klein die Nummer der Bestätigung.

Maße in Punkt, gemessen von oben (``t``); gezeichnet wird mit ReportLab von unten.
"""

import io
from decimal import ROUND_HALF_UP, Decimal

from reportlab.lib import colors
from reportlab.lib.enums import TA_JUSTIFY
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph

from apps.core.pdf import text

BREITE, HOEHE = A4
LINKS, RECHTS = 80.5, 539.5  # Kästen
TX, TR = 86.5, 534.5  # Text in und außerhalb der Kästen
EINRUECKEN = 101.5  # Text neben einem Ankreuzkästchen
KREUZ = 6.5  # Kantenlänge eines Ankreuzkästchens

_GRUND = ParagraphStyle("vordruck", fontName="Helvetica", fontSize=6.9, leading=9)
TEXT = _GRUND
FETT = ParagraphStyle("vordruck_fett", parent=_GRUND, fontName="Helvetica-Bold")
BLOCK = ParagraphStyle("vordruck_block", parent=_GRUND, alignment=TA_JUSTIFY)
WERT = ParagraphStyle("vordruck_wert", parent=_GRUND, fontSize=8.5, leading=10.5)
TITEL = ParagraphStyle("vordruck_titel", parent=_GRUND, fontName="Helvetica-Bold", fontSize=8,
                       leading=10)  # fmt: skip
TABELLE = ParagraphStyle("vordruck_tabelle", parent=_GRUND, fontSize=6.3, leading=7.5)
NEBEN_KREUZ = ParagraphStyle("vordruck_kreuz", parent=_GRUND, firstLineIndent=10.5)

ZIFFERN = ["null", "eins", "zwei", "drei", "vier", "fünf", "sechs", "sieben", "acht", "neun"]

HINWEIS_1 = (
    "Wer vorsätzlich oder grob fahrlässig eine unrichtige Zuwendungsbestätigung erstellt oder "
    "veranlasst, dass Zuwendungen nicht zu den in der Zuwendungsbestätigung angegebenen "
    "steuerbegünstigten Zwecken verwendet werden, haftet für die entgangene Steuer (§ 10b Abs. 4 "
    "EStG, § 9 Abs. 3 KStG, § 9 Nr. 5 GewStG)."
)
HINWEIS_2 = (
    "Diese Bestätigung wird nicht als Nachweis für die steuerliche Berücksichtigung der Zuwendung "
    "anerkannt, wenn das Datum des Freistellungsbescheides länger als 5 Jahre bzw. <b>das Datum "
    "der Feststellung der Einhaltung der satzungsmäßigen Voraussetzungen nach § 60a Abs. 1 AO "
    "länger als 3 Jahre seit Ausstellung des Bescheides zurückliegt (§ 63 Abs. 5 AO).</b>"
)
HERKUNFT = {
    "betrieb": "Die Sachzuwendung stammt nach den Angaben des Zuwendenden aus dem "
    "Betriebsvermögen. Die Zuwendung wurde nach dem Wert der Entnahme (ggf. mit dem niedrigeren "
    "gemeinen Wert) und nach der Umsatzsteuer, die auf die Entnahme entfällt, bewertet.",
    "privat": "Die Sachzuwendung stammt nach den Angaben des Zuwendenden aus dem Privatvermögen.",
    "unbekannt": "Der Zuwendende hat trotz Aufforderung keine Angaben zur Herkunft der "
    "Sachzuwendung gemacht.",
}


def ziffern(betrag) -> str:
    """Betrag ziffernweise in Buchstaben wie im Vordruck:
    500 -> „fünf-null-null-komma-null-null“."""
    betrag = Decimal(betrag).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    euro, cent = f"{betrag:.2f}".split(".")
    return "-".join([ZIFFERN[int(z)] for z in euro] + ["komma"] + [ZIFFERN[int(z)] for z in cent])


def betrag(wert) -> str:
    """Wie im Vordruck ohne Euro-Zeichen: 2000 -> „2.000,00“."""
    return f"{Decimal(wert):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def datum(d) -> str:
    return f"{d:%d.%m.%Y}" if d else ""


def zeile(*teile) -> str:
    """Anschrift in einer Zeile, Teile mit „ | “ getrennt."""
    return " | ".join(t.strip() for teil in teile for t in str(teil or "").split(",") if t.strip())


class Vordruck:
    """Eine Zuwendungsbestätigung (oder mehrere hintereinander) als PDF."""

    def __init__(self, titel: str, autor: str):
        self.puffer = io.BytesIO()
        self.c = Canvas(self.puffer, pagesize=A4)
        self.c.setTitle(titel)
        self.c.setAuthor(autor)
        self.c.setCreator("bintafeln")
        self.nummer = ""
        self.storniert = ""

    # --- Bausteine ---

    def absatz(self, inhalt: str, t: float, stil=TEXT, x=TX, rechts=TR) -> float:
        """Absatz (ReportLab-HTML, Werte schon mit ``text()`` maskiert) mit Oberkante bei ``t``;
        Ergebnis: Unterkante."""
        p = Paragraph(inhalt, stil)
        _, h = p.wrapOn(self.c, rechts - x, HOEHE)
        p.drawOn(self.c, x, HOEHE - t - h)
        return t + h

    def kasten(self, oben: float, unten: float, links=LINKS, rechts=RECHTS) -> None:
        self.c.setLineWidth(0.6)
        self.c.rect(links, HOEHE - unten, rechts - links, unten - oben)

    def kreuz(self, x: float, t: float, an: bool) -> None:
        """Ankreuzkästchen, Oberkante bei ``t`` (auf Höhe der ersten Textzeile daneben)."""
        y = HOEHE - t - 1 - KREUZ
        self.c.setLineWidth(0.6)
        self.c.rect(x, y, KREUZ, KREUZ)
        if an:
            self.c.line(x + 1, y + 1, x + KREUZ - 1, y + KREUZ - 1)
            self.c.line(x + 1, y + KREUZ - 1, x + KREUZ - 1, y + 1)

    def fett_in_luecke(self, wert: str, x: float, bis: float, t: float) -> None:
        """Wert fett in eine Lücke des Vordrucks (z. B. hinter „StNr.“), notfalls kleiner."""
        groesse = 6.9
        while groesse > 4.5 and stringWidth(wert, "Helvetica-Bold", groesse) > bis - x - 3:
            groesse -= 0.25
        self.c.setFont("Helvetica-Bold", groesse)
        self.c.drawString(x, HOEHE - t - 6.5, wert)

    def wort(self, inhalt: str, x: float, t: float, fett=False) -> None:
        self.c.setFont("Helvetica-Bold" if fett else "Helvetica", 6.9)
        self.c.drawString(x, HOEHE - t - 6.5, inhalt)

    def feldkasten(self, oben: float, beschriftung: str, wert_zeilen, mindestens=37) -> float:
        """Kasten mit kleiner Beschriftung und Wert darunter; Ergebnis: Unterkante."""
        t = self.absatz(text(beschriftung), oben + 0.1) - 2.5
        for z in wert_zeilen:
            t = self.absatz(text(z), t, WERT)
        unten = max(oben + mindestens, t + 4)
        self.kasten(oben, unten)
        return unten

    def betragskasten(self, oben: float, felder, mindestens=37) -> float:
        """Drei gleich breite Felder nebeneinander (Betrag in Ziffern | in Buchstaben | Tag)."""
        breite = (RECHTS - LINKS) / 3
        unten = oben + mindestens
        for i, (beschriftung, wert) in enumerate(felder):
            x = LINKS + i * breite
            t = self.absatz(text(beschriftung), oben + 0.1, x=x + 3, rechts=x + breite - 3)
            t = self.absatz(text(wert), t - 1.5, WERT, x=x + 3, rechts=x + breite - 3)
            unten = max(unten, t + 4)
        for i in range(3):
            x = LINKS + i * breite
            self.kasten(oben, unten, x, x + breite)
        return unten

    def seite_fertig(self) -> None:
        self.c.setFont("Helvetica", 6.5)
        self.c.setFillColor(colors.grey)
        if self.nummer:
            self.c.drawRightString(TR, 22, f"Nr. {self.nummer}")
        if self.storniert:
            self.c.setFillColor(colors.red)
            self.c.setFont("Helvetica-Bold", 10)
            self.c.drawString(TX, HOEHE - 40, self.storniert)
            self.c.saveState()
            self.c.setFillColor(colors.Color(1, 0, 0, alpha=0.18))
            self.c.setFont("Helvetica-Bold", 90)
            self.c.translate(BREITE / 2, HOEHE / 2)
            self.c.rotate(50)
            self.c.drawCentredString(0, 0, "STORNIERT")
            self.c.restoreState()
        self.c.setFillColor(colors.black)
        self.c.showPage()

    def erzeugen(self) -> bytes:
        self.c.save()
        return self.puffer.getvalue()


# --- Teile der Bestätigung ------------------------------------------------------------------------


def grundlage(v: Vordruck, t: float, e) -> float:
    """Die beiden Ankreuzfelder zur Steuerbegünstigung; angekreuzt und ausgefüllt ist das, was in
    den Einstellungen gewählt ist. Ergebnis: Oberkante des Kastens zur Verwendung."""
    freistellung = e.grundlage != e.Grundlage.FESTSTELLUNG
    v.kreuz(TX, t, freistellung)
    v.absatz("Wir sind wegen Förderung (Angabe des begünstigten Zwecks / der begünstigten Zwecke)",
             t, x=EINRUECKEN)  # fmt: skip
    if freistellung:
        v.absatz(f"<b>{text(e.zwecke)}</b>", t + 10, x=EINRUECKEN)
        v.absatz(f"<b>{text(e.finanzamt)}</b>", t + 39.5, x=EINRUECKEN)
    t += 29.8
    v.absatz("nach dem Freistellungsbescheid bzw. nach der Anlage zum Körperschaftsteuerbescheid "
             "des Finanzamtes", t, x=EINRUECKEN)  # fmt: skip
    t += 20
    v.wort("StNr.", EINRUECKEN, t)
    v.wort(", vom", 184, t)
    v.wort("für den letzten Veranlagungszeitraum", 256.5, t)
    v.wort("nach § 5 Abs. 1 Nr. 9 des", 436, t)
    if freistellung:
        v.fett_in_luecke(e.steuernummer, 122.5, 184, t)
        v.fett_in_luecke(datum(e.bescheid_vom), 205, 256.5, t)
        v.fett_in_luecke(e.veranlagungszeitraum, 375, 436, t)
    v.absatz("Körperschaftsteuergesetzes von der Körperschaftsteuer und nach § 3 Nr. 6 des "
             "Gewerbesteuergesetzes von der Gewerbesteuer befreit.", t + 8.5,
             x=EINRUECKEN)  # fmt: skip

    t += 34
    v.kreuz(TX, t, not freistellung)
    v.absatz("Die Einhaltung der satzungsmäßigen Voraussetzungen nach den §§ 51, 59, 60 und 61 AO "
             "wurde vom Finanzamt", t, x=EINRUECKEN)  # fmt: skip
    if not freistellung:
        v.absatz(f"<b>{text(e.finanzamt)}</b>", t + 8.5, x=EINRUECKEN)
    t += 16.5
    v.wort("StNr.", 100, t)
    v.wort("mit Bescheid vom", 185, t)
    v.wort("nach § 60a AO gesondert festgestellt. Wir fördern nach unserer Satzung", 302, t)
    if not freistellung:
        v.fett_in_luecke(e.steuernummer, 122.5, 185, t)
        v.fett_in_luecke(datum(e.bescheid_vom), 252, 302, t)
    t = v.absatz("(Angabe des begünstigten Zwecks / der begünstigten Zwecke)", t + 8.5, x=100)
    if not freistellung:
        t = v.absatz(f"<b>{text(e.zwecke)}</b>", t + 0.1, x=EINRUECKEN)
    else:
        t += 9
    return t + 22.4


def verwendung(v: Vordruck, oben: float, e, mitgliedsbeitrag_satz: bool, luft=0.0) -> float:
    """Kasten „Es wird bestätigt, dass die Zuwendung nur zur Förderung … verwendet wird“;
    ``luft`` macht ihn höher (Einzelbestätigung wie im Vordruck)."""
    t = v.absatz("Es wird bestätigt, dass die Zuwendung nur zur Förderung (Angabe des begünstigten "
                 "Zwecks / der begünstigten Zwecke)", oben + 0.5 + luft / 2)  # fmt: skip
    t = v.absatz(text(e.zwecke), t + luft / 6)
    t = v.absatz("verwendet wird.", max(t + 18, oben + 37 + luft * 2 / 3))
    if mitgliedsbeitrag_satz:
        t = v.absatz("<b>Nur für steuerbegünstigte Einrichtungen, bei denen die Mitgliedsbeiträge "
                     "steuerlich nicht abziehbar sind:</b>", t + 9.5)  # fmt: skip
        v.kreuz(TX, t, not e.mitgliedsbeitraege_abziehbar)
        t = v.absatz("Es wird bestätigt, dass es sich nicht um einen "
                     "Mitgliedsbeitrag handelt, dessen Abzug nach § 10b Abs. 1 des "
                     "Einkommensteuergesetzes ausgeschlossen ist", t, NEBEN_KREUZ)  # fmt: skip
    unten = max(t - 1 + luft / 2, (oben + 83 if mitgliedsbeitrag_satz else oben + 50) + luft)
    v.kasten(oben, unten)
    return unten


STEMPEL_MITTE = 470  # waagerecht, rechts neben der Unterschrift
STEMPEL_GROESSE = (95, 62)  # höchstens so breit und hoch (Punkt), Seitenverhältnis bleibt
STEMPEL_DREHUNG = 8  # Grad gegen den Uhrzeigersinn – wie von Hand gestempelt


def stempel(v: Vordruck, linie: float, bild: bytes) -> None:
    """Der Stempel der Tafel, leicht schräg, rechts neben der Unterschrift über der Linie."""
    leser = ImageReader(io.BytesIO(bild))
    b, h = leser.getSize()
    faktor = min(STEMPEL_GROESSE[0] / b, STEMPEL_GROESSE[1] / h)
    b, h = b * faktor, h * faktor
    v.c.saveState()
    v.c.translate(STEMPEL_MITTE, HOEHE - linie + 4 + STEMPEL_GROESSE[1] / 2)
    v.c.rotate(STEMPEL_DREHUNG)
    v.c.drawImage(leser, -b / 2, -h / 2, b, h, mask="auto")
    v.c.restoreState()


def unterschrift(v: Vordruck, linie: float, ort_datum: str, bild: bytes | None,
                 stempel_bild: bytes | None = None) -> None:  # fmt: skip
    """Ort und Datum links, darüber rechts die eingescannte Unterschrift, daneben der Stempel,
    darunter die Linie. Beide Bilder haben einen durchsichtigen Hintergrund."""
    if stempel_bild:
        stempel(v, linie, stempel_bild)
    if bild:
        leser = ImageReader(io.BytesIO(bild))
        b, h = leser.getSize()
        faktor = min(160 / b, 45 / h)
        v.c.drawImage(leser, 340 - (40 if stempel_bild else 0), HOEHE - linie + 2, b * faktor,
                      h * faktor, mask="auto")  # fmt: skip
    v.c.setFont("Helvetica", 8.5)
    v.c.drawString(88, HOEHE - linie + 4, ort_datum)
    v.c.setLineWidth(0.6)
    v.c.line(86, HOEHE - linie, TR, HOEHE - linie)
    v.absatz("(Ort, Datum und Unterschrift des Zuwendungsempfängers)", linie + 2)


def hinweis(v: Vordruck, t: float, e) -> None:
    t = v.absatz("<b>Hinweis:</b>", t)
    t = v.absatz(HINWEIS_1, t + 0.5, BLOCK)
    t = v.absatz(HINWEIS_2, t + 9, BLOCK)
    if e.maschinell_angezeigt:
        finanzamt = e.finanzamt.strip()
        if not finanzamt.lower().startswith("finanzamt"):
            finanzamt = f"Finanzamt {finanzamt}"
        v.absatz("Die maschinelle Erstellung von Zuwendungsbescheinigungen ohne eigenhändige "
                 "Unterschrift einer zeichnungsberechtigten Person wurde dem "
                 f"{text(finanzamt)} gemäß R 10b.1 Abs. 4 EStR angezeigt.", t + 3)  # fmt: skip


def anlage(v: Vordruck, spenden, gesamt) -> None:
    """Anlage zur Sammelbestätigung: alle Zuwendungen, die neueste zuerst."""
    links, rechts = 77, 515.5
    breite = (rechts - links) / 4
    kopf = ["Datum der Zuwendung",
            "Art der Zuwendung<br/><b>(Geldzuwendung/Mitgliedsbeitrag)</b>",
            "Verzicht auf Erstattung<br/>(ja/nein)", "Betrag in €"]  # fmt: skip
    zeilen = [[datum(s.datum), "Mitgliedsbeitrag" if s.mitgliedsbeitrag else "Geldzuwendung",
               "Ja" if s.verzicht_aufwand else "Nein", betrag(s.betrag)]
              for s in sorted(spenden, key=lambda s: (s.datum, s.pk), reverse=True)]  # fmt: skip

    def neue_seite() -> float:
        v.absatz("Anlage zur Sammelbestätigung", 89.5, ParagraphStyle(
            "anlage", parent=_GRUND, fontSize=8, leading=10), x=links, rechts=rechts)  # fmt: skip
        return zeichne([*kopf], 104, 19.5, kopfzeile=True)

    def zeichne(werte, oben, hoehe, kopfzeile=False) -> float:
        v.c.setLineWidth(0.5)
        for i, wert in enumerate(werte):
            x = links + i * breite
            v.c.rect(x, HOEHE - oben - hoehe, breite, hoehe)
            if not kopfzeile and i == 3:
                v.c.setFont("Helvetica", 6.3)
                v.c.drawRightString(x + breite - 3, HOEHE - oben - hoehe / 2 - 2, wert)
            else:  # senkrecht mittig wie im Vordruck
                p = Paragraph(wert if kopfzeile else text(wert), TABELLE)
                _, h = p.wrapOn(v.c, breite - 3, hoehe)
                p.drawOn(v.c, x + 2, HOEHE - oben - hoehe + (hoehe - h) / 2 + 0.5)
        return oben + hoehe

    t = neue_seite()
    for werte in zeilen:
        if t > HOEHE - 70:
            v.seite_fertig()
            t = neue_seite()
        t = zeichne(werte, t, 13)
    t += 32
    v.c.setFont("Helvetica", 7.5)
    v.c.drawString(links, HOEHE - t - 6, "Gesamtsumme")
    v.c.drawRightString(rechts - 15, HOEHE - t - 6, betrag(gesamt))
    v.c.drawRightString(rechts, HOEHE - t - 6, "€")
    v.c.setLineWidth(0.5)
    v.c.line(433, HOEHE - t - 8, rechts, HOEHE - t - 8)
