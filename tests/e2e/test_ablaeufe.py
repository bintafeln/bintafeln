"""Wichtige Abläufe im echten Browser (ADR 0066), alle mit erfundenen Daten."""

import datetime as dt
import re
from pathlib import Path

from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice
from playwright.sync_api import expect

from apps.konten import rollen
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe, Person
from tests.conftest import PASSWORT, code_fuer


def _haushalte(anzahl=3):
    stelle = Ausgabestelle.objects.create(name="Mitte")
    gruppe = Kundengruppe.objects.create(
        kuerzel="X", name="Jeden Tag", ausgabestelle=stelle, wochentage="Mo, Di, Mi, Do, Fr, Sa, So"
    )
    for i in range(1, anzahl + 1):
        h = Haushalt.objects.create(
            kundennummer=f"{40 + i:05d}",
            kundengruppe=gruppe,
            ausweis_gueltig_bis=timezone.localdate() + dt.timedelta(days=100),
        )
        Person.objects.create(
            haushalt=h, ist_hauptperson=True, vorname="Erika", nachname=f"Muster{i}"
        )
    return stelle


def test_anmelden_mit_zwei_faktor(seite, admin):
    geraet = TOTPDevice.objects.create(user=admin, name="Handy", confirmed=True)
    seite.goto("/")
    expect(seite).to_have_url(re.compile("/konten/anmelden/"))
    seite.get_by_label("Benutzername").fill(admin.username)
    seite.get_by_label("Passwort").fill(PASSWORT)
    seite.get_by_role("button", name="Anmelden").click()
    expect(seite.get_by_role("heading", name="Zwei-Faktor-Code")).to_be_visible()
    seite.get_by_label("Code").fill(code_fuer(geraet))
    seite.get_by_role("button", name="Anmelden").click()
    expect(seite).to_have_url(re.compile(r"/$"))
    expect(seite.get_by_role("navigation", name="Hauptnavigation")).to_contain_text("Kunden")


def test_einlass_kunde_aufrufen_und_abholung_eintragen(angemeldet, admin, benutzer_mit_rolle):
    _haushalte(1)
    seite = angemeldet(benutzer_mit_rolle("einlass", rollen.AUSGABE))
    seite.goto("/ausgabe/")
    seite.get_by_label("Kundennummer scannen oder eingeben").fill("41")
    seite.get_by_role("button", name="Prüfen").click()
    expect(seite.get_by_role("heading", name=re.compile("Kunde 00041"))).to_be_visible()
    seite.get_by_role("button", name=re.compile("Abholung eintragen")).click()
    expect(seite.get_by_text("Kunde 00041: Abholung eingetragen.")).to_be_visible()
    # Zurück in der Suche, der Kunde steht in „Letzte Kunden heute“
    expect(seite.get_by_label("Kundennummer scannen oder eingeben")).to_be_focused()
    seite.get_by_text(re.compile("Letzte Kunden heute")).click()
    expect(seite.locator(".letzte-kunden")).to_contain_text("abgeholt")


def test_kamera_zeigt_bei_jedem_scan_ein_bild(angemeldet, admin, benutzer_mit_rolle):
    seite = angemeldet(benutzer_mit_rolle("einlass", rollen.AUSGABE))
    seite.goto("/ausgabe/")
    knopf = seite.get_by_role("button", name=re.compile("Kamera"))
    dialog = seite.locator("#kamera-dialog")
    for _ in range(3):
        knopf.click()
        expect(dialog).to_be_visible()
        video = dialog.locator("video")
        # Das Testbild der Kamera läuft (Breite > 0), und das Feld ist quer
        seite.wait_for_function(
            "() => { const v = document.querySelector('#kamera-dialog video');"
            " return v && v.videoWidth > 0 && !v.paused; }"
        )
        box = video.bounding_box()
        assert box["width"] > box["height"] > 0
        dialog.get_by_role("button", name="Schließen").click()
        expect(dialog).to_be_hidden()


def test_kundenliste_auswahl_und_export(angemeldet, admin):
    _haushalte(3)
    seite = angemeldet(admin)
    seite.goto("/kunden/")
    zeilen = seite.locator("tbody input[type=checkbox]")
    expect(zeilen).to_have_count(3)
    zeilen.nth(0).check()
    zeilen.nth(2).check()
    expect(seite.locator("[data-auswahl-zahl]").first).to_contain_text("2")
    # „Alle“ wählt alle, ein zweiter Klick keine
    alle = seite.locator("thead input[type=checkbox]")
    alle.check()
    expect(seite.locator("tbody input[type=checkbox]:checked")).to_have_count(3)
    alle.uncheck()
    expect(seite.locator("tbody input[type=checkbox]:checked")).to_have_count(0)
    # Export nimmt nur die angehakten Haushalte
    zeilen.nth(1).check()
    with seite.expect_download() as laden:
        seite.get_by_role("button", name=re.compile("Als CSV exportieren")).click()
    inhalt = Path(laden.value.path()).read_text(encoding="utf-8-sig")
    assert "00042" in inhalt and "00041" not in inhalt and "00043" not in inhalt


def test_online_antrag_oeffnet(seite, admin):
    seite.goto("/antrag/")
    expect(seite).to_have_url(re.compile("/antrag/de/"))
    expect(seite.locator("form")).to_be_visible()


def test_suche_im_kopf(angemeldet, admin):
    _haushalte(1)
    seite = angemeldet(admin)
    seite.goto("/")
    seite.get_by_role("searchbox").first.fill("00041")
    seite.keyboard.press("Enter")
    expect(seite.get_by_text("00041").first).to_be_visible()


def test_ausgabestelle_im_menue_und_fortschritt(angemeldet, admin, benutzer_mit_rolle):
    _haushalte(2)  # Ausgabestelle „Mitte“, beide heute dran
    Ausgabestelle.objects.create(name="Nord")
    seite = angemeldet(benutzer_mit_rolle("einlass", rollen.AUSGABE))
    seite.goto("/ausgabe/")
    expect(seite.get_by_text("Bitte oben im Menü die Ausgabestelle wählen")).to_be_visible()
    seite.get_by_label("Ausgabestelle").select_option(label="Mitte")
    fortschritt = seite.locator("#ausgabe-fortschritt")
    expect(fortschritt).to_have_text("0/2")
    seite.get_by_label("Kundennummer scannen oder eingeben").fill("41")
    seite.get_by_role("button", name="Prüfen").click()
    seite.get_by_role("button", name=re.compile("Abholung eintragen")).click()
    expect(fortschritt).to_have_text("1/2")  # ohne neues Laden der Seite
    # Die Wahl bleibt beim nächsten Aufruf
    seite.goto("/kunden/")
    expect(seite.get_by_label("Ausgabestelle")).to_have_value(
        str(Ausgabestelle.objects.get(name="Mitte").pk)
    )
