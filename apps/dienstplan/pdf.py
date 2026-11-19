"""Dienstplan als PDF (ADR 0021, 0077): A4 quer wie der Papierplan – je Ausgabetag eine Seite mit
„Freitag | November“, Spalten für die Daten, Zeilen für die Aufgaben, unten die Abmeldung
(``monat``). Oder alle Ausgabetage des Monats auf einem großen Blatt, A3 quer (``uebersicht``)."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, A4, landscape
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
        return f'<font backColor="{GELB}"><strike>{text(p.wer.name)}</strike> <b>offen</b></font>'
    if p.ersatz and p.stamm:
        return f"<b>{text(p.wer.name)}</b>"
    return text(p.wer.name)


def _abmeldung(diensttag) -> str:
    """„Lea Leitung unter 0123 …“: Teamleitung des Tages und die Nummer für Abmeldungen (die beim
    Tag eingetragene, sonst Telefon oder Mobil der Teamleitung)."""
    leitung = diensttag.teamleitung if diensttag else None
    telefon = diensttag.telefon if diensttag and diensttag.telefon else ""
    if not telefon and leitung:
        telefon = leitung.telefon or leitung.mobil
    wer = text(leitung.name) if leitung else "der Teamleitung"
    return f"{wer} unter {text(telefon)}" if telefon else wer


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
    fuss = "Abmeldungen bitte bei " + _abmeldung(diensttag)
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


KLEIN_KOPF = ParagraphStyle("dp_klein_kopf", parent=KOPF, fontSize=11, leading=13)
KLEIN_NAME = ParagraphStyle("dp_klein_name", parent=NAME, fontSize=9, leading=10.5)
KLEIN_FUSS = ParagraphStyle("dp_klein_fuss", parent=FUSS, fontSize=11, leading=14)
HELLGRAU = colors.HexColor("#ececec")


def uebersicht(stelle, monatsname: str, jahr: int, seiten) -> bytes:
    """Alle Ausgabetage des Monats auf einem Blatt, A3 quer: Spalten = alle Termine der Reihe
    nach, Zeilen = die Aufgaben. Gleiche Aufgaben verschiedener Wochentage (Name und Uhrzeit)
    stehen in einer Zeile; gibt es eine Aufgabe an einem Wochentag nicht, ist das Feld grau.
    ``seiten`` wie bei ``monat``."""
    seite = landscape(A3)
    doc = Pdf(f"Dienstplan {stelle} – {monatsname} {jahr}", "", seite)
    breite = seite[0] - 2 * RAND
    termine = sorted((d, tagname) for tagname, daten, _, _ in seiten for d in daten)
    if not termine:
        doc.absatz("In diesem Monat gibt es an dieser Ausgabestelle keine Ausgabetage.")
        return doc.erzeugen()
    # Zeilen: Aufgaben in der Reihenfolge ihres ersten Auftretens; die dritte „Obst“-Zeile eines
    # Tages trifft die dritte „Obst“-Zeile der anderen Tage
    reihen: dict[tuple, dict] = {}
    for _, _, zeilen, _ in seiten:
        gezaehlt: dict[tuple, int] = {}
        name = ""
        for a, ps in zeilen:
            name = a.name or name  # leerer Name = weitere Zeile zur Aufgabe darüber
            art = (name, a.zeit)
            gezaehlt[art] = gezaehlt.get(art, 0) + 1
            reihe = reihen.setdefault((*art, gezaehlt[art]), {"name": name, "zeit": a.zeit,
                                                              "plaetze": {}})  # fmt: skip
            reihe["plaetze"].update({p.datum: p for p in ps})
    erste, zweite = 0.11 * breite, 0.07 * breite
    rest = (breite - erste - zweite) / len(termine)
    tabelle = [
        ["", "", *[Paragraph(text(tagname[:2]), KLEIN_KOPF) for _, tagname in termine]],
        ["", "", *[Paragraph(f"{d.day}.", KLEIN_KOPF) for d, _ in termine]],
    ]
    stil = [
        ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
        ("BOX", (0, 0), (-1, -1), 0.8, colors.black),
        ("BACKGROUND", (2, 1), (-1, 1), GRAU),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for reihe in reihen.values():
        zellen = [Paragraph(text(reihe["name"]), AUFGABE), Paragraph(text(reihe["zeit"]), ZEIT)]
        for spalte, (d, _) in enumerate(termine):
            p = reihe["plaetze"].get(d)
            zellen.append(Paragraph(_name(p), KLEIN_NAME) if p else "")
            if p is None:  # diese Aufgabe gibt es an dem Wochentag nicht
                stil.append(("BACKGROUND", (2 + spalte, len(tabelle)), (2 + spalte, len(tabelle)),
                             HELLGRAU))  # fmt: skip
        tabelle.append(zellen)
    fuss = "Abmeldungen bitte bei: " + " · ".join(
        f"{text(tagname)} {_abmeldung(diensttag)}" for tagname, daten, _, diensttag in seiten
        if daten)  # fmt: skip
    tabelle.append([Paragraph(fuss, KLEIN_FUSS), *[""] * (len(termine) + 1)])
    stil.append(("SPAN", (0, len(tabelle) - 1), (-1, len(tabelle) - 1)))
    titel = sum(f.wrap(breite, seite[1])[1] + f.getSpaceBefore() + f.getSpaceAfter()
                for f in doc.inhalt)  # fmt: skip
    hoehe = seite[1] - 42 * mm - titel - 6 * mm
    oben, fuss_h = [8 * mm, 8 * mm], 14 * mm
    zeile_h = min(max(hoehe - sum(oben) - fuss_h, 0) / max(len(reihen), 1), 14 * mm)
    blatt = Table(tabelle, colWidths=[erste, zweite, *[rest] * len(termine)],
                  rowHeights=[*oben, *[zeile_h] * len(reihen), fuss_h])  # fmt: skip
    blatt.setStyle(TableStyle(stil))
    doc.element(blatt)
    return doc.erzeugen()
