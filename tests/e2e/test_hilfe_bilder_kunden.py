"""Bilder für das Handbuch: Kunden finden und bearbeiten, Ausgabestellen, Dokumente, Ausweise,
Auskunft, Kundenstamm importieren und Daten importieren (Werkzeug und Anleitung in
``hilfe_bilder.py``)."""

import datetime as dt
import re

import pytest
from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect

from apps.kunden.models import (
    Ausgabestelle,
    AusgabestelleKontakt,
    AusgabestelleZeit,
    Gruppenzeit,
    Haushalt,
    HaushaltEreignis,
    Kundengruppe,
    Nachricht,
    Person,
    Zugriff,
)
from tests.e2e.hilfe_bilder import Marke, aufnehmen, oeffnen

# Kleinstes gültiges PDF, erfunden für das Hochladen
PDF = (
    b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n%%EOF\n"
)


@pytest.fixture
def sicherung(settings, tmp_path):
    """Frische Server-Sicherung: keine Warnung, „Import übernehmen“ ist zu sehen."""
    zeitpunkt = timezone.now() - dt.timedelta(hours=1)
    pfad = tmp_path / "status.txt"
    pfad.write_text(
        f"ergebnis=ok\nletzte_erfolgreiche={zeitpunkt.strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
    )
    settings.SICHERUNG_STATUSDATEI = pfad


def _mehr_haushalte():
    """Weitere erfundene Haushalte neben 00042 (Fixture ``muster``)."""
    heute = timezone.localdate()
    nord = Ausgabestelle.objects.get(name="Ausgabestelle Nord")
    a = Kundengruppe.objects.get(kuerzel="A")
    b = Kundengruppe.objects.create(kuerzel="B", name="Gruppe B", ausgabestelle=nord,
                                    wochentage="Di, Do")  # fmt: skip
    for nummer, gruppe, vorname, nachname, geboren in (
        ("00043", a, "Jonas", "Probe", dt.date(1988, 6, 2)),
        ("00051", b, "Mia", "Beispiel", dt.date(1975, 1, 20)),
        ("00057", b, "Paul", "Mustermann", dt.date(1949, 11, 8)),
    ):
        h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe,
                                    ausweis_gueltig_bis=heute + dt.timedelta(days=200))  # fmt: skip
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname=vorname,
                              nachname=nachname, geburtsdatum=geboren)  # fmt: skip


def _stelle_mitte():
    mitte = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    mitte.strasse, mitte.plz, mitte.ort = "Musterweg 1", "12345", "Musterstadt"
    mitte.telefon, mitte.email = "0000 111111", "mitte@example.org"
    mitte.plaetze, mitte.helfer, mitte.barrierefrei = 60, 8, True
    mitte.anmerkung = "Eingang über den Hof, Parkplätze hinter dem Haus."
    mitte.save()
    AusgabestelleZeit.objects.create(ausgabestelle=mitte, wochentag=1, von=dt.time(9),
                                     bis=dt.time(11), art="Anlieferung")  # fmt: skip
    AusgabestelleZeit.objects.create(ausgabestelle=mitte, wochentag=1, von=dt.time(13),
                                     bis=dt.time(15, 30))  # fmt: skip
    AusgabestelleKontakt.objects.create(ausgabestelle=mitte, zustaendigkeit="Leitung",
                                        name="Hanna Beispiel", telefon="0000 222222")  # fmt: skip
    return mitte


# --- Kunden finden ----------------------------------------------------------------------


def test_hilfe_bild_kunden_finden(angemeldet, admin, muster):
    _mehr_haushalte()
    seite = oeffnen(angemeldet, admin, reverse("kunden:uebersicht") + "?tag=")
    karte = seite.locator("section.karte").first
    haken = seite.locator("tbody input[type=checkbox]").nth(1)
    haken.check()
    aufnehmen(seite, "kunden-finden-liste", karte,
              Marke(seite.locator("form.filter-kompakt"), "rahmen", 1),
              Marke(seite.locator("summary", has_text="Herunterladen"), "rahmen", 2),
              Marke(seite.get_by_text("Spalten wählen"), nummer=3, laenge=50),
              Marke(haken, nummer=4, laenge=50))  # fmt: skip

    seite.goto(reverse("kunden:haushalt", args=["00042"]))
    kopf = seite.locator("section.kunden-kopf")
    angaben = seite.locator("section.karte", has=seite.get_by_role("heading", name="Angaben"))
    aufnehmen(seite, "kunden-finden-haushalt", [kopf, angaben],
              Marke(seite.locator(".aktionsleiste"), "rahmen", 1),
              Marke(angaben.locator("dl.angaben"), "rahmen", 2))  # fmt: skip


