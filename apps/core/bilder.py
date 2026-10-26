"""Hochgeladene Bilder für die Seiten verkleinern (Hintergrund, Logo).

Fotos vom Handy haben oft 3–5 MB. Als Hintergrund lädt sie jeder Browser beim Anmelden herunter;
über die Leitung einer kleinen Installation dauert das viele Sekunden, im Mobilfunk noch länger.
Deshalb werden sie beim Hochladen auf eine sinnvolle Größe gebracht. Die Bilddaten (EXIF, z. B.
Aufnahmeort) fallen dabei weg.
"""

import io
from pathlib import Path

from django.core.files.base import ContentFile
from PIL import Image, ImageOps

HINTERGRUND_KANTE = 1920  # längste Seite in Pixel
LOGO_KANTE = 800


def verkleinern(datei, kante: int, *, transparenz: bool = False) -> ContentFile | None:
    """Neues, kleineres Bild oder None, wenn das Bild nicht lesbar ist.

    Ohne Transparenz als JPEG (Fotos), mit Transparenz als PNG (Logos mit freiem Hintergrund).
    """
    try:
        datei.seek(0)
        bild = Image.open(datei)
        bild = ImageOps.exif_transpose(bild)  # Handyfotos richtig herum
    except (OSError, ValueError, Image.DecompressionBombError):
        return None
    bild.thumbnail((kante, kante), Image.Resampling.LANCZOS)
    puffer = io.BytesIO()
    hat_alpha = bild.mode in ("RGBA", "LA") or (bild.mode == "P" and "transparency" in bild.info)
    name = Path(getattr(datei, "name", "") or "bild").stem
    if transparenz and hat_alpha:
        bild.convert("RGBA").save(puffer, "PNG", optimize=True)
        return ContentFile(puffer.getvalue(), name=f"{name}.png")
    bild.convert("RGB").save(puffer, "JPEG", quality=82, optimize=True, progressive=True)
    return ContentFile(puffer.getvalue(), name=f"{name}.jpg")


# --- Fotos in privaten Uploads (ADR 0064) ------------------------------------------------------

FORMATE = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}


def foto_verkleinern(daten: bytes, typ: str, kante: int, qualitaet: int,
                     graustufen: bool = False) -> bytes:  # fmt: skip
    """Foto nach den Einstellungen verkleinern; das Format (JPEG, PNG, WebP) bleibt, damit der
    gespeicherte Dateityp stimmt. Liefert die Originaldaten, wenn nichts zu tun ist, das Bild
    nicht lesbar ist oder das Ergebnis nicht kleiner wäre."""
    format_ = FORMATE.get(typ)
    if not format_ or (not kante and not graustufen):
        return daten
    try:
        bild = ImageOps.exif_transpose(Image.open(io.BytesIO(daten)))
        if kante:
            bild.thumbnail((kante, kante), Image.Resampling.LANCZOS)
        if graustufen:
            bild = ImageOps.grayscale(bild)
        if format_ == "WEBP" or (format_ == "JPEG" and bild.mode not in ("RGB", "L")):
            bild = bild.convert("L" if graustufen and format_ == "JPEG" else "RGB")
        puffer = io.BytesIO()
        if format_ == "PNG":
            bild.save(puffer, "PNG", optimize=True)
        else:
            bild.save(puffer, format_, quality=qualitaet, optimize=True)
    except (OSError, ValueError, Image.DecompressionBombError):
        return daten
    neu = puffer.getvalue()
    return neu if len(neu) < len(daten) else daten
