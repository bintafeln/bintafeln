"""Freiwillige Meldung im bintafeln-Verzeichnis (ADR 0089). Nur erfundene Daten."""

import datetime as dt
import json
import uuid

import pytest
from django.core.cache import cache
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.core import verzeichnis
from apps.core.models import TafelEinstellungen, VerzeichnisEintrag, VerzeichnisMeldung

pytestmark = pytest.mark.django_db
SEITE = reverse("core:verzeichnis")
EMPFANG = reverse("core:verzeichnis_melden")


@pytest.fixture
def empfang(settings, client):
    """Eine Installation, die Meldungen annimmt; die Meldungen gehen über den Test-Client."""
    settings.VERZEICHNIS_EMPFANG = True
    cache.clear()
    gesendet = []

    def senden(daten):
        gesendet.append(daten)
        antwort = client.post(EMPFANG, json.dumps(daten), content_type="application/json")
        if antwort.status_code != 200:
            raise verzeichnis.VerzeichnisFehler(f"Antwort {antwort.status_code}")

    return senden, gesendet


@pytest.fixture
def tafel(admin):
    t = TafelEinstellungen.laden()
    t.name, t.email = "Tafel Musterstadt", "info@tafel.example.org"
    t.save()
    return t


def test_einschalten_melden_und_ausschalten(admin_client, tafel, empfang, monkeypatch):
    senden, gesendet = empfang
    monkeypatch.setattr(verzeichnis, "_senden", senden)
    seite = admin_client.get(SEITE).content.decode()
    assert "Nicht gemeldet" in seite and "Tafel Musterstadt" in seite
    assert "info@tafel.example.org" in seite  # Kontakt ohne Eintrag: E-Mail der Tafel
    admin_client.post(SEITE, {"aktiv": "on", "kontakt": "vorstand@tafel.example.org"})
    e = VerzeichnisEintrag.objects.get()
    assert (e.name, e.kontakt) == ("Tafel Musterstadt", "vorstand@tafel.example.org")
    assert set(gesendet[0]) == {"kennung", "name", "kontakt", "version"}  # sonst nichts
    m = VerzeichnisMeldung.laden()
    assert m.gemeldet_am and not m.fehler and str(m.kennung) == str(e.kennung)
    assert "Gemeldet, zuletzt am" in admin_client.get(SEITE).content.decode()
    # Liste beim Herausgeber
    liste = admin_client.get(reverse("core:verzeichnis_liste")).content.decode()
    assert "Tafel Musterstadt" in liste and "vorstand@tafel.example.org" in liste
    # Ausschalten löscht den Eintrag
    admin_client.post(SEITE, {"kontakt": ""})
    assert not VerzeichnisEintrag.objects.exists() and gesendet[-1]["abmelden"] is True


def test_faellig_nach_update_und_nach_einer_woche(tafel, monkeypatch):
    gesendet = []
    monkeypatch.setattr(verzeichnis, "_senden", gesendet.append)
    monkeypatch.setattr(verzeichnis, "version", lambda: "2026.10.1")
    assert not verzeichnis.faellig()  # nicht eingeschaltet
    VerzeichnisMeldung.laden()
    VerzeichnisMeldung.objects.update(aktiv=True)
    call_command("verzeichnis_melden")
    assert len(gesendet) == 1
    assert verzeichnis.bei_bedarf_melden() is False  # gerade gemeldet
    jetzt = timezone.now() + dt.timedelta(days=8)
    assert verzeichnis.faellig(jetzt)
    monkeypatch.setattr(verzeichnis, "version", lambda: "2026.10.2")  # Update
    assert verzeichnis.bei_bedarf_melden() is True and gesendet[-1]["version"] == "2026.10.2"


def test_nicht_erreichbar(admin_client, tafel, monkeypatch, settings):
    settings.VERZEICHNIS_URL = "http://127.0.0.1:9/verzeichnis/melden/"  # nichts lauscht
    antwort = admin_client.post(SEITE, {"aktiv": "on"}, follow=True).content.decode()
    assert "nicht geklappt" in antwort and "nicht erreichbar" in antwort
    m = VerzeichnisMeldung.laden()
    assert m.aktiv and m.gemeldet_am is None and m.fehler
    assert verzeichnis.faellig()  # nächster Versuch von selbst


def test_empfang_aus_und_ungueltige_meldungen(admin, settings):
    from django.test import Client

    client = Client()  # ohne Anmeldung, wie eine andere Tafel
    assert client.post(EMPFANG, "{}", content_type="application/json").status_code == 404
    settings.VERZEICHNIS_EMPFANG = True
    cache.clear()
    for daten in ([], {"kennung": "kaputt", "name": "X"}, {"kennung": str(uuid.uuid4())}):
        assert client.post(EMPFANG, json.dumps(daten), content_type="application/json"
                           ).status_code == 400  # fmt: skip
    assert client.post(EMPFANG, "x" * 5000, content_type="application/json").status_code == 413
    kennung = str(uuid.uuid4())
    daten = {"kennung": kennung, "name": "Tafel Beispielstadt", "kontakt": "kein mail",
             "version": "2026.10.120"}  # fmt: skip
    assert client.post(EMPFANG, json.dumps(daten), content_type="application/json").json() == {
        "ergebnis": "gemeldet"}  # fmt: skip
    assert VerzeichnisEintrag.objects.get(kennung=kennung).kontakt == ""  # ungültig: leer
    assert client.get(EMPFANG).status_code == 405
    for _ in range(40):
        letzte = client.post(EMPFANG, json.dumps(daten), content_type="application/json")
    assert letzte.status_code == 429  # zu viele aus derselben Adresse
    assert VerzeichnisEintrag.objects.count() == 1


def test_liste_nur_beim_herausgeber(admin_client, admin, settings):
    assert admin_client.get(reverse("core:verzeichnis_liste")).status_code == 404
    assert "Gemeldete Tafeln" not in admin_client.get(SEITE).content.decode()
    settings.VERZEICHNIS_EMPFANG = True
    alt = VerzeichnisEintrag.objects.create(kennung=uuid.uuid4(), name="Tafel Altdorf")
    VerzeichnisEintrag.objects.filter(pk=alt.pk).update(
        letzte_meldung=timezone.now() - dt.timedelta(days=30))  # fmt: skip
    seite = admin_client.get(reverse("core:verzeichnis_liste")).content.decode()
    assert "Tafel Altdorf" in seite and "marke-warnung" in seite


def test_demo_meldet_nicht(tafel, settings, monkeypatch):
    settings.DEMO = True
    VerzeichnisMeldung.laden()
    VerzeichnisMeldung.objects.update(aktiv=True)
    assert not verzeichnis.faellig()
