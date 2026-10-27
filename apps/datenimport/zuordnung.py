"""Spalten einer Tabelle den Feldern eines Ziels zuordnen (ADR 0078).

``vorschlagen()`` rät die Zuordnung aus den Spaltenüberschriften: zuerst eine gespeicherte
Vorlage, dann genaue Treffer (Schlüssel, Bezeichnung, Synonyme), dann ähnliche Schreibweisen.
Mehrere Spalten dürfen auf dasselbe Feld zeigen (z. B. Straße und Hausnummer); ihre Werte werden
mit Leerzeichen verbunden. Zwei Hilfsfelder teilen zusammengesetzte Spalten auf: „Name (Vor- und
Nachname)“ und „PLZ und Ort“.
"""

import difflib
import re
from dataclasses import dataclass, field

IGNORIEREN = ""
NAME_VOLL = "_name_voll"
PLZ_ORT = "_plz_ort"


@dataclass(frozen=True)
class Feld:
    schluessel: str
    bezeichnung: str
    synonyme: tuple[str, ...] = ()
    pflicht: bool = False
    mehrfach: bool = False  # mehrere Spalten werden verbunden (Straße + Hausnummer)
    typ: str = "text"  # text, datum, janein, email, liste
    laenge: int = 0


@dataclass
class Art:
    """Eine Art von Tabelle innerhalb eines Ziels, z. B. „Haushalte“ beim Kundenstamm."""

    schluessel: str
    titel: str
    felder: list[Feld] = field(default_factory=list)

    def feld(self, schluessel) -> Feld | None:
        return next((f for f in self.felder if f.schluessel == schluessel), None)

    @property
    def hilfsfelder(self) -> list[Feld]:
        namen = {f.schluessel for f in self.felder}
        hilfe = []
        if {"vorname", "nachname"} <= namen:
            hilfe.append(
                Feld(
                    NAME_VOLL,
                    "Name (Vor- und Nachname in einer Spalte)",
                    ("name", "vollername", "namevorname", "nachnamevorname"),
                )
            )
        if {"plz", "ort"} <= namen:
            hilfe.append(Feld(PLZ_ORT, "PLZ und Ort in einer Spalte", ("plzort", "wohnort")))
        return hilfe

    @property
    def alle_felder(self) -> list[Feld]:
        return self.felder + self.hilfsfelder


_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})


def normalisieren(text: str) -> str:
    """„Geb.-Datum“ → „gebdatum“, „Straße“ → „strasse“."""
    return re.sub(r"[^a-z0-9]", "", (text or "").lower().translate(_UMLAUTE))


def _namen(f: Feld) -> list[str]:
    return [normalisieren(n) for n in (f.schluessel, f.bezeichnung, *f.synonyme) if n]


def vorschlagen(kopf: list[str], art: Art, vorlage: dict | None = None) -> list[str]:
    """Je Spalte der Schlüssel des vermuteten Feldes oder ``IGNORIEREN``."""
    felder = art.alle_felder
    gueltig = {f.schluessel for f in felder}
    ergebnis = [IGNORIEREN] * len(kopf)
    vergeben: set[str] = set()
    mehrfach = {f.schluessel for f in felder if f.mehrfach}
    normal = [normalisieren(k) for k in kopf]

    def setzen(i, schluessel):
        ergebnis[i] = schluessel
        vergeben.add(schluessel)

    def frei(schluessel):
        return schluessel in mehrfach or schluessel not in vergeben

    for i, n in enumerate(normal):  # 1. gespeicherte Vorlage
        ziel = (vorlage or {}).get(n)
        if n and ziel in gueltig:
            setzen(i, ziel)
    for i, n in enumerate(normal):  # 2. genaue Treffer
        if ergebnis[i] or not n:
            continue
        for f in felder:
            if n in _namen(f) and frei(f.schluessel):
                setzen(i, f.schluessel)
                break
    for i, n in enumerate(normal):  # 3. ähnliche Schreibweise oder enthalten
        if ergebnis[i] or len(n) < 3:
            continue
        beste, wert = None, 0.0
        for f in felder:
            if not frei(f.schluessel):
                continue
            for name in _namen(f):
                if len(name) >= 5 and (name in n or n in name):
                    aehnlich = 0.86
                else:
                    aehnlich = difflib.SequenceMatcher(None, n, name).ratio()
                if aehnlich > wert:
                    beste, wert = f.schluessel, aehnlich
        if beste and wert >= 0.85:
            setzen(i, beste)
    # Nur eine Spalte „Name“ und kein Vorname: wahrscheinlich Vor- und Nachname zusammen
    if "vorname" not in vergeben and any(f.schluessel == NAME_VOLL for f in felder):
        for i, n in enumerate(normal):
            if ergebnis[i] == "nachname" and n == "name":
                ergebnis[i] = NAME_VOLL
    return ergebnis


def name_teilen(text: str) -> tuple[str, str]:
    """„Muster, Anna“ → (Anna, Muster); „Anna Maria Muster“ → (Anna Maria, Muster)."""
    text = " ".join(text.split())
    if "," in text:
        nach, vor = (t.strip() for t in text.split(",", 1))
        return vor, nach
    teile = text.rsplit(" ", 1)
    return (teile[0], teile[1]) if len(teile) == 2 else ("", text)


def plz_ort_teilen(text: str) -> tuple[str, str]:
    treffer = re.match(r"\s*(?:D-)?(\d{4,5})\s+(.+)", text or "")
    return (treffer.group(1), treffer.group(2).strip()) if treffer else ("", (text or "").strip())


def umsetzen(werte: list[str], zuordnung: list[str]) -> dict[str, str]:
    """Eine Zeile nach der Zuordnung als {Feld: Text}; leere Zellen ergeben ""."""
    ergebnis: dict[str, str] = {}
    for i, schluessel in enumerate(zuordnung):
        if not schluessel or i >= len(werte):
            continue
        wert = (werte[i] or "").strip()
        if schluessel == NAME_VOLL:
            vor, nach = name_teilen(wert)
            ergebnis["vorname"] = ergebnis.get("vorname") or vor
            ergebnis["nachname"] = ergebnis.get("nachname") or nach
        elif schluessel == PLZ_ORT:
            plz, ort = plz_ort_teilen(wert)
            ergebnis["plz"] = ergebnis.get("plz") or plz
            ergebnis["ort"] = ergebnis.get("ort") or ort
        elif ergebnis.get(schluessel) and wert:
            ergebnis[schluessel] = f"{ergebnis[schluessel]} {wert}"
        else:
            ergebnis[schluessel] = ergebnis.get(schluessel) or wert
    return ergebnis


def fehlende_pflicht(art: Art, zuordnung: list[str]) -> list[Feld]:
    gewaehlt = set(zuordnung)
    if NAME_VOLL in gewaehlt:
        gewaehlt |= {"vorname", "nachname"}
    if PLZ_ORT in gewaehlt:
        gewaehlt |= {"plz", "ort"}
    return [f for f in art.felder if f.pflicht and f.schluessel not in gewaehlt]
