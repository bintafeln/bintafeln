"""Aufnahme eines Antrags in den Kundenstamm (ADR 0028).

Reine Hilfsfunktionen, damit sie ohne Oberfläche testbar sind: ähnliche Kunden finden (auch bei
vertauschten oder falsch geschriebenen Namen), Gültigkeit des Ausweises vorschlagen, Kundengruppen
mit freiem Platz, nächste freie Kundennummer und das Speichern in einer Transaktion.
"""

import calendar
import datetime as dt
import difflib
import re
import unicodedata

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.kunden import historie
from apps.kunden.models import (
    Einkommensart,
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Kundengruppe,
    Person,
)

MIN_PUNKTE = 55
MAX_TREFFER = 10

# Feld, Bezeichnung, gehört zum Haushalt (sonst zur Hauptperson)
FELDER = [
    ("anrede", "Anrede", False),
    ("vorname", "Vorname", False),
    ("nachname", "Nachname", False),
    ("geburtsdatum", "Geburtsdatum", False),
    ("strasse", "Straße und Hausnummer", True),
    ("plz", "PLZ", True),
    ("ort", "Ort", True),
    ("telefon", "Telefon", True),
    ("email", "E-Mail", True),
    ("familienstand", "Familienstand", False),
    ("staatsangehoerigkeit", "Staatsangehörigkeit", False),
]
UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normal(text: str) -> str:
    """Für Vergleiche: klein, Umlaute ausgeschrieben, ohne Akzente und Satzzeichen."""
    text = (text or "").lower().translate(UMLAUTE)
    text = "".join(z for z in unicodedata.normalize("NFKD", text) if not unicodedata.combining(z))
    return " ".join(re.sub(r"[^a-z ]+", " ", text).split())


