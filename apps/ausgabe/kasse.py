"""Kasse: Auswertung der Kontobuchungen nach Tag, Monat und Jahr (ADR 0014).

Grundlage sind allein die Buchungen. Sie überstehen einen Neuimport des Kundenstamms, deshalb
bleibt die Kasse auch rückwirkend vollständig, solange die Buchungsfrist läuft.
"""

from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from reportlab.lib.pagesizes import A4, landscape

from apps.ausgabe.konto import euro
from apps.ausgabe.models import Buchung
from apps.core.pdf import Pdf

NULL = Decimal("0.00")

ABHOLUNG = Q(art=Buchung.Art.ABHOLUNG)

# Schlüssel, Bezeichnung, Ausdruck. Reihenfolge = Spalten in der Anzeige.
KENNZAHLEN = [
    ("bar_gesamt", "Bar eingenommen", Sum("bar")),
    ("abholungen", "Abholungen mit Beitrag", Count("pk", filter=ABHOLUNG)),
    ("beitraege", "Beiträge gesamt", Sum("soll", filter=ABHOLUNG)),
    ("beitraege_bar", "davon bar", Sum("bar", filter=ABHOLUNG)),
    (
        "vom_konto",
        "davon aus Guthaben",
        Sum(F("soll") - F("haben"), filter=ABHOLUNG & Q(zahlweise=Buchung.Zahlweise.GUTHABEN)),
    ),
    (
        "angeschrieben",
        "davon angeschrieben",
        Sum(F("soll") - F("haben"), filter=ABHOLUNG & Q(zahlweise=Buchung.Zahlweise.ANSCHREIBEN)),
    ),
    ("einzahlungen", "Einzahlungen (bar)", Sum("bar", filter=Q(art=Buchung.Art.EINZAHLUNG))),
    (
        "korrekturen",
        "Korrekturen (ohne Bargeld)",
        Sum(F("haben") - F("soll"), filter=Q(art=Buchung.Art.KORREKTUR)),
    ),
]
SPALTEN = [(schluessel, name) for schluessel, name, _ in KENNZAHLEN]
_AUSDRUECKE = {schluessel: ausdruck for schluessel, _, ausdruck in KENNZAHLEN}


def _bereinigen(zeile: dict) -> dict:
    """Leere Summen (keine passenden Buchungen) als 0 statt None."""
    return {k: (NULL if v is None and k in _AUSDRUECKE else v) for k, v in zeile.items()}


def summe(buchungen) -> dict:
    return _bereinigen(buchungen.aggregate(**_AUSDRUECKE))


def nach(buchungen, gruppe) -> list[dict]:
    """Kennzahlen je Gruppe. ``gruppe`` ist ein Feldname oder ein Ausdruck (als 'gruppe')."""
    zeilen = (
        buchungen.annotate(gruppe=gruppe if not isinstance(gruppe, str) else F(gruppe))
        .values("gruppe")
        .annotate(**_AUSDRUECKE)
        .order_by("gruppe")
    )
    return [_bereinigen(z) for z in zeilen]


def nach_ausgabestelle(buchungen) -> list[dict]:
    return nach(buchungen, "ausgabestelle__name")


def nach_tag(buchungen) -> list[dict]:
    return nach(buchungen, "datum")


def nach_monat(buchungen) -> list[dict]:
    return nach(buchungen, TruncMonth("datum"))


def bericht_pdf(ansicht, titel, stelle, zeilen, summe_werte, einzelbuchungen) -> bytes:
    """Kassenabschluss (Tag) oder Kassenbericht (Monat, Jahr) als PDF im Querformat.

    ``zeilen`` und ``summe_werte`` haben die Form der Kasse-Ansicht: je Zeile ein Titel und
    (Bezeichnung, Wert, ist Betrag) je Spalte.
    """

    def zelle(wert, betrag):
        return euro(wert) if betrag else str(wert)

    art = "Kassenabschluss" if ansicht == "tag" else "Kassenbericht"
    doc = Pdf(art, f"{titel}{f' · {stelle.name}' if stelle else ''}", landscape(A4))
    gruppe = {"tag": "Ausgabestelle", "monat": "Tag", "jahr": "Monat"}[ansicht]
    breite = 0.84 / len(SPALTEN)
    daten = [[z["titel"], *(zelle(w, b) for _, w, b in z["werte"])] for z in zeilen]
    if daten:
        daten.append(["Summe", *(zelle(w, b) for _, w, b in summe_werte)])
    doc.tabelle(
        [gruppe, *(name for _, name in SPALTEN)],
        daten,
        breiten=[0.16] + [breite] * len(SPALTEN),
        rechts=range(1, len(SPALTEN) + 1),
        summe=True,
    )
    doc.absatz(
        "„Bar eingenommen“ = bar gezahlte Beiträge + Einzahlungen. Verrechnetes Guthaben, "
        "Angeschriebenes und Korrekturen sind kein Bargeld.",
        klein=True,
    )
    if einzelbuchungen is not None:
        doc.ueberschrift("Buchungen des Tages")
        doc.tabelle(
            ["Uhrzeit", "Kundennummer", "Art", "Soll", "Haben", "bar", "Ausgabestelle", "Von"],
            [
                [
                    f"{timezone.localtime(b.zeitpunkt):%H:%M}",
                    b.kundennummer,
                    b.get_art_display()
                    + (f" ({b.get_zahlweise_display()})" if b.zahlweise else ""),
                    euro(b.soll),
                    euro(b.haben),
                    euro(b.bar),
                    b.ausgabestelle.name if b.ausgabestelle else "",
                    b.eingetragen_von,
                ]
                for b in einzelbuchungen
            ],
            breiten=[0.08, 0.12, 0.2, 0.1, 0.1, 0.1, 0.15, 0.15],
            rechts=[3, 4, 5],
        )
    if ansicht == "tag":
        doc.abstand()
        doc.unterschriften(["Bargeld gezählt (Euro)", "Gezählt von", "Geprüft von"])
    return doc.erzeugen()
