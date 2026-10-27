import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.konten import rollen
from tests.conftest import PASSWORT

pytestmark = pytest.mark.django_db


def test_rollen_als_gruppen_angelegt():
    assert set(Group.objects.values_list("name", flat=True)) >= set(rollen.MITGELIEFERT)
    assert {r.name for r in rollen.alle_rollen()} >= set(rollen.MITGELIEFERT)


def test_rollen_von(benutzer_mit_rolle, admin):
    assert rollen.rollen_von(AnonymousUser()) == set()
    assert rollen.rollen_von(admin) == {rollen.ADMIN}
    kiosk = benutzer_mit_rolle("kiosk", rollen.KIOSK)
    assert rollen.rollen_von(kiosk) == {rollen.KIOSK}
    assert not rollen.ist_admin(kiosk) and rollen.ist_admin(admin)


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
    url, code_url = reverse("konten:anmelden"), reverse("konten:anmelden_code")
    ohne_code = client.post(url, {"username": "chefin", "password": PASSWORT, "next": "/kunden/"})
    assert ohne_code.url == code_url and "_auth_user_id" not in client.session

    falscher_code = client.post(code_url, {"otp_token": "000000"})
    assert falscher_code.status_code == 200

    # Nach einem Fehlversuch sperrt django-otp kurz (Schutz vor Durchprobieren).
    geraet.refresh_from_db()
    assert geraet.throttling_failure_count == 1
    geraet.throttle_reset()

    totp = TOTP(geraet.bin_key, geraet.step, geraet.t0, geraet.digits, geraet.drift)
    code = f"{totp.token():0{geraet.digits}d}"
    antwort = client.post(code_url, {"otp_token": code})
    assert antwort.status_code == 302 and antwort.url == "/kunden/"
    assert client.session.get("otp_device_id")


def test_startseite_zeigt_eigene_rollen(client, benutzer_mit_rolle, admin, anmelden):
    anmelden(client, admin)
    inhalt = client.get(reverse("core:start")).content.decode()
    assert '<span class="marke-rolle">Admin</span>' in inhalt
    client.post(reverse("konten:abmelden"))

    anmelden(client, benutzer_mit_rolle("zwei", rollen.KIOSK, rollen.AUSGABE))
    inhalt = client.get(reverse("core:start")).content.decode()
    # in der festen Reihenfolge der Rollen
    assert inhalt.index(">Ausgabe<") < inhalt.index(">Kiosk<")
    assert "keine – bitte" not in inhalt


def test_zweiter_schritt_nur_kurz_und_mit_wenigen_versuchen(client, admin, anmelden):
    from apps.konten import views

    TOTPDevice.objects.create(user=admin, name="Handy", confirmed=True)
    url, code_url = reverse("konten:anmelden"), reverse("konten:anmelden_code")
    # ohne ersten Schritt geht es nicht
    assert client.get(code_url, follow=True).redirect_chain[-1][0] == url
    client.post(url, {"username": "chefin", "password": PASSWORT})
    for _ in range(views.ZWEITER_SCHRITT_VERSUCHE - 1):
        TOTPDevice.objects.update(throttling_failure_count=0, throttling_failure_timestamp=None)
        assert client.post(code_url, {"otp_token": "000000"}).status_code == 200
    antwort = client.post(code_url, {"otp_token": "000000"}, follow=True)
    assert "Zu viele falsche Codes" in antwort.content.decode()
    # nach Ablauf der Zeit wieder von vorn
    client.post(url, {"username": "chefin", "password": PASSWORT})
    sitzung = client.session
    offen = sitzung[views.SITZUNG_ZWEITER_SCHRITT]
    offen["zeit"] -= views.ZWEITER_SCHRITT_MINUTEN * 60 + 1
    sitzung[views.SITZUNG_ZWEITER_SCHRITT] = offen
    sitzung.save()
    antwort = client.get(code_url, follow=True)
    assert "Bitte zuerst Benutzername und Passwort" in antwort.content.decode()
    # Angemeldete landen auf der Startseite
    anmelden(client, admin)
    assert client.get(code_url).url == reverse("core:start")


def test_impressum_auf_der_anmeldeseite(client, admin):
    from apps.antraege.models import AntragEinstellungen
    from apps.core.models import TafelEinstellungen

    assert "Impressum" not in client.get(reverse("konten:anmelden")).content.decode()
    e = AntragEinstellungen.laden()
    e.impressum_url = "https://tafel.example.org/impressum"
    e.save()
    TafelEinstellungen.objects.update(name="Tafel Musterstadt")
    seite = client.get(reverse("konten:anmelden")).content.decode()
    assert 'href="https://tafel.example.org/impressum" rel="noopener">Impressum der Tafel ' in seite
    assert seite.count("https://tafel.example.org/impressum") == 2  # auch unten in der Fußzeile
