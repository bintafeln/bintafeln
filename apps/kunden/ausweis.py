"""Kundenausweis als PDF nach der Ausweis-Vorlage der Tafel (ADR 0021, ADR 0027).

Die Vorlage besteht aus Elementen (Text, Logo, Barcode, farbige Fläche) mit Position und Größe
in Millimetern, gemessen von oben links. Kundennummer und Barcode sind Pflicht. Der Barcode
(Code 128) enthält nur die Kundennummer, ohne Vor- oder Nachsilben: Ein Scanner am Einlass,
der als Tastatur arbeitet, tippt sie ins Suchfeld.
"""

import io
import re

from reportlab.graphics.barcode.code128 import Code128
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.pdfgen.canvas import Canvas

from apps.core.models import TafelEinstellungen
from apps.kunden.models import KundenEinstellungen

BREITE_MM, HOEHE_MM = 85.6, 54.0  # ISO/IEC 7810 ID-1
BREITE, HOEHE = BREITE_MM * mm, HOEHE_MM * mm
BARCODE_MIN_B, BARCODE_MIN_H = 30.0, 8.0  # darunter liest nicht jeder Scanner sicher
MAX_ELEMENTE = 40
MAX_SAMMELDRUCK = 500
FARBE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Typ: (Bezeichnung, Pflicht, Art)
TYPEN = {
    "kundennummer": ("Kundennummer", True, "text"),
    "barcode": ("Barcode (Kundennummer)", True, "barcode"),
    "ausweisname": ("Ausweisname", False, "text"),
    "tafelname": ("Name der Tafel", False, "text"),
    "logo": ("Logo der Tafel", False, "bild"),
    "hauptperson": ("Name der Hauptperson", False, "text"),
    "kundengruppe": ("Kundengruppe mit Termin", False, "text"),
    "ausgabestelle": ("Ausgabestelle", False, "text"),
    "gueltig_bis": ("Gültig bis", False, "text"),
    "kunde_seit": ("Kunde seit", False, "text"),
    "personen": ("Anzahl Personen", False, "text"),
    "personen_kinder": ("Personen/Minderjährige (z. B. 6/3)", False, "text"),
    "freitext": ("Freier Text", False, "text"),
    "flaeche": ("Farbige Fläche", False, "flaeche"),
}
PLATZHALTER = [t for t, (_, _, art) in TYPEN.items() if art == "text" and t != "freitext"]
AUSRICHTUNGEN = ("links", "mitte", "rechts")

# Bisheriger Aufbau des Ausweises als Standard-Vorlage
STANDARD = [
    {"typ": "logo", "x": 4, "y": 4, "b": 14, "h": 9, "ausrichtung": "links"},
    {"typ": "tafelname", "x": 19, "y": 4, "b": 40, "h": 4.5, "groesse": 9, "fett": True},
    {"typ": "ausweisname", "x": 19, "y": 8.5, "b": 40, "h": 4, "groesse": 7},
    {
        "typ": "kundennummer",
        "x": 52,
        "y": 4,
        "b": 29.6,
        "h": 7,
        "groesse": 15,
        "fett": True,
        "ausrichtung": "rechts",
    },  # fmt: skip
    {"typ": "hauptperson", "x": 4, "y": 17, "b": 77.6, "h": 5, "groesse": 10, "fett": True},
    {"typ": "kundengruppe", "x": 4, "y": 22, "b": 77.6, "h": 4, "groesse": 8},
    {"typ": "gueltig_bis", "x": 4, "y": 26, "b": 50, "h": 4, "groesse": 8},
    {
        "typ": "personen_kinder",
        "x": 56,
        "y": 26,
        "b": 25.6,
        "h": 4,
        "groesse": 9,
        "fett": True,
        "ausrichtung": "rechts",
    },  # fmt: skip
    {"typ": "barcode", "x": 8, "y": 37, "b": 69.6, "h": 13, "ausrichtung": "mitte"},
]

