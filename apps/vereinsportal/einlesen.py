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
from apps.core.models import TafelEinstellungen
from apps.spenden.models import Spende, SpendenBeleg, SpendenEinstellungen
from apps.vereinsportal import namen
from apps.vereinsportal.models import Kontakt, PortalEinstellungen
from apps.vereinsportal.namen import normal

FREMD = (Spende.Fremdbeleg.OFFEN, Spende.Fremdbeleg.VERSENDET)
MAX_BELEGE = 5000
MAX_PDF = 10 * 1024 * 1024
MIN_VERSCHIEDEN = 5  # ab so vielen Belegen muss es mehr als einen Spender geben
MAX_EXCEL = 30 * 1024 * 1024
MAX_ZEILEN = 20000
BLATT = "Spenden - Übersicht"
KOPFZEILE = 6
TAG = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})\b")
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
    belege: int = 0  # Spendenbelege (PDF) in der Datei
    dateien: int = 0  # alle Dateien im Archiv
    pdfs: int = 0  # davon PDF, auch solche, die keine Spendenbelege sind
    hinweis: str = ""  # warum sich der erste ausgelassene Beleg nicht lesen ließ (ohne Inhalte)

    @property
    def leer(self) -> bool:
        """Aus einem Archiv kam kein einziger Beleg an (weder neu noch schon vorhanden)."""
        return bool(self.dateien) and not (self.neu or self.doppelt)

    def warum_leer(self) -> str:
        if not self.belege:
            return (
                f"Die Datei enthält keine Spendenbelege: {self.dateien} Dateien, davon "
                f"{self.pdfs} PDF, aber keines mit „Spenden“ im Namen. Wurde der Export im "
                "Vereinsportal mit den Belegen erzeugt, und stimmt der Zeitraum?"
            )
        return (
            f"Kein Beleg ließ sich lesen ({self.belege} in der Datei): Bei allen fehlt die Zeile "
            "mit Absender und Anschrift oder ein Datum. Stimmt der „Name des Vereins im Absender "
            f"der Belege“ in den Einstellungen zum Vereinsportal? {self.hinweis}"
        ).strip()


def bericht(e: Ergebnis) -> str:
    """Das Ergebnis eines Einlesens als Satz für die Oberfläche."""
    if e.leer:
        return e.warum_leer()
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


def _zerlegen(text: str) -> list[str]:
    # PDF-Text enthält Ligaturen („ff“ als ein Zeichen) und unsichtbare Zeichen
    return [z.strip() for z in zeichen.bereinigen(text).split("\n") if z.strip()]


def _text_pypdf(inhalt: bytes, **optionen) -> str:
    seiten = PdfReader(io.BytesIO(inhalt)).pages
    return "\n".join(seite.extract_text(**optionen) or "" for seite in seiten)


def _text_pdfium(inhalt: bytes) -> str:
    import pypdfium2 as pdfium

    dokument = pdfium.PdfDocument(inhalt)
    try:
        return "\n".join(seite.get_textpage().get_text_range() for seite in dokument)
    finally:
        dokument.close()


# Wie ein PDF seinen Text in Zeilen ausgibt, hängt vom Werkzeug ab. Der Reihe nach versuchen:
# einfache Ausgabe, Ausgabe nach Anordnung auf der Seite, zweite Bibliothek.
LESARTEN = (
    lambda inhalt: _text_pypdf(inhalt),
    lambda inhalt: _text_pypdf(inhalt, extraction_mode="layout"),
    _text_pdfium,
)


def _lesarten(inhalt: bytes):
    """Der Text des Belegs in Zeilen, je Lesart einmal; kaputte PDFs liefern nichts."""
    for lesen in LESARTEN:
        try:
            zeilen = _zerlegen(lesen(inhalt))
        except Exception:  # noqa: BLE001, S112 – ein kaputtes PDF bricht den Lauf nicht ab
            continue
        if zeilen:
            yield zeilen


def _zeilen(inhalt: bytes) -> list[str]:
    return next(_lesarten(inhalt), [])


def _dicht(text: str) -> str:
    """Zum Vergleichen: ohne Leerzeichen und Groß-/Kleinschreibung („e. V.“ = „e.V.“)."""
    return re.sub(r"\s+", "", text).lower()


def _teile(zeile: str) -> list[str] | None:
    """„Name | Straße | PLZ Ort“ als drei Teile; None, wenn die Zeile das nicht hergibt."""
    teile = [t.strip() for t in zeile.split("|")]
    return teile if len(teile) >= 3 and all(teile[:3]) else None


PLZ_ORT = re.compile(r"^\d{5}\s+\S")


def _block(zeilen: list[str], anker: int) -> list[str] | None:
    """Anschrift als Block unter der Absenderzeile: Name, (Zusatz,) Straße, „PLZ Ort“ – jede
    Angabe in ihrer eigenen Zeile, ohne „|“."""
    for j in range(anker + 3, min(anker + 6, len(zeilen))):
        if PLZ_ORT.match(zeilen[j]) and "|" not in "".join(zeilen[anker + 1 : j + 1]):
            return [zeilen[anker + 1], zeilen[j - 1], zeilen[j]]
    return None


