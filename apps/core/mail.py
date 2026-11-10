"""Mails über den in bintafeln eingerichteten Mailserver senden (ADR 0016)."""

import smtplib
import socket
import ssl

from django.core.mail import EmailMultiAlternatives, get_connection

from apps.core import geheimnis
from apps.core.models import MailEinstellungen


class MailFehler(Exception):
    """Senden war nicht möglich. Der Text ist für Menschen ohne Technikwissen gedacht."""


def eingerichtet() -> bool:
    return MailEinstellungen.laden().eingerichtet


def _verstaendlich(fehler: Exception) -> str:
    if isinstance(fehler, smtplib.SMTPAuthenticationError):
        return "Anmeldung am Mailserver fehlgeschlagen. Benutzername und Passwort prüfen."
    if isinstance(fehler, smtplib.SMTPRecipientsRefused):
        return "Der Mailserver hat die Empfängeradresse abgelehnt."
    if isinstance(fehler, ssl.SSLError):
        return "Verschlüsselung passt nicht zum Server. Port und Verschlüsselung prüfen."
    if isinstance(fehler, (socket.gaierror, ConnectionError, TimeoutError, socket.timeout)):
        return "Mailserver nicht erreichbar. Adresse und Port prüfen."
    if isinstance(fehler, OSError) and fehler.strerror:
        return (
            f"Verbindung zum Mailserver fehlgeschlagen ({fehler.strerror}). Adresse, Port und "
            "Verschlüsselung prüfen."
        )
    return f"Senden fehlgeschlagen ({type(fehler).__name__}: {fehler})."


def _verbindung(e: MailEinstellungen):
    if not e.eingerichtet:
        raise MailFehler("Es ist kein Mailserver eingerichtet.")
    passwort = geheimnis.entschluesseln(e.passwort_verschluesselt)
    if passwort is None:
        raise MailFehler(
            "Das gespeicherte Passwort des Mailservers ist nicht mehr lesbar (der geheime "
            "Schlüssel der Installation wurde geändert). Bitte neu eingeben."
        )
    return get_connection(
        host=e.server,
        port=e.port,
        username=e.benutzer,
        password=passwort,
        use_tls=e.verschluesselung == MailEinstellungen.Verschluesselung.STARTTLS,
        use_ssl=e.verschluesselung == MailEinstellungen.Verschluesselung.SSL,
        timeout=20,
    )


def verbindung_pruefen() -> None:
    """Verbindet sich mit dem Mailserver und meldet sich an, ohne eine Mail zu senden."""
    verbindung = _verbindung(MailEinstellungen.laden())
    try:
        verbindung.open()
    except (smtplib.SMTPException, OSError) as fehler:
        raise MailFehler(_verstaendlich(fehler)) from fehler
    finally:
        verbindung.close()


# Wofür eine Mail gesendet wurde – im Archiv „Gesendete Mails“ zum Filtern (ADR 0124)
ARTEN = {
    "zugang": "Zugang und Passwort",
    "benachrichtigung": "Benachrichtigung",
    "antrag": "Antrag",
    "warteliste": "Warteliste",
    "spenden": "Spenden",
    "serienbrief": "Serienbrief",
    "aufruf": "Aufruf",
    "export": "Listen-Export",
    "test": "Testmail",
}
OHNE_INHALT = "(Inhalt nicht gespeichert: Die Mail enthält Zugangsdaten.)"


def _archivieren(betreff, text, an, anhaenge, art, vertraulich, fehler="") -> None:
    """Hält die Mail im Archiv fest, wenn die Tafel eines führt: Anhänge nur mit Name und
    Größe, Mails mit Zugangsdaten ohne Inhalt."""
    from apps.core.models import GesendeteMail

    if not MailEinstellungen.laden().archiv_tage:
        return
    GesendeteMail.objects.create(
        an=", ".join(an), betreff=betreff[:300], art=art if art in ARTEN else "",
        text="" if vertraulich else text, vertraulich=vertraulich, fehler=fehler[:300],
        anhaenge=[{"name": name, "groesse": len(inhalt), "typ": typ}
                  for name, inhalt, typ in anhaenge],
    )  # fmt: skip


def fristen_anwenden(jetzt=None) -> int:
    """Löscht archivierte Mails, die älter als die eingestellte Frist sind (ADR 0124)."""
    import datetime as dt

    from django.utils import timezone

    from apps.core.models import GesendeteMail

    tage = MailEinstellungen.laden().archiv_tage
    grenze = (jetzt or timezone.now()) - dt.timedelta(days=tage)
    return GesendeteMail.objects.filter(gesendet_am__lt=grenze).delete()[0]


def senden(betreff: str, text: str, an: list[str], html: str | None = None,
           anhaenge=(), art: str = "", vertraulich: bool = False) -> None:  # fmt: skip
    """Sendet ``text``; mit ``html`` zusätzlich eine gestaltete Fassung (Mailprogramme wählen).

    ``anhaenge`` = [(Dateiname, Inhalt, Medientyp)], z. B. ein PDF. ``art`` (Schlüssel aus
    ``ARTEN``) ordnet die Mail im Archiv ein; ``vertraulich`` bei Zugangsdaten (Link zum
    Passwort): Dann steht sie ohne Inhalt im Archiv. Auch ein Fehlschlag wird festgehalten.
    """
    anhaenge = list(anhaenge)
    e = MailEinstellungen.laden()
    try:
        verbindung = _verbindung(e)
    except MailFehler as fehler:
        _archivieren(betreff, text, an, anhaenge, art, vertraulich, str(fehler))
        raise
    nachricht = EmailMultiAlternatives(betreff, text, e.absenderadresse, an, connection=verbindung)
    if html:
        nachricht.attach_alternative(html, "text/html")
    for name, inhalt, typ in anhaenge:
        nachricht.attach(name, inhalt, typ)
    try:
        nachricht.send()
    except (smtplib.SMTPException, OSError) as fehler:
        verstaendlich = _verstaendlich(fehler)
        _archivieren(betreff, text, an, anhaenge, art, vertraulich, verstaendlich)
        raise MailFehler(verstaendlich) from fehler
    _archivieren(betreff, text, an, anhaenge, art, vertraulich)