# --- Haushalte bearbeiten ---------------------------------------------------------------


def test_hilfe_bild_kunden_bearbeiten(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("kunden:bearbeiten", args=["00042"]))
    seite.get_by_label("Straße und Hausnummer").fill("Musterweg 5")
    seite.get_by_label("PLZ", exact=True).fill("12345")
    seite.get_by_label("Ort", exact=True).fill("Musterstadt")
    titel = seite.get_by_role("link", name="← Haushalt 00042")
    speichern = seite.locator(".autosave-hinweis")  # kein Knopf: speichert sofort (ADR 0145)
    aufnehmen(seite, "kunden-bearbeiten-haushalt", [titel, speichern],
              Marke(seite.get_by_label("Ausweis gültig bis"), nummer=1, von="rechts", laenge=50),
              Marke(seite.get_by_label("Straße und Hausnummer"), nummer=2, von="rechts",
                    laenge=50),
              Marke(speichern, nummer=3, von="rechts", laenge=50))  # fmt: skip
    personen = seite.locator("section.karte", has=seite.get_by_role("heading", name="Personen"))
    aufnehmen(seite, "kunden-bearbeiten-personen", personen,
              Marke(personen.get_by_role("link", name="Max Muster"), nummer=1, von="rechts",
                    laenge=40),
              Marke(personen.get_by_role("link", name="Hinzufügen"), nummer=2, von="rechts",
                    laenge=40))  # fmt: skip


def test_hilfe_bild_kunden_nachrichten(angemeldet, admin, muster):
    _mehr_haushalte()
    nord = Ausgabestelle.objects.get(name="Ausgabestelle Nord")
    Nachricht.objects.create(kundennummer="00051", anliegen="adresse", von="Einlass",
                             stelle=nord, text="Neue Anschrift: Beispielgasse 4")  # fmt: skip
    Nachricht.objects.create(kundennummer="00042", anliegen="ausweis", von="Einlass",
                             stelle=Ausgabestelle.objects.get(name="Ausgabestelle Mitte"),
                             text="Ausweis ist verloren gegangen.")  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("kunden:nachrichten"))
    zeile = seite.locator("li.nachricht", has_text="00051")
    zeile.locator("summary", has_text="Antworten").click()
    zeile.locator("textarea").fill("Danke, ist eingetragen.")
    karte = seite.locator("section.karte").first
    aufnehmen(
        seite,
        "kunden-bearbeiten-nachrichten",
        karte,
        Marke(seite.locator("nav.nachrichten-reiter"), "rahmen", 1),
        Marke(zeile.get_by_role("button", name="✓ erledigt"), "rahmen", 2),
        Marke(zeile.get_by_role("button", name="Antwort senden"), "rahmen", 3),
    )
    # fmt: skip


def test_hilfe_bild_notizen_liste(angemeldet, admin, muster):
    """Liste aller Notizen: Bild fürs Handbuch und der Ablauf „anhaken, löschen“."""
    from apps.kunden.models import Notiz

    Notiz.objects.create(kundennummer="00042", text="Bringt eigene Taschen mit.",
                         verfasst_von="Büro")  # fmt: skip
    Notiz.objects.create(kundennummer="00042", text="Bitte den neuen Bescheid zeigen lassen.",
                         verfasst_von="Büro", an_stelle=True)  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("kunden:notizen"))
    karte = seite.locator("section.karte").first
    erste = seite.locator('tbody input[name="id"]').first
    erste.check()
    expect(seite.locator('[data-auswahl-zahl="auswahl"]')).to_have_text("1 ausgewählt")
    aufnehmen(seite, "notizen-liste", [karte],
              Marke(seite.locator("form.filter-kompakt"), "rahmen", 1),
              Marke(erste, nummer=2, von="links", laenge=30),
              Marke(seite.locator("[data-notizen-loeschen]"), "rahmen", 3),
              Marke(seite.locator(".listen-werkzeuge summary"), "rahmen", 4))  # fmt: skip
    vorher = Notiz.objects.count()
    seite.once("dialog", lambda d: d.accept())
    seite.locator("[data-notizen-loeschen]").click()
    expect(seite.get_by_text("1 Notiz in den Papierkorb gelegt.")).to_be_visible()
    assert Notiz.objects.count() == vorher - 1
    # ohne Haken: Hinweis statt Löschen
    seite.once("dialog", lambda d: d.accept())
    seite.locator("[data-notizen-loeschen]").click()
    assert Notiz.objects.count() == vorher - 1


