"""Finanzexport und Spenderliste aus dem Vereinsportal in den Spendenpool einlesen (ADR 0128).

Die Regeln zum Lesen stammen aus dem bisherigen Spendenbelege-Programm der Tafel:

- Finanzexport (ZIP): jede PDF-Datei mit „spenden“ im Namen ist ein Spendenbeleg. Die
  Belegnummer steht im Dateinamen (``Spendenbeleg_000123.pdf`` -> 123), der Spender in der Zeile
  unter der Absenderzeile (``Name | Straße | PLZ Ort``). Belege ohne vollständige Anschrift
  werden nicht übernommen.
- Die Excel-Datei des Finanzexports, Blatt „Spenden - Übersicht“ (Spaltennamen in Zeile 6),
  sagt über „Versendet am“ und „SQ-erstellt Datum“, welche Belegnummern schon versendet sind.
- Liste „Spender mit E-Mail“ (Excel): Spalten Vorname, Nachname, E-Mail, dazu auf Wunsch
  „Anrede“ (für die Briefanrede) und „immer per Post“.

Jeder Beleg wird eine Spende im gemeinsamen Spendenpool (``apps.spenden``): der Spender im
Adressbuch, die Spende mit Datum, Betrag und Belegnummer, das PDF als ``SpendenBeleg`` daran.
``Spende.fremdbeleg`` hält fest, dass es dafür schon einen Beleg aus dem Vereinsportal gibt und
ob er dort versendet ist – damit bintafeln nie eine zweite Bestätigung ausstellt.
"""

import datetime as dt
import io
import re
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from openpyxl import load_workbook
from pypdf import PdfReader

from apps.adressen.models import Adresse
from apps.core import privatdateien, zeichen
from apps.spenden.models import Spende, SpendenBeleg
from apps.vereinsportal import namen
from apps.vereinsportal.models import Kontakt, PortalEinstellungen
from apps.vereinsportal.namen import normal

FREMD = (Spende.Fremdbeleg.OFFEN, Spende.Fremdbeleg.VERSENDET)
MAX_BELEGE = 5000
MAX_PDF = 10 * 1024 * 1024
MAX_EXCEL = 30 * 1024 * 1024
MAX_ZEILEN = 20000
BLATT = "Spenden - Übersicht"
KOPFZEILE = 6
TAG = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
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
    datum: dt.date | None = None


@dataclass
class Ergebnis:
    neu: int = 0
    neue_spender: int = 0
    doppelt: int = 0
    ohne_anschrift: int = 0
    versendet: int = 0
    mit_uebersicht: bool = False


def bericht(e: Ergebnis) -> str:
    """Das Ergebnis eines Einlesens als Satz für die Oberfläche."""
    teile = [f"{e.neu} neue Spenden eingelesen", f"{e.doppelt} waren schon vorhanden"]
    if e.neue_spender:
        teile.append(f"{e.neue_spender} Spender neu ins Adressbuch aufgenommen")
    if e.ohne_anschrift:
        teile.append(f"{e.ohne_anschrift} ohne vollständige Anschrift ausgelassen")
    teile.append(
        f"{e.versendet} als im Vereinsportal versendet vermerkt" if e.mit_uebersicht
        else "keine Übersicht der versendeten Belege in der Datei gefunden"
    )  # fmt: skip
    return ", ".join(teile) + "."


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
    # PDF-Text enthält Ligaturen („ff“ als ein Zeichen) und unsichtbare Zeichen
    return [z.strip() for z in zeichen.bereinigen(text).split("\n") if z.strip()]


def _daten(zeile: str):
    for tag, monat, jahr in TAG.findall(zeile):
        try:
            yield dt.date(int(jahr), int(monat), int(tag))
        except ValueError:  # z. B. 31.02.
            continue


def spendendatum(zeilen: list[str]) -> dt.date | None:
    """Der Tag der Zuwendung: das Datum bei „Tag der Zuwendung“ (in derselben oder einer der
    nächsten Zeilen, je nachdem wie das PDF seine Tabelle ausgibt), sonst das erste Datum im
    Beleg."""
    marke = next((i for i, z in enumerate(zeilen) if "tag der zuwendung" in z.lower()), None)
    bereiche = ([zeilen[marke : marke + 4]] if marke is not None else []) + [zeilen]
    return next((d for bereich in bereiche for z in bereich for d in _daten(z)), None)


def beleg_lesen(inhalt: bytes, absender: str = "") -> Angaben | None:
    """Spender, Jahr und Betrag aus einem Beleg; None ohne vollständige Anschrift."""
    zeilen = _zeilen(inhalt)
    gesucht = absender.strip().lower()
    spender = next(
        (zeilen[i + 1] for i, z in enumerate(zeilen[:-1]) if "|" in z and gesucht in z.lower()),
        None,
    )
    datum = spendendatum(zeilen)
    jahr = datum.year if datum else None
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
    return Angaben(teile[0][:250], teile[1][:200], teile[2][:200], jahr, betrag, datum)


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
    offen = Spende.objects.filter(belegnummer__in=nummern, fremdbeleg=Spende.Fremdbeleg.OFFEN)
    return offen.update(fremdbeleg=Spende.Fremdbeleg.VERSENDET)


def uebersicht_einlesen(inhalt: bytes) -> Ergebnis:
    """Nur die Excel-Datei des Finanzexports: vermerkt, was inzwischen versendet ist."""
    nummern = versendete(inhalt)
    if nummern is None:
        raise EinleseFehler(
            f"In der Datei fehlt das Blatt „{BLATT}“ mit der Spalte „Belegnummer“ in Zeile "
            f"{KOPFZEILE}."
        )
    return Ergebnis(versendet=_versendet_vermerken(nummern), mit_uebersicht=True)