def _quote(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def namens_aehnlichkeit(vorname: str, nachname: str, v2: str, n2: str) -> float:
    """0 bis 1; vertauschte Vor- und Nachnamen und Doppelnamen zählen voll."""
    a, b = normal(f"{vorname} {nachname}"), normal(f"{v2} {n2}")
    sortiert = lambda t: " ".join(sorted(t.split()))  # noqa: E731
    return max(
        _quote(a, b),
        _quote(a, normal(f"{n2} {v2}")),
        _quote(sortiert(a), sortiert(b)),
    )


def _datum_punkte(a: dt.date | None, b: dt.date | None) -> tuple[int, str]:
    if not a or not b:
        return 0, ""
    if a == b:
        return 30, "gleiches Geburtsdatum"
    if a.year == b.year and a.day == b.month and a.month == b.day:
        return 20, "Geburtsdatum mit vertauschtem Tag und Monat"
    if a.year == b.year:
        return 5, "gleiches Geburtsjahr"
    return 0, ""


def treffer(antrag) -> list[dict]:
    """Ähnliche Haushalte, beste zuerst: {haushalt, person, punkte, gruende}."""
    beste: dict[int, dict] = {}
    if antrag.kundennummer:
        h = Haushalt.objects.filter(kundennummer__iexact=antrag.kundennummer).first()
        if h:
            beste[h.pk] = {"haushalt": h, "person": h.hauptperson, "punkte": 100,
                           "gruende": ["Kundennummer aus dem Antrag"]}  # fmt: skip
    plz, strasse = (antrag.plz or "").strip(), normal(antrag.strasse)
    for p in Person.objects.select_related("haushalt"):
        name = namens_aehnlichkeit(antrag.vorname, antrag.nachname, p.vorname, p.nachname)
        if name < 0.5:
            continue
        punkte = round(name * 70)
        gruende = [f"Name zu {round(name * 100)} % ähnlich"]
        dp, grund = _datum_punkte(antrag.geburtsdatum, p.geburtsdatum)
        if dp:
            punkte += dp
            gruende.append(grund)
        h = p.haushalt
        if plz and h.plz == plz and _quote(strasse, normal(h.strasse)) > 0.8:
            punkte += 10
            gruende.append("gleiche Anschrift")
        punkte = min(punkte, 100)
        if punkte >= MIN_PUNKTE and punkte > beste.get(h.pk, {}).get("punkte", 0):
            beste[h.pk] = {"haushalt": h, "person": p, "punkte": punkte, "gruende": gruende}
    return sorted(beste.values(), key=lambda t: -t["punkte"])[:MAX_TREFFER]


def monat_plus(datum: dt.date, monate: int, monatsende: bool) -> dt.date:
    jahr, monat = divmod(datum.month - 1 + monate, 12)
    jahr, monat = datum.year + jahr, monat + 1
    letzter = calendar.monthrange(jahr, monat)[1]
    return dt.date(jahr, monat, letzter if monatsende else min(datum.day, letzter))


def gueltigkeit_auswahl(heute: dt.date, e: KundenEinstellungen) -> list[tuple[str, str]]:
    """Vorschlag aus den Einstellungen zuerst, dann 3, 6, 12 und 24 Monate."""
    auswahl, gesehen = [], set()
    for monate in [e.ausweis_gueltig_monate, 3, 6, 12, 24]:
        bis = monat_plus(heute, monate, e.ausweis_bis_monatsende)
        if bis in gesehen:
            continue
        gesehen.add(bis)
        zusatz = " (Vorschlag)" if not auswahl else ""
        auswahl.append((bis.isoformat(), f"{monate} Monate: bis {bis:%d.%m.%Y}{zusatz}"))
    return auswahl


def freie_gruppen(haushalt: Haushalt | None = None) -> list[dict]:
    """Aktive Kundengruppen mit freiem Platz (gezählt in Haushalten, ohne beendete).

    Die bisherige Gruppe eines bestehenden Haushalts bleibt immer wählbar.
    """
    belegt = Count("haushalte", filter=~Q(haushalte__status=Haushalt.Status.BEENDET))
    gruppen = []
    for g in (
        Kundengruppe.objects.filter(aktiv=True)
        .select_related("ausgabestelle")
        .annotate(belegt=belegt)
        .order_by("ausgabestelle__name", "name")
    ):
        frei = None if g.maximum is None else g.maximum - g.belegt
        eigene = haushalt is not None and haushalt.kundengruppe_id == g.pk
        if frei is None or frei > 0 or eigene:
            gruppen.append({"gruppe": g, "belegt": g.belegt, "frei": frei, "eigene": eigene})
    return gruppen


def naechste_kundennummer() -> str:
    """Nächste freie Zahl über der höchsten rein numerischen Kundennummer."""
    zahlen = [
        int(n) for n in Haushalt.objects.values_list("kundennummer", flat=True) if n.isdigit()
    ]
    return str(max(zahlen, default=0) + 1)


def _datum(wert):
    return dt.date.fromisoformat(wert) if wert else None


@transaction.atomic
def uebernehmen(antrag, zustand: dict, von: str) -> Haushalt:
    """Legt den Haushalt an oder aktualisiert ihn und schließt den Antrag ab.

    zustand: haushalt (Kundennummer oder None), werte (Feld → Wert), personen (Liste mit pk,
    vorname, nachname, geburtsdatum, staatsangehoerigkeit), einkommensart (pk), gueltig_bis (ISO),
    kundengruppe (pk).
    """
    jetzt = timezone.now()
    h = Haushalt.objects.select_for_update().filter(kundennummer=zustand.get("haushalt")).first()
    neu = h is None
    vorher = historie.schnappschuss(h)
    if neu:
        h = Haushalt(kundennummer=naechste_kundennummer(), kunde_seit=timezone.localdate())
        h.aufgenommen_am = jetzt
    werte = zustand.get("werte", {})
    for feld, _, zum_haushalt in FELDER:
        if zum_haushalt and feld in werte:
            setattr(h, feld, werte[feld] or "")
    h.status = Haushalt.Status.AKTIV
    if zustand.get("einkommensart"):
        h.einkommensart = Einkommensart.objects.filter(pk=zustand["einkommensart"]).first()
    if zustand.get("gueltig_bis"):
        h.ausweis_gueltig_bis = _datum(zustand["gueltig_bis"])
    if zustand.get("kundengruppe"):
        h.kundengruppe = Kundengruppe.objects.filter(pk=zustand["kundengruppe"]).first()
    h.geaendert_am, h.geaendert_von = jetzt, von
    h.anzahl_erwachsene = h.anzahl_kinder = None  # ergibt sich aus den Personen
    h.save()

    hp = h.hauptperson if not neu else None
    if hp is None:
        h.personen.update(ist_hauptperson=False)
        hp = Person(haushalt=h, ist_hauptperson=True)
    for feld, _, zum_haushalt in FELDER:
        if not zum_haushalt and feld in werte:
            setattr(hp, feld, _datum(werte[feld]) if feld == "geburtsdatum" else werte[feld] or "")
    hp.save()

    behalten = set()
    for p in zustand.get("personen", []):
        if not (p.get("vorname") or "").strip():
            continue
        person = h.personen.filter(pk=p.get("pk"), ist_hauptperson=False).first() if p.get(
            "pk") else None  # fmt: skip
        person = person or Person(haushalt=h)
        person.vorname, person.nachname = p["vorname"].strip(), (p.get("nachname") or "").strip()
        person.geburtsdatum = _datum(p.get("geburtsdatum"))
        if "staatsangehoerigkeit" in p:  # ältere Zwischenstände ohne das Feld ändern nichts
            person.staatsangehoerigkeit = p["staatsangehoerigkeit"]
        person.save()
        behalten.add(person.pk)
    h.personen.filter(ist_hauptperson=False).exclude(pk__in=behalten).delete()

    antrag.kundennummer = h.kundennummer
    antrag.status_setzen(antrag.Status.ERLEDIGT, von)
    historie.festhalten(
        h.kundennummer, vorher, historie.schnappschuss(h),
        quelle=HaushaltEreignis.Quelle.AUFNAHME, von=von,
        zusatz=f"{'Aufgenommen' if neu else 'Aktualisiert'} mit Antrag {antrag.nummer}",
    )  # fmt: skip
    return h
