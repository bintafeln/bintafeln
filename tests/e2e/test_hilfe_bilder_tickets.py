"""Bilder für das Handbuch: Tickets und Benachrichtigungen (Werkzeug und Anleitung in
``hilfe_bilder.py``)."""

from django.contrib.auth.models import Group
from django.urls import reverse
from playwright.sync_api import expect

from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.tickets.models import Kategorie, Kommentar, Ticket
from tests.e2e.hilfe_bilder import Marke, aufnehmen, oeffnen


def _ohne_menue(seite):
    seite.get_by_role("button", name="Menü einfahren").click()
    expect(seite.locator("nav.seitenmenue")).to_be_hidden()


def _tickets(admin, benutzer_mit_rolle):
    t = TafelEinstellungen.laden()
    t.module = ["tickets"]
    t.save()
    theo = benutzer_mit_rolle("theo", rollen.AUSGABE)
    theo.first_name, theo.last_name = "Theo", "Technik"
    theo.save()
    technik = Kategorie.objects.create(name="Technik und Geräte",
                                       beschreibung="Kühlung, Waagen, Kassen")  # fmt: skip
    technik.personen.add(theo)
    technik.rollen.add(Group.objects.get(name=rollen.BUERO))
    Kategorie.objects.create(name="Lager", beschreibung="Regale, Paletten, Ordnung")
    Kategorie.objects.create(name="Programm (bintafeln)", beschreibung="Fehler oder Wünsche")
    return theo, technik


def test_hilfe_bild_tickets(angemeldet, admin, muster, benutzer_mit_rolle):
    theo, technik = _tickets(admin, benutzer_mit_rolle)
    seite = oeffnen(angemeldet, admin, reverse("tickets:neu"))
    _ohne_menue(seite)
    seite.get_by_label("Kategorie").select_option(label="Technik und Geräte")
    seite.get_by_label("Worum geht es?").fill("Kühlschrank 2 brummt laut")
    seite.get_by_label("Beschreibung").fill("Seit Montag sehr laut, Temperatur noch in Ordnung.")
    karte = seite.locator("section.karte").first
    aufnehmen(seite, "tickets-neu", karte,
              Marke(seite.get_by_label("Kategorie"), "rahmen", 1),
              Marke(seite.get_by_label("Worum geht es?"), "rahmen", 2),
              Marke(seite.locator('input[name="dateien"]'), "rahmen", 3),
              Marke(seite.get_by_role("button", name="Ticket eröffnen"), nummer=4,
                    von="rechts"))  # fmt: skip
    t = Ticket.objects.create(kategorie=technik, titel="Kühlschrank 2 brummt laut",
                              beschreibung="Seit Montag sehr laut, Temperatur noch in Ordnung.",
                              erstellt_von=admin)  # fmt: skip
    Kommentar.objects.create(ticket=t, von=theo, text="Schaue ich mir Donnerstag an.")
    seite.goto(reverse("tickets:ticket", args=[t.pk]))
    seite.get_by_label("Status").select_option("in_arbeit")
    seite.get_by_label("Zuständig").select_option(label="Theo Technik")
    raster = seite.locator(".seiten-raster")
    aufnehmen(seite, "tickets-bearbeiten", raster,
              Marke(seite.locator("#verlauf .notiz").first, "rahmen", 1),
              Marke(seite.get_by_label("Antwort oder Notiz"), "rahmen", 2),
              Marke(seite.get_by_label("Status"), "rahmen", 3),
              Marke(seite.get_by_label("Zuständig"), "rahmen", 4))  # fmt: skip
    seite.goto(reverse("tickets:kategorie", args=[technik.pk]))
    menue = seite.locator("details#id_personen")
    aufnehmen(seite, "tickets-kategorie", seite.locator("section.karte").first,
              Marke(seite.get_by_label("Name"), "rahmen", 1),
              Marke(menue.locator("summary"), "rahmen", 2),
              Marke(seite.locator("details#id_rollen summary"), "rahmen", 3))  # fmt: skip


def test_hilfe_bild_benachrichtigungen(angemeldet, admin, muster, benutzer_mit_rolle):
    _tickets(admin, benutzer_mit_rolle)
    admin.email = "clara@example.org"
    admin.save()
    seite = oeffnen(angemeldet, admin, reverse("konten:benachrichtigungen"))
    _ohne_menue(seite)
    seite.locator('select[name="art_korrekturwunsch"]').select_option("taeglich")
    seite.locator('select[name="art_ticket_neu"]').select_option("stuendlich")
    aufnehmen(seite, "benachrichtigungen", seite.locator("section.karte").first,
              Marke(seite.locator('select[name="art_korrekturwunsch"]'), nummer=1, von="rechts"),
              Marke(seite.get_by_label("Uhrzeit für „täglich“ und „wöchentlich“"), "rahmen", 2),
              Marke(seite.get_by_role("button", name="Speichern"), nummer=3,
                    von="rechts"))  # fmt: skip
