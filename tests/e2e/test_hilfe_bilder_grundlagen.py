"""Bilder für das Handbuch: Grundlagen und Einlass (Anmelden, Suche, Zwei-Faktor, Papierkorb,
Scannen, Ampel, Bezahlen, Notizen, Sonderaktionen, Korrekturen, Ausnahme, Kasse). Werkzeug und
Anleitung in ``hilfe_bilder.py``."""

import datetime as dt
import re
from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
from playwright.sync_api import expect

from apps.ausgabe import korrekturen
from apps.ausgabe.models import (
    Abholung,
    AusgabeEinstellungen,
    Sonderaktion,
    SonderaktionAuswahl,
)
from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.konten.models import AnmeldeEinstellungen
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe, Person
from tests.conftest import PASSWORT
from tests.e2e.hilfe_bilder import BREITE, HOEHE, Marke, aufnehmen, oeffnen

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _ohne_ueberraschung():
    """Die Festtags-Figuren (z. B. Fledermäuse um Halloween) gehören nicht ins Handbuch-Bild."""
    e = AnmeldeEinstellungen.laden()
    e.ueberraschungen = False
    e.save()


def _animationen_abwarten(seite):
    seite.evaluate("() => Promise.all(document.getAnimations().map(a => a.finished))")


def _einlass_konto(benutzer_mit_rolle):
    """Ein Konto mit der Rolle Ausgabe an der Ausgabestelle Mitte (ohne Rücknahme-Recht)."""
    b = benutzer_mit_rolle("anna", rollen.AUSGABE)
    b.first_name, b.last_name = "Anna", "Probe"
    b.gewaehlte_stelle = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    b.save()
    return b


def _haushalt(nummer, vorname, nachname, geburt, gruppe=None, tage=150):
    gueltig = timezone.localdate() + dt.timedelta(days=tage)
    gruppe = gruppe or Kundengruppe.objects.get(kuerzel="A")
    h = Haushalt.objects.create(kundennummer=nummer, ausweis_gueltig_bis=gueltig,
                                kundengruppe=gruppe)  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname=vorname, nachname=nachname,
                          geburtsdatum=geburt)  # fmt: skip
    return h


def _kunde(seite, nummer):
    seite.goto(reverse("ausgabe:empfang") + f"?nummer={nummer}")
    expect(seite.locator(".einlass-leiste")).to_be_visible()


def _abholung(seite, nummer, gezahlt=None):
    _kunde(seite, nummer)
    if gezahlt is not None:
        seite.fill("#bar", gezahlt)
    seite.get_by_role("button", name="✓ Abholung eintragen").click()
    expect(seite.get_by_text(f"Kunde {nummer}: Abholung eingetragen")).to_be_visible()


# --- Erste Schritte, Suche, Zwei-Faktor, Papierkorb ---


def test_hilfe_bild_erste_schritte(seite, admin, muster):
    _ohne_ueberraschung()
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("konten:anmelden"))
    seite.get_by_label("Benutzername").fill("clara")
    seite.get_by_label("Passwort").fill("vier zufällige Wörter")
    _animationen_abwarten(seite)
    karte = seite.locator("section.karte").first
    aufnehmen(seite, "erste-schritte-anmelden", karte,
              Marke(seite.get_by_label("Benutzername"), nummer=1, von="rechts"),
              Marke(seite.get_by_label("Passwort"), nummer=2, von="rechts"),
              Marke(seite.get_by_role("button", name="Anmelden"), nummer=3,
                    von="rechts"))  # fmt: skip


def test_hilfe_bild_erste_schritte_startseite(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("core:start"))
    menue = seite.get_by_role("navigation", name="Hauptnavigation")
    aufnehmen(seite, "erste-schritte-startseite", [seite.locator(".kopf"), menue],
              Marke(menue.locator("summary", has_text="Einstellungen").first, nummer=1,
                    von="rechts", laenge=60),
              Marke(seite.locator(".menue-einfahren"), nummer=2, von="rechts"),
              Marke(seite.get_by_role("navigation", name="Konto"), nummer=3, von="unten",
                    laenge=50))  # fmt: skip


def test_hilfe_bild_suche(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("core:start"))
    feld = seite.locator("#kopf-suche")
    feld.fill("Muster")
    treffer = seite.locator("#kopf-suche-liste a", has_text="Erika").first
    expect(treffer).to_be_visible()
    liste = seite.locator("#kopf-suche-liste > *").first
    aufnehmen(seite, "suche-kopf", [seite.locator(".kopf"), liste],
              Marke(feld, nummer=1, von="unten", laenge=50),
              Marke(treffer, nummer=2, von="rechts"))  # fmt: skip


