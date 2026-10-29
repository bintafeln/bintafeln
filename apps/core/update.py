"""Update aus der Oberfläche (ADR 0043): Stand des Dienstes "updater" lesen, Aufträge ablegen.

bintafeln steuert Docker nicht selbst. Es tauscht mit dem Dienst nur Dateien im Ordner
``settings.BETRIEB_ORDNER`` aus (Format Schlüssel=Wert, siehe docker/updater/updater.sh).
"""

import os
import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

VERSIONSMUSTER = re.compile(r"^\d{4}\.\d{1,2}\.\d+$")
DIENST_STILL = timedelta(minutes=1)  # Der Dienst meldet sich alle 5 Sekunden
PROTOKOLL_ZEILEN = 300


class UpdateFehler(ValueError):
    pass


# Stufen einer Version (ADR 0084), gesetzt über das Label am Pull Request (version.yml)
STUFEN = {"sicherheit": "Sicherheitsupdate", "wichtig": "Wichtige Korrektur",
          "neu": "Neue Funktionen", "klein": ""}  # fmt: skip
WICHTIG_NACH = timedelta(days=7)
NEU_NACH = timedelta(days=30)
ABRUF_FEHLT_NACH = timedelta(days=14)


def _schluessel(name: str) -> tuple[int, ...]:
    return tuple(int(t) for t in name.split("."))


@dataclass(frozen=True)
class Version:
    name: str
    datum: str
    aenderungen: list[str]
    stufe: str = "klein"

    @property
    def stufe_text(self) -> str:
        return STUFEN.get(self.stufe, "")

    @property
    def tag(self) -> date | None:
        try:
            return date.fromisoformat(self.datum)
        except ValueError:
            return None

    @property
    def schluessel(self) -> tuple[int, ...]:
        return _schluessel(self.name)


@dataclass(frozen=True)
class Sicherheitshinweis:
    """Aus docs/sicherheitshinweise.txt auf main: Versionen vor ``version`` sind betroffen."""

    version: str
    text: str


@dataclass(frozen=True)
class Warnung:
    """Warnung auf der Startseite: art = sicherheit, wichtig, abruf oder neu."""

    art: str
    tage: int  # so lange gibt es das Update schon (bei „abruf“: so lange nichts abgerufen)
    version: str = ""  # neueste verfügbare Version
    hinweise: tuple[Sicherheitshinweis, ...] = ()


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
    vorher: str = ""  # beim letzten Auftrag installierte Version (für „Was ist neu?“)
    ziel: str = ""  # Version des letzten Auftrags
    erfolgreich: datetime | None = None  # letzter gelungener Abruf
    sicherheitshinweise: list[Sicherheitshinweis] = field(default_factory=list)

    @property
    def beschaeftigt(self) -> bool:
        return self.zustand == "laeuft" or bool(self.angefordert)

    @property
    def neueste(self) -> Version | None:
        return self.versionen[0] if self.versionen else None

    def neu_seit_auftrag(self) -> list[Version]:
        """Versionen des letzten Updates (nach „vorher“ bis einschließlich Ziel). Während und nach
        dem Update gilt das Ziel schon als installiert; „Was ist neu?“ bleibt so stehen."""
        if not self.ziel or self.ziel not in {v.name for v in self.versionen}:
            return []
        ziel = next(v for v in self.versionen if v.name == self.ziel)
        if not VERSIONSMUSTER.match(self.vorher):
            return [ziel]
        von = tuple(int(t) for t in self.vorher.split("."))
        return [v for v in self.versionen if von < v.schluessel <= ziel.schluessel]

    def ist_neuer(self, version: Version) -> bool:
        if not VERSIONSMUSTER.match(self.installiert):
            return True
        return version.schluessel > _schluessel(self.installiert)

    def offene_hinweise(self) -> list[Sicherheitshinweis]:
        """Sicherheitshinweise, die die installierte Version betreffen."""
        if not VERSIONSMUSTER.match(self.installiert):
            return []
        return [h for h in self.sicherheitshinweise
                if _schluessel(h.version) > _schluessel(self.installiert)]  # fmt: skip


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
    zeilen = _lesen("versionen.txt")
    stufen = {}
    for schluessel, wert in zeilen:
        name, _, rest = wert.partition("|")
        if schluessel == "stufe" and rest.strip() in STUFEN:
            stufen[name] = rest.strip()
        elif schluessel == "sicherheit" and VERSIONSMUSTER.match(name) and rest.strip():
            s.sicherheitshinweise.append(Sicherheitshinweis(name, rest.strip()))
    for schluessel, wert in zeilen:
        if schluessel == "version":
            name, _, rest = wert.partition("|")
            datum, _, titel = rest.partition("|")
            if VERSIONSMUSTER.match(name):
                aenderungen = [t.strip() for t in titel.split("\t") if t.strip()]
                s.versionen.append(Version(name, datum, aenderungen, stufen.get(name, "klein")))
        elif schluessel == "erfolgreich":
            s.erfolgreich = _zeit(wert)
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
    vorher = dict(_lesen("vorher.txt"))
    s.vorher, s.ziel = vorher.get("von", "").strip(), vorher.get("ziel", "").strip()
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
    _schreiben("vorher.txt", f"von={s.installiert}\nziel={version}\n")
    _schreiben("auftrag.txt", f"version={version}\nvon={von}\n")


