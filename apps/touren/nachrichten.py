"""Nachricht der Fahrdienstleitung an die Mannschaft einer Tour (ADR 0168).

Wer Touren plant, schickt der Mannschaft einer Tour – oder allen Touren des Tages – einen kurzen
Text, für heute oder einen kommenden Tag. Die Mannschaft bekommt
- eine Push-Nachricht aufs Handy (wer das auf „Mein Konto“ eingeschaltet hat) und
- in bintafeln denselben roten Brief wie bei einem neuen Stopp vom Büro (``heuler``), über jeder
  Seite, bis jemand aus der Mannschaft „Gelesen“ tippt.

Beides erst, wenn die Mannschaft die Fahrt begonnen hat (``heuler.unterwegs()``); vorher wartet die
Nachricht still, auch eine für einen kommenden Tag.

Die Fahrdienstleitung sieht je Nachricht, ob und von wem sie bestätigt wurde: Bleibt sie offen,
hilft nur der Anruf. Für vergangene Tage gibt es keine Nachrichten; nach 30 Tagen werden sie
gelöscht."""

import datetime as dt

from django.urls import reverse
from django.utils import timezone

from apps.core import push
from apps.konten import rollen
from apps.touren import ablauf, heuler
from apps.touren.models import Kurztext, Tour, Tournachricht

AUFBEWAHREN_TAGE = 30


class NachrichtFehler(ValueError):
    pass


def darf_senden(benutzer) -> bool:
    return rollen.hat_recht(benutzer, "touren.planen")


def kurztexte() -> list[str]:
    """Die fertigen Texte der Tafel zum Antippen."""
    return list(Kurztext.objects.filter(aktiv=True).values_list("text", flat=True))


def adresse(nachricht: Tournachricht) -> str:
    return f"{reverse('touren:fahren', args=[nachricht.tour_id])}?tag={nachricht.datum:%Y-%m-%d}"


def senden(
    touren_: list[Tour], text: str, benutzer, datum: dt.date | None = None
) -> list[Tournachricht]:
    """Schickt den Text an die Mannschaft jeder der Touren – für heute oder einen kommenden Tag und
    nur an Touren, die an dem Tag fahren. Liefert die angelegten Nachrichten."""
    text = " ".join((text or "").split())[:300]
    if not text:
        raise NachrichtFehler("Bitte einen Text eingeben.")
    heute = timezone.localdate()
    datum = datum or heute
    if datum < heute:
        raise NachrichtFehler("Für einen vergangenen Tag lässt sich keine Nachricht schicken.")
    fahren = [t for t in touren_ if ablauf.faehrt_am(t, datum)]
    if not fahren:
        wann = "Heute" if datum == heute else f"Am {datum:%d.%m.%Y}"
        raise NachrichtFehler(f"{wann} fährt keine der gewählten Touren.")
    von = (benutzer.get_full_name() or benutzer.get_username())[:150]
    neu = [Tournachricht.objects.create(tour=t, datum=datum, text=text, von=benutzer, von_name=von)
           for t in fahren]  # fmt: skip
    for n in neu:
        # Brief und Push erst, wenn die Mannschaft die Fahrt begonnen hat; sonst beim Beginn
        if heuler.unterwegs(n.tour, datum):
            _push(n)
    return neu


def nachholen(tour, datum: dt.date) -> None:
    """Die Fahrt hat begonnen: Push für die Nachrichten, die bis dahin gewartet haben."""
    for n in Tournachricht.objects.filter(tour=tour, datum=datum, gesehen_am=None).select_related(
        "tour"
    ):
        _push(n)


def _push(n: Tournachricht) -> None:
    konten = heuler.mannschaft(n.tour, n.datum)
    if konten:
        titel, link, kennung = f"Nachricht: {n.tour.name}", adresse(n), f"nachricht-{n.pk}"
        push.nach_speichern(
            lambda k=konten, t=titel, x=n.text, li=link, ke=kennung: push.an_benutzer(
                k, t, x, li, ke))  # fmt: skip


def offene(benutzer, datum: dt.date | None = None) -> list[Tournachricht]:
    """Nachrichten von heute an die eigenen Touren, die noch niemand bestätigt hat – nur von
    Touren, deren Fahrt begonnen hat. Eine Nachricht für einen kommenden Tag wartet bis dahin."""
    datum = datum or timezone.localdate()
    offen = (
        Tournachricht.objects.filter(datum=datum, gesehen_am=None)
        .select_related("tour", "tour__fahrdienst_tour")
        .order_by("gesendet_am", "pk")
    )
    if not offen:
        return []
    person = ablauf.person_von(benutzer)
    return [
        n for n in offen
        if ablauf.faehrt_mit(n.tour, datum, person) and heuler.unterwegs(n.tour, datum)
    ]  # fmt: skip


def gesehen(nachricht: Tournachricht, benutzer) -> bool:
    """Bestätigen darf nur, wer auf der Tour mitfährt; die erste Bestätigung zählt."""
    if not ablauf.faehrt_mit(nachricht.tour, nachricht.datum, ablauf.person_von(benutzer)):
        return False
    Tournachricht.objects.filter(pk=nachricht.pk, gesehen_am=None).update(
        gesehen_am=timezone.now(),
        gesehen_von_name=(benutzer.get_full_name() or benutzer.get_username())[:150],
    )
    return True


def am(datum: dt.date) -> list[Tournachricht]:
    """Für die Fahrdienstleitung: alle Nachrichten des Tages, die neueste zuerst."""
    return list(Tournachricht.objects.filter(datum=datum).select_related("tour")
                .order_by("-gesendet_am", "-pk"))  # fmt: skip


def fristen_anwenden(heute: dt.date | None = None) -> int:
    heute = heute or timezone.localdate()
    alt = Tournachricht.objects.filter(datum__lt=heute - dt.timedelta(days=AUFBEWAHREN_TAGE))
    anzahl = alt.count()
    alt.delete()
    return anzahl
