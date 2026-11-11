"""Besuche eines Tages aus dem bisherigen Programm übernehmen, Kundenkonto angleichen (ADR 0110).

Liest die Tages-Abholungsliste aus dem bisherigen Programm (Excel **oder** CSV) und trägt je Kunde
den **Besuch** als Abholung nach. Der **Kontostand** wird dabei genau auf den Wert aus der Liste
gesetzt – nicht direkt, sondern über eine **Korrektur-Buchung** (ADR 0014: Kundenkonto nur über
``apps.ausgabe.konto``). Weil der exportierte Stand Vorauszahlungen schon enthält, stimmt das Konto
danach automatisch.

Die Spalten werden tolerant über die Überschriften erkannt; das Datum heißt je nach Export
„Letzter Besuch“ oder „Letzte Abholung“. Es geht auch eine **reine Kontostand-Liste** (alle Kunden
mit Guthaben, ganz **ohne** Datumsspalte, zusätzliche Spalten wie Name/Vorname werden ignoriert):
Dann wird nur der Kontostand gesetzt (kein Besuch nachgetragen).

Vorgehen: erst :func:`plan` (Probelauf, bucht nichts) zeigt, was passieren würde; dann
:func:`uebernehmen` legt die Abholungen an und bucht die Korrekturen in einer Transaktion. Beides
ist mehrfach anwendbar: Ein Besuch wird je Kunde und Tag nur einmal angelegt, und eine Korrektur
fällt weg, wenn der Stand schon passt (Differenz 0).

Mehrtages-Listen: Der Besuch wird je Tag angelegt; für den Kontostand zählt der **jüngste** Tag je
Kunde (der aktuellste Stand ist die Wahrheit).
"""

import csv
import datetime as dt
import io
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

import openpyxl

BREITE = 5  # Das bisherige Programm zeigt die Kundennummer fünfstellig mit führenden Nullen

SPALTEN = {
    "kundennummer": ("kundennummer", "nummer"),
    "datum": ("letzter besuch", "besuch", "letzte abholung", "abholung", "datum", "tag"),
    "uhrzeit": ("uhrzeit", "zeit"),
    "betrag": ("beitrag", "betrag"),
    "kontostand": ("kontostand", "guthaben", "saldo", "konto"),
}


class BesucheFehler(Exception):
    """Die hochgeladene Datei ist keine lesbare Besuchsliste."""


# ── Zellwerte ────────────────────────────────────────────────────────────────


def _knr(wert) -> str:
    if isinstance(wert, int):
        return str(wert).zfill(BREITE)
    return str(wert if wert is not None else "").strip()


def _datum(wert) -> dt.date | None:
    if isinstance(wert, dt.datetime):
        return wert.date()
    if isinstance(wert, dt.date):
        return wert
    text = str(wert if wert is not None else "").strip()[:10]
    for fmt in ("%d.%m.%Y", "%Y-%m-%d", "%d.%m.%y"):
        try:
            return dt.datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def _zeit(wert) -> dt.time | None:
    if isinstance(wert, dt.datetime):
        return wert.time().replace(second=0, microsecond=0)
    if isinstance(wert, dt.time):
        return wert.replace(second=0, microsecond=0)
    teile = str(wert if wert is not None else "").strip().split(":")
    if len(teile) >= 2 and teile[0].strip().isdigit() and teile[1].strip().isdigit():
        try:
            return dt.time(int(teile[0]), int(teile[1]))
        except ValueError:
            return None
    return None


def euro(b: Decimal) -> str:
    """Decimal → deutsches Geldformat, z. B. '1.234,50 €'."""
    return f"{b:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _betrag(wert) -> Decimal | None:
    if wert is None or wert == "":
        return None
    if isinstance(wert, (int, float, Decimal)):
        return Decimal(str(wert))
    text = str(wert).replace("€", "").replace("EUR", "").strip().replace(" ", "")
    if not text or text in ("-", "--"):
        return None
    if "," in text:  # deutsches Format: Punkt = Tausender, Komma = Dezimal
        text = text.replace(".", "").replace(",", ".")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


