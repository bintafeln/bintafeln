"""Ausgabestellen mit Anschrift, Zeiten, Ansprechpartnern und Karte (ADR 0048). Daten erfunden."""

import datetime as dt

import pytest
from django.urls import reverse

from apps.konten import rollen
from apps.kunden.models import (
    Ausgabestelle,
    AusgabestelleKontakt,
    AusgabestelleZeit,
    Haushalt,
    Kundengruppe,
)
from apps.kunden.views_ausgabestellen import karten_links

pytestmark = pytest.mark.django_db


def formsets(**mehr):
    return {"z-TOTAL_FORMS": "0", "z-INITIAL_FORMS": "0", "k-TOTAL_FORMS": "0",
            "k-INITIAL_FORMS": "0"} | mehr  # fmt: skip


def test_anlegen_mit_zeiten_und_ansprechpartnern(admin_client, admin):
    daten = formsets(**{
        "name": "Zentrale", "aktiv": "on", "strasse": "Musterweg 1", "plz": "12345",
        "ort": "Musterstadt", "telefon": "0123 4567", "email": "zentrale@example.org",
        "anmerkung": "Eingang über den Hof",
        "z-TOTAL_FORMS": "2", "z-0-wochentag": "4", "z-0-von": "13:30", "z-0-bis": "15:30",
        "z-0-art": "Ausgabe", "z-0-hinweis": "", "z-1-wochentag": "", "z-1-art": "Ausgabe",
        "k-TOTAL_FORMS": "2", "k-0-zustaendigkeit": "Leitung", "k-0-benutzer": admin.pk,
        "k-0-telefon": "0170 000", "k-1-zustaendigkeit": "Vermieter / Hausverwaltung",
        "k-1-name": "Gemeindebüro", "k-1-email": "buero@example.org",
    })  # fmt: skip
    antwort = admin_client.post(reverse("kunden:ausgabestelle_neu"), daten)
    s = Ausgabestelle.objects.get()
    assert antwort.url == reverse("kunden:ausgabestelle", args=[s.pk])
    assert s.anschrift == "Musterweg 1, 12345 Musterstadt"
    z = s.zeiten.get()
    assert (z.wochentag, z.von, z.bis, z.art) == (4, dt.time(13, 30), dt.time(15, 30), "Ausgabe")
    assert str(z) == "Freitag 13:30–15:30 Ausgabe"
    leitung, buero = s.kontakte.all()
    assert leitung.anzeige_name == (admin.get_full_name() or admin.username)
    assert buero.anzeige_name == "Gemeindebüro" and buero.anzeige_email == "buero@example.org"
    Kundengruppe.objects.create(name="Fr 13:30", ausgabestelle=s, wochentage="Fr", maximum=80)
    seite = admin_client.get(antwort.url).content.decode()
    for text in ("Eingang über den Hof", "Freitag", "13:30–15:30 Uhr", "Gemeindebüro",
                 "Fr 13:30", "0 von 80", "Karte anzeigen", "In Google Maps öffnen",
                 "karte.js"):  # fmt: skip
        assert text in seite, text
    assert "<iframe" not in seite  # Karte erst nach Klick
    liste = admin_client.get(reverse("kunden:ausgabestellen")).content.decode()
    assert "Musterweg 1, 12345 Musterstadt" in liste and "Fr 13:30–15:30 Ausgabe" in liste


def test_pruefungen(admin_client, admin):
    s = Ausgabestelle.objects.create(name="Nord")
    url = reverse("kunden:ausgabestelle_bearbeiten", args=[s.pk])
    fehler = admin_client.post(url, formsets(**{
        "name": "Nord", "z-TOTAL_FORMS": "1", "z-0-wochentag": "0", "z-0-von": "15:00",
        "z-0-bis": "14:00", "z-0-art": "Ausgabe", "k-TOTAL_FORMS": "1",
        "k-0-zustaendigkeit": "Leitung"})).content.decode()  # fmt: skip
    assert "„bis“ liegt nicht nach „von“." in fehler
    assert "Bitte Mitarbeiter/in wählen oder einen Namen eintragen." in fehler
    assert not AusgabestelleZeit.objects.exists() and not AusgabestelleKontakt.objects.exists()


def test_karte_und_alte_listen_adressen(admin_client):
    s = Ausgabestelle.objects.create(name="Ohne Anschrift")
    assert karten_links(s) is None
    assert "bitte die Anschrift eintragen" in admin_client.get(
        reverse("kunden:ausgabestelle", args=[s.pk])).content.decode()  # fmt: skip
    s.strasse, s.ort = "Weg 1 & 2", "Musterstadt"
    links = karten_links(s)
    assert "query=Weg+1+%26+2%2C+Musterstadt" in links["oeffnen"]
    assert links["einbetten"].endswith("&output=embed")
    assert admin_client.get(reverse("kunden:liste", args=["ausgabestellen"])).url == reverse(
        "kunden:ausgabestellen")  # fmt: skip
    assert admin_client.get(reverse("kunden:listeneintrag_neu", args=["ausgabestellen"])).url == (
        reverse("kunden:ausgabestelle_neu"))  # fmt: skip


def test_rechte_und_auskunft(client, admin, benutzer_mit_rolle, anmelden, pdf_text):
    s = Ausgabestelle.objects.create(name="Süd", telefon="0123")
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    AusgabestelleKontakt.objects.create(ausgabestelle=s, zustaendigkeit="Schlüssel", benutzer=b,
                                        telefon="0170 111")  # fmt: skip
    anmelden(client, b)
    seite = client.get(reverse("kunden:ausgabestelle", args=[s.pk])).content.decode()
    assert "Schlüssel" in seite and "Bearbeiten</a>" not in seite
    # Im Menü nur für die Verwaltung; die Seiten selbst bleiben erreichbar (z. B. Ansprechpartner)
    assert "Ausgabestellen</a>" not in client.get(reverse("core:start")).content.decode()
    assert client.get(reverse("kunden:ausgabestelle_bearbeiten", args=[s.pk])).status_code == 403
    client.logout()
    anmelden(client, benutzer_mit_rolle("kurt", rollen.KIOSK))
    assert client.get(reverse("kunden:ausgabestellen")).status_code == 403
    client.logout()
    client.force_login(admin)
    anmelden(client, admin)
    text = pdf_text(client.get(reverse("konten:auskunft", args=[b.pk])))
    assert "Ansprechpartner für Ausgabestellen" in text and "0170 111" in text
    assert Haushalt.objects.count() == 0


def test_leere_zeilen_werden_uebergangen(admin_client, admin):
    s = Ausgabestelle.objects.create(name="Ost")
    url = reverse("kunden:ausgabestelle_bearbeiten", args=[s.pk])
    seite = admin_client.get(url).content.decode()
    assert '<option value="" selected>—</option>' in seite
    antwort = admin_client.post(url, formsets(**{
        "name": "Ost", "z-TOTAL_FORMS": "1", "z-0-art": "Ausgabe", "z-0-wochentag": "",
        "k-TOTAL_FORMS": "1", "k-0-zustaendigkeit": "", "k-0-benutzer": ""}))  # fmt: skip
    assert antwort.status_code == 302 and not s.kontakte.exists() and not s.zeiten.exists()