def test_hilfe_bild_zwei_faktor(seite, admin, muster, benutzer_mit_rolle):
    _ohne_ueberraschung()
    anna = _einlass_konto(benutzer_mit_rolle)
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("konten:anmelden"))
    seite.get_by_label("Benutzername").fill(anna.username)
    seite.get_by_label("Passwort").fill(PASSWORT)
    seite.get_by_role("button", name="Anmelden").click()
    expect(seite.get_by_role("navigation", name="Hauptnavigation")).to_be_visible()
    seite.goto(reverse("konten:mein_konto"))
    kachel = seite.locator(".konto-kachel", has=seite.get_by_role("heading", name="Zwei-Faktor"))
    knopf = kachel.get_by_role("link", name="Jetzt einrichten")
    aufnehmen(seite, "zwei-faktor-konto", [seite.locator(".kopf-rechts"), kachel],
              Marke(seite.get_by_role("navigation", name="Konto"), nummer=1, von="unten",
                    laenge=50),
              Marke(knopf, nummer=2, von="rechts"))  # fmt: skip
    knopf.click()
    karte = seite.locator("section.karte").first
    aufnehmen(seite, "zwei-faktor-einrichten", karte,
              Marke(seite.locator(".qr-code"), "rahmen", 1),
              Marke(seite.get_by_role("textbox").first, nummer=2, von="rechts"),
              Marke(seite.get_by_role("button", name="Bestätigen"), nummer=3,
                    von="rechts"))  # fmt: skip


def test_hilfe_bild_zwei_faktor_code(seite, admin, muster):
    _ohne_ueberraschung()
    e = AnmeldeEinstellungen.laden()
    e.vertrauen_tage = 30
    e.save()
    TOTPDevice.objects.create(user=admin, name="Handy", confirmed=True)
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("konten:anmelden"))
    seite.get_by_label("Benutzername").fill(admin.username)
    seite.get_by_label("Passwort").fill(PASSWORT)
    seite.get_by_role("button", name="Anmelden").click()
    expect(seite.get_by_role("heading", name="Zwei-Faktor-Code")).to_be_visible()
    seite.get_by_label("Code").fill("123456")
    aufnehmen(seite, "zwei-faktor-code", seite.locator("section.karte").first,
              Marke(seite.get_by_label("Code"), nummer=1, von="rechts"),
              Marke(seite.get_by_label(re.compile("Diesem Gerät")), nummer=2),
              Marke(seite.get_by_role("button", name="Anmelden"), nummer=3, von="unten",
                    laenge=40))  # fmt: skip


def test_hilfe_bild_papierkorb(angemeldet, admin, muster):
    from apps.kunden.entfernen import haushalt_loeschen

    h = _haushalt("00057", "Jonas", "Probe", dt.date(1990, 2, 1))
    haushalt_loeschen(admin, h)
    seite = oeffnen(angemeldet, admin, reverse("core:start"))
    menue = seite.get_by_role("navigation", name="Hauptnavigation")
    eintrag = menue.get_by_role("link", name=re.compile("Papierkorb"))
    aufnehmen(seite, "papierkorb-menue", eintrag, Marke(eintrag, nummer=1, von="rechts"))
    eintrag.click()
    tabelle = seite.locator("table.tabelle")
    link = tabelle.get_by_role("link", name=re.compile("00057"))
    aufnehmen(seite, "papierkorb-liste", seite.locator("section.karte").first,
              Marke(link, nummer=1, von="unten", laenge=50),
              Marke(tabelle.get_by_role("button", name="Wiederherstellen"), nummer=2,
                    von="unten", laenge=50))  # fmt: skip
    link.click()
    karte = seite.locator("section.karte").first
    aufnehmen(seite, "papierkorb-eintrag", karte,
              Marke(seite.get_by_role("button", name="Wiederherstellen"), nummer=1, laenge=60),
              Marke(seite.get_by_role("button", name="Endgültig löschen"), nummer=2,
                    von="rechts"),
              Marke(karte.locator("details").first, "rahmen", 3))  # fmt: skip


# --- Einlass ---


