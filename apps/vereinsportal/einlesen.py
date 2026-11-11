"""Finanzexport und Spenderliste aus dem Vereinsportal einlesen (ADR 0126).

Die Regeln stammen aus dem bisherigen Spendenbelege-Programm der Tafel:

- Finanzexport (ZIP): jede PDF-Datei mit „spenden“ im Namen ist ein Spendenbeleg. Die
  Belegnummer steht im Dateinamen (``Spendenbeleg_000123.pdf`` -> 123), der Spender in der Zeile
  unter der Absenderzeile (``Name | Straße | PLZ Ort``). Belege ohne vollständige Anschrift
  werden nicht übernommen. Ein schon eingelesener Dateiname zählt als doppelt.
- Die Excel-Datei des Finanzexports, Blatt „Spenden - Übersicht“ (Spaltennamen in Zeile 6),
  sagt über „Versendet am“ und „SQ-erstellt Datum“, welche Belegnummern schon versendet sind.
- Liste „Spender mit E-Mail“ (Excel): Spalten Vorname, Nachname, E-Mail, dazu auf Wunsch
  „Anrede“ (für die Briefanrede) und „immer per Post“.
"""

import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from openpyxl import load_workbook
from pypdf import PdfReader

from apps.core import privatdateien
from apps.vereinsportal.models import Beleg, Kontakt, PortalEinstellungen

MAX_BELEGE = 5000
MAX_PDF = 10 * 1024 * 1024
MAX_EXCEL = 30 * 1024 * 1024
MAX_ZEILEN = 20000
BLATT = "Spenden - Übersicht"
KOPFZEILE = 6
DATUM = re.compile(r"\d{2}\.\d{2}\.(\d{4})")
BETRAG = re.compile(r"([\d.]+,\d{2})\s+[a-zä-ü\-]+", re.IGNORECASE)
NUMMER = re.compile(r"_(\d+)\.pdf$", re.IGNORECASE)


class EinleseFehler(ValueError):
    """Meldung für die Oberfläche."""


@dataclass
class Angaben:
    name: str
    strasse: str
    plz_ort: str
    jahr: int
    betrag: Decimal


@dataclass
class Ergebnis:
    neu: int = 0
    doppelt: int = 0
    ohne_anschrift: int = 0
    versendet: int = 0
    mit_uebersicht: bool = False


def normal(name: str) -> str:
    """Name zum Vergleichen: klein geschrieben, einfache Leerzeichen."""
    return " ".join((name or "").strip().lower().split())


def belegnummer(dateiname: str) -> str:
    treffer = NUMMER.search(dateiname)
    return str(int(treffer.group(1))) if treffer else ""


def _zeilen(inhalt: bytes) -> list[str]:
    try:
        text = "\n".join(
            seite.extract_text() or "" for seite in PdfReader(io.BytesIO(inhalt)).pages
        )
    except Exception:  # noqa: BLE001 – ein kaputtes PDF soll den Lauf nicht abbrechen
        return []
    return [z.strip() for z in text.split("\n") if z.strip()]


def beleg_lesen(inhalt: bytes, absender: str = "") -> Angaben | None:
    """Spender, Jahr und Betrag aus einem Beleg; None ohne vollständige Anschrift."""
    zeilen = _zeilen(inhalt)
    gesucht = absender.strip().lower()
    spender = next(
        (zeilen[i + 1] for i, z in enumerate(zeilen[:-1]) if "|" in z and gesucht in z.lower()),
        None,
    )
    jahr = next((int(t.group(1)) for t in map(DATUM.search, zeilen) if t), None)
    if not spender or not jahr:
        return None
    teile = [t.strip() for t in spender.split("|")]
    if len(teile) < 3 or not all(teile[:3]):
        return None
    betrag = Decimal("0")
    for treffer in filter(None, map(BETRAG.search, zeilen)):
        try:
            betrag = Decimal(treffer.group(1).replace(".", "").replace(",", "."))
            break
        except InvalidOperation:
            continue
    return Angaben(teile[0][:250], teile[1][:200], teile[2][:200], jahr, betrag)


def _mappe(inhalt):
    try:
        return load_workbook(io.BytesIO(inhalt), read_only=True, data_only=True)
    except Exception as fehler:  # noqa: BLE001 – openpyxl meldet kaputte Dateien uneinheitlich
        raise EinleseFehler("Die Excel-Datei lässt sich nicht lesen.") from fehler


def _nummer(wert) -> str:
    try:
        return str(int(float(str(wert).strip())))
    except ValueError:
        return str(wert).strip()


def versendete(inhalt: bytes) -> set[str] | None:
    """Belegnummern, die laut Übersicht schon versendet sind; None, wenn das Blatt fehlt."""
    mappe = _mappe(inhalt)
    if BLATT not in mappe.sheetnames:
        return None
    zeilen = mappe[BLATT].iter_rows(min_row=KOPFZEILE, values_only=True)
    kopf = [str(z or "").strip() for z in next(zeilen, ())]
    if "Belegnummer" not in kopf:
        return None
    nummer = kopf.index("Belegnummer")
    spalten = [kopf.index(s) for s in ("Versendet am", "SQ-erstellt Datum") if s in kopf]
    return {
        _nummer(z[nummer])
        for z in zeilen
        if z[nummer] not in (None, "") and any(z[s] not in (None, "") for s in spalten)
    }


