import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.konten import rollen
from tests.conftest import PASSWORT

pytestmark = pytest.mark.django_db


def test_rollen_als_gruppen_angelegt():
    assert set(Group.objects.values_list("name", flat=True)) >= set(rollen.ALLE)


def test_rollen_von(benutzer_mit_rolle, admin):
    assert rollen.rollen_von(AnonymousUser()) == set()
    assert rollen.rollen_von(admin) == set(rollen.ALLE)
    kiosk = benutzer_mit_rolle("kiosk", rollen.KIOSK)
    assert rollen.rollen_von(kiosk) == {rollen.KIOSK}
    assert rollen.hat_rolle(kiosk, rollen.KIOSK, rollen.BUERO)
    assert not rollen.hat_rolle(kiosk, rollen.ADMIN)


def test_anmelden_und_abmelden(client, admin):
    antwort = client.post(reverse("konten:anmelden"), {"username": "chefin", "password": PASSWORT})
    assert antwort.status_code == 302
    assert antwort.url == reverse("core:start")
    assert client.get(reverse("konten:anmelden")).status_code == 302  # schon angemeldet
    assert client.get(reverse("konten:abmelden")).status_code == 405  # nur POST
    client.post(reverse("konten:abmelden"))
    assert client.get("/").status_code == 302


def test_anmelden_falsches_passwort(client, admin):
    antwort = client.post(reverse("konten:anmelden"), {"username": "chefin", "password": "nein"})
    assert antwort.status_code == 200
    assert "falsch" in antwort.content.decode()


def test_anmelden_ohne_felder(client, admin):
    antwort = client.post(reverse("konten:anmelden"), {"username": "chefin"})
    assert antwort.status_code == 200


def test_weiterleitung_nur_auf_eigene_seiten(client, admin):
    daten = {"username": "chefin", "password": PASSWORT}
    antwort = client.post(reverse("konten:anmelden"), {**daten, "next": "https://boese.example"})
    assert antwort.url == reverse("core:start")
    client.post(reverse("konten:abmelden"))
    antwort = client.post(reverse("konten:anmelden"), {**daten, "next": "/einstellungen/"})
    assert antwort.url == "/einstellungen/"


def test_admin_login_nutzt_eigene_anmeldung(client, admin):
    antwort = client.get("/admin/login/?next=/admin/")
    assert antwort.status_code == 302
    assert antwort.url.startswith(reverse("konten:anmelden"))


def test_zwei_faktor_wenn_geraet_eingerichtet(client, admin):
    geraet = TOTPDevice.objects.create(user=admin, name="Handy", confirmed=True)
    url = reverse("konten:anmelden")
    ohne_code = client.post(url, {"username": "chefin", "password": PASSWORT})
    assert ohne_code.status_code == 200

    falscher_code = client.post(
        url, {"username": "chefin", "password": PASSWORT, "otp_token": "000000"}
    )
    assert falscher_code.status_code == 200

    # Nach einem Fehlversuch sperrt django-otp kurz (Schutz vor Durchprobieren).
    geraet.refresh_from_db()
    assert geraet.throttling_failure_count == 1
    geraet.throttle_reset()

    totp = TOTP(geraet.bin_key, geraet.step, geraet.t0, geraet.digits, geraet.drift)
    code = f"{totp.token():0{geraet.digits}d}"
    antwort = client.post(url, {"username": "chefin", "password": PASSWORT, "otp_token": code})
    assert antwort.status_code == 302
    assert client.session.get("otp_device_id")
