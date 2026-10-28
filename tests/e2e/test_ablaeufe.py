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


def test_antrag_nachweise_ablegen(seite, admin):
    from apps.antraege.models import AntragEinstellungen, AntragText

    e = AntragEinstellungen.laden()
    e.aktiv = True
    e.save()
    AntragText.objects.create(sprache="de", anhaenge_hinweis="<p>Bitte Ausweis und die ersten "
                              "Seiten des Bescheids anhängen.</p>")  # fmt: skip
    seite.goto("/antrag/en/")  # ohne englischen Hinweis gilt der deutsche
    expect(seite.get_by_text("Bitte Ausweis und die ersten Seiten")).to_be_visible()
    expect(seite.get_by_role("button", name="Take a photo")).to_be_visible()
    feld = seite.locator("input.ablage-feld")
    png = {"name": "ausweis.png", "mimeType": "image/png", "buffer": b"\x89PNG erfunden"}
    pdf = {"name": "bescheid.pdf", "mimeType": "application/pdf", "buffer": b"%PDF erfunden"}
    feld.set_input_files([png])
    feld.set_input_files([pdf])  # ergänzt, statt zu ersetzen
    liste = seite.locator(".ablage-liste li")
    expect(liste).to_have_count(2)
    assert feld.evaluate("f => f.files.length") == 2
    feld.set_input_files([{"name": "notiz.txt", "mimeType": "text/plain", "buffer": b"x"}])
    expect(seite.locator(".ablage-fehler")).to_be_visible()
    expect(liste).to_have_count(2)
    liste.first.get_by_role("button").click()
    expect(liste).to_have_count(1)
    expect(liste.first).to_contain_text("bescheid.pdf")
    assert feld.evaluate("f => f.files[0].name") == "bescheid.pdf"


def test_editor_gestalten_und_html(angemeldet, admin):
    from apps.antraege.models import AntragText

    AntragText.objects.create(
        sprache="de",
        einleitung='<p>Hallo <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" '
        'onerror="alert(1)"></p>',
    )
    seite = angemeldet(admin)
    seite.goto("/antraege/einstellungen/texte/de/")
    flaeche = seite.locator(".editor-flaeche").first
    expect(flaeche).to_contain_text("Hallo")
    assert "onerror" not in flaeche.inner_html()  # Ereignisse fallen vor dem Anzeigen weg
    flaeche.click()
    seite.keyboard.press("End")
    seite.keyboard.type(" Welt")
    seite.keyboard.press("Shift+Home")
    seite.locator(".editor-leiste").first.get_by_role("button", name="Fett").click()
    seite.locator(".editor-reiter").first.get_by_role("tab", name="HTML").click()
    feld = seite.locator("#id_einleitung")
    expect(feld).to_be_visible()
    assert "Welt" in feld.input_value() and (
        "<b>" in feld.input_value() or "font-weight" in feld.input_value()
    )
    seite.get_by_role("button", name="Speichern").click()
    assert "Welt" in AntragText.objects.get(sprache="de").einleitung


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
    # Abholung am Einlass: Die Nummer verschwindet sofort aus dem Kasten (nicht erst nach 5 s)
    seite.get_by_label("Kundennummer scannen oder eingeben").fill(erste)
    seite.get_by_role("button", name="Prüfen").click()
    seite.get_by_role("button", name="✓ Abholung eintragen").click()
    expect(leiste.locator(".aufruf-leiste-nummern")).not_to_contain_text(erste, timeout=3000)


