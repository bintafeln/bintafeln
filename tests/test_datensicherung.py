"""Datenexport und Zurücklesen (ADR 0037). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.core import datensicherung as ds
from apps.core import privatdateien
from apps.konten import rollen
from apps.kunden.models import Dokumentart, Haushalt, HaushaltDokument, Kundengruppe, Person

pytestmark = pytest.mark.django_db
PW = "erfunden-und-lang"


@pytest.fixture
def bestand():
    g = Kundengruppe.objects.create(name="Montag")
    h = Haushalt.objects.create(kundennummer="100", kundengruppe=g)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Probe")
    return h


def test_export_und_lesen(bestand):
    datei = ds.exportieren(list(ds.BEREICHE), PW, "chefin")
    assert datei.startswith(ds.KOPF) and b"Erika" not in datei  # verschlüsselt
    inhalt = ds.lesen(datei, PW)
    assert inhalt["vollstaendig"] and inhalt["erstellt_von"] == "chefin"
    assert any(e["model"] == "kunden.person" and e["fields"]["vorname"] == "Erika"
               for e in inhalt["daten"])  # fmt: skip
    with pytest.raises(ds.DatensicherungsFehler, match="Passwort passt nicht"):
        ds.lesen(datei, "falsches-passwort")
    with pytest.raises(ds.DatensicherungsFehler, match="keine Exportdatei"):
        ds.lesen(b"irgendwas", PW)
    with pytest.raises(ds.DatensicherungsFehler, match="mindestens"):
        ds.exportieren(["kunden"], "kurz")
    with pytest.raises(ds.DatensicherungsFehler, match="Bereich"):
        ds.exportieren([], PW)


def test_aktualisieren_loescht_nichts(bestand):
    datei = ds.exportieren(["kunden"], PW)
    inhalt = ds.lesen(datei, PW)
    assert not inhalt["vollstaendig"]
    # danach geändert und ergänzt
    Person.objects.filter(vorname="Erika").update(vorname="Geändert")
    Haushalt.objects.create(kundennummer="200")
    v = ds.vorschau(inhalt)
    assert not v.andere_installation and any(z["vorhanden"] for z in v.zeilen)
    ds.zuruecklesen(inhalt)
    assert Person.objects.get().vorname == "Erika"  # überschrieben
    assert Haushalt.objects.filter(kundennummer="200").exists()  # nicht gelöscht
    with pytest.raises(ds.DatensicherungsFehler, match="vollständigen"):
        ds.zuruecklesen(inhalt, ersetzen=True)
    neu = Haushalt.objects.create(kundennummer="300")  # Nummernkreis läuft weiter
    assert neu.pk > max(e["pk"] for e in inhalt["daten"] if e["model"] == "kunden.haushalt")


def test_ersetzen_mit_dateien(bestand, admin):
    art = Dokumentart.objects.first()
    pdf = SimpleUploadedFile("b.pdf", b"%PDF erfunden", content_type="application/pdf")
    name = privatdateien.speichern(HaushaltDokument.ORDNER, pdf)
    HaushaltDokument.objects.create(kundennummer="100", art=art, titel="T", datei=name)
    datei = ds.exportieren(list(ds.BEREICHE), PW)
    inhalt = ds.lesen(datei, PW)
    assert any(p.startswith("privat/kunden-dokumente/") for p in inhalt["dateien"])

    Haushalt.objects.create(kundennummer="999")
    privatdateien.loeschen(HaushaltDokument.ORDNER, name)
    gezaehlt = ds.zuruecklesen(inhalt, ersetzen=True)
    assert not Haushalt.objects.filter(kundennummer="999").exists()
    assert Haushalt.objects.filter(kundennummer="100").exists() and gezaehlt["Dateien"] >= 1
    assert privatdateien.lesen(HaushaltDokument.ORDNER, name) == b"%PDF erfunden"


def test_neuere_version_abgelehnt(bestand):
    datei = ds.exportieren(["einstellungen"], PW)
    inhalt = ds.lesen(datei, PW)
    inhalt["migrationen"]["kunden"] = "9999_zukunft"
    import gzip
    import json
    import os

    salz = os.urandom(16)
    roh = gzip.compress(json.dumps(inhalt).encode())
    zukunft = ds.KOPF + salz + ds._schluessel(PW, salz).encrypt(roh)
    with pytest.raises(ds.DatensicherungsFehler, match="neueren"):
        ds.lesen(zukunft, PW)


def test_oberflaeche(client, admin_client, benutzer_mit_rolle, anmelden, bestand, monkeypatch):
    seite = admin_client.get(reverse("core:datensicherung")).content.decode()
    assert "Exportieren" in seite and "Zurücklesen" in seite and "Export und Zurücklesen</a>" in seite
    antwort = admin_client.post(reverse("core:daten_export"), {
        "bereiche": ["kunden", "einstellungen"], "passwort": PW, "passwort2": PW})  # fmt: skip
    assert antwort["Content-Disposition"].startswith('attachment; filename="bintafeln-export-')
    datei = antwort.content
    falsch = admin_client.post(reverse("core:daten_export"), {
        "bereiche": ["kunden"], "passwort": PW, "passwort2": "anders"}, follow=True)  # fmt: skip
    assert "stimmen nicht überein" in falsch.content.decode()

    Person.objects.update(vorname="Geändert")
    hochladen = {"datei": SimpleUploadedFile("x.bintafeln", datei), "passwort": PW}
    vorschau = admin_client.post(reverse("core:daten_pruefen"), hochladen, follow=True)
    inhalt = vorschau.content.decode()
    assert "Vorschau" in inhalt and "Teil:" in inhalt and "Vollständig ersetzen" not in inhalt
    falsch = admin_client.post(
        reverse("core:daten_pruefen"),
        {"datei": SimpleUploadedFile("x.bintafeln", datei), "passwort": "falsch"},
        follow=True,
    )
    assert "Passwort passt nicht" in falsch.content.decode()
    erledigt = admin_client.post(reverse("core:daten_uebernehmen"), {"modus": "aktualisieren"},
                                 follow=True)  # fmt: skip
    assert "nichts gelöscht" in erledigt.content.decode()
    assert Person.objects.get().vorname == "Erika"
    assert not list((ds.Path(ds.settings.MEDIA_ROOT) / "privat" / "datenimport").iterdir())

    # Vollständig ersetzen nur mit frischer Server-Sicherung und Bestätigung
    voll = ds.exportieren(list(ds.BEREICHE), PW)
    admin_client.post(
        reverse("core:daten_pruefen"),
        {"datei": SimpleUploadedFile("v.bintafeln", voll), "passwort": PW},
    )
    antwort = admin_client.post(reverse("core:daten_uebernehmen"),
                                {"modus": "ersetzen", "bestaetigt": "ja"}, follow=True)  # fmt: skip
    assert "Server-Sicherung von heute" in antwort.content.decode()
    from apps.core import sicherung

    monkeypatch.setattr(sicherung, "lese_status", lambda: sicherung.SicherungsStatus(
        sicherung.OK, timezone.now() - dt.timedelta(hours=1)))  # fmt: skip
    antwort = admin_client.post(reverse("core:daten_uebernehmen"), {"modus": "ersetzen"},
                                follow=True)  # fmt: skip
    assert "ausdrücklich bestätigen" in antwort.content.decode()
    antwort = admin_client.post(reverse("core:daten_uebernehmen"),
                                {"modus": "ersetzen", "bestaetigt": "ja"}, follow=True)  # fmt: skip
    assert "Daten ersetzt" in antwort.content.decode()
    admin_client.post(reverse("core:daten_verwerfen"))

    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))  # derselbe Client
    assert client.get(reverse("core:datensicherung")).status_code == 403
    assert client.post(reverse("core:daten_export"), {"passwort": PW}).status_code == 403


def test_fehlende_verweise_verstaendlich(bestand):
    inhalt = ds.lesen(ds.exportieren(["kunden"], PW), PW)
    Haushalt.objects.all().delete()
    Kundengruppe.objects.all().delete()
    with pytest.raises(ds.DatensicherungsFehler, match="Es wurde nichts verändert"):
        ds.zuruecklesen(inhalt)
    assert not Haushalt.objects.exists()
