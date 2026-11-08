"""Anmeldeprotokoll (ADR 0117): Erfolg und Fehlversuche mit IP und Browser. Alle Daten erfunden."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.konten import anmeldeprotokoll
from apps.konten.models import AnmeldeEinstellungen, AnmeldeProtokoll
from tests.conftest import PASSWORT

pytestmark = pytest.mark.django_db


def test_erfolgreiche_anmeldung_wird_protokolliert(client, admin):
    client.post(
        reverse("konten:anmelden"), {"username": "chefin", "password": PASSWORT},
        HTTP_X_FORWARDED_FOR="9.9.9.9, 10.0.0.1", HTTP_USER_AGENT="Firefox/Test",
    )
    e = AnmeldeProtokoll.objects.get()
    assert e.erfolg is True and e.benutzer == admin
    assert e.benutzername == "chefin"
    assert e.ip == "9.9.9.9"  # echte Besucher-IP: erster Eintrag aus X-Forwarded-For
    assert e.browser == "Firefox/Test"


def test_falsches_passwort_wird_protokolliert(client, admin):
    client.post(reverse("konten:anmelden"), {"username": "chefin", "password": "falsch"},
                HTTP_USER_AGENT="Chrome/Test")  # fmt: skip
    e = AnmeldeProtokoll.objects.get()
    assert e.erfolg is False and e.grund == "Passwort" and e.benutzername == "chefin"
    assert e.benutzer is None  # Passwort stimmte nicht, also kein Konto verknüpft


def test_ausgeschaltet_protokolliert_nichts(client, admin):
    e = AnmeldeEinstellungen.laden()
    e.protokoll_tage = 0
    e.save()
    client.post(reverse("konten:anmelden"), {"username": "chefin", "password": PASSWORT})
    client.post(reverse("konten:anmelden"), {"username": "chefin", "password": "falsch"})
    assert AnmeldeProtokoll.objects.count() == 0


def test_frist_loescht_alte_eintraege():
    AnmeldeProtokoll.objects.create(benutzername="alt", erfolg=True,
                                    zeitpunkt=timezone.now() - dt.timedelta(days=100))  # fmt: skip
    AnmeldeProtokoll.objects.create(benutzername="neu", erfolg=True)
    e = AnmeldeEinstellungen.laden()
    e.protokoll_tage = 90
    e.save()
    anmeldeprotokoll.fristen_anwenden()
    assert list(AnmeldeProtokoll.objects.values_list("benutzername", flat=True)) == ["neu"]
    # „Aus“ räumt alles weg
    e.protokoll_tage = 0
    e.save()
    anmeldeprotokoll.fristen_anwenden()
    assert AnmeldeProtokoll.objects.count() == 0


def test_seite_zeigt_eintraege_und_fehlt_ohne_recht(admin_client, client, anmelden,
                                                    benutzer_mit_rolle):  # fmt: skip
    from apps.konten import rollen

    AnmeldeProtokoll.objects.create(benutzername="erika", erfolg=False, grund="Passwort",
                                    ip="203.0.113.7", browser="Safari")  # fmt: skip
    seite = admin_client.get(reverse("konten:anmeldeprotokoll"))
    inhalt = seite.content.decode()
    assert "erika" in inhalt and "203.0.113.7" in inhalt and "Fehlversuch" in inhalt
    # nur Fehlversuche
    nur = admin_client.get(reverse("konten:anmeldeprotokoll"), {"nur": "fehlversuche"})
    assert "erika" in nur.content.decode()

    # Ohne das Recht „protokoll.sehen“ gesperrt (Rolle Ausgabe)
    anmelden(client, benutzer_mit_rolle("helfer", rollen.AUSGABE))
    assert client.get(reverse("konten:anmeldeprotokoll")).status_code == 403


def test_anmeldungen_in_der_auskunft(admin_client, admin, pdf_text):
    AnmeldeProtokoll.objects.create(benutzer=admin, benutzername="chefin", erfolg=True,
                                    ip="198.51.100.4", browser="Edge")  # fmt: skip
    text = pdf_text(admin_client.get(reverse("konten:auskunft", args=[admin.pk])))
    assert "Anmeldungen" in text and "198.51.100.4" in text