def test_handy_steuerung_zeigt_kiosk_meldungen(angemeldet, admin, benutzer_mit_rolle):
    from apps.aufruf import ablauf
    from apps.aufruf.models import AufrufEinstellungen
    from apps.core.models import TafelEinstellungen

    stelle = _haushalte(8)
    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    tag = ablauf.starten(stelle, timezone.localdate())
    d = ablauf.stand_fuer_anzeige(tag, AufrufEinstellungen.laden(stelle), timezone.localdate())
    da = d["current_numbers"][0]
    ablauf.kiosk_melden(stelle, timezone.localdate(), da)
    seite = angemeldet(admin)
    seite.goto(f"/aufruf/{stelle.pk}/mobil/")
    knopf = seite.locator("#btnNumbers")
    expect(knopf.locator(".nr-da")).to_have_text(da)
    expect(knopf.locator(".nr-fehlt")).to_have_count(len(d["current_numbers"]) - 1)
    expect(seite.locator("#nextCustomersDisplay .nr-fehlt").first).to_be_visible()


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


def test_statistik_springen_zu(angemeldet, admin):
    """Auswahlfeld „Springen zu“ springt zum Abschnitt der Statistik."""
    seite = angemeldet(admin)
    seite.goto("/statistik/")
    wahl = seite.locator("#sprung")
    erster = wahl.locator("option").nth(1).get_attribute("value")
    wahl.select_option(erster)
    seite.wait_for_function("id => location.hash === '#' + id", arg=erster)
    expect(wahl).to_have_value("")


def test_menue_einfahren_und_ausfahren(angemeldet, admin):
    """Breiter Bildschirm: « fährt das Menü ein (bleibt so beim Seitenwechsel), » wieder aus."""
    seite = angemeldet(admin)
    seite.goto("/")
    menue = seite.locator("nav.seitenmenue")
    expect(menue).to_be_visible()
    seite.get_by_role("button", name="Menü einfahren").click()
    expect(menue).to_be_hidden()
    seite.goto("/kunden/")
    expect(menue).to_be_hidden()
    seite.get_by_role("button", name="Menü ausfahren").click()
    expect(menue).to_be_visible()
    seite.goto("/")
    expect(menue).to_be_visible()


def test_liste_zeigt_kriterium_sofort(angemeldet, admin):
    """Listen: Ein gewähltes Kriterium zeigt das Ergebnis ohne „Anzeigen“; die Spaltenwahl nicht."""
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.module = ["listen"]
    t.save()
    _haushalte(2)
    Haushalt.objects.filter(kundennummer="00042").update(status="pausiert")
    seite = angemeldet(admin)
    seite.goto("/listen/kunden_stelle/")
    expect(seite.locator("tbody input[name=id]")).to_have_count(1)  # Vorgabe: aktiv
    with seite.expect_navigation():
        seite.select_option("#f-status", "")
    expect(seite.locator("tbody input[name=id]")).to_have_count(2)
    assert "status=&" in seite.url or seite.url.endswith("status=")
    seite.click(".spalten-wahl summary")
    adresse = seite.url
    seite.locator(".spalten-haken input").first.uncheck()
    seite.wait_for_timeout(300)
    assert seite.url == adresse  # Spalten warten auf „Anzeigen“


def test_statistik_grafik_gross_und_zurueck(angemeldet, admin):
    """Grafik anklicken: bildschirmfüllend; „Zurück“ schließt, die Seite bleibt an ihrer Stelle."""
    from apps.kunden.models import Abholung

    _haushalte(2)
    for h in Haushalt.objects.all():
        Abholung.objects.create(haushalt=h, datum=timezone.localdate())
    seite = angemeldet(admin)
    seite.goto("/statistik/")
    grafik = seite.locator("figure.diagramm-rahmen[data-gross]").last
    grafik.scroll_into_view_if_needed()
    oben = seite.evaluate("window.scrollY")
    grafik.click()
    dialog = seite.locator("#diagramm-gross")
    expect(dialog).to_be_visible()
    expect(dialog.locator(".diagramm-gross-inhalt svg")).to_have_count(1)
    seite.get_by_role("button", name="← Zurück").click()
    expect(dialog).to_be_hidden()
    assert seite.evaluate("window.scrollY") == oben
    # Auch über „⤢ Groß“ und mit Esc
    seite.locator("button[data-gross]").first.click()
    expect(dialog).to_be_visible()
    seite.keyboard.press("Escape")
    expect(dialog).to_be_hidden()


