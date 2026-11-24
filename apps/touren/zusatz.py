"""Zusatzstopps (ADR 0156): Im Lauf des Tages kommt ein Abholauftrag dazu. Das Büro hängt ihn
an eine Tour des Tages; die Mannschaft kann ihrer eigenen Tour selbst einen Stopp einfügen. Die
Station ist eine aus der Liste oder eine freie Adresse – die wird als Station angelegt.

Einfügen darf, wer an dem Tag auf der Tour eingetragen ist oder das Recht ``touren.besetzung``
hat (``start.darf()``); die Mannschaft nur am Tag selbst. Der Stopp gilt nur für diesen Tag."""

import datetime as dt

from django.utils import timezone

from apps.touren import ablauf, anfahrten, heuler, start
from apps.touren.models import Station, Tour, Zusatzstopp


class ZusatzFehler(Exception):
    pass


def darf(benutzer, tour: Tour, datum: dt.date) -> bool:
    if not ablauf.faehrt_am(tour, datum):
        return False
    if start.darf_alle(benutzer):
        return datum >= timezone.localdate()
    return datum == timezone.localdate() and start.darf(benutzer, tour, datum)


def naechste_stelle(tour: Tour, datum: dt.date) -> int:
    """So viele Stationen stehen vor dem nächsten offenen Halt – dort kommt „als Nächstes“ hin."""
    halte = anfahrten.stand(tour, datum)
    for nr, h in enumerate(halte):
        if not h.angefahren:
            return nr
    return len(halte)


def einfuegen(tour: Tour, datum: dt.date, benutzer, station: Station, hinweis: str = "",
              am_ende: bool = False) -> Zusatzstopp:  # fmt: skip
    if not darf(benutzer, tour, datum):
        raise ZusatzFehler("Sie können an dieser Tour keinen Zusatzstopp einfügen.")
    if not station.aktiv:
        raise ZusatzFehler("Diese Station wird nicht mehr angefahren.")
    halte = ablauf.halte(tour, datum)
    # Eine Station darf mehrfach auf der Tour stehen (ADR 0172) – als Zusatzstopp aber nur einmal
    if any(h.zusatz is not None and h.station_id == station.pk for h in halte):
        raise ZusatzFehler(f"„{station.name}“ ist an dem Tag schon als Zusatzstopp eingefügt.")
    stelle = len(halte) if am_ende else naechste_stelle(tour, datum)
    # gezählt wird in festen Stationen, damit die Stelle stabil bleibt, wenn weitere dazukommen
    vorher = sum(1 for h in halte[:stelle] if h.zusatz is None)
    stopp = Zusatzstopp.objects.create(
        tour=tour, datum=datum, station=station, nach=vorher,
        hinweis=" ".join((hinweis or "").split())[:300], angelegt_von=benutzer,
        angelegt_von_name=(benutzer.get_full_name() or benutzer.get_username())[:150],
        vom_buero=not ablauf.faehrt_mit(tour, datum, ablauf.person_von(benutzer)),
    )  # fmt: skip
    heuler.melden(stopp)
    return stopp


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Zusatzstopps verschwinden nach 90 Tagen."""
    heute = heute or timezone.localdate()
    alt = Zusatzstopp.objects.filter(datum__lt=heute - dt.timedelta(days=90))
    anzahl = alt.count()
    alt.delete()
    return anzahl
