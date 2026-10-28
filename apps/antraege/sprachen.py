"""Sprachen des öffentlichen Antragsformulars (ADR 0024).

Die Texte liegen je Sprache in uebersetzungen/<code>.json, Grundlage ist de.json. Fehlt in
einer Sprache ein Text, erscheint der deutsche. Was Antragstellende eingeben, verlässt den
Server nicht; nur die eigenen Texte der Tafel lassen sich auf Knopfdruck mit KI übersetzen
(ADR 0082).
"""

import json
from dataclasses import dataclass
from functools import cache
from pathlib import Path

ORDNER = Path(__file__).resolve().parent / "uebersetzungen"


@dataclass(frozen=True)
class Sprache:
    code: str
    name: str  # in der eigenen Sprache, für die Auswahl
    deutsch: str  # für die Mitarbeitenden
    rtl: bool = False  # Schrift von rechts nach links


SPRACHEN = [
    Sprache("de", "Deutsch", "Deutsch"),
    Sprache("en", "English", "Englisch"),
    Sprache("ar", "العربية", "Arabisch", rtl=True),
    Sprache("tr", "Türkçe", "Türkisch"),
    Sprache("uk", "Українська", "Ukrainisch"),
    Sprache("ru", "Русский", "Russisch"),
    Sprache("pl", "Polski", "Polnisch"),
    Sprache("ro", "Română", "Rumänisch"),
    Sprache("bg", "Български", "Bulgarisch"),
    Sprache("fa", "فارسی", "Persisch (Farsi)", rtl=True),
    Sprache("prs", "دری", "Dari", rtl=True),
    Sprache("ps", "پښتو", "Paschtu", rtl=True),
    Sprache("kmr", "Kurmancî", "Kurdisch (Kurmandschi)"),
    Sprache("ckb", "کوردی", "Kurdisch (Sorani)", rtl=True),
    Sprache("ti", "ትግርኛ", "Tigrinya"),
    Sprache("so", "Soomaali", "Somali"),
    Sprache("fr", "Français", "Französisch"),
    Sprache("es", "Español", "Spanisch"),
    Sprache("it", "Italiano", "Italienisch"),
    Sprache("pt", "Português", "Portugiesisch"),
    Sprache("sq", "Shqip", "Albanisch"),
    Sprache("sr", "Srpski", "Serbisch"),
    Sprache("hr", "Hrvatski", "Kroatisch"),
    Sprache("bs", "Bosanski", "Bosnisch"),
    Sprache("el", "Ελληνικά", "Griechisch"),
    Sprache("hu", "Magyar", "Ungarisch"),
    Sprache("vi", "Tiếng Việt", "Vietnamesisch"),
    Sprache("zh", "中文", "Chinesisch"),
    Sprache("ur", "اردو", "Urdu", rtl=True),
]
NACH_CODE = {s.code: s for s in SPRACHEN}
# Codes, die Browser für dieselben Sprachen senden.
ALIASSE = {"ku": "kmr", "fa-af": "prs", "zh-cn": "zh", "zh-hans": "zh"}
AUSWAHL = [(s.code, s.deutsch) for s in SPRACHEN]


def sprache(code: str) -> Sprache:
    return NACH_CODE.get(code, NACH_CODE["de"])


@cache
def _datei(code: str) -> dict:
    pfad = ORDNER / f"{code}.json"
    return json.loads(pfad.read_text(encoding="utf-8")) if pfad.exists() else {}


@cache
def texte(code: str) -> dict[str, str]:
    """Alle Texte einer Sprache; fehlende aus der deutschen Grundlage."""
    return {**_datei("de"), **_datei(sprache(code).code)}


def aus_browser(kopfzeile: str) -> str:
    """Erste unterstützte Sprache aus Accept-Language, sonst Deutsch."""
    for teil in kopfzeile.split(","):
        code = teil.split(";")[0].strip().lower()
        for kandidat in (code, code.split("-")[0]):
            kandidat = ALIASSE.get(kandidat, kandidat)
            if kandidat in NACH_CODE:
                return kandidat
    return "de"
