"""Druck der Wochenübersicht als PDF (ADR 0021): Hochformat je Tag, Querformat wie das bisherige
Excel-Blatt (Zeilen = Ausgabestellen, je Tag fünf Spalten mit gedrehten Köpfen)."""

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.platypus import Flowable, Table, TableStyle

from apps.core.pdf import RAND, Pdf

ORANGE = colors.HexColor("#e8830a")
HELL = colors.HexColor("#fde8c8")
BLASS = colors.HexColor("#fff5e8")
SPALTEN = ["Soll HH", "Ist HH", "Erw.", "Kinder", "Gesamt"]


def _z(wert) -> str:
    return "" if wert in (None, 0) else str(wert)


def _untertitel(daten) -> str:
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
        doc.ueberschrift(tag.name)
        zeilen = [[z.name, _z(z.soll), z.haushalte, z.erwachsene, z.kinder, z.personen]
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
    return doc.erzeugen()


class Gedreht(Flowable):
    """Senkrecht gedrehter Spaltenkopf."""

    def __init__(self, text, hoehe=16 * mm):
        super().__init__()
        self.text, self.hoehe = text, hoehe

    def wrap(self, verfuegbar_breite, verfuegbar_hoehe):
        return 3 * mm, self.hoehe

    def draw(self):
        c = self.canv
        c.saveState()
        c.setFont("Helvetica-Bold", 7)
        c.rotate(90)
        c.drawString(0, -2.6 * mm, self.text)
        c.restoreState()


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
    kopf2 = [""] + [Gedreht(s) for _ in tage for s in SPALTEN]
    zeilen = [kopf1, kopf2]
    for name in namen:
        zeile = [name]
        for t in tage:
            z = next((z for z in t.zeilen if z.name == name), None)
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
    breite = landscape(A4)[0] - 2 * RAND
    erste = 0.2 * breite
    rest = (breite - erste) / (len(tage) * n)
    tabelle = Table(zeilen, colWidths=[erste] + [rest] * (len(tage) * n), repeatRows=2)
    stil = [
        ("FONT", (0, 0), (-1, -1), "Helvetica", 7.5),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8),
        ("FONT", (0, -1), (-1, -1), "Helvetica-Bold", 7.5),
        ("BACKGROUND", (1, 0), (-1, 0), ORANGE),
        ("TEXTCOLOR", (1, 0), (-1, 0), colors.white),
        ("BACKGROUND", (0, -1), (-1, -1), HELL),
        ("ALIGN", (1, 2), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 1), (-1, -1), 0.25, colors.lightgrey),
        ("LINEBELOW", (0, 1), (-1, 1), 0.8, colors.black),
        ("LINEABOVE", (0, -1), (-1, -1), 0.8, colors.black),
    ]
    for i in range(len(tage)):
        start = 1 + i * n
        stil.append(("SPAN", (start, 0), (start + n - 1, 0)))
        stil.append(("LINEAFTER", (start + n - 1, 0), (start + n - 1, -1), 1.5, colors.black))
    for zeile in range(2 + len(namen), 2 + len(namen) + len(selbst_namen)):
        stil.append(("BACKGROUND", (0, zeile), (-1, zeile), BLASS))
    tabelle.setStyle(TableStyle(stil))
    doc.element(tabelle)
    doc.abstand()
    g = daten["gesamt"]
    doc.absatz(f"GESAMT: Ausgabestellen {g.personen} | Selbstabholer {daten['selbst_gesamt']} | "
               f"Alle Personen {daten['alle_personen']}")  # fmt: skip
    return doc.erzeugen()
