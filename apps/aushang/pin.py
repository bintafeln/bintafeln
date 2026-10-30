"""Persönliche PIN für das Ändern am Aushang-Monitor (ADR 0080): Wer am Monitor etwas einträgt,
wählt seinen Namen und bestätigt mit seiner PIN. So steht der richtige Name im Plan und im
Änderungsprotokoll. Gespeichert wird die PIN nur gehasht; nach ``VERSUCHE`` falschen Eingaben
ist sie eine Weile gesperrt."""

import datetime as dt

from django.contrib.auth.hashers import check_password, make_password
from django.utils import timezone

from apps.aushang.models import MonitorPin

MINDESTLAENGE = 6


def setzen(benutzer, pin: str) -> None:
    MonitorPin.objects.update_or_create(
        benutzer=benutzer, defaults={"pin": make_password(pin), "fehler": 0, "gesperrt_bis": None}
    )


def entfernen(benutzer) -> None:
    MonitorPin.objects.filter(benutzer=benutzer).delete()


def mit_pin() -> set[int]:
    """Konten (aktiv, keine Ausgabestellen-Konten), die eine PIN eingerichtet haben."""
    return set(MonitorPin.objects.filter(benutzer__is_active=True, benutzer__stelle__isnull=True)
               .values_list("benutzer_id", flat=True))  # fmt: skip


def pruefen(benutzer_pk, pin: str):
    """Das Konto zur PIN; ValueError mit verständlichem Text, wenn es nicht passt."""
    eintrag = (MonitorPin.objects.select_related("benutzer")
               .filter(benutzer_id=benutzer_pk if str(benutzer_pk).isdigit() else 0,
                       benutzer__is_active=True).first())  # fmt: skip
    if eintrag is None:
        raise ValueError("Für diese Person ist keine PIN eingerichtet.")
    jetzt = timezone.now()
    if eintrag.gesperrt_bis and eintrag.gesperrt_bis > jetzt:
        bis = timezone.localtime(eintrag.gesperrt_bis)
        raise ValueError(f"Zu viele falsche Versuche: Die PIN ist bis {bis:%H:%M} Uhr gesperrt.")
    if not check_password(pin or "", eintrag.pin):
        eintrag.fehler += 1
        if eintrag.fehler >= MonitorPin.VERSUCHE:
            eintrag.fehler = 0
            eintrag.gesperrt_bis = jetzt + dt.timedelta(minutes=MonitorPin.SPERRE_MINUTEN)
        eintrag.save(update_fields=["fehler", "gesperrt_bis"])
        raise ValueError("Die PIN stimmt nicht.")
    if eintrag.fehler or eintrag.gesperrt_bis:
        eintrag.fehler, eintrag.gesperrt_bis = 0, None
        eintrag.save(update_fields=["fehler", "gesperrt_bis"])
    return eintrag.benutzer
