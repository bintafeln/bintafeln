"""Druck der Wochenübersicht als PDF (ADR 0021): Hochformat je Tag, Querformat wie das bisherige
Excel-Blatt (Zeilen = Ausgabestellen, je Tag fünf Spalten mit gedrehten Köpfen)."""

import datetime as dt

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Table, TableStyle

from apps.core.pdf import RAND, Pdf

ORANGE = colors.HexColor("#e8830a")
HELL = colors.HexColor("#fde8c8")
BLASS = colors.HexColor("#fff5e8")
SPALTEN = ["Soll HH", "Ist HH", "Erw.", "Kinder", "Gesamt"]


def _z(wert) -> str:
    return "" if wert in (None, 0) else str(wert)


def _untertitel(daten) -> str:
    vorschau = daten.get("vorschau")
    if vorschau:
        ende = vorschau + dt.timedelta(days=6)
        return (f"Vorschau KW {vorschau:%V} ({vorschau:%d.%m.}–{ende:%d.%m.%Y}) · "
                f"gerechnet am {daten['stichtag']:%d.%m.%Y}")  # fmt: skip
    teile = [f"Stand {daten['stichtag']:%d.%m.%Y}"]
    if daten["woche"]:
        teile.append(f"Abholungen KW {daten['woche']:%V} ab {daten['woche']:%d.%m.%Y}")
    return " · ".join(teile)


def hochformat(daten) -> bytes:
    doc = Pdf("Wochenübersicht der Ausgabestellen", _untertitel(daten))
    mit_abholung = daten["woche"] is not None
    kopf = ["Ausgabestelle", *SPALTEN] + (["Abgeholt"] if mit_abholung else [])
    breiten = [0.34] + [0.11] * 6 if mit_abholung else [0.4] + [0.12] * 5
    for tag in daten["tage"]:
        doc.ueberschrift(f"{tag.name}, {tag.datum:%d.%m.}" if tag.datum else tag.name)
        zeilen = [([f"{z.name} – {z.geschlossen}", "", "", "", "", ""] if z.geschlossen else
                   [z.name, _z(z.soll), z.haushalte, z.erwachsene, z.kinder, z.personen])
                  + ([_z(z.abgeholt)] if mit_abholung else []) for z in tag.zeilen]  # fmt: skip
        for s in tag.selbstabholer:
            zeilen.append([f"Selbstabholer: {s.name}", "", "", "", "", s.personen]
                          + ([""] if mit_abholung else []))  # fmt: skip
        s = tag.summe
        zeilen.append([s.name, _z(s.soll), s.haushalte, s.erwachsene, s.kinder,
                       f"{s.personen} (+{tag.selbst_personen})" if tag.selbst_personen
                       else s.personen] + ([_z(s.abgeholt)] if mit_abholung else []))  # fmt: skip
        doc.tabelle(kopf, zeilen, breiten=breiten, rechts=range(1, len(kopf)), summe=True)
    g = daten["gesamt"]
    doc.ueberschrift("Gesamt (alle Tage)")
    doc.tabelle(["Was", "Personen"], [
        ["Ausgabestellen gesamt", g.personen],
        ["Selbstabholer gesamt", daten["selbst_gesamt"]],
        ["GESAMT ALLE PERSONEN", daten["alle_personen"]],
    ], breiten=[0.7, 0.3], rechts=[1], summe=True)  # fmt: skip
    for hinweis in daten.get("hinweise", []):
        doc.absatz(hinweis)
    return doc.erzeugen()


class Gedreht(Flowable):
    """Senkrecht gedrehter Spaltenkopf."""

    def __init__(self, text, hoehe=16 * mm, schrift=7):
        super().__init__()
        self.text, self.hoehe, self.schrift = text, hoehe, schrift

    def wrap(self, verfuegbar_breite, verfuegbar_hoehe):
        return self.schrift, self.hoehe

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont("Helvetica-Bold", self.schrift)
        c.rotate(90)
        c.drawString(0, -0.85 * self.schrift, self.text)
        c.restoreState()


# Querformat: Die Tabelle füllt das Blatt. Schrift und Zeilenhöhe richten sich danach, wie viele
# Zeilen auf die Seite müssen – zwischen diesen Grenzen (in Punkt).
SCHRIFT_MIN, SCHRIFT_MAX = 7.5, 10.5
GITTER = colors.HexColor("#b9b9b9")
STREIFEN = colors.HexColor("#f3f3f3")


def _masse(zeilen_zahl: int, hinweise: int) -> tuple[float, float, float]:
    """Schriftgröße, Zeilenhöhe, Höhe der gedrehten Köpfe: Die Tabelle soll die Seite füllen."""
    frei = landscape(A4)[1] - 42 * mm - 31 * mm - hinweise * 6 * mm  # Ränder, Titel, Gesamt
    kopf = 7.5 * mm
    for schrift in (SCHRIFT_MAX, 10, 9.5, 9, 8.5, 8, SCHRIFT_MIN):
        gedreht = schrift * 6.2
        hoehe = (frei - kopf - gedreht - 6) / zeilen_zahl
        if hoehe >= schrift * 1.75 or schrift == SCHRIFT_MIN:
            break
    return schrift, max(schrift * 1.75, min(hoehe, schrift * 2.3)), gedreht


