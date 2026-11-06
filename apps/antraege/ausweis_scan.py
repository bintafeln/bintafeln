"""Alle Nachweise eines Antrags auf einen Ausweis durchsuchen und die Staatsangehörigkeit gegen die
angegebenen abgleichen (ADR 0107).

Baut auf ``apps.antraege.ausweis_pruefung`` (liest die MRZ eines Bildes lokal) auf: Hier wird je
Antrag über **alle** Bild-Nachweise gegangen und das Ergebnis am Antrag gespeichert
(``ausweis_staat``, ``ausweis_abweichung``, ``ausweis_anhang``, ``ausweis_geprueft_am``). Eine
**Abweichung** liegt nur vor, wenn die im Ausweis erkannte Staatsangehörigkeit zu **keiner** im
Antrag angegebenen passt (Hauptperson und Angehörige). Wird kein Ausweis gefunden oder passt alles,
gibt es keine Abweichung und damit keinen Hinweis.

Neue Anträge werden beim Eingang automatisch im Hintergrund geprüft (ein Thread, der seine
DB-Verbindung selbst schließt); über die Antragsliste lassen sich auf Befehl auch **alle** Anträge
prüfen (Fortschritt im gemeinsamen Cache).

Die Sammelprüfung läuft dabei in einem **eigenen Prozess** (Management-Befehl ``ausweise_pruefen``),
mit einem **Zeitlimit je Antrag**. So hält ein einzelner Nachweis, der eine Bild-/PDF-Bibliothek
zum Absturz bringt oder endlos hängen lässt, den ganzen Lauf nicht mehr an: Nur dieser Prozess wird
beendet, der Antrag wird übersprungen (als geprüft markiert) und der Lauf läuft weiter.
"""

import logging
import os
import threading
import time

from django.core.cache import cache
from django.db import connections
from django.utils import timezone

from apps.antraege.models import ANHANG_ORDNER
from apps.core import privatdateien

log = logging.getLogger(__name__)

CACHE_SCHLUESSEL = "ausweis_scan_fortschritt"
# Der Fortschritt lebt im gemeinsamen Cache (überlebt einen App-Neustart), damit ein durch ein
# Update unterbrochener Lauf erkannt und fortgesetzt werden kann.
CACHE_DAUER = 86400  # 1 Tag – so lange bleibt ein unterbrochener Lauf fortsetzbar
# Der Hintergrund-Thread hinterlässt bei jedem Antrag ein Lebenszeichen (``aktualisiert``). Kommt
# so lange keins mehr, gilt der Lauf als abgebrochen (z. B. durch einen Update-Neustart, der den
# Thread beendet) und wird beim nächsten Seitenaufruf automatisch fortgesetzt.
VERWAIST_SEKUNDEN = 180
# Zeitlimit je Antrag im Prüf-Prozess: Hängt eine Bibliothek an einem Bild, wird der Antrag nach so
# vielen Sekunden übersprungen. Kleiner als VERWAIST_SEKUNDEN, damit ein einzelner langsamer Antrag
# den Lauf nicht fälschlich als „verwaist“ erscheinen lässt.
ZEIT_JE_ANTRAG = 90


def _verwaist(stand) -> bool:
    """True, wenn ein als laufend markierter Lauf kein frisches Lebenszeichen mehr hat."""
    return bool(
        stand
        and stand.get("laeuft")
        and time.time() - stand.get("aktualisiert", 0) > VERWAIST_SEKUNDEN
    )


def aktiv() -> bool:
    from apps.antraege import ausweis_pruefung
    from apps.antraege.models import AntragEinstellungen

    return ausweis_pruefung.aktiv(AntragEinstellungen.laden())


def angegebene_staaten(antrag) -> set[str]:
    """Angegebene Staatsangehörigkeiten (Hauptperson + Angehörige), kleingeschrieben."""
    namen = [antrag.staatsangehoerigkeit] + [p.staatsangehoerigkeit for p in antrag.personen.all()]
    return {n.strip().casefold() for n in namen if n and n.strip()}


