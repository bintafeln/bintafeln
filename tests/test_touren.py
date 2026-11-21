"""Modul Touren: Stationen, Import, Navigation, Übertragen ins Adressbuch (ADR 0147).
Alle Daten sind erfunden."""

from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.adressen.models import Adresse, AdressKategorie
from apps.core.models import TafelEinstellungen
from apps.touren import adressbuch, importieren
from apps.touren.models import Station

pytestmark = pytest.mark.django_db

KOPF = (
    "kennung;art;name;kette;strasse;hausnummer;plz;ort;ortsteil;email;email_lieferschein;"
    "abholtage;lieferschein;aktiv"
)


@pytest.fixture(autouse=True)
def modul_an():
    t = TafelEinstellungen.laden()
    t.module = ["touren"]
    t.save()


def station(**mehr):
    daten = {"kennung": "M-1", "art": "markt", "name": "Beispielmarkt Mitte",
             "strasse": "Musterstraße", "hausnummer": "1", "plz": "12345", "ort": "Musterstadt",
             **mehr}  # fmt: skip
    return Station.objects.create(**daten)


def csv(*zeilen, kopf=KOPF):
    return "\n".join([kopf, *zeilen]) + "\n"


# --- Import ------------------------------------------------------------------------------------


def test_import_legt_neue_an():
    text = csv(
        "M-1;Markt;Beispielmarkt Mitte;Beispielkette;Musterstraße;1;12345;Musterstadt;Mitte;"
        "markt@example.org;;Montag, Mi;ja;",
        "B-2;baeckerei;Bäckerei Probe;;Probeweg;7;12345;Musterstadt;;;;Sa;nein;ja",
    )
    bericht = importieren.pruefen(text)
    assert not bericht.fehler
    assert len(bericht.neu) == 2
    assert importieren.uebernehmen(bericht, "anton") == (2, 0)
    m = Station.objects.get(kennung="M-1")
    assert m.art == "markt" and m.abholtage == "Mo, Mi" and m.lieferschein and m.aktiv
    assert m.kette == "Beispielkette" and m.geaendert_von == "anton"
    b = Station.objects.get(kennung="B-2")
    assert b.art == "baeckerei" and not b.lieferschein


def test_import_aktualisiert_und_leere_zellen_aendern_nichts():
    station(telefon="0000 111", ortsteil="Mitte", email="alt@example.org")
    text = csv(
        "M-1;markt;Beispielmarkt Mitte;;Musterstraße;1;12345;Musterstadt;;neu@example.org;;;;"
    )
    bericht = importieren.pruefen(text)
    assert not bericht.neu
    assert len(bericht.geaendert) == 1
    zeile, name, felder, daten = bericht.geaendert[0]
    assert felder == ["E-Mail"]
    importieren.uebernehmen(bericht, "anton")
    s = Station.objects.get(kennung="M-1")
    assert s.email == "neu@example.org"
    assert s.telefon == "0000 111" and s.ortsteil == "Mitte"  # leer in der Datei: bleibt


def test_import_unveraendert_und_fehlende_bleiben():
    station()
    station(kennung="M-2", name="Zweiter Markt")
    bericht = importieren.pruefen(
        csv("M-1;markt;Beispielmarkt Mitte;;Musterstraße;1;12345;Musterstadt;;;;;;")
    )
    assert len(bericht.unveraendert) == 1 and not bericht.etwas_zu_tun
    assert Station.objects.filter(kennung="M-2").exists()


def test_import_meldet_fehler_je_zeile():
    text = csv(
        "X-1;tankstelle;Tanke;;Weg;1;12345;Musterstadt;;;;;;",
        "X-2;markt;Ohne Ort;;Weg;1;12345;;;;;;;",
        "X-3;markt;Falsche Mail;;Weg;1;12345;Musterstadt;;keine-mail;;;;",
        "X-4;markt;Falsche PLZ;;Weg;1;ABC;Musterstadt;;;;;;",
        "X-5;markt;Tage;;Weg;1;12345;Musterstadt;;;;irgendwann;;",
        "X-6;markt;Gut;;Weg;1;12345;Musterstadt;;;;;;",
        "X-6;markt;Doppelt;;Weg;1;12345;Musterstadt;;;;;;",
    )
    bericht = importieren.pruefen(text)
    zeilen = dict(bericht.fehler)
    assert set(zeilen) == {2, 3, 4, 5, 6, 8}
    assert "unbekannte Art" in zeilen[2] and "ort fehlt" in zeilen[3]
    assert "mehrfach" in zeilen[8]
    assert [d["kennung"] for d in bericht.neu] == ["X-6"]


