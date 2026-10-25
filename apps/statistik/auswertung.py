"""Auswertungen für die Statistik (ADR 0036): reine Abfragen, keine Darstellung.

Alle Zahlen sind Summen ohne Personenbezug. ``stellen`` schränkt auf Ausgabestellen ein
(None = alle); Abholungen und Einnahmen zählen nach der Ausgabestelle, an der sie gebucht wurden,
Bestandszahlen (Haushalte, Personen) nach der Ausgabestelle der Kundengruppe.
"""

import datetime as dt
from collections import Counter
from dataclasses import dataclass, field
from decimal import Decimal

from django.db.models import Count, Q, Sum
from django.db.models.functions import (
    ExtractHour,
    ExtractIsoWeekDay,
    TruncDay,
    TruncMonth,
    TruncWeek,
)
from django.utils import timezone

from apps.ausgabe.ampel import WOCHENTAGE
from apps.ausgabe.konto import MONATE
from apps.ausgabe.models import Buchung, Sonderaktion
from apps.kunden.models import Abholung, Haushalt, KundenEinstellungen, Kundengruppe

ALTERSGRUPPEN = [
    (0, 5, "0–5"),
    (6, 13, "6–13"),
    (14, 17, "14–17"),
    (18, 24, "18–24"),
    (25, 49, "25–49"),
    (50, 64, "50–64"),
    (65, 200, "65 und älter"),
]
MAX_SERIEN = 8  # mehr Ausgabestellen werden zu „Andere“ zusammengefasst


@dataclass
class Zeitraum:
    von: dt.date
    bis: dt.date
    titel: str = ""

    @property
    def tage(self) -> int:
        return (self.bis - self.von).days + 1

    @property
    def einheit(self) -> str:
        """Feinheit der Verläufe: Tag (bis 31 Tage), Woche (bis gut 3 Monate), sonst Monat."""
        if self.tage <= 31:
            return "tag"
        if self.tage <= 100:
            return "woche"
        return "monat"


def zeitraeume(heute: dt.date) -> dict[str, Zeitraum]:
    """Vorauswahl für das Filterfeld."""
    monatsanfang = heute.replace(day=1)
    vormonat_ende = monatsanfang - dt.timedelta(days=1)
    vor12 = (monatsanfang.replace(year=monatsanfang.year - 1) + dt.timedelta(days=32)).replace(
        day=1
    )
    return {
        "jahr": Zeitraum(heute.replace(month=1, day=1), heute, f"Dieses Jahr ({heute.year})"),
        "vorjahr": Zeitraum(
            dt.date(heute.year - 1, 1, 1),
            dt.date(heute.year - 1, 12, 31),
            f"Letztes Jahr ({heute.year - 1})",
        ),
        "12monate": Zeitraum(vor12, heute, "Letzte 12 Monate"),
        "monat": Zeitraum(monatsanfang, heute, "Dieser Monat"),
        "vormonat": Zeitraum(vormonat_ende.replace(day=1), vormonat_ende, "Letzter Monat"),
        "30tage": Zeitraum(heute - dt.timedelta(days=29), heute, "Letzte 30 Tage"),
    }


def perioden(z: Zeitraum) -> list[tuple[dt.date, str]]:
    """Alle Perioden des Zeitraums (auch leere) mit Beschriftung."""
    ergebnis = []
    if z.einheit == "tag":
        tag = z.von
        while tag <= z.bis:
            ergebnis.append((tag, f"{tag:%d.%m.}"))
            tag += dt.timedelta(days=1)
    elif z.einheit == "woche":
        tag = z.von - dt.timedelta(days=z.von.weekday())
        while tag <= z.bis:
            ergebnis.append((tag, f"KW {tag.isocalendar()[1]}"))
            tag += dt.timedelta(days=7)
    else:
        tag = z.von.replace(day=1)
        mehrere_jahre = z.von.year != z.bis.year
        while tag <= z.bis:
            name = MONATE[tag.month - 1][:3]
            ergebnis.append((tag, f"{name} {tag:%y}" if mehrere_jahre else name))
            tag = (tag + dt.timedelta(days=32)).replace(day=1)
    return ergebnis


def _trunc(z: Zeitraum, feld: str):
    return {"tag": TruncDay, "woche": TruncWeek, "monat": TruncMonth}[z.einheit](feld)


def _als_datum(wert) -> dt.date:
    return wert.date() if isinstance(wert, dt.datetime) else wert


def abholungen(z: Zeitraum, stellen=None):
    qs = Abholung.objects.filter(datum__gte=z.von, datum__lte=z.bis)
    if stellen is not None:
        qs = qs.filter(ausgabestelle__in=stellen)
    return qs


def verlauf(qs, z: Zeitraum, datumsfeld="datum", wert=None) -> list[float]:
    """Werte je Periode (Anzahl oder Summe von ``wert``), passend zu ``perioden(z)``."""
    gruppiert = (
        qs.annotate(p=_trunc(z, datumsfeld))
        .values("p")
        .annotate(w=Sum(wert) if wert else Count("pk"))
    )
    je = {_als_datum(g["p"]): g["w"] or 0 for g in gruppiert}
    return [float(je.get(beginn, 0)) for beginn, _ in perioden(z)]


