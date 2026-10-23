import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from apps.core.models import TafelEinstellungen

pytestmark = pytest.mark.django_db

DATEN = {
    "tafel_name": "Beispiel-Tafel",
    "username": "erste",
    "email": "erste@example.org",
    "password1": "Sicher-genug-123",
    "password2": "Sicher-genug-123",
}


def test_ohne_admin_wird_zur_einrichtung_umgeleitet(client):
    antwort = client.get("/")
    assert antwort.status_code == 302
    assert antwort.url == reverse("core:einrichtung")


def test_healthz_und_static_bleiben_frei(client):
    assert client.get("/healthz/").status_code == 200


def test_einrichtung_legt_admin_und_tafelnamen_an(client):
    antwort = client.post(reverse("core:einrichtung"), DATEN)
    assert antwort.status_code == 302
    admin = get_user_model().objects.get(username="erste")
    assert admin.is_superuser
    assert admin.groups.filter(name="Admin").exists()
    assert TafelEinstellungen.laden().name == "Beispiel-Tafel"
    # direkt angemeldet
    assert client.get("/").status_code == 200


def test_einrichtung_nach_admin_gesperrt(admin_client, client):
    assert client.get(reverse("core:einrichtung")).status_code == 404
    assert client.post(reverse("core:einrichtung"), DATEN).status_code == 404
    assert get_user_model().objects.filter(username="erste").count() == 0


def test_einrichtung_prueft_passwoerter(client):
    falsch = {**DATEN, "password2": "anders-anders-123"}
    antwort = client.post(reverse("core:einrichtung"), falsch)
    assert antwort.status_code == 200
    assert "stimmen nicht überein" in antwort.content.decode()

    schwach = {**DATEN, "password1": "123", "password2": "123"}
    antwort = client.post(reverse("core:einrichtung"), schwach)
    assert antwort.status_code == 200
    assert not get_user_model().objects.exists()


def test_einrichtung_benutzername_vergeben(client, django_user_model):
    django_user_model.objects.create_user(username="Erste", password="x")
    antwort = client.post(reverse("core:einrichtung"), DATEN)
    assert "bereits vergeben" in antwort.content.decode()


def test_zweiter_check_in_transaktion(client, monkeypatch):
    """Legt ein paralleler Request zwischen Formularprüfung und Sperre einen Admin an,
    bricht die Einrichtung ab."""
    from apps.core import views

    aufrufe = iter([False, True])
    monkeypatch.setattr(views, "admin_existiert", lambda: next(aufrufe))
    antwort = client.post(reverse("core:einrichtung"), DATEN)
    assert antwort.status_code == 404
    assert not get_user_model().objects.filter(username="erste").exists()