def test_hilfe_bild_scannen(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    feld = seite.get_by_label("Kundennummer scannen oder eingeben")
    kamera = seite.get_by_role("button", name=re.compile("Kamera"))
    aufnehmen(seite, "scannen-feld", seite.locator(".empfang-kopf"),
              Marke(feld, nummer=1, von="unten", laenge=50),
              Marke(kamera, nummer=2, von="rechts"))  # fmt: skip


def _ampel(seite, name, *marken):
    aufnehmen(seite, name, [seite.locator(".einlass-leiste"), seite.locator(".ampel-grafik"),
                            seite.locator("section.ampel").first],
              Marke(seite.locator(".ampel-grafik"), "rahmen", 1),
              Marke(seite.locator("section.ampel").first, "rahmen", 2), *marken)  # fmt: skip


def test_hilfe_bild_ampel(angemeldet, admin, muster):
    _haushalt("00057", "Jonas", "Probe", dt.date(1990, 2, 1), tage=9)
    _haushalt("00063", "Mia", "Beispiel", dt.date(1985, 6, 20), tage=-3)
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    _kunde(seite, "00057")
    expect(seite.locator("section.ampel-gelb")).to_be_visible()
    _ampel(seite, "ampel-gelb", Marke(seite.get_by_role("button", name="✓ Abholung eintragen"),
                                      nummer=3, von="oben", laenge=30))  # fmt: skip
    _kunde(seite, "00063")
    expect(seite.locator("section.ampel-rot")).to_be_visible()
    _ampel(seite, "ampel-rot")


def test_hilfe_bild_bezahlen(angemeldet, admin, muster):
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_person = Decimal("1.50")
    e.max_je_tag = 1
    e.max_abholungen = 1
    e.zeitraum = AusgabeEinstellungen.Zeitraum.MONAT  # kein Vorschlag „Vorauszahlung“ im Bild
    e.anschreiben_erlaubt = True
    e.save()
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    _kunde(seite, "00042")
    leiste = seite.locator(".einlass-leiste")
    seite.fill("#bar", "1,00")
    aufnehmen(seite, "bezahlen-felder", leiste,
              Marke(seite.locator("#beitrag"), nummer=1, von="unten", laenge=40),
              Marke(seite.locator("#bar"), nummer=2, von="unten", laenge=40),
              Marke(seite.get_by_role("button", name="✓ Abholung eintragen"), nummer=3,
                    von="unten", laenge=40))  # fmt: skip
    seite.get_by_role("button", name="✓ Abholung eintragen").click()
    meldung = seite.locator(".kasse-meldung")
    expect(meldung).to_contain_text("Abholung eingetragen")
    aufnehmen(seite, "bezahlen-bestaetigung", [seite.locator(".empfang-kopf"), meldung],
              Marke(meldung, "rahmen", 1))  # fmt: skip
    # Heute schon abgeholt: nur noch Zahlung ohne Abholung
    _kunde(seite, "00042")
    feld = seite.get_by_label("Gezahlt ohne Abholung (Euro)")
    feld.fill("0,50")
    zahlung = seite.locator("section.karte", has=seite.get_by_role("heading", name="Zahlung"))
    aufnehmen(seite, "bezahlen-ohne-abholung", zahlung,
              Marke(feld, nummer=1, von="rechts"),
              Marke(zahlung.get_by_role("button", name="Zahlung buchen"), nummer=2,
                    von="rechts"))  # fmt: skip


def test_hilfe_bild_notizen(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    _kunde(seite, "00042")
    notizen = seite.locator("section.notizen")
    notizen.locator("#notiz-text").fill("Kommt heute mit dem Lastenrad.")
    notizen.get_by_role("button", name="Notiz speichern").click()
    expect(notizen.get_by_text("Kommt heute mit dem Lastenrad.")).to_be_visible()
    notizen.locator("#notiz-text").fill("Fragt nach einem Termin im Büro.")
    aufnehmen(seite, "notizen-einlass", notizen,
              Marke(notizen.locator(".knopf-vorlage").first, nummer=1, von="rechts"),
              Marke(notizen.locator("#notiz-text"), nummer=2, von="rechts"),
              Marke(notizen.get_by_role("button", name="Notiz speichern"), nummer=3,
                    von="rechts"),
              Marke(notizen.get_by_role("button", name=re.compile("löschen")).first, nummer=4,
                    von="rechts"))  # fmt: skip


def test_hilfe_bild_notizen_an_stelle(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("kunden:haushalt", args=["00042"]))
    notizen = seite.locator("section.notizen")
    notizen.locator("#notiz-text").fill("Neuer Ausweis liegt im Büro bereit.")
    haken = notizen.get_by_label(re.compile("An die Ausgabestelle schicken"))
    haken.check()
    aufnehmen(seite, "notizen-an-stelle", notizen.locator("form.notiz-neu"),
              Marke(notizen.locator("#notiz-text"), nummer=1, von="rechts"),
              Marke(haken, nummer=2),
              Marke(notizen.get_by_role("button", name="Notiz speichern"), nummer=3,
                    von="rechts"))  # fmt: skip


def test_hilfe_bild_sonderaktionen_einlass(angemeldet, admin, muster):
    heute = timezone.localdate()
    aktion = Sonderaktion.objects.create(bezeichnung="Schulranzen", von=heute,
                                         bis=heute + dt.timedelta(days=30),
                                         beschreibung="Nur gegen Unterschrift ausgeben",
                                         menge=Sonderaktion.Menge.JE_KIND)  # fmt: skip
    SonderaktionAuswahl.objects.create(aktion=aktion, bezeichnung="Ranzen", reihenfolge=1)
    SonderaktionAuswahl.objects.create(aktion=aktion, bezeichnung="Turnbeutel", reihenfolge=2)
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    _kunde(seite, "00042")
    karte = seite.locator("section.sonderaktion")
    knopf = karte.get_by_role("button", name="1× Ranzen")
    aufnehmen(seite, "sonderaktionen-einlass-karte", karte,
              Marke(karte.locator(".hinweis"), nummer=1, von="rechts", laenge=50),
              Marke(knopf, nummer=2, von="unten", laenge=40))  # fmt: skip
    knopf.click()
    karte = seite.locator("section.sonderaktion")
    expect(karte.locator(".sonderaktion-erhalten")).to_be_visible()
    aufnehmen(seite, "sonderaktionen-einlass-erhalten", karte,
              Marke(karte.locator(".sonderaktion-erhalten"), nummer=3, von="rechts",
                    laenge=50))  # fmt: skip


def test_hilfe_bild_korrigieren(angemeldet, admin, muster, benutzer_mit_rolle):
    anna = _einlass_konto(benutzer_mit_rolle)
    seite = oeffnen(angemeldet, anna, reverse("ausgabe:empfang"))
    _abholung(seite, "00042")
    _kunde(seite, "00042")
    wunsch = seite.locator("details.korrektur-wunsch").first
    wunsch.locator("summary").click()
    wunsch.get_by_label("Grund").select_option("Falscher Kunde aufgerufen")
    wunsch.get_by_label("Anmerkung (optional)").fill("war Kunde 24")
    aufnehmen(seite, "korrigieren-wunsch", wunsch,
              Marke(wunsch.locator("summary"), nummer=1, von="rechts"),
              Marke(wunsch.get_by_label("Grund"), nummer=2, von="rechts"),
              Marke(wunsch.get_by_role("button", name="Korrekturwunsch senden"), nummer=3,
                    von="rechts"))  # fmt: skip
    wunsch.get_by_role("button", name="Korrekturwunsch senden").click()
    hinweis = seite.get_by_text(re.compile("Korrektur beantragt"))
    expect(hinweis).to_be_visible()
    aufnehmen(seite, "korrigieren-beantragt", seite.locator("section.karte", has=hinweis),
              Marke(hinweis, "rahmen", 3))  # fmt: skip


def test_hilfe_bild_korrekturen(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    _abholung(seite, "00042")
    abholung = Abholung.objects.get(haushalt=muster)
    korrekturen.beantragen("abholung", abholung.pk, grund="Falscher Kunde aufgerufen",
                           anmerkung="war Kunde 24", von="Anna Probe")  # fmt: skip
    seite.goto(reverse("ausgabe:korrekturen"))
    menue = seite.get_by_role("navigation", name="Hauptnavigation")
    eintrag = menue.get_by_role("link", name=re.compile("Korrekturwünsche"))
    karte = seite.locator(".korrektur-karte").first
    aufnehmen(seite, "korrekturen-liste", [eintrag, karte],
              Marke(eintrag, nummer=1, von="rechts", laenge=50),
              Marke(karte.locator("p").first, "rahmen", 2),
              Marke(karte.get_by_role("button", name="Zurücknehmen"), nummer=3, von="unten",
                    laenge=40),
              Marke(karte.get_by_label("Antwort (optional)"), nummer=4, von="unten",
                    laenge=40))  # fmt: skip


def test_hilfe_bild_ausnahme(angemeldet, admin, muster):
    heute = timezone.localdate()
    andere = [t for i, t in enumerate(WOCHENTAGE) if i != heute.weekday()]
    mitte = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    gruppe = Kundengruppe.objects.create(kuerzel="B", name="Gruppe B", ausgabestelle=mitte,
                                         wochentage=", ".join(andere[:2]))  # fmt: skip
    _haushalt("00057", "Jonas", "Probe", dt.date(1990, 2, 1), gruppe=gruppe)
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    _kunde(seite, "00057")
    feld = seite.get_by_label("Ausnahme für heute, Begründung")
    feld.fill("Termin wegen Arzt verlegt")
    aufnehmen(seite, "ausnahme-erteilen", [seite.locator("section.ampel").first,
                                           feld.locator("xpath=ancestor::form")],
              Marke(feld, nummer=1, von="unten", laenge=40),
              Marke(seite.get_by_role("button", name="Ausnahme erteilen"), nummer=2,
                    von="rechts"))  # fmt: skip
    seite.get_by_role("button", name="Ausnahme erteilen").click()
    expect(seite.locator("section.ampel-gruen")).to_be_visible()
    _ampel(seite, "ausnahme-gruen")


def test_hilfe_bild_kasse(angemeldet, admin, muster):
    _haushalt("00057", "Jonas", "Probe", dt.date(1990, 2, 1))
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    _abholung(seite, "00042")
    _abholung(seite, "00057", gezahlt="5,00")
    seite.goto(reverse("ausgabe:kasse"))
    karte = seite.locator("section.karte").first
    summe = seite.locator("section.karte", has=seite.locator("table.kasse"))
    aufnehmen(seite, "kasse-tag", [karte, summe],
              Marke(karte.locator("nav.reiter"), "rahmen", 1),
              Marke(karte.get_by_role("link", name="später →"), nummer=2, von="rechts",
                    laenge=50),
              Marke(seite.locator("#stelle"), "rahmen", 3),
              Marke(seite.get_by_role("link", name=re.compile("drucken \\(PDF\\)")), nummer=4,
                    von="rechts"),
              Marke(summe.locator("table.kasse"), "rahmen", 5))  # fmt: skip
    titel = seite.get_by_role("heading", name="Buchungen des Tages")
    buchungen = seite.locator("section.karte", has=titel)
    zelle = buchungen.locator("tbody td[data-titel=Kundennummer]").first
    aufnehmen(seite, "kasse-einzelbuchungen", buchungen, Marke(zelle, "rahmen", 1))


def test_hilfe_bild_verzeichnis(angemeldet, admin):
    t = TafelEinstellungen.laden()
    t.name, t.email = "Tafel Musterstadt", "info@tafel.example.org"
    t.save()
    seite = oeffnen(angemeldet, admin, reverse("core:verzeichnis"))
    seite.get_by_label("Diese Tafel im bintafeln-Verzeichnis melden").check()
    seite.get_by_label(re.compile("Kontakt-Mail")).fill("vorstand@tafel.example.org")
    karten = seite.locator("section.karte")
    aufnehmen(seite, "verzeichnis", [karten.nth(0), karten.nth(1)],
              Marke(seite.get_by_label("Diese Tafel im bintafeln-Verzeichnis melden"), nummer=1),
              Marke(seite.get_by_label(re.compile("Kontakt-Mail")), nummer=2, von="rechts"),
              Marke(seite.get_by_role("button", name="Speichern"), nummer=3, von="rechts"),
              Marke(karten.nth(1).locator("dl"), "rahmen", 4))  # fmt: skip


def test_hilfe_bild_nachtragen(angemeldet, admin, muster):
    _haushalt("00043", "Jonas", "Probe", dt.date(1990, 2, 1))
    _haushalt("00044", "Lea", "Beispiel", dt.date(1985, 7, 9), tage=-10)
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:nachtragen"), breite=1100)
    filter_ = seite.locator("form.filter").first
    seite.get_by_label("00042 nachtragen").check()
    seite.get_by_label("00043 nachtragen").check()
    betrag = seite.get_by_label("Betrag für 00043")
    betrag.fill("0,00")
    knopf = seite.get_by_role("button", name="Angehakte nachtragen")
    aufnehmen(seite, "nachtragen-liste", [filter_, knopf],
              Marke(filter_, "rahmen", 1),
              Marke(seite.get_by_label("00042 nachtragen"), nummer=2, von="links", laenge=40),
              Marke(betrag, nummer=3, von="rechts", laenge=50),
              Marke(knopf, nummer=4, von="unten", laenge=30))  # fmt: skip
