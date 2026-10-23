import re

import pytest
from auditlog.models import LogEntry
from django.core.management import call_command
from django.core.management.base import CommandError
from django.urls import reverse
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.core.models import TafelEinstellungen
from apps.konten import rollen, zwei_faktor
from tests.conftest import PASSWORT, code_fuer

pytestmark = pytest.mark.django_db

EINRICHTEN = reverse("konten:zwei_faktor_einrichten")
KONTO = reverse("konten:mein_konto")
ANMELDEN = reverse("konten:anmelden")


@pytest.fixture
def buero(benutzer_mit_rolle, admin):
    return benutzer_mit_rolle("buero", rollen.BUERO)


@pytest.fixture
def ausgabe(benutzer_mit_rolle, admin):
    return benutzer_mit_rolle("ausgabe", rollen.AUSGABE)


def einrichten(client, benutzer):
    """Durchläuft die Einrichtung und gibt die angezeigten Notfallcodes zurück."""
    client.get(EINRICHTEN)
    geraet = TOTPDevice.objects.get(user=benutzer, confirmed=False)
    antwort = client.post(EINRICHTEN, {"code": code_fuer(geraet)})
    assert antwort.status_code == 200
    return re.findall(r"<code>([a-z2-7]{8})</code>", antwort.content.decode())


# --- Pflicht je Rolle --------------------------------------------------------------------


def test_standard_pflicht_admin_und_buero():
    assert TafelEinstellungen.laden().zwei_faktor_pflicht_rollen() == {rollen.ADMIN, rollen.BUERO}


def test_pflicht_rolle_wird_zur_einrichtung_geleitet(client, buero):
    client.force_login(buero)
    for pfad in ("/", KONTO, "/protokoll/", "/admin/"):
        antwort = client.get(pfad)
        assert antwort.status_code == 302, pfad
        assert antwort.url == EINRICHTEN
    seite = client.get(EINRICHTEN).content.decode()
    assert "Mein Konto" not in seite  # Menü während der Pflicht-Einrichtung reduziert
    assert "Abmelden" in seite
    assert client.get("/healthz/").status_code == 200
    assert client.post(reverse("konten:abmelden")).status_code == 302


def test_ohne_pflicht_freier_zugang(client, ausgabe):
    client.force_login(ausgabe)
    assert client.get("/").status_code == 200


def test_pflicht_aus_einstellungen(client, ausgabe):
    einstellungen = TafelEinstellungen.laden()
    einstellungen.zwei_faktor_ausgabe = True
    einstellungen.save()
    client.force_login(ausgabe)
    assert client.get("/").url == EINRICHTEN
    assert zwei_faktor.ist_pflicht(ausgabe)


def test_ist_pflicht_anonym():
    from django.contrib.auth.models import AnonymousUser

    assert not zwei_faktor.ist_pflicht(AnonymousUser())


def test_admin_stellt_pflicht_in_einstellungen_um(admin_client):
    antwort = admin_client.post(
        reverse("core:einstellungen"),
        {"name": "Tafel", "zwei_faktor_admin": "on", "zwei_faktor_kiosk": "on"},
    )
    assert antwort.status_code == 302
    assert TafelEinstellungen.laden().zwei_faktor_pflicht_rollen() == {rollen.ADMIN, rollen.KIOSK}
    assert 'type="checkbox"' in admin_client.get(reverse("core:einstellungen")).content.decode()


# --- Einrichtung -------------------------------------------------------------------------


def test_einrichtung_mit_qr_code_und_notfallcodes(client, buero):
    client.force_login(buero)
    seite = client.get(EINRICHTEN)
    inhalt = seite.content.decode()
    assert "<svg" in inhalt
    assert "otpauth://totp/" in inhalt
    assert "no-store" in seite["Cache-Control"]
    # neu laden zeigt denselben Schlüssel
    client.get(EINRICHTEN)
    assert TOTPDevice.objects.filter(user=buero, confirmed=False).count() == 1

    codes = einrichten(client, buero)
    assert len(codes) == zwei_faktor.ANZAHL_NOTFALLCODES
    assert TOTPDevice.objects.filter(user=buero, confirmed=True).count() == 1
    assert not TOTPDevice.objects.filter(user=buero, confirmed=False).exists()
    # Sitzung ist jetzt verifiziert, das volle Menü ist da
    start = client.get("/")
    assert start.status_code == 200
    assert "Mein Konto" in start.content.decode()
    # erneuter Aufruf der Einrichtung führt zum Konto
    assert client.get(EINRICHTEN).url == KONTO


def test_einrichtung_falscher_code(client, buero):
    client.force_login(buero)
    client.get(EINRICHTEN)
    antwort = client.post(EINRICHTEN, {"code": "000000"})
    assert "Code stimmt nicht" in antwort.content.decode()
    assert not TOTPDevice.objects.filter(user=buero, confirmed=True).exists()


def test_aussteller_ist_tafelname():
    from django.contrib.auth import get_user_model

    benutzer = get_user_model().objects.create_user(username="x", password="y")
    geraet = zwei_faktor.neues_app_geraet(benutzer)
    assert "issuer=bintafeln" in geraet.config_url
    einstellungen = TafelEinstellungen.laden()
    einstellungen.name = "Tafel Musterstadt"
    einstellungen.save()
    assert "issuer=Tafel%20Musterstadt" in geraet.config_url


def test_schluessel_als_text_in_viererbloecken(django_user_model):
    geraet = zwei_faktor.neues_app_geraet(django_user_model.objects.create_user(username="x"))
    teile = zwei_faktor.schluessel_als_text(geraet).split(" ")
    assert all(len(teil) <= 4 for teil in teile)


