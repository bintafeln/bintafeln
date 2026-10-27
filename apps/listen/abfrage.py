"""Rechnet eine Liste aus (ADR 0063): Grundmenge nach Zugang (eigene Ausgabestellen), Filter,
Werte je Spalte, Sortierung, Gruppen mit Anzahl und Summen. Alles in Python, damit abgeleitete
Werte wie Alter oder Altersgruppe genauso sortierbar und gruppierbar sind wie Felder."""

import datetime as dt
from dataclasses import dataclass, field

from django.db.models import Count, Prefetch, Q
from django.utils import timezone

from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Einkommensart,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Person,
)
from apps.listen import spalten as sp
from apps.listen.katalog import Liste

STATUS = [("", "alle"), ("aktiv", "aktiv"), ("nicht_aktiv", "nicht aktiv (pausiert, gesperrt, "
          "beendet)"), *[(w, n) for w, n in Haushalt.Status.choices if w != "aktiv"]]  # fmt: skip


def _datum(text):
    try:
        return dt.date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _zahl(text):
    try:
        return int(text) if text is not None and str(text).strip() != "" else None
    except ValueError:
        return None


@dataclass
class Ergebnis:
    spalten: list  # sichtbare Spalten (sp.Spalte)
    gruppen: list = field(default_factory=list)  # [{"titel", "zeilen", "anzahl", "summen"}]
    anzahl: int = 0
    summen: dict = field(default_factory=dict)
    haushalte: set = field(default_factory=set)  # Kundennummern (für das Zugriffsprotokoll)
    summen_zeile: list = field(default_factory=list)
    zahl_titel: list = field(default_factory=list)  # Zahlenspalten (für „nur Summen“)
    zahlen: list = field(default_factory=list)  # [(Titel, Summe)] über alles


def stellen(benutzer):
    eigene = zugang.stellen(benutzer)
    return list(Ausgabestelle.objects.order_by("name")) if eigene is None else eigene


def gruppen(benutzer):
    qs = Kundengruppe.objects.order_by("name")
    eigene = zugang.stellen(benutzer)
    return qs if eigene is None else qs.filter(ausgabestelle__in=eigene)


def staatsangehoerigkeiten(benutzer):
    haushalte = zugang.filtern(Haushalt.objects.all(), benutzer)
    werte = (Person.objects.filter(haushalt__in=haushalte).exclude(staatsangehoerigkeit="")
             .values_list("staatsangehoerigkeit", flat=True).distinct())  # fmt: skip
    return sorted(set(werte), key=str.casefold)


def einkommensarten():
    return list(Einkommensart.objects.values_list("bezeichnung", flat=True))


def _haushalte(benutzer, p):
    qs = zugang.filtern(Haushalt.objects.all(), benutzer).select_related(
        "kundengruppe__ausgabestelle", "einkommensart"
    )
    if (pk := _zahl(p.get("stelle"))) is not None:
        qs = qs.filter(kundengruppe__ausgabestelle_id=pk)
    if (pk := _zahl(p.get("kundengruppe"))) is not None:
        qs = qs.filter(kundengruppe_id=pk)
    status = p.get("status", "")
    if status == "nicht_aktiv":
        qs = qs.exclude(status=Haushalt.Status.AKTIV)
    elif status in Haushalt.Status.values:
        qs = qs.filter(status=status)
    if p.get("einkommensart"):
        qs = qs.filter(einkommensart__bezeichnung__icontains=p["einkommensart"])
    if (tag := _datum(p.get("ausweis_bis"))) is not None:
        qs = qs.filter(ausweis_gueltig_bis__lte=tag)
    if (tag := _datum(p.get("besuch_vor"))) is not None:
        qs = qs.filter(Q(letzter_besuch__lt=tag) | Q(letzter_besuch__isnull=True))
    if (tag := _datum(p.get("seit_ab"))) is not None:
        qs = qs.filter(kunde_seit__gte=tag)
    if p.get("kontostand_minus"):
        qs = qs.filter(kontostand__lt=0)
    if p.get("ohne_gruppe"):
        qs = qs.filter(kundengruppe__isnull=True)
    qs = Haushalt.mit_besuch_zeit(qs)
    return qs.prefetch_related(Prefetch("personen", queryset=Person.objects.order_by(
        "-ist_hauptperson", "pk")))  # fmt: skip


def _abholungen(haushalte, p) -> dict:
    qs = Abholung.objects.filter(haushalt__in=haushalte)
    if (von := _datum(p.get("von"))) is not None:
        qs = qs.filter(datum__gte=von)
    if (bis := _datum(p.get("bis"))) is not None:
        qs = qs.filter(datum__lte=bis)
    return dict(qs.values("haushalt").annotate(n=Count("pk")).values_list("haushalt", "n"))