def test_hilfe_bild_anmerkungen_liste(angemeldet, admin, muster):
    """Liste aller Anmerkungen: Bild fürs Handbuch und der Ablauf „anhaken, löschen“."""
    from apps.kunden.models import Bemerkung

    h = Haushalt.objects.get(kundennummer="00042")
    Bemerkung.objects.filter(haushalt=h).delete()
    for tag, text in ((3, "Zahlt den Beitrag für den ganzen Monat im Voraus."),
                      (10, "Neue Anschrift ab Dezember, Bescheid folgt.")):  # fmt: skip
        Bemerkung.objects.create(haushalt=h, datum=dt.date(2026, 11, tag), text=text,
                                 verfasst_von="Büro")  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("kunden:anmerkungen"))
    karte = seite.locator("section.karte").first
    erste = seite.locator('tbody input[name="id"]').first
    erste.check()
    aufnehmen(seite, "anmerkungen-liste", [karte],
              Marke(seite.locator("form.filter-kompakt"), "rahmen", 1),
              Marke(erste, nummer=2, von="links", laenge=30),
              Marke(seite.locator("[data-anmerkungen-loeschen]"), "rahmen", 3),
              Marke(seite.locator(".listen-werkzeuge summary"), "rahmen", 4))  # fmt: skip
    seite.once("dialog", lambda d: d.accept())
    seite.locator("[data-anmerkungen-loeschen]").click()
    expect(seite.get_by_text("1 Anmerkung in den Papierkorb gelegt.")).to_be_visible()
    assert Bemerkung.objects.filter(haushalt=h).count() == 1


def test_hilfe_bild_eulenpost(angemeldet, admin, muster):
    from apps.kunden import eulenpost

    mitte = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    alt = eulenpost.schreiben(
        [mitte], admin, "Neue Öffnungszeiten", "Ab Dezember öffnen wir um 10 Uhr."
    )
    eulenpost.gelesen(alt.empfaenge.get(), admin)
    eulenpost.schreiben(
        [mitte], admin, "Kühlware", "Morgen kommt keine Kühlware, bitte Bescheid geben."
    )
    seite = oeffnen(angemeldet, admin, reverse("kunden:postfach"))
    expect(seite.locator(".eulen-landeplatz.eule-gelandet")).to_be_visible(timeout=6000)
    seite.wait_for_timeout(700)  # Landung abwarten
    karte = seite.locator("section.karte").first
    aufnehmen(seite, "eulenpost", [seite.locator(".kopf-rechts"), karte],
              Marke(seite.locator(".eulen-landeplatz"), "rahmen", 1),
              Marke(karte.get_by_role("button", name="✓ Gelesen"), nummer=2, von="rechts",
                    laenge=40),
              Marke(seite.locator("[data-eulenton]"), "rahmen", 3))  # fmt: skip


def test_hilfe_bild_an_verwaltung(angemeldet, admin, muster):
    from apps.kunden.models import StellenNachricht

    mitte = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    admin.gewaehlte_stelle = mitte
    admin.save()
    StellenNachricht.objects.create(
        stelle=mitte, von="Einlass", betreff="Kühlschrank", text="Die Tür schließt nicht mehr.",
        antwort="Der Hausmeister kommt am Freitag.", antwort_von="Büro",
        beantwortet_am=timezone.now(), erledigt_am=timezone.now())  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("kunden:an_verwaltung"))
    seite.get_by_label("Betreff").fill("Schlüssel für das Lager")
    seite.get_by_label("Nachricht").fill("Wer hat diese Woche den Schlüssel für das Lager?")
    karten = seite.locator("section.karte")
    aufnehmen(seite, "an-verwaltung", [karten.nth(0), karten.nth(1)],
              Marke(seite.get_by_label("Betreff"), "rahmen", 1),
              Marke(seite.get_by_role("button", name="Nachricht senden"), nummer=2, von="rechts",
                    laenge=40),
              Marke(karten.nth(1).locator("li.nachricht").first, "rahmen", 3))  # fmt: skip


# --- Ausgabestellen ---------------------------------------------------------------------


