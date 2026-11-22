"""Regeln der Abholtouren (ADR 0148): wann eine Tour fährt, welche Stationen sie an einem Tag
anfährt, wer fährt, die Route in Google Maps und das Verschicken kurzfristiger Touren."""

import datetime as dt
from urllib.parse import urlencode

from django.db import transaction
from django.db.models import Max
from django.utils import timezone

from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.core import module
from apps.touren.models import GOOGLE_MAPS_ROUTE, Halt, Station, Tour

# Google Maps nimmt in einem Link höchstens neun Zwischenstopps (im mobilen Browser ohne App
# nur drei); längere Touren werden in Abschnitte geteilt.
MAX_ZWISCHENSTOPPS = 9


def kuerzel(datum: dt.date) -> str:
    return WOCHENTAGE[datum.weekday()]


def _fahrdienst_an() -> bool:
    return module.aktiv("fahrdienst")


def faehrt_am(tour: Tour, datum: dt.date) -> bool:
    if not tour.aktiv:
        return False
    if tour.datum:
        return tour.datum == datum
    if tour.fahrdienst_tour_id and _fahrdienst_an():
        # eigene Fahrtage grenzen ein: „Montag Katernberg“ ist die Tour „Katernberg“ am Montag
        ft, tage = tour.fahrdienst_tour, wochentage(tour.fahrtage)
        return ft.aktiv and ft.faehrt_am(datum) and (not tage or kuerzel(datum) in tage)
    tage = wochentage(tour.fahrtage)
    return not tage or kuerzel(datum) in tage


def touren_am(datum: dt.date) -> list[Tour]:
    """Alle Touren des Tages: erst die regelmäßigen, dann die kurzfristigen."""
    alle = Tour.objects.filter(aktiv=True).select_related("fahrdienst_tour")
    heute = [t for t in alle if faehrt_am(t, datum)]
    return sorted(heute, key=lambda t: (t.kurzfristig, t.name.lower(), t.pk))


def halte(tour: Tour, datum: dt.date | None = None) -> list[Halt]:
    """Die Halte in Fahrtreihenfolge; mit ``datum`` nur die, die an dem Tag angefahren werden
    (Wochentage des Halts, aktive Station)."""
    alle = list(tour.halte.select_related("station"))
    if datum is None:
        return alle
    tag = kuerzel(datum)
    return [h for h in alle if h.station.aktiv
            and (not wochentage(h.wochentage) or tag in wochentage(h.wochentage))]  # fmt: skip


def besetzung(tour: Tour, datum: dt.date) -> list[dict]:
    """Wer an dem Tag fährt: [{"person": Adresse | None, "name", "rolle", "offen"}]. Bei einer
    Tour aus dem Fahrerplan die Plätze von dort (mit Ersatz und Ausfall), sonst die gewählten
    Personen."""
    if tour.fahrdienst_tour_id and not tour.datum and _fahrdienst_an():
        from apps.fahrdienst import plan

        for ft, plaetze in plan.tage([datum])[0][1]:
            if ft.pk == tour.fahrdienst_tour_id:
                return [
                    {"person": None if p.ausfall else p.wer, "rolle": p.name, "offen": p.fehlt,
                     "name": "offen" if p.fehlt else (p.gast or (p.wer.name if p.wer else ""))}
                    for p in plaetze if p.wer is not None or p.gast or p.fehlt
                ]  # fmt: skip
        return []
    # eigene und kurzfristige Tour: Fahrer, bis zu zwei Beifahrer, dazu ein Gast ohne Konto
    plaetze = [(tour.fahrer, "Fahrer"), (tour.beifahrer, "Beifahrer"),
               (tour.beifahrer2, "Beifahrer")]  # fmt: skip
    zeilen = [{"person": p, "name": p.name, "rolle": rolle, "offen": False}
              for p, rolle in plaetze if p is not None]  # fmt: skip
    dabei = {z["person"].pk for z in zeilen}
    zeilen += [
        {"person": p, "name": p.name, "rolle": "", "offen": False}
        for p in tour.personen.order_by("nachname", "vorname")
        if p.pk not in dabei
    ]
    if tour.gast:
        zeilen.append({"person": None, "name": tour.gast, "rolle": "Gast", "offen": False})
    return zeilen


def faehrt_mit(tour: Tour, datum: dt.date, person) -> bool:
    return person is not None and any(
        b["person"] is not None and b["person"].pk == person.pk for b in besetzung(tour, datum)
    )


def person_von(benutzer):
    from apps.adressen.models import Adresse

    return Adresse.objects.filter(konto=benutzer).first() if benutzer else None


def meine(benutzer, datum: dt.date) -> list[Tour]:
    person = person_von(benutzer)
    return [t for t in touren_am(datum) if faehrt_mit(t, datum, person)]


