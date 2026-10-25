"""Adressen aus einer CSV-Datei übernehmen (ADR 0044), z. B. aus Excel oder einem Altsystem.

Zwei Schritte wie beim Kundenstamm: ``pruefen()`` liest die Datei und erstellt einen Bericht,
``uebernehmen()`` legt die gültigen, neuen Adressen in einer Transaktion an. Vorhandene Adressen
werden nie überschrieben: Gleicher Name mit gleicher PLZ oder gleiche E-Mail gilt als schon da.
Spalten wie in ``SPALTEN``; dieselben schreibt der CSV-Export, die Datei lässt sich also
zurücklesen.
"""

import csv
import io
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator
from django.db import transaction
from django.utils import timezone

from apps.adressen.models import Adresse, AdressKategorie
from apps.kunden import werte

SPALTEN = [
    "art", "organisation", "ansprechperson", "anrede", "vorname", "nachname", "strasse", "plz",
    "ort", "land", "telefon", "mobil", "email", "webseite", "kategorien", "notiz",
    "einwilligung_post", "einwilligung_email", "veroeffentlichen",
]  # fmt: skip
DATUMSFELDER = ("einwilligung_post", "einwilligung_email", "veroeffentlichen")
MAX_ZEILEN = 20000
ARTEN = {
    "person": Adresse.Art.PERSON, "privat": Adresse.Art.PERSON,
    "organisation": Adresse.Art.ORGANISATION, "firma": Adresse.Art.ORGANISATION,
    "verein": Adresse.Art.ORGANISATION, "markt": Adresse.Art.ORGANISATION,
}  # fmt: skip


class ImportFehler(ValueError):
    pass


@dataclass
class Bericht:
    neu: list[dict] = field(default_factory=list)
    vorhanden: list[tuple[int, str]] = field(default_factory=list)  # (Zeile, Name)
    fehler: list[tuple[int, str]] = field(default_factory=list)  # (Zeile, Grund)
    neue_kategorien: list[str] = field(default_factory=list)
    unbekannte_spalten: list[str] = field(default_factory=list)


def text_lesen(roh: bytes) -> str:
    """UTF-8 (auch mit BOM); sonst Windows-1252, wie Excel es oft speichert."""
    try:
        return roh.decode("utf-8-sig")
    except UnicodeDecodeError:
        return roh.decode("cp1252", errors="replace")


def _schluessel(name: str, plz: str) -> str:
    return f"{name.strip().lower()}|{plz.strip()}"


def pruefen(text: str) -> Bericht:
    zeilen = text.splitlines()
    if not zeilen:
        raise ImportFehler("Die Datei ist leer.")
    trenner = ";" if zeilen[0].count(";") >= zeilen[0].count(",") else ","
    leser = csv.DictReader(io.StringIO(text, newline=""), delimiter=trenner)
    kopf = [(k or "").strip().lower() for k in (leser.fieldnames or [])]
    leser.fieldnames = kopf
    if not {"organisation", "nachname"} & set(kopf):
        raise ImportFehler(
            "Die erste Zeile braucht Spaltennamen, mindestens „organisation“ oder „nachname“ "
            f"(Trennzeichen Semikolon). Gefunden: {', '.join(kopf) or 'nichts'}."
        )
    bericht = Bericht(unbekannte_spalten=[k for k in kopf if k and k not in SPALTEN])
    vorhanden = {_schluessel(a.name, a.plz) for a in Adresse.objects.all()}
    mails = {e.lower() for e in Adresse.objects.exclude(email="").values_list("email", flat=True)}
    kategorien = {k.name.lower(): k.name for k in AdressKategorie.objects.all()}
    for nummer, zeile in enumerate(leser, start=2):
        if nummer > MAX_ZEILEN + 1:
            raise ImportFehler(f"Mehr als {MAX_ZEILEN} Zeilen; bitte aufteilen.")
        werte_ = {s: (zeile.get(s) or "").strip() for s in SPALTEN}
        if not any(werte_.values()):
            continue
        try:
            daten = _zeile(werte_, kategorien, bericht)
        except (werte.UngueltigerWert, ValidationError) as fehler:
            meldung = "; ".join(fehler.messages) if isinstance(fehler, ValidationError) else (
                str(fehler))  # fmt: skip
            bericht.fehler.append((nummer, meldung))
            continue
        name = daten["organisation"] if daten["art"] == Adresse.Art.ORGANISATION else (
            f"{daten['vorname']} {daten['nachname']}".strip())  # fmt: skip
        schluessel = _schluessel(name, daten["plz"])
        if schluessel in vorhanden or (daten["email"] and daten["email"].lower() in mails):
            bericht.vorhanden.append((nummer, name))
            continue
        vorhanden.add(schluessel)
        if daten["email"]:
            mails.add(daten["email"].lower())
        bericht.neu.append(daten)
    return bericht


