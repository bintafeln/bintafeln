"""Handbuch im Programm (ADR 0038)."""

from pathlib import Path

import pytest
from django.conf import settings
from django.urls import reverse

from apps.core import hilfe
from apps.konten import rechte, rollen

pytestmark = pytest.mark.django_db
URL = reverse("core:hilfe")


def test_jedes_kapitel_hat_eine_vorlage_und_gueltige_rechte():
    ordner = Path(settings.BASE_DIR) / "templates" / "hilfe"
    kennungen = [k.kennung for k in hilfe.KAPITEL]
    assert len(kennungen) == len(set(kennungen))
    for k in hilfe.KAPITEL:
        assert (ordner / f"{k.kennung}.html").is_file(), k.kennung
        assert set(k.rechte) <= rechte.ALLE, k.kennung
    vorlagen = {p.stem for p in ordner.glob("*.html")} - {"handbuch"}
    assert vorlagen == set(kennungen)  # keine verwaisten Kapitel


def test_admin_sieht_alles(admin_client):
    inhalt = admin_client.get(URL).content.decode()
    for k in hilfe.KAPITEL:
        assert f'id="{k.kennung}"' in inhalt
    assert "Hilfe</a>" in inhalt


def test_einlass_sieht_nur_seine_kapitel(client, admin, benutzer_mit_rolle, anmelden):
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    inhalt = client.get(URL).content.decode()
    for sichtbar in ("erste-schritte", "einlass", "scannen", "ampel", "notizen", "korrigieren"):
        assert f'id="{sichtbar}"' in inhalt, sichtbar
    for verborgen in ("mitarbeitende", "personal", "rollen", "einstellungen", "datensicherung",
                      "statistik", "import", "korrekturen"):  # fmt: skip
        assert f'id="{verborgen}"' not in inhalt, verborgen
    # Absätze innerhalb eines Kapitels folgen ebenfalls den Rechten
    assert "Korrektur beantragen" in inhalt and "selbst zurücknehmen</strong>" not in inhalt


def test_ohne_rollen_nur_grundlagen(client, admin, django_user_model):
    b = django_user_model.objects.create_user(username="neu", password="x-erfunden-123")
    client.force_login(b)
    inhalt = client.get(URL).content.decode()
    assert 'id="erste-schritte"' in inhalt and 'id="einlass"' not in inhalt
    assert client.get(URL.replace("hilfe", "hilfe")).status_code == 200


def test_nur_angemeldet(client):
    assert client.get(URL).status_code == 302


def test_bilder_im_handbuch_vorhanden_und_benutzt(admin_client):
    """Jedes Bild in ``{% hilfe_bild %}`` liegt in static/hilfe/bilder, jedes Bild dort wird
    benutzt (erzeugt von tests/e2e/test_hilfe_bilder.py)."""
    import re

    basis = Path(settings.BASE_DIR)
    ordner = basis / "static" / "hilfe" / "bilder"
    vorlagen = [*basis.glob("templates/hilfe/*.html"), *basis.glob("apps/*/templates/hilfe/*.html")]
    benutzt = {name for p in vorlagen
               for name in re.findall(r'{% hilfe_bild "([^"]+)"', p.read_text())}  # fmt: skip
    assert benutzt, "keine Bilder im Handbuch"
    assert benutzt == {p.stem for p in ordner.glob("*.png")}
    inhalt = admin_client.get(URL).content.decode()
    assert 'src="/static/hilfe/bilder/einlass-kunde.png"' in inhalt
    assert 'alt="① Ampel und Gründe lesen, ② Notizen lesen' in inhalt
    assert re.search(r'einlass-kunde\.png" alt="[^"]*" width="\d+" height="\d+" loading="lazy"',
                     inhalt)  # fmt: skip


def test_bild_fehlt_zeigt_nichts():
    from apps.core.templatetags.handbuch import hilfe_bild

    assert hilfe_bild("gibt-es-nicht", "x") == ""
