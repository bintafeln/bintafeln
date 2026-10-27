"""Arbeitszeiterfassung: Kommen und Gehen stempeln, vergessenes Gehen erkennen (ADR 0020)."""

import datetime as dt

from django.utils import timezone

from apps.personal.models import ArbeitszeitEinstellungen, Zeitbuchung


class StempelFehler(ValueError):
    pass


def darf_stempeln(benutzer) -> bool:
    """Fest Angestellte immer, Ehrenamtliche nur, wenn es in den Einstellungen erlaubt ist."""
    if not benutzer.is_authenticated or not benutzer.is_active:
        return False
    if benutzer.beschaeftigung == benutzer.Beschaeftigung.FEST:
        return True
    return ArbeitszeitEinstellungen.laden().ehrenamtliche_stempeln


def _grenze(jetzt=None) -> dt.datetime:
    stunden = ArbeitszeitEinstellungen.laden().offen_hoechstens_stunden
    return (jetzt or timezone.now()) - dt.timedelta(hours=stunden)


def laufend(benutzer, jetzt=None) -> Zeitbuchung | None:
    """Die offene Buchung, zu der jetzt noch ein „Gehen“ passt."""
    return (
        benutzer.zeitbuchungen.filter(ende__isnull=True, beginn__gte=_grenze(jetzt))
        .order_by("-beginn")
        .first()
    )


def vergessen(benutzer=None, jetzt=None):
    """Offene Buchungen, die älter als die Grenze sind: Hier fehlt ein „Gehen“."""
    buchungen = Zeitbuchung.objects.filter(ende__isnull=True, beginn__lt=_grenze(jetzt))
    if benutzer is not None:
        buchungen = buchungen.filter(benutzer=benutzer)
    return buchungen.select_related("benutzer").order_by("beginn")


def kommen(benutzer, jetzt=None) -> Zeitbuchung:
    jetzt = jetzt or timezone.now()
    if laufend(benutzer, jetzt):
        raise StempelFehler("Sie sind schon eingestempelt. Bitte zuerst „Gehen“ stempeln.")
    return Zeitbuchung.objects.create(benutzer=benutzer, beginn=jetzt.replace(microsecond=0))


def gehen(benutzer, jetzt=None) -> Zeitbuchung:
    jetzt = jetzt or timezone.now()
    buchung = laufend(benutzer, jetzt)
    if buchung is None:
        raise StempelFehler("Kein offenes „Kommen“. Bitte die Zeit vom Personal nachtragen lassen.")
    buchung.ende = max(jetzt.replace(microsecond=0), buchung.beginn + dt.timedelta(minutes=1))
    buchung.save()
    return buchung


def in_pause(benutzer, jetzt=None) -> Zeitbuchung | None:
    """Nicht eingestempelt, aber heute schon gearbeitet: die letzte Buchung von heute (für
    „Pause beenden“; die Lücke bis zum nächsten Kommen zählt als Pause)."""
    jetzt = jetzt or timezone.now()
    if laufend(benutzer, jetzt):
        return None
    heute = timezone.localtime(jetzt).date()
    letzte = benutzer.zeitbuchungen.filter(ende__isnull=False).order_by("-ende").first()
    return letzte if letzte and timezone.localtime(letzte.ende).date() == heute else None


def ueberschneidung(buchung: Zeitbuchung) -> Zeitbuchung | None:
    """Eine andere Buchung derselben Person, die sich mit dieser zeitlich überschneidet."""
    ende = buchung.ende or buchung.beginn + dt.timedelta(minutes=1)
    andere = Zeitbuchung.objects.filter(benutzer_id=buchung.benutzer_id).exclude(pk=buchung.pk)
    for b in andere.filter(beginn__lt=ende):
        if (b.ende is None and b.beginn >= buchung.beginn) or (b.ende and b.ende > buchung.beginn):
            return b
    return None
