import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen
from apps.kunden.models import Haushalt, ImportLauf, ImportVorbereitung

pytestmark = pytest.mark.django_db

IMPORT = reverse("kunden:import")
UEBERSICHT = reverse("kunden:uebersicht")


def datei(name, *zeilen):
    return SimpleUploadedFile(name, ("\n".join(zeilen) + "\n").encode(), "text/csv")


def gueltig():
    return datei("haushalte.csv", "kundennummer;nachname;vorname;telefon", "1;A;B;201", "2;C;D;")


@pytest.fixture
def sicherung(settings, tmp_path):
    """Schreibt eine Statusdatei wie der Dienst backup; Alter in Stunden einstellbar."""

    def schreiben(stunden_alt):
        zeitpunkt = timezone.now() - dt.timedelta(hours=stunden_alt)
        pfad = tmp_path / "status.txt"
        pfad.write_text(
            f"ergebnis=ok\nletzte_erfolgreiche={zeitpunkt.strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
        )
        settings.SICHERUNG_STATUSDATEI = pfad

    return schreiben


@pytest.fixture
def buero_client(client, admin, benutzer_mit_rolle, anmelden):
    return anmelden(client, benutzer_mit_rolle("buero", rollen.BUERO))


@pytest.mark.parametrize("rolle", [rollen.AUSGABE, rollen.KIOSK])
def test_import_nur_admin_und_buero(client, admin, benutzer_mit_rolle, anmelden, rolle):
    anmelden(client, benutzer_mit_rolle("person", rolle))
    assert client.get(IMPORT).status_code == 403


def test_buero_sieht_menue_und_uebersicht(buero_client):
    assert "Kunden</a>" in buero_client.get("/").content.decode()
    inhalt = buero_client.get(UEBERSICHT).content.decode()
    assert "0 Haushalte" in inhalt and "Neuen Stand importieren" in inhalt
    assert "Noch kein Import" in buero_client.get(IMPORT).content.decode()


def test_ohne_dateien(buero_client):
    antwort = buero_client.post(IMPORT, {})
    assert "mindestens haushalte.csv" in antwort.content.decode()


def test_zu_grosse_datei(buero_client, monkeypatch):
    monkeypatch.setattr("apps.kunden.views.MAX_DATEIGROESSE", 5)
    antwort = buero_client.post(IMPORT, {"dateien": [gueltig()]})
    assert "höchstens 20 MB" in antwort.content.decode()
    assert not ImportVorbereitung.objects.exists()


def test_fehlerhafte_dateien_zeigen_bericht_ohne_speichern(buero_client, sicherung):
    sicherung(1)
    antwort = buero_client.post(
        IMPORT,
        {"dateien": [datei("haushalte.csv", "kundennummer;nachname;vorname", "1;A;B", "1;C;D")]},
    )
    inhalt = antwort.content.decode()
    assert "Import nicht möglich" in inhalt
    assert "Kundennummer kommt doppelt vor." in inhalt
    assert ">C<" not in inhalt  # keine Inhalte im Bericht
    assert not ImportVorbereitung.objects.exists()


def test_ablauf_pruefen_und_uebernehmen(buero_client, sicherung):
    sicherung(23)
    antwort = buero_client.post(IMPORT, {"dateien": [gueltig()]})
    vorbereitung = ImportVorbereitung.objects.get()
    assert antwort.url == reverse("kunden:import_vorschau", args=[vorbereitung.pk])
    assert str(vorbereitung).startswith("Import in Vorbereitung vom")

    vorschau = buero_client.get(antwort.url).content.decode()
    assert "Keine Fehler" in vorschau
    assert "1 Warnung" in vorschau and "führende 0" in vorschau
    assert "Import übernehmen" in vorschau

    fertig = buero_client.post(reverse("kunden:import_uebernehmen", args=[vorbereitung.pk]))
    assert fertig.url == UEBERSICHT
    assert Haushalt.objects.count() == 2
    assert not ImportVorbereitung.objects.exists()
    lauf = ImportLauf.objects.get()
    assert lauf.benutzer.username == "buero" and lauf.anzahl_warnungen == 1
    inhalt = buero_client.get(UEBERSICHT).content.decode()
    assert "2 Haushalte" in inhalt and "Import abgeschlossen" in inhalt


@pytest.mark.parametrize("stunden", [25, None])
def test_uebernehmen_nur_mit_frischer_sicherung(
    buero_client, sicherung, settings, tmp_path, stunden
):
    if stunden is None:
        settings.SICHERUNG_STATUSDATEI = tmp_path / "fehlt.txt"
    else:
        sicherung(stunden)
    assert "älter als 24 Stunden" in buero_client.get(IMPORT).content.decode()
    buero_client.post(IMPORT, {"dateien": [gueltig()]})
    vorbereitung = ImportVorbereitung.objects.get()
    vorschau = buero_client.get(reverse("kunden:import_vorschau", args=[vorbereitung.pk]))
    assert "Import übernehmen" not in vorschau.content.decode()
    antwort = buero_client.post(reverse("kunden:import_uebernehmen", args=[vorbereitung.pk]))
    assert antwort.url == reverse("kunden:import_vorschau", args=[vorbereitung.pk])
    assert not Haushalt.objects.exists()


def test_verwerfen(buero_client, sicherung):
    sicherung(1)
    buero_client.post(IMPORT, {"dateien": [gueltig()]})
    pk = ImportVorbereitung.objects.get().pk
    antwort = buero_client.post(reverse("kunden:import_verwerfen", args=[pk]))
    assert antwort.url == IMPORT
    assert not ImportVorbereitung.objects.exists()
    # zweites Verwerfen schadet nicht
    assert buero_client.post(reverse("kunden:import_verwerfen", args=[pk])).url == IMPORT


def test_fremde_und_abgelaufene_vorbereitung(buero_client, admin, sicherung, client):
    sicherung(1)
    buero_client.post(IMPORT, {"dateien": [gueltig()]})
    vorbereitung = ImportVorbereitung.objects.get()
    url = reverse("kunden:import_vorschau", args=[vorbereitung.pk])

    # Nur wer hochgeladen hat, sieht die Daten

    andere = vorbereitung.erstellt_von.__class__.objects.get(username="chefin")
    vorbereitung.erstellt_von = andere
    vorbereitung.save()
    assert buero_client.get(url).url == IMPORT
    assert (
        buero_client.post(reverse("kunden:import_uebernehmen", args=[vorbereitung.pk])).url
        == IMPORT
    )

    # Nach einer Stunde gelöscht, auch beim Aufruf der Startseite
    vorbereitung.erstellt_am = timezone.now() - dt.timedelta(minutes=61)
    vorbereitung.save()
    assert vorbereitung.abgelaufen
    buero_client.get("/")
    assert not ImportVorbereitung.objects.exists()


def test_uebernehmen_nur_per_post(buero_client):
    import uuid

    assert (
        buero_client.get(reverse("kunden:import_uebernehmen", args=[uuid.uuid4()])).status_code
        == 405
    )