BEISPIEL = {
    "kundennummer": "1234",
    "ausweisname": "Kundenausweis",
    "tafelname": "Tafel Musterstadt",
    "hauptperson": "Erika Mustermann",
    "kundengruppe": "Gruppe Montag · Mo, 12:30 Uhr",
    "ausgabestelle": "Ausgabestelle Mitte",
    "gueltig_bis": "Gültig bis 31.12.2027",
    "kunde_seit": "Kunde seit 01.02.2024",
    "personen": "3 Personen",
    "personen_kinder": "6/3",
}


def _zahl(wert, standard, kleinste, groesste) -> float:
    try:
        zahl = float(wert)
    except (TypeError, ValueError):
        zahl = standard
    return round(min(max(zahl, kleinste), groesste), 1)


def element_pruefen(roh) -> dict | None:
    """Bereinigt ein Element aus dem Gestalter; unbekannte Typen fallen weg."""
    if not isinstance(roh, dict) or roh.get("typ") not in TYPEN:
        return None
    typ = roh["typ"]
    art = TYPEN[typ][2]
    e = {"typ": typ}
    e["b"] = _zahl(roh.get("b"), 30, 2, BREITE_MM)
    e["h"] = _zahl(roh.get("h"), 5, 1, HOEHE_MM)
    if art == "barcode":
        e["b"] = max(e["b"], BARCODE_MIN_B)
        e["h"] = max(e["h"], BARCODE_MIN_H)
    e["x"] = _zahl(roh.get("x"), 4, 0, BREITE_MM - e["b"])
    e["y"] = _zahl(roh.get("y"), 4, 0, HOEHE_MM - e["h"])
    ausrichtung = roh.get("ausrichtung")
    e["ausrichtung"] = ausrichtung if ausrichtung in AUSRICHTUNGEN else "links"
    farbe = roh.get("farbe")
    e["farbe"] = farbe if isinstance(farbe, str) and FARBE.match(farbe) else (
        "#e8710a" if art == "flaeche" else "#000000")  # fmt: skip
    if art == "text":
        e["groesse"] = _zahl(roh.get("groesse"), 9, 5, 40)
        e["fett"] = bool(roh.get("fett"))
    if typ == "freitext":
        e["text"] = str(roh.get("text") or "")[:200]
    return e


def elemente_pruefen(liste) -> list[dict]:
    """Bereinigte Elemente; fehlen Kundennummer oder Barcode, kommen sie aus dem Standard."""
    elemente = [e for e in (element_pruefen(r) for r in (liste or [])[:MAX_ELEMENTE]) if e]
    for typ in ("kundennummer", "barcode"):
        if not any(e["typ"] == typ for e in elemente):
            elemente.append(element_pruefen(next(s for s in STANDARD if s["typ"] == typ)))
    return elemente


def standard() -> list[dict]:
    return [element_pruefen(e) for e in STANDARD]


def werte(h, tafel, vorlage) -> dict[str, str]:
    """Texte eines Haushalts für die Elemente."""
    hp = h.hauptperson
    g = h.kundengruppe
    termin = ""
    if g:
        teile = [t for t in (g.wochentage, f"{g.uhrzeit:%H:%M} Uhr" if g.uhrzeit else "") if t]
        termin = f"Gruppe {g.name}" + (f" · {', '.join(teile)}" if teile else "")
    stelle = g.ausgabestelle.name if g and g.ausgabestelle else ""
    anzahl = h.personen.count()
    erwachsene, kinder = h.groesse(KundenEinstellungen.laden().kind_bis_alter)
    return {
        "kundennummer": h.kundennummer,
        "ausweisname": vorlage.name,
        "tafelname": tafel.name or "Tafel",
        "hauptperson": f"{hp.vorname} {hp.nachname}" if hp else "",
        "kundengruppe": termin,
        "ausgabestelle": stelle,
        "gueltig_bis": f"Gültig bis {h.ausweis_gueltig_bis:%d.%m.%Y}"
        if h.ausweis_gueltig_bis
        else "",
        "kunde_seit": f"Kunde seit {h.kunde_seit:%d.%m.%Y}" if h.kunde_seit else "",
        "personen": f"{anzahl} Person{'en' if anzahl != 1 else ''}" if anzahl else "",
        "personen_kinder": f"{erwachsene + kinder}/{kinder}",
    }


