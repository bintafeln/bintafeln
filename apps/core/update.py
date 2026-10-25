"""Update aus der Oberfläche (ADR 0043): Stand des Dienstes "updater" lesen, Aufträge ablegen.

bintafeln steuert Docker nicht selbst. Es tauscht mit dem Dienst nur Dateien im Ordner
``settings.BETRIEB_ORDNER`` aus (Format Schlüssel=Wert, siehe docker/updater/updater.sh).
"""

import os
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

VERSIONSMUSTER = re.compile(r"^\d{4}\.\d{1,2}\.\d+$")
DIENST_STILL = timedelta(minutes=1)  # Der Dienst meldet sich alle 5 Sekunden
PROTOKOLL_ZEILEN = 300


class UpdateFehler(ValueError):
    pass


@dataclass(frozen=True)
class Version:
    name: str
    datum: str
    aenderungen: list[str]

    @property
    def schluessel(self) -> tuple[int, ...]:
        return tuple(int(t) for t in self.name.split("."))


@dataclass
class Stand:
    erreichbar: bool = False
    installiert: str = ""
    abgerufen: datetime | None = None
    abruf_fehler: str = ""
    versionen: list[Version] = field(default_factory=list)  # neueste zuerst
    zustand: str = ""  # laeuft, ok, fehler oder leer
    version: str = ""
    beginn: datetime | None = None
    ende: datetime | None = None
    meldung: str = ""
    protokoll: str = ""
    angefordert: str = ""
    sucht: bool = False  # Suche angefordert, vom Dienst noch nicht erledigt

    @property
    def beschaeftigt(self) -> bool:
        return self.zustand == "laeuft" or bool(self.angefordert)

    @property
    def neueste(self) -> Version | None:
        return self.versionen[0] if self.versionen else None

    def ist_neuer(self, version: Version) -> bool:
        if not VERSIONSMUSTER.match(self.installiert):
            return True
        return version.schluessel > tuple(int(t) for t in self.installiert.split("."))


def _ordner() -> Path:
    return Path(settings.BETRIEB_ORDNER)


def _lesen(name: str) -> list[tuple[str, str]]:
    try:
        text = (_ordner() / name).read_text(encoding="utf-8")
    except OSError:
        return []
    return [tuple(z.split("=", 1)) for z in text.splitlines() if "=" in z]


def _zeit(text: str) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def stand(jetzt: datetime | None = None) -> Stand:
    jetzt = jetzt or timezone.now()
    s = Stand()
    lebenszeichen = _zeit(dict(_lesen("lebenszeichen.txt")).get("zeit", ""))
    s.erreichbar = lebenszeichen is not None and jetzt - lebenszeichen <= DIENST_STILL
    for schluessel, wert in _lesen("versionen.txt"):
        if schluessel == "version":
            name, _, rest = wert.partition("|")
            datum, _, titel = rest.partition("|")
            if VERSIONSMUSTER.match(name):
                aenderungen = [t.strip() for t in titel.split("\t") if t.strip()]
                s.versionen.append(Version(name, datum, aenderungen))
        elif schluessel == "installiert":
            s.installiert = wert.strip()
        elif schluessel == "abgerufen":
            s.abgerufen = _zeit(wert)
        elif schluessel == "fehler":
            s.abruf_fehler = wert.strip()
    s.versionen.sort(key=lambda v: v.schluessel, reverse=True)
    status = dict(_lesen("status.txt"))
    s.zustand, s.version = status.get("zustand", ""), status.get("version", "")
    s.beginn, s.ende = _zeit(status.get("beginn", "")), _zeit(status.get("ende", ""))
    s.meldung = status.get("meldung", "")
    try:
        zeilen = (_ordner() / "protokoll.txt").read_text(encoding="utf-8", errors="replace")
        s.protokoll = "\n".join(zeilen.splitlines()[-PROTOKOLL_ZEILEN:])
    except OSError:
        pass
    s.angefordert = dict(_lesen("auftrag.txt")).get("version", "")
    s.sucht = (_ordner() / "abrufen.txt").exists()
    return s


def _schreiben(name: str, text: str) -> None:
    ordner = _ordner()
    ordner.mkdir(parents=True, exist_ok=True)
    tmp = ordner / f".{name}.{os.getpid()}.tmp"
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(ordner / name)


def anfordern(version: str, von: str) -> None:
    """Auftrag für den Dienst; er prüft die Version noch einmal selbst."""
    s = stand()
    if not s.erreichbar:
        raise UpdateFehler("Der Update-Dienst läuft nicht. Siehe Hinweis oben auf der Seite.")
    if s.beschaeftigt:
        raise UpdateFehler("Es läuft schon ein Update.")
    if version not in {v.name for v in s.versionen}:
        raise UpdateFehler(f"Die Version {version} ist nicht verfügbar.")
    von = re.sub(r"[\r\n=]", " ", von)
    _schreiben("auftrag.txt", f"version={version}\nvon={von}\n")


def jetzt_abrufen() -> None:
    _schreiben("abrufen.txt", "jetzt\n")
