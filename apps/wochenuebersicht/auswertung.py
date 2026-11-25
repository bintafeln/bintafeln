"""Wochenübersicht der Ausgabestellen (ADR 0054): Soll und Ist je Ausgabestelle und Wochentag.

Die Zahlen kommen aus dem Kundenstamm: Soll = „Maximum Haushalte“ der Kundengruppen, Ist = aktive
Haushalte mit Erwachsenen und Kindern. Eine Kundengruppe zählt an jedem ihrer Wochentage; alle
Gruppen einer Ausgabestelle an einem Tag ergeben eine Zeile (z. B. alle Zeitfenster der Zentrale).
Gruppen ohne Ausgabestelle stehen mit ihrem Namen. Selbstabholer zählen nur zu „alle Personen“.

Vorschau auf eine kommende Woche (ADR 0054, Nachtrag): Jeder Tag wird auf sein Datum gerechnet –
geplante Umzüge (``GeplanterWechsel``) zählen ab ihrem Stichtag in der neuen Kundengruppe, eine
Ausgabestelle mit Enddatum (``schliesst_am``) fällt danach weg, Schließzeiten stehen als
„geschlossen“ und zählen nicht in die Summe. Neuaufnahmen und Abgänge bis dahin kennt niemand.
"""

import datetime as dt
from collections import defaultdict
from dataclasses import dataclass, field

from django.db.models import Count

from apps.ausgabe.ampel import WOCHENTAGE
from apps.ausgabe.models import Schliesszeit
from apps.kunden.models import (
    Abholung,
    GeplanterWechsel,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
)
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
    geschlossen: str = ""  # Vorschau: Schließzeit an dem Tag (Bezeichnung oder „geschlossen“)
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
    datum: dt.date | None = None  # nur in der Vorschau: der Tag, auf den gerechnet wurde

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


def ordnen(tage: list, folge: list[str]) -> list:
    """Die Tage in eigener Reihenfolge (Kürzel wie „Mi“); nicht genannte folgen wie gewohnt."""
    platz = {kurz: i for i, kurz in enumerate(folge)}
    return sorted(tage, key=lambda t: (platz.get(t.kurz, len(platz)), t.nummer))


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


def _vorschauwerte(montag_: dt.date) -> tuple[list[dict[int, Zeile]], int]:
    """Für jeden Tag der Woche ab ``montag_`` die Werte je Kundengruppe, wie sie an dem Tag
    gelten: Wer einen geplanten Umzug hat, zählt ab dessen Stichtag in der neuen Gruppe. Dazu die
    Zahl der Umzüge, die bis zum Ende der Woche wirksam sind."""
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    tage = [montag_ + dt.timedelta(days=i) for i in range(7)]
    wechsel = {w.haushalt_id: w for w in GeplanterWechsel.objects.filter(
        erledigt_am__isnull=True, ab__lte=tage[-1])}  # fmt: skip
    werte: list[dict[int, Zeile]] = [defaultdict(lambda: Zeile("")) for _ in tage]
    aktive = Haushalt.objects.filter(status=Haushalt.Status.AKTIV)
    for h in aktive.prefetch_related("personen"):
        plan = wechsel.get(h.pk)
        if h.kundengruppe_id is None and plan is None:
            continue
        for i, tag in enumerate(tage):
            gruppe = plan.ziel_gruppe_id if plan and plan.ab <= tag else h.kundengruppe_id
            if gruppe is None:
                continue
            erwachsene, kinder = h.groesse(kind_bis, tag)
            z = werte[i][gruppe]
            z.haushalte += 1
            z.erwachsene += erwachsene
            z.kinder += kinder
    return werte, len(wechsel)


