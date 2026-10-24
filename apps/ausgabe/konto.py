"""Kundenkonto: Buchen am Empfang, Vorschlag für Vorauszahlungen, Fristen (ADR 0014).

Der Kontostand steht in ``Haushalt.kontostand`` (Anfangsstand aus dem Import) und ändert sich
mit jeder Buchung um ``haben − soll``. Alle Änderungen laufen über die Funktionen hier, in einer
Transaktion mit gesperrter Haushaltszeile.
"""

import calendar
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from auditlog.context import disable_auditlog
from django.db import transaction
from django.utils import timezone

from apps.ausgabe.ampel import WOCHENTAGE
from apps.ausgabe.models import AusgabeEinstellungen, Buchung
from apps.core.feiertage import feiertage, ist_feiertag
from apps.core.models import TafelEinstellungen
from apps.kunden.models import Haushalt, abholfrist_beginn

NULL = Decimal("0.00")
MONATE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]  # fmt: skip


class KontoFehler(ValueError):
    pass


def euro(betrag: Decimal) -> str:
    """1234.5 → '1.234,50 €'"""
    text = f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} €"


@dataclass
class Zahlung:
    """Ergebnis einer gebuchten Abholung für die Anzeige am Empfang."""

    bar: Decimal
    vom_konto: Decimal
    kontostand: Decimal


def _gesperrt(haushalt) -> Haushalt:
    return Haushalt.objects.select_for_update().get(pk=haushalt.pk)


def _buchen(h: Haushalt, **felder) -> Buchung:
    buchung = Buchung.objects.create(haushalt=h, kundennummer=h.kundennummer, **felder)
    h.kontostand = (h.kontostand or NULL) + buchung.wirkung
    h.save(update_fields=["kontostand"])
    return buchung


@transaction.atomic
def abholung_buchen(abholung, beitrag, zahlweise, einstellungen, stelle, von) -> Zahlung:
    """Bucht den Beitrag einer Abholung je nach Zahlweise."""
    h = _gesperrt(abholung.haushalt)
    stand = h.kontostand or NULL
    if zahlweise == Buchung.Zahlweise.GUTHABEN:
        vom_konto = min(beitrag, max(stand, NULL))
    elif zahlweise == Buchung.Zahlweise.ANSCHREIBEN:
        if not einstellungen.anschreiben_erlaubt:
            raise KontoFehler("Anschreiben ist in den Einstellungen nicht erlaubt.")
        vom_konto = beitrag
    else:
        vom_konto = NULL
    bar = beitrag - vom_konto
    if beitrag:
        _buchen(
            h,
            art=Buchung.Art.ABHOLUNG,
            zahlweise=zahlweise,
            datum=abholung.datum,
            soll=beitrag,
            haben=bar,
            bar=bar,
            abholung=abholung,
            ausgabestelle=stelle,
            eingetragen_von=von,
        )
    return Zahlung(bar=bar, vom_konto=vom_konto, kontostand=h.kontostand or NULL)


@transaction.atomic
def einzahlen(haushalt, betrag, stelle, von, bemerkung="") -> Buchung:
    if betrag is None or betrag <= 0:
        raise KontoFehler("Bitte einen Betrag größer als 0 angeben.")
    return _buchen(
        _gesperrt(haushalt),
        art=Buchung.Art.EINZAHLUNG,
        haben=betrag,
        bar=betrag,
        ausgabestelle=stelle,
        bemerkung=bemerkung[:200],
        eingetragen_von=von,
    )


@transaction.atomic
def korrigieren(haushalt, betrag, begruendung, von) -> Buchung:
    """Korrektur ohne Bargeld: positiv schreibt gut, negativ belastet."""
    if not betrag:
        raise KontoFehler("Bitte einen Betrag ungleich 0 angeben.")
    if not begruendung.strip():
        raise KontoFehler("Bitte eine Begründung angeben.")
    return _buchen(
        _gesperrt(haushalt),
        art=Buchung.Art.KORREKTUR,
        soll=-betrag if betrag < 0 else NULL,
        haben=betrag if betrag > 0 else NULL,
        bemerkung=begruendung.strip()[:200],
        eingetragen_von=von,
    )


