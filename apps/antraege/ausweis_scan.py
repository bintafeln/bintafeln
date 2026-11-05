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

from django.core.cache import cache
from django.db import connections
from django.utils import timezone

from apps.antraege.models import ANHANG_ORDNER
from apps.core import privatdateien

log = logging.getLogger(__name__)

CACHE_SCHLUESSEL = "ausweis_scan_fortschritt"


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
    """Alle (nicht gelöschten) Anträge prüfen; Fortschritt im Cache. Liefert die Zahl der
    Abweichungen. Synchron – der Aufrufer sorgt für den Hintergrund."""
    from apps.antraege.models import Antrag

    pks = list(Antrag.objects.order_by("pk").values_list("pk", flat=True))
    stand = {"laeuft": True, "gesamt": len(pks), "fertig": 0, "abweichungen": 0}
    cache.set(CACHE_SCHLUESSEL, stand, 3600)
    for pk in pks:
        antrag = Antrag.objects.filter(pk=pk).first()
        if antrag and antrag_pruefen(antrag):
            stand["abweichungen"] += 1
        stand["fertig"] += 1
        cache.set(CACHE_SCHLUESSEL, stand, 3600)
    stand["laeuft"] = False
    cache.set(CACHE_SCHLUESSEL, stand, 3600)
    return stand["abweichungen"]


def alle_pruefen_starten() -> None:
    """Die Prüfung aller Anträge im Hintergrund anstoßen (tut nichts, wenn schon eine läuft)."""
    stand = cache.get(CACHE_SCHLUESSEL)
    if stand and stand.get("laeuft"):
        return
    cache.set(CACHE_SCHLUESSEL, {"laeuft": True, "gesamt": 0, "fertig": 0, "abweichungen": 0}, 3600)
    _im_hintergrund(alle_pruefen_jetzt)


def fortschritt() -> dict | None:
    """Stand der laufenden/letzten Sammelprüfung (oder None, wenn noch nie gestartet)."""
    return cache.get(CACHE_SCHLUESSEL)