def jetzt_abrufen() -> None:
    _schreiben("abrufen.txt", "jetzt\n")


def warnung(s: Stand, jetzt: datetime | None = None) -> Warnung | None:
    """Warnung für die Startseite, nur bei wirklich wichtigen Updates (ADR 0084):
    Sicherheit sofort, wichtige Korrekturen nach 7 Tagen, neue Funktionen nach 30 Tagen; dazu,
    wenn seit 14 Tagen keine Versionen mehr abgerufen werden konnten. Kleine Updates nie."""
    if not VERSIONSMUSTER.match(s.installiert):
        return None  # Entwicklung oder ohne Dienst „updater“
    jetzt = jetzt or timezone.now()
    heute = timezone.localdate(jetzt)
    neuere = [v for v in s.versionen if s.ist_neuer(v)]  # neueste zuerst
    neueste = neuere[0].name if neuere else ""

    def tage(versionen) -> int:
        tage_ = [(heute - v.tag).days for v in versionen if v.tag]
        return max(tage_, default=0)

    hinweise = tuple(s.offene_hinweise())
    sicher = [v for v in neuere if v.stufe == "sicherheit"]
    if sicher or hinweise:
        behoben = [v for v in neuere if v.name in {h.version for h in hinweise}]
        return Warnung("sicherheit", tage(sicher + behoben), neueste, hinweise)
    wichtig = [v for v in neuere if v.stufe == "wichtig"]
    if wichtig and tage(wichtig) >= WICHTIG_NACH.days:
        return Warnung("wichtig", tage(wichtig), neueste)
    if s.erfolgreich and jetzt - s.erfolgreich >= ABRUF_FEHLT_NACH:
        return Warnung("abruf", (jetzt - s.erfolgreich).days)
    neu = [v for v in neuere if v.stufe == "neu"]
    if neu and tage(neu) >= NEU_NACH.days:
        return Warnung("neu", tage(neu), neueste)
    return None


def _empfaenger() -> list[str]:
    from django.contrib.auth import get_user_model

    from apps.konten import rollen

    benutzer = get_user_model().objects.filter(is_active=True).exclude(email="")
    return sorted(b.email for b in benutzer if rollen.hat_recht(b, "system.update"))


def sicherheit_melden(w: Warnung | None) -> None:
    """Einmal je Sicherheitsupdate eine Mail an alle mit dem Recht „Programm aktualisieren“."""

    from apps.core.models import TafelEinstellungen

    if not w or w.art != "sicherheit":
        return
    kennung = w.version or ",".join(h.version for h in w.hinweise)
    e = TafelEinstellungen.laden()
    if e.update_gemeldet == kennung:
        return
    e.update_gemeldet = kennung
    e.save(update_fields=["update_gemeldet"])
    an = _empfaenger()
    if not an:
        return
    zeilen = [
        f"Für bintafeln{f' ({e.name})' if e.name else ''} ist ein Sicherheitsupdate verfügbar"
        f"{f': Version {w.version}' if w.version else ''}.",
        "",
        *(f"- {h.text} (behoben ab {h.version})" for h in w.hinweise),
        *([""] if w.hinweise else []),
        "Bitte bald aktualisieren: in bintafeln unter Einstellungen → Update oder auf dem Server "
        "mit ./betrieb update.",
    ]
    from apps.core import benachrichtigung

    benachrichtigung.melden("sicherheitsupdate", an, "bintafeln: Sicherheitsupdate verfügbar",
                            "\n".join(zeilen))  # fmt: skip