def _zeile(w: dict, kategorien: dict, bericht: Bericht) -> dict:
    art = ARTEN.get(w["art"].lower()) if w["art"] else (
        Adresse.Art.ORGANISATION if w["organisation"] and not w["nachname"]
        else Adresse.Art.PERSON)  # fmt: skip
    if art is None:
        raise werte.UngueltigerWert(f"unbekannte Art „{w['art']}“ (Person oder Organisation)")
    daten = {s: w[s] for s in SPALTEN if s not in DATUMSFELDER and s != "kategorien"}
    daten["art"] = art
    for s in DATUMSFELDER:
        daten[s] = werte.datum(w[s])
    if daten["email"]:
        EmailValidator(message=f"keine gültige E-Mail: {daten['email']}")(daten["email"])
    if daten["webseite"]:
        if "://" not in daten["webseite"]:
            daten["webseite"] = "https://" + daten["webseite"]
        URLValidator(message=f"keine gültige Webseite: {daten['webseite']}")(daten["webseite"])
    probe = Adresse(**{k: v for k, v in daten.items()})
    probe.clean()
    for feld in ("organisation", "vorname", "nachname", "strasse", "plz", "ort", "telefon"):
        grenze = Adresse._meta.get_field(feld).max_length
        if len(daten[feld]) > grenze:
            raise werte.UngueltigerWert(f"{feld} ist länger als {grenze} Zeichen")
    namen = []
    for teil in w["kategorien"].replace("|", ",").split(","):
        teil = teil.strip()
        if not teil:
            continue
        if teil.lower() not in kategorien:
            kategorien[teil.lower()] = teil[:100]
            bericht.neue_kategorien.append(teil[:100])
        namen.append(kategorien[teil.lower()])
    daten["kategorien"] = namen
    return daten


@transaction.atomic
def uebernehmen(bericht: Bericht, von: str) -> int:
    jetzt = timezone.now()
    for name in bericht.neue_kategorien:
        AdressKategorie.objects.get_or_create(name=name)
    nach_name = {k.name: k for k in AdressKategorie.objects.all()}
    for daten in bericht.neu:
        daten = dict(daten)
        kategorien = daten.pop("kategorien")
        a = Adresse.objects.create(**daten, geaendert_am=jetzt, geaendert_von=von)
        a.kategorien.set([nach_name[n] for n in kategorien])
    return len(bericht.neu)


def exportieren(adressen) -> str:
    """CSV mit denselben Spalten wie der Import (Semikolon, UTF-8 mit BOM für Excel)."""
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    schreiber.writerow(SPALTEN)
    for a in adressen.prefetch_related("kategorien"):
        zeile = []
        for s in SPALTEN:
            if s == "kategorien":
                zeile.append(", ".join(k.name for k in a.kategorien.all()))
            elif s in DATUMSFELDER:
                wert = getattr(a, s)
                zeile.append(f"{wert:%d.%m.%Y}" if wert else "")
            else:
                zeile.append(getattr(a, s))
        schreiber.writerow(zeile)
    return "﻿" + puffer.getvalue()