def text_von(e: dict, w: dict) -> str:
    if e["typ"] != "freitext":
        return w.get(e["typ"], "")
    text = e.get("text", "")
    for name in PLATZHALTER:
        text = text.replace("{" + name + "}", w.get(name, ""))
    return text


def _bild(datei):
    if not datei:
        return None
    try:
        return ImageReader(datei.path)
    except (OSError, ValueError):
        return None


def _seite(c: Canvas, elemente, hintergrund, logo, w, x0, y0) -> None:
    """Zeichnet eine Kartenseite; (x0, y0) ist die linke untere Ecke."""
    if hintergrund:
        c.drawImage(hintergrund, x0, y0, width=BREITE, height=HOEHE, mask="auto",
                    preserveAspectRatio=False)  # fmt: skip
    for e in elemente:
        x, b, h = x0 + e["x"] * mm, e["b"] * mm, e["h"] * mm
        y = y0 + HOEHE - (e["y"] + e["h"]) * mm  # untere Kante des Elements
        art = TYPEN[e["typ"]][2]
        if art == "flaeche":
            c.setFillColor(colors.HexColor(e["farbe"]))
            c.rect(x, y, b, h, stroke=0, fill=1)
        elif art == "bild" and logo:
            bb, bh = logo.getSize()
            faktor = min(b / bb, h / bh)
            zb, zh = bb * faktor, bh * faktor
            dx = {"links": 0, "mitte": (b - zb) / 2, "rechts": b - zb}[e["ausrichtung"]]
            c.drawImage(logo, x + dx, y + (h - zh) / 2, width=zb, height=zh, mask="auto")
        elif art == "barcode":
            _barcode(c, w["kundennummer"], x, y, b, h, e["ausrichtung"])
        elif art == "text":
            _text(c, text_von(e, w), e, x, y, b, h)


def _text(c: Canvas, text, e, x, y, b, h) -> None:
    if not text:
        return
    schrift = "Helvetica-Bold" if e.get("fett") else "Helvetica"
    groesse = e.get("groesse", 9)
    while groesse > 4 and stringWidth(text, schrift, groesse) > b:  # passend verkleinern
        groesse -= 0.5
    c.setFont(schrift, groesse)
    c.setFillColor(colors.HexColor(e["farbe"]))
    grundlinie = y + (h - groesse * 0.7) / 2  # senkrecht mittig
    if e["ausrichtung"] == "mitte":
        c.drawCentredString(x + b / 2, grundlinie, text)
    elif e["ausrichtung"] == "rechts":
        c.drawRightString(x + b, grundlinie, text)
    else:
        c.drawString(x, grundlinie, text)


def _barcode(c: Canvas, nummer, x, y, b, h, ausrichtung) -> None:
    probe = Code128(nummer, barWidth=1, barHeight=h, humanReadable=False)
    breite = min(0.45 * mm, b / probe.width)  # Strichbreite so, dass der Code in die Box passt
    code = Code128(nummer, barWidth=breite, barHeight=h, humanReadable=False)
    dx = {"links": 0, "mitte": (b - code.width) / 2, "rechts": b - code.width}[ausrichtung]
    code.drawOn(c, x + dx, y)


def _schnittmarken(c: Canvas, x, y) -> None:
    c.setStrokeColor(colors.grey)
    c.setLineWidth(0.3)
    for px in (x, x + BREITE):
        c.line(px, y - 8 * mm, px, y - 2 * mm)
        c.line(px, y + HOEHE + 2 * mm, px, y + HOEHE + 8 * mm)
    for py in (y, y + HOEHE):
        c.line(x - 8 * mm, py, x - 2 * mm, py)
        c.line(x + BREITE + 2 * mm, py, x + BREITE + 8 * mm, py)