def test_hilfe_bild_ausgabestellen(angemeldet, admin, muster):
    mitte = _stelle_mitte()
    seite = oeffnen(angemeldet, admin, reverse("kunden:ausgabestelle", args=[mitte.pk]))
    kopf = seite.locator("section.karte").first
    lage = seite.locator("section.karte", has=seite.get_by_role("heading", name="Lage"))
    titel = seite.get_by_role("heading", name="Anschrift und Kontakt")
    kontakt = seite.locator("section.karte", has=titel)
    aufnehmen(seite, "ausgabestellen-seite", [kopf, kontakt, lage],
              Marke(kontakt.get_by_role("link", name="0000 111111"), nummer=1, von="rechts",
                    laenge=50),
              Marke(lage.get_by_role("button", name="Karte anzeigen"), nummer=2, von="rechts",
                    laenge=40),
              Marke(seite.get_by_role("link", name="Bearbeiten"), "rahmen", 3))  # fmt: skip

    seite.get_by_role("link", name="Bearbeiten").click()
    zeiten = seite.locator("section.karte", has=seite.get_by_role("heading", name="Zeiten"))
    kontakte = seite.locator("section.karte",
                             has=seite.get_by_role("heading", name="Ansprechpartner"))  # fmt: skip
    aufnehmen(seite, "ausgabestellen-bearbeiten", [zeiten, kontakte],
              Marke(zeiten.locator("tbody tr").nth(2), "rahmen", 1),
              Marke(kontakte.locator("tbody tr").first.locator("select").nth(1), "rahmen", 2),
              rand=8)  # fmt: skip


# --- Dokumente --------------------------------------------------------------------------


def test_hilfe_bild_dokumente(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("kunden:haushalt", args=["00042"]))
    karte = seite.locator("#dokumente")
    karte.locator("summary", has_text="Dokument hochladen").click()
    karte.get_by_label("Dokumentart").select_option(label="Bescheid")
    karte.get_by_label("Dokumentdatum").fill("15.09.2026")
    datei = karte.locator("input[type=file]")
    datei.set_input_files([{"name": "bescheid.pdf", "mimeType": "application/pdf", "buffer": PDF}])
    aufnehmen(seite, "dokumente-hochladen", karte,
              Marke(karte.get_by_label("Dokumentart"), "rahmen", 1),
              Marke(karte.get_by_label("Dokumentdatum"), "rahmen", 2),
              Marke(datei, "rahmen", 3),
              Marke(karte.get_by_role("button", name="Hochladen"), nummer=4, von="rechts",
                    laenge=40))  # fmt: skip
    karte.get_by_role("button", name="Hochladen").click()
    karte = seite.locator("#dokumente")
    expect(karte.locator("tbody tr")).to_have_count(1)
    aufnehmen(seite, "dokumente-liste", karte,
              Marke(karte.get_by_role("link", name="Bescheid"), nummer=1, laenge=40),
              Marke(karte.locator("td[data-titel='Löschen am']"), "rahmen", 2),
              Marke(karte.get_by_role("button", name="löschen"), nummer=3, von="rechts",
                    laenge=40))  # fmt: skip


# --- Ausweise ---------------------------------------------------------------------------


def test_hilfe_bild_ausweis(angemeldet, admin, muster):
    _mehr_haushalte()
    seite = oeffnen(angemeldet, admin, reverse("kunden:uebersicht") + "?tag=")
    gruppe = Kundengruppe.objects.get(kuerzel="B")
    seite.select_option("#gruppe", str(gruppe.pk))
    expect(seite.locator("tbody tr")).to_have_count(2)
    karte = seite.locator("section.karte").first
    aufnehmen(seite, "ausweis-viele", karte,
              Marke(seite.locator("#gruppe"), "rahmen", 1),
              Marke(seite.get_by_role("button", name=re.compile("Ausweise drucken")),
                    nummer=2, von="rechts", laenge=60))  # fmt: skip

    seite.goto(reverse("kunden:ausweis_gestalten"))
    seite.select_option("#neu-typ", "merkmale")
    gestalter = seite.locator("#gestalter")
    expect(gestalter).to_be_visible()
    knoepfe = seite.get_by_role("button", name="Vorschau als PDF")
    aufnehmen(seite, "ausweis-gestalten", [gestalter, knoepfe],
              Marke(seite.locator(".ausweis-element", has_text="Erika Mustermann").first,
                    "rahmen", 1),
              Marke(seite.locator("#neu-typ"), "rahmen", 2),
              Marke(seite.locator("#neu-knopf"), nummer=3, von="rechts", laenge=30),
              Marke(knoepfe, "rahmen", 4))  # fmt: skip


