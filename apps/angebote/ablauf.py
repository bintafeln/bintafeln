"""Regeln für Angebote mit Anmeldung (ADR 0131), ohne Oberfläche testbar.

Am Einlass werden Interessierte gesammelt, bis die Höchstzahl erreicht ist; dann schließt die
Liste von selbst. Das Büro vergibt die Plätze – als Vorgabe in der Reihenfolge der Anmeldung."""

import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.angebote.models import Angebot, Interesse

MITZAEHLEN = [Interesse.Stand.INTERESSIERT, Interesse.Stand.ZUGESAGT,
              Interesse.Stand.NACHRUECKER]  # fmt: skip


class AngebotFehler(ValueError):
    """Meldung für die Oberfläche."""


def anzahl(angebot: Angebot) -> int:
    """Interessierte, die zählen (Absagen zählen nicht – ihr Platz in der Liste wird frei)."""
    return angebot.interessierte.filter(stand__in=MITZAEHLEN).count()


def laeuft(angebot: Angebot, heute: dt.date) -> bool:
    """Liegt heute im Zeitraum der Anmeldung (unabhängig davon, ob noch Platz ist)?"""
    return angebot.anmeldung_von <= heute <= angebot.anmeldung_bis


def offen(angebot: Angebot, heute: dt.date) -> bool:
    """Kann am Einlass noch jemand eingetragen werden?"""
    return (laeuft(angebot, heute) and not angebot.geschlossen
            and anzahl(angebot) < angebot.hoechstens)  # fmt: skip


def laufende(heute: dt.date):
    return Angebot.objects.filter(anmeldung_von__lte=heute, anmeldung_bis__gte=heute)


def eingetragen(angebot: Angebot, kundennummer: str):
    return angebot.interessierte.filter(kundennummer=kundennummer)


def _schon_da(angebot, haushalt, person) -> bool:
    return (
        eingetragen(angebot, haushalt.kundennummer)
        .filter(vorname=person.vorname, nachname=person.nachname, geburtsdatum=person.geburtsdatum)
        .exists()
    )


def noch_frei(angebot: Angebot, haushalt) -> list:
    """Personen des Haushalts, die noch nicht eingetragen sind – die Hauptperson zuerst."""
    personen = sorted(haushalt.personen.all(), key=lambda p: (not p.ist_hauptperson, p.pk))
    return [p for p in personen if not _schon_da(angebot, haushalt, p)]


@transaction.atomic
def eintragen(angebot: Angebot, haushalt, person, *, stelle=None, von: str = "",
              heute: dt.date | None = None) -> Interesse:  # fmt: skip
    """Trägt eine Person des Haushalts als interessiert ein. Die Zeile des Angebots wird dabei
    gesperrt, damit zwei Einlass-Plätze gleichzeitig die Höchstzahl nicht überschreiten."""
    heute = heute or timezone.localdate()
    angebot = Angebot.objects.select_for_update().get(pk=angebot.pk)
    if person.haushalt_id != haushalt.pk:
        raise AngebotFehler("Diese Person gehört nicht zu diesem Haushalt.")
    if not laeuft(angebot, heute):
        raise AngebotFehler(f"Für „{angebot}“ läuft gerade keine Anmeldung.")
    if angebot.geschlossen:
        raise AngebotFehler(f"Die Anmeldung für „{angebot}“ ist geschlossen.")
    if anzahl(angebot) >= angebot.hoechstens:
        raise AngebotFehler(f"Die Liste für „{angebot}“ ist voll.")
    if _schon_da(angebot, haushalt, person):
        raise AngebotFehler(f"{person.vorname} {person.nachname} ist schon eingetragen.")
    return Interesse.objects.create(
        angebot=angebot, kundennummer=haushalt.kundennummer, vorname=person.vorname,
        nachname=person.nachname, geburtsdatum=person.geburtsdatum, telefon=haushalt.telefon,
        ausgabestelle=stelle, eingetragen_von=von,
    )  # fmt: skip


@transaction.atomic
def plaetze_vergeben(angebot: Angebot) -> tuple[int, int]:
    """Vorgabe für die Plätze: die ersten in der Reihenfolge der Anmeldung bekommen einen Platz,
    die übrigen werden Nachrücker. Absagen bleiben. Liefert (zugesagt, Nachrücker); einzelne
    lassen sich danach von Hand ändern."""
    liste = list(angebot.interessierte.select_for_update().filter(stand__in=MITZAEHLEN))
    for nr, eintrag in enumerate(liste):
        neu = Interesse.Stand.ZUGESAGT if nr < angebot.plaetze else Interesse.Stand.NACHRUECKER
        if eintrag.stand != neu:
            eintrag.stand = neu
            eintrag.save(update_fields=["stand"])
    zugesagt = min(len(liste), angebot.plaetze)
    return zugesagt, len(liste) - zugesagt


def zahlen(angebot: Angebot) -> dict:
    je_stand = {s: 0 for s in Interesse.Stand.values}
    for stand in angebot.interessierte.values_list("stand", flat=True):
        je_stand[stand] += 1
    interessiert = sum(je_stand[s] for s in MITZAEHLEN)
    return {**je_stand, "anzahl": interessiert,
            "frei": max(angebot.hoechstens - interessiert, 0)}  # fmt: skip


def einlass(haushalt, heute: dt.date, stelle=None) -> list[dict]:
    """Hinweise für die Einlass-Karte: je laufendem Angebot der Stand der Liste, wer aus dem
    Haushalt schon eingetragen ist, und der Knopf zum Eintragen."""
    from django.urls import reverse

    hinweise = []
    for angebot in laufende(heute):
        n = anzahl(angebot)
        da = [e.name for e in eingetragen(angebot, haushalt.kundennummer)
              .filter(stand__in=MITZAEHLEN)]  # fmt: skip
        text = f"{angebot.bezeichnung} – {n} von {angebot.hoechstens} Interessierten"
        if da:
            text += f". Eingetragen: {', '.join(da)}"
        kann = offen(angebot, heute)
        if not kann:
            text += ". Anmeldung geschlossen" if angebot.geschlossen else ". Liste voll"
        hinweis = {"text": text, "farbe": "info"}
        if kann or da:
            hinweis["knopf"] = {
                "recht": "angebote.eintragen",
                "url": reverse("angebote:eintragen", args=[angebot.pk, haushalt.kundennummer]),
                "text": "Interesse eintragen …" if kann and not da else "Eintrag ändern …",
                "erklaerung": (angebot.beschreibung or "Trägt eine Person dieses Haushalts als "
                               "interessiert ein.")[:300],
            }  # fmt: skip
        hinweise.append(hinweis)
    return hinweise


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Löscht die Einträge der Kunden, wenn die Frist nach dem Ende des Angebots abgelaufen ist.
    Das Angebot selbst (ohne Personendaten) bleibt."""
    heute = heute or timezone.localdate()
    geloescht = 0
    for angebot in Angebot.objects.filter(interessierte__isnull=False).distinct():
        if angebot.ende + dt.timedelta(days=angebot.loeschen_nach_tagen) < heute:
            geloescht += angebot.interessierte.all().delete()[0]
    return geloescht
