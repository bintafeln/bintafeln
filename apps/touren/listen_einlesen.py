"""Marktliste und Lieferadressen im Exportformat der eco-platform in ``stationen.csv`` umschreiben.

Die eco-platform exportiert die Märkte und die Lieferadressen einer Tafel in einem festen Format,
das sich nicht anpassen lässt. Damit niemand die Dateien von Hand umbauen muss, erkennt der Import
sie an ihren Spaltennamen und schreibt sie hier in das eigene Format um
(docs/importformat-touren.md); danach läuft alles wie bei jeder ``stationen.csv`` (Prüfbericht,
neu/geändert, leere Zellen ändern nichts). Im Programm steht nur das Format – keine Daten einer
Tafel.

- **Marktliste:** ``Name; Handelskette; Externe Marktkennung; Adresse; Bemerkung; Empfänger der
  Lieferscheine; Kontakt Name; Kontakt Telefon; Kontakt E-Mail-Adresse; Nur digitaler Lieferschein``
- **Lieferadressen:** ``Name; Adresse; Kontakt; Öffnungszeiten``

Die Anschrift steht dort in einer Zelle („Musterstraße 1, 12345 Musterstadt, Deutschland“) und
wird zerlegt. Eine Kennung gibt es nicht; sie wird aus Kette und Marktkennung bzw. aus Name und
Anschrift gebildet – gleich bleibende Angaben ergeben bei jedem Import dieselbe Kennung.
"""

import csv
import io
import re
import unicodedata

MARKT_SPALTEN = {"handelskette", "externe marktkennung", "nur digitaler lieferschein"}
BAECKEREI = ("bäcker", "baecker", "backwerk", "backstube", "konditorei", "back ")
ZIEL = ["kennung", "art", "name", "kette", "filialnummer", "strasse", "hausnummer", "plz", "ort",
        "ortsteil", "telefon", "email", "email_lieferschein", "ansprechpartner",
        "oeffnungszeiten", "lieferschein", "notiz"]  # fmt: skip


def _kurz(text: str, laenge: int) -> str:
    """Kleinbuchstaben, Ziffern und Bindestriche – für die Kennung."""
    text = text.lower().replace("ß", "ss")
    for alt, neu in (("ä", "ae"), ("ö", "oe"), ("ü", "ue")):
        text = text.replace(alt, neu)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", text).strip("-")[:laenge].strip("-")


def anschrift(text: str) -> dict:
    """„Straße 1, 12345 Ort - Ortsteil, Land“ in Straße, Hausnummer, PLZ, Ort, Ortsteil. Was sich
    nicht erkennen lässt, bleibt leer – der Prüfbericht meldet die Zeile dann."""
    teile = [t.strip() for t in text.split(",")]
    daten = {"strasse": teile[0] if teile else "", "hausnummer": "", "plz": "", "ort": "",
             "ortsteil": ""}  # fmt: skip
    mit_nummer = re.match(r"^(.*?)\s+(\d[\w\s\-/+.]*)$", daten["strasse"])
    if mit_nummer:
        daten["strasse"], daten["hausnummer"] = mit_nummer.group(1), mit_nummer.group(2).strip()
    plz_ort = re.match(r"^(\d+)\s+(.*)$", teile[1]) if len(teile) > 1 else None
    if plz_ort:
        daten["plz"], ort = plz_ort.group(1), plz_ort.group(2).strip()
        bezirk = re.match(r"^(.*?)-(Stadtbezirke?\s+\S+)$", ort)
        if bezirk:
            ort, daten["ortsteil"] = bezirk.group(1), bezirk.group(2)
        else:
            teil = re.split(r"\s+[-/]\s+", ort, maxsplit=1)
            ort, daten["ortsteil"] = teil[0].strip(), (teil[1].strip() if len(teil) > 1 else "")
        daten["ort"] = ort
    return daten


def _kontakt(text: str) -> tuple[str, str]:
    """Telefon und Name aus einer Zelle: Oft steht beides darin, durch einen Tabulator getrennt
    („0123 4567<Tab>Frau Muster“)."""
    telefon, _, name = (t.strip() for t in text.partition("\t"))
    return telefon, name


def _zeile(z: dict, markt: bool) -> dict:
    name = z.get("name", "")
    daten = {"name": name, **anschrift(z.get("adresse", ""))}
    ort = f"{daten['strasse']} {daten['hausnummer']} {daten['plz']}"
    notiz = []
    if markt:
        kette, nummer = z.get("handelskette", ""), z.get("externe marktkennung", "")
        telefon, wer = _kontakt(z.get("kontakt telefon", ""))
        daten.update(
            kennung=(f"{_kurz(kette, 25)}-{_kurz(nummer, 30)}" if nummer
                     else f"m-{_kurz(name, 24)}-{_kurz(ort, 30)}"),
            art="baeckerei" if any(w in f"{name.lower()} " for w in BAECKEREI) else "markt",
            kette=kette, filialnummer=nummer,
            email=z.get("kontakt e-mail-adresse", ""),
            email_lieferschein=z.get("empfänger der lieferscheine", ""),
            ansprechpartner=z.get("kontakt name", "") or wer,
            lieferschein=z.get("nur digitaler lieferschein", ""),
        )  # fmt: skip
        if z.get("kontakt name") and wer:
            notiz.append(f"Kontakt am Telefon: {wer}")
        if z.get("bemerkung"):
            notiz.append(z["bemerkung"])
    else:
        telefon, wer = _kontakt(z.get("kontakt", ""))
        daten.update(
            kennung=f"l-{_kurz(name, 24)}-{_kurz(ort, 30)}",
            art="einrichtung",
            ansprechpartner=wer,
            oeffnungszeiten=z.get("öffnungszeiten", ""),
            lieferschein="nein",  # hierhin wird geliefert, nicht abgeholt
        )
    if len(telefon) > 50:  # Text statt Nummer: nichts abschneiden, in die Notiz
        notiz.insert(0, f"Kontakt: {telefon}")
        telefon = ""
    daten.update(telefon=telefon, notiz="\n".join(notiz))
    return daten


def umschreiben(text: str) -> str:
    """Erkennt eine der beiden Listen an der Kopfzeile und liefert sie als ``stationen.csv``;
    jede andere Datei kommt unverändert zurück."""
    zeilen = text.splitlines()
    if not zeilen:
        return text
    trenner = ";" if zeilen[0].count(";") >= zeilen[0].count(",") else ","
    leser = csv.DictReader(io.StringIO(text, newline=""), delimiter=trenner)
    kopf = [(k or "").strip().lower().lstrip("﻿") for k in (leser.fieldnames or [])]
    if "kennung" in kopf or not {"name", "adresse"} <= set(kopf):
        return text
    leser.fieldnames = kopf
    markt = bool(MARKT_SPALTEN & set(kopf))
    puffer = io.StringIO()
    schreiber = csv.DictWriter(puffer, ZIEL, delimiter=";", lineterminator="\n",
                               extrasaction="ignore")  # fmt: skip
    schreiber.writeheader()
    for z in leser:
        z = {k: (v or "").strip(" \r\n") for k, v in z.items() if k}
        if any(z.values()):
            schreiber.writerow(_zeile(z, markt))
    return puffer.getvalue()
