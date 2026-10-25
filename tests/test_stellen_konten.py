"""Konten der Ausgabestellen für Einlass-Tablets (ADR 0059). Alle Daten sind erfunden."""

import time

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse

from apps.konten import rollen, zwei_faktor
from apps.konten.middleware import StellenKontoMiddleware
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe

pytestmark = pytest.mark.django_db
ANMELDEN = reverse("konten:anmelden")
PW = "Drei-Woerter-Tafel-2026"


@pytest.fixture
def mitte():
    s = Ausgabestelle.objects.create(name="Carnaper Tisch", strasse="Weg 1", plz="1",
                                     ort="Musterstadt")  # fmt: skip
    nord = Ausgabestelle.objects.create(name="Nord")
    Haushalt.objects.create(kundennummer="101", kundengruppe=Kundengruppe.objects.create(
        name="Mo", ausgabestelle=s, wochentage="Mo"))  # fmt: skip
    Haushalt.objects.create(kundennummer="201", kundengruppe=Kundengruppe.objects.create(
        name="Nord Mo", ausgabestelle=nord, wochentage="Mo"))  # fmt: skip
    return s


def konto_anlegen(admin_client, stelle, passwort=PW):
    return admin_client.post(reverse("konten:stelle", args=[stelle.pk]),
                             {"passwort1": passwort, "passwort2": passwort})  # fmt: skip


def test_anlegen_und_anmelden_mit_namen(admin_client, mitte):
    assert "kein Konto" in admin_client.get(reverse("konten:stellen")).content.decode()
    antwort = konto_anlegen(admin_client, mitte)
    assert antwort.status_code == 302
    konto = get_user_model().objects.get(stelle=mitte)
    assert konto.username == f"ausgabestelle-{mitte.pk}" and konto.first_name == "Carnaper Tisch"
    assert list(konto.groups.values_list("name", flat=True)) == [rollen.AUSGABE]
    assert list(konto.ausgabestellen.all()) == [mitte]
    assert not zwei_faktor.ist_pflicht(konto)  # Rolle Ausgabe hat sonst Pflicht
    seite = admin_client.get(reverse("konten:stelle", args=[mitte.pk])).content.decode()
    assert "Anmelden mit" in seite and "Passwort ändern" in seite
    # Tablet: Name der Ausgabestelle (Groß/Klein egal) und Passwort, kein Code
    tablet = Client()
    antwort = tablet.post(ANMELDEN, {"username": "carnaper tisch", "password": PW})
    assert antwort.status_code == 302 and antwort.url == "/"
    start = tablet.get("/")
    assert start.status_code == 200 and "stellen_konto.js" in start.content.decode()
    # Keine Auskunft nach Art. 15 für das Konto einer Ausgabestelle (gehört keiner Person)
    assert "Meine Daten" not in tablet.get(reverse("konten:mein_konto")).content.decode()
    assert tablet.get(reverse("konten:meine_auskunft")).status_code == 404
    assert "Meine Daten" in admin_client.get(reverse("konten:mein_konto")).content.decode()
    liste = tablet.get(reverse("kunden:uebersicht"), {"tag": ""})
    assert [h.kundennummer for h in liste.context["seite"].object_list] == ["101"]
    # In der Liste der Mitarbeitenden steht das Konto nicht; dessen Seite führt zur Stelle
    assert (
        "ausgabestelle-" not in admin_client.get(reverse("konten:mitarbeitende")).content.decode()
    )
    antwort = admin_client.get(reverse("konten:mitarbeiter", args=[konto.pk]))
    assert antwort.url == reverse("konten:stelle", args=[mitte.pk])


def test_passwort_fehler(admin_client, mitte):
    daten = {"passwort1": PW, "passwort2": PW + "x"}
    seite = admin_client.post(reverse("konten:stelle", args=[mitte.pk]), daten).content.decode()
    assert "stimmen nicht überein" in seite
    seite = konto_anlegen(admin_client, mitte, "123").content.decode()
    assert "zu kurz" in seite or "zu häufig" in seite
    assert not get_user_model().objects.filter(stelle=mitte).exists()