def querformat(daten) -> bytes:
    doc = Pdf("Wochenübersicht der Ausgabestellen", _untertitel(daten), landscape(A4))
    tage = daten["tage"]
    namen: list[str] = []
    for tag in tage:
        for z in tag.zeilen:
            if z.name not in namen:
                namen.append(z.name)
    selbst_namen: list[str] = []
    for tag in tage:
        for s in tag.selbstabholer:
            if s.name not in selbst_namen:
                selbst_namen.append(s.name)
    n = len(SPALTEN)
    kopf1 = ["Verteilstelle"] + [x for t in tage for x in [t.name] + [""] * (n - 1)]
    kopf2 = [""] * (1 + len(tage) * n)  # gedrehte Köpfe, sobald die Schriftgröße feststeht
    zeilen = [kopf1, kopf2]
    for name in namen:
        zeile = [name]
        for t in tage:
            z = next((z for z in t.zeilen if z.name == name), None)
            if z and z.geschlossen:
                zeile += ["zu"] + [""] * (n - 1)
                continue
            zeile += ([_z(z.soll), _z(z.haushalte), _z(z.erwachsene), _z(z.kinder),
                       _z(z.personen)] if z else [""] * n)  # fmt: skip
        zeilen.append(zeile)
    for name in selbst_namen:
        zeile = [f"Selbstabholer: {name}"]
        for t in tage:
            s = next((s for s in t.selbstabholer if s.name == name), None)
            zeile += [""] * (n - 1) + [_z(s.personen) if s else ""]
        zeilen.append(zeile)
    summe = ["Summe"]
    for t in tage:
        s = t.summe
        summe += [_z(s.soll), _z(s.haushalte), _z(s.erwachsene), _z(s.kinder),
                  _z(s.personen + t.selbst_personen)]  # fmt: skip
    zeilen.append(summe)
    hinweise = daten.get("hinweise", [])
    schrift, hoehe, gedreht = _masse(len(zeilen) - 2, len(hinweise))
    zeilen[1] = [""] + [Gedreht(s, gedreht, schrift - 0.5) for _ in tage for s in SPALTEN]
    breite = landscape(A4)[0] - 2 * RAND
    laengster = max(stringWidth(str(z[0]), "Helvetica", schrift) for z in zeilen) + 12
    erste = min(max(laengster, 0.14 * breite), 0.25 * breite)
    rest = (breite - erste) / (len(tage) * n)
    tabelle = Table(zeilen, colWidths=[erste] + [rest] * (len(tage) * n), repeatRows=2,
                    rowHeights=[7.5 * mm, gedreht + 6] + [hoehe] * (len(zeilen) - 2))  # fmt: skip
    letzte = 2 + len(namen) + len(selbst_namen)
    # Vierstellige Summen müssen in die Spalte passen: die Summenzeile notfalls kleiner setzen
    breiteste = max(stringWidth(str(w), "Helvetica-Bold", schrift) for w in summe[1:])
    schrift_summe = max(schrift - 1.5, min(schrift, schrift * (rest - 3) / breiteste))
    stil = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", schrift),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", schrift + 0.5),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", schrift_summe),
        ("TEXTCOLOR", (0, 1), (-1, -1), colors.black),
        ("BACKGROUND", (1, 0), (-1, 0), ORANGE),
        ("TEXTCOLOR", (1, 0), (-1, 0), colors.white),
        ("ALIGN", (1, 0), (-1, 1), "CENTER"),
        ("ALIGN", (1, 2), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("VALIGN", (0, 1), (-1, 1), "BOTTOM"),
        ("LEFTPADDING", (1, 0), (-1, -1), 2),
        ("RIGHTPADDING", (1, 0), (-1, -1), 3),
        ("LEFTPADDING", (1, -1), (-1, -1), 1),
        ("RIGHTPADDING", (1, -1), (-1, -1), 1.5),
        ("TOPPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ("BOTTOMPADDING", (0, 1), (-1, 1), 3),
        ("GRID", (0, 1), (-1, -1), 0.4, GITTER),
        ("LINEBELOW", (0, 1), (-1, 1), 1, colors.black),
        ("LINEABOVE", (0, -1), (-1, -1), 1, colors.black),
        ("BOX", (0, 1), (-1, -1), 1, colors.black),
    ]
    for zeile in range(3, 2 + len(namen), 2):
        stil.append(("BACKGROUND", (0, zeile), (-1, zeile), STREIFEN))
    for i in range(len(tage)):
        start = 1 + i * n
        stil.append(("SPAN", (start, 0), (start + n - 1, 0)))
        stil.append(("LINEAFTER", (start + n - 1, 0), (start + n - 1, -1), 1.5, colors.black))
        # „Gesamt“ ist die Zahl, auf die es ankommt: fett
        stil.append(("FONT", (start + n - 1, 2), (start + n - 1, -2), "Helvetica-Bold", schrift))
    for zeile in range(2 + len(namen), letzte):
        stil.append(("BACKGROUND", (0, zeile), (-1, zeile), BLASS))
    stil.append(("BACKGROUND", (0, -1), (-1, -1), HELL))
    tabelle.setStyle(TableStyle(stil))
    doc.element(tabelle)
    doc.abstand()
    g = daten["gesamt"]
    doc.absatz(f"GESAMT: Ausgabestellen {g.personen} | Selbstabholer {daten['selbst_gesamt']} | "
               f"Alle Personen {daten['alle_personen']}")  # fmt: skip
    for hinweis in daten.get("hinweise", []):
        doc.absatz(hinweis)
    return doc.erzeugen()
