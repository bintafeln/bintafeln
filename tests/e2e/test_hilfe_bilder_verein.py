"""Bilder für das Handbuch: Anträge, Aufnahme, Sonderaktionen, Adressbuch, Mitglieder,
Serienbriefe, Spenden, Zuwendungsbestätigungen, Statistik (Werkzeug und Anleitung in
``hilfe_bilder.py``)."""

import datetime as dt
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect

from apps.adressen.models import Adresse, AdressKategorie
from apps.antraege.models import Antrag, AntragEinstellungen, AntragPerson
from apps.ausgabe.models import Sonderaktion, SonderaktionAuswahl, Teilnahme
from apps.kunden.models import Abholung, Ausgabestelle, Einkommensart, Haushalt, Person
from apps.mitglieder.models import Mitglied
from apps.spenden.models import Spende, SpendenEinstellungen
from tests.e2e.hilfe_bilder import Marke, aufnehmen, oeffnen

JAHR = timezone.localdate().year


def _antrag(**mehr) -> Antrag:
    daten = {"vorname": "Erika", "nachname": "Muster", "geburtsdatum": dt.date(1961, 4, 12),
             "strasse": "Erfundene Gasse 1", "plz": "12345", "ort": "Musterstadt",
             "telefon": "0123 456789", "email": "erika@example.org", **mehr}  # fmt: skip
    return Antrag.objects.create(**daten)


def _spender():
    spender = AdressKategorie.objects.get(name="Spender")
    probe = Adresse.objects.create(art="person", anrede="Herr", vorname="Max", nachname="Probe",
                                   strasse="Lindenweg 2", plz="12345", ort="Musterstadt",
                                   email="max.probe@example.org",
                                   einwilligung_post=dt.date(JAHR, 1, 10))  # fmt: skip
    markt = Adresse.objects.create(organisation="Frischmarkt Beispiel", ansprechperson="Lena Test",
                                   strasse="Marktplatz 5", plz="12345", ort="Musterstadt",
                                   telefon="0123 98765")  # fmt: skip
    verein = Adresse.objects.create(organisation="Förderkreis Musterstadt", plz="12345",
                                    ort="Musterstadt")  # fmt: skip
    for a in (probe, markt, verein):
        a.kategorien.add(spender)
    return probe, markt, verein


def _ohne_menue(seite):
    """Menü einfahren, damit die Bilder nur den Inhalt zeigen (bleibt beim Seitenwechsel)."""
    seite.get_by_role("button", name="Menü einfahren").click()
    expect(seite.locator("nav.seitenmenue")).to_be_hidden()


# --- Anträge und Aufnahme ---------------------------------------------------------------------


def test_hilfe_bild_antrag_formular(seite, admin, muster):
    e = AntragEinstellungen.laden()
    e.aktiv = True
    e.save()
    seite.set_viewport_size({"width": 1000, "height": 860})
    seite.goto("/antrag/de/")
    hinweis = seite.locator("#sprach-hinweis")
    expect(hinweis).to_be_visible()
    seite.locator(".sprach-hinweis-zu").click()
    expect(hinweis).to_be_hidden()
    seite.get_by_label("Vorname").first.fill("Erika")
    seite.get_by_label("Nachname").first.fill("Muster")
    formular = seite.locator("form.antrag-formular")
    art = formular.locator("> .feld").first
    namen = formular.locator(".reihe-3").first
    aufnehmen(seite, "antraege-formular", [seite.locator("header.kopf"), art, namen],
              Marke(seite.locator("#sprache"), nummer=1, von="unten", laenge=40),
              Marke(art, "rahmen", 2),
              Marke(namen, "rahmen", 3))  # fmt: skip


def test_hilfe_bild_antraege_liste(angemeldet, admin, muster):
    _antrag(vorname="Jonas", nachname="Probe", geburtsdatum=dt.date(1990, 2, 1),
            email="jonas@example.org", staatsangehoerigkeit="deutsch")  # fmt: skip
    a = _antrag(staatsangehoerigkeit="deutsch")
    seite = oeffnen(angemeldet, admin, reverse("antraege:liste"), breite=1850)
    _ohne_menue(seite)
    zeile = seite.locator("tr", has=seite.get_by_role("link", name=a.nummer, exact=True))
    aufnehmen(seite, "antraege-liste", seite.locator("section.karte").first,
              Marke(seite.locator(".reiter"), "rahmen", 1),
              Marke(zeile.locator(".zeilen-aktionen"), "rahmen", 2),
              Marke(zeile.locator("a.aufnehmen"), nummer=3, von="rechts", laenge=40))  # fmt: skip


