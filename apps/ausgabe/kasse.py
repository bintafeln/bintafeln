"""Kasse: Auswertung der Kontobuchungen nach Tag, Monat und Jahr (ADR 0014).

Grundlage sind allein die Buchungen. Sie überstehen einen Neuimport des Kundenstamms, deshalb
bleibt die Kasse auch rückwirkend vollständig, solange die Buchungsfrist läuft.
"""

from decimal import Decimal

from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncMonth

from apps.ausgabe.models import Buchung

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