# --- Anmeldung ---------------------------------------------------------------------------


def test_anmeldung_mit_app_code_und_notfallcode(client, buero):
    client.force_login(buero)
    codes = einrichten(client, buero)
    client.post(reverse("konten:abmelden"))

    ohne = client.post(ANMELDEN, {"username": "buero", "password": PASSWORT})
    assert ohne.status_code == 200

    # Notfallcode, auch mit Großbuchstaben und Leerzeichen eingegeben
    eingabe = f" {codes[0][:4].upper()} {codes[0][4:].upper()} "
    antwort = client.post(
        ANMELDEN, {"username": "buero", "password": PASSWORT, "otp_token": eingabe}
    )
    assert antwort.status_code == 302
    assert client.get("/").status_code == 200
    assert zwei_faktor.notfallcodes_uebrig(buero) == zwei_faktor.ANZAHL_NOTFALLCODES - 1

    # derselbe Notfallcode gilt kein zweites Mal
    client.post(reverse("konten:abmelden"))
    StaticDevice.objects.get(user=buero).throttle_reset()
    nochmal = client.post(
        ANMELDEN, {"username": "buero", "password": PASSWORT, "otp_token": codes[0]}
    )
    assert nochmal.status_code == 200


def test_unverifizierte_sitzung_mit_geraet_wird_abgemeldet(client, buero):
    TOTPDevice.objects.create(user=buero, name="App", confirmed=True)
    client.force_login(buero)
    antwort = client.get("/")
    assert antwort.url == ANMELDEN
    assert "_auth_user_id" not in client.session


# --- Mein Konto, Notfallcodes, Abschalten ------------------------------------------------


def test_mein_konto_zustaende(client, ausgabe, anmelden):
    client.force_login(ausgabe)
    inhalt = client.get(KONTO).content.decode()
    assert "Nicht eingerichtet" in inhalt
    einrichten(client, ausgabe)
    inhalt = client.get(KONTO).content.decode()
    assert "Eingeschaltet" in inhalt
    assert "Noch 10 unbenutzte Notfallcodes" in inhalt
    assert "Zwei-Faktor abschalten" in inhalt


def test_mein_konto_pflicht_kein_abschalten(client, buero):
    client.force_login(buero)
    einrichten(client, buero)
    inhalt = client.get(KONTO).content.decode()
    assert "kann nicht" in inhalt
    assert "Zwei-Faktor abschalten" not in inhalt


def test_notfallcodes_neu_erzeugen(client, buero):
    client.force_login(buero)
    alte = einrichten(client, buero)
    antwort = client.post(reverse("konten:notfallcodes_neu"))
    neue = re.findall(r"<code>([a-z2-7]{8})</code>", antwort.content.decode())
    assert len(neue) == zwei_faktor.ANZAHL_NOTFALLCODES
    assert not set(alte) & set(StaticToken.objects.values_list("token", flat=True))
    assert StaticDevice.objects.filter(user=buero).count() == 1


def test_notfallcodes_neu_ohne_app(client, ausgabe):
    client.force_login(ausgabe)
    assert client.post(reverse("konten:notfallcodes_neu")).url == KONTO
    assert not StaticDevice.objects.filter(user=ausgabe).exists()


def test_abschalten_mit_code(client, ausgabe):
    client.force_login(ausgabe)
    einrichten(client, ausgabe)
    url = reverse("konten:zwei_faktor_abschalten")

    client.post(url, {"code": "falsch"})
    assert zwei_faktor.app_geraet(ausgabe) is not None

    # Der Fehlversuch sperrt kurz alle Geräte (Schutz vor Durchprobieren).
    StaticDevice.objects.get(user=ausgabe).throttle_reset()
    # Ein bereits benutzter Zeitschritt zählt nicht; deshalb einen Notfallcode nehmen.
    code = StaticToken.objects.filter(device__user=ausgabe).first().token
    client.post(url, {"code": code})
    assert zwei_faktor.app_geraet(ausgabe) is None
    assert not StaticDevice.objects.filter(user=ausgabe).exists()
    assert client.get("/").status_code == 200


def test_abschalten_bei_pflicht_verboten(client, buero):
    client.force_login(buero)
    codes = einrichten(client, buero)
    antwort = client.post(reverse("konten:zwei_faktor_abschalten"), {"code": codes[0]})
    assert antwort.url == KONTO
    assert zwei_faktor.app_geraet(buero) is not None


def test_abschalten_nur_per_post(client, ausgabe):
    client.force_login(ausgabe)
    assert client.get(reverse("konten:zwei_faktor_abschalten")).status_code == 405


# --- Protokoll und Notfallbefehl ---------------------------------------------------------


def test_protokoll_ohne_geheimnisse(client, buero):
    client.force_login(buero)
    einrichten(client, buero)
    eintraege = LogEntry.objects.filter(content_type__model__in=["totpdevice", "staticdevice"])
    assert eintraege.exists()
    for eintrag in eintraege:
        assert set(eintrag.changes_dict) <= {"id", "user", "name", "confirmed"}


def test_befehl_zuruecksetzen(client, buero, capsys):
    client.force_login(buero)
    einrichten(client, buero)
    call_command("zwei_faktor_zuruecksetzen", "buero")
    assert zwei_faktor.app_geraet(buero) is None
    assert "zurückgesetzt" in capsys.readouterr().out
    with pytest.raises(CommandError):
        call_command("zwei_faktor_zuruecksetzen", "gibt-es-nicht")


def test_anmeldeseite_fuer_angemeldete_leitet_weiter(client, ausgabe):
    client.force_login(ausgabe)
    assert client.get(ANMELDEN).url == reverse("core:start")
