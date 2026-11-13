"""Eigene Unterschrift für Zuwendungsbestätigungen hinterlegen (ADR 0130), dazu der Stempel der
Tafel (ADR 0137).

Das hochgeladene Bild wird geprüft, der weiße Hintergrund durchsichtig gemacht (damit es keinen
Text der Bestätigung verdeckt) und als PNG in handlicher Größe verschlüsselt abgelegt. Es gibt
hier bewusst keine Funktion, die die Unterschrift eines anderen Kontos liefert."""

import io

from PIL import Image, ImageChops, UnidentifiedImageError

from apps.core import privatdateien
from apps.spenden.models import SpendenEinstellungen, Unterschrift

MAX_MB = 3
MAX_BREITE = 1200
WEISS = 235  # ab dieser Helligkeit ganz durchsichtig …
FARBE = 175  # … bis hierhin ganz deckend, dazwischen weicher Übergang (glatte Ränder)


class BildFehler(ValueError):
    pass


def freistellen(bild: Image.Image) -> Image.Image:
    """Weißes Papier und hellen Hintergrund durchsichtig machen; Tinte bleibt, wie sie ist."""
    bild = bild.convert("RGBA")
    hell = bild.convert("L")
    deckend = hell.point(
        lambda v: 0 if v >= WEISS else 255 if v <= FARBE else (WEISS - v) * 255 // (WEISS - FARBE)
    )
    bild.putalpha(ImageChops.multiply(bild.getchannel("A"), deckend))
    return bild


def aufbereiten(datei, was="der Unterschrift") -> bytes:
    """Hochgeladenes Bild (PNG, JPG, WebP) als PNG mit höchstens ``MAX_BREITE`` Pixeln Breite und
    durchsichtigem Hintergrund."""
    if datei.size > MAX_MB * 1024 * 1024:
        raise BildFehler(f"Das Bild darf höchstens {MAX_MB} MB groß sein.")
    try:
        bild = Image.open(datei)
        bild.load()
    except (UnidentifiedImageError, OSError, ValueError) as fehler:
        raise BildFehler(f"Bitte ein Bild {was} hochladen (PNG oder JPG).") from fehler
    if bild.format not in ("PNG", "JPEG", "WEBP"):
        raise BildFehler(f"Bitte ein Bild {was} hochladen (PNG oder JPG).")
    bild = freistellen(bild)
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


# --- Stempel der Tafel ---------------------------------------------------------------------------


def stempel_speichern(datei) -> None:
    """Der Stempel der Tafel; ein neues Bild ersetzt das alte."""
    e = SpendenEinstellungen.laden()
    alt = e.stempel
    e.stempel = privatdateien.ablegen(
        SpendenEinstellungen.ORDNER, aufbereiten(datei, "des Stempels")
    )
    e.save(update_fields=["stempel"])
    privatdateien.loeschen(SpendenEinstellungen.ORDNER, alt)


def stempel_loeschen() -> None:
    e = SpendenEinstellungen.laden()
    privatdateien.loeschen(SpendenEinstellungen.ORDNER, e.stempel)
    e.stempel = ""
    e.save(update_fields=["stempel"])


def stempel() -> bytes | None:
    e = SpendenEinstellungen.laden()
    return privatdateien.lesen(SpendenEinstellungen.ORDNER, e.stempel) if e.stempel else None
