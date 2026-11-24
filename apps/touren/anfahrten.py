"""Station ohne Lieferschein abhaken (ADR 0152, 0163): Stationen einer Tour als angefahren
kennzeichnen, mit dem Umstand („Keine Ware“, „Markt geschlossen“ …) und einer Anmerkung. Die
Station bleibt stehen (man fährt manchmal noch einmal hin), ist aber deutlich als erledigt zu
sehen; die Tour am Handy springt zur nächsten offenen Station.

Kennzeichnen darf, wer an dem Tag auf der Tour eingetragen ist oder das Recht
``touren.besetzung`` hat (``start.darf()``), und nur am Tag selbst. Ein Lieferschein des Tages
gilt ebenfalls als „angefahren“."""

import datetime as dt

from django.utils import timezone

from apps.touren import ablauf, start
from apps.touren.models import Anfahrt, Station, Tour, TourenEinstellungen, Umstand


class AnfahrtFehler(Exception):
    pass


def am_tag(tour: Tour, datum: dt.date) -> dict[tuple[int, int], Anfahrt]:
    """Die Anfahrten des Tages je (Station, Besuch)."""
    return {(a.station_id, a.durchgang): a
            for a in Anfahrt.objects.filter(tour=tour, datum=datum)}  # fmt: skip


def stand(tour: Tour, datum: dt.date, halte: list | None = None) -> list:
    """Die Halte des Tages mit ``h.anfahrt`` (abgehakt, oder None) und ``h.angefahren``.
    Steht eine Station mehrfach auf der Tour (ADR 0172), zählt jeder Besuch für sich: Der zweite
    ist erst erledigt, wenn er selbst abgehakt ist oder es an dem Tag einen zweiten Lieferschein
    der Station gibt."""
    from apps.touren import lieferscheine

    halte = ablauf.halte(tour, datum) if halte is None else halte
    da = am_tag(tour, datum)
    scheine = lieferscheine.anzahl_am_tag(datum, {h.station_id for h in halte})
    for h in halte:
        h.anfahrt = da.get((h.station_id, h.durchgang))
        h.angefahren = h.anfahrt is not None or scheine.get(h.station_id, 0) >= h.durchgang
    return halte


def fortschritt(tour: Tour, datum: dt.date) -> dict:
    """Wie weit die Tour ist: {"gesamt", "erledigt", "naechste" (Station | None), "prozent"}.
    Angefahren ist eine Station mit „Hier waren wir“ oder mit einem Lieferschein des Tages."""
    halte = stand(tour, datum)
    offen = [h.station for h in halte if not h.angefahren]
    erledigt = len(halte) - len(offen)
    return {"gesamt": len(halte), "erledigt": erledigt, "naechste": offen[0] if offen else None,
            "prozent": round(100 * erledigt / len(halte)) if halte else 0,
            "zusatz": sum(1 for h in halte if h.zusatz is not None)}  # fmt: skip


def _pruefen(tour: Tour, station: Station, benutzer, durchgang: int = 1) -> dt.date:
    datum = timezone.localdate()
    if not ablauf.faehrt_am(tour, datum) or not start.darf(benutzer, tour, datum):
        raise AnfahrtFehler("Sie sind für diese Tour heute nicht eingetragen.")
    if all((h.station_id, h.durchgang) != (station.pk, durchgang)
           for h in ablauf.halte(tour, datum)):  # fmt: skip
        raise AnfahrtFehler("Diese Station steht heute nicht auf der Tour.")
    return datum


def umstaende() -> list[Umstand]:
    """Was zur Wahl steht. Ist die Liste leer, wird ohne Umstand abgehakt."""
    return list(Umstand.objects.filter(aktiv=True))


def markieren(tour: Tour, station: Station, benutzer, umstand=None, anmerkung="",
              durchgang: int = 1) -> Anfahrt:  # fmt: skip
    """``umstand`` ist die pk aus ``umstaende()``; ohne Liste entfällt die Wahl. ``durchgang``:
    der wievielte Besuch der Station auf der Tour (bei mehrfach angefahrenen Stationen)."""
    datum = _pruefen(tour, station, benutzer, durchgang)
    anmerkung = " ".join((anmerkung or "").split())[:200]
    name = ""
    zur_wahl = umstaende()
    if zur_wahl:
        gewaehlt = next((u for u in zur_wahl if str(u.pk) == str(umstand)), None)
        if gewaehlt is None:
            raise AnfahrtFehler("Bitte wählen, was an der Station war.")
        if gewaehlt.anmerkung_pflicht and not anmerkung:
            raise AnfahrtFehler(f"Bitte bei „{gewaehlt.name}“ kurz dazuschreiben, was war.")
        name = gewaehlt.name
    anfahrt, _ = Anfahrt.objects.get_or_create(
        tour=tour, station=station, datum=datum, durchgang=durchgang,
        defaults={"von": (benutzer.get_full_name() or benutzer.get_username())[:150],
                  "umstand": name, "anmerkung": anmerkung},
    )  # fmt: skip
    return anfahrt


def zuruecknehmen(tour: Tour, station: Station, benutzer, durchgang: int = 1) -> None:
    datum = _pruefen(tour, station, benutzer, durchgang)
    Anfahrt.objects.filter(tour=tour, station=station, datum=datum, durchgang=durchgang).delete()


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Nach 90 Tagen verschwindet, wer abgehakt hat – und das Kennzeichen selbst, wenn kein
    Umstand dabeisteht. Mit Umstand bleibt es für die Statistik je Station, so lange wie die
    Lieferscheine (ohne Namen)."""
    heute = heute or timezone.localdate()
    alt = Anfahrt.objects.filter(datum__lt=heute - dt.timedelta(days=90))
    ohne = alt.filter(umstand="")
    anzahl = ohne.count()
    ohne.delete()
    alt.exclude(von="").update(von="")
    jahre = TourenEinstellungen.laden().aufbewahrung_jahre
    uralt = Anfahrt.objects.filter(datum__lt=heute - dt.timedelta(days=365 * jahre))
    anzahl += uralt.count()
    uralt.delete()
    return anzahl
