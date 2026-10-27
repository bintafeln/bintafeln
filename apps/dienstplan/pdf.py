"""Dienstplan als PDF (ADR 0021, 0077): A4 quer wie der Papierplan – je Ausgabetag eine Seite mit
„Freitag | November“, Spalten für die Daten, Zeilen für die Aufgaben, unten die Abmeldung."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, Table, TableStyle

from apps.core.pdf import RAND, ZELLE, Pdf, text
from apps.dienstplan import plan

BLAU = colors.HexColor("#1f6fbf")
GRAU = colors.HexColor("#c8c8c8")
GELB = "#ffe94d"  # nur hinter dem Namen, der fehlt
GROSS = ParagraphStyle("dp_gross", parent=ZELLE, fontName="Helvetica-Bold", fontSize=30,
                       leading=34, alignment=1, textColor=BLAU)  # fmt: skip
KOPF = ParagraphStyle("dp_kopf", parent=ZELLE, fontName="Helvetica-Bold", fontSize=13,
                      leading=15, alignment=1)  # fmt: skip
AUFGABE = ParagraphStyle("dp_aufgabe", parent=ZELLE, fontName="Helvetica-Bold", fontSize=11,
                         leading=13)  # fmt: skip
ZEIT = ParagraphStyle("dp_zeit", parent=ZELLE, fontSize=11, leading=13)
NAME = ParagraphStyle("dp_name", parent=ZELLE, fontSize=10.5, leading=12.5, alignment=1)
FUSS = ParagraphStyle("dp_fuss", parent=ZELLE, fontSize=13, leading=16, alignment=1)


def _name(p) -> str:
    if p.gast:
        return f"{text(p.gast)} <font size=7>(Gast)</font>"
    if p.status == plan.UNBESETZT:
        return f'<font backColor="{GELB}"><b>unbesetzt</b></font>'
    if p.wer is None:
        return ""
    if p.status == plan.OFFEN:
        return (
            f'<font backColor="{GELB}"><strike>{text(p.wer.anzeige)}</strike> <b>offen</b></font>'
        )
    if p.ersatz and p.stamm:
        return f"<b>{text(p.wer.anzeige)}</b>"
    return text(p.wer.anzeige)


def _seite(tagname, monat, daten, zeilen, diensttag, breite, hoehe):
    """Eine Seite als Tabelle: Kopf mit Wochentag und Monat, dann Aufgaben × Daten."""
    spalten = max(len(daten), 4)  # wie auf Papier mindestens vier Termin-Spalten
    erste, zweite = 0.17 * breite, 0.12 * breite
    rest = (breite - erste - zweite) / spalten
    links = 2 + spalten // 2
    kopf = [
        Paragraph(text(tagname), GROSS),
        "",
        *[""] * (links - 2),
        Paragraph(text(monat), GROSS),
        *[""] * (spalten - links + 1),
    ]
    kopf = kopf[: 2 + spalten]
    tage1 = ["", "", *[Paragraph(text(tagname), KOPF) for _ in range(spalten)]]
    tage2 = [
        "",
        "",
        *[
            Paragraph(f"{d.day}" if i < len(daten) else "", KOPF)
            for i, d in enumerate([*daten, *[None] * (spalten - len(daten))])
        ],
    ]
    zeilen_tab = [kopf, tage1, tage2]
    stil = [
        ("GRID", (0, 1), (-1, -1), 0.4, colors.black),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("SPAN", (0, 0), (1, 0)), ("SPAN", (2, 0), (links - 1, 0)),
        ("SPAN", (links, 0), (-1, 0)),
        ("BACKGROUND", (2, 2), (-1, 2), GRAU),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.8, colors.black),
    ]  # fmt: skip
    for a, ps in zeilen:
        zellen = [Paragraph(text(a.name), AUFGABE), Paragraph(text(a.zeit), ZEIT)]
        zellen += [Paragraph(_name(p), NAME) for p in ps]
        zeilen_tab.append(zellen + [""] * (spalten - len(ps)))
    leitung = diensttag.teamleitung if diensttag else None
    telefon = (diensttag.telefon if diensttag and diensttag.telefon else
               (leitung.tel if leitung else ""))  # fmt: skip
    fuss = "Abmeldungen bitte bei " + (text(leitung.anzeige) if leitung else "der Teamleitung")
    fuss += f" unter {text(telefon)}" if telefon else ""
    zeilen_tab.append([Paragraph(fuss, FUSS), *[""] * (spalten + 1)])
    stil += [("SPAN", (0, len(zeilen_tab) - 1), (-1, len(zeilen_tab) - 1)),
             ("LINEABOVE", (0, len(zeilen_tab) - 1), (-1, len(zeilen_tab) - 1), 0.8,
              colors.black)]  # fmt: skip
    # Zeilen über die ganze Seitenhöhe strecken (wie der Papierplan)
    oben, fuss_h = [16 * mm, 9 * mm, 9 * mm], 16 * mm
    rest_h = max(hoehe - sum(oben) - fuss_h, 0)
    zeile_h = min(rest_h / max(len(zeilen), 1), 14 * mm)
    hoehen = [*oben, *[zeile_h] * len(zeilen), fuss_h]
    tabelle = Table(zeilen_tab, colWidths=[erste, zweite, *[rest] * spalten], rowHeights=hoehen)
    tabelle.setStyle(TableStyle(stil))
    return tabelle


def monat(stelle, monatsname: str, jahr: int, seiten) -> bytes:
    """``seiten``: [(Wochentag ausgeschrieben, Daten, Zeilen, Diensttag)] – je eine Seite."""
    seite = landscape(A4)
    doc = Pdf(f"Dienstplan {stelle} – {monatsname} {jahr}", "", seite)
    breite = seite[0] - 2 * RAND
    # Platz: Seite ohne Ränder (oben 24 mm, unten 18 mm) und ohne den Titel der ersten Seite
    titel = sum(f.wrap(breite, seite[1])[1] + f.getSpaceBefore() + f.getSpaceAfter()
                for f in doc.inhalt)  # fmt: skip
    hoehe = seite[1] - 42 * mm - titel - 6 * mm
    if not seiten:
        doc.absatz("An dieser Ausgabestelle sind keine Ausgabetage eingestellt.")
    for i, (tagname, daten, zeilen, diensttag) in enumerate(seiten):
        if i:
            doc.element(PageBreak())
        doc.element(_seite(tagname, monatsname, daten, zeilen, diensttag, breite, hoehe))
    return doc.erzeugen()
