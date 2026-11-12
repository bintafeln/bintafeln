"""Automatischer Abruf aus dem Vereinsportal über den Dienst „abruf“ (ADR 0127).

bintafeln hat keinen Browser. Es schickt dem Dienst den Auftrag (Adressen, Zugangsdaten,
Zeitraum), reicht den 2FA-Code weiter, holt am Ende die Dateien ab und liest sie mit denselben
Regeln ein wie beim Hochladen von Hand (``einlesen.py``). Der Stand liegt im Dienst, damit alle
Serverprozesse dasselbe sehen. In Tests ``abruf._anfrage`` ersetzen.
"""

import datetime as dt
import json
import tempfile
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache

from apps.core import geheimnis
from apps.vereinsportal import einlesen
from apps.vereinsportal.models import PortalEinstellungen

MAX_TAGE = 93  # wie im bisherigen Programm: höchstens drei Monate
SPERRE = "vereinsportal-abruf-einlesen"
AKTIV = ("laeuft", "warte_auf_code")


class AbrufFehler(Exception):
    """Meldung für die Oberfläche."""


def verfuegbar() -> bool:
    """Ist der Dienst für diese Installation eingeschaltet (gemeinsamer Schlüssel gesetzt)?"""
    return bool(settings.ABRUF_SCHLUESSEL)


def _anfrage(pfad: str, daten: dict | None = None, ziel=None):
    """Spricht den Dienst an. Liefert das JSON der Antwort; mit ``ziel`` (Datei) wird der Inhalt
    dorthin geschrieben."""
    anfrage = urllib.request.Request(  # noqa: S310 – feste Adresse des eigenen Dienstes
        settings.ABRUF_URL + pfad,
        data=None if daten is None else json.dumps(daten).encode(),
        headers={"X-Abruf-Schluessel": settings.ABRUF_SCHLUESSEL,
                 "Content-Type": "application/json"},
        method="GET" if daten is None else "POST",
    )  # fmt: skip
    try:
        with urllib.request.urlopen(anfrage, timeout=600 if ziel else 10) as antwort:  # noqa: S310
            if ziel is None:
                return json.loads(antwort.read())
            while block := antwort.read(1024 * 1024):
                ziel.write(block)
            return None
    except urllib.error.HTTPError as fehler:
        try:
            meldung = json.loads(fehler.read()).get("fehler") or ""
        except ValueError:
            meldung = ""
        raise AbrufFehler(
            meldung or f"Der Abruf-Dienst meldet einen Fehler ({fehler.code})."
        ) from None
    except (OSError, ValueError) as fehler:
        raise AbrufFehler(
            "Der Abruf-Dienst ist nicht erreichbar. Läuft er (COMPOSE_PROFILES=abruf in der .env)?"
        ) from fehler


def stand() -> dict:
    """Stand des Dienstes; bei einer Störung ``{"stand": "stoerung", "fehler": …}``."""
    try:
        return _anfrage("/stand")
    except AbrufFehler as fehler:
        return {"stand": "stoerung", "schritt": "", "fehler": str(fehler), "dateien": {}}


def zeitraum_pruefen(von: dt.date, bis: dt.date) -> None:
    if bis < von:
        raise AbrufFehler("Das Enddatum liegt vor dem Startdatum.")
    if (bis - von).days > MAX_TAGE:
        raise AbrufFehler("Der Zeitraum ist zu groß: höchstens drei Monate.")
    if bis > dt.date.today():
        raise AbrufFehler("Das Enddatum liegt in der Zukunft.")


def starten(von: dt.date, bis: dt.date, mit_liste: bool) -> dict:
    e = PortalEinstellungen.laden()
    if not e.abruf_eingerichtet:
        raise AbrufFehler("Bitte zuerst Adressen und Zugangsdaten in den Einstellungen eintragen.")
    passwort = geheimnis.entschluesseln(e.passwort_verschluesselt)
    if not passwort:
        raise AbrufFehler("Das gespeicherte Passwort ist nicht mehr lesbar; bitte neu eintragen.")
    zeitraum_pruefen(von, bis)
    return _anfrage("/start", {
        "anmeldung_url": e.anmeldung_url, "liste_url": e.liste_url, "export_url": e.export_url,
        "email": e.email, "passwort": passwort, "von": f"{von:%d.%m.%Y}", "bis": f"{bis:%d.%m.%Y}",
        "mit_liste": bool(mit_liste and e.liste_url),
    })  # fmt: skip


def code_senden(code: str) -> dict:
    return _anfrage("/code", {"code": code.strip()})


def abbrechen() -> dict:
    return _anfrage("/abbrechen", {})


def verwerfen() -> None:
    _anfrage("/fertig", {})


def uebernehmen(von: str) -> list[tuple[bool, str]]:
    """Holt die fertigen Dateien ab und liest sie ein; liefert Meldungen ``(gelungen, Text)``.

    Jede Datei für sich: Eine unlesbare Spenderliste hält den Finanzexport nicht auf. Danach
    wirft der Dienst die Dateien weg, auch nach einem Fehler – sonst bliebe der Abruf hängen;
    das Hochladen von Hand bleibt ja. Eine Sperre im gemeinsamen Cache sorgt dafür, dass zwei
    Aufrufe (zwei Fenster, zwei Serverprozesse) nicht gleichzeitig einlesen."""
    if not cache.add(SPERRE, 1, timeout=900):
        return []
    try:
        s = _anfrage("/stand")
        if s.get("stand") != "fertig":
            return []
        meldungen = []
        for art, lesen in (("spenderliste", _spenderliste), ("finanzexport", _finanzexport)):
            if not s["dateien"].get(art):
                continue
            try:
                with tempfile.TemporaryFile() as datei:
                    _anfrage(f"/datei/{art}", ziel=datei)
                    datei.seek(0)
                    meldungen.append((True, lesen(datei, von)))
            except (AbrufFehler, einlesen.EinleseFehler) as fehler:
                meldungen.append((False, f"{NAMEN[art]}: {fehler}"))
        # Was der Dienst nicht holen konnte, ohne den Abruf abzubrechen (z. B. die Spenderliste)
        meldungen += [(False, hinweis) for hinweis in s.get("hinweise") or []]
        verwerfen()
        return meldungen
    finally:
        cache.delete(SPERRE)


NAMEN = {"spenderliste": "Spenderliste", "finanzexport": "Finanzexport"}


def _spenderliste(datei, von: str) -> str:
    return spenderliste_bericht(*einlesen.spenderliste_einlesen(datei.read()))


def spenderliste_bericht(anzahl: int, ohne: int) -> str:
    zusatz = f", {ohne} Zeilen ohne gültige E-Mail ausgelassen." if ohne else "."
    return f"Spenderliste ersetzt: {anzahl} Spender mit E-Mail{zusatz}"


def _finanzexport(datei, von: str) -> str:
    return einlesen.bericht(einlesen.finanzexport_einlesen(datei, von))
