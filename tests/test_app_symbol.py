"""App-Symbol (Browser-Tab, Startbildschirm) und Web-App-Manifest; Bilder werden erzeugt."""

import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from PIL import Image

from apps.core.models import TafelEinstellungen

pytestmark = pytest.mark.django_db


def png(breite, hoehe, farbe=(0, 128, 0)):
    puffer = io.BytesIO()
    Image.new("RGB", (breite, hoehe), farbe).save(puffer, "PNG")
    return SimpleUploadedFile("symbol.png", puffer.getvalue(), content_type="image/png")


def test_ohne_eigenes_symbol_das_von_bintafeln(admin):
    c = Client()  # auch ohne Anmeldung, die Anmeldeseite zeigt es schon
    antwort = c.get(reverse("core:app_symbol", args=[192]))
    assert antwort.status_code == 302 and antwort.url.endswith("img/bintafeln-192.png")
    assert c.get(reverse("core:app_symbol", args=[64])).status_code == 404
    manifest = c.get(reverse("core:manifest")).json()
    assert manifest["name"] == "bintafeln" and manifest["display"] == "standalone"
    assert [i["sizes"] for i in manifest["icons"]] == ["192x192", "512x512"]
    seite = c.get(reverse("konten:anmelden")).content.decode()
    assert 'rel="apple-touch-icon"' in seite and reverse("core:manifest") in seite


def test_eigenes_symbol_hochladen(admin_client, tmp_path, settings):
    settings.MEDIA_ROOT = tmp_path
    antwort = admin_client.post(reverse("core:einstellungen"), {
        "name": "Tafel Musterstadt", "farbe": "#e5007d", "hintergrund_staerke": 15,
        "app_symbol": png(800, 400),
    })  # fmt: skip
    assert antwort.status_code == 302
    tafel = TafelEinstellungen.laden()
    with tafel.app_symbol.open("rb") as d:
        assert Image.open(d).size == (512, 512)  # quadratisch, Bild mittig
    gross = Client().get(reverse("core:app_symbol", args=[512]))
    assert gross.status_code == 200 and gross["Content-Type"] == "image/png"
    apple = Image.open(io.BytesIO(Client().get(reverse("core:app_symbol", args=[180])).content))
    assert apple.size == (180, 180) and apple.mode == "RGB"  # weißer statt durchsichtiger Rand
    assert apple.getpixel((0, 0)) == (255, 255, 255)
    manifest = Client().get(reverse("core:manifest")).json()
    assert manifest["name"] == "Tafel Musterstadt" and manifest["theme_color"] == "#e5007d"
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert "?v=oeffentlich/app/" in seite  # neue Adresse nach dem Hochladen


def test_unlesbares_bild_wird_abgelehnt(admin_client):
    kaputt = SimpleUploadedFile("symbol.png", b"kein Bild", content_type="image/png")
    antwort = admin_client.post(reverse("core:einstellungen"), {
        "name": "Tafel", "farbe": "#e5007d", "hintergrund_staerke": 15, "app_symbol": kaputt,
    })  # fmt: skip
    assert antwort.status_code == 200 and not TafelEinstellungen.laden().app_symbol