# ── Datei lesen (Excel oder CSV) ─────────────────────────────────────────────


@dataclass
class Zeile:
    kundennummer: str
    datum: dt.date | None
    uhrzeit: dt.time | None
    betrag: Decimal | None
    kontostand: Decimal | None


def _kopf_finden(zeilen: list[list]) -> int:
    for i, r in enumerate(zeilen):
        if any(str(c).strip().lower() == "kundennummer" for c in r if c is not None):
            return i
    raise BesucheFehler(
        "In der Datei wurde keine Spalte „Kundennummer“ gefunden. Bitte die Tagesliste der "
        "Abholungen aus dem bisherigen Programm unverändert als Excel- oder CSV-Datei hochladen."
    )


def _xlsx_zeilen(daten: bytes) -> list[list]:
    try:
        wb = openpyxl.load_workbook(io.BytesIO(daten), read_only=True, data_only=True)
    except Exception as fehler:  # noqa: BLE001
        raise BesucheFehler("Die Datei ließ sich nicht als Excel-Datei (.xlsx) öffnen.") from fehler
    ws = wb[wb.sheetnames[0]]
    return [list(r) for r in ws.iter_rows(values_only=True)]


def _csv_zeilen(daten: bytes) -> list[list]:
    text = daten.decode("utf-8-sig", errors="replace")
    kopf = text[:2000]
    trenner = ";" if kopf.count(";") >= kopf.count(",") else ","
    return [list(r) for r in csv.reader(io.StringIO(text), delimiter=trenner)]


def lesen(daten: bytes) -> list[Zeile]:
    rohzeilen = _xlsx_zeilen(daten) if daten[:2] == b"PK" else _csv_zeilen(daten)
    k = _kopf_finden(rohzeilen)
    kopf = [str(c).strip().lower() if c is not None else "" for c in rohzeilen[k]]

    def spalte(feld) -> int:
        for name in SPALTEN[feld]:
            if name in kopf:
                return kopf.index(name)
        return -1

    i = {feld: spalte(feld) for feld in SPALTEN}

    def zelle(r, feld):
        j = i[feld]
        return r[j] if 0 <= j < len(r) else None

    zeilen = []
    for r in rohzeilen[k + 1 :]:
        if not r or all(c is None or str(c).strip() == "" for c in r):
            continue
        knr = _knr(zelle(r, "kundennummer"))
        if not knr:
            continue
        zeilen.append(
            Zeile(
                kundennummer=knr,
                datum=_datum(zelle(r, "datum")),
                uhrzeit=_zeit(zelle(r, "uhrzeit")),
                betrag=_betrag(zelle(r, "betrag")),
                kontostand=_betrag(zelle(r, "kontostand")),
            )
        )
    if not zeilen:
        raise BesucheFehler("In der Datei standen keine Kundennummern.")
    return zeilen


# ── Plan (Probelauf) und Übernehmen ──────────────────────────────────────────


def _besuche_und_ziele(zeilen: list[Zeile]):
    """(Besuche je Kunde+Tag, Ziel-Kontostand je Kunde).

    Für den Kontostand zählt der jüngste Tag je Kunde. Zeilen **ohne** Datum setzen den Stand
    ebenfalls – so lässt sich auch eine reine Kontostand-Liste (alle Kunden mit Guthaben, ohne
    letzten Besuch) einlesen. Ein datierter Eintrag hat dabei Vorrang vor einem undatierten.
    """
    besuche = [z for z in zeilen if z.datum]
    ziele: dict[str, tuple[dt.date | None, Decimal]] = {}
    for z in zeilen:
        if z.kontostand is None:
            continue
        vorhanden = ziele.get(z.kundennummer)
        if vorhanden is None:
            ziele[z.kundennummer] = (z.datum, z.kontostand)
            continue
        alt_tag = vorhanden[0]
        if z.datum is None:
            if alt_tag is None:  # beide ohne Datum: der letzte Eintrag gewinnt
                ziele[z.kundennummer] = (z.datum, z.kontostand)
        elif alt_tag is None or z.datum >= alt_tag:  # datiert schlägt undatiert; jüngster gewinnt
            ziele[z.kundennummer] = (z.datum, z.kontostand)
    return besuche, ziele