def _aufnahme_daten(muster):
    from apps.kunden.models import Kundengruppe

    stelle = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    Einkommensart.objects.create(bezeichnung="Bürgergeld", aktiv=True)
    muster.strasse, muster.plz, muster.ort = "Alte Straße 9", "12345", "Musterstadt"
    muster.save()
    gruppe = muster.kundengruppe
    gruppe.maximum = 40
    gruppe.save()
    Kundengruppe.objects.create(kuerzel="B", name="Gruppe B", ausgabestelle=stelle, maximum=40,
                                wochentage="Di, Do")  # fmt: skip
    a = _antrag(vorname="Muster", nachname="Erika", strasse="Neue Straße 7")
    AntragPerson.objects.create(antrag=a, vorname="Max", nachname="Muster",
                                geburtsdatum=dt.date(2014, 9, 3))  # fmt: skip
    return a


def test_hilfe_bild_aufnahme(angemeldet, admin, muster):
    a = _aufnahme_daten(muster)
    seite = oeffnen(angemeldet, admin, reverse("antraege:aufnahme", args=[a.pk]))
    _ohne_menue(seite)
    treffer = seite.locator('input[name="haushalt"][value="00042"]')
    treffer.check()
    weiter = seite.get_by_role("button", name="Weiter")
    aufnehmen(seite, "aufnahme-kunde", [seite.locator("section.karte").first,
                                         seite.locator(".aktionen")],
              Marke(treffer, nummer=1, von="oben", laenge=40),
              Marke(seite.locator("tr.zeile-neu"), "rahmen", 2),
              Marke(weiter, nummer=3, von="unten", laenge=30))  # fmt: skip
    weiter.click()
    seite.locator('input[name="wahl_strasse"][value="antrag"]').check()
    aufnehmen(seite, "aufnahme-abgleich", [seite.locator("form section.karte"),
                                            seite.locator(".aktionen")],
              Marke(seite.locator('input[name="wahl_vorname"][value="bestand"]'), nummer=1),
              Marke(seite.locator('input[name="wahl_strasse"][value="antrag"]'), nummer=2),
              Marke(seite.get_by_role("button", name="Weiter"), nummer=3, von="rechts",
                    laenge=40))  # fmt: skip


# --- Sonderaktionen ---------------------------------------------------------------------------


def test_hilfe_bild_sonderaktion(angemeldet, admin, muster):
    heute = timezone.localdate()
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:sonderaktion_neu"))
    _ohne_menue(seite)
    seite.get_by_label("Bezeichnung").fill("Weihnachtsaktion")
    seite.get_by_label("Von").fill(heute.isoformat())
    seite.get_by_label("Bis einschließlich").fill((heute + dt.timedelta(days=14)).isoformat())
    menge = seite.get_by_label("Wie viel je Haushalt")
    menge.select_option("je_kind")
    seite.get_by_label("Nur Haushalte mit Kindern").check()
    seite.get_by_label("Hinweis für den Einlass").fill("Nur gegen Unterschrift ausgeben")
    seite.get_by_label("Auswahlmöglichkeiten").fill("Spielzeug\nKleidung")
    aufnehmen(seite, "sonderaktionen-neu", seite.locator("section.karte").first,
              Marke(seite.locator(".formular-raster .feld").nth(0), "rahmen", 1),
              Marke(menge, "rahmen", 2),
              Marke(seite.get_by_label("Hinweis für den Einlass"), "rahmen", 3),
              Marke(seite.get_by_label("Auswahlmöglichkeiten"), "rahmen", 4),
              Marke(seite.get_by_role("button", name="Speichern"), nummer=5, von="rechts",
                    laenge=40))  # fmt: skip

    aktion = Sonderaktion.objects.create(bezeichnung="Schulranzen", von=heute,
                                         bis=heute + dt.timedelta(days=14),
                                         menge=Sonderaktion.Menge.JE_KIND)  # fmt: skip
    rot = SonderaktionAuswahl.objects.create(aktion=aktion, bezeichnung="Ranzen rot")
    blau = SonderaktionAuswahl.objects.create(aktion=aktion, bezeichnung="Ranzen blau")
    stelle = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    for nummer, wahl, stueck in (("00042", rot, 1), ("00057", blau, 2), ("00063", rot, 1)):
        Teilnahme.objects.create(aktion=aktion, kundennummer=nummer, auswahl=wahl,
                                 menge=stueck, ausgabestelle=stelle,
                                 eingetragen_von="Clara Beispiel")  # fmt: skip
    seite.goto(reverse("ausgabe:sonderaktion", args=[aktion.pk]))
    aufnehmen(seite, "sonderaktionen-ergebnis", seite.locator("section.karte").first,
              Marke(seite.locator("table.kompakt"), "rahmen", 1),
              Marke(seite.locator("table.tabelle").last, "rahmen", 2),
              Marke(seite.get_by_role("link", name="CSV-Export"), "rahmen", 3))  # fmt: skip


