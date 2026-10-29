"""Werkzeug für die Bilder im Handbuch (ADR 0038), benutzt von ``test_hilfe_bilder*.py``.

Ein Test spielt einen Ablauf mit erfundenen Daten (Fixture ``muster`` in ``conftest.py``) im
Browser durch und ruft ``aufnehmen()`` mit dem Bereich und den Marken auf: nummerierte Pfeile
oder Rahmen in Tafel-Orange. Neu erzeugt werden die Bilder mit::

    BINTAFELN_HILFE_BILDER=1 .venv/bin/pytest -m e2e tests/e2e -k hilfe_bild

Ohne die Variable laufen die Abläufe nur durch (CI): Fehlt ein markiertes Element, etwa weil ein
Knopf umbenannt wurde, schlägt der Test fehl, und das Bild muss mit dem Handbuch nachgezogen
werden. Die Bilder liegen in ``static/hilfe/bilder/``; ``{% hilfe_bild %}`` zeigt sie an.
"""

import io
import os
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from playwright.sync_api import Locator, Page, expect

from apps.core.farben import STANDARDFARBE

ORDNER = Path(settings.BASE_DIR) / "static" / "hilfe" / "bilder"
SPEICHERN = bool(os.environ.get("BINTAFELN_HILFE_BILDER"))
BREITE, HOEHE = 1200, 860


@dataclass
class Marke:
    ziel: Locator
    art: str = "pfeil"  # „pfeil“ zeigt auf das Element, „rahmen“ umrandet es
    nummer: int | None = None  # ①, ② … wie im Text des Handbuchs
    von: str = "links"  # woher der Pfeil kommt: links, rechts, oben, unten
    laenge: int = 80  # Länge des Pfeils in Pixeln


# Zeichnet Pfeile und Rahmen über die Seite
ZEICHNEN = (Path(__file__).parent / "hilfe_marken.js").read_text().split("\n", 2)[2]


def _box(seite: Page, ziel: Locator) -> dict:
    expect(ziel).to_be_visible()
    box = ziel.bounding_box()
    assert box, ziel
    scroll = seite.evaluate("() => [window.scrollX, window.scrollY]")
    return {**box, "x": box["x"] + scroll[0], "y": box["y"] + scroll[1]}


def aufnehmen(seite: Page, name: str, bereich: Locator | list[Locator], *marken: Marke,
              rand: int = 24):  # fmt: skip
    """Zeichnet die Marken ein und nimmt ``bereich`` (bei mehreren: alles von oben links bis
    unten rechts) samt Marken auf (PNG, 256 Farben)."""
    felder = [_box(seite, b) for b in (bereich if isinstance(bereich, list) else [bereich])]
    links, oben = min(f["x"] for f in felder), min(f["y"] for f in felder)
    feld = {"x": links, "y": oben,
            "width": max(f["x"] + f["width"] for f in felder) - links,
            "height": max(f["y"] + f["height"] for f in felder) - oben}  # fmt: skip
    boxen = [{"box": _box(seite, m.ziel), "art": m.art, "nummer": m.nummer, "von": m.von,
              "laenge": m.laenge} for m in marken]  # fmt: skip
    seite.evaluate("() => document.activeElement && document.activeElement.blur()")
    seite.evaluate(ZEICHNEN, [boxen, STANDARDFARBE])
    links, oben = feld["x"], feld["y"]
    rechts, unten = links + feld["width"], oben + feld["height"]
    for m in boxen:  # Pfeile ragen über das Element hinaus
        b, weit = m["box"], m["laenge"] + 45 if m["art"] == "pfeil" else 30
        links, oben = min(links, b["x"] - weit), min(oben, b["y"] - weit)
        rechts = max(rechts, b["x"] + b["width"] + weit)
        unten = max(unten, b["y"] + b["height"] + weit)
    breite = seite.evaluate("() => document.documentElement.scrollWidth")
    links, oben = max(0, links - rand), max(0, oben - rand)
    clip = {"x": links, "y": oben, "width": min(breite, rechts + rand) - links,
            "height": unten + rand - oben}  # fmt: skip
    png = seite.screenshot(clip=clip, full_page=True, animations="disabled", caret="hide")
    seite.evaluate("() => document.getElementById('hilfe-marken').remove()")
    if not SPEICHERN:
        return
    from PIL import Image

    bild = Image.open(io.BytesIO(png)).convert("RGB")
    bild = bild.quantize(colors=256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
    ORDNER.mkdir(parents=True, exist_ok=True)
    bild.save(ORDNER / f"{name}.png", optimize=True)


def oeffnen(angemeldet, benutzer, url: str, breite: int = BREITE, hoehe: int = HOEHE) -> Page:
    """Meldet ``benutzer`` an und öffnet ``url`` in der Größe für die Bilder."""
    seite = angemeldet(benutzer)
    seite.set_viewport_size({"width": breite, "height": hoehe})
    seite.goto(url)
    return seite
