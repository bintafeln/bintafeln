"""Spendenentwicklung als Grafik (Vorschläge): Geldspenden je Monat und Jahr, Verlauf der
Jahressumme, Anzahl, Spenden nach Höhe, Einmal- und Mehrfachspender. Gezeichnet mit den
Diagrammen der Statistik (ADR 0036, SVG ohne JavaScript); jeder Abschnitt auch als Tabelle und
CSV. Gezählt werden Geldspenden (mit Mitgliedsbeiträgen, wenn sie als Spende erfasst sind)."""

from collections import Counter
from decimal import Decimal

from django.db.models import Count, Sum

from apps.spenden.models import Spende
from apps.statistik import diagramme
from apps.statistik.auswertung import Serie

MONATE = ["Jan", "Feb", "Mär", "Apr", "Mai", "Jun", "Jul", "Aug", "Sep", "Okt", "Nov", "Dez"]
# Spendenhöhe in Stufen (bis einschließlich)
STUFEN = [(Decimal("25"), "bis 25 €"), (Decimal("100"), "25,01 – 100 €"),
          (Decimal("500"), "100,01 – 500 €"), (None, "über 500 €")]  # fmt: skip


def _euro(wert) -> str:
    return diagramme._zahl(float(wert or 0), 2) + " €"


def _geld(jahr=None):
    qs = Spende.objects.filter(art=Spende.Art.GELD, betrag__gt=0)
    return qs.filter(datum__year=jahr) if jahr else qs


def je_monat(jahr: int) -> list[float]:
    werte = [0.0] * 12
    for monat, summe in _geld(jahr).values_list("datum__month").annotate(s=Sum("betrag")):
        werte[monat - 1] = float(summe or 0)
    return werte


def anzahl_je_monat(jahr: int) -> list[int]:
    werte = [0] * 12
    for monat, n in _geld(jahr).values_list("datum__month").annotate(n=Count("pk")):
        werte[monat - 1] = n
    return werte


def laufend(werte: list[float], bis_monat: int = 12) -> list[float]:
    """Laufende Summe bis zum Monat; danach nichts mehr (für das laufende Jahr)."""
    summe, ergebnis = 0.0, []
    for w in werte[:bis_monat]:
        summe += w
        ergebnis.append(summe)
    return ergebnis


def _monat_bis(jahr: int, heute) -> int:
    return heute.month if jahr == heute.year else 12


def abschnitt_monate(jahr: int, heute) -> dict:
    jetzt, vorher = je_monat(jahr), je_monat(jahr - 1)
    bis = _monat_bis(jahr, heute)
    # linien() braucht gleich lange Reihen: im laufenden Jahr beide nur bis zum aktuellen Monat
    serien = [Serie(str(jahr - 1), vorher[:bis], sum(vorher[:bis]), farbe=1),
              Serie(str(jahr), jetzt[:bis], sum(jetzt[:bis]), farbe=0)]  # fmt: skip
    return {
        "id": "monate", "titel": f"Geldspenden je Monat {jahr} im Vergleich zu {jahr - 1}",
        "text": "Summe der Geldspenden in jedem Monat. Die hellere Linie ist das Vorjahr.",
        "svg": diagramme.linien(MONATE[:bis], serien, "Geldspenden je Monat", " €")
        if any(jetzt) or any(vorher) else "",
        "kopf": ["Monat", str(jahr), str(jahr - 1)],
        "zeilen": [[MONATE[i], _euro(jetzt[i]), _euro(vorher[i])] for i in range(12)],
    }  # fmt: skip


def abschnitt_verlauf(jahr: int, heute) -> dict:
    """„Kontoentwicklung“: wie die Spenden im Lauf des Jahres zusammenkommen."""
    bis = _monat_bis(jahr, heute)
    jetzt, vorher = laufend(je_monat(jahr), bis), laufend(je_monat(jahr - 1), bis)
    gesamt_vorher = sum(je_monat(jahr - 1))
    serien = [Serie(str(jahr - 1), vorher, vorher[-1] if vorher else 0, farbe=1),
              Serie(str(jahr), jetzt, jetzt[-1] if jetzt else 0, farbe=0)]  # fmt: skip
    text = (
        "Die Spenden des Jahres zusammengezählt, Monat für Monat – so sieht man, ob das Jahr "
        "besser oder schlechter läuft als das Vorjahr zur selben Zeit."
    )
    if jetzt and bis < 12 and gesamt_vorher:
        text += (f" Bis Ende {MONATE[bis - 1]}: {_euro(jetzt[-1])}; im Vorjahr bis dahin "
                 f"{_euro(vorher[-1])}, im ganzen Vorjahr {_euro(gesamt_vorher)}.")  # fmt: skip
    return {
        "id": "verlauf", "titel": f"Spendensumme im Jahresverlauf {jahr}",
        "text": text,
        "svg": diagramme.linien(MONATE[:bis], serien, "Spendensumme im Jahresverlauf", " €")
        if any(jetzt) or any(vorher) else "",
        "kopf": ["bis Ende", str(jahr), str(jahr - 1)],
        "zeilen": [[MONATE[i], _euro(jetzt[i]), _euro(vorher[i])] for i in range(bis)],
    }  # fmt: skip


