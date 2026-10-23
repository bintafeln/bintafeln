import pytest
from django.urls import reverse

from apps.konten import rollen
from apps.kunden.models import KundenEinstellungen, Zusatzfeld

pytestmark = pytest.mark.django_db

EINSTELLUNGEN = reverse("kunden:einstellungen")
NEU = reverse("kunden:zusatzfeld_neu")


@pytest.mark.parametrize("rolle", [rollen.BUERO, rollen.AUSGABE, rollen.KIOSK])
def test_nur_admin(client, admin, benutzer_mit_rolle, anmelden, rolle):
    anmelden(client, benutzer_mit_rolle("person", rolle))
    assert client.get(EINSTELLUNGEN).status_code == 403
    assert client.get(NEU).status_code == 403


def test_link_auf_tafel_einstellungen(admin_client):
    assert EINSTELLUNGEN in admin_client.get(reverse("core:einstellungen")).content.decode()


def test_einstellungen_speichern(admin_client):
    inhalt = admin_client.get(EINSTELLUNGEN).content.decode()
    assert "Noch keine Zusatzfelder" in inhalt
    antwort = admin_client.post(
        EINSTELLUNGEN,
        {
            "telefon_erfassen": "on",
            "bemerkungen_importieren": "on",
            "kind_bis_alter": "16",
            "abholungen_aufbewahren_jahre": "2",
        },
    )
    assert antwort.status_code == 302
    e = KundenEinstellungen.laden()
    assert e.telefon_erfassen and e.bemerkungen_importieren
    assert not e.email_erfassen
    assert e.kind_bis_alter == 16
    assert e.abholungen_aufbewahren_jahre == 2


def test_einstellungen_ungueltig(admin_client):
    antwort = admin_client.post(EINSTELLUNGEN, {"kind_bis_alter": "-1"})
    assert antwort.status_code == 200


def test_zusatzfeld_anlegen_und_bearbeiten(admin_client):
    daten = {
        "schluessel": "schwerbehindert",
        "bezeichnung": "Schwerbehindert",
        "gilt_fuer": "person",
        "typ": "auswahl",
        "optionen": "nein\nja",
        "besondere_kategorie": "on",
        "reihenfolge": "1",
        "aktiv": "on",
    }
    assert admin_client.post(NEU, daten).status_code == 302
    feld = Zusatzfeld.objects.get()
    assert feld.besondere_kategorie and feld.optionen_liste() == ["nein", "ja"]

    liste = admin_client.get(EINSTELLUNGEN).content.decode()
    assert "zusatz_schwerbehindert" in liste and "Art. 9" in liste and "nein, ja" in liste

    url = reverse("kunden:zusatzfeld", args=[feld.pk])
    seite = admin_client.get(url).content.decode()
    assert "disabled" in seite  # Schlüssel nicht mehr änderbar
    admin_client.post(url, {**daten, "schluessel": "anders", "bezeichnung": "SB", "aktiv": ""})
    feld.refresh_from_db()
    assert feld.schluessel == "schwerbehindert"
    assert feld.bezeichnung == "SB" and not feld.aktiv
    assert "inaktiv" in admin_client.get(EINSTELLUNGEN).content.decode()


def test_zusatzfeld_auswahl_ohne_optionen_abgelehnt(admin_client):
    antwort = admin_client.post(
        NEU,
        {
            "schluessel": "essen",
            "bezeichnung": "Essen",
            "gilt_fuer": "haushalt",
            "typ": "auswahl",
            "optionen": "",
            "reihenfolge": "0",
        },
    )
    assert antwort.status_code == 200
    assert "mindestens eine Option" in antwort.content.decode()
    assert not Zusatzfeld.objects.exists()


def test_zusatzfeld_unbekannt(admin_client):
    assert admin_client.get(reverse("kunden:zusatzfeld", args=[999])).status_code == 404