# --- Adressbuch und Mitglieder ----------------------------------------------------------------


def test_hilfe_bild_adressbuch(angemeldet, admin, muster):
    probe, _, _ = _spender()
    Mitglied.objects.create(adresse=probe, nummer="17", art="Aktives Mitglied",
                            eintritt=dt.date(2019, 5, 1))  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("adressen:liste"))
    _ohne_menue(seite)
    aufnehmen(seite, "adressbuch-liste", seite.locator("section.karte").first,
              Marke(seite.locator("#q"), "rahmen", 1),
              Marke(seite.locator("#verein"), nummer=2, von="unten", laenge=40),
              Marke(seite.locator("a.marke-rolle", has_text="Mitglied 17"), nummer=3,
                    von="oben", laenge=30),
              Marke(seite.get_by_role("link", name="+ Neue Adresse"), "rahmen", 4))  # fmt: skip


def test_hilfe_bild_mitglied_aufnehmen(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("adressen:neu") + "?mitglied=1")
    _ohne_menue(seite)
    seite.get_by_label("Vorname").first.fill("Lena")
    seite.get_by_label("Nachname").first.fill("Test")
    bereich = seite.locator("section.mitglied-wahl")
    haken = bereich.locator("label", has=seite.locator('input[name="ist_mitglied"]'))
    expect(haken.locator("input")).to_be_checked()
    bereich.scroll_into_view_if_needed()
    knopf = seite.get_by_role("button", name="Speichern")
    aufnehmen(seite, "mitglieder-aufnehmen", [bereich, knopf],
              Marke(haken.locator("input"), nummer=1, laenge=60),
              Marke(seite.locator("#id_m-nummer"), "rahmen", 2),
              Marke(seite.locator("#id_m-art"), "rahmen", 2),
              Marke(seite.locator("#id_m-eintritt"), "rahmen", 2),
              Marke(knopf, nummer=3, von="unten", laenge=30))  # fmt: skip


# --- Serienbriefe -----------------------------------------------------------------------------


def test_hilfe_bild_serienbrief(angemeldet, admin, muster):
    probe, markt, _ = _spender()
    markt.einwilligung_post = dt.date(JAHR, 1, 3)
    markt.save()
    Spende.objects.create(adresse=probe, datum=dt.date(JAHR, 2, 1), betrag=Decimal("150"))
    Spende.objects.create(adresse=markt, datum=dt.date(JAHR, 3, 1), betrag=Decimal("80"))
    seite = oeffnen(angemeldet, admin, reverse("serienbriefe:erstellen"), breite=1400)
    _ohne_menue(seite)
    seite.get_by_label("Vorlage").select_option(index=1)
    seite.get_by_label("Spender eines Jahres").check()
    felder = seite.locator("section.karte .formular-raster > .feld")
    aufnehmen(seite, "serienbriefe-auswahl", [felder.nth(0), felder.nth(3)],
              Marke(seite.locator("#id_vorlage"), "rahmen", 1),
              Marke(seite.locator("#id_quelle"), "rahmen", 2),
              Marke(seite.locator("#id_versandart"), "rahmen", 3))  # fmt: skip
    seite.get_by_role("button", name="Vorschau").click()
    pdf = seite.get_by_role("button", name="PDF mit 2 Briefen erzeugen")
    raster = seite.locator(".seiten-raster")
    aufnehmen(seite, "serienbriefe-vorschau", [seite.locator(".aktionsleiste"), raster],
              Marke(seite.get_by_role("button", name="Vorschau"), "rahmen", 1),
              Marke(raster, "rahmen", 2),
              Marke(pdf, nummer=3, von="rechts"))  # fmt: skip


# --- Spenden und Zuwendungsbestätigungen ------------------------------------------------------


def test_hilfe_bild_spende_erfassen(angemeldet, admin, muster):
    probe, _, _ = _spender()
    seite = oeffnen(angemeldet, admin, reverse("spenden:neu") + f"?adresse={probe.pk}",
                    breite=1250)  # fmt: skip
    _ohne_menue(seite)
    seite.get_by_label("Betrag").first.fill("50,00")
    seite.get_by_label("Zahlungsweg").select_option(index=1)
    abschnitte = seite.locator("fieldset.abschnitt")
    aufnehmen(seite, "spenden-erfassen", seite.locator("section.karte").first,
              Marke(seite.get_by_label("Spender (aus dem Adressbuch)"), "rahmen", 1),
              Marke(seite.get_by_label("Betrag").first, "rahmen", 2),
              Marke(seite.get_by_label("Zahlungsweg"), "rahmen", 2),
              Marke(abschnitte.nth(2).get_by_label("Bezeichnung"), "rahmen", 3),
              Marke(seite.get_by_role("button", name="Speichern und nächste Spende"), nummer=4,
                    von="unten", laenge=30))  # fmt: skip