def abschnitt_anzahl(jahr: int) -> dict:
    werte = anzahl_je_monat(jahr)
    daten = list(zip(MONATE, werte, strict=True))
    return {
        "id": "anzahl", "titel": f"Anzahl der Geldspenden je Monat {jahr}",
        "text": "Wie viele einzelne Spenden in jedem Monat eingegangen sind – unabhängig von "
        "ihrer Höhe.",
        "svg": diagramme.saeulen(daten, "Anzahl der Geldspenden je Monat", farbe=2)
        if any(werte) else "",
        "kopf": ["Monat", "Spenden"], "zeilen": [[m, n] for m, n in daten],
    }  # fmt: skip


def abschnitt_jahre() -> dict:
    zeilen = list(_geld().values_list("datum__year").annotate(s=Sum("betrag"), n=Count("pk"),
                  spender=Count("adresse", distinct=True)).order_by("datum__year"))  # fmt: skip
    daten = [(str(j), float(s or 0)) for j, s, _, _ in zeilen]
    return {
        "id": "jahre", "titel": "Geldspenden je Jahr",
        "text": "Die Summe der Geldspenden in jedem Jahr, das in bintafeln erfasst ist.",
        "svg": diagramme.saeulen(daten, "Geldspenden je Jahr", " €", farbe=0) if daten else "",
        "kopf": ["Jahr", "Summe", "Spenden", "Spender"],
        "zeilen": [[j, _euro(s), n, sp] for j, s, n, sp in zeilen],
    }  # fmt: skip


def stufe(betrag) -> str:
    return next(name for grenze, name in STUFEN if grenze is None or betrag <= grenze)


def abschnitt_hoehe(jahr: int) -> dict:
    zaehler, summen = Counter(), Counter()
    for betrag in _geld(jahr).values_list("betrag", flat=True):
        zaehler[stufe(betrag)] += 1
        summen[stufe(betrag)] += betrag
    daten = [(name, zaehler[name]) for _, name in STUFEN]
    return {
        "id": "hoehe", "titel": f"Spenden nach Höhe {jahr}",
        "text": "Wie viele Spenden in welche Größenordnung fallen. Viele kleine Spenden tragen "
        "oft genauso viel bei wie wenige große – die Tabelle zeigt auch die Summen.",
        "svg": diagramme.balken(daten, "Spenden nach Höhe", farbe=3) if any(zaehler.values())
        else "",
        "kopf": ["Höhe", "Spenden", "Summe"],
        "zeilen": [[name, zaehler[name], _euro(summen[name])] for _, name in STUFEN],
    }  # fmt: skip


def abschnitt_spender(jahr: int) -> dict:
    """Einmal- und Mehrfachspender, dazu neue Spender (im Vorjahr nicht dabei)."""
    je_spender = dict(_geld(jahr).values_list("adresse").annotate(n=Count("pk")))
    vorher = set(_geld(jahr - 1).values_list("adresse", flat=True))
    einmal = sum(1 for n in je_spender.values() if n == 1)
    mehrfach = len(je_spender) - einmal
    neu = sum(1 for a in je_spender if a not in vorher)
    daten = [("einmal gespendet", einmal), ("mehrfach gespendet", mehrfach),
             ("neu (im Vorjahr nicht dabei)", neu),
             ("wieder dabei (auch im Vorjahr)", len(je_spender) - neu)]  # fmt: skip
    return {
        "id": "spender", "titel": f"Spender {jahr}",
        "text": f"{len(je_spender)} Spender im Jahr. Wer mehrfach spendet, bekommt eine "
        "Sammelbestätigung.",
        "svg": diagramme.balken(daten, "Spender", farbe=4) if je_spender else "",
        "kopf": ["Spender", "Anzahl"], "zeilen": [[n, w] for n, w in daten],
    }  # fmt: skip


def abschnitte(jahr: int, heute) -> list[dict]:
    return [abschnitt_verlauf(jahr, heute), abschnitt_monate(jahr, heute),
            abschnitt_anzahl(jahr), abschnitt_hoehe(jahr), abschnitt_spender(jahr),
            abschnitt_jahre()]  # fmt: skip


def kennzahlen(jahr: int, heute) -> dict:
    bis = _monat_bis(jahr, heute)
    jetzt = _geld(jahr).aggregate(s=Sum("betrag"), n=Count("pk"),
                                  sp=Count("adresse", distinct=True))  # fmt: skip
    vorher_bis = sum(je_monat(jahr - 1)[:bis])
    summe = float(jetzt["s"] or 0)
    return {
        "summe": _euro(summe), "anzahl": jetzt["n"], "spender": jetzt["sp"],
        "schnitt": _euro(summe / jetzt["n"]) if jetzt["n"] else "–",
        "vergleich": round((summe - vorher_bis) / vorher_bis * 100) if vorher_bis else None,
        "bis_monat": MONATE[bis - 1],
    }  # fmt: skip