def spenderzeile(zeilen: list[str], absender: str = "", eigene=()) -> list[str] | None:
    """Die Anschrift des Spenders. Auf dem Beleg steht die Absenderzeile des Vereins
    („Verein | Straße | Ort“) und darunter der Spender – in derselben Form oder als Block mit
    einer Angabe je Zeile. Je nach Lesart liegt eine Zeile dazwischen, oder der Spender steht
    davor. ``eigene`` sind weitere Namen des Vereins (Name der Tafel, Körperschaft): Eine Zeile,
    in der einer davon steht, ist nie der Spender."""
    gesucht = _dicht(absender)
    namen_des_vereins = [n for n in map(_dicht, (absender, *eigene)) if n]
    vom_verein = [any(n in _dicht(z) for n in namen_des_vereins) for z in zeilen]
    mit_strich = [i for i, z in enumerate(zeilen) if "|" in z]
    if not mit_strich:
        return None
    anker = next((i for i in mit_strich if vom_verein[i]), None)
    if anker is None and not gesucht:  # ohne Angabe gilt die erste Zeile mit „|“ als Absender
        anker = mit_strich[0]
    if anker is not None:
        # die nächsten drei Zeilen, sonst die Zeile davor – nie eine Zeile des Vereins selbst
        for i in [*range(anker + 1, anker + 4), anker - 1]:
            if 0 <= i < len(zeilen) and not vom_verein[i] and (teile := _teile(zeilen[i])):
                return teile
        return _block(zeilen, anker)
    # Der Name des Vereins steht nirgends im Text (anders geschrieben oder als Bild). Gibt es
    # genau eine Zeile der Form „Name | Straße | PLZ Ort“, ist sie der Spender – außer darunter
    # steht eine Anschrift als Block: dann war die Zeile der Absender.
    passende = [i for i in mit_strich if (t := _teile(zeilen[i])) and PLZ_ORT.match(t[2])]
    if len(passende) != 1:
        return None
    return _block(zeilen, passende[0]) or _teile(zeilen[passende[0]])


def _muster(text: str) -> str:
    """Die Form eines Textes ohne seinen Inhalt: Buchstaben als x/X, Ziffern als 9."""
    return re.sub(r"[a-zäöüß]", "x", re.sub(r"[A-ZÄÖÜ]", "X", re.sub(r"\d", "9", text)))


def diagnose(inhalt: bytes, absender: str = "") -> str:
    """Warum sich ein Beleg nicht lesen ließ – Zahlen, Ja/Nein und die Form der Zeilen mit „|“
    (Buchstaben als x), keine Inhalte."""
    lesarten = list(_lesarten(inhalt))
    if not lesarten:
        return "Aus dem PDF ließ sich kein Text lesen (z. B. eingescannt oder geschützt)."
    zeilen = lesarten[0]
    gesucht = _dicht(absender)
    striche = [z for z in zeilen if "|" in z]
    gefunden = any(gesucht in _dicht(z) for z in zeilen) if gesucht else None
    in_strichzeile = any(gesucht in _dicht(z) for z in striche) if gesucht else None
    ja = {True: "ja", False: "nein", None: "nicht angegeben"}
    formen = "; ".join(f"„{_muster(z)[:80]}“" for z in striche[:3])
    return (
        f"Erster Beleg: {len(zeilen)} Textzeilen, davon {len(striche)} mit „|“; Name des Vereins "
        f"gefunden: {ja[gefunden]}, in einer Zeile mit „|“: {ja[in_strichzeile]}; Datum "
        f"gefunden: {ja[spendendatum(zeilen) is not None]}."
        + (f" Eingetragen ist „{absender.strip()}“." if gesucht and not gefunden else "")
        + (f" Form der Zeilen mit „|“ (Buchstaben als x): {formen}." if formen else "")
    )


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


def beleg_lesen(inhalt: bytes, absender: str = "", eigene=()) -> Angaben | None:
    """Spender, Jahr und Betrag aus einem Beleg; None ohne vollständige Anschrift."""
    for zeilen in _lesarten(inhalt):
        teile, datum = spenderzeile(zeilen, absender, eigene), spendendatum(zeilen)
        if teile and datum:
            return _angaben(zeilen, teile, datum)
    return None


def _angaben(zeilen: list[str], teile: list[str], datum: dt.date) -> Angaben:
    jahr = datum.year
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
    alle = [i for i in archiv.infolist() if not i.is_dir()]
    ergebnis.dateien, ergebnis.belege = len(alle), len(belege)
    ergebnis.pdfs = sum(i.filename.lower().endswith(".pdf") for i in alle)
    if len(belege) > MAX_BELEGE:
        raise EinleseFehler(f"Mehr als {MAX_BELEGE} Belege; bitte einen kürzeren Zeitraum wählen.")
    # Erst alle neuen Belege lesen, dann anlegen: So lässt sich vorher prüfen, ob das Ergebnis
    # plausibel ist.
    eigene = (TafelEinstellungen.laden().name, SpendenEinstellungen.laden().koerperschaft)
    gelesen = []
    for eintrag in belege:
        name = eintrag.filename.rsplit("/", 1)[-1][:200]
        if name in vorhanden:
            ergebnis.doppelt += 1
            continue
        inhalt = archiv.read(eintrag) if eintrag.file_size <= MAX_PDF else b""
        angaben = beleg_lesen(inhalt, absender, eigene)
        if angaben is None:
            ergebnis.ohne_anschrift += 1
            ergebnis.hinweis = ergebnis.hinweis or diagnose(inhalt, absender)
            continue
        gelesen.append((eintrag, name, angaben))
    spender = {normal(a.name) for _, _, a in gelesen}
    if len(gelesen) >= MIN_VERSCHIEDEN and len(spender) == 1:
        raise EinleseFehler(
            f"Alle {len(gelesen)} Belege nennen denselben Spender – das ist vermutlich die "
            "Anschrift des Vereins selbst, nicht die der Spender. Nichts wurde eingelesen. Bitte "
            "unter „Einstellungen → Verein → Vereinsportal“ den „Namen des Vereins im Absender "
            "der Belege“ genau so eintragen, wie er auf einem Beleg in der kleinen Zeile über "
            "der Anschrift steht."
        )
    for eintrag, name, angaben in gelesen:
        inhalt = archiv.read(eintrag)
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
