"""Tourstart (ADR 0150): Wer eine Tour aus dem Fahrerplan am Handy öffnet, bestätigt zuerst die
Besetzung („Seid ihr Peter und Paul?“) oder berichtigt sie. Eine Berichtigung steht für diesen
Tag als Ersatz im Fahrerplan – Plan, Aushang und Tour zeigen dasselbe.

Bestätigen und ändern darf nur, wer an dem Tag selbst auf der Tour eingetragen ist; wer das Recht
``touren.besetzung`` hat, auch sonst. Niemand trägt sich ohne dieses Recht selbst in eine fremde
Tour ein, und niemand nimmt sich selbst heraus."""

import datetime as dt

from django.db import transaction

from apps.core import module
from apps.konten import rollen
from apps.touren import ablauf
from apps.touren.models import Tour, Tourstart


class StartFehler(Exception):
    pass


NICHT_FREI = ("Diese Person kann an dem Tag nicht auf diesem Platz fahren (Ausfall gemeldet, "
              "schon eingeteilt oder kein Fahrer).")  # fmt: skip


def gefragt(tour: Tour, datum: dt.date) -> bool:
    """Gibt es zu dieser Tour an dem Tag eine Besetzung zu bestätigen? Nur für Touren aus dem
    Fahrerplan, an Tagen, an denen sie fährt."""
    return bool(tour.fahrdienst_tour_id and not tour.datum and module.aktiv("fahrdienst")
                and ablauf.faehrt_am(tour, datum))  # fmt: skip


def gestartet(tour: Tour, datum: dt.date) -> Tourstart | None:
    return Tourstart.objects.filter(tour=tour, datum=datum).first()


def darf_alle(benutzer) -> bool:
    return rollen.hat_recht(benutzer, "touren.besetzung")


def darf(benutzer, tour: Tour, datum: dt.date) -> bool:
    return darf_alle(benutzer) or ablauf.faehrt_mit(tour, datum, ablauf.person_von(benutzer))


def plaetze(tour: Tour, datum: dt.date) -> list[dict]:
    """Je Platz der Tour im Fahrerplan: {"nr", "rolle", "person", "gast", "offen", "wahl"}.
    ``wahl``: wer dort stattdessen fahren könnte (Springer zuerst)."""
    from apps.fahrdienst import plan

    ergebnis = []
    for ft, liste in plan.tage([datum])[0][1]:
        if ft.pk != tour.fahrdienst_tour_id:
            continue
        for p in liste:
            springer, weitere = plan.verfuegbar(datum, nur_fahrer=p.platz == 1)
            person = None if p.ausfall else p.wer
            ergebnis.append({
                "nr": p.platz, "rolle": p.name, "person": person, "gast": p.gast,
                "offen": p.fehlt, "wahl": springer + weitere,
            })  # fmt: skip
    return ergebnis


def frage(liste: list[dict]) -> str:
    """„Seid ihr Peter Probe und Paul Probe?“ – mit den Namen aus dem Fahrerplan."""
    namen = [p["person"].name if p["person"] else p["gast"] for p in liste]
    namen = [n for n in namen if n]
    if not namen:
        return "Für diese Tour ist niemand eingetragen. Wer fährt?"
    if len(namen) == 1:
        return f"Bist du {namen[0]}?"
    return f"Seid ihr {', '.join(namen[:-1])} und {namen[-1]}?"


def aenderbar(tour: Tour, datum: dt.date) -> bool:
    """Lässt sich die Besetzung des Tages ändern? Tour aus dem Fahrerplan, die an dem Tag fährt."""
    return gefragt(tour, datum)


@transaction.atomic
def aendern(tour: Tour, datum: dt.date, benutzer, wahl: dict[int, int] | None = None,
            gaeste: dict[int, str] | None = None) -> bool:  # fmt: skip
    """Die Besetzung des Tages berichtigen: ``wahl`` = {Platz: pk der Person}, ``gaeste`` =
    {Platz: Name eines Mitfahrers ohne Konto} (nur Beifahrerplätze). Alles steht danach als
    Ersatz im Fahrerplan. Rückgabe: Wurde etwas geändert?"""
    from apps.fahrdienst import plan

    if not aenderbar(tour, datum):
        raise StartFehler("Diese Tour fährt an dem Tag nicht nach dem Fahrerplan.")
    if not darf(benutzer, tour, datum):
        raise StartFehler("Sie sind für diese Tour nicht eingetragen. Bitte im Büro melden.")
    liste = plaetze(tour, datum)
    neu, gast_neu = {}, {}
    for p in liste:
        pk = (wahl or {}).get(p["nr"])
        name = ((gaeste or {}).get(p["nr"]) or "").strip()[:100]
        if pk and not (p["person"] is not None and p["person"].pk == pk):
            person = next((w for w in p["wahl"] if w.pk == pk), None)
            if person is None or person.pk in {n.pk for n in neu.values()}:
                raise StartFehler(NICHT_FREI)
            neu[p["nr"]] = person
        elif name and not pk and name != p["gast"]:
            if p["nr"] == 1:
                raise StartFehler("Auf dem Fahrerplatz kann kein Gast stehen.")
            gast_neu[p["nr"]] = name
    if not darf_alle(benutzer):
        ich = ablauf.person_von(benutzer)
        danach = [None if p["nr"] in gast_neu else neu.get(p["nr"], p["person"]) for p in liste]
        if ich is None or all(d is None or d.pk != ich.pk for d in danach):
            raise StartFehler("Sie können sich nicht selbst aus der Tour nehmen. Das Büro "
                              "trägt den Ersatz ein.")  # fmt: skip
    von = benutzer.get_username()
    for nr, person in neu.items():
        plan.ersatz_eintragen(datum, tour.fahrdienst_tour, nr, person, von)
    for nr, name in gast_neu.items():
        plan.ersatz_eintragen(datum, tour.fahrdienst_tour, nr, None, von, gast=name)
    return bool(neu or gast_neu)


@transaction.atomic
def bestaetigen(tour: Tour, datum: dt.date, benutzer, wahl: dict[int, int] | None = None,
                gaeste: dict[int, str] | None = None):  # fmt: skip
    """Hält fest, dass die Besetzung stimmt – nach einer Berichtigung (``aendern()``)."""
    geaendert = aendern(tour, datum, benutzer, wahl, gaeste)
    start = gestartet(tour, datum) or Tourstart(tour=tour, datum=datum)
    start.bestaetigt_von = (benutzer.get_full_name() or benutzer.get_username())[:150]
    start.geaendert = start.geaendert or geaendert
    start.save()
    return start


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Bestätigungen verschwinden nach 90 Tagen (wie kurzfristige Touren)."""
    from django.utils import timezone

    heute = heute or timezone.localdate()
    alt = Tourstart.objects.filter(datum__lt=heute - dt.timedelta(days=90))
    anzahl = alt.count()
    alt.delete()
    return anzahl
