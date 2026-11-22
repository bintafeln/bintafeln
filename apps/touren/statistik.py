"""Statistik der Touren (ADR 0157): Mengen aus den Lieferscheinen, Fahrten und Kilometer aus dem
Fahrtenbuch – je Monat, Warengruppe, Tour, Station, Handelskette und Fahrzeug.

Kisten werden für eine Gesamtzahl in Kilogramm umgerechnet: mit „kg je Kiste“ der Warengruppe,
sonst mit dem allgemeinen Durchschnittsgewicht (``TourenEinstellungen.kiste_kg``). Bewusst **keine
Auswertung je Person**: Wer wie oft oder wie lange gefahren ist, wertet bintafeln nicht aus.

Jeder Abschnitt ist ein dict für ``statistik/_abschnitt.html`` (Grafik, Tabelle, CSV); gezeichnet
mit ``apps.statistik.diagramme``."""

import datetime as dt
from collections import defaultdict
from decimal import Decimal

from apps.statistik import diagramme
from apps.touren.models import (
    Anfahrt,
    Fahrt,
    Lieferschein,
    Position,
    Station,
    TourenEinstellungen,
    Warengruppe,
)

MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
OHNE = "ohne Angabe"


def _zahl(wert, nachkomma: int = 0) -> str:
    return diagramme._zahl(float(wert or 0), nachkomma)


def _menge(wert) -> str:
    """Kisten und gewogene kg: eine Nachkommastelle nur, wenn es eine gibt („15“, „25,5“)."""
    wert = Decimal(wert or 0)
    return _zahl(wert, 0 if wert == wert.to_integral_value() else 1)


def jahre(heute: dt.date) -> list[int]:
    """Jahre, zu denen es Lieferscheine oder Fahrten gibt – das laufende immer."""
    alle = {heute.year}
    alle |= {d.year for d in Lieferschein.objects.dates("datum", "year")}
    alle |= {d.year for d in Fahrt.objects.dates("datum", "year")}
    return sorted(alle, reverse=True)


class Gewichte:
    """Rechnet Kisten in kg um: Wert der Warengruppe, sonst der allgemeine."""

    def __init__(self):
        self.allgemein = TourenEinstellungen.laden().kiste_kg
        self.je_gruppe = {g.name: g.kiste_kg for g in Warengruppe.objects.all()
                          if g.kiste_kg is not None}  # fmt: skip

    def kg(self, position: Position) -> Decimal:
        if position.einheit == Position.Einheit.KG:
            return position.menge
        return position.menge * self.je_gruppe.get(position.warengruppe, self.allgemein)


def _positionen(jahr: int):
    return (Position.objects.filter(lieferschein__datum__year=jahr)
            .select_related("lieferschein", "lieferschein__station"))  # fmt: skip


class Daten:
    """Alles für ein Jahr einmal geladen und nach den Fragen der Statistik zusammengezählt."""

    def __init__(self, jahr: int):
        self.jahr = jahr
        gewichte = Gewichte()
        leer = lambda: {"kg": Decimal(0), "kisten": Decimal(0), "gewogen": Decimal(0),  # noqa: E731
                        "scheine": set()}  # fmt: skip
        self.monat, self.gruppe = defaultdict(leer), defaultdict(leer)
        self.tour, self.station, self.kette = (
            defaultdict(leer),
            defaultdict(leer),
            defaultdict(leer),
        )
        for p in _positionen(jahr):
            ls = p.lieferschein
            kette = (ls.station.kette if ls.station else "") or OHNE
            ziele = (self.monat[ls.datum.month], self.gruppe[p.warengruppe],
                     self.tour[ls.tour_name or OHNE], self.station[ls.station_name],
                     self.kette[kette])  # fmt: skip
            kg = gewichte.kg(p)
            for z in ziele:
                z["kg"] += kg
                z["scheine"].add(ls.pk)
                if p.einheit == Position.Einheit.KG:
                    z["gewogen"] += p.menge
                else:
                    z["kisten"] += p.menge
        self.scheine = Lieferschein.objects.filter(datum__year=jahr).count()
        self.fahrten = list(Fahrt.objects.filter(datum__year=jahr))
        self.vorjahr_kg = defaultdict(Decimal)
        for p in _positionen(jahr - 1):
            self.vorjahr_kg[p.lieferschein.datum.month] += gewichte.kg(p)

    @staticmethod
    def stunden(fahrten) -> float:
        """Fahrzeit nur von Fahrten, die am Handy beendet wurden (nicht nachgetragene)."""
        sekunden = sum(f.dauer.total_seconds() for f in fahrten
                       if f.dauer is not None and f.beendet_von_name)  # fmt: skip
        return sekunden / 3600

    @staticmethod
    def km(fahrten) -> int:
        return sum(f.km or 0 for f in fahrten)


