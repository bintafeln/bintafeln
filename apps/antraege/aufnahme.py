"""Aufnahme eines Antrags in den Kundenstamm (ADR 0028).

Reine Hilfsfunktionen, damit sie ohne Oberfläche testbar sind: ähnliche Kunden finden (auch bei
vertauschten oder falsch geschriebenen Namen), Gültigkeit des Ausweises vorschlagen, Kundengruppen
mit freiem Platz, nächste freie Kundennummer und das Speichern in einer Transaktion.
"""

import calendar
import datetime as dt
import difflib

from django.db import transaction
from django.db.models import Count, Q
from django.utils import timezone

from apps.kunden import gruppen, historie, merkmale
from apps.kunden.models import (
    Einkommensart,
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Kundengruppe,
    Person,
)
from apps.kunden.namen import normal

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


def _quote(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _namen_paar_n(av: str, an: str, bv: str, bn: str) -> float:
    """Wie :func:`_namen_paar`, aber mit bereits normalisierten Namen (schon klein, ohne Akzente).
    Beide Hälften müssen passen: passt nur eine (z. B. gleicher Nachname, aber anderer Vorname),
    wird stark abgewertet, damit nicht schon halbe Namensgleichheit als Treffer durchgeht."""
    vn, nn = _quote(av, bv), _quote(an, bn)
    mittel = (vn + nn) / 2
    schwaecher = min(vn, nn)
    # Erst ab spürbarer Ähnlichkeit beider Hälften zählt der Name voll; darunter (z. B. zufällig
    # ein paar gleiche Buchstaben im Vornamen) fällt der Wert schnell ab.
    return mittel if schwaecher >= 0.55 else mittel * (schwaecher / 0.55) ** 2


def _aehnlichkeit_n(av: str, an: str, bv: str, bn: str) -> float:
    """0 bis 1 aus bereits normalisierten Namen; berücksichtigt vertauschte Vor-/Nachnamen."""
    return max(_namen_paar_n(av, an, bv, bn), _namen_paar_n(av, an, bn, bv))


def namens_aehnlichkeit(vorname: str, nachname: str, v2: str, n2: str) -> float:
    """0 bis 1; berücksichtigt auch vertauschte Vor- und Nachnamen."""
    return _aehnlichkeit_n(normal(vorname), normal(nachname), normal(v2), normal(n2))


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


def einstufung(punkte: int) -> tuple[str, str]:
    """Verständliche Einstufung eines Treffers statt nackter Punkte: Schlüssel (für die Farbe)
    und Klartext. Die Punkte stehen daneben nur noch als Detail."""
    if punkte >= 80:
        return "hoch", "sehr wahrscheinlich dieselbe Person"
    if punkte >= 65:
        return "mittel", "möglich – bitte prüfen"
    return "niedrig", "eher nicht – nur bei Bedarf"


def kandidaten(av: str, an: str) -> list[tuple]:
    """Mögliche Personen aus dem Kundenstamm mit schon normalisierten Namen
    ``(person, vorname_norm, nachname_norm)`` – über den Trigramm-Index ``Person.such_name``
    (pg_trgm) nur die mit ähnlichem Namen, statt alle. Beide Reihenfolgen, damit vertauschte
    Vor-/Nachnamen gefunden werden. ``av``/``an`` sind der schon normalisierte Vor-/Nachname."""
    name, name_dreh = f"{av} {an}".strip(), f"{an} {av}".strip()
    if not name:
        return []
    qs = Person.objects.filter(
        Q(such_name__trigram_similar=name) | Q(such_name__trigram_similar=name_dreh)
    ).select_related("haushalt")
    return [(p, normal(p.vorname), normal(p.nachname)) for p in qs]


def treffer(antrag) -> list[dict]:
    """Ähnliche Haushalte, beste zuerst: {haushalt, person, punkte, gruende, stufe, stufe_text}.
    Die Vorauswahl der Personen kommt über den Trigramm-Index (:func:`kandidaten`), danach bewertet
    jede genau wie bisher – so bleibt der Abgleich auch bei großem Kundenstamm schnell."""
    beste: dict[int, dict] = {}
    if antrag.kundennummer:
        h = Haushalt.objects.filter(kundennummer__iexact=antrag.kundennummer).first()
        if h:
            beste[h.pk] = {"haushalt": h, "person": h.hauptperson, "punkte": 100,
                           "gruende": ["Kundennummer aus dem Antrag"]}  # fmt: skip
    plz, strasse = (antrag.plz or "").strip(), normal(antrag.strasse)
    av, an = normal(antrag.vorname), normal(antrag.nachname)
    for p, pv, pn in kandidaten(av, an):
        name = _aehnlichkeit_n(av, an, pv, pn)
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
    liste = sorted(beste.values(), key=lambda t: -t["punkte"])[:MAX_TREFFER]
    for t in liste:
        t["stufe"], t["stufe_text"] = einstufung(t["punkte"])
    return liste


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
    merkmale.gdb_setzen(hp, antrag.gdb, antrag.merkzeichen)
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
        merkmale.gdb_setzen(person, p.get("gdb"), p.get("merkzeichen", ""))
        person.save()
        behalten.add(person.pk)
    h.personen.filter(ist_hauptperson=False).exclude(pk__in=behalten).delete()

    antrag.kundennummer = h.kundennummer
    antrag.status_setzen(antrag.Status.ERLEDIGT, von)
    gruppen.pruefen(h)
    historie.festhalten(
        h.kundennummer, vorher, historie.schnappschuss(h),
        quelle=HaushaltEreignis.Quelle.AUFNAHME, von=von,
        zusatz=f"{'Aufgenommen' if neu else 'Aktualisiert'} mit Antrag {antrag.nummer}",
    )  # fmt: skip
    return h
