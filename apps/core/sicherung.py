"""Liest den Status der Sicherung, den der Dienst "backup" schreibt."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

MAX_ALTER = timedelta(hours=48)

OK = "ok"
VERALTET = "veraltet"
FEHLER = "fehler"
NICHT_EINGERICHTET = "nicht_eingerichtet"
UNBEKANNT = "unbekannt"


@dataclass(frozen=True)
class SicherungsStatus:
    zustand: str
    letzte_erfolgreiche: datetime | None = None
    meldung: str = ""

    @property
    def in_ordnung(self) -> bool:
        return self.zustand == OK


def _zeitpunkt(text: str) -> datetime | None:
    try:
        return datetime.strptime(text.strip(), "%Y-%m-%dT%H:%M:%S%z")
    except ValueError:
        return None


def lese_status(pfad: Path | None = None, jetzt: datetime | None = None) -> SicherungsStatus:
    pfad = Path(pfad or settings.SICHERUNG_STATUSDATEI)
    jetzt = jetzt or timezone.now()
    try:
        text = pfad.read_text(encoding="utf-8")
    except OSError:
        return SicherungsStatus(UNBEKANNT)

    werte = dict(zeile.split("=", 1) for zeile in text.splitlines() if "=" in zeile)
    erfolgreich = _zeitpunkt(werte.get("letzte_erfolgreiche", ""))
    meldung = werte.get("meldung", "")
    ergebnis = werte.get("ergebnis", "")

    if ergebnis == NICHT_EINGERICHTET:
        zustand = NICHT_EINGERICHTET
    elif ergebnis == FEHLER:
        zustand = FEHLER
    elif erfolgreich is None:
        zustand = UNBEKANNT
    elif jetzt - erfolgreich > MAX_ALTER:
        zustand = VERALTET
    else:
        zustand = OK
    return SicherungsStatus(zustand, erfolgreich, meldung)
