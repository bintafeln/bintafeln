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
    assert ">Probe</a>" in liste and '<td data-titel="Vorname">Max</td>' in liste
    assert "50,00 €" in liste
    csv = admin_client.get(reverse("spenden:liste"), {"jahr": "2026", "aktion": "csv"})
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


def test_spendenliste_nach_nachname_und_vorname_sortieren(admin_client):
    """Nachname und Vorname sind getrennte, einzeln sortierbare Spalten; Organisationen stehen
    mit ihrem Namen zwischen den Nachnamen."""

    def adresse(**angaben):
        return Adresse.objects.create(strasse="Weg 1", plz="12345", ort="Musterstadt", **angaben)

    zeta = adresse(art="person", vorname="Anna", nachname="Zeta")
    alpha = adresse(art="person", vorname="Zoe", nachname="Alpha")
    markt = adresse(organisation="Markt Beispiel")
    for nr, a in enumerate((zeta, alpha, markt), start=1):
        geld(a, dt.date(2026, 1, nr), "10")

    def reihenfolge(sort):
        seite = admin_client.get(reverse("spenden:liste"), {"jahr": 2026, "sort": sort})
        return [s.adresse.name for s in seite.context["seite"]]

    assert reihenfolge("spender") == ["Zoe Alpha", "Markt Beispiel", "Anna Zeta"]
    assert reihenfolge("-spender") == ["Anna Zeta", "Markt Beispiel", "Zoe Alpha"]
    assert reihenfolge("vorname")[-2:] == ["Anna Zeta", "Zoe Alpha"]  # ohne Vornamen zuerst
    assert reihenfolge("datum") == ["Anna Zeta", "Zoe Alpha", "Markt Beispiel"]
    inhalt = admin_client.get(reverse("spenden:liste"), {"jahr": 2026}).content.decode()
    assert "Nachname / Organisation" in inhalt and ">Markt Beispiel</a>" in inhalt


def test_bestaetigungen_fuer_angehakte_ausstellen_und_oeffnen(admin_client, einstellungen):
    """Auf der Seite lassen sich einzelne Spender anhaken: ausgestellt wird nur für sie, in der
    Reihenfolge der Seite; ebenso öffnet „Ausgewählte als PDF“ nur die angehakten."""
    spender = [Adresse.objects.create(art="person", vorname="V", nachname=name, strasse="Weg 1",
                                      plz="12345", ort="Musterstadt")
               for name in ("Alpha", "Beta", "Gamma")]  # fmt: skip
    for a in spender:
        geld(a, dt.date(2026, 2, 1), "20")
    alpha, beta, gamma = spender
    url = reverse("spenden:ausstellen") + "?jahr=2026"
    seite = admin_client.get(reverse("spenden:bestaetigungen"), {"jahr": 2026}).content.decode()
    assert 'name="adresse"' in seite and "Ausgewählte ausstellen" in seite
    assert "data-sortierbar" in seite and "Nachname / Organisation" in seite
    # nichts angehakt: Meldung, nichts ausgestellt
    antwort = admin_client.post(url, {"auswahl": "1"}, follow=True)
    assert "mindestens einen Spender anhaken" in antwort.content.decode()
    assert not Zuwendungsbestaetigung.objects.exists()
    # zwei angehakt, in der Reihenfolge der Seite (Gamma vor Alpha)
    admin_client.post(url, {"auswahl": "1", "adresse": [gamma.pk, alpha.pk]})
    assert [b.adresse for b in Zuwendungsbestaetigung.objects.order_by("nummer")] == [gamma, alpha]
    # der Knopf in der Zeile stellt nur diesen einen aus, auch wenn andere angehakt sind
    admin_client.post(url, {"einzeln": beta.pk, "adresse": [alpha.pk]})
    assert Zuwendungsbestaetigung.objects.count() == 3
    # „Alle“ gilt für alle offenen, auch mit Haken
    neu = Adresse.objects.create(art="person", nachname="Delta", strasse="Weg 1", plz="12345",
                                 ort="Musterstadt")  # fmt: skip
    geld(neu, dt.date(2026, 3, 1), "5")
    geld(alpha, dt.date(2026, 3, 2), "5")
    admin_client.post(url, {"alle": "1", "adresse": [neu.pk]})
    assert Zuwendungsbestaetigung.objects.count() == 5
    # ausgewählte als PDF: nur die angehakten, in der Reihenfolge der Seite
    nummern = [b.nummer for b in Zuwendungsbestaetigung.objects.order_by("nummer")]
    pdf = admin_client.get(reverse("spenden:pdf"), {"nr": [nummern[2], nummern[0]]})
    assert pdf.status_code == 200 and pdf["Content-Type"] == "application/pdf"
    assert f"zuwendungsbestaetigung-{nummern[2]}-bis-{nummern[0]}" in pdf["Content-Disposition"]
    leer = admin_client.get(reverse("spenden:pdf"), follow=True)
    assert "mindestens eine Bestätigung anhaken" in leer.content.decode()
    assert admin_client.get(reverse("spenden:pdf"), {"nummern": "9999"}).status_code == 404
