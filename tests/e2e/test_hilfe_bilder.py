"""Bilder für das Handbuch: Einlass, Neuer Haushalt, Ausweise verlängern (Werkzeug und
Anleitung in ``hilfe_bilder.py``)."""

import datetime as dt

from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect

from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    KundenEinstellungen,
    Nachricht,
    Person,
    Zusatzfeld,
)
from tests.e2e.hilfe_bilder import BREITE, HOEHE, Marke, aufnehmen


def test_bild_einlass(angemeldet, admin, muster):
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("ausgabe:empfang"))
    feld = seite.get_by_label("Kundennummer scannen oder eingeben")
    aufnehmen(seite, "einlass-suche", [seite.locator(".kopf"), seite.locator(".menue-stelle"),
                                         seite.locator(".empfang-kopf")],
              Marke(seite.locator("#menue-stelle"), nummer=1, von="rechts"),
              Marke(feld, nummer=2, von="unten"))  # fmt: skip
    feld.fill("42")
    seite.get_by_role("button", name="Prüfen").click()
    knopf = seite.get_by_role("button", name="✓ Abholung eintragen")
    notiz = seite.locator("section.notizen .notiz").first
    aufnehmen(seite, "einlass-kunde", [seite.locator(".einlass-leiste"), notiz],
              Marke(seite.locator("section.ampel").first, "rahmen", 1),
              Marke(notiz, "rahmen", 2),
              Marke(knopf, nummer=3, von="oben", laenge=36))  # fmt: skip


def test_bild_neuer_haushalt(angemeldet, admin, muster):
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("kunden:haushalt_neu"))
    seite.fill("#id_hp-vorname", "Erika")
    seite.fill("#id_hp-nachname", "Beispiel")
    seite.select_option("#id_hp-gdb", "50")
    seite.get_by_label("G (erheblich gehbehindert)").first.check()
    titel = seite.get_by_role("heading", name="3. Weitere Angaben")
    abschnitt = seite.locator("section", has=titel)
    aufnehmen(seite, "haushalt-neu-behinderung", abschnitt,
              Marke(seite.locator("#id_hp-gdb"), nummer=1),
              Marke(seite.locator('[data-merkzeichen-fuer="id_hp-gdb"]'), "rahmen", 2))  # fmt: skip
    seite.fill("#id_a-0-vorname", "Max")
    seite.fill("#id_a-0-geburtsdatum", "2014-09-03")
    seite.select_option("#id_a-0-gdb", "80")
    angehoerige = seite.locator("section", has=seite.get_by_role("heading", name="4. Angehörige"))
    aufnehmen(seite, "haushalt-neu-angehoerige", angehoerige,
              Marke(seite.locator("#id_a-0-vorname"), nummer=1),
              Marke(seite.locator("#id_a-0-gdb"), nummer=2, von="rechts"))  # fmt: skip


def test_bild_ausweise_verlaengern(angemeldet, admin, muster):
    heute = timezone.localdate()
    sb = Zusatzfeld.objects.get(schluessel="schwerbehindert")
    e = KundenEinstellungen.laden()
    e.verlaengern_regel = KundenEinstellungen.Verlaengern.ALLE
    e.verlaengern_ab_alter = 60
    e.save()
    e.verlaengern_felder.set([sb])
    jung = Haushalt.objects.create(kundennummer="00057",
                                   ausweis_gueltig_bis=heute + dt.timedelta(days=20))  # fmt: skip
    Person.objects.create(haushalt=jung, ist_hauptperson=True, vorname="Jonas",
                          nachname="Probe", geburtsdatum=dt.date(1990, 2, 1))  # fmt: skip
    muster.ausweis_gueltig_bis = heute + dt.timedelta(days=20)
    muster.save()
    muster.personen.filter(vorname="Max").delete()
    stelle = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    for nummer in ("00042", "00057"):
        Nachricht.objects.create(kundennummer=nummer, anliegen="verlaengern", von="einlass",
                                 stelle=stelle)  # fmt: skip
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": BREITE, "height": HOEHE})
    seite.goto(reverse("kunden:verlaengern"))
    seite.locator('input[name="wahl_00057"][value="verlaengern"]').check()
    seite.fill('textarea[name="grund_00057"]', "Härtefall, Bescheid folgt")
    tabelle = seite.locator("table.tabelle").first
    aufnehmen(seite, "verlaengern-liste", seite.locator("section.karte").first,
              Marke(seite.locator('input[name="wahl_00042"][value="verlaengern"]'), nummer=1),
              Marke(seite.locator('input[name="wahl_00057"][value="verlaengern"]'), nummer=2),
              Marke(seite.locator('textarea[name="grund_00057"]'), nummer=3, von="rechts"),
              Marke(seite.get_by_role("button", name="Ausgewählte ausführen"), nummer=4,
                    von="rechts"))  # fmt: skip
    expect(tabelle).to_be_visible()
    seite.get_by_role("button", name="Ausgewählte ausführen").click()
    knopf = seite.get_by_role("button", name="Nochmal prüfen").first
    erledigt = seite.locator("section", has=seite.get_by_role("heading", name="Erledigt (2)"))
    haken = seite.locator('input[name="nummer"][value="00057"]')
    haken.check()
    drucken = seite.get_by_role("button", name="Angehakte Ausweise drucken (PDF)")
    aufnehmen(seite, "verlaengern-erledigt", erledigt, Marke(knopf, nummer=1, von="rechts"),
              Marke(haken, nummer=2), Marke(drucken, nummer=3, von="rechts"))  # fmt: skip
