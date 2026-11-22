"""„Hier waren wir“ (ADR 0152): Stationen einer Tour als angefahren kennzeichnen. Die Station
bleibt stehen (man fährt manchmal noch einmal hin), ist aber deutlich als erledigt zu sehen; die
Tour am Handy springt zur nächsten offenen Station.

Kennzeichnen darf, wer an dem Tag auf der Tour eingetragen ist oder das Recht
``touren.besetzung`` hat (``start.darf()``), und nur am Tag selbst. Ein Lieferschein des Tages
gilt ebenfalls als „angefahren“."""

import datetime as dt

from django.utils import timezone

from apps.touren import ablauf, start
from apps.touren.models import Anfahrt, Station, Tour


class AnfahrtFehler(Exception):
    pass


def am_tag(tour: Tour, datum: dt.date) -> dict[int, Anfahrt]:
    return {a.station_id: a for a in Anfahrt.objects.filter(tour=tour, datum=datum)}


def _pruefen(tour: Tour, station: Station, benutzer) -> dt.date:
    datum = timezone.localdate()
    if not ablauf.faehrt_am(tour, datum) or not start.darf(benutzer, tour, datum):
        raise AnfahrtFehler("Sie sind für diese Tour heute nicht eingetragen.")
    if all(h.station_id != station.pk for h in ablauf.halte(tour, datum)):
        raise AnfahrtFehler("Diese Station steht heute nicht auf der Tour.")
    return datum


def markieren(tour: Tour, station: Station, benutzer) -> Anfahrt:
    datum = _pruefen(tour, station, benutzer)
    anfahrt, _ = Anfahrt.objects.get_or_create(
        tour=tour, station=station, datum=datum,
        defaults={"von": (benutzer.get_full_name() or benutzer.get_username())[:150]},
    )  # fmt: skip
    return anfahrt


def zuruecknehmen(tour: Tour, station: Station, benutzer) -> None:
    datum = _pruefen(tour, station, benutzer)
    Anfahrt.objects.filter(tour=tour, station=station, datum=datum).delete()


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Die Kennzeichen verschwinden nach 90 Tagen."""
    heute = heute or timezone.localdate()
    alt = Anfahrt.objects.filter(datum__lt=heute - dt.timedelta(days=90))
    anzahl = alt.count()
    alt.delete()
    return anzahl