def _versendet_vermerken(nummern: set[str]) -> int:
    offen = Beleg.objects.filter(belegnummer__in=nummern, im_portal_versendet=False)
    return offen.update(im_portal_versendet=True)


def uebersicht_einlesen(inhalt: bytes) -> Ergebnis:
    """Nur die Excel-Datei des Finanzexports: vermerkt, was inzwischen versendet ist."""
    nummern = versendete(inhalt)
    if nummern is None:
        raise EinleseFehler(
            f"In der Datei fehlt das Blatt „{BLATT}“ mit der Spalte „Belegnummer“ in Zeile "
            f"{KOPFZEILE}."
        )
    return Ergebnis(versendet=_versendet_vermerken(nummern), mit_uebersicht=True)


@transaction.atomic
def finanzexport_einlesen(datei, von: str) -> Ergebnis:
    """Der Finanzexport als ZIP: neue Belege speichern, Versendetes vermerken."""
    try:
        archiv = zipfile.ZipFile(datei)
    except zipfile.BadZipFile as fehler:
        raise EinleseFehler("Die Datei ist kein ZIP-Archiv.") from fehler
    absender = PortalEinstellungen.laden().absender
    vorhanden = set(Beleg.objects.values_list("dateiname", flat=True))
    ergebnis, nummern = Ergebnis(), set()
    namen = ((i, i.filename.lower()) for i in archiv.infolist())
    belege = [i for i, n in namen if "spenden" in n and n.endswith(".pdf")]
    if len(belege) > MAX_BELEGE:
        raise EinleseFehler(f"Mehr als {MAX_BELEGE} Belege; bitte einen kürzeren Zeitraum wählen.")
    for eintrag in belege:
        name = eintrag.filename.rsplit("/", 1)[-1][:200]
        if name in vorhanden:
            ergebnis.doppelt += 1
            continue
        inhalt = archiv.read(eintrag) if eintrag.file_size <= MAX_PDF else b""
        angaben = beleg_lesen(inhalt, absender)
        if angaben is None:
            ergebnis.ohne_anschrift += 1
            continue
        Beleg.objects.create(
            dateiname=name, belegnummer=belegnummer(name), name=angaben.name,
            such_name=normal(angaben.name), strasse=angaben.strasse, plz_ort=angaben.plz_ort,
            jahr=angaben.jahr, betrag=angaben.betrag, eingelesen_von=von,
            datei=privatdateien.ablegen(Beleg.ORDNER, inhalt),
        )  # fmt: skip
        vorhanden.add(name)
        ergebnis.neu += 1
    for eintrag in archiv.infolist():
        if eintrag.filename.lower().endswith(".xlsx") and eintrag.file_size <= MAX_EXCEL:
            gefunden = versendete(archiv.read(eintrag))
            if gefunden is not None:
                nummern |= gefunden
                ergebnis.mit_uebersicht = True
    ergebnis.versendet = _versendet_vermerken(nummern)
    return ergebnis


def _ja(wert) -> bool:
    return str(wert or "").strip().lower() == "ja"


@transaction.atomic
def spenderliste_einlesen(inhalt: bytes) -> tuple[int, int]:
    """Ersetzt die Liste „Spender mit E-Mail“; liefert (übernommen, ohne gültige E-Mail)."""
    zeilen = _mappe(inhalt).worksheets[0].iter_rows(values_only=True)
    kopf = [str(z or "").strip() for z in next(zeilen, ())]
    fehlt = [s for s in ("Vorname", "Nachname", "E-Mail") if s not in kopf]
    if fehlt:
        raise EinleseFehler(
            "Die erste Zeile braucht die Spalten „Vorname“, „Nachname“ und „E-Mail“ (dazu auf "
            f"Wunsch „immer per Post“). Es fehlt: {', '.join(fehlt)}."
        )
    spalte = {s: kopf.index(s) for s in ("Vorname", "Nachname", "E-Mail")}
    post = kopf.index("immer per Post") if "immer per Post" in kopf else None
    anrede = kopf.index("Anrede") if "Anrede" in kopf else None
    kontakte, ohne_mail = {}, 0
    for nummer, z in enumerate(zeilen, start=2):
        if nummer > MAX_ZEILEN + 1:
            raise EinleseFehler(f"Mehr als {MAX_ZEILEN} Zeilen.")
        vorname, nachname, email = (str(z[spalte[s]] or "").strip()
                                    for s in ("Vorname", "Nachname", "E-Mail"))  # fmt: skip
        name = f"{vorname} {nachname}".strip().removeprefix("- ").strip()
        if not name or name == "-":
            continue
        try:
            validate_email(email)
        except ValidationError:
            ohne_mail += 1
            continue
        kontakte.setdefault(normal(name), Kontakt(
            such_name=normal(name)[:250], vorname=vorname[:120], nachname=nachname[:120],
            email=email, immer_post=post is not None and _ja(z[post]),
            anrede="" if anrede is None else str(z[anrede] or "").strip()[:30],
        ))  # fmt: skip
    Kontakt.objects.all().delete()
    Kontakt.objects.bulk_create(kontakte.values())
    return len(kontakte), ohne_mail