def test_einstellungen_speichern_sofort(angemeldet, admin):
    """Einstellungen ohne Speichern-Knopf: jede Änderung gleich gespeichert, Fehler am Feld."""
    from apps.kunden.models import KundenEinstellungen

    seite = angemeldet(admin)
    seite.goto("/kunden/einstellungen/")
    expect(seite.get_by_role("button", name="Speichern")).to_be_hidden()
    haken = seite.get_by_label("Telefon erfassen")
    vorher = KundenEinstellungen.laden().telefon_erfassen
    haken.click()
    expect(seite.locator(".autosave-ok").first).to_have_text("✓ gespeichert")
    assert KundenEinstellungen.laden().telefon_erfassen is not vorher
    feld = seite.get_by_label("Verlängern frühestens … Tage vor Ablauf")
    feld.fill("999")
    feld.press("Tab")
    expect(seite.locator(".autosave-meldung.fehler")).to_contain_text("365")
    assert KundenEinstellungen.laden().verlaengern_fruehestens_tage == 60  # alter Wert bleibt
    feld.fill("45")
    feld.press("Tab")
    rahmen = seite.locator(".feld", has=feld)
    expect(rahmen.locator(".autosave-ok")).to_be_visible()
    expect(rahmen.locator(".fehler")).to_have_count(0)
    assert KundenEinstellungen.laden().verlaengern_fruehestens_tage == 45
    # Die Regel als Satz passt sich sofort an
    regel = seite.locator("#verlaengern-regel")
    expect(regel).to_contain_text("Ohne Bedingung")
    seite.get_by_label("Verlängern nur, wenn").select_option("alle")
    expect(regel).to_contain_text("Verlängert wird, wenn jede Person im Haushalt mindestens 60")


def test_suchfeld_der_listen_auf_dem_handy_einzeilig(angemeldet, admin):
    """Auf schmalen Bildschirmen stehen die Filter untereinander; das Suchfeld bleibt eine
    normale Zeile hoch (vorher machte flex-basis daraus eine riesige Fläche)."""
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 390, "height": 800})
    seite.goto("/antraege/")
    assert seite.locator("input#suche").bounding_box()["height"] < 80


def test_kiosk_nummer_auf_dem_monitor_ist_jetzt_dran(seite, admin):
    """Steht eine Nummer gerade auf dem Monitor (auch an dritter Stelle), zeigt der Kiosk
    „jetzt dran“ – nicht „gleich dran“. Wer erst danach kommt, sieht „gleich dran“."""
    from apps.aufruf import ablauf
    from apps.aufruf.models import AufrufEinstellungen
    from apps.core.models import TafelEinstellungen

    stelle = _haushalte(8)
    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    e = AufrufEinstellungen.laden(stelle)
    e.anzahl = 3
    e.save()
    tag = ablauf.starten(stelle, timezone.localdate())
    wartend = tag.stand["gruppen"][0]["wartend"]
    for nummer, text in ((wartend[2], "jetzt dran"), (wartend[3], "gleich dran")):
        seite.goto(f"/aufruf/anzeige/{e.schluessel}/kiosk/")
        seite.keyboard.type(nummer)
        seite.keyboard.press("Enter")
        expect(seite.locator("#statusCard")).to_contain_text(text)


