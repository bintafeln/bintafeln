"""Mails über den in bintafeln eingerichteten Mailserver senden (ADR 0016)."""

import smtplib
import socket
import ssl

from django.core.mail import EmailMessage, get_connection

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


def senden(betreff: str, text: str, an: list[str]) -> None:
    e = MailEinstellungen.laden()
    verbindung = _verbindung(e)
    try:
        EmailMessage(betreff, text, e.absenderadresse, an, connection=verbindung).send()
    except (smtplib.SMTPException, OSError) as fehler:
        raise MailFehler(_verstaendlich(fehler)) from fehler
