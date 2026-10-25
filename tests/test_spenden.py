"""Spenden und Zuwendungsbestätigungen (ADR 0045). Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.konten import rollen
from apps.spenden import bestaetigung as bst
from apps.spenden import worte
from apps.spenden.models import Spende, SpendenEinstellungen, Zuwendungsbestaetigung

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def einstellungen():
    e = SpendenEinstellungen.laden()
    e.koerperschaft, e.anschrift = "Tafel Musterstadt e. V.", "Marktweg 1, 12345 Musterstadt"
    e.zwecke = "mildtätiger Zwecke im Sinne des § 53 AO"
    e.finanzamt, e.steuernummer = "Musterstadt", "12/345/67890"
    e.bescheid_vom, e.veranlagungszeitraum = dt.date(2025, 3, 1), "2021 bis 2023"
    e.unterzeichnet_von, e.ort = "Erika Muster, Kassenwartin", "Musterstadt"
    e.save()
    return e


@pytest.fixture
def spender():
    return Adresse.objects.create(art="person", anrede="Herr", vorname="Max", nachname="Probe",
                                  strasse="Weg 2", plz="12345", ort="Musterstadt")  # fmt: skip


def geld(adresse, tag, betrag, **mehr):
    return Spende.objects.create(adresse=adresse, datum=tag, betrag=D(betrag), **mehr)


def test_worte():
    assert worte.zahl(1999) == "eintausendneunhundertneunundneunzig"
    assert worte.zahl(71) == "einundsiebzig" and worte.zahl(0) == "null"
    assert worte.zahl(1_250_000) == "eine Million zweihundertfünfzigtausend"
    assert worte.euro(D("150.50")) == "einhundertfünfzig Euro und fünfzig Cent"
    assert worte.euro(D("1")) == "ein Euro" and worte.euro(D("2001.01")) == (
        "zweitausendeins Euro und ein Cent")  # fmt: skip
    with pytest.raises(ValueError):
        worte.zahl(-1)


def test_fehlende_angaben_verhindern_bestaetigung(spender):
    geld(spender, dt.date(2026, 1, 5), "50")
    e = SpendenEinstellungen.laden()
    assert "Steuernummer" in e.fehlende_angaben()
    with pytest.raises(bst.BestaetigungsFehler, match="fehlen noch Angaben"):
        bst.geld_ausstellen(spender, 2026, "chefin")
    e.grundlage = e.Grundlage.FESTSTELLUNG
    assert "Veranlagungszeitraum" not in e.fehlende_angaben()


def test_einzel_und_sammelbestaetigung(einstellungen, spender, pdf_text, admin_client):
    andere = Adresse.objects.create(organisation="Bäckerei Probe", plz="1", ort="X")
    geld(spender, dt.date(2026, 1, 5), "50")
    geld(spender, dt.date(2026, 3, 1), "100.50", verzicht_aufwand=True)
    geld(spender, dt.date(2025, 12, 31), "20")  # anderes Jahr
    geld(andere, dt.date(2026, 2, 2), "30")
    assert [(a.name, s, n) for a, s, n in bst.jahresliste(2026)] == [
        ("Max Probe", D("150.50"), 2), ("Bäckerei Probe", D("30.00"), 1)]  # fmt: skip
    einstellungen.naechste_nummer = 7
    einstellungen.save()
    sammel = bst.geld_ausstellen(spender, 2026, "chefin")
    assert (sammel.nummer, sammel.art, sammel.betrag) == (7, "sammel", D("150.50"))
    einzel = bst.geld_ausstellen(andere, 2026, "chefin")
    assert (einzel.nummer, einzel.art) == (8, "geld")
    with pytest.raises(bst.BestaetigungsFehler, match="keine unbestätigten"):
        bst.geld_ausstellen(spender, 2026, "chefin")  # nie doppelt
    assert bst.jahresliste(2026) == []

    antwort = admin_client.get(reverse("spenden:pdf"), {"nummern": "7,8"})
    text = pdf_text(antwort)
    assert "Sammelbestätigung über Geldzuwendungen/Mitgliedsbeiträge" in text
    assert "einhundertfünfzig Euro und fünfzig Cent" in text and "05.01.2026 bis 01.03.2026" in text
    assert "Anlage zur Sammelbestätigung Nr. 7" in text and "Herr Max Probe" in text
    assert "12/345/67890" in text and "§ 63 Abs. 5 AO" in text and "dreißig Euro" in text

    # Storno: Nummer bleibt, Spenden lassen sich neu bestätigen
    bst.stornieren(sammel, "chefin")
    assert "STORNIERT" in pdf_text(admin_client.get(reverse("spenden:pdf"), {"nummern": "7"}))
    neu = bst.geld_ausstellen(spender, 2026, "chefin")
    assert neu.nummer == 9 and Zuwendungsbestaetigung.objects.count() == 3


def test_sachspende(einstellungen, spender, pdf_text, admin_client):
    s = Spende.objects.create(adresse=spender, art="sach", datum=dt.date(2026, 4, 1),
                              beschreibung="Kühlschrank, 2 Jahre alt, sehr gut", herkunft="privat",
                              unterlagen=True)  # fmt: skip
    with pytest.raises(bst.BestaetigungsFehler, match="Ohne Wert"):
        bst.sach_ausstellen(s, "chefin")
    s.betrag = D("120")
    s.save()
    b = bst.sach_ausstellen(s, "chefin")
    text = pdf_text(admin_client.get(reverse("spenden:pdf"), {"nummern": b.nummer}))
    assert "Bestätigung über Sachzuwendungen" in text and "Kühlschrank" in text
    assert "aus dem Privatvermögen" in text and "einhundertzwanzig Euro" in text


def test_mitgliedsbeitraege_nicht_abziehbar(einstellungen, spender):
    geld(spender, dt.date(2026, 1, 5), "24", mitgliedsbeitrag=True)
    assert bst.jahresliste(2026)
    einstellungen.mitgliedsbeitraege_abziehbar = False
    einstellungen.save()
    assert bst.jahresliste(2026) == []


def test_oberflaeche(admin_client, einstellungen, spender, pdf_text):
    neu = reverse("spenden:neu")
    seite = admin_client.get(neu, {"adresse": spender.pk}).content.decode()
    assert f'<option value="{spender.pk}" selected>' in seite and "Überweisung" in seite
    fehlt = admin_client.post(neu, {"art": "geld", "adresse": spender.pk, "datum": "2026-01-05"})
    assert "Bei einer Geldspende bitte den Betrag angeben." in fehlt.content.decode()
    antwort = admin_client.post(neu, {"art": "geld", "adresse": spender.pk, "datum": "2026-01-05",
                                      "betrag": "50,00", "zahlungsweg": "Überweisung"})  # fmt: skip
    assert antwort.url == reverse("adressen:adresse", args=[spender.pk])
    s = Spende.objects.get()
    assert s.betrag == D("50") and s.eingetragen_von == "chefin"
    adresse = admin_client.get(antwort.url).content.decode()
    assert "Geldspenden je Jahr" in adresse and "50,00 €" in adresse
    liste = admin_client.get(reverse("spenden:liste"), {"jahr": "2026"}).content.decode()
    assert "Max Probe" in liste and "50,00 €" in liste
    csv = admin_client.get(reverse("spenden:liste"), {"jahr": "2026", "csv": "1"})
    assert "Max Probe;12345;Musterstadt;50,00" in csv.content.decode()
    # Alle ausstellen, dann PDF-Link
    url = reverse("spenden:ausstellen") + "?jahr=2026"
    seite = admin_client.post(url, follow=True).content.decode()
    assert "1 Zuwendungsbestätigung ausgestellt" in seite and "nummern=1" in seite
    # Bestätigte Spende: nicht mehr änderbar, Adresse nicht löschbar
    assert admin_client.get(reverse("spenden:bearbeiten", args=[s.pk])).status_code == 302
    admin_client.post(reverse("spenden:loeschen", args=[s.pk]))
    assert Spende.objects.exists()
    admin_client.post(reverse("adressen:loeschen", args=[spender.pk]))
    assert Adresse.objects.filter(pk=spender.pk).exists()
    auskunft = pdf_text(admin_client.get(reverse("adressen:auskunft", args=[spender.pk])))
    assert "Zuwendungsbestätigungen" in auskunft and "Nr. 1" in auskunft
    # Einstellungen
    seite = admin_client.get(reverse("spenden:einstellungen")).content.decode()
    assert "Steuerbegünstigte Zwecke" in seite


def test_rechte(client, admin, benutzer_mit_rolle, anmelden, spender):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(reverse("spenden:liste")).status_code == 200
    assert client.get(reverse("spenden:bestaetigungen")).status_code == 200
    assert client.get(reverse("spenden:einstellungen")).status_code == 403
    client.logout()
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(reverse("spenden:liste")).status_code == 403
