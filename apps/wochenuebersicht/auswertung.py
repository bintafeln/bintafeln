"""Wochenübersicht der Ausgabestellen (ADR 0054): Soll und Ist je Ausgabestelle und Wochentag.

Die Zahlen kommen aus dem Kundenstamm: Soll = „Maximum Haushalte“ der Kundengruppen, Ist = aktive
Haushalte mit Erwachsenen und Kindern. Eine Kundengruppe zählt an jedem ihrer Wochentage; alle
Gruppen einer Ausgabestelle an einem Tag ergeben eine Zeile (z. B. alle Zeitfenster der Zentrale).
Gruppen ohne Ausgabestelle stehen mit ihrem Namen. Selbstabholer zählen nur zu „alle Personen“.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Count

from apps.ausgabe.ampel import WOCHENTAGE
from apps.kunden.models import Abholung, Haushalt, KundenEinstellungen, Kundengruppe
from apps.wochenuebersicht.models import Selbstabholer, StellenReihenfolge

TAGNAMEN = ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"]


@dataclass
class Zeile:
    name: str
    soll: int | None = None
    haushalte: int = 0
    erwachsene: int = 0
    kinder: int = 0
    abgeholt: int | None = None
    gruppen: list[str] = field(default_factory=list)
    sortierung: tuple = ()

    @property
    def personen(self) -> int:
        return self.erwachsene + self.kinder

    def dazu(self, andere: "Zeile") -> None:
        if andere.soll is not None:
            self.soll = (self.soll or 0) + andere.soll
        self.haushalte += andere.haushalte
        self.erwachsene += andere.erwachsene
        self.kinder += andere.kinder
        if andere.abgeholt is not None:
            self.abgeholt = (self.abgeholt or 0) + andere.abgeholt


@dataclass
class Tag:
    nummer: int
    zeilen: list[Zeile]
    selbstabholer: list[Selbstabholer]
    summe: Zeile

    @property
    def name(self) -> str:
        return TAGNAMEN[self.nummer]

    @property
    def kurz(self) -> str:
        return WOCHENTAGE[self.nummer]

    @property
    def selbst_personen(self) -> int:
        return sum(s.personen for s in self.selbstabholer)


def tage_von(text: str) -> list[int]:
    kuerzel = {t.strip() for t in (text or "").split(",")}
    return [i for i, k in enumerate(WOCHENTAGE) if k in kuerzel]


def montag(datum: dt.date) -> dt.date:
    return datum - dt.timedelta(days=datum.weekday())


def _gruppenwerte(stichtag: dt.date) -> dict[int, Zeile]:
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    werte: dict[int, Zeile] = defaultdict(lambda: Zeile(""))
    aktive = Haushalt.objects.filter(status=Haushalt.Status.AKTIV, kundengruppe__isnull=False)
    for h in aktive.prefetch_related("personen"):
        erwachsene, kinder = h.groesse(kind_bis, stichtag)
        z = werte[h.kundengruppe_id]
        z.haushalte += 1
        z.erwachsene += erwachsene
        z.kinder += kinder
    return werte


def _abgeholt(woche: dt.date) -> dict[tuple[int, int], int]:
    """Haushalte mit Abholung je (Ausgabestelle, Wochentag) in der Woche ab ``woche``."""
    zaehler: dict[tuple[int, int], int] = defaultdict(int)
    abholungen = (
        Abholung.objects.filter(datum__range=(woche, woche + dt.timedelta(days=6)),
                                ausgabestelle__isnull=False)
        .values("ausgabestelle_id", "datum")
        .annotate(n=Count("haushalt", distinct=True))
    )  # fmt: skip
    for a in abholungen:
        zaehler[(a["ausgabestelle_id"], a["datum"].weekday())] += a["n"]
    return zaehler


def uebersicht(stichtag: dt.date, woche: dt.date | None = None) -> dict:
    """Tage mit Zeilen und Summen; ``woche`` (Montag) ergänzt die Abholungen dieser Woche."""
    werte = _gruppenwerte(stichtag)
    abgeholt = _abgeholt(woche) if woche else None
    reihenfolge = dict(StellenReihenfolge.objects.values_list("ausgabestelle_id", "reihenfolge"))
    zeilen: dict[int, dict[tuple, Zeile]] = defaultdict(dict)
    gruppen = Kundengruppe.objects.filter(aktiv=True).select_related("ausgabestelle")
    for g in gruppen:
        wert = werte.get(g.pk, Zeile(""))
        for tag in tage_von(g.wochentage):
            stelle = g.ausgabestelle
            schluessel = ("stelle", stelle.pk) if stelle else ("gruppe", g.pk)
            z = zeilen[tag].get(schluessel)
            if z is None:
                name = stelle.name if stelle else g.name
                z = Zeile(name, sortierung=(reihenfolge.get(stelle.pk, 100) if stelle else 999,
                                            name.lower()))  # fmt: skip
                if abgeholt is not None and stelle:
                    z.abgeholt = abgeholt.get((stelle.pk, tag), 0)
                zeilen[tag][schluessel] = z
            z.dazu(Zeile("", soll=g.maximum, haushalte=wert.haushalte,
                         erwachsene=wert.erwachsene, kinder=wert.kinder))  # fmt: skip
            z.gruppen.append(g.name)
    selbst: dict[int, list[Selbstabholer]] = defaultdict(list)
    for s in Selbstabholer.objects.filter(aktiv=True):
        for tag in tage_von(s.tage):
            selbst[tag].append(s)
    benutzt = set(zeilen) | set(selbst)
    nummern = [t for t in range(7) if t < 5 or t in benutzt]
    tage, gesamt = [], Zeile("Ausgabestellen gesamt", abgeholt=0 if woche else None)
    for nr in nummern:
        liste = sorted(zeilen[nr].values(), key=lambda z: z.sortierung)
        summe = Zeile(f"Summe {TAGNAMEN[nr]}", abgeholt=0 if woche else None)
        for z in liste:
            summe.dazu(z)
        gesamt.dazu(summe)
        tage.append(Tag(nr, liste, selbst[nr], summe))
    selbst_gesamt = sum(t.selbst_personen for t in tage)
    return {
        "tage": tage,
        "gesamt": gesamt,
        "selbst_gesamt": selbst_gesamt,
        "alle_personen": gesamt.personen + selbst_gesamt,
        "woche": woche,
        "stichtag": stichtag,
    }
