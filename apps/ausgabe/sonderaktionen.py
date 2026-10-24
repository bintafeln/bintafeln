"""Sonderaktionen am Einlass (ADR 0032): wer darf teilnehmen, wie viel, eintragen, Fristen."""

import datetime as dt

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.ausgabe.models import Sonderaktion, Teilnahme
from apps.kunden.models import abholfrist_beginn


class SonderaktionFehler(ValueError):
    pass


def menge(aktion: Sonderaktion, erwachsene: int, kinder: int) -> int:
    if aktion.menge == Sonderaktion.Menge.JE_KIND:
        return kinder
    if aktion.menge == Sonderaktion.Menge.JE_PERSON:
        return erwachsene + kinder
    return 1


def fuer_haushalt(h, heute: dt.date, erwachsene: int, kinder: int) -> list[dict]:
    """Heute laufende Aktionen mit Teilnahme (falls schon eingetragen) und Berechtigung."""
    aktionen = Sonderaktion.objects.filter(von__lte=heute, bis__gte=heute).prefetch_related(
        "auswahl"
    )
    teilnahmen = {
        t.aktion_id: t
        for t in Teilnahme.objects.filter(kundennummer=h.kundennummer, aktion__in=aktionen)
        .select_related("auswahl")
    }  # fmt: skip
    ergebnis = []
    for a in aktionen:
        anzahl = menge(a, erwachsene, kinder)
        grund = ""
        if a.nur_mit_kindern and not kinder:
            grund = "Nur für Haushalte mit Kindern."
        elif anzahl < 1:
            grund = "Keine Personen, für die es etwas gibt."
        ergebnis.append({"aktion": a, "auswahl": list(a.auswahl.all()), "menge": anzahl,
                         "teilnahme": teilnahmen.get(a.pk), "grund": grund})  # fmt: skip
    return ergebnis


def eintragen(aktion, h, *, auswahl, erwachsene, kinder, stelle, von, heute=None) -> Teilnahme:
    heute = heute or timezone.localdate()
    if not aktion.laeuft(heute):
        raise SonderaktionFehler(f"„{aktion}“ läuft heute nicht.")
    if aktion.nur_mit_kindern and not kinder:
        raise SonderaktionFehler(f"„{aktion}“ gibt es nur für Haushalte mit Kindern.")
    anzahl = menge(aktion, erwachsene, kinder)
    if anzahl < 1:
        raise SonderaktionFehler(f"Bei „{aktion}“ bekommt dieser Haushalt nichts.")
    optionen = list(aktion.auswahl.all())
    if optionen and auswahl not in optionen:
        raise SonderaktionFehler("Bitte eine Auswahl treffen.")
    try:
        with transaction.atomic():
            return Teilnahme.objects.create(
                aktion=aktion, kundennummer=h.kundennummer, auswahl=auswahl, menge=anzahl,
                ausgabestelle=stelle, eingetragen_von=von[:100],
            )  # fmt: skip
    except IntegrityError:
        raise SonderaktionFehler(f"„{aktion}“ ist für diesen Haushalt schon eingetragen.") from None


def zuruecknehmen(teilnahme: Teilnahme, heute=None) -> None:
    """Nur am selben Tag (Versehen am Einlass)."""
    heute = heute or timezone.localdate()
    if timezone.localdate(teilnahme.zeitpunkt) != heute:
        raise SonderaktionFehler("Nur am selben Tag zurücknehmbar.")
    teilnahme.delete()


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Teilnahmen werden so lange aufbewahrt wie Abholungen."""
    grenze = timezone.make_aware(dt.datetime.combine(abholfrist_beginn(heute), dt.time()))
    return Teilnahme.objects.filter(zeitpunkt__lt=grenze).delete()[0]
