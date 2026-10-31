"""Admin-Verweise („legt der Admin unter Einstellungen → …") sehen nur Konten mit dem Recht der
Zielseite; das Suchfeld der Kundenliste fokussiert nur auf Geräten mit Maus. Erfundene Daten."""

import pytest
from django.urls import reverse

from apps.konten import rollen

pytestmark = pytest.mark.django_db


def test_spaltenhinweis_nur_mit_einstellungsrecht(admin_client, client, benutzer_mit_rolle,
                                                  recht_geben, anmelden):  # fmt: skip
    url = reverse("kunden:uebersicht")
    # Admin (hat einstellungen.kundenstamm) sieht den Verweis auf die Einstellungen.
    assert "legt der Admin unter" in admin_client.get(url).content.decode()
    # Ausgabe-Konto mit Kundenliste, aber ohne Einstellungsrecht: kein Verweis (weniger Ballast).
    b = benutzer_mit_rolle("anna", rollen.AUSGABE)
    recht_geben(rollen.AUSGABE, "kunden.liste")
    anmelden(client, b)
    assert "legt der Admin unter" not in client.get(url).content.decode()


def test_kundenliste_fokus_nur_mit_maus(admin_client):
    html = admin_client.get(reverse("kunden:uebersicht")).content.decode()
    # Kein natives autofocus mehr (sonst Tastatur am Tablet); stattdessen „nur mit Maus".
    assert "data-fokus-maus" in html and "autofocus" not in html
