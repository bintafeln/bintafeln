"""Ausweis-Gestalter, Ausweis nach Vorlage und Sammeldruck (ADR 0027). Nur erfundene Daten."""

import datetime as dt
import io
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.konten import rollen
from apps.kunden import ausweis
from apps.kunden.models import AusweisVorlage, Haushalt, Kundengruppe, Person

pytestmark = pytest.mark.django_db
GESTALTEN = reverse("kunden:ausweis_gestalten")


def png(groesse=(20, 10)) -> bytes:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, "orange").save(puffer, "PNG")
    return puffer.getvalue()


@pytest.fixture
def gruppe():
    g = Kundengruppe.objects.create(name="Montag", wochentage="Mo")
    for nr, name in (("A-1", "Erika"), ("A-2", "Max")):
        h = Haushalt.objects.create(kundennummer=nr, kundengruppe=g,
                                    ausweis_gueltig_bis=dt.date(2027, 5, 1))  # fmt: skip
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname=name, nachname="Test")
    Haushalt.objects.create(kundennummer="B-1")
    return g


def test_elemente_pruefen():
    roh = [
        {"typ": "unbekannt"},
        "kein Element",
        {"typ": "barcode", "x": 80, "y": -3, "b": 5, "h": 2, "ausrichtung": "quer"},
        {"typ": "freitext", "text": "x" * 300, "groesse": 99, "farbe": "rot", "fett": 1},
        {"typ": "flaeche", "b": "breit"},
    ]
    e = ausweis.elemente_pruefen(roh)
    assert [x["typ"] for x in e] == ["barcode", "freitext", "flaeche", "kundennummer"]
    barcode, frei, flaeche, nummer = e
    assert (barcode["b"], barcode["h"]) == (ausweis.BARCODE_MIN_B, ausweis.BARCODE_MIN_H)
    assert barcode["x"] == round(ausweis.BREITE_MM - ausweis.BARCODE_MIN_B, 1)
    assert barcode["y"] == 0 and barcode["ausrichtung"] == "links"
    assert len(frei["text"]) == 200 and frei["groesse"] == 40 and frei["farbe"] == "#000000"
    assert frei["fett"] is True and flaeche["farbe"] == "#e8710a" and flaeche["b"] == 30
    assert ausweis.elemente_pruefen([])[-2:] == [
        ausweis.element_pruefen(s) for s in ausweis.STANDARD if s["typ"] in ("kundennummer",
                                                                               "barcode")
    ]  # fmt: skip
    assert (
        len(ausweis.elemente_pruefen([{"typ": "flaeche"}] * 100)) == ausweis.MAX_ELEMENTE + 2
    )  # plus Pflicht-Elemente


def test_text_mit_platzhaltern():
    w = {"kundennummer": "7", "gueltig_bis": "Gültig bis 01.01.2027"}
    e = {"typ": "freitext", "text": "Nr. {kundennummer}, {gueltig_bis} {unbekannt}"}
    assert ausweis.text_von(e, w) == "Nr. 7, Gültig bis 01.01.2027 {unbekannt}"
    assert ausweis.text_von({"typ": "hauptperson"}, {}) == ""


def test_nur_admin_gestaltet(client, admin, benutzer_mit_rolle, anmelden):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(GESTALTEN).status_code == 403


