import pytest
from django.urls import reverse

from bintafeln import version as version_modul


@pytest.fixture
def datei(tmp_path, monkeypatch):
    pfad = tmp_path / "VERSION"
    monkeypatch.setattr(version_modul, "DATEI", pfad)
    version_modul.version.cache_clear()
    yield pfad
    version_modul.version.cache_clear()


def test_version_aus_datei(datei):
    assert version_modul.version() == "Entwicklungsstand"
    version_modul.version.cache_clear()
    datei.write_text("2026.10.3\n")
    assert version_modul.version() == "2026.10.3"
    version_modul.version.cache_clear()
    datei.write_text("")
    assert version_modul.version() == "unbekannt"


@pytest.mark.django_db
def test_nur_admins_sehen_version(datei, client, admin_client, benutzer_mit_rolle, anmelden):
    datei.write_text("2026.10.3")
    assert "Version 2026.10.3" in admin_client.get(reverse("core:start")).content.decode()
    admin_client.logout()
    anmelden(client, benutzer_mit_rolle("kim", "Ausgabe"))
    assert "Version 2026" not in client.get(reverse("core:start")).content.decode()
