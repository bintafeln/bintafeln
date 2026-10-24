"""Verschlüsselt gespeicherte Geheimnisse, z. B. das Passwort des Mailservers (ADR 0016).

Der Schlüssel wird aus DJANGO_SECRET_KEY (in .env) abgeleitet. Wer nur die Datenbank oder eine
Sicherung hat, kann die Geheimnisse deshalb nicht lesen. Wird DJANGO_SECRET_KEY geändert, lassen
sie sich nicht mehr entschlüsseln und müssen neu eingegeben werden.
"""

import base64

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings

ZWECK = b"bintafeln-geheimnisse-v1"


def _fernet() -> Fernet:
    schluessel = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=ZWECK).derive(
        settings.SECRET_KEY.encode()
    )
    return Fernet(base64.urlsafe_b64encode(schluessel))


def verschluesseln(klartext: str) -> str:
    return _fernet().encrypt(klartext.encode()).decode() if klartext else ""


def bytes_verschluesseln(daten: bytes) -> bytes:
    """Für Dateien, z. B. eine Führerschein-Kopie."""
    return _fernet().encrypt(daten)


def bytes_entschluesseln(daten: bytes) -> bytes | None:
    try:
        return _fernet().decrypt(daten)
    except InvalidToken:
        return None


def entschluesseln(geheimtext: str) -> str | None:
    """Klartext, leerer Text wenn nichts gespeichert ist, None wenn nicht lesbar."""
    if not geheimtext:
        return ""
    try:
        return _fernet().decrypt(geheimtext.encode()).decode()
    except InvalidToken:
        return None
