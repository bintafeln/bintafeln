"""Stationen aus einer CSV-Datei (``stationen.csv``, docs/importformat-touren.md) übernehmen.

Zwei Schritte wie beim Adressbuch: ``pruefen()`` liest die Datei und erstellt einen Bericht,
``uebernehmen()`` schreibt in einer Transaktion. Die Spalte ``kennung`` entscheidet: Gibt es die
Station schon, wird sie aktualisiert, sonst neu angelegt. Beim Aktualisieren überschreiben nur
gefüllte Zellen – eine leere Zelle heißt „unbekannt“, nicht „löschen“, damit ein unvollständiger
Auszug keine von Hand gepflegten Angaben leert. Stationen, die in der Datei fehlen, bleiben
unverändert. Der Export schreibt dieselben Spalten, die Datei lässt sich also zurücklesen.
"""

import csv
import io
import re
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.utils import timezone

from apps.adressen.importieren import ImportFehler, text_lesen
from apps.ausgabe.ampel import wochentage
from apps.kunden import werte
from apps.touren.models import Station

__all__ = ["ImportFehler", "text_lesen", "pruefen", "uebernehmen", "exportieren", "SPALTEN"]

SPALTEN = [
    "kennung", "art", "name", "kette", "filialnummer", "strasse", "hausnummer", "plz", "ort",
    "ortsteil", "telefon", "email", "email_lieferschein", "ansprechpartner", "oeffnungszeiten",
    "abholtage", "abholzeit", "anfahrt", "lieferschein", "aktiv", "breite", "laenge", "notiz",
]  # fmt: skip
PFLICHT = ["kennung", "art", "name", "strasse", "plz", "ort"]
JA_NEIN = ("lieferschein", "aktiv")
KOORDINATEN = {"breite": 90, "laenge": 180}
MAX_ZEILEN = 5000

# Art: Wert aus dem Format, Bezeichnung in der Oberfläche und ein paar naheliegende Wörter
ARTEN = {wert: wert for wert in Station.Art.values}
ARTEN.update({label.lower(): wert for wert, label in Station.Art.choices})
ARTEN.update({"bäckerei": "baeckerei", "baeckerei": "baeckerei", "supermarkt": "markt",
              "discounter": "markt", "laden": "markt", "firma": "lieferant",
              "großhandel": "lieferant", "grosshandel": "lieferant"})  # fmt: skip


@dataclass
class Bericht:
    neu: list[dict] = field(default_factory=list)
    # (Zeile, Name, geänderte Felder als Bezeichnungen, Daten mit Kennung)
    geaendert: list[tuple[int, str, list[str], dict]] = field(default_factory=list)
    unveraendert: list[tuple[int, str]] = field(default_factory=list)
    fehler: list[tuple[int, str]] = field(default_factory=list)
    unbekannte_spalten: list[str] = field(default_factory=list)

    @property
    def etwas_zu_tun(self) -> bool:
        return bool(self.neu or self.geaendert)


def _bezeichnung(feld: str) -> str:
    return str(Station._meta.get_field(feld).verbose_name)


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
    bericht = Bericht(unbekannte_spalten=[k for k in kopf if k and k not in SPALTEN])
    vorhanden = {s.kennung: s for s in Station.objects.all()}
    gesehen: set[str] = set()
    for nummer, zeile in enumerate(leser, start=2):
        if nummer > MAX_ZEILEN + 1:
            raise ImportFehler(f"Mehr als {MAX_ZEILEN} Zeilen; bitte aufteilen.")
        roh = {s: (zeile.get(s) or "").strip() for s in SPALTEN if s in kopf}
        if not any(roh.values()):
            continue
        try:
            daten = _zeile(roh)
        except (werte.UngueltigerWert, ValidationError) as fehler:
            meldung = "; ".join(fehler.messages) if isinstance(fehler, ValidationError) else (
                str(fehler))  # fmt: skip
            bericht.fehler.append((nummer, meldung))
            continue
        kennung = daten["kennung"]
        if kennung in gesehen:
            bericht.fehler.append((nummer, f"Kennung „{kennung}“ steht mehrfach in der Datei"))
            continue
        gesehen.add(kennung)
        station = vorhanden.get(kennung)
        if station is None:
            bericht.neu.append(daten)
            continue
        anders = [f for f, wert in daten.items() if f != "kennung" and getattr(station, f) != wert]
        if anders:
            bericht.geaendert.append(
                (nummer, station.name, [_bezeichnung(f) for f in anders],
                 {"kennung": kennung, **{f: daten[f] for f in anders}})
            )  # fmt: skip
        else:
            bericht.unveraendert.append((nummer, station.name))
    return bericht