# --- Auskunft, Historie, Zugriffsprotokoll ----------------------------------------------


def test_hilfe_bild_auskunft(angemeldet, admin, muster):
    jetzt = timezone.now()
    for tage, quelle, text, von in (
        (90, "import", "Neu aufgenommen (Import)", ""),
        (30, "bearbeitung", "Ausweis gültig bis: 31.01.2026 → 31.01.2027", "Clara Beispiel"),
        (2, "bearbeitung", "Person hinzugekommen: Max Muster", "Clara Beispiel"),
    ):
        HaushaltEreignis.objects.create(kundennummer="00042", quelle=quelle, text=text, von=von,
                                        zeitpunkt=jetzt - dt.timedelta(days=tage))  # fmt: skip
    Gruppenzeit.objects.create(kundennummer="00042", gruppe_name="Gruppe A",
                               kundengruppe=muster.kundengruppe,
                               von=timezone.localdate() - dt.timedelta(days=90))  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("kunden:haushalt", args=["00042"]))
    angaben = seite.locator("section.karte", has=seite.get_by_role("heading", name="Angaben"))
    aufnehmen(seite, "auskunft-haushalt", angaben,
              Marke(angaben.get_by_role("link", name=re.compile("Auskunft nach Art. 15")),
                    nummer=1, von="unten", laenge=40),
              Marke(angaben.get_by_role("link", name="Zugriffe auf diesen Haushalt"),
                    nummer=2, von="unten", laenge=40))  # fmt: skip
    historie = seite.locator("#historie")
    aufnehmen(seite, "auskunft-historie", historie,
              Marke(historie.locator("ul.historie li").nth(1), "rahmen", 1),
              Marke(historie.locator("table"), "rahmen", 2))  # fmt: skip

    for stunden, name, nummer in ((3, "lena.probe", "00042"), (26, "lena.probe", "00057")):
        Zugriff.objects.create(benutzername=name, kundennummer=nummer,
                               zeitpunkt=jetzt - dt.timedelta(hours=stunden))  # fmt: skip
    seite.goto(reverse("kunden:zugriffe"))
    seite.get_by_label("Kundennummer").fill("00042")
    seite.get_by_role("button", name="Filtern").click()
    karte = seite.locator("section.karte").first
    expect(karte.locator("tbody tr")).to_have_count(2)
    aufnehmen(seite, "auskunft-zugriffsprotokoll", karte,
              Marke(seite.get_by_label("Kundennummer"), nummer=1, von="unten", laenge=40),
              Marke(seite.get_by_role("button", name="Filtern"), nummer=2, von="rechts",
                    laenge=50))  # fmt: skip


# --- Kundenstamm importieren ------------------------------------------------------------


def test_hilfe_bild_import(angemeldet, admin, muster, sicherung):
    _mehr_haushalte()
    Haushalt.objects.filter(kundennummer="00043").update(ort="Beispielhausen")
    haushalte = "\n".join([
        "kundennummer;nachname;vorname;geburtsdatum;ort",
        "00042;Muster;Erika;12.04.1961;Musterstadt",
        "00043;Probe;Jonas;02.06.1988;Musterdorf",
        "00051;Beispiel;Mia;20.01.1975;",
        "00060;Probe;Jonas;02.06.1988;Musterdorf",
        "00061;Test;Lina;03.03.1980;Musterstadt",
    ]) + "\n"  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("datenimport:start") + "?ziel=kunden")
    seite.locator("#dateien").set_input_files(
        [{"name": "haushalte.csv", "mimeType": "text/csv", "buffer": haushalte.encode()}]
    )
    seite.get_by_role("button", name="Weiter zur Zuordnung").click()
    seite.get_by_role("button", name="Prüfen und abgleichen").click()
    expect(seite.get_by_role("heading", name="Kundenstamm ergänzen")).to_be_visible()
    titel = seite.get_by_role("link", name="← Daten importieren")
    konflikt = seite.locator("tr.unterschied", has_text="Ort").first
    dublette = seite.locator("tr.unterschied", has_text="Mögliche Dublette")
    aufnehmen(seite, "import-abgleich", [titel, seite.locator("tr", has_text="00061")],
              Marke(seite.locator("nav.reiter"), "rahmen", 1),
              Marke(konflikt.locator("input[type=checkbox]"), nummer=2, von="rechts",
                    laenge=60),
              Marke(dublette.locator("td[data-titel=Wahl]"), "rahmen", 3), rand=8)  # fmt: skip
    fehlt = seite.locator("details", has_text="Nicht mehr in der Datei")
    uebernehmen = seite.get_by_role("button", name="Import übernehmen")
    aufnehmen(seite, "import-uebernehmen", [fehlt, uebernehmen],
              Marke(fehlt.locator("select").first, nummer=1, von="rechts", laenge=50),
              Marke(uebernehmen, nummer=2, von="rechts", laenge=40))  # fmt: skip


