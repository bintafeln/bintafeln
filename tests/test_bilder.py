"""Hochgeladene Bilder werden verkleinert, damit die Anmeldung schnell lädt."""

import io
from importlib import import_module

import pytest
from django.apps import apps
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.core import bilder
from apps.core.models import TafelEinstellungen

pytestmark = pytest.mark.django_db


def foto(breite=4000, hoehe=3000, art="JPEG", modus="RGB") -> bytes:
    """Großes, schlecht komprimierbares Bild (Rauschen) wie ein Handyfoto."""
    bild = Image.effect_noise((breite, hoehe), 40).convert(modus)
    puffer = io.BytesIO()
    bild.save(puffer, art, quality=90)
    return puffer.getvalue()


def test_verkleinern():
    neu = bilder.verkleinern(io.BytesIO(foto(3000, 2000)), 1920)
    bild = Image.open(io.BytesIO(neu.read()))
    assert bild.size == (1920, 1280) and bild.format == "JPEG"
    logo = bilder.verkleinern(io.BytesIO(foto(1200, 600, "PNG", "RGBA")), 800, transparenz=True)
    assert logo.name.endswith(".png") and Image.open(io.BytesIO(logo.read())).size == (800, 400)
    assert bilder.verkleinern(io.BytesIO(b"kein Bild"), 100) is None


def test_hochladen_verkleinert(admin_client):
    gross = foto(3200, 2400)
    datei = SimpleUploadedFile("urlaub.jpg", gross, content_type="image/jpeg")
    admin_client.post(reverse("core:einstellungen"), {"name": "X", "hintergrund_anmeldung": datei,
                                                      "hintergrund_staerke": "20"})  # fmt: skip
    t = TafelEinstellungen.laden()
    assert t.hintergrund_anmeldung.name.endswith(".jpg")
    assert t.hintergrund_anmeldung.size < len(gross) / 2
    assert Image.open(t.hintergrund_anmeldung.path).size == (1920, 1440)


def test_migration_verkleinert_vorhandene():
    t = TafelEinstellungen.laden()
    gross = foto(2600, 1950)
    t.hintergrund.save("alt.jpg", ContentFile(gross), save=True)
    alt = t.hintergrund.name
    t.logo.save("logo.png", ContentFile(foto(300, 100, "PNG")), save=True)  # klein: bleibt
    logo = t.logo.name
    import_module("apps.core.migrations.0014_bilder_verkleinern").verkleinern(apps, None)
    t.refresh_from_db()
    assert t.hintergrund.name != alt and t.hintergrund.size < len(gross) / 2
    assert default_storage.exists(alt)  # Original bleibt erhalten
    assert t.logo.name == logo
