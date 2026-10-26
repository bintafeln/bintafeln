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