def test_sperren_und_entsperren(admin_client, mitte):
    konto_anlegen(admin_client, mitte)
    url = reverse("konten:stelle", args=[mitte.pk])
    admin_client.post(url, {"aktion": "sperren"})
    konto = get_user_model().objects.get(stelle=mitte)
    assert not konto.is_active
    assert "gesperrt" in admin_client.get(reverse("konten:stellen")).content.decode()
    assert (
        Client().post(ANMELDEN, {"username": "Carnaper Tisch", "password": PW}).status_code == 200
    )
    admin_client.post(url, {"aktion": "entsperren"})
    konto.refresh_from_db()
    assert konto.is_active


def test_sperren_ohne_konto_verboten(admin_client, mitte):
    url = reverse("konten:stelle", args=[mitte.pk])
    assert admin_client.post(url, {"aktion": "sperren"}).status_code == 403


def test_abmeldung_nach_30_minuten(admin_client, mitte):
    konto_anlegen(admin_client, mitte)
    tablet = Client()
    tablet.post(ANMELDEN, {"username": "Carnaper Tisch", "password": PW})
    assert tablet.get("/").status_code == 200
    sitzung = tablet.session
    sitzung[StellenKontoMiddleware.SCHLUESSEL] = time.time() - 31 * 60
    sitzung.save()
    antwort = tablet.get("/", follow=True)
    assert antwort.redirect_chain[-1][0] == ANMELDEN
    assert "30 Minuten ohne Eingabe" in antwort.content.decode()
    assert "_auth_user_id" not in tablet.session


def test_sperre_nach_fehlversuchen(admin, mitte, admin_client):
    konto_anlegen(admin_client, mitte)
    c = Client()
    for _ in range(5):
        assert "falsch" in c.post(ANMELDEN, {"username": "Carnaper Tisch",
                                             "password": "falsch"}).content.decode()  # fmt: skip
    seite = c.post(ANMELDEN, {"username": "Carnaper Tisch", "password": PW}).content.decode()
    assert "Zu viele falsche Versuche" in seite


def test_nur_fuer_verwalter(admin, benutzer_mit_rolle, anmelden, mitte):
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert c.get(reverse("konten:stellen")).status_code == 403
    assert c.get(reverse("konten:stelle", args=[mitte.pk])).status_code == 403


def test_zwei_faktor_nur_mit_freigabe(admin_client, mitte):
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from apps.konten.models import AnmeldeEinstellungen
    from tests.test_zwei_faktor import einrichten

    konto_anlegen(admin_client, mitte)
    konto = get_user_model().objects.get(stelle=mitte)
    tablet = Client()
    tablet.post(ANMELDEN, {"username": "Carnaper Tisch", "password": PW})
    assert "Zwei-Faktor" not in tablet.get(reverse("konten:mein_konto")).content.decode()
    assert tablet.get(reverse("konten:zwei_faktor_einrichten")).status_code == 404
    # freigeschaltet: sichtbar und einrichtbar (aber keine Pflicht)
    url = reverse("konten:anmelde_einstellungen")
    admin_client.post(url, {"vertrauen_tage": "0", "stellen_zwei_faktor": "on"})
    assert AnmeldeEinstellungen.laden().stellen_zwei_faktor
    assert "Zwei-Faktor" in tablet.get(reverse("konten:mein_konto")).content.decode()
    einrichten(tablet, konto)
    assert TOTPDevice.objects.filter(user=konto).exists()
    # wieder aus: Geräte entfernt, Anmeldung mit Name und Passwort klappt ohne Code
    antwort = admin_client.post(url, {"vertrauen_tage": "0"}, follow=True)
    assert "Zwei-Faktor bei den Konten der Ausgabestellen entfernt" in antwort.content.decode()
    assert not TOTPDevice.objects.filter(user=konto).exists()
    neu = Client()
    antwort = neu.post(ANMELDEN, {"username": "Carnaper Tisch", "password": PW})
    assert antwort.status_code == 302 and antwort.url == "/"
    # Für andere Konten ändert die Freigabe nichts
    assert "Zwei-Faktor" in admin_client.get(reverse("konten:mein_konto")).content.decode()
