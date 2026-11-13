"""Automatischer Abruf aus WISO MeinVerein über den Dienst „abruf“ (ADR 0127).

bintafeln hat keinen Browser. Es schickt dem Dienst den Auftrag (Adressen, Zugangsdaten,
Zeitraum), reicht den 2FA-Code weiter, holt am Ende die Dateien ab und liest sie mit denselben
Regeln ein wie beim Hochladen von Hand (``einlesen.py``). Der Stand liegt im Dienst, damit alle
Serverprozesse dasselbe sehen. In Tests ``abruf._anfrage`` ersetzen.

Die Zugangsdaten sind persönlich (ADR 0129): Jeder ruft mit dem eigenen ``Zugang`` ab, den
2FA-Code gibt nur ein, wer den Abruf gestartet hat. Jeder Abruf steht als ``Abruf`` in der
Historie; was er einliest, sehen alle.
"""

import datetime as dt
import json
import tempfile
import urllib.error
import urllib.request

from django.conf import settings
from django.core.cache import cache
from django.db.models import Sum
from django.utils import timezone

from apps.core import geheimnis
from apps.vereinsportal import einlesen
from apps.vereinsportal.models import Abruf, PortalEinstellungen, Zugang

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


def zugang(benutzer) -> Zugang | None:
    """Der persönliche Zugang dieses Kontos, wenn E-Mail und Passwort gespeichert sind."""
    z = Zugang.objects.filter(benutzer=benutzer).first()
    return z if z and z.vollstaendig else None


def laufender() -> Abruf | None:
    return Abruf.objects.filter(stand=Abruf.Stand.LAEUFT).first()


def _beenden(stand: str, meldung: str = "", **werte) -> None:
    """Schließt den laufenden Abruf in der Historie ab."""
    Abruf.objects.filter(stand=Abruf.Stand.LAEUFT).update(
        stand=stand, meldung=meldung[:2000], beendet_am=timezone.now(), **werte
    )


def abgleichen(s: dict) -> None:
    """Hält die Historie am Stand des Dienstes: Ein Fehler dort beendet den Abruf hier; läuft
    dort nichts mehr (z. B. nach einem Neustart des Dienstes), gilt er als abgebrochen."""
    if s["stand"] == "fehler":
        _beenden(Abruf.Stand.FEHLER, s.get("fehler") or "")
    elif s["stand"] == "frei":
        _beenden(Abruf.Stand.ABGEBROCHEN)


def starten(benutzer, von: dt.date, bis: dt.date, mit_liste: bool) -> dict:
    e = PortalEinstellungen.laden()
    if not e.adressen_eingerichtet:
        raise AbrufFehler("Bitte zuerst die Adressen in den Einstellungen eintragen.")
    z = zugang(benutzer)
    if not z:
        raise AbrufFehler("Bitte zuerst Ihre persönlichen Zugangsdaten eintragen.")
    passwort = geheimnis.entschluesseln(z.passwort_verschluesselt)
    if not passwort:
        raise AbrufFehler("Das gespeicherte Passwort ist nicht mehr lesbar; bitte neu eintragen.")
    zeitraum_pruefen(von, bis)
    mit_liste = bool(mit_liste and e.liste_url)
    antwort = _anfrage("/start", {
        "anmeldung_url": e.anmeldung_url, "liste_url": e.liste_url, "export_url": e.export_url,
        "email": z.email, "passwort": passwort, "von": f"{von:%d.%m.%Y}", "bis": f"{bis:%d.%m.%Y}",
        "mit_liste": mit_liste,
    })  # fmt: skip
    _beenden(Abruf.Stand.ABGEBROCHEN)  # Reste eines Abrufs, den der Dienst nicht mehr kennt
    Abruf.objects.create(
        benutzer=benutzer, wer=benutzer.get_full_name() or benutzer.get_username(),
        von=von, bis=bis, mit_liste=mit_liste,
    )  # fmt: skip
    return antwort


def gehoert(benutzer) -> bool:
    """Darf dieses Konto den 2FA-Code eingeben? Nur wer den laufenden Abruf gestartet hat."""
    a = laufender()
    return bool(a and a.benutzer_id == benutzer.pk)


