"""Nachricht der Fahrdienstleitung an die Mannschaft einer Tour (ADR 0168).

Wer Touren plant, schickt der Mannschaft einer Tour von heute – oder allen Touren von heute – einen
kurzen Text. Die Mannschaft bekommt
- eine Push-Nachricht aufs Handy (wer das auf „Mein Konto“ eingeschaltet hat) und
- in bintafeln denselben roten Brief wie bei einem neuen Stopp vom Büro (``heuler``), über jeder
  Seite, bis jemand aus der Mannschaft „Gelesen“ tippt.

Die Fahrdienstleitung sieht je Nachricht, ob und von wem sie bestätigt wurde: Bleibt sie offen,
hilft nur der Anruf. Nachrichten gibt es nur für heute; sie werden nach 30 Tagen gelöscht."""

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


def senden(touren_: list[Tour], text: str, benutzer) -> list[Tournachricht]:
    """Schickt den Text an die Mannschaft jeder der Touren – nur für heute und nur an Touren, die
    heute fahren. Liefert die angelegten Nachrichten."""
    text = " ".join((text or "").split())[:300]
    if not text:
        raise NachrichtFehler("Bitte einen Text eingeben.")
    heute = timezone.localdate()
    fahren = [t for t in touren_ if ablauf.faehrt_am(t, heute)]
    if not fahren:
        raise NachrichtFehler("Heute fährt keine der gewählten Touren.")
    von = (benutzer.get_full_name() or benutzer.get_username())[:150]
    neu = [Tournachricht.objects.create(tour=t, datum=heute, text=text, von=benutzer, von_name=von)
           for t in fahren]  # fmt: skip
    for n in neu:
        konten = heuler.mannschaft(n.tour, heute)
        if konten:
            titel, link, kennung = f"Nachricht: {n.tour.name}", adresse(n), f"nachricht-{n.pk}"
            push.nach_speichern(
                lambda k=konten, t=titel, x=n.text, li=link, ke=kennung: push.an_benutzer(
                    k, t, x, li, ke))  # fmt: skip
    return neu


def offene(benutzer, datum: dt.date | None = None) -> list[Tournachricht]:
    """Nachrichten von heute an die eigenen Touren, die noch niemand bestätigt hat."""
    datum = datum or timezone.localdate()
    offen = (
        Tournachricht.objects.filter(datum=datum, gesehen_am=None)
        .select_related("tour", "tour__fahrdienst_tour")
        .order_by("gesendet_am", "pk")
    )
    if not offen:
        return []
    person = ablauf.person_von(benutzer)
    return [n for n in offen if ablauf.faehrt_mit(n.tour, datum, person)]


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