def kennzahlen(d: Daten) -> dict:
    kg = sum((m["kg"] for m in d.monat.values()), Decimal(0))
    vorjahr = sum(d.vorjahr_kg.values(), Decimal(0))
    return {
        "kg": _zahl(kg), "tonnen": _zahl(kg / 1000, 1),
        "kisten": _zahl(sum((m["kisten"] for m in d.monat.values()), Decimal(0))),
        "scheine": d.scheine, "stationen": len(d.station),
        "fahrten": len(d.fahrten), "km": _zahl(Daten.km(d.fahrten)),
        "stunden": _zahl(Daten.stunden(d.fahrten)),
        "vergleich": round((kg - vorjahr) / vorjahr * 100) if vorjahr else None,
    }  # fmt: skip


def _mengen_zeile(name, z) -> list:
    return [name, len(z["scheine"]), _menge(z["kisten"]), _menge(z["gewogen"]),
            _zahl(z["kg"])]  # fmt: skip


MENGEN_KOPF = ["Lieferscheine", "Kisten", "kg gewogen", "kg gesamt"]


def abschnitt_mengen(d: Daten) -> dict:
    hat = bool(d.monat)  # vor dem Zugriff: das Nachschlagen legt leere Monate an
    daten = [(MONATE[m - 1], float(d.monat[m]["kg"])) for m in range(1, 13)]
    zeilen = [[*_mengen_zeile(MONATE[m - 1], d.monat[m]), _zahl(d.vorjahr_kg[m])]
              for m in range(1, 13)]  # fmt: skip
    return {
        "id": "mengen", "titel": f"Abgeholte Menge je Monat {d.jahr}",
        "text": "Kilogramm; Kisten sind mit dem Durchschnittsgewicht umgerechnet.",
        "svg": diagramme.saeulen(daten, "Abgeholte Menge je Monat", " kg", farbe=0)
        if hat else "",
        "kopf": ["Monat", *MENGEN_KOPF, f"kg {d.jahr - 1}"], "zeilen": zeilen if hat else [],
    }  # fmt: skip


def _nach_kg(gruppen: dict, grenze: int | None = None) -> list:
    sortiert = sorted(gruppen.items(), key=lambda paar: (-paar[1]["kg"], paar[0].lower()))
    return sortiert[:grenze] if grenze else sortiert


def abschnitt_warengruppen(d: Daten) -> dict:
    reihe = _nach_kg(d.gruppe)
    return {
        "id": "warengruppen", "titel": "Menge je Warengruppe",
        "svg": diagramme.balken([(n, float(z["kg"])) for n, z in reihe],
                                "Menge je Warengruppe", " kg", farbe=1) if reihe else "",
        "kopf": ["Warengruppe", *MENGEN_KOPF],
        "zeilen": [_mengen_zeile(n, z) for n, z in reihe],
    }  # fmt: skip


def abschnitt_fahrten(d: Daten) -> dict:
    je = defaultdict(list)
    for f in d.fahrten:
        je[f.datum.month].append(f)
    zeilen = [[MONATE[m - 1], len(je[m]), _zahl(Daten.km(je[m])), _zahl(Daten.stunden(je[m]), 1)]
              for m in range(1, 13)]  # fmt: skip
    return {
        "id": "fahrten", "titel": f"Fahrten und Kilometer je Monat {d.jahr}",
        "text": "Aus dem Fahrtenbuch. Stunden zählen nur Fahrten, die am Handy beendet wurden.",
        "svg": diagramme.saeulen([(MONATE[m - 1], float(Daten.km(je[m]))) for m in range(1, 13)],
                                 "Kilometer je Monat", " km", farbe=2) if d.fahrten else "",
        "kopf": ["Monat", "Fahrten", "km", "Stunden"], "zeilen": zeilen if d.fahrten else [],
    }  # fmt: skip


def abschnitt_touren(d: Daten) -> dict:
    fahrten = defaultdict(list)
    for f in d.fahrten:
        fahrten[f.tour_name or OHNE].append(f)
    namen = sorted(set(d.tour) | set(fahrten), key=lambda n: (-d.tour[n]["kg"], n.lower()))
    zeilen = [[n, len(fahrten[n]), _zahl(Daten.km(fahrten[n])),
               _zahl(Daten.stunden(fahrten[n]), 1), len(d.tour[n]["scheine"]),
               _zahl(d.tour[n]["kg"])] for n in namen]  # fmt: skip
    daten = [(n, float(d.tour[n]["kg"])) for n in namen if d.tour[n]["kg"]][:20]
    return {
        "id": "touren", "titel": "Je Tour",
        "svg": diagramme.balken(daten, "Menge je Tour", " kg", farbe=3) if daten else "",
        "kopf": ["Tour", "Fahrten", "km", "Stunden", "Lieferscheine", "kg gesamt"],
        "zeilen": zeilen,
    }  # fmt: skip


