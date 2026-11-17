"""Termin der Warteliste als Kalendereintrag (iCalendar, RFC 5545) für den eigenen Kalender.

Die Datei enthält nur, was man für den Kalender braucht: Tag und Uhrzeit, Ort, Anmerkung und die
Zahl der Eingeladenen – keine Namen und keine anderen Angaben zu den Antragstellern.
"""

import datetime as dt

from django.utils import timezone

from apps.warteliste.models import Wartestand

DAUER_OHNE_ENDE = dt.timedelta(hours=1)
S = Wartestand.Status


def erwartet(termin) -> int:
    """Wie viele zu diesem Termin eingeladen sind und (noch) kommen sollen."""
    return termin.wartende.exclude(status__in=[S.ENTSCHULDIGT, S.GESTRICHEN]).count()


def _text(wert: str) -> str:
    """Text nach RFC 5545 maskieren."""
    wert = wert.replace("\\", "\\\\").replace(";", r"\;").replace(",", "\\,")
    return wert.replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def _zeile(zeile: str) -> str:
    """Lange Zeilen umbrechen: höchstens 75 Bytes, Folgezeilen beginnen mit einem Leerzeichen."""
    teile, rest = [], zeile.encode()
    grenze = 75
    while len(rest) > grenze:
        schnitt = grenze
        while rest[schnitt] & 0xC0 == 0x80:  # nicht mitten in einem Zeichen trennen
            schnitt -= 1
        teile.append(rest[:schnitt].decode())
        rest = rest[schnitt:]
        grenze = 74
    teile.append(rest.decode())
    return "\r\n ".join(teile)


def _utc(datum: dt.date, zeit: dt.time) -> dt.datetime:
    lokal = timezone.make_aware(dt.datetime.combine(datum, zeit))
    return lokal.astimezone(dt.UTC)


def ics(termin, ort: str, host: str, adresse: str = "") -> str:
    """Der Termin als .ics-Text. ``host`` für die eindeutige Kennung, ``adresse`` der Link zur
    Terminseite in bintafeln."""
    anzahl = erwartet(termin)
    beginn = _utc(termin.datum, termin.von)
    ende = _utc(termin.datum, termin.bis) if termin.bis else beginn + DAUER_OHNE_ENDE
    if ende <= beginn:
        ende = beginn + DAUER_OHNE_ENDE
    personen = "1 Eingeladene/r" if anzahl == 1 else f"{anzahl} Eingeladene"
    beschreibung = [f"Neuanmeldung: {personen}."]
    if termin.anmerkung:
        beschreibung.append(termin.anmerkung)
    if adresse:
        beschreibung.append(adresse)
    fmt = "%Y%m%dT%H%M%SZ"
    zeilen = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//bintafeln//Warteliste//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "BEGIN:VEVENT",
        f"UID:warteliste-termin-{termin.pk}@{host}",
        f"DTSTAMP:{timezone.now().astimezone(dt.UTC):{fmt}}",
        f"DTSTART:{beginn:{fmt}}",
        f"DTEND:{ende:{fmt}}",
        f"SUMMARY:{_text(f'Neuanmeldung ({personen})')}",
        f"LOCATION:{_text(', '.join(z.strip() for z in ort.splitlines() if z.strip()))}",
        f"DESCRIPTION:{_text(chr(10).join(beschreibung))}",
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(_zeile(z) for z in zeilen) + "\r\n"
