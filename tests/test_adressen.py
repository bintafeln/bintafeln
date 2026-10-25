"""Adressbuch (ADR 0044). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.adressen import importieren
from apps.adressen.models import Adresse, AdressKategorie
from apps.core import suche
from apps.konten import rollen

pytestmark = pytest.mark.django_db
LISTE = reverse("adressen:liste")


@pytest.fixture
def markt():
    a = Adresse.objects.create(organisation="Frischmarkt Muster", ansprechperson="Frau Probe",
                               strasse="Marktweg 1", plz="12345", ort="Musterstadt",
                               email="info@frischmarkt.example")  # fmt: skip
    a.kategorien.set([AdressKategorie.objects.get(name="Lieferant/Markt")])
    return a


def test_vorgaben_und_name():
    assert list(AdressKategorie.objects.values_list("name", flat=True)) == [
        "Spender", "Lieferant/Markt", "Partner", "Presse", "Behörde"]  # fmt: skip
    p = Adresse(art=Adresse.Art.PERSON, anrede="Frau", vorname="Erika", nachname="Muster",
                strasse="Weg 2", plz="12345", ort="Musterstadt")  # fmt: skip
    assert p.name == "Erika Muster"
    assert p.anschrift_zeilen == ["Frau Erika Muster", "Weg 2", "12345 Musterstadt"]
    o = Adresse(organisation="Bäckerei Probe", ansprechperson="Herr Test", plz="1", ort="X")
    assert o.anschrift_zeilen == ["Bäckerei Probe", "Herr Test", "1 X"]


def test_anlegen_bearbeiten_loeschen(admin_client):
    neu = reverse("adressen:neu")
    seite = admin_client.get(neu).content.decode()
    assert "<legend>Anschrift und Kontakt</legend>" in seite and "Lieferant/Markt" in seite
    fehlt = admin_client.post(neu, {"art": "person", "vorname": "Erika"}).content.decode()
    assert "Bei einer Person ist der Nachname nötig." in fehlt
    spender = AdressKategorie.objects.get(name="Spender")
    antwort = admin_client.post(neu, {
        "art": "person", "anrede": "Frau", "vorname": "Erika", "nachname": "Muster",
        "plz": "12345", "ort": "Musterstadt", "kategorien": [spender.pk],
        "einwilligung_post": "2026-01-02",
    })  # fmt: skip
    a = Adresse.objects.get()
    assert antwort.url == reverse("adressen:adresse", args=[a.pk])
    assert a.geaendert_von == "chefin" and a.einwilligung_post == dt.date(2026, 1, 2)
    assert list(a.kategorien.all()) == [spender]
    seite = admin_client.get(antwort.url).content.decode()
    assert "Frau Erika Muster" in seite and "ja, seit 02.01.2026" in seite
    # Inaktive Kategorie bleibt bei der Adresse wählbar, fehlt aber bei neuen
    AdressKategorie.objects.filter(pk=spender.pk).update(aktiv=False)
    assert (
        "Spender" in admin_client.get(reverse("adressen:bearbeiten", args=[a.pk])).content.decode()
    )
    assert ">\n Spender" not in admin_client.get(neu).content.decode()
    admin_client.post(reverse("adressen:loeschen", args=[a.pk]))
    assert not Adresse.objects.exists()


def test_liste_filter_csv_auskunft(admin_client, markt, pdf_text):
    Adresse.objects.create(art="person", vorname="Max", nachname="Presse", ort="Anderswo")
    inhalt = admin_client.get(LISTE, {"q": "frisch"}).content.decode()
    assert "Frischmarkt Muster" in inhalt and "Max Presse" not in inhalt and "1 Adresse" in inhalt
    kat = AdressKategorie.objects.get(name="Lieferant/Markt").pk
    assert "Max Presse" not in admin_client.get(LISTE, {"kategorie": kat}).content.decode()
    assert "Frischmarkt" not in admin_client.get(LISTE, {"art": "person"}).content.decode()
    csv = admin_client.get(LISTE, {"csv": "1"})
    text = csv.content.decode("utf-8")
    assert text.startswith("﻿art;organisation") and "Frischmarkt Muster" in text
    assert ";Lieferant/Markt;" in text
    pdf = admin_client.get(reverse("adressen:auskunft", args=[markt.pk]))
    assert "Frischmarkt Muster" in pdf_text(pdf) and "Frau Probe" in pdf_text(pdf)


CSV = (
    "organisation;vorname;nachname;plz;ort;email;kategorien;einwilligung_post;quatsch\n"
    "Frischmarkt Muster;;;12345;Musterstadt;;Lieferant/Markt;;x\n"  # schon da (Name + PLZ)
    "Bäckerei Probe;;;12345;Musterstadt;;Spender, Neue Kategorie;01.02.2026;\n"
    ";Erika;Muster;12345;Musterstadt;erika@example.org;;;\n"
    ";Kaputt;;;;;;;\n"  # Person ohne Nachname
    "Firma;;;;;keine-mail;;;\n"
    ";Erika;Muster;99999;Woanders;ERIKA@example.org;;;\n"  # E-Mail schon in der Datei
    ";;;;;;;;\n"
)


def test_import_pruefen_und_uebernehmen(markt):
    bericht = importieren.pruefen(CSV)
    assert [d["organisation"] or d["nachname"] for d in bericht.neu] == ["Bäckerei Probe", "Muster"]
    assert [z for z, _ in bericht.vorhanden] == [2, 7]
    assert [z for z, _ in bericht.fehler] == [5, 6]
    assert "keine gültige E-Mail" in bericht.fehler[1][1]
    assert bericht.neue_kategorien == ["Neue Kategorie"] and bericht.unbekannte_spalten == [
        "quatsch"
    ]
    assert importieren.uebernehmen(bericht, "chefin") == 2
    b = Adresse.objects.get(organisation="Bäckerei Probe")
    assert b.art == "organisation" and b.einwilligung_post == dt.date(2026, 2, 1)
    assert sorted(k.name for k in b.kategorien.all()) == ["Neue Kategorie", "Spender"]
    assert Adresse.objects.get(nachname="Muster").art == "person"
    # Export lässt sich wieder einlesen: alles schon vorhanden
    zurueck = importieren.pruefen(importieren.exportieren(Adresse.objects.all()).lstrip("﻿"))
    assert not zurueck.neu and len(zurueck.vorhanden) == 3
    with pytest.raises(importieren.ImportFehler, match="Spaltennamen"):
        importieren.pruefen("a;b\n1;2\n")
    assert importieren.text_lesen("Bäckerei".encode("cp1252")) == "Bäckerei"


def test_import_oberflaeche(admin_client):
    url = reverse("adressen:importieren")
    datei = SimpleUploadedFile("adressen.csv", CSV.encode("cp1252"))
    bericht = admin_client.post(url, {"datei": datei}).content.decode()
    assert "Prüfbericht" in bericht and "3 Adressen übernehmen" in bericht
    assert not Adresse.objects.exists()
    erledigt = admin_client.post(url, {"schritt": "uebernehmen"}, follow=True).content.decode()
    assert "3 Adressen übernommen" in erledigt and Adresse.objects.count() == 3
    nochmal = admin_client.post(url, {"schritt": "uebernehmen"}, follow=True).content.decode()
    assert "Keine geprüfte Datei" in nochmal


def test_suche_und_rechte(client, admin, benutzer_mit_rolle, anmelden, markt):
    gruppen = {g.bereich: g for g in suche.suchen(admin, "frisch").gruppen}
    assert gruppen["adressen"].treffer[0].titel == "Frischmarkt Muster · Musterstadt"
    assert suche.suchen(admin, "ad probe").gruppen[0].bereich == "adressen"
    buero = benutzer_mit_rolle("berta", rollen.BUERO)
    anmelden(client, buero)
    assert client.get(LISTE).status_code == 200
    assert "Adressbuch</a>" in client.get(reverse("core:start")).content.decode()
    assert client.post(reverse("adressen:loeschen", args=[markt.pk])).status_code == 403
    client.logout()
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anmelden(client, anton)
    assert client.get(LISTE).status_code == 403
    assert not any(g.bereich == "adressen" for g in suche.suchen(anton, "frisch").gruppen)