def test_gestalten_speichern_vorschau_standard(admin_client, pdf_text, gruppe):
    seite = admin_client.get(GESTALTEN).content.decode()
    assert 'id="ausweis-daten"' in seite and "ausweis_gestalter.js" in seite
    assert '"kundennummer"' in seite  # Standard-Elemente im versteckten Feld
    vorne = [
        {"typ": "freitext", "x": 4, "y": 4, "b": 60, "h": 6, "text": "Ausweis Nr. {kundennummer}"},
        {"typ": "flaeche", "x": 0, "y": 50, "b": 85.6, "h": 4, "farbe": "#1565c0"},
    ]
    daten = {
        "name": "Tafelausweis Testtafel",
        "seitenformat": "a4",
        "rueckseite_aktiv": "on",
        "vorne": json.dumps(vorne),
        "hinten": json.dumps([{"typ": "freitext", "text": "Öffnungszeiten Mo 10–12"}]),
    }
    vorschau = pdf_text(admin_client.post(GESTALTEN, {**daten, "vorschau": "1"}))
    assert "Ausweis Nr. 1234" in vorschau and "Mo 10" in vorschau
    assert AusweisVorlage.laden().vorderseite == []  # Vorschau speichert nicht
    antwort = admin_client.post(GESTALTEN, daten)
    assert antwort.status_code == 302
    v = AusweisVorlage.laden()
    assert v.name == "Tafelausweis Testtafel" and v.rueckseite_aktiv
    assert [e["typ"] for e in v.elemente_vorne()] == ["freitext", "flaeche", "kundennummer",
                                                      "barcode"]  # fmt: skip
    inhalt = pdf_text(admin_client.get(reverse("kunden:ausweis", args=["A-1"])))
    assert "Ausweis Nr. A-1" in inhalt and "Mo 10" in inhalt and "Beide Seiten" in inhalt
    admin_client.post(GESTALTEN, {**daten, "standard": "1"})
    v.refresh_from_db()
    assert v.vorderseite == [] and v.elemente_vorne() == ausweis.standard()
    kaputt = admin_client.post(GESTALTEN, {**daten, "vorne": "{kein json"}).content.decode()
    assert "nicht lesbar" in kaputt


def test_hintergrundbild_und_kartenformat(admin_client, pdf_text, gruppe):
    daten = {"name": "Ausweis", "seitenformat": "karte", "rueckseite_aktiv": "on",
             "vorne": "[]", "hinten": "[]",
             "hintergrund": SimpleUploadedFile("h.png", png(), "image/png")}  # fmt: skip
    admin_client.post(GESTALTEN, daten)
    v = AusweisVorlage.laden()
    assert v.hintergrund and str(v) == "Ausweis-Vorlage „Ausweis“"
    inhalt = pdf_text(admin_client.get(reverse("kunden:ausweis", args=["A-1"])))
    assert inhalt.count("/Type /Page\n") + inhalt.count("/Type /Page ") >= 2  # vorn und hinten
    assert "/Subtype /Image" in inhalt
    gross = SimpleUploadedFile("g.png", b"x" * (2 * 1024 * 1024 + 1), "image/png")
    fehler = admin_client.post(GESTALTEN, {**daten, "hintergrund": gross}).content.decode()
    assert "Bild" in fehler


def test_sammeldruck(admin_client, pdf_text, gruppe, monkeypatch):
    seite = admin_client.get(reverse("kunden:uebersicht"), {"gruppe": gruppe.pk}).content.decode()
    assert "Ausweise dieser 2 drucken" in seite
    url = reverse("kunden:ausweise")
    inhalt = pdf_text(admin_client.get(url, {"gruppe": gruppe.pk}))
    assert "A-1" in inhalt and "A-2" in inhalt and "B-1" not in inhalt
    leer = admin_client.get(url, {"q": "gibtsnicht"}, follow=True).content.decode()
    assert "Keine Haushalte ausgewählt." in leer
    monkeypatch.setattr("apps.kunden.views.MAX_SAMMELDRUCK", 1)
    zu_viele = admin_client.get(url, follow=True).content.decode()
    assert "Mehr als 1 Haushalte" in zu_viele


def test_sammeldruck_nicht_fuer_ausgabe(client, admin, benutzer_mit_rolle, anmelden, gruppe):
    anmelden(client, benutzer_mit_rolle("kim", rollen.AUSGABE))
    assert client.get(reverse("kunden:ausweise")).status_code == 403
    seite = client.get(reverse("kunden:uebersicht")).content.decode()
    assert "Ausweise dieser" not in seite