class _Adressbuch:
    """Findet den Spender eines Belegs im Adressbuch (Name und PLZ) oder legt ihn an."""

    def __init__(self, von: str):
        self.von, self.neu = von, 0
        self.index = {}
        for a in Adresse.objects.only("pk", "art", "organisation", "vorname", "nachname", "plz"):
            self.index.setdefault(namen.schluessel(a.name, a.plz), a.pk)
        self.kontakte = {k.such_name: k for k in Kontakt.objects.all()}

    def adresse(self, angaben: Angaben) -> int:
        plz, ort = namen.plz_ort(angaben.plz_ort)
        schluessel = namen.schluessel(angaben.name, plz)
        if schluessel not in self.index:
            a = Adresse(**namen.teile(angaben.name), strasse=angaben.strasse, plz=plz, ort=ort,
                        geaendert_am=timezone.now(), geaendert_von=self.von)  # fmt: skip
            kontakt_anwenden(a, self.kontakte.get(normal(angaben.name)))
            a.save()
            self.index[schluessel] = a.pk
            self.neu += 1
        return self.index[schluessel]


def kontakt_anwenden(adresse: Adresse, kontakt: Kontakt | None) -> bool:
    """E-Mail, Anrede und Versandweg aus der Liste „Spender mit E-Mail“ in die Adresse. Eine
    schon eingetragene andere E-Mail bleibt; „immer per Post“ nimmt die Einwilligung zurück."""
    if kontakt is None:
        return False
    vorher = (adresse.email, adresse.anrede, adresse.einwilligung_email)
    adresse.email = adresse.email or kontakt.email
    if adresse.art == Adresse.Art.PERSON:
        adresse.anrede = adresse.anrede or kontakt.anrede
    if kontakt.immer_post:
        adresse.einwilligung_email = None
    elif adresse.email == kontakt.email:
        adresse.einwilligung_email = adresse.einwilligung_email or timezone.localdate()
    return vorher != (adresse.email, adresse.anrede, adresse.einwilligung_email)


@transaction.atomic
def finanzexport_einlesen(datei, von: str) -> Ergebnis:
    """Der Finanzexport als ZIP: neue Belege als Spenden anlegen, Versendetes vermerken."""
    try:
        archiv = zipfile.ZipFile(datei)
    except zipfile.BadZipFile as fehler:
        raise EinleseFehler("Die Datei ist kein ZIP-Archiv.") from fehler
    absender = PortalEinstellungen.laden().absender
    # Was schon da ist: Belege aus dem Vereinsportal (am Dateinamen) und Spenden mit derselben
    # Belegnummer, z. B. aus einem früheren CSV-Import
    vorhanden = set(SpendenBeleg.objects.filter(spende__fremdbeleg__in=FREMD)
                    .values_list("dateiname", flat=True))  # fmt: skip
    nach_nummer = {s.belegnummer: s for s in Spende.objects.exclude(belegnummer="")}
    buch, ergebnis, nummern = _Adressbuch(von), Ergebnis(), set()
    eintraege = ((i, i.filename.lower()) for i in archiv.infolist())
    belege = [i for i, n in eintraege if "spenden" in n and n.endswith(".pdf")]
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
        nummer = belegnummer(name)
        spende = nach_nummer.get(nummer) if nummer else None
        if spende is None:
            spende = Spende.objects.create(
                art=Spende.Art.GELD, adresse_id=buch.adresse(angaben), datum=angaben.datum,
                betrag=angaben.betrag, belegnummer=nummer, eingetragen_von=von,
                fremdbeleg=Spende.Fremdbeleg.OFFEN,
            )  # fmt: skip
            if nummer:
                nach_nummer[nummer] = spende
            ergebnis.neu += 1
        else:  # die Spende gibt es schon: nur den Beleg anhängen und kennzeichnen
            if not spende.fremdbeleg:
                spende.fremdbeleg = Spende.Fremdbeleg.OFFEN
                spende.save(update_fields=["fremdbeleg"])
            ergebnis.doppelt += 1
        SpendenBeleg.objects.create(
            adresse_id=spende.adresse_id, spende=spende, jahr=spende.datum.year, dateiname=name,
            datei=privatdateien.ablegen(SpendenBeleg.ORDNER, inhalt), hochgeladen_von=von,
        )  # fmt: skip
        vorhanden.add(name)
    for eintrag in archiv.infolist():
        if eintrag.filename.lower().endswith(".xlsx") and eintrag.file_size <= MAX_EXCEL:
            gefunden = versendete(archiv.read(eintrag))
            if gefunden is not None:
                nummern |= gefunden
                ergebnis.mit_uebersicht = True
    ergebnis.versendet = _versendet_vermerken(nummern)
    ergebnis.neue_spender = buch.neu
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
    kontakte_anwenden()
    return len(kontakte), ohne_mail


def kontakte_anwenden() -> int:
    """Trägt E-Mail und Versandweg bei allen Spendern aus dem Vereinsportal nach."""
    kontakte = {k.such_name: k for k in Kontakt.objects.all()}
    geaendert = 0
    for a in Adresse.objects.filter(spenden__fremdbeleg__in=FREMD).distinct():
        if kontakt_anwenden(a, kontakte.get(normal(a.name))):
            a.save(update_fields=["email", "anrede", "einwilligung_email"])
            geaendert += 1
    return geaendert
