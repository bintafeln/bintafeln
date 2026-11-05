"""Nachweise (Anhänge) im Stapel aus einem Altsystem in die Anträge übernehmen.

Ein ZIP enthält die Dateien und eine Liste ``nachweise.csv`` mit den Spalten
``antragsnummer;datei`` (optional ``name`` für den Anzeigenamen). Jede Datei wird über die
Antragsnummer (``Antrag.laufnummer``) dem passenden Antrag als verschlüsselter Nachweis angehängt
(``AntragAnhang``). Bilder verkleinert bintafeln nach den Foto-Einstellungen der Tafel (ADR 0064);
PDFs bleiben unverändert (Obergrenze ``MAX_MB`` je gespeicherter Datei).

bintafeln kennt nur dieses neutrale ZIP-Format. Das Werkzeug, das die Dateien aus einem bestimmten
Altsystem herunterlädt und dieses ZIP erzeugt, gehört nicht in dieses Repository (siehe CLAUDE.md).
"""

import csv
import io
import zipfile
from pathlib import Path

from apps.antraege.forms import ANHANG_TYPEN
from apps.antraege.models import ANHANG_ORDNER, Antrag, AntragAnhang
from apps.core import bilder, privatdateien
from apps.core.models import FotoEinstellungen

MANIFEST = "nachweise.csv"
MAX_MB = 20  # Obergrenze je gespeicherter Datei (vor allem PDFs; Bilder werden verkleinert)
ENDUNG_TYP = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".pdf": "application/pdf",
}  # fmt: skip
# Status je Zeile und ihre verständliche Bezeichnung für den Bericht
STATUS = {
    "ok": "wird zugeordnet",
    "antrag_fehlt": "kein Antrag mit dieser Nummer",
    "datei_fehlt": "Datei nicht im ZIP",
    "typ": "kein Foto (JPG, PNG) oder PDF",
    "zu_gross": f"größer als {MAX_MB} MB",
    "dublette": "schon vorhanden (übersprungen)",
    "leer": "Datei ist leer",
}


class ImportFehler(ValueError):
    pass


def _typ(dateiname: str) -> str | None:
    return ENDUNG_TYP.get(Path(dateiname).suffix.lower())


def _zeilen(archiv: zipfile.ZipFile):
    """Liest die Begleitliste; liefert (antragsnummer:str, datei:str, name:str) je Zeile."""
    try:
        roh = archiv.read(MANIFEST)
    except KeyError:
        raise ImportFehler(
            f"Im ZIP fehlt die Liste {MANIFEST} (Spalten: antragsnummer;datei)."
        ) from None
    text = roh.decode("utf-8-sig", errors="replace")
    leser = csv.DictReader(io.StringIO(text), delimiter=";")
    spalten = {(s or "").strip().lower() for s in (leser.fieldnames or [])}
    if not {"antragsnummer", "datei"} <= spalten:
        raise ImportFehler(f"{MANIFEST} braucht die Spalten antragsnummer und datei.")
    for zeile in leser:
        werte = {(k or "").strip().lower(): (v or "").strip() for k, v in zeile.items()}
        datei = werte.get("datei", "")
        yield werte.get("antragsnummer", ""), datei, werte.get("name") or Path(datei).name


def _aufbereiten(inhalt: bytes, typ: str, e: FotoEinstellungen) -> bytes:
    """Bilder nach den Foto-Einstellungen verkleinern; PDFs unverändert lassen."""
    if typ == "application/pdf":
        return inhalt
    return bilder.foto_verkleinern(inhalt, typ, e.kante, e.qualitaet, e.graustufen)


def verarbeiten(datei, *, schreiben: bool) -> dict:
    """Prüft (``schreiben=False``) oder übernimmt (``schreiben=True``) die Nachweise aus dem ZIP.

    Liefert einen Bericht mit Zählern je Status und – nur für die auffälligen Zeilen – einer
    begrenzten Liste. Dedup über (Antrag, Anzeigename): ein erneuter oder stapelweiser Lauf legt
    nichts doppelt an."""
    zaehler = dict.fromkeys(STATUS, 0)
    probleme = []
    e = FotoEinstellungen.laden()
    try:
        archiv = zipfile.ZipFile(datei)
    except zipfile.BadZipFile:
        raise ImportFehler("Die Datei ist kein lesbares ZIP-Archiv.") from None
    with archiv:
        namen = set(archiv.namelist())
        for nummer, pfad_im_zip, anzeige in _zeilen(archiv):
            status = _eine_zeile(archiv, namen, nummer, pfad_im_zip, anzeige, e, schreiben)
            zaehler[status] += 1
            if status != "ok" and len(probleme) < 300:
                probleme.append({"antragsnummer": nummer, "datei": pfad_im_zip,
                                 "status": status, "text": STATUS[status]})  # fmt: skip
    zaehler["gesamt"] = sum(zaehler[s] for s in STATUS)
    zusammenfassung = [(STATUS[s], zaehler[s]) for s in STATUS if zaehler[s]]
    return {"zaehler": zaehler, "zusammenfassung": zusammenfassung, "probleme": probleme,
            "geschrieben": schreiben}  # fmt: skip


def _eine_zeile(archiv, namen, nummer, pfad_im_zip, anzeige, e, schreiben) -> str:
    if not (nummer.isdigit() and pfad_im_zip):
        return "antrag_fehlt" if not nummer.isdigit() else "datei_fehlt"
    antrag = Antrag.objects.filter(laufnummer=int(nummer)).first()
    if antrag is None:
        return "antrag_fehlt"
    typ = _typ(pfad_im_zip)
    if typ not in ANHANG_TYPEN:
        return "typ"
    if pfad_im_zip not in namen:
        return "datei_fehlt"
    if AntragAnhang.objects.filter(antrag=antrag, name=anzeige[:200]).exists():
        return "dublette"
    inhalt = archiv.read(pfad_im_zip)
    if not inhalt:
        return "leer"
    fertig = _aufbereiten(inhalt, typ, e)
    if len(fertig) > MAX_MB * 1024 * 1024:
        return "zu_gross"
    if schreiben:
        name = privatdateien.ablegen(ANHANG_ORDNER, fertig)
        AntragAnhang.objects.create(antrag=antrag, name=anzeige[:200], datei=name, typ=typ,
                                    groesse=len(fertig))  # fmt: skip
    return "ok"


def pruefen(datei) -> dict:
    return verarbeiten(datei, schreiben=False)


def uebernehmen(datei) -> dict:
    return verarbeiten(datei, schreiben=True)
