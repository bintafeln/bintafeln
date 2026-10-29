"""Bilder für das Handbuch (ADR 0038), nur mit erfundenen Daten.

Jeder Test spielt einen Ablauf im Browser durch, zeichnet Pfeile und Rahmen in Tafel-Orange ein
und nimmt den Bereich auf. Neu erzeugt werden die Bilder mit::

    BINTAFELN_HILFE_BILDER=1 .venv/bin/pytest -m e2e tests/e2e/test_hilfe_bilder.py

Ohne die Variable laufen die Abläufe nur durch (CI): Fehlt ein markiertes Element, etwa weil ein
Knopf umbenannt wurde, schlägt der Test fehl, und das Bild muss mit dem Handbuch nachgezogen
werden. Die Bilder liegen in ``static/hilfe/bilder/``; ``{% hilfe_bild %}`` zeigt sie an.
"""

import datetime as dt
import io
import os
from dataclasses import dataclass
from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import Locator, Page, expect

from apps.core.farben import STANDARDFARBE
from apps.core.models import TafelEinstellungen
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Nachricht,
    Notiz,
    Person,
    Zusatzfeld,
)

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


@pytest.fixture
def muster(admin):
    """Eine erfundene Tafel mit zwei Ausgabestellen und einem Haushalt, der heute dran ist."""
    t = TafelEinstellungen.laden()
    t.name = "Tafel Musterstadt"
    t.save()
    mitte = Ausgabestelle.objects.create(name="Ausgabestelle Mitte")
    Ausgabestelle.objects.create(name="Ausgabestelle Nord")
    gruppe = Kundengruppe.objects.create(kuerzel="A", name="Gruppe A", ausgabestelle=mitte,
                                         wochentage="Mo, Di, Mi, Do, Fr, Sa, So")  # fmt: skip
    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="00042", kundengruppe=gruppe,
                                ausweis_gueltig_bis=heute + dt.timedelta(days=150))  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster",
                          geburtsdatum=dt.date(1961, 4, 12))  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Max", nachname="Muster",
                          geburtsdatum=dt.date(2014, 9, 3))  # fmt: skip
    Notiz.objects.create(kundennummer="00042", verfasst_von="Büro",
                         text="Bringt nächste Woche den neuen Bescheid mit.")  # fmt: skip
    admin.first_name, admin.last_name = "Clara", "Beispiel"
    admin.gewaehlte_stelle = mitte
    admin.save()
    return h


def test_bild_einlass(angemeldet, admin, muster):
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("ausgabe:empfang"))
    feld = seite.get_by_label("Kundennummer scannen oder eingeben")
    aufnehmen(seite, "einlass-suche", [seite.locator(".kopf"), seite.locator(".menue-stelle"),
                                         seite.locator(".empfang-kopf")],
              Marke(seite.locator("#menue-stelle"), nummer=1, von="rechts"),
              Marke(feld, nummer=2, von="unten"))  # fmt: skip
    feld.fill("42")
    seite.get_by_role("button", name="Prüfen").click()
    knopf = seite.get_by_role("button", name="✓ Abholung eintragen")
    notiz = seite.locator("section.notizen .notiz").first
    aufnehmen(seite, "einlass-kunde", [seite.locator(".einlass-leiste"), notiz],
              Marke(seite.locator("section.ampel").first, "rahmen", 1),
              Marke(notiz, "rahmen", 2),
              Marke(knopf, nummer=3, von="oben", laenge=36))  # fmt: skip


def test_bild_neuer_haushalt(angemeldet, admin, muster):
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("kunden:haushalt_neu"))
    seite.fill("#id_hp-vorname", "Erika")
    seite.fill("#id_hp-nachname", "Beispiel")
    seite.select_option("#id_hp-gdb", "50")
    seite.get_by_label("G (erheblich gehbehindert)").first.check()
    titel = seite.get_by_role("heading", name="3. Weitere Angaben")
    abschnitt = seite.locator("section", has=titel)
    aufnehmen(seite, "haushalt-neu-behinderung", abschnitt,
              Marke(seite.locator("#id_hp-gdb"), nummer=1),
              Marke(seite.locator('[data-merkzeichen-fuer="id_hp-gdb"]'), "rahmen", 2))  # fmt: skip
    seite.fill("#id_a-0-vorname", "Max")
    seite.fill("#id_a-0-geburtsdatum", "2014-09-03")
    seite.select_option("#id_a-0-gdb", "80")
    angehoerige = seite.locator("section", has=seite.get_by_role("heading", name="4. Angehörige"))
    aufnehmen(seite, "haushalt-neu-angehoerige", angehoerige,
              Marke(seite.locator("#id_a-0-vorname"), nummer=1),
              Marke(seite.locator("#id_a-0-gdb"), nummer=2, von="rechts"))  # fmt: skip


def test_bild_ausweise_verlaengern(angemeldet, admin, muster):
    heute = timezone.localdate()
    sb = Zusatzfeld.objects.get(schluessel="schwerbehindert")
    e = KundenEinstellungen.laden()
    e.verlaengern_regel = KundenEinstellungen.Verlaengern.ALLE
    e.verlaengern_ab_alter = 60
    e.save()
    e.verlaengern_felder.set([sb])
    jung = Haushalt.objects.create(kundennummer="00057",
                                   ausweis_gueltig_bis=heute + dt.timedelta(days=20))  # fmt: skip
    Person.objects.create(haushalt=jung, ist_hauptperson=True, vorname="Jonas",
                          nachname="Probe", geburtsdatum=dt.date(1990, 2, 1))  # fmt: skip
    muster.ausweis_gueltig_bis = heute + dt.timedelta(days=20)
    muster.save()
    muster.personen.filter(vorname="Max").delete()
    stelle = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    for nummer in ("00042", "00057"):
        Nachricht.objects.create(kundennummer=nummer, anliegen="verlaengern", von="einlass",
                                 stelle=stelle)  # fmt: skip
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("kunden:verlaengern"))
    seite.locator('input[name="wahl_00057"][value="verlaengern"]').check()
    seite.fill('input[name="grund_00057"]', "Härtefall, Bescheid folgt")
    tabelle = seite.locator("table.tabelle").first
    aufnehmen(seite, "verlaengern-liste", seite.locator("section.karte").first,
              Marke(seite.locator('input[name="wahl_00042"][value="verlaengern"]'), nummer=1),
              Marke(seite.locator('input[name="wahl_00057"][value="verlaengern"]'), nummer=2),
              Marke(seite.locator('input[name="grund_00057"]'), nummer=3, von="unten"),
              Marke(seite.get_by_role("button", name="Ausgewählte ausführen"), nummer=4,
                    von="rechts"))  # fmt: skip
    expect(tabelle).to_be_visible()
    seite.get_by_role("button", name="Ausgewählte ausführen").click()
    knopf = seite.get_by_role("button", name="Nochmal prüfen").first
    erledigt = seite.locator("section", has=seite.get_by_role("heading", name="Erledigt (2)"))
    aufnehmen(seite, "verlaengern-erledigt", erledigt, Marke(knopf, nummer=1, von="rechts"))
