"""Modul Wetter (ADR 0053): Kopfzeile, Auswahl der Ausgabestelle, Zwischenspeicher, Fehler."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TafelEinstellungen
from apps.kunden.models import Ausgabestelle
from apps.wetter import wetter
from apps.wetter.models import WetterStand

pytestmark = pytest.mark.django_db

SUCHE = {"results": [
    {"name": "Musterstadt", "latitude": 1.0, "longitude": 2.0, "postcodes": ["99999"]},
    {"name": "Musterstadt", "latitude": 51.5, "longitude": 7.1, "postcodes": ["12345", "12346"]},
]}  # fmt: skip


@pytest.fixture
def dienst(monkeypatch):
    """Ersetzt Open-Meteo; zählt die Anfragen."""
    anfragen = []
    antwort = {"current": {"temperature_2m": 12.4, "weather_code": 3, "is_day": 1}}

    def holen(adresse, werte):
        anfragen.append((adresse, werte))
        if isinstance(antwort.get("fehler"), Exception):
            raise antwort["fehler"]
        return SUCHE if adresse == wetter.SUCHE else antwort

    monkeypatch.setattr(wetter, "_json", holen)
    return anfragen, antwort


@pytest.fixture
def modul_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["wetter"]
    t.save()


@pytest.fixture
def stelle():
    return Ausgabestelle.objects.create(name="Mitte", strasse="Hauptstr. 1", plz="12345",
                                        ort="Musterstadt")  # fmt: skip


def test_kopfzeile_nur_mit_modul(admin_client, stelle, dienst):
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert "bintafeln" in seite and "freie Tafelsoftware" in seite
    assert reverse("wetter:kopf") not in seite
    assert admin_client.get(reverse("wetter:kopf")).status_code == 404
    TafelEinstellungen.objects.update(module=["wetter"])
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert reverse("wetter:kopf") in seite and "kopfzeile.js" in seite


def test_wetter_abrufen_und_zwischenspeichern(modul_an, admin_client, stelle, dienst):
    anfragen, _ = dienst
    teil = admin_client.get(reverse("wetter:kopf")).content.decode()
    assert "12 °C" in teil and "bedeckt" in teil and "☁️" in teil and "Mitte" in teil
    # Suche nur nach dem Ort (keine Straße), Treffer mit passender PLZ
    assert anfragen[0][1]["name"] == "Musterstadt" and "Hauptstr" not in str(anfragen)
    assert anfragen[1][1]["latitude"] == 51.5
    admin_client.get(reverse("wetter:kopf"))
    assert len(anfragen) == 2  # zwischengespeichert
    WetterStand.objects.update(abgerufen_am=timezone.now() - dt.timedelta(minutes=31))
    admin_client.get(reverse("wetter:kopf"))
    assert len(anfragen) == 3  # nur das Wetter, die Koordinaten sind bekannt
    stelle.plz, stelle.ort = "", "Andersdorf"
    stelle.save()
    admin_client.get(reverse("wetter:kopf"))
    assert anfragen[3][1]["name"] == "Andersdorf"  # neue Anschrift: neu suchen


def test_nacht_und_unbekannter_code(stelle, dienst):
    _, antwort = dienst
    antwort["current"] = {"temperature_2m": -0.6, "weather_code": 0, "is_day": 0}
    w = wetter.aktuell(stelle)
    assert w["symbol"] == "🌙" and w["temperatur"] == -1 and w["text"] == "klar"
    WetterStand.objects.update(abgerufen_am=None)
    antwort["current"] = {"temperature_2m": 20, "weather_code": 42}
    assert wetter.aktuell(stelle)["text"] == ""


def test_dienst_nicht_erreichbar(stelle, dienst):
    anfragen, antwort = dienst
    antwort["fehler"] = OSError("keine Verbindung")
    assert wetter.aktuell(stelle) is None
    assert wetter.aktuell(stelle) is None
    assert len(anfragen) == 1  # Pause nach einem Fehler
    del antwort["fehler"]
    WetterStand.objects.update(fehler_am=timezone.now() - dt.timedelta(minutes=11))
    assert wetter.aktuell(stelle)["temperatur"] == 12
    # Danach wieder Fehler: das letzte Wetter bleibt eine Weile stehen, aber nicht zu lange
    antwort["fehler"] = ValueError("kaputt")
    WetterStand.objects.update(abgerufen_am=timezone.now() - dt.timedelta(minutes=40))
    assert wetter.aktuell(stelle)["temperatur"] == 12
    WetterStand.objects.update(abgerufen_am=timezone.now() - dt.timedelta(hours=4), fehler_am=None)
    assert wetter.aktuell(stelle) is None


def test_ort_nicht_gefunden(stelle, monkeypatch):
    monkeypatch.setattr(wetter, "_json", lambda adresse, werte: {})
    assert wetter.aktuell(stelle) is None
    assert WetterStand.objects.get().fehler_am is not None


def test_ohne_anschrift_und_ohne_stelle(admin, dienst):
    assert wetter.aktuell(None) is None
    leer = Ausgabestelle.objects.create(name="Ohne")
    assert wetter.aktuell(leer) is None
    assert wetter.stelle_fuer(admin) is None
    assert dienst[0] == []


def test_stelle_der_person(admin, stelle):
    nord = Ausgabestelle.objects.create(name="Nord", plz="12346", ort="Musterstadt")
    Ausgabestelle.objects.create(name="Alt", plz="1", ort="X", aktiv=False)
    assert wetter.stelle_fuer(admin) == stelle  # keine Zuordnung: erste nach Name
    admin.ausgabestellen.add(nord)
    assert wetter.stelle_fuer(admin) == nord


def test_kopf_nennt_den_grund(modul_an, admin_client, monkeypatch):
    teil = admin_client.get(reverse("wetter:kopf")).content.decode()
    assert "🌡️ –" in teil and "Keine aktive Ausgabestelle mit PLZ oder Ort" in teil
    Ausgabestelle.objects.create(name="Mitte", plz="12345", ort="Musterstadt")

    def kein_netz(adresse, werte):
        raise OSError("Tunnel connection failed")

    monkeypatch.setattr(wetter, "_json", kein_netz)
    teil = admin_client.get(reverse("wetter:kopf")).content.decode()
    assert "Wetter für Mitte: Wetterdienst nicht erreichbar" in teil and "open-meteo.com" in teil
    monkeypatch.setattr(wetter, "_json", lambda adresse, werte: {})
    WetterStand.objects.update(fehler_am=None)
    teil = admin_client.get(reverse("wetter:kopf")).content.decode()
    assert "Ort „Musterstadt“ nicht gefunden – PLZ und Ort der Ausgabestelle prüfen" in teil
    WetterStand.objects.update(fehler="")
    assert "Noch kein aktuelles Wetter" in admin_client.get(reverse("wetter:kopf")).content.decode()


def test_kopf_nur_angemeldet(modul_an, client):
    assert client.get(reverse("wetter:kopf")).status_code == 302


def test_echter_abruf_baut_die_adresse(monkeypatch):
    """_json ruft urlopen mit Zeitlimit und der zusammengesetzten Adresse auf."""
    gesehen = {}

    class Antwort:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self, *a):
            return b'{"ok": 1}'

    def urlopen(anfrage, timeout):
        gesehen["url"], gesehen["timeout"] = anfrage.full_url, timeout
        return Antwort()

    monkeypatch.setattr(wetter, "urlopen", urlopen)
    assert wetter._json(wetter.WETTER, {"a": 1}) == {"ok": 1}
    assert gesehen == {"url": f"{wetter.WETTER}?a=1", "timeout": wetter.ZEIT}