def test_beispieldatei_der_dokumentation():
    from pathlib import Path

    from django.conf import settings

    roh = (Path(settings.BASE_DIR) / "docs/beispiele/touren/stationen.csv").read_bytes()
    bericht = importieren.pruefen(importieren.text_lesen(roh))
    assert not bericht.fehler and not bericht.unbekannte_spalten
    assert len(bericht.neu) == 4
    assert bericht.neu[0]["anfahrt"] == "Rampe hinten links; bitte klingeln"


def test_demo_daten():
    from apps.core import demo_daten

    demo_daten.touren()
    assert Station.objects.count() == len(demo_daten.STATIONEN)
    assert all(s.strasse and s.hausnummer for s in Station.objects.all())


def test_import_ohne_pflichtspalten():
    with pytest.raises(importieren.ImportFehler, match="plz"):
        importieren.pruefen("kennung;art;name;strasse;ort\nM-1;markt;A;B;C\n")


def test_import_koordinaten_nur_zusammen():
    kopf = "kennung;art;name;strasse;plz;ort;breite;laenge"
    gut = importieren.pruefen(csv("M-1;markt;A;Weg 1;12345;Musterstadt;51,45;7.01", kopf=kopf))
    assert gut.neu[0]["breite"] == Decimal("51.450000")
    schlecht = importieren.pruefen(csv("M-1;markt;A;Weg 1;12345;Musterstadt;51.45;", kopf=kopf))
    assert "zusammen" in schlecht.fehler[0][1]


def test_export_laesst_sich_zurueckspielen():
    station(abholtage="Mo, Fr", lieferschein=False, breite=Decimal("51.1"), laenge=Decimal("7.2"))
    text = importieren.exportieren(Station.objects.all()).lstrip("﻿")
    assert text.splitlines()[0] == ";".join(importieren.SPALTEN)
    bericht = importieren.pruefen(text)
    assert not bericht.fehler and not bericht.etwas_zu_tun


# --- Navigation --------------------------------------------------------------------------------


def test_navigation_mit_anschrift_oder_koordinaten():
    s = station()
    assert s.navigation.startswith("https://www.google.com/maps/dir/?api=1&destination=")
    assert "Musterstra%C3%9Fe+1%2C+12345+Musterstadt" in s.navigation
    s.breite, s.laenge = Decimal("51.450000"), Decimal("7.010000")
    assert s.navigation.endswith("destination=51.450000%2C7.010000")


# --- Adressbuch --------------------------------------------------------------------------------


def test_uebertragen_legt_organisation_an():
    s = station(ansprechpartner="Frau Muster", email="", email_lieferschein="ls@example.org",
                telefon="0000 222")  # fmt: skip
    adresse, neu = adressbuch.uebertragen(s, "anton")
    assert neu
    assert adresse.art == Adresse.Art.ORGANISATION
    assert adresse.organisation == "Beispielmarkt Mitte"
    assert adresse.strasse == "Musterstraße 1" and adresse.plz == "12345"
    assert adresse.email == "ls@example.org" and adresse.ansprechperson == "Frau Muster"
    assert [k.name for k in adresse.kategorien.all()] == ["Markt"]
    s.refresh_from_db()
    assert s.adresse == adresse
    # zweites Mal: nichts Neues
    assert adressbuch.uebertragen(s, "anton") == (adresse, False)
    assert Adresse.objects.count() == 1


def test_uebertragen_verknuepft_vorhandene():
    vorhanden = Adresse.objects.create(
        art=Adresse.Art.ORGANISATION, organisation="beispielmarkt mitte", plz="12345"
    )
    adresse, neu = adressbuch.uebertragen(station(), "anton")
    assert not neu and adresse == vorhanden
    assert Adresse.objects.count() == 1


def test_uebertragen_ohne_kategorie_bei_sonstiges_und_abgeschalteter():
    AdressKategorie.objects.create(name="Bäckerei", aktiv=False)
    a, _ = adressbuch.uebertragen(station(art="baeckerei"), "anton")
    b, _ = adressbuch.uebertragen(station(kennung="S-9", name="Etwas", art="sonstiges"), "anton")
    assert not a.kategorien.exists() and not b.kategorien.exists()


# --- Seiten ------------------------------------------------------------------------------------


@pytest.fixture
def buero(client, admin, benutzer_mit_rolle, anmelden):
    return anmelden(client, benutzer_mit_rolle("bernd", "Büro"))


@pytest.fixture
def fahrer(client, admin, benutzer_mit_rolle, anmelden):
    return anmelden(client, benutzer_mit_rolle("fritz", "Fahrer"))


