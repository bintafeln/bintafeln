"""Aufgerufene Nummern auf der Homepage der Tafel (ADR 0181).

Eine kleine öffentliche Seite je Ausgabestelle: während der Ausgabe die gerade aufgerufenen
Kundennummern, sonst „Zurzeit keine Ausgabe“ oder „Ausgabe beendet“ – dann mit der nächsten
Ausgabe und der Zeit bis dahin (Tage, Stunden, Minuten). Sie hat einen eigenen
Schlüssel (``AufrufEinstellungen.homepage_schluessel``), der nichts anderes öffnet – der Schlüssel
der Anzeige-Geräte käme auch an Kiosk, Abfrage und Monitor-Aufteilung und gehört deshalb nie auf
eine öffentliche Seite. Die Seite liest nur: kein Abgleich, kein Schreiben. Der Stand wird kurz
zwischengespeichert, damit viele Besucher den Server nicht belasten.
"""

import datetime as dt

from django.core.cache import cache
from django.utils import timezone

from apps.aufruf import ablauf
from apps.aufruf.models import AufrufEinstellungen
from apps.ausgabe import ausgabetag
from apps.ausgabe.models import Schliesszeit

KEINE, BEENDET, NUMMERN, GLEICH = "keine", "beendet", "nummern", "gleich"
SEKUNDEN = 5  # so lange gilt ein berechneter Stand für alle Besucher
NEU_LADEN = 10  # so oft fragt die Seite nach (Sekunden)
VORAUS_TAGE = 14  # so weit sucht die Seite nach der nächsten Ausgabe
NACHFRIST = dt.timedelta(minutes=60)  # so lange nach dem Beginn heißt es noch „beginnt heute“


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


def naechste_ausgabe(stelle, jetzt: dt.datetime, heute_mit: bool = True) -> dict | None:
    """Die nächste Ausgabe der Stelle in den nächsten Tagen: {"tag", "beginn", "ziel"}.

    Es zählen die Kundengruppen des Tages (auch Sonderausgaben, ADR 0072), nicht die Tage einer
    Schließzeit (ADR 0144). ``beginn`` ist die früheste Uhrzeit der Gruppen (None, wenn keine
    bekannt ist), ``ziel`` der Zeitpunkt für den Countdown (None ohne Uhrzeit). Heute zählt nur,
    wenn ``heute_mit`` und der Beginn noch nicht länger als ``NACHFRIST`` vorbei ist.
    """
    jetzt = timezone.localtime(jetzt)
    heute = jetzt.date()
    geschlossen = Schliesszeit.tage(stelle, heute, heute + dt.timedelta(days=VORAUS_TAGE))
    for i in range(VORAUS_TAGE + 1):
        tag = heute + dt.timedelta(days=i)
        if (i == 0 and not heute_mit) or tag in geschlossen:
            continue
        gruppen = ausgabetag.gruppen_am(stelle, tag)
        if not gruppen:
            continue
        zeiten = [z for z in map(ausgabetag.beginn, gruppen) if z is not None]
        beginn = min(zeiten) if zeiten else None
        ziel = None
        if beginn is not None:
            ziel = timezone.make_aware(dt.datetime.combine(tag, beginn))
        if i == 0 and (ziel is None or jetzt - ziel > NACHFRIST):
            continue  # heute ohne bekannte Uhrzeit oder längst vorbei: nicht „gleich“ versprechen
        return {"tag": tag, "beginn": beginn, "ziel": ziel}
    return None


def countdown(ziel: dt.datetime | None, jetzt: dt.datetime) -> str:
    """„noch 2 Tage, 5 Std., 12 Min.“ – ohne Sekunden; gleicher Text wie im Browser."""
    if ziel is None:
        return ""
    minuten = int((ziel - jetzt).total_seconds() // 60)
    if minuten < 1:
        return "gleich geht es los"
    tage, rest = divmod(minuten, 24 * 60)
    stunden, minuten = divmod(rest, 60)
    teile = []
    if tage:
        teile.append(f"{tage} Tag" if tage == 1 else f"{tage} Tage")
    if tage or stunden:
        teile.append(f"{stunden} Std.")
    teile.append(f"{minuten} Min.")
    return "noch " + ", ".join(teile)


def _berechnen(e) -> dict:
    jetzt = timezone.now()
    heute = timezone.localdate()
    d = ablauf.stand_fuer_anzeige(ablauf.tag_holen(e.ausgabestelle, heute), e, heute)
    if "error" in d:
        art, nummern = KEINE, []
    elif d["finished"]:
        art, nummern = BEENDET, []
    else:
        nummern = list(d["current_numbers"])
        art = NUMMERN if nummern else GLEICH
    naechste = None
    if art in (KEINE, BEENDET):
        naechste = naechste_ausgabe(e.ausgabestelle, jetzt, heute_mit=art == KEINE)
    return {"art": art, "nummern": nummern, "naechste": naechste, "stand": jetzt}


def stand(e) -> dict:
    """{"art", "nummern", "naechste", "stand"} – nur Kundennummern, nie Namen, Vorrang oder wer
    danach kommt; ``naechste`` siehe ``naechste_ausgabe()``."""
    schluessel = f"aufruf-homepage-{e.pk}"
    ergebnis = cache.get(schluessel)
    if ergebnis is None:
        ergebnis = _berechnen(e)
        cache.set(schluessel, ergebnis, SEKUNDEN)
    return ergebnis


def einbetten_erlaubt(e) -> str:
    """Wert für ``Content-Security-Policy: frame-ancestors``: nur die eingetragene Homepage."""
    return e.homepage_adresse or "'none'"
