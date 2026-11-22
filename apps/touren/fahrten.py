"""Fahrten (ADR 0151): Beginn und Ende einer Tour am Handy mit Fahrzeug und Kilometerstand –
Grundlage für Fahrtenbuch und Statistik.

Beginnen und beenden darf, wer an dem Tag auf der Tour eingetragen ist oder das Recht
``touren.besetzung`` hat (wie beim Bestätigen der Besetzung, ``start.darf()``). Beendet wird
dort, wo das Fahrzeug stehen bleibt; einen Ort prüft bintafeln nicht. Das Büro berichtigt
Kilometerstände im Fahrtenbuch (Recht ``touren.fahrten``)."""

import datetime as dt

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.touren import ablauf, start
from apps.touren.models import Fahrt, Fahrzeug, Tour, TourenEinstellungen

MAX_KM_AM_TAG = 1500  # mehr an einem Tag ist ein Tippfehler


class FahrtFehler(Exception):
    pass


def fahrzeuge() -> list[Fahrzeug]:
    return list(Fahrzeug.objects.filter(aktiv=True))


def heute(tour: Tour, datum: dt.date) -> Fahrt | None:
    return Fahrt.objects.filter(tour=tour, datum=datum).select_related("fahrzeug").first()


def letzter_stand(fahrzeug: Fahrzeug | None) -> int | None:
    """Der aktuelle Kilometerstand des Fahrzeugs – als Vorschlag für die Abfahrt. Er steht am
    Fahrzeug, wird mit jeder Fahrt fortgeschrieben und lässt sich in den Einstellungen ändern."""
    return None if fahrzeug is None else fahrzeug.kilometerstand


def staende() -> dict[int, int]:
    """Kilometerstand je Fahrzeug (pk → Stand) für das Formular am Handy."""
    return {f.pk: f.kilometerstand for f in fahrzeuge() if f.kilometerstand is not None}


def _stand_merken(fahrzeug: Fahrzeug | None, km: int | None) -> None:
    if fahrzeug is not None and km is not None and fahrzeug.kilometerstand != km:
        fahrzeug.kilometerstand = km
        fahrzeug.save(update_fields=["kilometerstand"])


def zahl(wert) -> int:
    """Kilometerstand aus dem Formular: „123.456“, „123 456“ oder „123456“."""
    text = str(wert or "").replace(".", "").replace(" ", "").replace("\u00a0", "").strip()
    if not text.isdigit() or len(text) > 7:
        raise FahrtFehler("Bitte den Kilometerstand als ganze Zahl eintragen.")
    return int(text)


def _name(benutzer) -> str:
    return (benutzer.get_full_name() or benutzer.get_username())[:150]


def _pruefen(km_start: int, km_ende: int | None) -> None:
    if km_ende is None:
        return
    if km_ende < km_start:
        raise FahrtFehler(f"Der Kilometerstand bei Ankunft ({km_ende}) ist kleiner als bei "
                          f"Abfahrt ({km_start}).")  # fmt: skip
    if km_ende - km_start > MAX_KM_AM_TAG:
        raise FahrtFehler(f"Das wären {km_ende - km_start} km an einem Tag – bitte den "
                          "Kilometerstand prüfen.")  # fmt: skip


@transaction.atomic
def beginnen(tour: Tour, benutzer, km_start, fahrzeug_pk=None) -> Fahrt:
    datum = timezone.localdate()
    if not ablauf.faehrt_am(tour, datum):
        raise FahrtFehler("Diese Tour fährt heute nicht.")
    if not start.darf(benutzer, tour, datum):
        raise FahrtFehler("Sie sind für diese Tour nicht eingetragen. Bitte im Büro melden.")
    if heute(tour, datum):
        raise FahrtFehler("Die Fahrt ist schon begonnen.")
    zur_wahl = fahrzeuge()
    fahrzeug = next((f for f in zur_wahl if str(f.pk) == str(fahrzeug_pk)), None)
    if zur_wahl and fahrzeug is None:
        raise FahrtFehler("Bitte das Fahrzeug wählen.")
    km = zahl(km_start)
    wer = ", ".join(b["name"] for b in ablauf.besetzung(tour, datum) if not b["offen"])
    try:
        with transaction.atomic():
            fahrt = Fahrt.objects.create(
                tour=tour, tour_name=tour.name, datum=datum, fahrzeug=fahrzeug,
                fahrzeug_name=str(fahrzeug) if fahrzeug else "", besetzung=wer[:300],
                km_start=km, begonnen_am=timezone.now(), begonnen_von=benutzer,
                begonnen_von_name=_name(benutzer),
            )  # fmt: skip
    except IntegrityError:  # zwei Handys gleichzeitig
        raise FahrtFehler("Die Fahrt ist schon begonnen.") from None
    _stand_merken(fahrzeug, km)
    return fahrt


def beenden(fahrt: Fahrt, benutzer, km_ende) -> Fahrt:
    if fahrt.beendet_am:
        raise FahrtFehler("Die Fahrt ist schon beendet.")
    if fahrt.tour is None or not start.darf(benutzer, fahrt.tour, fahrt.datum):
        raise FahrtFehler("Sie sind für diese Tour nicht eingetragen. Bitte im Büro melden.")
    km = zahl(km_ende)
    _pruefen(fahrt.km_start, km)
    fahrt.km_ende, fahrt.beendet_am = km, timezone.now()
    fahrt.beendet_von, fahrt.beendet_von_name = benutzer, _name(benutzer)
    fahrt.save()
    _stand_merken(fahrt.fahrzeug, km)
    return fahrt


def berichtigen(fahrt: Fahrt, benutzer, km_start, km_ende, fahrzeug_pk=None) -> Fahrt:
    """Das Büro trägt Kilometerstände nach oder berichtigt sie; eine nicht beendete Fahrt gilt
    mit dem Stand bei Ankunft als beendet."""
    start_km = zahl(km_start)
    ende_km = zahl(km_ende) if str(km_ende or "").strip() else None
    _pruefen(start_km, ende_km)
    fahrzeug = Fahrzeug.objects.filter(pk=fahrzeug_pk).first() if fahrzeug_pk else None
    fahrt.km_start, fahrt.km_ende = start_km, ende_km
    fahrt.fahrzeug, fahrt.fahrzeug_name = fahrzeug, str(fahrzeug) if fahrzeug else ""
    if ende_km is not None and fahrt.beendet_am is None:
        fahrt.beendet_am = timezone.now()
    fahrt.berichtigt_von = _name(benutzer)
    fahrt.save()
    if (
        fahrzeug
        and not Fahrt.objects.filter(fahrzeug=fahrzeug, begonnen_am__gt=fahrt.begonnen_am).exists()
    ):
        # die letzte Fahrt des Fahrzeugs bestimmt seinen Stand
        _stand_merken(fahrzeug, ende_km if ende_km is not None else start_km)
    return fahrt


def fristen_anwenden(heute_: dt.date | None = None) -> int:
    """Fahrten werden so lange aufbewahrt wie Lieferscheine (Einstellungen der Touren)."""
    heute_ = heute_ or timezone.localdate()
    jahre = TourenEinstellungen.laden().aufbewahrung_jahre
    try:
        grenze = heute_.replace(year=heute_.year - jahre)
    except ValueError:  # 29. Februar
        grenze = heute_.replace(year=heute_.year - jahre, day=28)
    alt = Fahrt.objects.filter(datum__lt=grenze)
    anzahl = alt.count()
    alt.delete()
    return anzahl