def antrag_pruefen(antrag) -> bool:
    """Prüft alle Bild-Nachweise des Antrags und speichert das Ergebnis am Antrag. Liefert True,
    wenn eine Abweichung gefunden wurde. Fehler werden verschluckt (nur ein Hinweis)."""
    from apps.antraege import ausweis_pruefung

    angegeben = angegebene_staaten(antrag)
    erste = None  # erster lesbarer Ausweis (für die Anzeige, wenn nichts abweicht)
    treffer = None  # erster Ausweis, dessen Staat zu keiner Angabe passt
    for d in antrag.anhaenge.all():
        typ = (d.typ or "").lower()
        if "image" not in typ and "pdf" not in typ:  # Bilder und PDFs einbeziehen
            continue
        inhalt = privatdateien.lesen(ANHANG_ORDNER, d.datei)
        if inhalt is None:
            continue
        try:
            bericht = ausweis_pruefung.pruefen_datei(inhalt, d.typ)
        except Exception as fehler:  # noqa: BLE001 – nur ein Hinweis, nichts darf abbrechen
            log.warning("Ausweisprüfung für Antrag %s fehlgeschlagen: %s", antrag.pk, fehler)
            continue
        staat = bericht.get("staatsangehoerigkeit", "") if bericht.get("erkannt") else ""
        if not staat:
            continue
        if erste is None:
            erste = (d, staat)
        if angegeben and staat.casefold() not in angegeben:
            treffer = (d, staat)
            break
    gewaehlt = treffer or erste
    antrag.ausweis_geprueft_am = timezone.now()
    antrag.ausweis_anhang = gewaehlt[0] if gewaehlt else None
    antrag.ausweis_staat = gewaehlt[1] if gewaehlt else ""
    antrag.ausweis_abweichung = treffer is not None
    antrag.save(update_fields=[
        "ausweis_geprueft_am", "ausweis_anhang", "ausweis_staat", "ausweis_abweichung",
    ])  # fmt: skip
    return antrag.ausweis_abweichung


def _im_hintergrund(fn) -> None:
    """``fn`` in einem Daemon-Thread laufen lassen; dessen DB-Verbindung danach schließen."""

    def lauf():
        try:
            fn()
        except Exception as fehler:  # noqa: BLE001
            log.warning("Ausweisprüfung im Hintergrund fehlgeschlagen: %s", fehler)
        finally:
            connections.close_all()

    threading.Thread(target=lauf, daemon=True).start()


def neuen_pruefen(antrag_pk: int) -> None:
    """Einen neuen Antrag beim Eingang im Hintergrund prüfen (nur wenn die Prüfung aktiv ist)."""
    if not aktiv():
        return

    def lauf():
        from apps.antraege.models import Antrag

        antrag = Antrag.objects.filter(pk=antrag_pk).first()
        if antrag:
            antrag_pruefen(antrag)

    _im_hintergrund(lauf)


def _cache_stand(laeuft: bool, gesamt: int) -> dict:
    """Aktuellen Fortschritt aus der Datenbank in den gemeinsamen Cache schreiben (zugleich
    Lebenszeichen). ``fertig`` = schon geprüfte Anträge."""
    from apps.antraege.models import Antrag

    offen = Antrag.objects.filter(ausweis_geprueft_am__isnull=True).count()
    stand = {
        "laeuft": laeuft,
        "gesamt": gesamt,
        "fertig": gesamt - offen,
        "abweichungen": Antrag.objects.filter(ausweis_abweichung=True).count(),
        "aktualisiert": time.time(),
    }
    cache.set(CACHE_SCHLUESSEL, stand, CACHE_DAUER)
    return stand


def _erster_offener():
    from apps.antraege.models import Antrag

    return (
        Antrag.objects.filter(ausweis_geprueft_am__isnull=True)
        .order_by("pk")
        .values_list("pk", flat=True)
        .first()
    )