def test_hilfe_bild_zuwendungsbestaetigungen(angemeldet, admin, muster):
    e = SpendenEinstellungen.laden()
    e.koerperschaft, e.anschrift = "Tafel Musterstadt e. V.", "Marktweg 1, 12345 Musterstadt"
    e.zwecke = "mildtätiger Zwecke im Sinne des § 53 AO"
    e.finanzamt, e.steuernummer = "Musterstadt", "12/345/67890"
    e.bescheid_vom, e.veranlagungszeitraum = dt.date(JAHR - 1, 3, 1), "2021 bis 2023"
    e.unterzeichnet_von, e.ort = "Clara Beispiel, Vorsitzende", "Musterstadt"
    e.save()
    probe, markt, verein = _spender()
    for tag in (dt.date(JAHR, 1, 15), dt.date(JAHR, 2, 15)):
        Spende.objects.create(adresse=probe, datum=tag, betrag=Decimal("50"))
    Spende.objects.create(adresse=markt, datum=dt.date(JAHR, 3, 2), betrag=Decimal("250"))
    Spende.objects.create(adresse=verein, datum=dt.date(JAHR, 4, 20), betrag=Decimal("100"))
    seite = oeffnen(angemeldet, admin, reverse("spenden:bestaetigungen"))
    _ohne_menue(seite)
    offen = seite.locator("section.karte").nth(1)
    zeile = offen.locator("tr", has_text="Probe")
    aufnehmen(seite, "zuwendungsbestaetigungen-ausstellen",
              [seite.locator("section.karte").first, offen],
              Marke(seite.locator("#jahr"), nummer=1, von="rechts", laenge=30),
              Marke(zeile.get_by_role("button", name="ausstellen"), nummer=2, von="rechts"),
              Marke(offen.get_by_role("button", name="Alle 3 ausstellen"), nummer=3,
                    von="rechts"),
              Marke(offen.locator(".marke-warnung"), nummer=4, von="rechts",
                    laenge=50))  # fmt: skip
    zeile.get_by_role("button", name="ausstellen").click()
    oeffnen_knopf = seite.get_by_role("link", name="Ausgestellte Bestätigungen als PDF öffnen")
    ausgestellt = seite.locator("section.karte").last
    aufnehmen(seite, "zuwendungsbestaetigungen-ausgestellt",
              [seite.locator("main.inhalt > *").first, ausgestellt],
              Marke(oeffnen_knopf, nummer=1, von="rechts"),
              Marke(ausgestellt.get_by_role("button", name="stornieren"), nummer=2,
                    von="rechts", laenge=50))  # fmt: skip


# --- Statistik --------------------------------------------------------------------------------


def test_hilfe_bild_statistik(angemeldet, admin, muster):
    heute = timezone.localdate()
    haushalte = [muster]
    for i, nummer in enumerate(("00057", "00063", "00071", "00078", "00085")):
        h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=muster.kundengruppe)
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Kim", nachname="Probe",
                              geburtsdatum=dt.date(1970 + 5 * i, 3, 1))  # fmt: skip
        haushalte.append(h)
    for monat in range(12):  # jeden Monat ein paar Abholungen mehr oder weniger
        j, m = divmod(heute.year * 12 + heute.month - 1 - monat, 12)
        tag = min(heute, dt.date(j, m + 1, 5))
        for h in haushalte[: 3 + (monat * 5) % 4]:
            Abholung.objects.create(haushalt=h, datum=tag)
    seite = oeffnen(angemeldet, admin, reverse("statistik:uebersicht"), breite=1400)
    _ohne_menue(seite)
    kopf = seite.locator(".statistik-kopf form")
    aufnehmen(seite, "statistik-kopf", seite.locator("section.karte").first,
              Marke(kopf.first, "rahmen", 1),
              Marke(seite.locator(".statistik-sprung"), "rahmen", 2),
              Marke(kopf.last, "rahmen", 3))  # fmt: skip
    abschnitt = seite.locator("section.statistik-abschnitt").first
    aufnehmen(seite, "statistik-abschnitt", abschnitt,
              Marke(abschnitt.locator(".liste-kopf > span"), "rahmen", 1),
              Marke(abschnitt.locator("summary").first, "rahmen", 2))  # fmt: skip
