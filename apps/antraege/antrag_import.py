"""Anträge im Stapel aus einem Altsystem übernehmen: eine ``antraege.csv`` einlesen und daraus
Anträge anlegen (mit weiteren Haushaltspersonen und optionaler Anmerkung).

Das Format entspricht dem **Export** der Antragsliste (gleiche Spalten, Trennzeichen ``;``,
``utf-8``): Pflicht sind ``vorname`` und ``nachname``; alles andere ist optional. Weitere Personen
im Haushalt stehen in der Spalte ``personen`` (durch `` | `` getrennt, je Person „Vorname Nachname
JJJJ-MM-TT (Staat)``; Datum und Staat optional). Ist eine ``nummer`` (Antragsnummer) angegeben und
schon vorhanden, wird die Zeile übersprungen (kein Doppelimport); fehlt sie, vergibt bintafeln die
nächste Nummer. Die Nachweise werden getrennt über den Nachweis-Import (ZIP + ``nachweise.csv``,
Zuordnung über die Antragsnummer) übernommen.

bintafeln kennt nur dieses neutrale Format. Das Werkzeug, das die Daten aus einem bestimmten
Altsystem herunterlädt und diese Datei erzeugt, gehört nicht in dieses Repository (siehe CLAUDE.md).
"""

import csv
import datetime as dt
import io

from django.utils import timezone

from apps.antraege import sprachen
from apps.antraege.models import Antrag, AntragAnmerkung, AntragPerson

STATUS = {
    "ok": "wird angelegt",
    "dublette": "Antragsnummer schon vorhanden (übersprungen)",
    "unvollstaendig": "Vorname oder Nachname fehlt",
    "fehler": "konnte nicht gelesen werden",
}
_SPRACHEN = {c for c, _ in sprachen.AUSWAHL}


class ImportFehler(ValueError):
    pass


def _datum(text: str) -> dt.date | None:
    text = (text or "").strip()
    for form in ("%Y-%m-%d", "%d.%m.%Y"):
        try:
            return dt.datetime.strptime(text, form).date()
        except ValueError:
            continue
    return None


def _datum_zeit(text: str):
    text = (text or "").strip()
    for form in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%d.%m.%Y %H:%M"):
        try:
            return timezone.make_aware(dt.datetime.strptime(text, form))
        except (ValueError, OverflowError):
            continue
    tag = _datum(text)
    return timezone.make_aware(dt.datetime.combine(tag, dt.time())) if tag else None


def _wahl(text: str, choices, vorgabe: str) -> str:
    text = (text or "").strip().lower()
    return text if text in choices.values else vorgabe


def _personen(text: str) -> list[dict]:
    """Die Spalte ``personen`` zerlegen: `` | `` trennt Personen, je Person „Name … JJJJ-MM-TT
    (Staat)``. Datum und Staat sind optional; der Rest ist der Name."""
    leute = []
    for eintrag in (text or "").split(" | "):
        eintrag = eintrag.strip()
        if not eintrag:
            continue
        staat = ""
        if eintrag.endswith(")") and "(" in eintrag:
            eintrag, _, rest = eintrag.rpartition("(")
            staat = rest.rstrip(")").strip()
            eintrag = eintrag.strip()
        geburt = None
        teile = eintrag.split()
        if teile and _datum(teile[-1]):
            geburt = _datum(teile[-1])
            teile = teile[:-1]
        vorname = teile[0] if teile else ""
        nachname = " ".join(teile[1:])
        if vorname or nachname:
            leute.append({"vorname": vorname[:100], "nachname": nachname[:100],
                          "geburtsdatum": geburt, "staatsangehoerigkeit": staat[:100]})  # fmt: skip
    return leute


