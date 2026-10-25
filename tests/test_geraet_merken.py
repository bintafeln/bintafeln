"""Zwei-Faktor: Gerät für eine einstellbare Zahl von Tagen vertrauen."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen, zwei_faktor
from apps.konten.models import AnmeldeEinstellungen, VertrautesGeraet
from tests.conftest import PASSWORT
from tests.test_zwei_faktor import einrichten

pytestmark = pytest.mark.django_db
ANMELDEN = reverse("konten:anmelden")
CODE = reverse("konten:anmelden_code")


@pytest.fixture
def buero(benutzer_mit_rolle, admin):
    return benutzer_mit_rolle("buero", rollen.BUERO)


def tage(n):
    e = AnmeldeEinstellungen.laden()
    e.vertrauen_tage = n
    e.save()


def mit_code(client, code, vertrauen=True):
    """Beide Schritte: Passwort, dann Code (ADR 0052, zweiter Schritt eigenes Fenster)."""
    client.post(reverse("konten:abmelden"))
    assert client.post(ANMELDEN, {"username": "buero", "password": PASSWORT}).url == CODE
    daten = {"otp_token": code}
    if vertrauen:
        daten["vertrauen"] = "on"
    return client.post(CODE, daten)


def ohne_code(client) -> bool:
    """True, wenn das Passwort reicht (vertrautes Gerät); False, wenn der Code-Schritt folgt."""
    antwort = client.post(ANMELDEN, {"username": "buero", "password": PASSWORT})
    assert antwort.status_code == 302
    return antwort.url != CODE


def test_aus_kein_haken_und_kein_vertrauen(client, buero):
    client.force_login(buero)
    codes = einrichten(client, buero)
    client.post(reverse("konten:abmelden"))
    assert "vertrauen" not in client.get(ANMELDEN).content.decode()
    client.post(ANMELDEN, {"username": "buero", "password": PASSWORT})
    assert "vertrauen" not in client.get(CODE).content.decode()
    mit_code(client, codes[0])
    assert not VertrautesGeraet.objects.exists()


def test_vertrautes_geraet_braucht_keinen_code(client, buero):
    client.force_login(buero)
    codes = einrichten(client, buero)
    client.post(reverse("konten:abmelden"))
    tage(7)
    client.post(ANMELDEN, {"username": "buero", "password": PASSWORT})
    assert "Diesem Gerät 7 Tage vertrauen" in client.get(CODE).content.decode()
    antwort = mit_code(client, codes[0])
    assert antwort.status_code == 302 and zwei_faktor.COOKIE in antwort.cookies
    g = VertrautesGeraet.objects.get(benutzer=buero)
    assert dt.timedelta(days=6) < g.gueltig_bis - timezone.now() <= dt.timedelta(days=7)
    client.post(reverse("konten:abmelden"))
    # ohne Code angemeldet, Sitzung gilt als verifiziert (Pflicht-Rolle Büro)
    assert ohne_code(client) is True
    assert client.get(reverse("core:start")).status_code == 200
    # Falsches Passwort hilft auch auf vertrautem Gerät nicht
    client.post(reverse("konten:abmelden"))
    falsch = client.post(ANMELDEN, {"username": "buero", "password": "falsch-falsch-1"})
    assert falsch.status_code == 200
    # Anderer Browser ohne Cookie braucht den Code
    assert ohne_code(Client()) is False


def test_ungueltig_nach_ablauf_passwort_und_entfernen(client, buero):
    client.force_login(buero)
    codes = einrichten(client, buero)
    client.post(reverse("konten:abmelden"))
    tage(30)
    mit_code(client, codes[0])
    client.post(reverse("konten:abmelden"))
    # abgelaufen
    VertrautesGeraet.objects.update(gueltig_bis=timezone.now() - dt.timedelta(minutes=1))
    assert ohne_code(client) is False
    # neues Passwort
    VertrautesGeraet.objects.update(gueltig_bis=timezone.now() + dt.timedelta(days=1))
    assert ohne_code(client) is True
    client.post(reverse("konten:abmelden"))
    buero.set_password(PASSWORT)  # gleicher Text, aber neuer Hash
    buero.save()
    assert ohne_code(client) is False
    # Mein Konto: eigene Geräte sehen und entfernen
    mit_code(client, codes[1])
    seite = client.get(reverse("konten:mein_konto")).content.decode()
    assert "Vertraute Geräte" in seite and "gültig bis" in seite
    client.post(reverse("konten:geraete_entfernen"))
    assert not buero.vertraute_geraete.exists()


def test_admin_entfernt_und_ausschalten_loescht(admin_client, buero):
    client = Client()  # admin_client ist sonst derselbe Client
    client.force_login(buero)
    codes = einrichten(client, buero)
    client.post(reverse("konten:abmelden"))
    tage(14)
    mit_code(client, codes[0])
    seite = admin_client.get(reverse("konten:mitarbeiter", args=[buero.pk])).content.decode()
    assert "Vertraute Geräte entfernen (1)" in seite
    admin_client.post(reverse("konten:geraete_zuruecksetzen", args=[buero.pk]))
    assert not VertrautesGeraet.objects.exists()
    mit_code(client, codes[1])
    antwort = admin_client.post(reverse("konten:anmelde_einstellungen"), {"vertrauen_tage": 0})
    assert antwort.status_code == 302 and not VertrautesGeraet.objects.exists()
    # Neue Einrichtung der Zwei-Faktor-Anmeldung entzieht das Vertrauen ebenfalls
    tage(14)
    client.post(reverse("konten:abmelden"))
    mit_code(client, codes[2])
    assert VertrautesGeraet.objects.exists()
    zwei_faktor.abschalten(buero)
    assert not VertrautesGeraet.objects.exists()


def test_einstellungen_nur_mit_recht(client, buero, anmelden):
    anmelden(client, buero)
    assert client.get(reverse("konten:anmelde_einstellungen")).status_code == 403


def test_geraetename():
    assert zwei_faktor.geraet_name("Mozilla/5.0 (Windows NT 10.0) Firefox/130") == (
        "Firefox unter Windows"
    )
    assert zwei_faktor.geraet_name("") == "Browser"
