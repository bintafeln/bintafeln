"""Spenden aus einer CSV-Datei übernehmen, z. B. aus dem Export eines Vereinsportals oder einer
Kontoliste (ADR 0055). Neutrales Format wie beim Adress-Import: erst ``pruefen()`` mit Bericht,
dann ``uebernehmen()`` in einer Transaktion.

Der Spender wird über die E-Mail oder über Name und PLZ einer vorhandenen Adresse zugeordnet;
unbekannte Spender werden als neue Adresse angelegt (vorhandene Adressen werden nie geändert).
Eine ``belegnummer`` (z. B. die Nummer im Vereinsportal) verhindert, dass dieselbe Spende bei einem
späteren Import noch einmal angelegt wird.
"""

import csv
import io
from dataclasses import dataclass, field
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import transaction
from django.utils import timezone

from apps.adressen.importieren import ImportFehler, _schluessel, text_lesen
from apps.adressen.models import Adresse
from apps.kunden import werte
from apps.spenden.models import Spende

__all__ = ["ImportFehler", "text_lesen", "pruefen", "uebernehmen", "SPALTEN"]

SPENDE_SPALTEN = ["datum", "betrag", "art", "beschreibung", "zahlungsweg", "zweck", "belegnummer",
                  "mitgliedsbeitrag"]  # fmt: skip
ADRESS_SPALTEN = ["organisation", "anrede", "vorname", "nachname", "strasse", "plz", "ort",
                  "email", "einwilligung_post", "einwilligung_email"]  # fmt: skip
SPALTEN = SPENDE_SPALTEN + ADRESS_SPALTEN
MAX_ZEILEN = 20000
ARTEN = {"": Spende.Art.GELD, "geld": Spende.Art.GELD, "geldspende": Spende.Art.GELD,
         "sach": Spende.Art.SACH, "sachspende": Spende.Art.SACH}  # fmt: skip


@dataclass
class Bericht:
    spenden: list[dict] = field(default_factory=list)  # je Spende: Felder + "spender"
    neue_spender: dict[str, dict] = field(default_factory=dict)  # Schlüssel -> Adressdaten
    vorhandene_spender: set[int] = field(default_factory=set)
    doppelt: list[tuple[int, str]] = field(default_factory=list)  # (Zeile, Belegnummer)
    fehler: list[tuple[int, str]] = field(default_factory=list)
    unbekannte_spalten: list[str] = field(default_factory=list)

    @property
    def summe(self) -> Decimal:
        return sum((s["betrag"] or Decimal("0") for s in self.spenden), Decimal("0"))


def _adressdaten(w: dict) -> dict:
    art = Adresse.Art.ORGANISATION if w["organisation"] and not w["nachname"] else (
        Adresse.Art.PERSON)  # fmt: skip
    daten = {s: w[s] for s in ADRESS_SPALTEN if not s.startswith("einwilligung")}
    daten["art"] = art
    daten["einwilligung_post"] = werte.datum(w["einwilligung_post"])
    daten["einwilligung_email"] = werte.datum(w["einwilligung_email"])
    if daten["email"]:
        EmailValidator(message=f"keine gültige E-Mail: {daten['email']}")(daten["email"])
    Adresse(**daten).clean()
    for feld in ("organisation", "anrede", "vorname", "nachname", "strasse", "plz", "ort"):
        grenze = Adresse._meta.get_field(feld).max_length
        if len(daten[feld]) > grenze:
            raise werte.UngueltigerWert(f"{feld} ist länger als {grenze} Zeichen")
    return daten


def _name(daten: dict) -> str:
    if daten["art"] == Adresse.Art.ORGANISATION:
        return daten["organisation"]
    return f"{daten['vorname']} {daten['nachname']}".strip()


def _spende(w: dict) -> dict:
    art = ARTEN.get(w["art"].lower())
    if art is None:
        raise werte.UngueltigerWert(f"unbekannte Art „{w['art']}“ (Geld oder Sach)")
    datum = werte.datum(w["datum"])
    if datum is None:
        raise werte.UngueltigerWert("Datum fehlt")
    if datum > timezone.localdate():
        raise werte.UngueltigerWert(f"Datum liegt in der Zukunft: {w['datum']}")
    daten = {
        "art": art, "datum": datum, "betrag": werte.betrag(w["betrag"]),
        "beschreibung": w["beschreibung"], "zahlungsweg": w["zahlungsweg"], "zweck": w["zweck"],
        "belegnummer": w["belegnummer"],
        "mitgliedsbeitrag": werte.ja_nein(w["mitgliedsbeitrag"]) if w["mitgliedsbeitrag"]
        else False,
    }  # fmt: skip
    Spende(**daten).clean()
    for feld in ("beschreibung", "zahlungsweg", "zweck", "belegnummer"):
        grenze = Spende._meta.get_field(feld).max_length
        if len(daten[feld]) > grenze:
            raise werte.UngueltigerWert(f"{feld} ist länger als {grenze} Zeichen")
    return daten


