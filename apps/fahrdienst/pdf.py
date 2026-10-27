"""Fahrerplan als PDF (ADR 0021, 0074): A3 quer wie der bisherige Papierplan, Springer darunter."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A3, landscape
from reportlab.platypus import Paragraph, Table, TableStyle

from apps.ausgabe.ampel import WOCHENTAGE
from apps.core.pdf import RAND, ZELLE, ZELLE_KOPF, Pdf, text
from apps.fahrdienst import plan
from apps.fahrdienst.models import Springer

GELB = colors.HexColor("#ffe94d")
GRAU = colors.HexColor("#f0f0f0")


def _name(b) -> str:
    return b.get_full_name() or b.username


def _platz(p) -> str:
    """Ein Platz als Absatztext: offen markiert, Ersatz mit „für …“."""
    if p.gast:
        return f"{text(p.gast)} <font size=7>(Gast)</font>"
    if p.status == plan.UNBESETZT:
        return "<b>unbesetzt</b>"
    if p.wer is None:
        return ""
    if p.status == plan.OFFEN:
        return f"<strike>{text(_name(p.wer))}</strike> <b>offen</b>"
    if p.ersatz and p.stamm:
        return f"<b>{text(_name(p.wer))}</b> <font size=7>(für {text(_name(p.stamm))})</font>"
    return text(_name(p.wer))


def monat(titel: str, tage, touren) -> bytes:
    seite = landscape(A3)
    doc = Pdf(f"Fahrerplan {titel}", "offen = fällt aus, noch kein Ersatz · fett = springt ein",
              seite)  # fmt: skip
    kopf = [Paragraph("Tag", ZELLE_KOPF)] + [Paragraph(text(t.name), ZELLE_KOPF) for t in touren]
    zeilen = [kopf]
    stil = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
        ("BACKGROUND", (0, 0), (-1, 0), GRAU),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ]
    for i, (datum, zeile) in enumerate(tage, start=1):
        tag = f"{WOCHENTAGE[datum.weekday()]} {datum:%d.%m.}"
        zellen = [Paragraph(f"<b>{tag}</b>", ZELLE)]
        for j, (_, plaetze) in enumerate(zeile, start=1):
            zellen.append(Paragraph(" / ".join(x for x in map(_platz, plaetze) if x), ZELLE))
            if any(p.fehlt for p in plaetze):
                stil.append(("BACKGROUND", (j, i), (j, i), GELB))
        zeilen.append(zellen)
        if datum.weekday() == 0 and i > 1:  # neue Woche wie auf dem Papierplan
            stil.append(("LINEABOVE", (0, i), (-1, i), 1.5, colors.black))
    if len(zeilen) == 1:
        doc.absatz("In diesem Monat sind keine Fahrtage.")
    else:
        breite = seite[0] - 2 * RAND
        tag_breite = 0.07 * breite
        spalten = [tag_breite] + [(breite - tag_breite) / len(touren)] * len(touren)
        tabelle = Table(zeilen, colWidths=spalten, repeatRows=1)
        tabelle.setStyle(TableStyle(stil))
        doc.element(tabelle)
    springer = Springer.objects.select_related("benutzer").filter(benutzer__is_active=True)
    if springer:
        doc.ueberschrift("Springer")
        doc.absatz(", ".join(_name(s.benutzer) + (f" (nur {s.wochentage})" if s.wochentage else "")
                             for s in springer))  # fmt: skip
    return doc.erzeugen()