def abschnitt_fahrzeuge(d: Daten) -> dict:
    je = defaultdict(list)
    for f in d.fahrten:
        je[f.fahrzeug_name or "ohne Fahrzeug"].append(f)
    namen = sorted(je, key=lambda n: (-Daten.km(je[n]), n.lower()))
    return {
        "id": "fahrzeuge", "titel": "Je Fahrzeug",
        "svg": diagramme.balken([(n, float(Daten.km(je[n]))) for n in namen],
                                "Kilometer je Fahrzeug", " km", farbe=4) if namen else "",
        "kopf": ["Fahrzeug", "Fahrten", "km"],
        "zeilen": [[n, len(je[n]), _zahl(Daten.km(je[n]))] for n in namen],
    }  # fmt: skip


def abschnitt_stationen(d: Daten) -> dict:
    reihe = _nach_kg(d.station)
    return {
        "id": "stationen", "titel": "Je Station",
        "text": "Die Grafik zeigt die 15 Stationen mit der größten Menge, die Tabelle alle.",
        "svg": diagramme.balken([(n, float(z["kg"])) for n, z in reihe[:15]],
                                "Stationen mit der größten Menge", " kg", farbe=5)
        if reihe else "",
        "kopf": ["Station", *MENGEN_KOPF], "zeilen": [_mengen_zeile(n, z) for n, z in reihe],
    }  # fmt: skip


def abschnitt_ketten(d: Daten) -> dict:
    reihe = _nach_kg(d.kette)
    return {
        "id": "ketten", "titel": "Je Handelskette",
        "svg": diagramme.balken([(n, float(z["kg"])) for n, z in reihe[:15]],
                                "Menge je Handelskette", " kg", farbe=6) if reihe else "",
        "kopf": ["Handelskette", *MENGEN_KOPF], "zeilen": [_mengen_zeile(n, z) for n, z in reihe],
    }  # fmt: skip


def abschnitt_ohne(d: Daten) -> dict:
    """Aktive Stationen mit Lieferschein, zu denen es im Jahr keinen Lieferschein gibt."""
    mit = set(Lieferschein.objects.filter(datum__year=d.jahr, station__isnull=False)
              .values_list("station_id", flat=True))  # fmt: skip
    ohne = Station.objects.filter(aktiv=True, lieferschein=True).exclude(pk__in=mit)
    return {
        "id": "ohne", "titel": f"Stationen ohne Lieferschein {d.jahr}",
        "text": "Aktive Stationen, an denen ein Lieferschein vorgesehen ist, zu denen es in "
        "diesem Jahr aber keinen gibt.",
        "svg": "", "kopf": ["Station", "Art", "Ort"],
        "zeilen": [[s.name, s.get_art_display(), s.ort] for s in ohne.order_by("name")],
    }  # fmt: skip


def abschnitt_umstaende(d: Daten) -> dict:
    """Stationen, die ohne Lieferschein abgehakt wurden: wie oft welcher Umstand, je Station
    (ADR 0163) – nie je Person."""
    je = defaultdict(lambda: defaultdict(int))
    namen = defaultdict(int)
    for station, umstand in (Anfahrt.objects.filter(datum__year=d.jahr).exclude(umstand="")
                             .values_list("station__name", "umstand")):  # fmt: skip
        je[station][umstand] += 1
        namen[umstand] += 1
    spalten = sorted(namen, key=lambda n: (-namen[n], n))
    reihe = sorted(je, key=lambda s: (-sum(je[s].values()), s))
    return {
        "id": "umstaende", "titel": "Ohne Lieferschein abgehakt",
        "text": "Wie oft an einer Station was war, wenn sie ohne Lieferschein abgehakt wurde.",
        "svg": "", "kopf": ["Station", *spalten, "Gesamt"],
        "zeilen": [[s, *[je[s].get(n, 0) or "" for n in spalten], sum(je[s].values())]
                   for s in reihe],
    }  # fmt: skip


def abschnitte(d: Daten) -> list[dict]:
    return [abschnitt_mengen(d), abschnitt_warengruppen(d), abschnitt_fahrten(d),
            abschnitt_touren(d), abschnitt_fahrzeuge(d), abschnitt_stationen(d),
            abschnitt_ketten(d), abschnitt_umstaende(d), abschnitt_ohne(d)]  # fmt: skip
