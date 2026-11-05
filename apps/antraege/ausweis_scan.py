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
prüfen (ebenfalls im Hintergrund, Fortschritt im gemeinsamen Cache).
"""

import logging
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


def alle_pruefen_jetzt() -> int:
    """Alle noch **nicht geprüften** Anträge prüfen; Fortschritt im Cache. Liefert die Gesamtzahl
    der Abweichungen. Synchron – der Aufrufer sorgt für den Hintergrund.

    Es werden nur Anträge ohne ``ausweis_geprueft_am`` abgearbeitet. Dadurch setzt ein nach einem
    Neustart (Update) erneut gestarteter Lauf genau dort fort, wo er abgebrochen wurde, statt von
    vorn zu beginnen. Schon geprüfte Anträge zählen als „fertig“ in den Stand hinein."""
    from apps.antraege.models import Antrag

    gesamt = Antrag.objects.count()
    offen = list(
        Antrag.objects.filter(ausweis_geprueft_am__isnull=True)
        .order_by("pk")
        .values_list("pk", flat=True)
    )
    stand = {
        "laeuft": True,
        "gesamt": gesamt,
        "fertig": gesamt - len(offen),  # bereits geprüfte Anträge
        "abweichungen": Antrag.objects.filter(ausweis_abweichung=True).count(),
        "aktualisiert": time.time(),
    }
    cache.set(CACHE_SCHLUESSEL, stand, CACHE_DAUER)
    for pk in offen:
        antrag = Antrag.objects.filter(pk=pk).first()
        if antrag and antrag_pruefen(antrag):
            stand["abweichungen"] += 1
        stand["fertig"] += 1
        stand["aktualisiert"] = time.time()  # Lebenszeichen
        cache.set(CACHE_SCHLUESSEL, stand, CACHE_DAUER)
    stand["laeuft"] = False
    stand["aktualisiert"] = time.time()
    cache.set(CACHE_SCHLUESSEL, stand, CACHE_DAUER)
    return stand["abweichungen"]


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