def _zeile(w: dict) -> dict:
    """Werte einer Zeile prüfen und umwandeln; leere Zellen fehlen im Ergebnis (außer Pflicht)."""
    for s in PFLICHT:
        if not w.get(s):
            raise werte.UngueltigerWert(f"{s} fehlt")
    daten: dict = {}
    for s, text in w.items():
        if not text:
            continue
        if s == "art":
            wert = ARTEN.get(text.lower())
            if wert is None:
                raise werte.UngueltigerWert(
                    f"unbekannte Art „{text}“ (erlaubt: {', '.join(Station.Art.values)})"
                )
            daten[s] = wert
        elif s in JA_NEIN:
            daten[s] = werte.ja_nein(text)
        elif s == "abholtage":
            tage = wochentage(text)
            if not tage:
                raise werte.UngueltigerWert(f"keine Wochentage erkannt in „{text}“ (Mo, Di, …)")
            daten[s] = ", ".join(tage)
        elif s in KOORDINATEN:
            try:
                zahl = Decimal(text.replace(",", ".")).quantize(Decimal("0.000001"))
            except InvalidOperation:
                raise werte.UngueltigerWert(f"{s}: keine Zahl „{text}“") from None
            if abs(zahl) > KOORDINATEN[s]:
                raise werte.UngueltigerWert(f"{s}: „{text}“ liegt außerhalb ±{KOORDINATEN[s]}")
            daten[s] = zahl
        elif s in ("email", "email_lieferschein"):
            EmailValidator(message=f"keine gültige E-Mail: {text}")(text)
            daten[s] = text
        else:
            grenze = Station._meta.get_field(s).max_length
            if grenze and len(text) > grenze:
                raise werte.UngueltigerWert(f"{s} ist länger als {grenze} Zeichen")
            daten[s] = text
    if not re.fullmatch(r"\d{4,5}", daten["plz"]):
        raise werte.UngueltigerWert(f"PLZ „{daten['plz']}“ ist keine Postleitzahl")
    if ("breite" in daten) != ("laenge" in daten):
        raise werte.UngueltigerWert("breite und laenge nur zusammen angeben")
    return daten


@transaction.atomic
def uebernehmen(bericht: Bericht, von: str) -> tuple[int, int]:
    """Legt die neuen Stationen an und aktualisiert die geänderten. Rückgabe (neu, geändert)."""
    jetzt = timezone.now()
    for daten in bericht.neu:
        Station.objects.create(**daten, geaendert_am=jetzt, geaendert_von=von)
    for _, _, _, daten in bericht.geaendert:
        station = Station.objects.select_for_update().get(kennung=daten["kennung"])
        for feld, wert in daten.items():
            setattr(station, feld, wert)
        station.geaendert_am, station.geaendert_von = jetzt, von
        station.save()
    return len(bericht.neu), len(bericht.geaendert)


def exportieren(stationen) -> str:
    """CSV mit denselben Spalten wie der Import (Semikolon, UTF-8 mit BOM für Excel)."""
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    schreiber.writerow(SPALTEN)
    for s in stationen:
        zeile = []
        for feld in SPALTEN:
            wert = getattr(s, feld)
            if feld in JA_NEIN:
                wert = "ja" if wert else "nein"
            zeile.append("" if wert is None else str(wert))
        schreiber.writerow(zeile)
    return "﻿" + puffer.getvalue()