def stapel_im_prozess(zeit_je_antrag: int = ZEIT_JE_ANTRAG) -> None:
    """Die offenen Anträge der Reihe nach prüfen – gedacht als **eigener Prozess** (Management-
    Befehl ``ausweise_pruefen``), damit ein Absturz oder Hänger an einem Nachweis nur diesen Prozess
    trifft.

    Je Antrag gilt ein **Zeitlimit** (SIGALRM, nur im Haupt-Thread verfügbar); jeder Antrag wird –
    auch bei Fehler oder Zeitüberschreitung – als geprüft markiert, und der Fortschritt landet live
    im gemeinsamen Cache. Läuft diese Funktion ausnahmsweise nicht als Haupt-Thread (Rückfall ohne
    eigenen Prozess), fehlt nur das Zeitlimit; alles andere bleibt gleich."""
    import signal

    from apps.antraege.models import Antrag

    class _Zeitlimit(Exception):
        pass

    def _wecker(signum, rahmen):
        raise _Zeitlimit(f"Zeitlimit {zeit_je_antrag}s überschritten")

    try:
        signal.signal(signal.SIGALRM, _wecker)
        hat_wecker = True
    except (ValueError, AttributeError):  # nicht im Haupt-Thread / kein SIGALRM (z. B. Windows)
        hat_wecker = False

    gesamt = Antrag.objects.count()
    while True:
        pk = _erster_offener()
        if pk is None:
            break
        _cache_stand(True, gesamt)  # Lebenszeichen vor der (evtl. langen) Prüfung
        antrag = Antrag.objects.filter(pk=pk).first()
        if antrag is None:  # zwischenzeitlich gelöscht – nächster
            continue
        if hat_wecker:
            signal.alarm(zeit_je_antrag)
        try:
            antrag_pruefen(antrag)
        except Exception as fehler:  # noqa: BLE001 – inkl. Zeitlimit; nie den Lauf anhalten
            log.warning("Ausweisprüfung für Antrag %s übersprungen: %s", pk, fehler)
            Antrag.objects.filter(pk=pk).update(ausweis_geprueft_am=timezone.now())
        finally:
            if hat_wecker:
                signal.alarm(0)
        _cache_stand(True, gesamt)


def ressourcen_begrenzen() -> None:
    """Den eigenen Prozess ausbremsen und – wenn eingestellt – deckeln (ADR 0111).

    Wird zu Beginn des Prüf-Prozesses aufgerufen: niedrige CPU-Priorität (``nice``), damit die
    rechenintensive Bildprüfung den Einlass nicht ausbremst, und optional ein harter Speicherdeckel
    (``RLIMIT_AS``), damit ein einzelner Nachweis nie den ganzen Arbeitsspeicher aufbraucht. Läuft
    der Prozess in den Deckel, beendet das Betriebssystem ihn mit einem Fehler; der Treiber
    überspringt dann diesen Antrag wie bei einem Absturz. Fehlt die Funktion auf einer Plattform
    (z. B. Windows), wird der jeweilige Schritt einfach übersprungen."""
    from django.conf import settings

    nice = getattr(settings, "AUSWEIS_NICE", 0)
    if nice:
        try:
            os.nice(nice)
        except (AttributeError, OSError) as fehler:  # z. B. Windows oder fehlende Rechte
            log.debug("Priorität des Prüf-Prozesses nicht gesetzt: %s", fehler)

    speicher_mb = getattr(settings, "AUSWEIS_SPEICHER_MB", 0)
    if speicher_mb:
        try:
            import resource

            grenze = speicher_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (grenze, grenze))
        except (ImportError, ValueError, OSError) as fehler:  # z. B. Windows
            log.debug("Speicherdeckel des Prüf-Prozesses nicht gesetzt: %s", fehler)


