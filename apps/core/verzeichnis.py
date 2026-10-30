"""Freiwillige Meldung im bintafeln-Verzeichnis (ADR 0089).

Eine Tafel kann sich in den Einstellungen melden. Dann schickt bintafeln Name der Tafel,
Kontakt-Mail und Version an ``settings.VERZEICHNIS_URL``: beim Einschalten, nach jedem Update und
einmal pro Woche (``manage.py verzeichnis_melden`` im Takt der Benachrichtigungen). Beim
Ausschalten wird der Eintrag dort gelöscht. Nie gehen Kunden- oder Personendaten mit.

Die Installation des Herausgebers nimmt Meldungen an (``BINTAFELN_VERZEICHNIS_EMPFANG``) und
zeigt sie als Liste (``annehmen()``).
"""

import datetime as dt
import json
import logging
import uuid
from urllib.error import URLError
from urllib.request import Request, urlopen

from django.conf import settings
from django.utils import timezone

from apps.core.models import TafelEinstellungen, VerzeichnisEintrag, VerzeichnisMeldung
from bintafeln import programm
from bintafeln.version import version

logger = logging.getLogger(__name__)

ABSTAND = dt.timedelta(days=7)
ZEITLIMIT = 10
HOECHSTENS = 5000  # Einträge im Verzeichnis, gegen Fluten mit erfundenen Meldungen


class VerzeichnisFehler(Exception):
    """Verständliche Meldung für die Oberfläche."""


def angaben(meldung: VerzeichnisMeldung | None = None) -> dict:
    """Was gemeldet wird – genau das zeigt auch die Einstellungsseite."""
    meldung = meldung or VerzeichnisMeldung.laden()
    tafel = TafelEinstellungen.laden()
    return {
        "kennung": str(meldung.kennung),
        "name": tafel.name or "Tafel ohne Namen",
        "kontakt": meldung.kontakt or tafel.email,
        "version": version(),
    }


def _senden(daten: dict) -> None:
    anfrage = Request(  # noqa: S310 – Adresse aus der Konfiguration, nur https/http
        settings.VERZEICHNIS_URL,
        data=json.dumps(daten).encode(),
        headers={"Content-Type": "application/json", "User-Agent": programm.NAME},
        method="POST",
    )
    try:
        with urlopen(anfrage, timeout=ZEITLIMIT) as antwort:  # noqa: S310
            if antwort.status != 200:
                raise VerzeichnisFehler(f"Das Verzeichnis antwortet mit {antwort.status}.")
    except URLError as e:
        raise VerzeichnisFehler(f"Das Verzeichnis ist nicht erreichbar ({e.reason}).") from e
    except (OSError, ValueError) as e:
        raise VerzeichnisFehler("Das Verzeichnis ist nicht erreichbar.") from e


def melden() -> bool:
    """Meldet diese Tafel jetzt; hält Zeitpunkt, Version und einen Fehler fest."""
    m = VerzeichnisMeldung.laden()
    daten = angaben(m)
    try:
        _senden(daten)
    except VerzeichnisFehler as e:
        m.fehler = str(e)[:300]
        m.save(update_fields=["fehler"])
        logger.warning("Meldung im bintafeln-Verzeichnis: %s", e)
        return False
    m.gemeldet_am, m.gemeldete_version, m.fehler = timezone.now(), daten["version"], ""
    m.save(update_fields=["gemeldet_am", "gemeldete_version", "fehler"])
    return True


def abmelden() -> bool:
    """Löscht den Eintrag dieser Tafel im Verzeichnis."""
    m = VerzeichnisMeldung.laden()
    try:
        _senden({"kennung": str(m.kennung), "abmelden": True})
    except VerzeichnisFehler as e:
        logger.warning("Abmeldung im bintafeln-Verzeichnis: %s", e)
        return False
    m.gemeldet_am, m.gemeldete_version, m.fehler = None, "", ""
    m.save(update_fields=["gemeldet_am", "gemeldete_version", "fehler"])
    return True


def faellig(jetzt=None) -> bool:
    m = VerzeichnisMeldung.laden()
    if not m.aktiv or settings.DEMO:
        return False
    jetzt = jetzt or timezone.now()
    return (m.gemeldet_am is None or m.gemeldete_version != version()
            or jetzt - m.gemeldet_am >= ABSTAND)  # fmt: skip


def bei_bedarf_melden(jetzt=None) -> bool:
    """Nach einem Update und sonst einmal pro Woche (aus ``verzeichnis_melden``)."""
    return melden() if faellig(jetzt) else False


# --- Empfang (nur auf der Installation des Herausgebers) ------------------------------------


def annehmen(daten) -> str:
    """Nimmt eine Meldung an; liefert „gemeldet“, „abgemeldet“ oder wirft ValueError."""
    if not isinstance(daten, dict):
        raise ValueError("Ungültige Meldung")
    kennung = uuid.UUID(str(daten.get("kennung", "")))
    if daten.get("abmelden"):
        VerzeichnisEintrag.objects.filter(kennung=kennung).delete()
        return "abgemeldet"
    name = str(daten.get("name", "")).strip()[:200]
    if not name:
        raise ValueError("Name fehlt")
    kontakt = str(daten.get("kontakt", "")).strip()[:254]
    if kontakt and ("@" not in kontakt or any(z.isspace() for z in kontakt)):
        kontakt = ""
    werte = {"name": name, "kontakt": kontakt, "version": str(daten.get("version", ""))[:50],
             "letzte_meldung": timezone.now()}  # fmt: skip
    if not VerzeichnisEintrag.objects.filter(kennung=kennung).exists() and (
        VerzeichnisEintrag.objects.count() >= HOECHSTENS
    ):
        raise ValueError("Verzeichnis voll")
    VerzeichnisEintrag.objects.update_or_create(kennung=kennung, defaults=werte)
    return "gemeldet"