@transaction.atomic
def zuruecknehmen(buchung: Buchung) -> None:
    """Löscht eine Buchung und stellt den Kontostand davor wieder her."""
    if buchung.haushalt_id:
        h = _gesperrt(buchung.haushalt)
        h.kontostand = (h.kontostand or NULL) - buchung.wirkung
        h.save(update_fields=["kontostand"])
    buchung.delete()


# --- Vorschlag für Vorauszahlungen -------------------------------------------------------


@dataclass
class Vorschlag:
    titel: str
    tage: list[dt.date]
    beitrag: Decimal
    erklaerung: list[str] = field(default_factory=list)

    @property
    def betrag(self) -> Decimal:
        return self.beitrag * len(self.tage)


def _tage(von: dt.date, bis: dt.date, wochentage: list[str]) -> list[dt.date]:
    anzahl = (bis - von).days + 1
    tage = (von + dt.timedelta(days=i) for i in range(max(anzahl, 0)))
    return [t for t in tage if WOCHENTAGE[t.weekday()] in wochentage]


def _begrenzen(tage, abgeholt, einstellungen) -> tuple[list[dt.date], str]:
    """Kürzt die Tage auf die erlaubte Höchstzahl; liefert dazu einen erklärenden Satz."""
    hoechst = einstellungen.max_abholungen
    zeitraum = einstellungen.zeitraum
    if zeitraum == AusgabeEinstellungen.Zeitraum.VIERZEHN_TAGE:
        return tage, f"Die Höchstzahl ({hoechst} je 14 Tage) ist im Vorschlag nicht berücksichtigt."
    if zeitraum == AusgabeEinstellungen.Zeitraum.MONAT:

        def gruppe(t):
            return (t.year, t.month)

        einheit = "Kalendermonat"
    else:

        def gruppe(t):
            return t.isocalendar()[:2]

        einheit = "Kalenderwoche"
    ergebnis, gezaehlt = [], {}
    for t in abgeholt:
        gezaehlt[gruppe(t)] = gezaehlt.get(gruppe(t), 0) + 1
    for t in tage:
        if gezaehlt.get(gruppe(t), 0) < hoechst:
            ergebnis.append(t)
            gezaehlt[gruppe(t)] = gezaehlt.get(gruppe(t), 0) + 1
    weggelassen = len(tage) - len(ergebnis)
    satz = f"Höchstens {hoechst} Abholung{'en' if hoechst != 1 else ''} je {einheit}"
    if weggelassen:
        satz += f": {weggelassen} Abholtag{'e' if weggelassen != 1 else ''} nicht gezählt."
    else:
        satz += " ist eingehalten."
    return ergebnis, satz


