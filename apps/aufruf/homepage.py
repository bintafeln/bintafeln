"""Aufgerufene Nummern auf der Homepage der Tafel (ADR 0181).

Eine kleine öffentliche Seite je Ausgabestelle: während der Ausgabe die gerade aufgerufenen
Kundennummern, sonst „Zurzeit keine Ausgabe“ oder „Ausgabe beendet“. Sie hat einen eigenen
Schlüssel (``AufrufEinstellungen.homepage_schluessel``), der nichts anderes öffnet – der Schlüssel
der Anzeige-Geräte käme auch an Kiosk, Abfrage und Monitor-Aufteilung und gehört deshalb nie auf
eine öffentliche Seite. Die Seite liest nur: kein Abgleich, kein Schreiben. Der Stand wird kurz
zwischengespeichert, damit viele Besucher den Server nicht belasten.
"""

from django.core.cache import cache
from django.utils import timezone

from apps.aufruf import ablauf
from apps.aufruf.models import AufrufEinstellungen

KEINE, BEENDET, NUMMERN, GLEICH = "keine", "beendet", "nummern", "gleich"
SEKUNDEN = 5  # so lange gilt ein berechneter Stand für alle Besucher
NEU_LADEN = 10  # so oft fragt die Seite nach (Sekunden)


def einstellungen(schluessel) -> AufrufEinstellungen | None:
    """Die Ausgabestelle zu einem Homepage-Schlüssel – nur wenn dort eingeschaltet."""
    if not schluessel:
        return None
    return (
        AufrufEinstellungen.objects.select_related("ausgabestelle")
        .filter(homepage=True, homepage_schluessel=schluessel, aktiv=True,
                ausgabestelle__aktiv=True)
        .first()
    )  # fmt: skip


def _berechnen(e) -> dict:
    heute = timezone.localdate()
    d = ablauf.stand_fuer_anzeige(ablauf.tag_holen(e.ausgabestelle, heute), e, heute)
    if "error" in d:
        return {"art": KEINE, "nummern": []}
    if d["finished"]:
        return {"art": BEENDET, "nummern": []}
    nummern = list(d["current_numbers"])
    return {"art": NUMMERN if nummern else GLEICH, "nummern": nummern}


def stand(e) -> dict:
    """{"art", "nummern"} – nur Kundennummern, nie Namen, Vorrang oder wer danach kommt."""
    schluessel = f"aufruf-homepage-{e.pk}"
    ergebnis = cache.get(schluessel)
    if ergebnis is None:
        ergebnis = _berechnen(e)
        cache.set(schluessel, ergebnis, SEKUNDEN)
    return ergebnis


def einbetten_erlaubt(e) -> str:
    """Wert für ``Content-Security-Policy: frame-ancestors``: nur die eingetragene Homepage."""
    return e.homepage_adresse or "'none'"
