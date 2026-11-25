"""Kunden herausnehmen, die lange unentschuldigt gefehlt haben (ADR 0177).

Ein Knopf auf der Kundenseite erledigt, wofür man sich sonst durch mehrere Masken klickt: Der
Ausweis endet gestern, eine Sperre läuft ab heute für die eingestellte Zeit. Damit fällt der Kunde
aus der Kundengruppe (ADR 0061) und steht auf „gesperrt“ (ADR 0176). Die Sperre merkt sich das
Ausweisdatum von vorher, damit sich die Herausnahme zurücknehmen lässt.
"""

import calendar
import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.core import papierkorb
from apps.kunden import gruppen, historie
from apps.kunden.models import Haushalt, HaushaltEreignis, KundenEinstellungen, Sperre

BEGRUENDUNG = "Lange unentschuldigt gefehlt"
S = Haushalt.Status


class HerausnehmenFehler(Exception):
    pass


def _name(benutzer) -> str:
    return (benutzer.get_full_name() or benutzer.get_username())[:100]


def grenze(heute: dt.date | None = None) -> dt.date:
    """Wer zuletzt vor diesem Tag abgeholt hat, ist lange nicht gekommen."""
    heute = heute or timezone.localdate()
    return heute - dt.timedelta(days=KundenEinstellungen.laden().herausnehmen_nach_tagen)


def sperre_bis(heute: dt.date) -> dt.date:
    """Heute plus die eingestellten Monate (derselbe Tag, am Monatsende der letzte)."""
    monate = heute.month - 1 + KundenEinstellungen.laden().herausnehmen_sperre_monate
    jahr, monat = heute.year + monate // 12, monate % 12 + 1
    return dt.date(jahr, monat, min(heute.day, calendar.monthrange(jahr, monat)[1]))


def laufende(h: Haushalt, heute: dt.date | None = None) -> Sperre | None:
    """Die Sperre einer Herausnahme, die noch läuft – sie lässt sich zurücknehmen."""
    heute = heute or timezone.localdate()
    return next((s for s in h.sperren.filter(herausnahme=True) if s.ist_aktiv(heute)), None)


def faellig(h: Haushalt, heute: dt.date | None = None) -> bool:
    """Ob der Knopf „Kunden herausnehmen“ erscheint: wie die Liste „Lange nicht gekommen“ – seit
    der eingestellten Zeit keine Abholung (oder noch nie) –, und der Kunde ist weder schon
    gesperrt noch beendet oder verstorben."""
    heute = heute or timezone.localdate()
    if h.status in (S.GESPERRT, *Haushalt.NICHT_MEHR):
        return False
    if any(s.ist_aktiv(heute) for s in h.sperren.all()):
        return False
    return h.letzter_besuch is None or h.letzter_besuch < grenze(heute)


@transaction.atomic
def herausnehmen(h: Haushalt, benutzer, begruendung: str = "") -> Sperre:
    heute = timezone.localdate()
    if not faellig(h, heute):
        raise HerausnehmenFehler("Dieser Kunde erfüllt die Bedingung „lange nicht gekommen“ "
                                 "nicht (mehr) oder ist schon gesperrt.")  # fmt: skip
    begruendung = " ".join(begruendung.split())[:300] or BEGRUENDUNG
    vorher = historie.schnappschuss(h)
    alt = h.ausweis_gueltig_bis
    sperre = Sperre.objects.create(
        haushalt=h, von=heute, bis=sperre_bis(heute), begruendung=begruendung,
        eingetragen_von=_name(benutzer), herausnahme=True, ausweis_vorher=alt,
    )  # fmt: skip
    h.ausweis_gueltig_bis = heute - dt.timedelta(days=1)
    h.geaendert_am, h.geaendert_von = timezone.now(), benutzer.get_username()
    h.save(update_fields=["ausweis_gueltig_bis", "geaendert_am", "geaendert_von"])
    gruppen.pruefen(h, heute)  # Kundengruppe weg, Status nach Sperre und Ausweis
    historie.festhalten(
        h.kundennummer, vorher, historie.schnappschuss(h),
        quelle=HaushaltEreignis.Quelle.BEARBEITUNG, von=benutzer.get_username(),
        zusatz=f"Kunde herausgenommen: {begruendung}, gesperrt bis {sperre.bis:%d.%m.%Y}",
    )  # fmt: skip
    return sperre


@transaction.atomic
def zuruecknehmen(h: Haushalt, benutzer) -> None:
    """Sperre der Herausnahme weg (in den Papierkorb) und das Ausweisdatum von vorher wieder
    eintragen. Die Kundengruppe kommt nicht von selbst zurück – der Platz kann vergeben sein."""
    heute = timezone.localdate()
    sperre = laufende(h, heute)
    if sperre is None:
        raise HerausnehmenFehler("Zu diesem Kunden läuft keine Herausnahme.")
    vorher = historie.schnappschuss(h)
    h.ausweis_gueltig_bis = sperre.ausweis_vorher
    h.geaendert_am, h.geaendert_von = timezone.now(), benutzer.get_username()
    h.save(update_fields=["ausweis_gueltig_bis", "geaendert_am", "geaendert_von"])
    papierkorb.loeschen(
        benutzer, "Sperre", f"{h.kundennummer} – {sperre}", sperre, recht="kunden.herausnehmen",
        kundennummer=h.kundennummer,
    )  # fmt: skip
    gruppen.pruefen(h, heute)
    historie.festhalten(
        h.kundennummer, vorher, historie.schnappschuss(h),
        quelle=HaushaltEreignis.Quelle.BEARBEITUNG, von=benutzer.get_username(),
        zusatz="Herausnahme zurückgenommen",
    )  # fmt: skip
