"""Verschlüsselt abgelegte, nie öffentlich ausgelieferte Dateien (ADR 0017).

Die Dateien liegen unter MEDIA_ROOT/privat/<ordner>/ und werden mit dem Schlüssel aus
apps.core.geheimnis verschlüsselt. Ausgeliefert werden sie nur über Ansichten mit
Rechteprüfung, die jeden Abruf protokollieren.
"""

import uuid
from pathlib import Path

from django.conf import settings

from apps.core import geheimnis

FOTO_ODER_PDF = {"image/jpeg", "image/png", "image/webp", "application/pdf"}


class DateiFehler(ValueError):
    pass


def pfad(ordner: str, name: str) -> Path:
    return Path(settings.MEDIA_ROOT) / "privat" / ordner / name


def speichern(ordner: str, datei, *, typen=FOTO_ODER_PDF, max_mb=5) -> str:
    """Prüft und speichert eine hochgeladene Datei verschlüsselt; liefert den Dateinamen."""
    if datei.content_type not in typen:
        raise DateiFehler("Bitte ein Foto (JPG, PNG, WebP) oder ein PDF hochladen.")
    if datei.size > max_mb * 1024 * 1024:
        raise DateiFehler(f"Die Datei darf höchstens {max_mb} MB groß sein.")
    name = f"{uuid.uuid4().hex}.bin"
    ziel = pfad(ordner, name)
    ziel.parent.mkdir(parents=True, exist_ok=True)
    ziel.write_bytes(geheimnis.bytes_verschluesseln(datei.read()))
    return name


def lesen(ordner: str, name: str) -> bytes | None:
    """Entschlüsselter Inhalt oder None, wenn nicht vorhanden oder nicht mehr lesbar."""
    if not name:
        return None
    datei = pfad(ordner, name)
    return geheimnis.bytes_entschluesseln(datei.read_bytes()) if datei.exists() else None


def loeschen(ordner: str, name: str) -> None:
    if name:
        pfad(ordner, name).unlink(missing_ok=True)