def _stapel_starten() -> None:
    """Den Prüf-Unterprozess (Management-Befehl ``ausweise_pruefen``) starten und auf sein Ende
    warten. Als eigene Funktion, damit Tests sie ersetzen. Wirft ``OSError``, wenn er sich nicht
    starten lässt (dann rechnet der Treiber im selben Prozess weiter)."""
    import subprocess
    import sys
    from pathlib import Path

    from django.conf import settings

    subprocess.run(  # noqa: S603 – feste Argumente, keine Shell
        [sys.executable, str(Path(settings.BASE_DIR) / "manage.py"), "ausweise_pruefen"],
        cwd=str(settings.BASE_DIR),
        check=False,
    )


def alle_pruefen_jetzt() -> int:
    """Treiber der Sammelprüfung (läuft im Hintergrund-Thread). Startet die eigentliche Prüfung in
    einem **eigenen Prozess** (``stapel_im_prozess`` über den Management-Befehl), damit ein Absturz
    oder Hänger an einem Nachweis nur diesen Prozess trifft. Kommt der Prozess am ersten offenen
    Antrag nicht voran (er ist daran abgestürzt/gehangen), wird dieser übersprungen und neu
    gestartet – bis alle geprüft sind. Liefert die Gesamtzahl der Abweichungen.

    Nur Anträge ohne ``ausweis_geprueft_am`` werden abgearbeitet, der Lauf ist also fortsetzbar."""
    from apps.antraege.models import Antrag

    gesamt = Antrag.objects.count()
    _cache_stand(True, gesamt)
    while True:
        erster = _erster_offener()
        if erster is None:
            break
        _cache_stand(True, gesamt)  # Lebenszeichen vor dem blockierenden Unterprozess
        try:
            _stapel_starten()
        except OSError as fehler:
            # Unterprozess nicht startbar → im selben Prozess weiter (ohne Absturz-/Hänger-Schutz).
            log.warning("Prüf-Unterprozess nicht startbar (%s); im Prozess weiter.", fehler)
            stapel_im_prozess()
        else:
            if _erster_offener() == erster:  # kein Fortschritt → dieser Antrag hat ihn abgeschossen
                log.warning("Antrag %s übersprungen (Prüf-Prozess abgebrochen).", erster)
                Antrag.objects.filter(pk=erster).update(ausweis_geprueft_am=timezone.now())
    return _cache_stand(False, gesamt)["abweichungen"]


def alle_pruefen_starten() -> None:
    """Die Prüfung aller Anträge im Hintergrund anstoßen. Tut nichts, wenn wirklich noch eine
    läuft; einen verwaisten (abgebrochenen) Lauf ersetzt sie dagegen durch einen neuen, der die
    offenen Anträge fortsetzt."""
    stand = cache.get(CACHE_SCHLUESSEL)
    if stand and stand.get("laeuft") and not _verwaist(stand):
        return
    cache.set(
        CACHE_SCHLUESSEL,
        {"laeuft": True, "gesamt": 0, "fertig": 0, "abweichungen": 0, "aktualisiert": time.time()},
        CACHE_DAUER,
    )
    _im_hintergrund(alle_pruefen_jetzt)


def fortsetzen_wenn_unterbrochen() -> bool:
    """Einen durch einen Neustart (Update) abgebrochenen Sammellauf im Hintergrund fortsetzen.
    Liefert True, wenn gerade fortgesetzt wurde. Wird bei jedem Aufruf der Antragsliste und des
    Fortschritt-Pollings aufgerufen, damit ein hängengebliebener Lauf von selbst weiterläuft."""
    if _verwaist(cache.get(CACHE_SCHLUESSEL)) and aktiv():
        alle_pruefen_starten()
        return True
    return False


def fortschritt() -> dict | None:
    """Stand der laufenden/letzten Sammelprüfung (oder None, wenn noch nie gestartet). Enthält
    zusätzlich ``unterbrochen`` (ein als laufend markierter Lauf ohne frisches Lebenszeichen)."""
    stand = cache.get(CACHE_SCHLUESSEL)
    if stand is None:
        return None
    stand = dict(stand)
    stand["unterbrochen"] = _verwaist(stand)
    return stand