@dataclass
class Serie:
    name: str
    werte: list[float]
    summe: float = 0
    farbe: int = 0  # Platz in der festen Farbreihenfolge


def verlauf_je_stelle(z: Zeitraum, stellen=None) -> list[Serie]:
    """Abholungen je Ausgabestelle und Periode; mehr als MAX_SERIEN werden „Andere“."""
    qs = abholungen(z, stellen)
    gruppiert = (
        qs.annotate(p=_trunc(z, "datum")).values("p", "ausgabestelle__name").annotate(n=Count("pk"))
    )
    index = {beginn: i for i, (beginn, _) in enumerate(perioden(z))}
    serien: dict[str, list[float]] = {}
    for g in gruppiert:
        name = g["ausgabestelle__name"] or "ohne Ausgabestelle"
        werte = serien.setdefault(name, [0.0] * len(index))
        i = index.get(_als_datum(g["p"]))
        if i is not None:
            werte[i] += g["n"]
    # Feste Farbe je Ausgabestelle nach Namen (Farbe folgt der Stelle, nicht dem Rang)
    alle = sorted(serien)
    liste = [Serie(n, serien[n], sum(serien[n]), alle.index(n)) for n in alle]
    if len(liste) > MAX_SERIEN:
        liste.sort(key=lambda s: -s.summe)
        rest = liste[MAX_SERIEN - 1 :]
        andere = Serie(
            "Andere",
            [sum(w) for w in zip(*(s.werte for s in rest), strict=True)],
            sum(s.summe for s in rest),
            MAX_SERIEN - 1,
        )
        liste = sorted(liste[: MAX_SERIEN - 1], key=lambda s: s.name) + [andere]
        for i, s in enumerate(liste[:-1]):
            s.farbe = i
    return liste


def je_wochentag(z: Zeitraum, stellen=None) -> list[tuple[str, int]]:
    je = dict(
        abholungen(z, stellen)
        .annotate(t=ExtractIsoWeekDay("datum"))
        .values_list("t")
        .annotate(n=Count("pk"))
    )
    return [(WOCHENTAGE[i], je.get(i + 1, 0)) for i in range(7)]


def je_stunde(z: Zeitraum, stellen=None) -> list[tuple[str, int]]:
    mit_zeit = abholungen(z, stellen).filter(uhrzeit__isnull=False)
    je = dict(mit_zeit.annotate(s=ExtractHour("uhrzeit")).values_list("s").annotate(n=Count("pk")))
    if not je:
        return []
    von, bis = min(je), max(je)
    return [(f"{s} Uhr", je.get(s, 0)) for s in range(von, bis + 1)]


def je_stelle(z: Zeitraum, stellen=None) -> list[tuple[str, int]]:
    zeilen = abholungen(z, stellen).values("ausgabestelle__name").annotate(n=Count("pk"))
    return sorted(
        ((g["ausgabestelle__name"] or "ohne Ausgabestelle", g["n"]) for g in zeilen),
        key=lambda x: -x[1],
    )


def bestand(stellen=None):
    """Haushalte (ohne beendete) der gewählten Ausgabestellen."""
    qs = Haushalt.objects.exclude(status=Haushalt.Status.BEENDET)
    if stellen is not None:
        qs = qs.filter(kundengruppe__ausgabestelle__in=stellen)
    return qs


def haushaltsgroessen(heute: dt.date, stellen=None) -> list[tuple[str, int]]:
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    zaehler = Counter()
    for h in bestand(stellen).filter(status=Haushalt.Status.AKTIV).prefetch_related("personen"):
        erwachsene, kinder = h.groesse(kind_bis, heute)
        zaehler[min(erwachsene + kinder, 6)] += 1
    return [("6 und mehr" if n == 6 else str(n), zaehler.get(n, 0)) for n in range(1, 7)]


def altersgruppen(heute: dt.date, stellen=None) -> list[tuple[str, int]]:
    zaehler = Counter()
    ohne = 0
    for h in bestand(stellen).filter(status=Haushalt.Status.AKTIV).prefetch_related("personen"):
        for p in h.personen.all():
            if p.geburtsdatum is None:
                ohne += 1
                continue
            alter = (
                heute.year
                - p.geburtsdatum.year
                - ((heute.month, heute.day) < (p.geburtsdatum.month, p.geburtsdatum.day))
            )
            for von, bis, name in ALTERSGRUPPEN:
                if von <= alter <= bis:
                    zaehler[name] += 1
    zeilen = [(name, zaehler.get(name, 0)) for _, _, name in ALTERSGRUPPEN]
    return zeilen + ([("ohne Geburtsdatum", ohne)] if ohne else [])