def plan(zeilen: list[Zeile]) -> dict:
    """Probelauf: was würde passieren? Bucht nichts, liest nur. Liefert die Konto-Änderungen (mit
    altem und neuem Stand), die neuen Besuche und unbekannte Kundennummern."""
    from apps.kunden.models import Abholung, Haushalt

    besuche, ziele = _besuche_und_ziele(zeilen)
    bekannt = {
        h.kundennummer: h
        for h in Haushalt.objects.filter(kundennummer__in={z.kundennummer for z in zeilen})
    }
    unbekannt = sorted({z.kundennummer for z in zeilen if z.kundennummer not in bekannt})
    ohne_datum = sum(1 for z in zeilen if z.datum is None)

    besuche_neu = 0
    for z in besuche:
        h = bekannt.get(z.kundennummer)
        if h and not Abholung.objects.filter(haushalt=h, datum=z.datum).exists():
            besuche_neu += 1

    konto = []
    summe = Decimal("0")
    for knr, (tag, ziel) in sorted(ziele.items()):
        h = bekannt.get(knr)
        if h is None:
            continue
        aktuell = h.kontostand or Decimal("0")
        differenz = ziel - aktuell
        if differenz != 0:
            summe += differenz
            konto.append({"kundennummer": knr, "tag": tag, "aktuell": euro(aktuell),
                          "ziel": euro(ziel), "differenz": euro(differenz),
                          "mehr": differenz > 0})  # fmt: skip
    return {
        "zeilen": len(zeilen),
        "besuche_neu": besuche_neu,
        "konto": konto,
        "summe": euro(summe),
        "unbekannt": unbekannt,
        "ohne_datum": ohne_datum,
    }


def uebernehmen(zeilen: list[Zeile], von: str) -> dict:
    """Besuche als Abholungen nachtragen und den Kontostand je Kunde per Korrektur-Buchung auf den
    Wert aus der Liste setzen. In einer Transaktion; mehrfach anwendbar (idempotent)."""
    from django.db import transaction

    from apps.ausgabe import konto as konto_
    from apps.kunden.models import Abholung, Haushalt

    besuche, ziele = _besuche_und_ziele(zeilen)
    with transaction.atomic():
        bekannt = {
            h.kundennummer: h
            for h in Haushalt.objects.filter(kundennummer__in={z.kundennummer for z in zeilen})
        }
        besuche_neu = 0
        for z in besuche:
            h = bekannt.get(z.kundennummer)
            if h is None:
                continue
            if not Abholung.objects.filter(haushalt=h, datum=z.datum).exists():
                Abholung.objects.create(
                    haushalt=h, datum=z.datum, uhrzeit=z.uhrzeit, beitrag=z.betrag,
                    eingetragen_von=von, nachgetragen=True,
                )  # fmt: skip
                besuche_neu += 1

        korrekturen = 0
        summe = Decimal("0")
        for knr, (tag, ziel) in ziele.items():
            h = bekannt.get(knr)
            if h is None:
                continue
            differenz = ziel - (h.kontostand or Decimal("0"))
            if differenz != 0:
                stand = f"Stand {tag:%d.%m.%Y}" if tag else "aktueller Stand"
                konto_.korrigieren(h, differenz, f"Abgleich bisheriges Programm ({stand})", von)
                korrekturen += 1
                summe += differenz

    unbekannt = sorted({z.kundennummer for z in zeilen if z.kundennummer not in bekannt})
    return {"besuche_neu": besuche_neu, "korrekturen": korrekturen, "summe": summe,
            "unbekannt": unbekannt}  # fmt: skip
