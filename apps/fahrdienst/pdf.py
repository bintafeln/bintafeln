"""Fahrerplan als PDF (ADR 0021, 0074): A3 quer wie der bisherige Papierplan, Springer darunter."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, Table, TableStyle

from apps.ausgabe.ampel import WOCHENTAGE
from apps.core.pdf import RAND, ZELLE, Pdf, text
from apps.fahrdienst import plan
from apps.fahrdienst.models import Springer

GELB = "#ffe94d"  # nur hinter dem Namen, der fehlt (wie der gelbe Aufkleber im Plan)
GRAU = colors.HexColor("#f0f0f0")


def _name(b) -> str:
    return b.name


def _platz(p) -> str:
    """Ein Platz als Absatztext: offen markiert, Ersatz mit „für …“."""
    if p.gast:
        return f"{text(p.gast)} <font size=7>(Gast)</font>"
    if p.status == plan.UNBESETZT:
        return f'<font backColor="{GELB}"><b>unbesetzt</b></font>'
    if p.wer is None:
        return ""
    if p.status == plan.OFFEN:
        return f'<font backColor="{GELB}"><strike>{text(_name(p.wer))}</strike> <b>offen</b></font>'
    if p.ersatz and p.stamm:
        return f"<b>{text(_name(p.wer))}</b> <font size=7>(für {text(_name(p.stamm))})</font>"
    return text(_name(p.wer))


def _stil(groesse: float):
    zelle = ParagraphStyle(f"fd{groesse}", parent=ZELLE, fontSize=groesse, leading=groesse * 1.2)
    return zelle, ParagraphStyle(f"fdk{groesse}", parent=zelle, fontName="Helvetica-Bold")


def _tabelle(tage, touren, groesse, breite, zeilenhoehen=None):
    """Der Plan als Tabelle in Schriftgröße ``groesse``; Ausfälle gelb, neue Woche mit Linie."""
    zelle, kopf_stil = _stil(groesse)
    zeilen = [[Paragraph("Tag", kopf_stil)] + [Paragraph(text(t.name), kopf_stil) for t in touren]]
    stil = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), GRAU),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]
    for i, (datum, zeile) in enumerate(tage, start=1):
        tag = f"{WOCHENTAGE[datum.weekday()]} {datum:%d.%m.}"
        zellen = [Paragraph(f"<b>{tag}</b>", zelle)]
        for _, plaetze in zeile:
            inhalt = " / ".join(x for x in map(_platz, plaetze) if x) if plaetze else "–"
            zellen.append(Paragraph(inhalt, zelle))
        zeilen.append(zellen)
        if datum.weekday() == 0 and i > 1:  # neue Woche wie auf dem Papierplan
            stil.append(("LINEABOVE", (0, i), (-1, i), 1.5, colors.black))
    tag_breite = 0.065 * breite
    spalten = [tag_breite] + [(breite - tag_breite) / len(touren)] * len(touren)
    tabelle = Table(zeilen, colWidths=spalten, rowHeights=zeilenhoehen, repeatRows=1)
    tabelle.setStyle(TableStyle(stil))
    return tabelle


def _seite_fuellen(tage, touren, breite, hoehe):
    """Größte Schrift, bei der der Monat auf eine Seite passt; die Zeilen strecken sich dann über
    die ganze Höhe (die Seite wird voll genutzt, wie beim Papierplan)."""
    for groesse in [x / 2 for x in range(36, 15, -1)]:  # 18 … 8 pt in halben Schritten
        tabelle = _tabelle(tage, touren, groesse, breite)
        _, h = tabelle.wrap(breite, hoehe)
        if h <= hoehe:
            break
    hoehen = list(tabelle._rowHeights)
    extra = max(hoehe - sum(hoehen), 0) / len(hoehen)
    return _tabelle(tage, touren, groesse, breite, [x + extra for x in hoehen])


def monat(titel: str, tage, touren) -> bytes:
    seite = landscape(A3)
    doc = Pdf(f"Fahrerplan {titel}", "offen = fällt aus, noch kein Ersatz · fett = springt ein",
              seite)  # fmt: skip
    breite = seite[0] - 2 * RAND
    springer = list(Springer.objects.select_related("person")
                    .exclude(person__konto__is_active=False))  # fmt: skip
    if not tage:
        doc.absatz("In diesem Monat sind keine Fahrtage.")
    else:
        # Platz: Seite ohne Ränder (oben 24 mm, unten 18 mm), Titel und Springer darunter
        oben = sum(f.wrap(breite, seite[1])[1] + f.getSpaceBefore() + f.getSpaceAfter()
                   for f in doc.inhalt)  # fmt: skip
        hoehe = seite[1] - 42 * mm - oben - (24 * mm if springer else 0) - 4 * mm
        doc.element(_seite_fuellen(list(tage), touren, breite, hoehe))
    if springer:
        doc.ueberschrift("Springer")
        doc.absatz(", ".join(_name(s.person) + (f" (nur {s.wochentage})" if s.wochentage else "")
                             for s in springer))  # fmt: skip
    return doc.erzeugen()
