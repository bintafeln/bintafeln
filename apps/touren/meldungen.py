"""Meldungen zum Fahrzeug (ADR 0155): Die Fahrer melden beim Beenden der Tour (oder danach), was
am Fahrzeug aufgefallen ist – „Lampe defekt“, „getankt“, eine Anmerkung. Die Fahrdienstleitung
(Recht ``touren.fahrten``) sieht offene Meldungen auf ihrer Startseite und hakt sie ab.

Melden darf, wer die Fahrt fahren darf (``start.darf()``), am Tag der Fahrt."""

import datetime as dt

from django.utils import timezone

from apps.touren import start
from apps.touren.models import Fahrt, Fahrzeugmeldung, TourenEinstellungen


class MeldungFehler(Exception):
    pass


def _name(benutzer) -> str:
    return (benutzer.get_full_name() or benutzer.get_username())[:150]


def melden(fahrt: Fahrt, benutzer, art: str, text: str) -> Fahrzeugmeldung:
    text = " ".join((text or "").split())[:500]
    if not text:
        raise MeldungFehler("Bitte kurz beschreiben, was zu melden ist.")
    if art not in Fahrzeugmeldung.Art.values:
        art = Fahrzeugmeldung.Art.SONSTIGES
    if fahrt.datum != timezone.localdate():
        raise MeldungFehler("Zu dieser Fahrt lässt sich nichts mehr melden. Bitte im Büro melden.")
    if fahrt.tour is None or not start.darf(benutzer, fahrt.tour, fahrt.datum):
        raise MeldungFehler("Sie sind für diese Tour nicht eingetragen. Bitte im Büro melden.")
    return Fahrzeugmeldung.objects.create(
        fahrzeug=fahrt.fahrzeug, fahrzeug_name=fahrt.fahrzeug_name, fahrt=fahrt,
        tour_name=fahrt.tour_name, art=art, text=text, gemeldet_von=benutzer,
        gemeldet_von_name=_name(benutzer),
    )  # fmt: skip


def offene():
    return Fahrzeugmeldung.objects.filter(erledigt_am__isnull=True).select_related("fahrzeug")


def erledigen(meldung: Fahrzeugmeldung, benutzer, notiz: str = "") -> None:
    if meldung.erledigt_am is None:
        meldung.erledigt_am, meldung.erledigt_von = timezone.now(), _name(benutzer)
        meldung.erledigt_notiz = " ".join((notiz or "").split())[:300]
        meldung.save(update_fields=["erledigt_am", "erledigt_von", "erledigt_notiz"])


def wieder_oeffnen(meldung: Fahrzeugmeldung) -> None:
    meldung.erledigt_am, meldung.erledigt_von = None, ""
    meldung.save(update_fields=["erledigt_am", "erledigt_von"])


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Erledigte Meldungen werden so lange aufbewahrt wie Fahrten und Lieferscheine; offene
    bleiben, bis jemand sie abhakt."""
    heute = heute or timezone.localdate()
    jahre = TourenEinstellungen.laden().aufbewahrung_jahre
    try:
        grenze = heute.replace(year=heute.year - jahre)
    except ValueError:  # 29. Februar
        grenze = heute.replace(year=heute.year - jahre, day=28)
    alt = Fahrzeugmeldung.objects.filter(erledigt_am__date__lt=grenze)
    anzahl = alt.count()
    alt.delete()
    return anzahl