def routen(stationen: list[Station]) -> list[dict]:
    """Die ganze Tour als Links zu Google Maps: [{"url", "von", "bis"}] (Nummern der Stationen,
    ab 1). Start ist der eigene Standort; ein Link fasst höchstens zehn Stationen (neun
    Zwischenstopps und das Ziel)."""
    links = []
    schritt = MAX_ZWISCHENSTOPPS + 1
    for anfang in range(0, len(stationen), schritt):
        teil = stationen[anfang : anfang + schritt]
        werte = {"api": "1", "destination": teil[-1].ziel, "travelmode": "driving"}
        if len(teil) > 1:
            werte["waypoints"] = "|".join(s.ziel for s in teil[:-1])
        links.append({"url": GOOGLE_MAPS_ROUTE + urlencode(werte), "von": anfang + 1,
                      "bis": anfang + len(teil)})  # fmt: skip
    return links


# --- Halte pflegen ------------------------------------------------------------------------------


def halt_anhaengen(tour: Tour, station: Station, wochentage_: str = "") -> Halt:
    letzte = tour.halte.aggregate(m=Max("reihenfolge"))["m"] or 0
    halt, _ = Halt.objects.get_or_create(
        tour=tour, station=station,
        defaults={"reihenfolge": letzte + 1, "wochentage": wochentage_},
    )  # fmt: skip
    return halt


@transaction.atomic
def halt_bewegen(halt: Halt, schritte: int) -> None:
    """Verschiebt den Halt um ``schritte`` Plätze (−1 = früher) und nummeriert neu durch."""
    folge = list(Halt.objects.select_for_update().filter(tour=halt.tour_id))
    alt = next(i for i, h in enumerate(folge) if h.pk == halt.pk)
    neu = min(max(alt + schritte, 0), len(folge) - 1)
    folge.insert(neu, folge.pop(alt))
    for nr, h in enumerate(folge, start=1):
        if h.reihenfolge != nr:
            h.reihenfolge = nr
            h.save(update_fields=["reihenfolge"])


# --- Kurzfristige Touren verschicken ------------------------------------------------------------


def nachricht(tour: Tour, adresse: str) -> tuple[str, str]:
    """Betreff und Text der Mail an die Fahrer; ``adresse`` ist der Link zur Tour."""
    tag = tour.datum or timezone.localdate()
    zeilen = [f"für {tag:%d.%m.%Y} ist die Tour „{tour.name}“ für Sie eingetragen.", ""]
    if tour.hinweis:
        zeilen += [tour.hinweis, ""]
    zeilen.append("Stationen in dieser Reihenfolge:")
    for nr, h in enumerate(halte(tour, tag), start=1):
        s = h.station
        zeilen.append(
            f"{nr}. {s.name}, {s.anschrift}" + (f" ({s.abholzeit})" if s.abholzeit else "")
        )
    mit = ", ".join(b["name"] for b in besetzung(tour, tag))
    if mit:
        zeilen += ["", f"Es fahren: {mit}"]
    zeilen += ["", f"Tour mit Navigation öffnen: {adresse}"]
    return f"Tour „{tour.name}“ am {tag:%d.%m.%Y}", "\n".join(zeilen)


def senden(tour: Tour, adresse: str) -> tuple[list[str], list[str]]:
    """Schickt die Tour an alle, die mitfahren. Rückgabe: (Namen mit Mail, Namen ohne Mail)."""
    from apps.core import benachrichtigung

    tag = tour.datum or timezone.localdate()
    personen = [b["person"] for b in besetzung(tour, tag) if b["person"] is not None]
    mit = [p for p in personen if p.mail]
    ohne = [p.name for p in personen if not p.mail]
    if mit:
        betreff, text = nachricht(tour, adresse)
        benachrichtigung.melden("touren_tour", [p.mail for p in mit], betreff, text,
                                schluessel=tour.pk)  # fmt: skip
        tour.gesendet_am = timezone.now()
        tour.save(update_fields=["gesendet_am"])
    return [p.name for p in mit], ohne


def tour_offen(schluessel) -> bool:
    """Für gesammelte Benachrichtigungen: Die Tour gibt es noch und sie ist nicht vorbei."""
    tour = (
        Tour.objects.filter(pk=schluessel, aktiv=True).first()
        if str(schluessel).isdigit()
        else None
    )
    return tour is not None and (tour.datum is None or tour.datum >= timezone.localdate())


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Kurzfristige Touren verschwinden 90 Tage nach ihrem Tag (mit ihren Halten)."""
    heute = heute or timezone.localdate()
    alt = Tour.objects.filter(datum__lt=heute - dt.timedelta(days=90))
    anzahl = alt.count()
    alt.delete()
    return anzahl