# --- Daten importieren ------------------------------------------------------------------


def test_hilfe_bild_datenimport(angemeldet, admin, muster, sicherung):
    _stelle_mitte()
    datei = "\n".join([
        "Stelle;Straße;PLZ Ort;Tel.;Plätze",
        "Ausgabestelle Mitte;Musterweg 1;12345 Musterstadt;0000 999999;60",
        "Ausgabestelle Süd;Am Testplatz 3;12346 Musterdorf;0000 333333;40",
    ]) + "\n"  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("datenimport:start"))
    wahl = seite.locator("input[name=ziel][value=ausgabestellen]")
    wahl.check()
    seite.locator("#dateien").set_input_files(
        [{"name": "ausgabestellen.csv", "mimeType": "text/csv", "buffer": datei.encode()}]
    )
    karte = seite.locator("section.karte").first
    aufnehmen(seite, "datenimport-hochladen", karte,
              Marke(wahl, nummer=1, laenge=40),
              Marke(seite.locator("div.feld", has=seite.locator("#dateien")), "rahmen", 2),
              Marke(seite.get_by_role("button", name="Weiter zur Zuordnung"), nummer=3,
                    von="rechts", laenge=50))  # fmt: skip

    seite.get_by_role("button", name="Weiter zur Zuordnung").click()
    tabelle = seite.locator("section.karte", has=seite.locator("table.zuordnung")).first
    seite.locator("#vn-0").fill("Liste aus dem Altprogramm")
    pruefen = seite.get_by_role("button", name="Prüfen und abgleichen")
    aufnehmen(seite, "datenimport-zuordnen",
              [tabelle, seite.locator("section.karte", has=pruefen)],
              Marke(tabelle.locator("table.zuordnung select").nth(2), nummer=1, von="rechts",
                    laenge=50),
              Marke(seite.locator("#vn-0"), nummer=2, von="rechts", laenge=50),
              Marke(pruefen, "rahmen", 3))  # fmt: skip

    pruefen.click()
    konflikt = seite.locator("tr.unterschied").first
    expect(konflikt).to_be_visible()
    karte = seite.locator("section.karte").first
    fehlt = seite.locator("details", has_text="Nicht mehr in der Datei")
    aufnehmen(
        seite,
        "datenimport-abgleich",
        karte,
        Marke(seite.locator("nav.reiter"), "rahmen", 1),
        Marke(konflikt.locator("input[type=checkbox]"), nummer=2, von="rechts", laenge=60),
        Marke(fehlt.locator("select").first, nummer=3, von="rechts", laenge=50),
    )
    # fmt: skip


def test_nachrichten_auf_dem_handy(angemeldet, admin, muster):
    """Schmale Ansicht: Karten statt Tabelle, Erledigte eingeklappt."""
    nord = Ausgabestelle.objects.get(name="Ausgabestelle Nord")
    Nachricht.objects.create(kundennummer="00042", anliegen="sonstiges", von="Einlass",
                             stelle=nord)  # fmt: skip
    Nachricht.objects.create(kundennummer="00042", anliegen="sonstiges", von="Einlass",
                             erledigt_am=timezone.now(), erledigt_von="chefin")  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("kunden:nachrichten"), breite=390, hoehe=844)
    expect(seite.locator("nav.nachrichten-reiter")).to_contain_text("Sonstiges 1")
    expect(seite.locator("li.nachricht").first).to_be_visible()
    expect(seite.get_by_role("button", name="wieder öffnen")).to_be_hidden()
    seite.locator(".nachrichten-erledigt summary").click()
    expect(seite.get_by_role("button", name="wieder öffnen")).to_be_visible()
