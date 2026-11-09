"""Freundliche Antwort bei fehlgeschlagener CSRF-Prüfung (ADR 0119).

Wenn eine Seite lange offen war und die Anmeldung abgelaufen ist, trägt das Formular ein
veraltetes CSRF-Token. Nicht Angemeldete sollen dann nicht in der Django-Sackgasse landen,
sondern auf einer frischen Anmeldeseite – ohne den Browser schließen zu müssen. Alle Daten
sind erfunden."""

import pytest
from django.test import Client
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_csrf_fehler_leitet_nicht_angemeldete_zur_anmeldung(admin):
    # Eigener Client mit CSRF-Prüfung (der normale Test-Client schaltet sie ab);
    # ``admin`` sorgt dafür, dass die Ersteinrichtung schon erledigt ist.
    client = Client(enforce_csrf_checks=True)
    antwort = client.post(reverse("konten:anmelden"), {"username": "x", "password": "y"})
    assert antwort.status_code == 302
    assert antwort.url == reverse("konten:anmelden")


def test_csrf_fehler_zeigt_angemeldeten_einen_hinweis(admin, anmelden):
    client = anmelden(Client(enforce_csrf_checks=True), admin)
    # Angemeldet, aber POST ohne gültiges Token (z. B. veraltetes Formular).
    antwort = client.post(reverse("konten:abmelden"))
    assert antwort.status_code == 403
    assert "zu lange offen" in antwort.content.decode()


def test_anmeldeseite_wird_nicht_zwischengespeichert(client, admin):
    antwort = client.get(reverse("konten:anmelden"))
    assert "no-store" in antwort.headers.get("Cache-Control", "")