def objekte(liste: Liste, benutzer, p, mit_abholungen=False) -> tuple[list, dict]:
    """Haushalte bzw. Personen nach den Filtern, dazu der Rechenkontext."""
    heute = timezone.localdate()
    haushalte = _haushalte(benutzer, p)
    k = {"heute": heute, "kind_bis": KundenEinstellungen.laden().kind_bis_alter,
         "abholungen": _abholungen(haushalte, p) if mit_abholungen else {}}  # fmt: skip
    hh = list(haushalte)
    if (ab := _zahl(p.get("personen_ab"))) is not None:
        hh = [h for h in hh if sum(h.groesse(k["kind_bis"], heute)) >= ab]
    if (tag := p.get("tag")) in WOCHENTAGE:
        hh = [h for h in hh if h.kundengruppe and tag in wochentage(h.kundengruppe.wochentage)]
    if p.get("kinder_unter_6"):
        hh = [h for h in hh if any((a := q.alter(heute)) is not None and a < 6
                                   for q in h.personen.all())]  # fmt: skip
    if liste.basis == "haushalt":
        return hh, k
    von, bis = _zahl(p.get("alter_von")), _zahl(p.get("alter_bis"))
    nat = p.get("staatsangehoerigkeit", "")
    personen = []
    for h in hh:
        for person in h.personen.all():
            person.haushalt = h  # schon geladen, keine weitere Abfrage
            alter = person.alter(heute)
            if (von is not None or bis is not None) and alter is None:
                continue
            if von is not None and alter < von or bis is not None and alter > bis:
                continue
            if nat and person.staatsangehoerigkeit != nat:
                continue
            personen.append(person)
    return personen, k


def rechnen(liste: Liste, benutzer, p, auswahl=None) -> Ergebnis:
    """``p``: GET-Werte (QueryDict). ``auswahl``: nur diese Zeilen (pk), z. B. für den Export."""
    darf = rollen.rechte_von(benutzer)
    erlaubt = {s.schluessel: s for s in sp.erlaubte(liste.basis, darf)}
    sichtbar = [erlaubt[k] for k in (p.getlist("s") or liste.spalten) if k in erlaubt]
    gruppe_key = p.get("gruppe", "")
    gruppe = erlaubt.get(gruppe_key)
    sort = p.get("sort") or liste.sort
    sort_spalte = erlaubt.get(sort.lstrip("-"))
    gebraucht = {s.schluessel for s in sichtbar} | {sort.lstrip("-"), gruppe_key}
    objs, k = objekte(liste, benutzer, p, mit_abholungen="abholungen" in gebraucht)
    if auswahl is not None:
        objs = [o for o in objs if o.pk in auswahl]
    benoetigt = {s.schluessel: s for s in [*sichtbar, *(x for x in (gruppe, sort_spalte) if x)]}
    zeilen = []
    for o in objs:
        werte = {key: s.wert(o, k) for key, s in benoetigt.items()}
        h = o if liste.basis == "haushalt" else o.haushalt
        texte = [sp.text(werte[s.schluessel]) for s in sichtbar]
        paare = list(zip([s.titel for s in sichtbar], texte, strict=True))
        zeilen.append({"pk": o.pk, "nummer": h.kundennummer, "werte": werte, "zellen": texte,
                       "paare": paare})  # fmt: skip
    if sort_spalte:
        zeilen.sort(key=lambda z: z["nummer"])
        zeilen.sort(key=lambda z: sp.sortschluessel(z["werte"][sort_spalte.schluessel]),
                    reverse=sort.startswith("-"))  # fmt: skip
        if sort.startswith("-"):  # leere Werte trotzdem hinten
            zeilen.sort(key=lambda z: z["werte"][sort_spalte.schluessel] in (None, ""))
    ergebnis = Ergebnis(spalten=sichtbar, anzahl=len(zeilen),
                        haushalte={z["nummer"] for z in zeilen})  # fmt: skip
    zahlen = [s for s in sichtbar if s.zahl]
    ergebnis.summen = {s.schluessel: sum(z["werte"][s.schluessel] or 0 for z in zeilen)
                       for s in zahlen}  # fmt: skip
    if gruppe:
        nach = {}
        for z in zeilen:
            nach.setdefault(sp.text(z["werte"][gruppe.schluessel]) or "(ohne Angabe)", []).append(z)
        reihenfolge = list(nach)
        if gruppe.schluessel == "altersgruppe":
            ordnung = [t for _, t in sp.ALTERSGRUPPEN] + ["unbekannt"]
            reihenfolge.sort(key=ordnung.index)
        elif gruppe.schluessel == "groesse":
            reihenfolge.sort(key=lambda t: int(t.split()[0]))
        elif gruppe.schluessel == "seit_monat":
            reihenfolge.sort()
        elif p.get("summen"):
            reihenfolge.sort(key=lambda t: (-len(nach[t]), t.casefold()))  # größte zuerst
        else:
            reihenfolge.sort(key=lambda t: (t == "(ohne Angabe)", t.casefold()))
        for titel in reihenfolge:
            gz = nach[titel]
            ergebnis.gruppen.append({"titel": titel, "zeilen": gz, "anzahl": len(gz), "summen": [
                sp.text(sum(z["werte"][s.schluessel] or 0 for z in gz)) if s.zahl else ""
                for s in sichtbar]})  # fmt: skip
    ergebnis.summen_zeile = [sp.text(ergebnis.summen[s.schluessel]) if s.zahl else ""
                             for s in sichtbar]  # fmt: skip
    if not gruppe:
        ergebnis.gruppen.append({"titel": "", "zeilen": zeilen, "anzahl": len(zeilen),
                                 "summen": ergebnis.summen_zeile})  # fmt: skip
    ergebnis.zahl_titel = [s.titel for s in zahlen]
    ergebnis.zahlen = [(s.titel, sp.text(ergebnis.summen[s.schluessel])) for s in zahlen]
    for g in ergebnis.gruppen:
        g["zahlen"] = [(s.titel, t) for s, t in zip(sichtbar, g["summen"], strict=True) if s.zahl]
    return ergebnis