def test_danach_zeigt_am_gruppenende_die_naechste_gruppe(angemeldet, admin):
    """Handy-Steuerung: Am Ende einer Gruppe stehen bei „Danach“ die ersten Nummern der
    nächsten Gruppe statt „-“."""
    from apps.aufruf import ablauf
    from apps.aufruf.models import AufrufEinstellungen
    from apps.core.models import TafelEinstellungen

    stelle = _haushalte(2)
    Kundengruppe.objects.filter(kuerzel="X").update(uhrzeit=dt.time(8, 0))
    spaet = Kundengruppe.objects.create(
        kuerzel="Y", name="Später", ausgabestelle=stelle, wochentage="Mo, Di, Mi, Do, Fr, Sa, So",
        uhrzeit=dt.time(23, 0),
    )  # fmt: skip
    gueltig = timezone.localdate() + dt.timedelta(days=9)
    h = Haushalt.objects.create(
        kundennummer="00099", kundengruppe=spaet, ausweis_gueltig_bis=gueltig
    )
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Spaet")
    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    e = AufrufEinstellungen.laden(stelle)
    e.anzahl = 2
    e.save()
    ablauf.starten(stelle, timezone.localdate())  # beide aus „Jeden Tag“ aufgerufen, danach Später
    seite = angemeldet(admin)
    seite.goto(f"/aufruf/{stelle.pk}/mobil/")
    expect(seite.locator("#nextCustomersDisplay")).to_contain_text("dann Später")
    expect(seite.locator("#nextCustomersDisplay")).to_contain_text("00099")


def test_werkseinstellungen_vergessen_eingefahrenes_menue(angemeldet, admin, benutzer_mit_rolle):
    """Nach „Werkseinstellungen“ (Admin) vergisst der Browser gemerkte Ansichten wie das
    eingefahrene Menü."""
    from apps.konten import verwaltung

    anna = benutzer_mit_rolle("anna", rollen.BUERO)
    seite = angemeldet(anna)
    seite.goto("/")
    seite.locator("[data-menue-einfahren]").click()
    seite.reload()
    expect(seite.locator("html")).to_have_class(re.compile("menue-eingefahren"))
    verwaltung.werkseinstellungen(admin, anna)
    seite.reload()
    expect(seite.locator("html")).not_to_have_class(re.compile("menue-eingefahren"))
    seite.reload()  # bleibt ausgefahren (der neue Stand ist gemerkt)
    expect(seite.locator(".seitenmenue")).to_be_visible()