def test_fahrer_sieht_und_navigiert_aber_bearbeitet_nicht(fahrer):
    s = station(anfahrt="Rampe hinten links")
    liste = fahrer.get(reverse("touren:stationen"))
    assert liste.status_code == 200
    assert s.navigation.replace("&", "&amp;") in liste.content.decode()
    seite = fahrer.get(reverse("touren:station", args=[s.pk])).content.decode()
    assert "Rampe hinten links" in seite and "Bearbeiten" not in seite
    assert fahrer.get(reverse("touren:bearbeiten", args=[s.pk])).status_code == 403
    assert fahrer.post(reverse("touren:uebertragen", args=[s.pk])).status_code == 403
    assert fahrer.get(reverse("touren:stationen"), {"format": "csv"}).status_code == 403
    assert "CSV herunterladen" not in liste.content.decode()


def test_liste_filtert(buero):
    station()
    station(kennung="B-1", name="Bäckerei Probe", art="baeckerei")
    station(kennung="A-1", name="Alter Markt", aktiv=False)
    seite = buero.get(reverse("touren:stationen"), {"art": "baeckerei"}).content.decode()
    assert "Bäckerei Probe" in seite and "Beispielmarkt" not in seite
    seite = buero.get(
        reverse("touren:stationen"), {"stand": "aktiv", "q": "markt"}
    ).content.decode()
    assert "Beispielmarkt" in seite and "Alter Markt" not in seite
    seite = buero.get(reverse("touren:stationen"), {"stand": "alle", "q": "markt"}).content.decode()
    assert "Alter Markt" in seite


def test_liste_als_csv(buero):
    station()
    antwort = buero.get(reverse("touren:stationen"), {"stand": "alle", "format": "csv"})
    assert antwort["Content-Type"].startswith("text/csv")
    assert "M-1;markt;Beispielmarkt Mitte" in antwort.content.decode("utf-8-sig")


def test_neu_anlegen_mit_vorgeschlagener_kennung(buero):
    station(kennung="S-4")
    seite = buero.get(reverse("touren:neu")).content.decode()
    assert 'value="S-5"' in seite
    antwort = buero.post(reverse("touren:neu"), {
        "name": "Hofladen Probe", "art": "lieferant", "kennung": "S-5", "strasse": "Feldweg",
        "plz": "12345", "ort": "Musterstadt", "abholtage": ["Di", "Do"], "lieferschein": "on",
        "aktiv": "on",
    })  # fmt: skip
    s = Station.objects.get(kennung="S-5")
    assert antwort.url == reverse("touren:station", args=[s.pk])
    assert s.abholtage == "Di, Do" and s.geaendert_von == "bernd"


def test_import_in_zwei_schritten(buero):
    datei = SimpleUploadedFile(
        "stationen.csv",
        csv("M-1;markt;Beispielmarkt Mitte;;Musterstraße;1;12345;Musterstadt;;;;;;").encode(),
    )
    seite = buero.post(reverse("touren:importieren"), {"datei": datei}).content.decode()
    assert "Prüfbericht" in seite and not Station.objects.exists()
    buero.post(reverse("touren:importieren"), {"schritt": "uebernehmen"})
    assert Station.objects.filter(kennung="M-1").exists()


def test_import_auf_der_seite_daten_importieren(buero):
    seite = buero.get(reverse("datenimport:start")).content.decode()
    assert reverse("touren:importieren") in seite


def test_ins_adressbuch_nur_mit_recht_adressen(buero, recht_nehmen):
    s = station()
    buero.post(reverse("touren:uebertragen", args=[s.pk]))
    assert Adresse.objects.count() == 1
    recht_nehmen("Büro", "adressen.bearbeiten")
    s2 = station(kennung="M-2", name="Zweiter Markt")
    assert buero.post(reverse("touren:uebertragen", args=[s2.pk])).status_code == 403


def test_alle_ins_adressbuch(buero):
    station()
    station(kennung="M-2", name="Zweiter Markt")
    station(kennung="M-3", name="Alter Markt", aktiv=False)
    buero.post(reverse("touren:alle_uebertragen"))
    assert Adresse.objects.count() == 2
    assert not Station.objects.get(kennung="M-3").adresse


def test_loeschen_in_den_papierkorb(buero):
    from apps.core.models import PapierkorbEintrag

    s = station()
    buero.post(reverse("touren:loeschen", args=[s.pk]))
    assert not Station.objects.exists()
    assert PapierkorbEintrag.objects.filter(art="Station").exists()


def test_suche_im_seitenkopf(admin):
    from apps.core import module

    treffer = module.suchen(admin, "beispiel", 10)
    assert treffer == []
    station()
    treffer = module.suchen(admin, "beispiel", 10)
    assert [t.titel for t in treffer] == ["Beispielmarkt Mitte"]


def test_modul_aus_keine_seiten(buero):
    t = TafelEinstellungen.laden()
    t.module = []
    t.save()
    assert buero.get(reverse("touren:stationen")).status_code == 404