def pruefen(text: str) -> Bericht:
    zeilen = text.splitlines()
    if not zeilen:
        raise ImportFehler("Die Datei ist leer.")
    trenner = ";" if zeilen[0].count(";") >= zeilen[0].count(",") else ","
    leser = csv.DictReader(io.StringIO(text, newline=""), delimiter=trenner)
    kopf = [(k or "").strip().lower() for k in (leser.fieldnames or [])]
    leser.fieldnames = kopf
    fehlt = [s for s in ("datum", "betrag") if s not in kopf]
    if fehlt or not {"organisation", "nachname"} & set(kopf):
        raise ImportFehler(
            "Die erste Zeile braucht Spaltennamen, mindestens „datum“, „betrag“ und "
            "„organisation“ oder „nachname“ (Trennzeichen Semikolon). Gefunden: "
            f"{', '.join(kopf) or 'nichts'}."
        )
    bericht = Bericht(unbekannte_spalten=[k for k in kopf if k and k not in SPALTEN])
    nach_mail, nach_name = {}, {}
    for a in Adresse.objects.only("pk", "art", "organisation", "vorname", "nachname", "plz",
                                  "email"):  # fmt: skip
        nach_name.setdefault(_schluessel(a.name, a.plz), a.pk)
        if a.email:
            nach_mail.setdefault(a.email.lower(), a.pk)
    belege = set(Spende.objects.exclude(belegnummer="").values_list("belegnummer", flat=True))
    in_datei: dict[str, int] = {}
    for nummer, zeile in enumerate(leser, start=2):
        if nummer > MAX_ZEILEN + 1:
            raise ImportFehler(f"Mehr als {MAX_ZEILEN} Zeilen; bitte aufteilen.")
        w = {s: (zeile.get(s) or "").strip() for s in SPALTEN}
        if not any(w.values()):
            continue
        try:
            spende = _spende(w)
            adresse = _adressdaten(w)
        except (werte.UngueltigerWert, ValidationError) as fehler:
            meldung = "; ".join(fehler.messages) if isinstance(fehler, ValidationError) else (
                str(fehler))  # fmt: skip
            bericht.fehler.append((nummer, meldung))
            continue
        beleg = spende["belegnummer"]
        if beleg and beleg in belege:
            bericht.doppelt.append((nummer, beleg))
            continue
        if beleg and beleg in in_datei:
            bericht.fehler.append((nummer, f"Belegnummer {beleg} steht schon in Zeile "
                                           f"{in_datei[beleg]}"))  # fmt: skip
            continue
        schluessel = _schluessel(_name(adresse), adresse["plz"])
        pk = (nach_mail.get(adresse["email"].lower()) if adresse["email"] else None) or (
            nach_name.get(schluessel))  # fmt: skip
        if pk:
            spende["spender"] = pk
            bericht.vorhandene_spender.add(pk)
        else:
            mail = adresse["email"].lower()
            vorher = next((k for k, d in bericht.neue_spender.items()
                           if mail and d["email"].lower() == mail), None)  # fmt: skip
            schluessel = vorher or schluessel
            bericht.neue_spender.setdefault(schluessel, adresse)
            spende["spender"] = schluessel
        if beleg:
            in_datei[beleg] = nummer
        bericht.spenden.append(spende)
    return bericht


@transaction.atomic
def uebernehmen(bericht: Bericht, von: str) -> int:
    jetzt = timezone.now()
    neu = {schluessel: Adresse.objects.create(**daten, geaendert_am=jetzt, geaendert_von=von)
           for schluessel, daten in bericht.neue_spender.items()}  # fmt: skip
    for daten in bericht.spenden:
        daten = dict(daten)
        spender = daten.pop("spender")
        adresse = neu[spender] if isinstance(spender, str) else Adresse.objects.get(pk=spender)
        Spende.objects.create(adresse=adresse, eingetragen_von=von, **daten)
    return len(bericht.spenden)