def _rahmen(c: Canvas, x, y) -> None:
    c.setStrokeColor(colors.lightgrey)
    c.setLineWidth(0.5)
    c.roundRect(x, y, BREITE, HOEHE, 3 * mm, stroke=1, fill=0)


def pdf(liste_werte, vorlage, vorne=None, hinten=None) -> bytes:
    """Ein Ausweis je Haushalt (Werte), im Seitenformat der Vorlage.

    A4: Vorderseite oben, Rückseite darunter, mit Schnittmarken. Kartengröße (Kartendrucker):
    je Ausweis eine Seite für vorn und, falls eingeschaltet, eine für hinten.
    """
    tafel = TafelEinstellungen.laden()
    vorne = vorne if vorne is not None else vorlage.elemente_vorne()
    hinten = (hinten if hinten is not None else vorlage.elemente_hinten()) if (
        vorlage.rueckseite_aktiv) else None  # fmt: skip
    logo = _bild(tafel.logo)
    bild_vorne, bild_hinten = _bild(vorlage.hintergrund), _bild(vorlage.hintergrund_rueckseite)
    puffer = io.BytesIO()
    karte = vorlage.seitenformat == vorlage.Seitenformat.KARTE
    c = Canvas(puffer, pagesize=(BREITE, HOEHE) if karte else A4)
    c.setTitle(f"{vorlage.name} {liste_werte[0]['kundennummer']}" if len(liste_werte) == 1
               else f"{vorlage.name} ({len(liste_werte)})")  # fmt: skip
    c.setAuthor(tafel.name or "bintafeln")
    seite_b, seite_h = A4
    for w in liste_werte:
        if karte:
            _seite(c, vorne, bild_vorne, logo, w, 0, 0)
            c.showPage()
            if hinten is not None:
                _seite(c, hinten, bild_hinten, logo, w, 0, 0)
                c.showPage()
            continue
        x, y = (seite_b - BREITE) / 2, seite_h - 40 * mm - HOEHE
        _seite(c, vorne, bild_vorne, logo, w, x, y)
        _rahmen(c, x, y)
        _schnittmarken(c, x, y)
        unten = y
        if hinten is not None:
            unten = y - 30 * mm - HOEHE
            _seite(c, hinten, bild_hinten, logo, w, x, unten)
            _rahmen(c, x, unten)
            _schnittmarken(c, x, unten)
        c.setFont("Helvetica", 8)
        c.setFillColor(colors.grey)
        hinweis = "Entlang der Marken ausschneiden. In 100 % Größe drucken."
        if hinten is not None:
            hinweis = "Beide Seiten ausschneiden und Rücken an Rücken kleben oder laminieren. " \
                "In 100 % Größe drucken."  # fmt: skip
        c.drawCentredString(seite_b / 2, unten - 14 * mm, hinweis)
        c.showPage()
    c.save()
    return puffer.getvalue()


def ausweise_pdf(haushalte) -> bytes:
    from apps.kunden.models import AusweisVorlage

    vorlage = AusweisVorlage.laden()
    tafel = TafelEinstellungen.laden()
    return pdf([werte(h, tafel, vorlage) for h in haushalte], vorlage)


def ausweis_pdf(h) -> bytes:
    return ausweise_pdf([h])


def beispiel_pdf(vorlage, vorne, hinten) -> bytes:
    """Vorschau aus dem Gestalter mit erfundenen Daten (noch nicht gespeicherte Elemente)."""
    tafel = TafelEinstellungen.laden()
    w = {**BEISPIEL, "ausweisname": vorlage.name, "tafelname": tafel.name or BEISPIEL["tafelname"]}
    return pdf([w], vorlage, vorne=vorne, hinten=hinten)
