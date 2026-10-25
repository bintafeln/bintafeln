"""Spenden-Import aus CSV (ADR 0055): Zuordnung der Spender, Belegnummer, Fehler, Oberfläche."""

from decimal import Decimal
from pathlib import Path

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.konten import rollen
from apps.spenden import importieren
from apps.spenden.models import Spende

pytestmark = pytest.mark.django_db
BEISPIEL = Path(__file__).parent.parent / "docs" / "beispiele" / "spenden" / "spenden.csv"
KOPF = (
    "datum;betrag;art;beschreibung;belegnummer;mitgliedsbeitrag;organisation;vorname;nachname;"
    "plz;email\n"
)


def test_beispieldatei():
    bericht = importieren.pruefen(BEISPIEL.read_text(encoding="utf-8"))
    assert not bericht.fehler and len(bericht.spenden) == 4
    assert len(bericht.neue_spender) == 3  # Erika zweimal, aber nur einmal angelegt
    assert bericht.summe == Decimal("150.00")
    assert importieren.uebernehmen(bericht, "test") == 4
    erika = Adresse.objects.get(nachname="Muster")
    assert erika.spenden.count() == 2 and erika.einwilligung_email is not None
    assert Spende.objects.get(belegnummer="MV-1004").art == Spende.Art.SACH
    # Dieselbe Datei noch einmal: alles schon da
    bericht = importieren.pruefen(BEISPIEL.read_text(encoding="utf-8"))
    assert bericht.spenden == [] and len(bericht.doppelt) == 4


def test_zuordnung_vorhandener_spender():
    per_mail = Adresse.objects.create(art=Adresse.Art.PERSON, vorname="Anna", nachname="Beispiel",
                                      plz="99999", email="Anna@Example.org")  # fmt: skip
    per_name = Adresse.objects.create(organisation="Bäckerei Beispiel", plz="12345")
    text = KOPF + (
        "01.02.2026;10,00;;;;;;Anna;Anders;11111;anna@example.org\n"
        "02.02.2026;20,00;;;;;Bäckerei Beispiel;;;12345;\n"
        "03.02.2026;5,00;;;;ja;;Neu;Spender;12345;neu@example.org\n"
        "04.02.2026;5,00;;;;nein;;Neu;Spender2;12345;NEU@example.org\n"
    )
    bericht = importieren.pruefen(text)
    assert bericht.vorhandene_spender == {per_mail.pk, per_name.pk}
    assert len(bericht.neue_spender) == 1  # gleiche E-Mail = derselbe neue Spender
    importieren.uebernehmen(bericht, "test")
    assert per_mail.spenden.get().betrag == Decimal("10.00")
    assert per_name.spenden.get().betrag == Decimal("20.00")
    neu = Adresse.objects.get(email="neu@example.org")
    assert neu.spenden.count() == 2 and neu.spenden.filter(mitgliedsbeitrag=True).count() == 1
    per_mail.refresh_from_db()
    assert per_mail.nachname == "Beispiel"  # vorhandene Adressen bleiben unverändert


def test_fehler_im_bericht():
    text = KOPF + (
        "kein Datum;10,00;;;;;;;Muster;1;\n"
        "01.01.2026;;;;;;;;Muster;1;\n"  # Geldspende ohne Betrag
        "01.01.2026;5,00;Gutschein;;;;;;Muster;1;\n"
        "01.01.2099;5,00;;;;;;;Muster;1;\n"
        "01.01.2026;5,00;;;;vielleicht;;;Muster;1;\n"
        "01.01.2026;5,00;;;;;;;;1;\n"  # weder Name noch Organisation
        "01.01.2026;5,00;;;;;;;Muster;1;keine-mail\n"
        "01.01.2026;5,00;;;B1;;;;Muster;1;\n"
        "01.01.2026;5,00;;;B1;;;;Muster;1;\n"
        ";;;;;;;;;;\n"
        f"01.01.2026;5,00;;;;;;;{'x' * 101};1;\n"
        f"01.01.2026;5,00;;;{'b' * 51};;;;Muster;1;\n"
        "01.01.2026;5,00;sach;;;;;;Muster;1;\n"  # Sachspende ohne Beschreibung
    )
    bericht = importieren.pruefen(text)
    gruende = dict(bericht.fehler)
    assert len(bericht.spenden) == 1 and len(bericht.fehler) == 11
    assert "kein Datum" in gruende[2] and "Betrag" in gruende[3] and "Gutschein" in gruende[4]
    assert "Zukunft" in gruende[5] and "Ja/Nein" in gruende[6] and "Nachname" in gruende[7]
    assert "E-Mail" in gruende[8] and "Zeile 9" in gruende[10]
    assert "nachname ist länger" in gruende[12] and "belegnummer ist länger" in gruende[13]


def test_kopf_und_leere_datei():
    with pytest.raises(importieren.ImportFehler, match="leer"):
        importieren.pruefen("")
    with pytest.raises(importieren.ImportFehler, match="datum"):
        importieren.pruefen("betrag;nachname\n1;x\n")
    with pytest.raises(importieren.ImportFehler, match="Zeilen"):
        zeilen = "".join("01.01.2026;1;x\n" for _ in range(importieren.MAX_ZEILEN + 1))
        importieren.pruefen("datum,betrag,nachname\n" + zeilen.replace(";", ","))
    bericht = importieren.pruefen("datum;betrag;nachname;foo\n01.01.2026;1;x;y\n")
    assert bericht.unbekannte_spalten == ["foo"] and len(bericht.spenden) == 1


def test_oberflaeche(admin_client):
    url = reverse("spenden:importieren")
    assert "Spenden importieren" in admin_client.get(url).content.decode()
    datei = SimpleUploadedFile("spenden.csv", BEISPIEL.read_bytes(), content_type="text/csv")
    seite = admin_client.post(url, {"datei": datei}).content.decode()
    assert "Prüfbericht" in seite and "4 Spenden übernehmen" in seite and "150,00" in seite
    antwort = admin_client.post(url, {"schritt": "uebernehmen"})
    assert antwort.status_code == 302 and Spende.objects.count() == 4
    assert Spende.objects.get(belegnummer="MV-1001").eingetragen_von == "chefin"
    # ohne geprüfte Datei
    antwort = admin_client.post(url, {"schritt": "uebernehmen"}, follow=True)
    assert "Keine geprüfte Datei" in antwort.content.decode()
    leer = SimpleUploadedFile("leer.csv", b"x;y\n1;2\n", content_type="text/csv")
    antwort = admin_client.post(url, {"datei": leer}, follow=True)
    assert "Spaltennamen" in antwort.content.decode()
    assert (
        reverse("spenden:importieren")
        in admin_client.get(reverse("spenden:liste")).content.decode()
    )


def test_rechte(admin, benutzer_mit_rolle, anmelden):
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert c.get(reverse("spenden:importieren")).status_code == 403


def test_belegnummer_im_formular(admin_client):
    a = Adresse.objects.create(organisation="Beispiel GmbH")
    daten = {"art": "geld", "adresse": a.pk, "datum": "01.02.2026", "betrag": "10,00",
             "belegnummer": "X-1"}  # fmt: skip
    admin_client.post(reverse("spenden:neu"), daten)
    assert Spende.objects.get().belegnummer == "X-1"
