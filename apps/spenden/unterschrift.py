"""Eigene Unterschrift für Zuwendungsbestätigungen hinterlegen (ADR 0130).

Das hochgeladene Bild wird geprüft und als PNG in handlicher Größe verschlüsselt abgelegt. Es
gibt hier bewusst keine Funktion, die die Unterschrift eines anderen Kontos liefert."""

import io

from PIL import Image, UnidentifiedImageError

from apps.core import privatdateien
from apps.spenden.models import Unterschrift

MAX_MB = 3
MAX_BREITE = 1200


class BildFehler(ValueError):
    pass


def aufbereiten(datei) -> bytes:
    """Hochgeladenes Bild (PNG, JPG, WebP) als PNG mit höchstens ``MAX_BREITE`` Pixeln Breite."""
    if datei.size > MAX_MB * 1024 * 1024:
        raise BildFehler(f"Das Bild darf höchstens {MAX_MB} MB groß sein.")
    try:
        bild = Image.open(datei)
        bild.load()
    except (UnidentifiedImageError, OSError, ValueError) as fehler:
        raise BildFehler("Bitte ein Bild der Unterschrift hochladen (PNG oder JPG).") from fehler
    if bild.format not in ("PNG", "JPEG", "WEBP"):
        raise BildFehler("Bitte ein Bild der Unterschrift hochladen (PNG oder JPG).")
    bild = bild.convert("RGBA" if "A" in bild.getbands() or "transparency" in bild.info else "RGB")
    if bild.width > MAX_BREITE:
        bild = bild.resize((MAX_BREITE, max(1, round(bild.height * MAX_BREITE / bild.width))))
    puffer = io.BytesIO()
    bild.save(puffer, "PNG")
    return puffer.getvalue()


def speichern(benutzer, name_funktion: str, datei=None) -> Unterschrift:
    """Legt die eigene Unterschrift an oder ändert sie; ein neues Bild ersetzt das alte."""
    u = Unterschrift.objects.filter(benutzer=benutzer).first() or Unterschrift(benutzer=benutzer)
    u.name_funktion = name_funktion
    if datei is not None:
        alt = u.bild
        u.bild = privatdateien.ablegen(Unterschrift.ORDNER, aufbereiten(datei))
        privatdateien.loeschen(Unterschrift.ORDNER, alt)
    u.save()
    return u


def loeschen(benutzer) -> None:
    """Entfernt die eigene Unterschrift endgültig (nicht in den Papierkorb: Niemand soll sie
    wiederherstellen können). Schon unterschriebene Bestätigungen bleiben, wie sie sind."""
    for u in Unterschrift.objects.filter(benutzer=benutzer):
        privatdateien.loeschen(Unterschrift.ORDNER, u.bild)
        u.delete()


def bild(benutzer) -> bytes | None:
    u = Unterschrift.objects.filter(benutzer=benutzer).first()
    return privatdateien.lesen(Unterschrift.ORDNER, u.bild) if u else None