def status(stellen=None) -> list[tuple[str, int]]:
    qs = Haushalt.objects.all()
    if stellen is not None:
        qs = qs.filter(kundengruppe__ausgabestelle__in=stellen)
    je = dict(qs.values_list("status").annotate(n=Count("pk")))
    return [(name, je.get(wert, 0)) for wert, name in Haushalt.Status.choices]


def einkommensarten(stellen=None) -> list[tuple[str, int]]:
    zeilen = bestand(stellen).values("einkommensart__bezeichnung").annotate(n=Count("pk"))
    return sorted(
        ((g["einkommensart__bezeichnung"] or "nicht angegeben", g["n"]) for g in zeilen),
        key=lambda x: -x[1],
    )


@dataclass
class Auslastung:
    name: str
    belegt: int
    maximum: int | None

    @property
    def prozent(self) -> float | None:
        return round(100 * self.belegt / self.maximum, 1) if self.maximum else None


def auslastung(stellen=None) -> list[Auslastung]:
    belegt = Count("haushalte", filter=~Q(haushalte__status=Haushalt.Status.BEENDET))
    gruppen = Kundengruppe.objects.filter(aktiv=True).annotate(belegt=belegt).order_by("name")
    if stellen is not None:
        gruppen = gruppen.filter(ausgabestelle__in=stellen)
    return [Auslastung(g.name, g.belegt, g.maximum) for g in gruppen]


def einnahmen(z: Zeitraum, stellen=None):
    qs = Buchung.objects.filter(datum__gte=z.von, datum__lte=z.bis)
    if stellen is not None:
        qs = qs.filter(ausgabestelle__in=stellen)
    return qs


def neuaufnahmen_und_antraege(z: Zeitraum, stellen=None) -> list[Serie]:
    from apps.antraege.models import Antrag

    neu = Haushalt.objects.filter(kunde_seit__gte=z.von, kunde_seit__lte=z.bis)
    if stellen is not None:
        neu = neu.filter(kundengruppe__ausgabestelle__in=stellen)
    serien = [Serie("Neue Kunden (Kunde seit)", verlauf(neu, z, "kunde_seit"), farbe=0)]
    if stellen is None:  # Anträge haben noch keine Ausgabestelle
        start = timezone.make_aware(dt.datetime.combine(z.von, dt.time()))
        ende = timezone.make_aware(dt.datetime.combine(z.bis + dt.timedelta(days=1), dt.time()))
        antraege = Antrag.objects.filter(eingegangen_am__gte=start, eingegangen_am__lt=ende)
        serien.append(
            Serie("Eingegangene Anträge", verlauf(antraege, z, "eingegangen_am"), farbe=1)
        )
    for s in serien:
        s.summe = sum(s.werte)
    return serien


def sonderaktionen(z: Zeitraum) -> list[dict]:
    aktionen = Sonderaktion.objects.filter(von__lte=z.bis, bis__gte=z.von).annotate(
        haushalte=Count("teilnahmen"), stueck=Sum("teilnahmen__menge")
    )
    return [
        {
            "name": a.bezeichnung,
            "zeitraum": f"{a.von:%d.%m.%Y} – {a.bis:%d.%m.%Y}",
            "haushalte": a.haushalte,
            "stueck": a.stueck or 0,
        }
        for a in aktionen
    ]


@dataclass
class Kennzahlen:
    abholungen: int = 0
    haushalte: int = 0
    personen: int = 0
    einnahmen: Decimal = Decimal("0")
    aktive_haushalte: int = 0
    aktive_personen: int = 0
    neue_kunden: int = 0
    antraege: int = 0
    extra: dict = field(default_factory=dict)


def kennzahlen(z: Zeitraum, stellen=None) -> Kennzahlen:
    from apps.antraege.models import Antrag

    qs = abholungen(z, stellen)
    k = Kennzahlen()
    k.abholungen = qs.count()
    besucht = list(qs.values_list("haushalt_id", flat=True))
    k.haushalte = len(set(besucht))
    besuchte = Haushalt.objects.filter(pk__in=set(besucht)).prefetch_related("personen")
    groesse = {
        h.pk: h.personen.count() or (h.anzahl_erwachsene or 0) + (h.anzahl_kinder or 0)
        for h in besuchte
    }
    k.personen = sum(groesse.get(h, 0) for h in besucht)
    k.einnahmen = einnahmen(z, stellen).aggregate(s=Sum("bar"))["s"] or Decimal("0")
    aktiv = bestand(stellen).filter(status=Haushalt.Status.AKTIV)
    k.aktive_haushalte = aktiv.count()
    k.aktive_personen = sum(h.personen.count() for h in aktiv.prefetch_related("personen"))
    k.neue_kunden = sum(neuaufnahmen_und_antraege(z, stellen)[0].werte)
    if stellen is None:
        start = timezone.make_aware(dt.datetime.combine(z.von, dt.time()))
        ende = timezone.make_aware(dt.datetime.combine(z.bis + dt.timedelta(days=1), dt.time()))
        k.antraege = Antrag.objects.filter(
            eingegangen_am__gte=start, eingegangen_am__lt=ende
        ).count()
    return k
