"""Stationen der Touren aus ``tourstationen.csv`` (docs/importformat-touren.md) übernehmen.

Je Zeile eine Station auf einer Tour. Für jede Tour, die in der Datei vorkommt, ersetzt die
Datei deren ganze Stationsfolge; Touren, die nicht vorkommen, bleiben unverändert. Unbekannte
Touren werden als eigene Touren angelegt – heißt eine Tour im Fahrerplan genauso, wird sie mit
ihr verbunden. Stationen werden über ihre ``kennung`` gefunden; dieselbe Station darf mehrfach
auf einer Tour stehen (ADR 0172).
"""

import csv
import io
from dataclasses import dataclass, field

from django.db import transaction

from apps.adressen.importieren import ImportFehler, text_lesen
from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.core import module
from apps.touren.models import Halt, Station, Tour

__all__ = ["ImportFehler", "text_lesen", "pruefen", "uebernehmen", "SPALTEN"]

SPALTEN = ["tour", "reihenfolge", "station", "wochentage"]
PFLICHT = ["tour", "reihenfolge", "station"]
MAX_ZEILEN = 5000
TAGESNAMEN = {
    lang: kurz
    for kurz, lang in zip(
        WOCHENTAGE,
        ["montag", "dienstag", "mittwoch", "donnerstag", "freitag", "samstag", "sonntag"],
        strict=True,
    )
} | {k.lower(): k for k in WOCHENTAGE}


@dataclass
class Bericht:
    # Name der Tour -> [(reihenfolge, Kennung der Station, Name der Station, Wochentage)]
    touren: dict[str, list[tuple[int, str, str, str]]] = field(default_factory=dict)
    neue_touren: list[str] = field(default_factory=list)
    fehler: list[tuple[int, str]] = field(default_factory=list)

    @property
    def halte(self) -> int:
        return sum(len(h) for h in self.touren.values())


def wochentag_im_namen(name: str) -> tuple[str, str]:
    """„Montag Katernberg“ → ("Mo", "Katernberg"): Beginnt der Name mit einem Wochentag, ist es
    die Tour „Katernberg“ aus dem Fahrerplan in der Reihenfolge dieses Tages. Sonst ("", name)."""
    erstes, _, rest = name.strip().partition(" ")
    if rest.strip() and erstes.strip(".").lower() in TAGESNAMEN:
        return TAGESNAMEN[erstes.strip(".").lower()], rest.strip()
    return "", name


def _vorhandene() -> dict[str, Tour]:
    return {t.name.lower(): t for t in Tour.objects.filter(datum__isnull=True)}


def pruefen(text: str) -> Bericht:
    zeilen = text.splitlines()
    if not zeilen:
        raise ImportFehler("Die Datei ist leer.")
    trenner = ";" if zeilen[0].count(";") >= zeilen[0].count(",") else ","
    leser = csv.DictReader(io.StringIO(text, newline=""), delimiter=trenner)
    kopf = [(k or "").strip().lower() for k in (leser.fieldnames or [])]
    leser.fieldnames = kopf
    fehlt = [s for s in PFLICHT if s not in kopf]
    if fehlt:
        raise ImportFehler(
            f"Es fehlen die Spalten {', '.join(fehlt)} (erste Zeile, Trennzeichen Semikolon). "
            f"Gefunden: {', '.join(k for k in kopf if k) or 'nichts'}."
        )
    stationen = {s.kennung: s for s in Station.objects.all()}
    vorhandene = _vorhandene()
    bericht = Bericht()
    namen: dict[str, str] = {}  # klein -> Schreibweise der ersten Zeile
    for nummer, zeile in enumerate(leser, start=2):
        if nummer > MAX_ZEILEN + 1:
            raise ImportFehler(f"Mehr als {MAX_ZEILEN} Zeilen; bitte aufteilen.")
        w = {s: (zeile.get(s) or "").strip() for s in SPALTEN}
        if not any(w.values()):
            continue
        if not w["tour"] or not w["station"]:
            bericht.fehler.append((nummer, "tour oder station fehlt"))
            continue
        if len(w["tour"]) > 80:
            bericht.fehler.append((nummer, "tour ist länger als 80 Zeichen"))
            continue
        if not w["reihenfolge"].isdigit() or not 0 < int(w["reihenfolge"]) < 1000:
            bericht.fehler.append((nummer, f"reihenfolge „{w['reihenfolge']}“ ist keine Zahl"))
            continue
        station = stationen.get(w["station"])
        if station is None:
            bericht.fehler.append((nummer, f"Station „{w['station']}“ gibt es nicht (Kennung)"))
            continue
        tage = ", ".join(wochentage(w["wochentage"]))
        if w["wochentage"] and not tage:
            bericht.fehler.append((nummer, f"keine Wochentage erkannt in „{w['wochentage']}“"))
            continue
        name = namen.setdefault(w["tour"].lower(), w["tour"])
        liste = bericht.touren.setdefault(name, [])
        # Dieselbe Station darf mehrfach auf einer Tour stehen (ADR 0172), z. B. zum Abladen
        liste.append((int(w["reihenfolge"]), station.kennung, station.name, tage))
    for name, liste in bericht.touren.items():
        liste.sort(key=lambda h: h[0])
        if name.lower() not in vorhandene:
            bericht.neue_touren.append(name)
    return bericht


@transaction.atomic
def uebernehmen(bericht: Bericht, von: str) -> tuple[int, int]:
    """Rückgabe: (Touren, Halte)."""
    vorhandene = _vorhandene()
    stationen = {s.kennung: s for s in Station.objects.all()}
    im_fahrerplan = {}
    if module.aktiv("fahrdienst"):
        from apps.fahrdienst.models import Tour as FahrdienstTour

        im_fahrerplan = {t.name.lower(): t for t in FahrdienstTour.objects.all()}
    for name, liste in bericht.touren.items():
        tour = vorhandene.get(name.lower())
        tag, rest = wochentag_im_namen(name)
        ft = im_fahrerplan.get(name.lower()) or (im_fahrerplan.get(rest.lower()) if tag else None)
        if tour is None:
            tour = Tour.objects.create(name=name, angelegt_von=von, fahrdienst_tour=ft,
                                       fahrtage=tag if ft and ft.name.lower() != name.lower()
                                       else "")  # fmt: skip
        elif tour.fahrdienst_tour_id is None and ft is not None:
            # schon eingelesen, bevor es die Tour im Fahrerplan gab: jetzt verbinden
            tour.fahrdienst_tour = ft
            if not tour.fahrtage and ft.name.lower() != name.lower():
                tour.fahrtage = tag
            tour.save(update_fields=["fahrdienst_tour", "fahrtage"])
        tour.halte.all().delete()
        Halt.objects.bulk_create(
            Halt(tour=tour, station=stationen[kennung], reihenfolge=nr, wochentage=tage)
            for nr, (_, kennung, _, tage) in enumerate(liste, start=1)
        )
    return len(bericht.touren), bericht.halte