def code_senden(benutzer, code: str) -> dict:
    if not gehoert(benutzer):
        raise AbrufFehler("Den Code gibt nur ein, wer den Abruf gestartet hat.")
    return _anfrage("/code", {"code": code.strip()})


def abbrechen() -> dict:
    antwort = _anfrage("/abbrechen", {})
    _beenden(Abruf.Stand.ABGEBROCHEN)
    return antwort


def verwerfen() -> None:
    _anfrage("/fertig", {})
    _beenden(Abruf.Stand.ABGEBROCHEN)


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
        meldungen, werte, export_ok = [], {}, False
        for art, lesen in (("spenderliste", _spenderliste), ("finanzexport", _finanzexport)):
            if not s["dateien"].get(art):
                continue
            try:
                with tempfile.TemporaryFile() as datei:
                    _anfrage(f"/datei/{art}", ziel=datei)
                    datei.seek(0)
                    text, zahlen = lesen(datei, von)
                    meldungen.append((True, text))
                    werte |= zahlen
                    export_ok = export_ok or art == "finanzexport"
            except (AbrufFehler, einlesen.EinleseFehler) as fehler:
                meldungen.append((False, f"{NAMEN[art]}: {fehler}"))
        if not s["dateien"].get("finanzexport"):
            meldungen.append((False, "Der Finanzexport wurde nicht geholt."))
        # Was der Dienst nicht holen konnte, ohne den Abruf abzubrechen (z. B. die Spenderliste)
        meldungen += [(False, hinweis) for hinweis in s.get("hinweise") or []]
        _anfrage("/fertig", {})
        fehler = " ".join(text for gelungen, text in meldungen if not gelungen)
        # Der Abruf gilt nur als gelungen, wenn aus dem Finanzexport Belege ankamen – die
        # Spenderliste allein ist kein Ergebnis.
        _beenden(Abruf.Stand.EINGELESEN if export_ok else Abruf.Stand.FEHLER, fehler, **werte)
        return meldungen
    finally:
        cache.delete(SPERRE)


NAMEN = {"spenderliste": "Spenderliste", "finanzexport": "Finanzexport"}


def _spenderliste(datei, von: str) -> tuple[str, dict]:
    anzahl, ohne = einlesen.spenderliste_einlesen(datei.read())
    return spenderliste_bericht(anzahl, ohne), {"kontakte": anzahl}


def spenderliste_bericht(anzahl: int, ohne: int) -> str:
    zusatz = f", {ohne} Zeilen ohne gültige E-Mail ausgelassen." if ohne else "."
    return f"Spenderliste ersetzt: {anzahl} Spender mit E-Mail{zusatz}"


def _finanzexport(datei, von: str) -> tuple[str, dict]:
    e = einlesen.finanzexport_einlesen(datei, von)
    if e.leer:  # nichts angekommen ist kein Erfolg, auch wenn die Datei lesbar war
        raise einlesen.EinleseFehler(e.warum_leer())
    zahlen = {
        "neu": e.neu, "doppelt": e.doppelt, "neue_spender": e.neue_spender,
        "versendet": e.versendet, "belege": e.belege, "ausgelassen": e.ohne_anschrift,
    }  # fmt: skip
    return einlesen.bericht(e), zahlen


def historie(alle: bool = False, grenze: int = 10) -> dict:
    """Die bisherigen Abrufe für die Abruf-Seite: Kurzstatistik und Liste (neueste zuerst)."""
    abrufe = Abruf.objects.all()
    gelungen = abrufe.filter(stand=Abruf.Stand.EINGELESEN)
    summe = gelungen.aggregate(neu=Sum("neu"), spender=Sum("neue_spender"))
    anzahl = abrufe.count()
    return {
        "anzahl": anzahl, "gelungen": gelungen.count(),
        "neu": summe["neu"] or 0, "neue_spender": summe["spender"] or 0,
        "letzter": gelungen.first(),
        "abrufe": abrufe if alle else abrufe[:grenze],
        "mehr": 0 if alle else max(anzahl - grenze, 0),
    }  # fmt: skip