def _vorschau_hinweise(stichtag: dt.date, montag_: dt.date, umzuege: int) -> list[str]:
    """Was man zur Vorschau wissen sollte: eingerechnete Umzüge, Ausgabestellen, die bis dahin
    schließen und noch Kunden ohne geplanten Umzug haben, und Ausweise, die bis dahin ablaufen
    (nicht abgezogen – viele werden verlängert)."""
    ende = montag_ + dt.timedelta(days=6)
    hinweise = []
    if umzuege:
        hinweise.append(f"{umzuege} geplante{'r' if umzuege == 1 else ''} Umzug"
                        f"{'' if umzuege == 1 else 'e'} in eine andere Kundengruppe "
                        f"{'ist' if umzuege == 1 else 'sind'} eingerechnet.")  # fmt: skip
    stelle = "kundengruppe__ausgabestelle"
    schliessend = Haushalt.objects.filter(
        status=Haushalt.Status.AKTIV, **{f"{stelle}__schliesst_am__lt": ende}
    ).exclude(geplante_wechsel__erledigt_am__isnull=True, geplante_wechsel__ab__lte=ende)
    je_stelle = (
        schliessend.values_list(f"{stelle}__name")
        .annotate(n=Count("pk", distinct=True))
        .order_by(f"{stelle}__name")
    )
    for name, anzahl in je_stelle:
        einer = anzahl == 1
        hinweise.append(
            f"„{name}“ schließt bis dahin: {anzahl} Haushalt{'' if einer else 'e'} dort "
            f"{'hat' if einer else 'haben'} noch keinen geplanten Umzug und "
            f"{'fehlt' if einer else 'fehlen'} nach der Schließung in der Übersicht."
        )
    ablaufend = Haushalt.objects.filter(
        status=Haushalt.Status.AKTIV, kundengruppe__isnull=False,
        ausweis_gueltig_bis__gte=stichtag, ausweis_gueltig_bis__lt=montag_,
    ).count()  # fmt: skip
    if ablaufend:
        hinweise.append(
            f"Bei {ablaufend} Haushalt{'' if ablaufend == 1 else 'en'} läuft der Ausweis vor "
            "dieser Woche ab. Sie sind mitgezählt – wird nicht verlängert, fallen sie heraus."
        )
    return hinweise


def uebersicht(stichtag: dt.date, woche: dt.date | None = None,
               vorschau: dt.date | None = None) -> dict:  # fmt: skip
    """Tage mit Zeilen und Summen; ``woche`` (Montag) ergänzt die Abholungen dieser Woche.
    ``vorschau`` (Montag einer kommenden Woche) rechnet jeden Tag auf sein Datum: geplante
    Umzüge, schließende Ausgabestellen und Schließzeiten sind berücksichtigt."""
    if vorschau:
        woche = None
        werte_je_tag, umzuege = _vorschauwerte(vorschau)
        pausen = list(Schliesszeit.objects.filter(
            von__lte=vorschau + dt.timedelta(days=6), bis__gte=vorschau))  # fmt: skip
    else:
        werte = _gruppenwerte(stichtag)
    abgeholt = _abgeholt(woche) if woche else None
    reihenfolge = dict(StellenReihenfolge.objects.values_list("ausgabestelle_id", "reihenfolge"))
    zeilen: dict[int, dict[tuple, Zeile]] = defaultdict(dict)
    gruppen = Kundengruppe.objects.filter(aktiv=True).select_related("ausgabestelle")
    for g in gruppen:
        for tag in tage_von(g.wochentage):
            stelle = g.ausgabestelle
            datum = vorschau + dt.timedelta(days=tag) if vorschau else None
            if datum and stelle and stelle.schliesst_am and datum > stelle.schliesst_am:
                continue  # die Ausgabestelle gibt es an dem Tag nicht mehr
            wert = (werte_je_tag[tag] if vorschau else werte).get(g.pk, Zeile(""))
            schluessel = ("stelle", stelle.pk) if stelle else ("gruppe", g.pk)
            z = zeilen[tag].get(schluessel)
            if z is None:
                name = stelle.name if stelle else g.name
                z = Zeile(name, sortierung=(reihenfolge.get(stelle.pk, 100) if stelle else 999,
                                            name.lower()))  # fmt: skip
                if abgeholt is not None and stelle:
                    z.abgeholt = abgeholt.get((stelle.pk, tag), 0)
                if datum and stelle:
                    pause = next((p for p in pausen if p.ausgabestelle_id == stelle.pk
                                  and p.von <= datum <= p.bis), None)  # fmt: skip
                    if pause:
                        z.geschlossen = pause.bezeichnung or "geschlossen"
                zeilen[tag][schluessel] = z
            soll = g.maximum_am(datum) if datum else g.maximum
            z.dazu(Zeile("", soll=soll, haushalte=wert.haushalte,
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
            if not z.geschlossen:  # in der Schließzeit kommt dort niemand
                summe.dazu(z)
        gesamt.dazu(summe)
        tage.append(Tag(nr, liste, selbst[nr], summe,
                        vorschau + dt.timedelta(days=nr) if vorschau else None))  # fmt: skip
    selbst_gesamt = sum(t.selbst_personen for t in tage)
    return {
        "tage": tage,
        "gesamt": gesamt,
        "selbst_gesamt": selbst_gesamt,
        "alle_personen": gesamt.personen + selbst_gesamt,
        "woche": woche,
        "stichtag": stichtag,
        "vorschau": vorschau,
        "hinweise": _vorschau_hinweise(stichtag, vorschau, umzuege) if vorschau else [],
    }
