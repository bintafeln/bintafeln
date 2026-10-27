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


def test_suche_treffer_antippen_wie_auf_dem_ipad(angemeldet, admin):
    """Safari (iPad) gibt Links beim Antippen keinen Fokus: Das Suchfeld verliert ihn, bevor der
    Klick ankommt. Die Trefferliste muss trotzdem stehen bleiben, bis der Link gewählt ist."""
    _haushalte(1)
    seite = angemeldet(admin)
    seite.add_init_script("""document.addEventListener("mousedown", function (e) {
        if (e.target.closest && e.target.closest("a")) {
          e.preventDefault();
          if (document.activeElement) document.activeElement.blur();
        }
      }, true);""")
    seite.goto("/")
    seite.get_by_role("searchbox").first.fill("Muster1")
    treffer = seite.locator("#kopf-suche-liste a", has_text="Muster1").first
    expect(treffer).to_be_visible()
    treffer.click()
    expect(seite).to_have_url(re.compile("00041"))
    # Tippen außerhalb schließt die Liste
    seite.get_by_role("searchbox").first.fill("Muster1")
    expect(treffer).to_be_visible()
    seite.mouse.click(1200, 800)
    expect(seite.locator("#kopf-suche-liste")).to_be_hidden()


def test_ausgabestelle_im_menue_und_fortschritt(angemeldet, admin, benutzer_mit_rolle):
    _haushalte(2)  # Ausgabestelle „Mitte“, beide heute dran
    Ausgabestelle.objects.create(name="Nord")
    seite = angemeldet(benutzer_mit_rolle("einlass", rollen.AUSGABE))
    seite.goto("/ausgabe/")
    expect(seite.get_by_text("Bitte oben im Menü die Ausgabestelle wählen")).to_be_visible()
    seite.get_by_label("Ausgabestelle").select_option(label="Mitte")
    fortschritt = seite.locator("#ausgabe-fortschritt .fortschritt-zahl")
    expect(fortschritt).to_have_text("0/2")
    blase = seite.locator("#fortschritt-blase")
    expect(blase).to_be_hidden()
    fortschritt.hover()  # Erklärung erscheint sofort
    expect(blase).to_be_visible()
    expect(blase).to_contain_text("0 von 2 möglichen Haushalten haben heute schon abgeholt.")
    seite.get_by_label("Kundennummer scannen oder eingeben").fill("41")
    seite.get_by_role("button", name="Prüfen").click()
    seite.get_by_role("button", name=re.compile("Abholung eintragen")).click()
    expect(fortschritt).to_have_text("1/2")  # ohne neues Laden der Seite
    # Die Wahl bleibt beim nächsten Aufruf
    seite.goto("/kunden/")
    expect(seite.get_by_label("Ausgabestelle")).to_have_value(
        str(Ausgabestelle.objects.get(name="Mitte").pk)
    )


def test_vorauszahlung_traegt_nur_ins_feld_ein(angemeldet, admin, benutzer_mit_rolle):
    from apps.ausgabe.models import AusgabeEinstellungen, Buchung

    _haushalte(1)
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_abholung = 1
    e.max_abholungen = 0
    e.save()
    seite = angemeldet(benutzer_mit_rolle("einlass", rollen.AUSGABE))
    seite.goto("/ausgabe/?nummer=41")
    knopf = seite.locator(".einlass-vorschlag")
    heute = timezone.localdate()
    rest = (heute.replace(day=28) + dt.timedelta(days=4)).replace(day=1) - heute
    if rest.days < 3:  # bis Monatsende weniger als drei Abholungen: kein Vorschlag
        expect(knopf).to_have_count(0)
        return
    expect(knopf).to_contain_text("Vorauszahlung Rest")
    betrag = knopf.locator("strong").inner_text().removesuffix(" €")
    knopf.click()
    expect(seite.locator("#bar")).to_have_value(betrag)
    assert not Buchung.objects.exists()  # gebucht wird erst mit „Abholung eintragen“


def test_aufruf_unter_dem_menue(angemeldet, admin, benutzer_mit_rolle):
    from apps.core.models import TafelEinstellungen

    _haushalte(8)
    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    seite = angemeldet(benutzer_mit_rolle("einlass", rollen.AUSGABE))
    seite.goto("/ausgabe/")  # nur eine Ausgabestelle: steht fest
    leiste = seite.locator(".aufruf-leiste")
    leiste.get_by_role("button", name="Aufruf starten").click()
    expect(leiste).to_contain_text("Bitte eintreten")
    erste = leiste.locator(".aufruf-leiste-nummern span").first.inner_text()
    leiste.get_by_role("button", name=re.compile("Nächste . hereinrufen")).click()
    expect(leiste.locator(".aufruf-leiste-nummern span").first).not_to_have_text(erste)
    leiste.get_by_role("button", name=re.compile("zurück")).click()
    expect(leiste.locator(".aufruf-leiste-nummern span").first).to_have_text(erste)


def test_ausweis_gestalter_merkmale_und_einlass(angemeldet, admin):
    """ADR 0071: Element „Merkmale“ im Gestalter, Merkmale am Einlass."""
    seite = angemeldet(admin)
    seite.goto("/kunden/ausweis/gestalten/")
    seite.select_option("#neu-typ", "merkmale")
    seite.click("#neu-knopf")
    expect(seite.locator(".ausweis-element.art-merkmale .merkmal-vorschau")).to_have_count(2)
    expect(seite.locator("#eig-farbe")).to_have_value("#1d4f91")

    _haushalte(1)
    p = Person.objects.get(haushalt__kundennummer="00041")
    p.zusatz = {"vegetarier": True}
    p.save()
    seite.goto("/ausgabe/?nummer=00041")
    expect(seite.locator(".merkmal")).to_have_text(["Vegetarier"])
