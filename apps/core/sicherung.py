"""Liest den Status der Sicherung, den der Dienst "backup" schreibt."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

from django.conf import settings
from django.utils import timezone

# Bis 5 Tage grün, bis 10 Tage gelb (älter), darüber rot (veraltet)
GELB_AB = timedelta(days=5)
MAX_ALTER = timedelta(days=10)

OK = "ok"
ALT = "alt"
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
    elif jetzt - erfolgreich > GELB_AB:
        zustand = ALT
    else:
        zustand = OK
    return SicherungsStatus(zustand, erfolgreich, meldung)


# --- Sicherungsaufträge und Dienst (ADR 0042) ---------------------------------------------------

DIENST_STILL = timedelta(minutes=2)  # Der Dienst meldet sich alle 15 Sekunden


@dataclass(frozen=True)
class DienstStatus:
    erreichbar: bool
    letzter_kontakt: datetime | None
    schluessel_ok: bool


def dienst_status(jetzt: datetime | None = None) -> DienstStatus:
    from apps.core.models import SicherungsDienst

    dienst = SicherungsDienst.objects.filter(pk=SicherungsDienst.EINZIGE_ID).first()
    if dienst is None or dienst.letzter_kontakt is None:
        return DienstStatus(False, None, False)
    jetzt = jetzt or timezone.now()
    return DienstStatus(
        jetzt - dienst.letzter_kontakt <= DIENST_STILL, dienst.letzter_kontakt, dienst.schluessel_ok
    )


def auftraege_mit_fehler():
    """Weitere Aufträge, deren letzter Lauf fehlgeschlagen ist (für die Startseite); den
    Standard-Auftrag zeigt dort schon der Sicherungsstand aus status.txt."""
    from apps.core.models import SicherungsAuftrag

    return list(SicherungsAuftrag.objects.filter(ergebnis=FEHLER, standard=False))


def anfordern(auftrag, von: str) -> None:
    """Sofort-Sicherung: Der Dienst führt den Auftrag innerhalb von etwa 15 Sekunden aus."""
    auftrag.angefordert_am = timezone.now()
    auftrag.angefordert_von = von
    auftrag.save(update_fields=["angefordert_am", "angefordert_von"])