def vorschlaege(h, heute, einstellungen, beitrag) -> tuple[list[Vorschlag], str]:
    """Vorschläge für den Rest dieses und den ganzen nächsten Monat, mit Erklärung.

    Liefert die Vorschläge und gegebenenfalls einen Hinweis, warum es keine gibt.
    """
    if not beitrag:
        return [], "Kein Vorschlag: In den Einstellungen ist kein Beitrag festgelegt."
    gruppe = h.kundengruppe
    wochentage = [t.strip() for t in (gruppe.wochentage if gruppe else "").split(",") if t]
    if not wochentage:
        return [], (
            "Kein Vorschlag: Die Kundengruppe hat keine festen Wochentage. "
            "Bitte den Betrag selbst eintragen."
        )
    abgeholt = [a.datum for a in h.abholungen.all()]
    land = TafelEinstellungen.laden().bundesland
    heute_abgeholt = heute in abgeholt
    start = heute + dt.timedelta(days=1) if heute_abgeholt else heute
    monatsende = heute.replace(day=calendar.monthrange(heute.year, heute.month)[1])
    naechster = monatsende + dt.timedelta(days=1)
    naechstes_ende = naechster.replace(day=calendar.monthrange(naechster.year, naechster.month)[1])
    ab_text = (
        "ab morgen, weil heute schon abgeholt wurde"
        if heute_abgeholt
        else "ab heute, weil heute noch nicht abgeholt wurde"
    )
    zeitraeume = [
        (f"Rest {MONATE[heute.month - 1]}", start, monatsende, ab_text),
        (f"Ganzer {MONATE[naechster.month - 1]}", naechster, naechstes_ende, None),
    ]
    ergebnis = []
    for titel, von, bis, zusatz in zeitraeume:
        tage = _tage(von, bis, wochentage)
        frei = [t for t in tage if ist_feiertag(t, land)]
        tage = [t for t in tage if t not in frei]
        if h.ausweis_gueltig_bis and any(t > h.ausweis_gueltig_bis for t in tage):
            tage = [t for t in tage if t <= h.ausweis_gueltig_bis]
            ausweis = f"Nur bis zum Ablauf des Ausweises am {h.ausweis_gueltig_bis:%d.%m.%Y}."
        else:
            ausweis = None
        tage, grenze = _begrenzen(tage, abgeholt, einstellungen)
        if not tage:
            continue
        v = Vorschlag(titel=titel, tage=tage, beitrag=beitrag)
        v.erklaerung = [
            f"{len(tage)} Abholtag{'e' if len(tage) != 1 else ''} × {euro(beitrag)} "
            f"= {euro(v.betrag)}",
            f"Gezählt: {', '.join(f'{WOCHENTAGE[t.weekday()]} {t:%d.%m.}' for t in tage)} "
            f"(Kundengruppe „{gruppe.name}“: {', '.join(wochentage)})",
        ]
        if zusatz:
            v.erklaerung.append(f"Gezählt {zusatz}.")
        if ausweis:
            v.erklaerung.append(ausweis)
        v.erklaerung.append(grenze)
        if frei:
            namen = ", ".join(
                f"{WOCHENTAGE[t.weekday()]} {t:%d.%m.} ({feiertage(t.year, land)[t]})" for t in frei
            )
            v.erklaerung.append(f"Nicht gezählt, weil Feiertag: {namen}.")
        if land:
            v.erklaerung.append(
                "Ausfallende Ausgabetage (z. B. Betriebsferien) sind nicht berücksichtigt."
            )
        else:
            v.erklaerung.append(
                "Feiertage sind nicht berücksichtigt (in den Einstellungen der Tafel ist kein "
                "Bundesland gewählt), ausfallende Ausgabetage ebenfalls nicht."
            )
        ergebnis.append(v)
    if not ergebnis:
        return [], "Kein Vorschlag: Bis Ende des nächsten Monats ist kein Abholtag mehr möglich."
    return ergebnis, ""


# --- Fristen -----------------------------------------------------------------------------


def buchungsfristen_anwenden(heute: dt.date | None = None) -> int:
    """Anonymisiert Buchungen nach der Frist für Abholungen, löscht sie nach der Buchungsfrist.

    Liefert die Zahl der gelöschten Buchungen.
    """
    heute = heute or timezone.localdate()
    jahre = AusgabeEinstellungen.laden().buchungen_aufbewahren_jahre
    try:
        grenze = heute.replace(year=heute.year - jahre)
    except ValueError:  # 29. Februar
        grenze = heute.replace(year=heute.year - jahre, day=28)
    with disable_auditlog():  # Fristablauf ist kein fachliches Ereignis je Buchung
        Buchung.objects.filter(datum__lt=abholfrist_beginn(heute)).exclude(
            haushalt=None, kundennummer="", bemerkung="", eingetragen_von=""
        ).update(haushalt=None, kundennummer="", bemerkung="", eingetragen_von="")
        return Buchung.objects.filter(datum__lt=grenze).delete()[0]
