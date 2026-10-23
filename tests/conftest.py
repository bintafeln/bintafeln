import pytest
from django.contrib.auth.models import Group

from apps.konten import rollen

PASSWORT = "Sicher-genug-123"


@pytest.fixture(autouse=True)
def medien_verzeichnis(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture
def benutzer_mit_rolle(django_user_model):
    def anlegen(name, *rollennamen):
        benutzer = django_user_model.objects.create_user(username=name, password=PASSWORT)
        for rolle in rollennamen:
            benutzer.groups.add(Group.objects.get(name=rolle))
        return benutzer

    return anlegen


@pytest.fixture
def admin(django_user_model):
    benutzer = django_user_model.objects.create_superuser(username="chefin", password=PASSWORT)
    benutzer.groups.add(Group.objects.get(name=rollen.ADMIN))
    return benutzer


@pytest.fixture
def admin_client(client, admin):
    client.force_login(admin)
    return client
