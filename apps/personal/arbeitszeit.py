"""Arbeitszeiterfassung: Kommen und Gehen stempeln, vergessenes Gehen erkennen (ADR 0020)."""

import datetime as dt

from django.utils import timezone

from apps.personal.models import ArbeitszeitEinstellungen, Zeitbuchung


class StempelFehler(ValueError):
    pass


def erfasst(benutzer) -> bool:
    """Ob für diese Person Arbeitszeit erfasst wird. Die Angabe bei der Person („stempelt“ oder
    „stempelt nicht“) geht vor; sonst gilt die Einstellung der Tafel: ausgeschaltet niemand,
    eingeschaltet fest Angestellte immer und Ehrenamtliche nur, wenn es erlaubt ist."""
    if benutzer.zeiterfassung == benutzer.Zeiterfassung.AN:
        return True
    if benutzer.zeiterfassung == benutzer.Zeiterfassung.AUS:
        return False
    e = ArbeitszeitEinstellungen.laden()
    if not e.aktiv:
        return False
    if benutzer.beschaeftigung == benutzer.Beschaeftigung.FEST:
        return True
    return e.ehrenamtliche_stempeln


def darf_stempeln(benutzer) -> bool:
    """Angemeldete, nicht gesperrte Konten, für die Arbeitszeit erfasst wird (``erfasst()``)."""
    if not benutzer.is_authenticated or not benutzer.is_active:
        return False
    return erfasst(benutzer)


# Sitzung: bis wann das Handy nach dem QR-Code am Aushang-Monitor stempeln darf (Zeitstempel)
SITZUNG_FREIGABE = "stempeln_frei_bis"
FREIGABE_MINUTEN = 5


def freigeben(request) -> None:
    """Der QR-Code am Monitor wurde gerade gescannt: Dieses Handy darf kurz stempeln."""
    bis = timezone.now() + dt.timedelta(minutes=FREIGABE_MINUTEN)
    request.session[SITZUNG_FREIGABE] = bis.timestamp()


def hier_erlaubt(request) -> bool:
    """Ob in dieser Sitzung gestempelt werden darf: immer, solange die Tafel nicht „nur am
    Monitor“ verlangt; sonst nur kurz nach dem Scannen des QR-Codes am Monitor."""
    if not ArbeitszeitEinstellungen.laden().nur_am_monitor:
        return True
    return request.session.get(SITZUNG_FREIGABE, 0) > timezone.now().timestamp()


def stand(benutzer, jetzt=None) -> tuple[str, list[tuple[str, str]]]:
    """Wo die Person gerade steht und was sie jetzt stempeln kann: (Text, [(aktion, Knopf)])."""
    offen = laufend(benutzer, jetzt)
    if offen:
        seit = timezone.localtime(offen.beginn)
        return f"Eingestempelt seit {seit:%H:%M} Uhr.", [("pause", "Pause"), ("gehen", "Gehen")]
    pause = in_pause(benutzer, jetzt)
    if pause:
        seit = timezone.localtime(pause.ende)
        return (f"Pause oder Feierabend seit {seit:%H:%M} Uhr.",
                [("kommen", "Pause beenden")])  # fmt: skip
    return "Nicht eingestempelt.", [("kommen", "Kommen")]


def stempeln(benutzer, aktion: str, jetzt=None) -> str:
    """Stempelt „kommen“, „pause“ oder „gehen“ und liefert die Meldung; sonst StempelFehler."""
    if aktion == "kommen":
        b = kommen(benutzer, jetzt)
        return f"Kommen um {timezone.localtime(b.beginn):%H:%M} gestempelt."
    if aktion not in ("pause", "gehen"):
        raise StempelFehler("Unbekannte Aktion.")
    b = gehen(benutzer, jetzt)
    um = f"{timezone.localtime(b.ende):%H:%M}"
    if aktion == "pause":
        return f"Pause ab {um} gestempelt. Danach „Pause beenden“."
    return f"Gehen um {um} gestempelt."


def _grenze(jetzt=None) -> dt.datetime:
    stunden = ArbeitszeitEinstellungen.laden().offen_hoechstens_stunden
    return (jetzt or timezone.now()) - dt.timedelta(hours=stunden)


def laufend(benutzer, jetzt=None) -> Zeitbuchung | None:
    """Die offene Buchung, zu der jetzt noch ein „Gehen“ passt."""
    return (
        benutzer.zeitbuchungen.filter(ende__isnull=True, beginn__gte=_grenze(jetzt))
        .order_by("-beginn")
        .first()
    )


def vergessen(benutzer=None, jetzt=None):
    """Offene Buchungen, die älter als die Grenze sind: Hier fehlt ein „Gehen“."""
    buchungen = Zeitbuchung.objects.filter(ende__isnull=True, beginn__lt=_grenze(jetzt))
    if benutzer is not None:
        buchungen = buchungen.filter(benutzer=benutzer)
    return buchungen.select_related("benutzer").order_by("beginn")


def kommen(benutzer, jetzt=None) -> Zeitbuchung:
    jetzt = jetzt or timezone.now()
    if laufend(benutzer, jetzt):
        raise StempelFehler("Sie sind schon eingestempelt. Bitte zuerst „Gehen“ stempeln.")
    return Zeitbuchung.objects.create(benutzer=benutzer, beginn=jetzt.replace(microsecond=0))


def gehen(benutzer, jetzt=None) -> Zeitbuchung:
    jetzt = jetzt or timezone.now()
    buchung = laufend(benutzer, jetzt)
    if buchung is None:
        raise StempelFehler(
            "Kein offenes „Kommen“. Bitte die Zeit von den Zuständigen nachtragen lassen."
        )
    buchung.ende = max(jetzt.replace(microsecond=0), buchung.beginn + dt.timedelta(minutes=1))
    buchung.save()
    return buchung


def in_pause(benutzer, jetzt=None) -> Zeitbuchung | None:
    """Nicht eingestempelt, aber heute schon gearbeitet: die letzte Buchung von heute (für
    „Pause beenden“; die Lücke bis zum nächsten Kommen zählt als Pause)."""
    jetzt = jetzt or timezone.now()
    if laufend(benutzer, jetzt):
        return None
    heute = timezone.localtime(jetzt).date()
    letzte = benutzer.zeitbuchungen.filter(ende__isnull=False).order_by("-ende").first()
    return letzte if letzte and timezone.localtime(letzte.ende).date() == heute else None


def ueberschneidung(buchung: Zeitbuchung) -> Zeitbuchung | None:
    """Eine andere Buchung derselben Person, die sich mit dieser zeitlich überschneidet."""
    ende = buchung.ende or buchung.beginn + dt.timedelta(minutes=1)
    andere = Zeitbuchung.objects.filter(benutzer_id=buchung.benutzer_id).exclude(pk=buchung.pk)
    for b in andere.filter(beginn__lt=ende):
        if (b.ende is None and b.beginn >= buchung.beginn) or (b.ende and b.ende > buchung.beginn):
            return b
    return None