def test_aushang_monitor_wechselt_passt_ein_und_sperrt_alten_link(seite, admin):
    from apps.aushang import pin
    from apps.aushang.models import Aushang, AushangSeite, neuer_schluessel
    from apps.core.models import TafelEinstellungen
    from apps.dienstplan import beispiel as dp_beispiel
    from apps.fahrdienst import beispiel as fd_beispiel
    from apps.fahrdienst import plan as fd_plan

    t = TafelEinstellungen.laden()
    t.module, t.bundesland = ["aushang", "dienstplan", "fahrdienst"], "NW"
    t.save()
    dp_beispiel.anlegen(seed=1)
    fd_beispiel.anlegen(seed=1)
    stelle = Ausgabestelle.objects.get(name=dp_beispiel.STELLE)
    aushang = Aushang.objects.create(name="Monitor Fahrerraum", sekunden=5)
    AushangSeite.objects.create(aushang=aushang, art="dienstplan", wert=str(stelle.pk), monate=2)
    AushangSeite.objects.create(aushang=aushang, art="fahrdienst", monate=2, reihenfolge=1)
    # Der erste Platz ab heute: diese Person bekommt eine PIN und trägt sich am Monitor aus
    heute = timezone.localdate()
    tag = fd_plan.fahrtage(heute, heute + dt.timedelta(days=14))[0]
    p = next(p for _, plaetze in fd_plan.tage([tag])[0][1] for p in plaetze if p.wer)
    pin.setzen(p.wer, "482915")

    seite.set_viewport_size({"width": 1280, "height": 720})
    seite.clock.install()
    seite.goto(f"/aushang/zeigen/{aushang.schluessel}/")
    sichtbar = seite.locator(".aushang-folie.sichtbar")
    expect(sichtbar).to_have_count(1)
    erste = sichtbar.locator("h1").inner_text()
    # Die Schrift ist so gewählt, dass die ganze Seite ohne Scrollen zu sehen ist
    passt = seite.evaluate("""() => {
        const i = document.querySelector('.aushang-folie.sichtbar .aushang-inhalt');
        return i.scrollHeight <= i.clientHeight + 1 && parseFloat(i.style.fontSize) >= 6; }""")
    assert passt
    expect(seite.locator(".aushang-punkt.aktiv")).to_have_count(1)
    seite.clock.run_for(5_000)
    expect(sichtbar.locator("h1")).not_to_have_text(erste)

    # Antippen zeigt den Plan groß; „Übersicht“ oder 30 Sekunden Ruhe führen zurück
    sichtbar.click()
    expect(seite.locator("body.aushang-gross")).to_have_count(1)
    expect(seite.get_by_role("button", name="Übersicht")).to_be_visible()
    expect(sichtbar.locator(".aushang-qr svg")).to_be_visible()
    # Der ganze Plan passt auch groß auf den Bildschirm, ohne Schieben
    gross_passt = seite.evaluate("""() => {
        const i = document.querySelector('.aushang-folie.sichtbar .aushang-inhalt');
        return i.scrollHeight <= i.clientHeight + 1 && i.scrollWidth <= i.clientWidth + 1; }""")
    assert gross_passt
    seite.clock.run_for(20_000)
    expect(seite.locator("body.aushang-gross")).to_have_count(1)  # kein Wechsel in groß
    # Die Knöpfe oben wechseln die Seite; der gezeigte ist hervorgehoben
    reiter = seite.locator("#aushang-reiter button")
    letzter = reiter.last
    letzter.click()
    expect(letzter).to_have_class(re.compile("aktiv"))
    expect(sichtbar.locator("h1")).to_contain_text("Fahrerplan")
    expect(seite.locator("#aushang-reiter button.aktiv")).to_have_count(1)
    seite.get_by_role("button", name="Übersicht").click()
    expect(seite.locator("body.aushang-gross")).to_have_count(0)
    sichtbar.click()
    seite.clock.run_for(31_000)
    expect(seite.locator("body.aushang-gross")).to_have_count(0)

    # Austragen am Monitor mit persönlicher PIN
    fahrerplan = seite.locator(".aushang-folie", has_text="Fahrerplan").first
    nr = int(fahrerplan.get_attribute("data-nr"))
    seite.evaluate(f"() => document.querySelector('.aushang-folie[data-nr=\"{nr}\"]').click()")
    expect(seite.locator("body.aushang-gross")).to_have_count(1)
    kennung = f"fahrdienst|{tag:%Y-%m-%d}|{p.tour.pk}|{p.platz}"
    seite.locator(f'[data-platz="{kennung}"]').click()
    dialog = seite.locator("#aushang-dialog")
    expect(dialog).to_contain_text(f"Ich bin {p.wer.get_full_name()}")
    dialog.get_by_label("Meine PIN").first.fill("000000")
    dialog.get_by_role("button", name="Austragen").click()
    expect(dialog.get_by_text("Die PIN stimmt nicht.")).to_be_visible()
    dialog.get_by_label("Meine PIN").first.fill("482915")
    dialog.get_by_role("button", name="Austragen").click()
    expect(seite.locator("#aushang-meldung")).to_contain_text("fällt am")
    expect(seite.locator(f'[data-platz="{kennung}"]')).to_contain_text("offen")

    aushang.nebeneinander = 2
    aushang.save()
    seite.reload()
    expect(seite.locator(".aushang-folie.sichtbar")).to_have_count(2)

    # Neuer Link: Der alte Monitor leert sich beim nächsten Abruf (spätestens nach einer Minute)
    aushang.schluessel = neuer_schluessel()
    aushang.save()
    seite.clock.run_for(61_000)
    expect(seite.get_by_text("Dieser Link ist nicht mehr gültig.")).to_be_visible()
    expect(seite.locator("table")).to_have_count(0)
