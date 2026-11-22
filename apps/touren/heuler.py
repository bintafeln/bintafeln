"""Neuer Stopp vom Büro: unübersehbar bei der Mannschaft (ADR 0159).

Fügt das Büro einer Tour einen Zusatzstopp ein, bekommt die Mannschaft
- eine Push-Nachricht aufs Handy (wer das auf „Mein Konto“ eingeschaltet hat, ``apps.core.push``),
  die beim Antippen zur Tour führt, und
- in bintafeln einen roten Brief über der Seite, bis jemand aus der Mannschaft „Gesehen“ tippt.

Stopps, die die Mannschaft selbst einfügt, lösen nichts aus. Das Büro sieht an der Tour, ob und von
wem der Stopp gesehen wurde."""

import datetime as dt

from django.urls import reverse
from django.utils import timezone

from apps.core import push
from apps.touren import ablauf
from apps.touren.models import Zusatzstopp


def mannschaft(tour, datum: dt.date) -> list:
    """Konten derer, die an dem Tag auf der Tour eingetragen sind."""
    return [b["person"].konto for b in ablauf.besetzung(tour, datum)
            if b["person"] is not None and b["person"].konto_id]  # fmt: skip


def adresse(stopp: Zusatzstopp) -> str:
    """Die Tour am Tag des Stopps."""
    return f"{reverse('touren:fahren', args=[stopp.tour_id])}?tag={stopp.datum:%Y-%m-%d}"


def melden(stopp: Zusatzstopp) -> None:
    """Push-Nachricht an die Mannschaft – nur bei Stopps vom Büro für heute."""
    if not stopp.vom_buero or stopp.datum != timezone.localdate():
        return
    konten = mannschaft(stopp.tour, stopp.datum)
    if not konten:
        return
    s = stopp.station
    text = f"{s.name}, {s.strasse_hausnummer}, {s.plz} {s.ort}"
    if stopp.hinweis:
        text += f"\n{stopp.hinweis}"
    titel, link, kennung = f"Neuer Stopp: {stopp.tour.name}", adresse(stopp), f"stopp-{stopp.pk}"
    push.nach_speichern(lambda: push.an_benutzer(konten, titel, text, link, kennung))


def offene(benutzer, datum: dt.date | None = None) -> list[Zusatzstopp]:
    """Stopps vom Büro auf den eigenen Touren von heute, die noch niemand bestätigt hat."""
    datum = datum or timezone.localdate()
    stopps = (
        Zusatzstopp.objects.filter(datum=datum, vom_buero=True, gesehen_am=None)
        .select_related("tour", "tour__fahrdienst_tour", "station")
        .order_by("angelegt_am")
    )
    if not stopps:
        return []
    person = ablauf.person_von(benutzer)
    return [s for s in stopps if ablauf.faehrt_mit(s.tour, datum, person)]


def gesehen(stopp: Zusatzstopp, benutzer) -> bool:
    """Bestätigen darf nur, wer auf der Tour mitfährt; die erste Bestätigung zählt."""
    if not ablauf.faehrt_mit(stopp.tour, stopp.datum, ablauf.person_von(benutzer)):
        return False
    Zusatzstopp.objects.filter(pk=stopp.pk, gesehen_am=None).update(
        gesehen_am=timezone.now(),
        gesehen_von_name=(benutzer.get_full_name() or benutzer.get_username())[:150],
    )
    return True