def _anlegen(w: dict) -> None:
    a = Antrag(
        anrede=w.get("anrede", "")[:30],
        vorname=w["vorname"][:100],
        nachname=w["nachname"][:100],
        geburtsdatum=_datum(w.get("geburtsdatum")),
        kundennummer=w.get("kundennummer", "")[:20],
        strasse=w.get("strasse", "")[:200],
        plz=w.get("plz", "")[:10],
        ort=w.get("ort", "")[:100],
        telefon=w.get("telefon", "")[:50],
        email=w.get("email", "")[:254],
        familienstand=w.get("familienstand", "")[:50],
        staatsangehoerigkeit=w.get("staatsangehoerigkeit", "")[:100],
        wochentage=w.get("wochentage", "")[:30],
        ausgabestelle=w.get("ausgabestelle", "")[:100],
        nachricht=w.get("nachricht", ""),
        sprache=w.get("sprache", "").strip() if w.get("sprache", "").strip() in _SPRACHEN else "de",
        art=_wahl(w.get("art"), Antrag.Art, Antrag.Art.NEU),
        status=_wahl(w.get("status"), Antrag.Status, Antrag.Status.NEU),
    )
    nummer = (w.get("nummer") or w.get("laufnummer") or "").strip()
    if nummer.isdigit():
        a.laufnummer = int(nummer)
    eingegangen = _datum_zeit(w.get("eingegangen_am"))
    if eingegangen:
        a.eingegangen_am = eingegangen
    a.save()
    for teil in _personen(w.get("personen", "")):
        AntragPerson.objects.create(antrag=a, **teil)
    anmerkung = w.get("anmerkung", "").strip()
    if anmerkung:
        AntragAnmerkung.objects.create(antrag=a, text=anmerkung, von="Import")


def verarbeiten(datei, *, schreiben: bool) -> dict:
    """Prüft (``schreiben=False``) oder übernimmt (``schreiben=True``) die Anträge aus der CSV.

    Liefert einen Bericht mit Zählern je Status und – nur für auffällige Zeilen – einer begrenzten
    Liste ohne Namen. Doppelte Antragsnummern (schon vorhanden oder zweimal in der Datei) werden
    übersprungen, nichts doppelt angelegt."""
    datei.seek(0)
    text = datei.read().decode("utf-8-sig", errors="replace")
    leser = csv.DictReader(io.StringIO(text), delimiter=";")
    spalten = {(s or "").strip().lower() for s in (leser.fieldnames or [])}
    if not {"vorname", "nachname"} <= spalten:
        raise ImportFehler("Die Datei braucht mindestens die Spalten vorname und nachname.")

    zaehler = dict.fromkeys(STATUS, 0)
    probleme = []
    gesehen: set[int] = set()  # Antragsnummern innerhalb dieser Datei
    for nr, zeile in enumerate(leser, start=2):  # Zeile 1 ist die Kopfzeile
        w = {(k or "").strip().lower(): (v or "").strip() for k, v in zeile.items()}
        status = _eine_zeile(w, gesehen, schreiben)
        zaehler[status] += 1
        if status != "ok" and len(probleme) < 300:
            nummer = (w.get("nummer") or w.get("laufnummer") or "").strip()
            probleme.append({"zeile": nr, "nummer": nummer, "status": status,
                             "text": STATUS[status]})  # fmt: skip
    zaehler["gesamt"] = sum(zaehler[s] for s in STATUS)
    zusammenfassung = [(STATUS[s], zaehler[s]) for s in STATUS if zaehler[s]]
    return {"zaehler": zaehler, "zusammenfassung": zusammenfassung, "probleme": probleme,
            "geschrieben": schreiben}  # fmt: skip


def _eine_zeile(w: dict, gesehen: set, schreiben: bool) -> str:
    if not (w.get("vorname") and w.get("nachname")):
        return "unvollstaendig"
    nummer = (w.get("nummer") or w.get("laufnummer") or "").strip()
    if nummer.isdigit():
        n = int(nummer)
        if n in gesehen or Antrag.objects.filter(laufnummer=n).exists():
            return "dublette"
        gesehen.add(n)
    try:
        if schreiben:
            _anlegen(w)
    except Exception:  # noqa: BLE001 – eine fehlerhafte Zeile darf die anderen nicht stoppen
        return "fehler"
    return "ok"


def pruefen(datei) -> dict:
    return verarbeiten(datei, schreiben=False)


def uebernehmen(datei) -> dict:
    return verarbeiten(datei, schreiben=True)
