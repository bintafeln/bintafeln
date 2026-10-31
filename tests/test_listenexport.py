"""Listen als PDF herunterladen und per E-Mail senden (ADR 0096)."""

import pytest
from django.core import mail as django_mail
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core import geheimnis, listenexport
from apps.core.models import MailEinstellungen

pytestmark = pytest.mark.django_db

CSV = "﻿Name;Ort\r\nErika Beispiel;Musterstadt\r\n"


def _mailserver():
    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()


def test_pdf_aus_csv_ist_pdf():
    assert listenexport.pdf_aus_csv("Testliste", CSV)[:4] == b"%PDF"


def test_liste_als_pdf(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "pdf"})
    assert antwort.status_code == 200
    assert antwort["Content-Type"] == "application/pdf" and antwort.content[:4] == b"%PDF"


def test_liste_als_csv_unveraendert(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "csv"})
    assert "text/csv" in antwort["Content-Type"] and b"Beispiel" in antwort.content


def test_liste_per_mail_mit_pdf_und_csv(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    _mailserver()
    antwort = admin_client.get(
        reverse("adressen:liste"),
        {"aktion": "mail", "email": "buero@example.org", "weiter": reverse("adressen:liste")},
    )
    assert antwort.status_code == 302
    assert len(django_mail.outbox) == 1
    gesendet = django_mail.outbox[0]
    assert gesendet.to == ["buero@example.org"]
    namen = [anhang[0] for anhang in gesendet.attachments]
    assert len(namen) == 2
    assert any(n.endswith(".pdf") for n in namen) and any(n.endswith(".csv") for n in namen)


def test_mail_ohne_adresse_sendet_nicht(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    _mailserver()
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "mail", "email": ""})
    assert antwort.status_code == 302 and not django_mail.outbox
