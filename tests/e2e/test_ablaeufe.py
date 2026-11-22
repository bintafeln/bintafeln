"""Wichtige Abläufe im echten Browser (ADR 0066), alle mit erfundenen Daten."""

import datetime as dt
import re
from pathlib import Path

from django.urls import reverse
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


def _pdf_fenster(seite, klick) -> str:
    """Klickt, erwartet ein neues Fenster und liefert die Adresse des PDFs. Die Antwort wird
    durch eine kleine Seite ersetzt: Die kopflose Chrome-Variante in CI zeigt PDFs nicht an."""
    adressen = []

    def ersetzen(route):
        adressen.append(route.request.url)
        route.fulfill(status=200, content_type="text/html", body="<p>PDF</p>")

    seite.context.route(re.compile(r"/kunden/ausweise/"), ersetzen)
    with seite.expect_popup() as fenster:
        klick()
    fenster.value.wait_for_load_state()
    seite.context.unroute(re.compile(r"/kunden/ausweise/"))
    return adressen[-1]


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
    # Export nimmt nur die angehakten Haushalte; „Als CSV-Datei“ liegt im Aufklapper
    # „⬇ Herunterladen …“, der erst geöffnet werden muss.
    zeilen.nth(1).check()
    seite.locator("summary", has_text="Herunterladen").click()
    with seite.expect_download() as laden:
        seite.get_by_role("button", name=re.compile("Als CSV-Datei")).click()
    inhalt = Path(laden.value.path()).read_text(encoding="utf-8-sig")
    assert "00042" in inhalt and "00041" not in inhalt and "00043" not in inhalt
    # Ausweise drucken öffnet ein eigenes Fenster (iPad-App), nur mit dem angehakten Haushalt
    adresse = _pdf_fenster(
        seite, seite.get_by_role("button", name=re.compile("Ausweise drucken")).click
    )
    assert re.search(r"/kunden/ausweise/\?.*id=\d+", adresse)
    assert seite.url.endswith("/kunden/")


def test_ehrenamtliche_liste_herunterladen(angemeldet, admin, benutzer_mit_rolle):
    """„Herunterladen …“ in der Liste der Ehrenamtlichen: CSV kommt als Datei."""
    benutzer_mit_rolle("erna", rollen.AUSGABE)
    seite = angemeldet(admin)
    seite.goto(reverse("konten:ehrenamtliche"))
    seite.locator("summary", has_text="Herunterladen").click()
    with seite.expect_download() as laden:
        seite.get_by_role("button", name=re.compile("Als CSV-Datei")).click()
    assert "erna" in Path(laden.value.path()).read_text(encoding="utf-8-sig")


def test_bestaetigungen_im_browser_sortieren_und_auswahl_ausstellen(angemeldet, admin):
    """Ein Klick auf die Spaltenüberschrift sortiert die Tabelle im Browser; ausgestellt wird
    für die angehakten Spender in der Reihenfolge, die man sieht."""
    import datetime as dt
    from decimal import Decimal

    from apps.adressen.models import Adresse
    from apps.spenden.models import Spende, SpendenEinstellungen, Zuwendungsbestaetigung

    e = SpendenEinstellungen.laden()
    e.zwecke, e.finanzamt, e.steuernummer = "mildtätiger Zwecke", "Musterstadt", "12/345/67890"
    e.bescheid_vom, e.veranlagungszeitraum = dt.date(2025, 3, 1), "2021 bis 2023"
    e.unterzeichnet_von = "Clara Beispiel, Vorsitzende"
    e.save()
    jahr = dt.date.today().year
    for nachname, vorname, betrag in (("Zeta", "Anna", "30"), ("Alpha", "Zoe", "10"),
                                      ("Mitte", "Max", "20")):  # fmt: skip
        a = Adresse.objects.create(art="person", vorname=vorname, nachname=nachname,
                                   strasse="Weg 1", plz="12345", ort="Musterstadt")  # fmt: skip
        Spende.objects.create(adresse=a, datum=dt.date(jahr, 1, 5), betrag=Decimal(betrag))
    seite = angemeldet(admin)
    seite.goto("/spenden/bestaetigungen/")
    tabelle = seite.locator("#offen-tabelle")

    def namen():
        return tabelle.locator("tbody tr td:nth-child(2)").all_inner_texts()

    tabelle.get_by_role("button", name="Nachname / Organisation").click()
    assert [n.strip() for n in namen()] == ["Alpha", "Mitte", "Zeta"]
    tabelle.get_by_role("button", name="Nachname / Organisation").click()
    assert [n.strip() for n in namen()] == ["Zeta", "Mitte", "Alpha"]
    tabelle.get_by_role("button", name="Vorname").click()
    assert [n.strip() for n in namen()] == ["Zeta", "Mitte", "Alpha"]  # Anna, Max, Zoe
    tabelle.get_by_role("button", name="Summe").click()
    assert [n.strip() for n in namen()] == ["Alpha", "Mitte", "Zeta"]  # 10, 20, 30
    # alle anhaken, einen wieder abwählen, ausstellen
    tabelle.locator("thead input[type=checkbox]").check()
    expect(tabelle.locator("tbody input[type=checkbox]:checked")).to_have_count(3)
    tabelle.locator("tbody tr", has_text="Mitte").locator("input[type=checkbox]").uncheck()
    seite.get_by_role("button", name="Ausgewählte ausstellen").click()
    expect(seite.locator("#ausgestellt-tabelle tbody tr")).to_have_count(2)
    ausgestellt = Zuwendungsbestaetigung.objects.order_by("nummer")
    assert [b.adresse.nachname for b in ausgestellt] == ["Alpha", "Zeta"]


def test_spaltenbreite_ziehen_merken_und_zuruecksetzen(angemeldet, admin):
    """Spaltenbreite per Ziehen: Die Breite bleibt nach dem Neuladen und lässt sich mit
    „Spaltenbreiten zurücksetzen“ wieder entfernen."""
    _haushalte()
    seite = angemeldet(admin)
    seite.goto(reverse("kunden:uebersicht"))
    kopf = seite.locator("table.tabelle thead th").nth(1)
    vorher = kopf.bounding_box()["width"]
    griff = kopf.locator(".spalten-griff")
    kasten = griff.bounding_box()
    x, y = kasten["x"] + kasten["width"] / 2, kasten["y"] + kasten["height"] / 2
    seite.mouse.move(x, y)
    seite.mouse.down()
    seite.mouse.move(x + 90, y, steps=5)
    seite.mouse.up()
    breiter = kopf.bounding_box()["width"]
    assert breiter > vorher + 60
    expect(seite.get_by_role("button", name="Spaltenbreiten zurücksetzen")).to_be_visible()
    seite.reload()  # gemerkt
    kopf = seite.locator("table.tabelle thead th").nth(1)
    assert abs(kopf.bounding_box()["width"] - breiter) < 3
    seite.get_by_role("button", name="Spaltenbreiten zurücksetzen").click()
    assert kopf.bounding_box()["width"] < breiter - 60
    expect(seite.get_by_role("button", name="Spaltenbreiten zurücksetzen")).to_be_hidden()


def test_online_antrag_oeffnet(seite, admin):
    seite.goto("/antrag/")
    expect(seite).to_have_url(re.compile("/antrag/de/"))
    expect(seite.locator("form")).to_be_visible()


def test_antragsformular_am_pc_breit(seite, admin):
    # Regression: Das öffentliche Antragsformular darf am PC (Viewport 1280) nicht auf
    # Handy-Breite schrumpfen. Früher kappte die Klasse „antrag-karte“ (aus dem
    # Aufnahme-Abgleich) es auf 20rem ≈ 320px.
    from apps.antraege.models import AntragEinstellungen

    e = AntragEinstellungen.laden()
    e.aktiv = True  # sonst zeigt die Seite nur „Zurzeit keine Anträge“ statt des Formulars
    e.save()
    seite.goto("/antrag/de/")
    kasten = seite.locator(".antrag-formular")
    expect(kasten).to_be_visible()
    breite = kasten.bounding_box()["width"]
    assert breite > 600, f"Antragsformular nur {breite:.0f}px breit"


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
    # der Editor der Einleitung (davor steht der des eigenen Kopfbereichs)
    editor = seite.locator(".editor", has=seite.locator("#id_einleitung"))
    flaeche = editor.locator(".editor-flaeche")
    expect(flaeche).to_contain_text("Hallo")
    assert "onerror" not in flaeche.inner_html()  # Ereignisse fallen vor dem Anzeigen weg
    flaeche.click()
    seite.keyboard.press("End")
    seite.keyboard.type(" Welt")
    seite.keyboard.press("Shift+Home")
    editor.locator(".editor-leiste").get_by_role("button", name="Fett").click()
    editor.locator(".editor-reiter").get_by_role("tab", name="HTML").click()
    feld = seite.locator("#id_einleitung")
    expect(feld).to_be_visible()
    assert "Welt" in feld.input_value() and (
        "<b>" in feld.input_value() or "font-weight" in feld.input_value()
    )
    editor.locator(".editor-reiter").get_by_role("tab", name="Gestalten").click()
    leiste = editor.locator(".editor-leiste")
    flaeche.click()
    seite.keyboard.press("Control+a")
    expect(leiste.get_by_role("button", name="Kasten")).to_be_hidden()  # im Menü „Mehr“
    leiste.locator(".editor-mehr summary").click()
    leiste.get_by_role("button", name="Kasten").click()
    expect(flaeche.locator(".kasten")).to_have_count(1)
    flaeche.locator(".kasten").click()
    leiste.get_by_role("button", name="Mitte").click()
    editor.locator(".editor-reiter").get_by_role("tab", name="HTML").click()
    html = feld.input_value()
    assert "text-align: center" in html and 'class="kasten"' in html
    assert "background-color" in html
    # kein Speichern-Knopf: Was im Reiter „Gestalten“ geschrieben wurde, speichert sich selbst
    expect(seite.get_by_role("button", name="Speichern")).to_be_hidden()
    expect(seite.get_by_role("button", name="Vorschau")).to_be_visible()
    expect(seite.locator(".autosave-ok").first).to_be_visible()
    gespeichert = AntragText.objects.get(sprache="de").einleitung
    assert "Welt" in gespeichert and "kasten" in gespeichert


def test_antrag_merkzeichen_erst_mit_gdb(seite, admin):
    from apps.antraege.models import Abfrage, AntragEinstellungen

    e = AntragEinstellungen.laden()
    e.aktiv, e.behinderung = True, Abfrage.OPTIONAL
    e.save()
    seite.goto("/antrag/de/")
    block = seite.locator('[data-merkzeichen-fuer="id_gdb"]')
    expect(block).to_be_hidden()
    seite.select_option("#id_gdb", "50")
    expect(block).to_be_visible()
    block.get_by_label("G (erheblich gehbehindert)").check()
    seite.select_option("#id_gdb", "0")
    expect(block).to_be_hidden()
    assert not block.get_by_label("G (erheblich gehbehindert)").is_checked()


def test_antrag_weitere_person_uebernimmt_nachname_und_staat(seite, admin):
    from apps.antraege.models import Abfrage, AntragEinstellungen

    e = AntragEinstellungen.laden()
    e.aktiv = True
    e.angehoerige = Abfrage.OPTIONAL
    e.staatsangehoerigkeit = Abfrage.OPTIONAL
    e.save()
    seite.goto("/antrag/de/")
    staat = seite.eval_on_selector("#id_staatsangehoerigkeit option[data-land]", "o => o.value")
    seite.fill("#id_nachname", "Mustermann")
    seite.select_option("#id_staatsangehoerigkeit", staat)
    # Weitere Person übernimmt Nachname und Staatsangehörigkeit der Hauptperson
    expect(seite.locator("#id_p1_nachname")).to_have_value("Mustermann")
    expect(seite.locator("#id_p1_staatsangehoerigkeit")).to_have_value(staat)
    # Überschreibbar: eine eigene Eingabe bleibt, auch wenn die Hauptperson sich ändert
    seite.fill("#id_p1_nachname", "Anders")
    seite.fill("#id_nachname", "Neumann")
    expect(seite.locator("#id_p1_nachname")).to_have_value("Anders")
    expect(seite.locator("#id_p2_nachname")).to_have_value("Neumann")


def test_kundenstamm_merkzeichen_erst_mit_gdb(angemeldet, admin):
    h = Haushalt.objects.create(kundennummer="4711")
    erika = Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                                  nachname="Muster")  # fmt: skip
    seite = angemeldet(admin)
    seite.goto(reverse("kunden:teil", args=["4711", "person", erika.pk]))
    g = seite.get_by_label("G (erheblich gehbehindert)")
    expect(g).to_be_hidden()
    seite.select_option("#id_gdb", "80")
    g.check()
    # kein Speichern-Knopf mehr: die Seite speichert sofort (ADR 0145)
    expect(seite.locator(".feld", has=g).locator(".autosave-ok")).to_be_visible()
    erika.refresh_from_db()
    assert erika.zusatz["gdb"] == "GdB 80" and erika.zusatz["schwerbehindert"]

    seite.goto(reverse("kunden:haushalt_neu"))
    for gdb in ("#id_hp-gdb", "#id_a-0-gdb"):  # Hauptperson und Angehörige
        block = seite.locator(f'[data-merkzeichen-fuer="{gdb[1:]}"]')
        expect(block).to_be_hidden()
        seite.select_option(gdb, "50")
        expect(block).to_be_visible()


def test_sprachhinweis_und_angaben_beim_umstellen(seite, admin):
    from apps.antraege.models import Abfrage, AntragEinstellungen

    e = AntragEinstellungen.laden()
    e.aktiv, e.staatsangehoerigkeit = True, Abfrage.OPTIONAL
    e.save()
    seite.set_viewport_size({"width": 390, "height": 800})  # Handy: Sprachwahl links, 2. Zeile
    seite.goto("/antrag/de/")
    hinweis = seite.locator("#sprach-hinweis")
    expect(hinweis).to_contain_text("Hier können Sie die Sprache umstellen.")  # einmal je Sitzung
    auswahl = seite.locator("#sprache").bounding_box()
    pfeil = seite.locator(".sprach-pfeil").bounding_box()
    mitte = pfeil["x"] + pfeil["width"] / 2
    assert auswahl["x"] <= mitte <= auswahl["x"] + auswahl["width"]  # Pfeil zeigt auf die Auswahl
    seite.set_viewport_size({"width": 1280, "height": 800})
    hinweis.get_by_role("button", name="✕").click()
    expect(hinweis).to_be_hidden()
    seite.goto("/antrag/de/")
    expect(hinweis).to_be_hidden()
    seite.fill("#id_vorname", "Erika")
    seite.select_option("#id_staatsangehoerigkeit", "Deutschland")
    expect(hinweis).to_be_hidden()  # passt zur Sprache
    seite.select_option("#id_staatsangehoerigkeit", "Syrien")
    expect(hinweis).to_be_visible()
    expect(hinweis.locator("p[lang=ar]")).to_contain_text("يمكنك تغيير اللغة")
    hinweis.get_by_role("button", name="→ العربية").click()
    seite.wait_for_url("**/antrag/ar/")
    expect(seite.locator("#id_vorname")).to_have_value("Erika")  # Angaben bleiben
    expect(seite.locator("#id_staatsangehoerigkeit")).to_have_value("Syrien")
    seite.goto("/antrag/ar/")
    expect(seite.locator("#id_vorname")).to_have_value("")  # nur einmal übernommen


def test_live_suche_ab_zwei_zeichen(angemeldet, admin):
    from apps.adressen.models import Adresse

    Adresse.objects.create(nachname="Musterfrau", vorname="Erika")
    Adresse.objects.create(nachname="Beispiel", vorname="Max")
    seite = angemeldet(admin)
    seite.goto("/adressen/")
    ergebnis = seite.locator("#ergebnis")
    expect(ergebnis).to_contain_text("Beispiel")
    feld = seite.locator("#q")
    feld.press_sequentially("M", delay=50)
    seite.wait_for_timeout(700)
    expect(ergebnis).to_contain_text("Beispiel")  # ein Zeichen: sucht noch nicht
    feld.press_sequentially("u", delay=50)
    expect(ergebnis).not_to_contain_text("Beispiel")  # ab zwei Zeichen, ohne „Suchen“
    expect(ergebnis).to_contain_text("Musterfrau")
    expect(feld).to_be_focused()  # man kann weitertippen
    feld.press_sequentially("st", delay=50)
    expect(feld).to_have_value("Must")
    seite.wait_for_url("**q=Must**")
    feld.fill("")
    feld.dispatch_event("input")
    expect(ergebnis).to_contain_text("Beispiel")  # leer: wieder alle
    seite.goto("/hilfe/")  # Handbuch: Treffer gleich unter dem Feld
    seite.locator("#handbuch-suche").press_sequentially("Ampel", delay=50)
    expect(seite.locator("#handbuch-suche-liste .suche-liste")).to_be_visible()


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
    # Erst tippen, wenn die neue Seite fertig geladen ist: Vorher hört die Suche noch nicht zu,
    # die Eingabe ginge verloren und es käme keine Trefferliste.
    seite.wait_for_load_state()
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
    seite.goto(f"/aufruf/{AufrufEinstellungen.laden(stelle).steuer_schluessel}/mobil/")
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


def test_menuepunkt_unten_aufklappen_zeigt_alle_unterpunkte(angemeldet, admin):
    """Klappt man einen Bereich weit unten auf, schiebt sich das Menü hoch, bis alles zu sehen ist
    (auch eine Zwischenebene darin); der Titel bleibt sichtbar."""
    seite = angemeldet(admin)
    for breite, hoehe in ((1280, 420), (390, 500)):  # breit: das Menü schiebt; Handy: die Seite
        seite.set_viewport_size({"width": breite, "height": hoehe})
        seite.goto("/")
        if breite < 768:
            seite.locator(".menue-knopf").click()
        bereich = seite.locator("nav.seitenmenue > details.menue-bereich").last
        titel = bereich.locator(":scope > summary")
        if bereich.evaluate("d => d.open"):
            titel.click()
        titel.click()
        expect(bereich.locator("summary:visible, a:visible").last).to_be_in_viewport()
        expect(titel).to_be_in_viewport()
        gruppe = bereich.locator("details.menue-gruppe").last
        if gruppe.count():
            if gruppe.evaluate("d => d.open"):
                gruppe.locator(":scope > summary").click()
            gruppe.locator(":scope > summary").click()
            expect(gruppe.locator("a").last).to_be_in_viewport()
            expect(gruppe.locator(":scope > summary")).to_be_in_viewport()


def test_breite_liste_scrollbalken_oben(angemeldet, admin):
    """Breite Mitarbeitenden-Liste: ein zweiter Scrollbalken oben, synchron mit dem Rahmen."""
    from django.contrib.auth import get_user_model

    from apps.konten.models import Stammdaten

    U = get_user_model()
    for i in range(3):
        b = U.objects.create_user(f"m{i}.muster", first_name=f"Max{i}", last_name=f"Muster{i}",
                                  beschaeftigung="ehrenamtlich")  # fmt: skip
        Stammdaten.objects.create(benutzer=b, strasse="Musterweg 7", plz="12345", ort="Musterstadt",
                                  telefon="0123 456", handy="0170 111")  # fmt: skip
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 700, "height": 700})
    seite.goto(reverse("konten:ehrenamtliche"))
    # Der obere Balken wird für jede Liste eingebaut, aber nur bei zu breiter Tabelle gezeigt.
    oben = seite.locator(".tabelle-oben-scroll:visible")
    rahmen = seite.locator(".tabelle-rahmen").first
    expect(oben).to_have_count(1)
    # Oben schieben → der Rahmen zieht mit
    oben.evaluate("el => el.scrollLeft = 150")
    seite.wait_for_timeout(100)
    assert rahmen.evaluate("el => el.scrollLeft") > 50
    # und umgekehrt
    rahmen.evaluate("el => el.scrollLeft = 0")
    seite.wait_for_timeout(100)
    assert oben.evaluate("el => el.scrollLeft") < 50


def test_antragsliste_knoepfe_bleiben_rechts_sichtbar(angemeldet, admin):
    """Antragsliste auf dem Tablet: Ist die Tabelle breiter als der Bildschirm, bleiben die Knöpfe
    jeder Zeile (ansehen, bearbeiten … aufnehmen) am rechten Rand sichtbar – nicht nur die
    Überschrift."""
    from apps.antraege.models import Antrag

    for i in range(3):
        Antrag.objects.create(
            vorname="Erika", nachname=f"Beispiel-Langername {i}", email="erika@example.org",
            telefon="0123 456789", staatsangehoerigkeit="Deutschland",
        )  # fmt: skip
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 1000, "height": 750})
    seite.goto(reverse("antraege:liste"))
    rahmen = seite.locator(".tabelle-rahmen").first
    assert rahmen.evaluate("el => el.scrollWidth > el.clientWidth")  # breiter als der Platz
    rand = rahmen.bounding_box()
    rechts = rand["x"] + rand["width"]
    zeile = seite.locator("table.antraege-liste tbody tr").first
    for name in ("ansehen", "bearbeiten", "aufnehmen"):
        knopf = zeile.get_by_role("link", name=name).bounding_box()
        assert knopf["x"] >= rand["x"] and knopf["x"] + knopf["width"] <= rechts + 1, name
    # auch nach dem Rollen ganz nach links und rechts
    rahmen.evaluate("el => el.scrollLeft = el.scrollWidth")
    knopf = zeile.get_by_role("link", name="aufnehmen").bounding_box()
    assert knopf["x"] + knopf["width"] <= rechts + 1


def test_listen_am_handy_mit_spaltenueberschrift(angemeldet, admin):
    """Hochkant am Handy steht jede Zeile als Karte da, vor jedem Wert die Spaltenüberschrift –
    auch in Listen, deren Vorlage sie nicht selbst mitgibt (static/js/tabellen_titel.js)."""
    from apps.core.models import TafelEinstellungen
    from apps.wochenuebersicht.models import Selbstabholer

    t = TafelEinstellungen.laden()
    t.module = ["wochenuebersicht"]
    t.save()
    Selbstabholer.objects.create(name="Beispielhilfe", tage="Mo, Fr", personen=70)
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 390, "height": 800})
    seite.goto(reverse("wochenuebersicht:selbstabholer"))
    zeile = seite.locator("table.tabelle tbody tr").first
    zellen = zeile.locator("td")
    expect(zellen.nth(1)).to_have_attribute("data-titel", "Tage")
    expect(zellen.nth(2)).to_have_attribute("data-titel", "Personen")
    davor = "el => getComputedStyle(el, '::before').content"
    assert zellen.nth(1).evaluate(davor) == '"Tage: "'
    assert zellen.nth(0).evaluate(davor) == '"Einrichtung: "'
    expect(zellen.nth(4)).to_be_hidden()  # kein Telefon: kein leeres Feld mit Doppelpunkt
    seite.set_viewport_size({"width": 1280, "height": 900})
    expect(zellen.nth(4)).to_be_visible()  # breit: normale Tabelle mit allen Spalten


def test_liste_zeigt_kriterium_sofort(angemeldet, admin):
    """Listen: Ein gewähltes Kriterium zeigt das Ergebnis ohne „Anzeigen“ – auch die Spaltenwahl,
    die dabei aufgeklappt bleibt."""
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
    spalten = seite.locator("thead th").count()
    erste = seite.locator(".spalten-haken input").first
    wert = erste.get_attribute("value")
    with seite.expect_navigation():
        erste.uncheck()
    assert f"s={wert}" not in seite.url
    expect(seite.locator("thead th")).to_have_count(spalten - 1)
    # Die Spaltenwahl bleibt offen: gleich das nächste Häkchen, ohne neu aufzuklappen
    expect(seite.locator(".spalten-haken")).to_be_visible()
    with seite.expect_navigation():
        seite.locator(".spalten-haken input").first.check()
    expect(seite.locator("thead th")).to_have_count(spalten)
    # Ein anderes Kriterium klappt sie nicht wieder auf
    seite.click(".spalten-wahl summary")
    with seite.expect_navigation():
        seite.select_option("#f-status", "aktiv")
    expect(seite.locator(".spalten-haken")).to_be_hidden()


def test_warteliste_erscheint_sofort_sperrhinweis_laedt_nach(angemeldet, admin):
    """Die Warteliste erscheint sofort; den Sperrzeit-Hinweis lädt htmx danach nach, damit die
    Seite auch bei großem Kundenstamm nie hängt (Grund für das Hängen in der Produktion)."""
    from apps.antraege.models import Antrag
    from apps.core.models import TafelEinstellungen
    from apps.warteliste import ablauf

    t = TafelEinstellungen.laden()
    t.module = ["warteliste"]
    t.save()
    h = Haushalt.objects.create(
        kundennummer="00900", ausweis_gueltig_bis=timezone.localdate() - dt.timedelta(days=60)
    )
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    Antrag.objects.create(vorname="Erika", nachname="Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()
    seite = angemeldet(admin)
    seite.goto("/warteliste/")
    # Die Zeile steht sofort, ohne auf den Vergleich mit dem Kundenstamm zu warten.
    expect(seite.locator("tbody tr")).to_have_count(1)
    expect(seite.get_by_role("link", name="Beispiel", exact=True)).to_be_visible()  # Nachname
    # Der Sperrzeit-Hinweis wird danach per htmx eingesetzt.
    expect(seite.locator(".sperr-hinweis")).to_be_visible()


def test_abgleich_erscheint_sofort_treffer_laden_nach(angemeldet, admin):
    """Der Abgleich mit dem Kundenstamm erscheint sofort und lädt die Treffer per htmx nach,
    damit die Seite bei großem Kundenstamm nicht hängt."""
    from apps.antraege.models import Antrag
    from apps.core.models import TafelEinstellungen
    from apps.warteliste import ablauf

    t = TafelEinstellungen.laden()
    t.module = ["warteliste"]
    t.save()
    h = Haushalt.objects.create(
        kundennummer="00900", ausweis_gueltig_bis=timezone.localdate() - dt.timedelta(days=60)
    )
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    Antrag.objects.create(vorname="Erika", nachname="Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()
    seite = angemeldet(admin)
    seite.goto("/warteliste/abgleich/")
    # Überschrift sofort da, der Vergleich wird nachgeladen.
    expect(seite.get_by_role("heading", name="Abgleich mit dem Kundenstamm")).to_be_visible()
    expect(seite.locator(".abgleich-regler")).to_be_visible()  # Treffer per htmx eingesetzt


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


def test_statistik_legende_blendet_reihe_aus(angemeldet, admin):
    """Auf einen Legendeneintrag tippen blendet die Reihe aus (durchgestrichen) und zeichnet das
    Diagramm neu; erneutes Tippen blendet sie wieder ein."""
    from apps.kunden.models import Abholung

    mitte = _haushalte(1)  # legt Ausgabestelle „Mitte“ mit einem Haushalt (00041) an
    nord = Ausgabestelle.objects.create(name="Nord")
    mitte_haushalt = Haushalt.objects.get(kundennummer="00041")
    nord_haushalt = Haushalt.objects.create(kundennummer="09000")
    heute = timezone.localdate()
    # Mitte viele, Nord wenige Abholungen → deutlich unterschiedliche Höhe
    for _ in range(12):
        Abholung.objects.create(haushalt=mitte_haushalt, datum=heute, ausgabestelle=mitte)
    Abholung.objects.create(haushalt=nord_haushalt, datum=heute, ausgabestelle=nord)

    seite = angemeldet(admin)
    seite.goto("/statistik/")
    abschnitt = seite.locator("#verlauf_stellen")
    linien = abschnitt.locator("svg path.linie")
    expect(linien).to_have_count(2)
    erster = abschnitt.locator(".legende-schalter").first
    erster.click()
    # Abschnitt wird per htmx neu geladen: nur noch eine Linie, Eintrag durchgestrichen
    expect(seite.locator("#verlauf_stellen svg path.linie")).to_have_count(1)
    expect(seite.locator("#verlauf_stellen .legende-schalter").first).to_have_class(
        re.compile(r"\baus\b")
    )
    assert "aus_verlauf_stellen" in seite.url
    # Erneutes Tippen blendet wieder ein
    seite.locator("#verlauf_stellen .legende-schalter").first.click()
    expect(seite.locator("#verlauf_stellen svg path.linie")).to_have_count(2)


def test_haushalt_bearbeiten_speichert_sofort(angemeldet, admin):
    """Haushalt bearbeiten ohne Speichern-Knopf; die Kundennummer erst beim Verlassen (ADR 0145)."""
    from apps.kunden.models import Haushalt

    Haushalt.objects.create(kundennummer="00042", ort="Altdorf")
    seite = angemeldet(admin)
    seite.goto(reverse("kunden:bearbeiten", args=["00042"]))
    expect(seite.get_by_role("button", name="Haushalt speichern")).to_be_hidden()
    expect(seite.locator(".autosave-hinweis")).to_have_text("Änderungen werden sofort gespeichert.")
    ort = seite.get_by_label("Ort", exact=True)
    ort.fill("Musterstadt")
    expect(seite.locator(".feld", has=ort).locator(".autosave-ok")).to_be_visible()
    assert Haushalt.objects.get(kundennummer="00042").ort == "Musterstadt"
    # halb getippte Kundennummer wird nicht gespeichert; nach dem Verlassen wechselt die Seite
    nummer = seite.get_by_label("Kundennummer")
    nummer.fill("0004")
    seite.wait_for_timeout(1600)
    assert Haushalt.objects.filter(kundennummer="00042").exists()
    nummer.fill("00043")
    nummer.press("Tab")
    seite.wait_for_url("**" + reverse("kunden:bearbeiten", args=["00043"]))
    assert Haushalt.objects.get(kundennummer="00043").ort == "Musterstadt"


def test_ausgabestelle_zeilen_speichern_sofort(angemeldet, admin):
    """Zeilentabelle ohne Speichern-Knopf: neue Zeile nur einmal, Entfernen wirkt (ADR 0145)."""
    from apps.kunden.models import AusgabestelleZeit

    stelle = Ausgabestelle.objects.create(name="Mitte")
    seite = angemeldet(admin)
    seite.goto(reverse("kunden:ausgabestelle_bearbeiten", args=[stelle.pk]))
    expect(seite.get_by_role("button", name="Speichern")).to_be_hidden()
    zeilen = seite.locator("#zeilen-zeiten tr")
    expect(zeilen).to_have_count(3)
    seite.select_option("#id_z-0-wochentag", index=1)
    seite.fill("#id_z-0-von", "10:00")
    seite.fill("#id_z-0-bis", "12:00")
    seite.locator("#id_z-0-bis").press("Tab")
    expect(zeilen).to_have_count(4)  # gespeichert: eine freie Zeile kam dazu
    assert AusgabestelleZeit.objects.filter(ausgabestelle=stelle).count() == 1
    # dieselbe Zeile weiter ändern: kein zweiter Eintrag
    hinweis = seite.locator("#id_z-0-hinweis")
    hinweis.fill("nur gerade Wochen")
    hinweis.press("Tab")
    expect(seite.locator("td", has=hinweis).locator(".autosave-ok")).to_be_visible()
    zeit = AusgabestelleZeit.objects.get(ausgabestelle=stelle)
    assert zeit.hinweis == "nur gerade Wochen"
    # entfernen: die Tabelle wird neu aufgebaut, die Zeile ist weg
    seite.locator("#id_z-0-DELETE").check()
    expect(zeilen).to_have_count(3)
    assert not AusgabestelleZeit.objects.filter(ausgabestelle=stelle).exists()


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
    seite.goto(f"/aufruf/{AufrufEinstellungen.laden(stelle).steuer_schluessel}/mobil/")
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
    # Diese Fahrdienst-Person bekommt ein Konto mit PIN, um sich am Monitor selbst auszutragen
    from django.contrib.auth import get_user_model

    konto = get_user_model().objects.create_user(
        f"monitor-{p.wer.pk}", first_name=p.wer.vorname, last_name=p.wer.nachname
    )
    p.wer.konto = konto
    p.wer.save(update_fields=["konto"])
    pin.setzen(konto, "482915")

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
    expect(dialog).to_contain_text(f"Ich bin {p.wer.name}")
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


def test_hintergrundbilder_gehen_beim_naechsten_aufruf_weiter(seite, admin):
    """Mehrere Hintergrundbilder: der nächste Seitenaufruf blendet zum nächsten Bild über."""
    import io

    from PIL import Image

    from apps.core.models import Hintergrundbild, TafelEinstellungen

    puffer = io.BytesIO()
    Image.new("RGB", (4, 4), "green").save(puffer, "PNG")
    bild = puffer.getvalue()  # Medien liefert der Testserver nicht aus
    seite.route("**/media/**", lambda r: r.fulfill(body=bild, content_type="image/png"))
    t = TafelEinstellungen.laden()
    t.hintergrund_anmeldung = "oeffentlich/hintergrund/a.png"
    t.save()
    Hintergrundbild.objects.create(bereich="anmeldung", bild="oeffentlich/hintergrund/b.png")
    seite.goto(reverse("konten:anmelden"))
    hintergrund = seite.locator(".hintergrund")
    expect(hintergrund).to_have_count(1)
    expect(hintergrund).to_have_attribute("style", re.compile(r"a\.png"))
    seite.reload()
    expect(hintergrund.last).to_have_attribute("style", re.compile(r"b\.png"))
    expect(hintergrund).to_have_count(1)  # das alte Bild ist nach dem Überblenden weg


def test_nach_dem_absenden_bleibt_die_position(angemeldet, admin, muster):
    """Vorschau springt zum Ergebnis; ein Formular an dieselbe Seite landet nicht wieder oben."""
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 1100, "height": 600})
    seite.goto(reverse("serienbriefe:erstellen"))
    seite.get_by_label("Vorlage").select_option(index=1)
    seite.get_by_role("button", name="Vorschau").click()
    expect(seite.locator("#ergebnis-vorschau")).to_be_in_viewport()
    assert seite.evaluate("window.scrollY") > 200

    seite.goto(reverse("statistik:uebersicht"))
    seite.evaluate("window.scrollTo(0, 700)")
    with seite.expect_navigation():
        seite.locator("form.filter-kompakt").first.evaluate("f => f.requestSubmit()")
    seite.wait_for_function("window.scrollY > 600")


def test_serienbrief_empfaenger_mit_auswahlmenue(angemeldet, admin, muster):
    """Nur die Filter der gewählten Empfänger; Mehrfachauswahl als Menü mit Suche."""
    for kuerzel in "BCDEFGHI":
        Kundengruppe.objects.create(kuerzel=kuerzel, name=f"Gruppe {kuerzel}", wochentage="Mo")
    seite = angemeldet(admin)
    seite.goto(reverse("serienbriefe:erstellen"))
    kategorien = seite.locator("details#id_kategorien")
    gruppen = seite.locator("details#id_kundengruppen")
    expect(kategorien).to_be_visible()
    expect(gruppen).to_be_hidden()  # nur bei „Kunden“
    seite.get_by_label("Empfänger").select_option("kunden")
    expect(kategorien).to_be_hidden()
    expect(gruppen.locator("summary")).to_have_text("alle Kundengruppen")
    gruppen.locator("summary").click()
    gruppen.get_by_placeholder("In der Liste suchen …").fill("gruppe c")
    expect(gruppen.get_by_label("B – Gruppe B")).to_be_hidden()
    gruppen.get_by_label("C – Gruppe C").check()
    expect(gruppen.locator("summary")).to_contain_text("C – Gruppe C")
    seite.locator("h1").click()  # daneben klicken klappt zu
    expect(gruppen).not_to_have_attribute("open", "")


def test_serienbrief_vorlage_platzhalter_ziehen_und_antippen(angemeldet, admin):
    """Platzhalter-Kärtchen: antippen fügt an der Schreibmarke ein, ziehen an der Drop-Stelle."""
    from apps.serienbriefe.models import Vorlage

    seite = angemeldet(admin)
    seite.goto(reverse("serienbriefe:vorlage_neu"))
    seite.locator("#id_name").fill("Probe")
    seite.get_by_label("Betreff").fill("Einladung ")
    editor = seite.locator(".editor", has=seite.locator("#id_text"))
    flaeche = editor.locator(".editor-flaeche")
    flaeche.click()
    seite.keyboard.type("Liebe Grüße")
    seite.keyboard.press("Home")
    seite.locator('[data-platzhalter-karte="anrede"]').click()  # wie Antippen auf dem iPad
    feld = flaeche.locator('[data-platzhalter="anrede"]')
    expect(feld).to_have_text("Briefanrede")
    expect(feld).to_have_attribute("contenteditable", "false")
    text_vorher = flaeche.inner_text()
    assert text_vorher.index("Briefanrede") < text_vorher.index("Liebe")  # an der Schreibmarke
    seite.locator('[data-platzhalter-karte="vorname"]').drag_to(flaeche)
    expect(flaeche.locator('[data-platzhalter="vorname"]')).to_have_text("Vorname")
    # Schriftgröße: ohne Markierung gilt sie für die Zeile, in der die Schreibmarke steht
    flaeche.click()
    seite.keyboard.press("End")
    editor.get_by_label("Schriftgröße").select_option(label="groß")
    assert "x-large" in flaeche.inner_html()
    expect(editor.get_by_label("Schriftgröße")).to_have_value("")  # wieder bereit
    # Im Betreff gewesen: dort einfügen
    seite.get_by_label("Betreff").click()
    seite.keyboard.press("End")
    seite.locator('[data-platzhalter-karte="jahr"]').click()
    expect(seite.get_by_label("Betreff")).to_have_value("Einladung {jahr}")
    editor.locator(".editor-reiter").get_by_role("tab", name="HTML").click()
    html = seite.locator("#id_text").input_value()
    assert "{anrede}" in html and "{vorname}" in html and "platzhalter" not in html
    editor.locator(".editor-reiter").get_by_role("tab", name="Gestalten").click()
    expect(flaeche.locator(".platzhalter")).to_have_count(2)
    seite.get_by_role("button", name="Anlegen").click()
    expect(seite.get_by_text("Vorlage „Probe“ gespeichert.")).to_be_visible()
    v = Vorlage.objects.get(name="Probe")
    assert "{anrede}" in v.text and "{vorname}" in v.text and "Liebe Grüße" in v.text
    assert v.betreff == "Einladung {jahr}" and "platzhalter" not in v.text


def test_serienbrief_vorlage_platzhalter_entfernen(angemeldet, admin):
    """Ein gesetzter Platzhalter lässt sich über das × oder markiert mit Entf wieder entfernen."""
    seite = angemeldet(admin)
    seite.goto(reverse("serienbriefe:vorlage_neu"))
    editor = seite.locator(".editor", has=seite.locator("#id_text"))
    flaeche = editor.locator(".editor-flaeche")
    flaeche.click()
    seite.keyboard.type("Hallo ")
    seite.locator('[data-platzhalter-karte="anrede"]').click()
    seite.locator('[data-platzhalter-karte="vorname"]').click()
    expect(flaeche.locator(".platzhalter")).to_have_count(2)
    # × am rechten Rand des Feldes antippen
    anrede = flaeche.locator('[data-platzhalter="anrede"]')
    box = anrede.bounding_box()
    seite.mouse.click(box["x"] + box["width"] - 8, box["y"] + box["height"] / 2)
    expect(anrede).to_have_count(0)
    # Feld antippen (markiert es) und Entf
    vorname = flaeche.locator('[data-platzhalter="vorname"]')
    vorname.click(position={"x": 5, "y": 5})
    seite.keyboard.press("Delete")
    expect(flaeche.locator(".platzhalter")).to_have_count(0)
    expect(flaeche).to_contain_text("Hallo")
    editor.locator(".editor-reiter").get_by_role("tab", name="HTML").click()
    html = seite.locator("#id_text").input_value()
    assert "{anrede}" not in html and "{vorname}" not in html and "Hallo" in html


def test_warteliste_spalten_waehlen_bleibt_gemerkt(angemeldet, admin):
    from apps.antraege.models import Antrag
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.module = ["warteliste"]
    t.save()
    Antrag.objects.create(vorname="Erika", nachname="Beispiel", email="erika@example.org")
    seite = angemeldet(admin)
    seite.goto(reverse("warteliste:liste"))
    kontakt = seite.get_by_role("columnheader", name=re.compile("Kontakt"))
    geburt = seite.get_by_role("columnheader", name=re.compile("Geburtsdatum"))
    expect(kontakt).to_be_visible()
    expect(geburt).to_have_count(0)  # zu Beginn aus
    # Die Spaltenwahl wird je Konto gespeichert (Formular mit „Übernehmen").
    seite.get_by_text("Spalten wählen").click()
    form = seite.locator("details.spalten-wahl form")
    form.locator('input[value="kontakt"]').uncheck()
    form.locator('input[value="geburtsdatum"]').check()
    form.get_by_role("button", name="Übernehmen").click()
    expect(seite.get_by_role("columnheader", name=re.compile("Kontakt"))).to_have_count(0)
    expect(seite.get_by_role("columnheader", name=re.compile("Geburtsdatum"))).to_be_visible()
    seite.reload()
    expect(seite.get_by_role("columnheader", name=re.compile("Kontakt"))).to_have_count(0)
    expect(seite.get_by_role("columnheader", name=re.compile("Geburtsdatum"))).to_be_visible()


def test_verlaengern_begruendung_eintragen_und_pflicht(angemeldet, admin):
    """Trotzdem verlängern: Begründung ist ein richtiges Feld und dann Pflicht (zeigen_bei.js)."""
    from apps.kunden.models import KundenEinstellungen, Nachricht

    e = KundenEinstellungen.laden()
    e.verlaengern_regel = KundenEinstellungen.Verlaengern.ALLE
    e.verlaengern_ab_alter = 60
    e.save()
    bis = timezone.localdate() + dt.timedelta(days=20)
    h = Haushalt.objects.create(kundennummer="00057", ausweis_gueltig_bis=bis)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Jonas", nachname="Probe",
                          geburtsdatum=dt.date(1990, 2, 1))  # fmt: skip
    Nachricht.objects.create(kundennummer="00057", anliegen="verlaengern", von="einlass")
    seite = angemeldet(admin)
    seite.goto(reverse("kunden:verlaengern"))
    feld = seite.get_by_role("textbox", name=re.compile("Begründung"))
    assert feld.evaluate("e => e.required") is False
    seite.locator('input[name="wahl_00057"][value="verlaengern"]').check()
    assert feld.evaluate("e => e.required") is True
    seite.get_by_role("button", name="Ausgewählte ausführen").click()
    expect(seite.get_by_text("Erledigt (")).to_have_count(0)  # Browser hält das Absenden an
    feld.fill("Härtefall, Bescheid folgt")
    seite.get_by_role("button", name="Ausgewählte ausführen").click()
    expect(seite.get_by_text("1 Ausweis verlängert.")).to_be_visible()
    h.refresh_from_db()
    assert h.ausweis_gueltig_bis > timezone.localdate() + dt.timedelta(days=300)


def test_ausweise_drucken_oeffnet_neues_fenster(angemeldet, admin):
    """Sammeldruck öffnet das PDF in einem eigenen Fenster; die Seite bleibt (iPad-App)."""
    from apps.kunden.models import Nachricht

    for nummer in ("00061", "00062"):
        Haushalt.objects.create(kundennummer=nummer)
        Nachricht.objects.create(kundennummer=nummer, anliegen="verlaengern",
                                 ergebnis="Verlängert bis 30.11.2027",
                                 erledigt_am=timezone.now(), erledigt_von="chefin")  # fmt: skip
    Nachricht.objects.create(kundennummer="00061", anliegen="ausweis")
    seite = angemeldet(admin)
    seite.goto(reverse("kunden:verlaengern"))
    seite.locator('input[name="nummer"][value="00062"]').check()
    knopf = seite.get_by_role("button", name="Angehakte Ausweise drucken (PDF)")
    assert "nummer=00062" in _pdf_fenster(seite, knopf.click)
    assert seite.url.endswith(reverse("kunden:verlaengern"))
    seite.goto(reverse("kunden:nachrichten"))
    link = seite.get_by_role("link", name=re.compile("Alle gemeldeten Ausweise drucken"))
    assert "gemeldet=1" in _pdf_fenster(seite, link.click)
    expect(seite.get_by_role("heading", name="Nachrichten der Ausgabestellen")).to_be_visible()


def test_wartezeit_handy_sprachhinweis(seite, admin):
    """Wartezeit aufs Handy: Hinweis auf die Sprachwahl beim ersten Besuch; nach der Anmeldung
    zweisprachig Deutsch und die Sprache zur Staatsangehörigkeit, „Deutsch“ wählen = nur Deutsch."""
    from apps.aufruf.models import HandyEinstellungen
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    HandyEinstellungen.objects.update_or_create(pk=1, defaults={"modus": "alle"})
    stelle = Ausgabestelle.objects.create(name="Mitte")
    g = Kundengruppe.objects.create(name="Gruppe", ausgabestelle=stelle)
    h = Haushalt.objects.create(kundennummer="00077", kundengruppe=g)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Ayla", nachname="Probe",
                          geburtsdatum=dt.date(1975, 3, 12),
                          staatsangehoerigkeit="Türkei")  # fmt: skip
    seite.goto(reverse("warten:seite"))
    hinweis = seite.locator("#sprach-hinweis")
    expect(hinweis).to_be_visible()  # beim ersten Besuch
    seite.locator(".sprach-hinweis-zu").click()
    seite.get_by_label("Kundennummer").fill("00077")
    seite.get_by_label("Geburtsdatum der Hauptperson").fill("1975-03-12")
    seite.get_by_role("button", name="Anmelden").click()
    abmelden = seite.get_by_role("button", name=re.compile("Dieses Handy abmelden"))
    expect(abmelden).to_contain_text("Bu telefonun oturumunu kapat")  # Türkisch gleich dabei
    expect(seite.locator("html")).to_have_attribute("lang", "de")
    expect(hinweis).to_be_hidden()  # kein Vorschlag mehr nötig
    seite.locator("#sprache").select_option("de")
    expect(abmelden).not_to_contain_text("Bu telefonun oturumunu kapat")


def test_wartezeit_push_einschalten(seite, admin):
    """Benachrichtigung aufs Handy (ADR 0134): Service Worker meldet sich an, das Abo kommt beim
    Server an, der Knopf wird zu „Benachrichtigung ist an“ und lässt sich wieder ausschalten. Der
    Push-Dienst des Browsers ist im Test durch ein festes Abo ersetzt (kein Netz nötig)."""
    from apps.aufruf.models import HandyEinstellungen, HandyZugang
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    HandyEinstellungen.objects.update_or_create(pk=1, defaults={"modus": "alle"})
    stelle = Ausgabestelle.objects.create(name="Mitte")
    g = Kundengruppe.objects.create(name="Gruppe", ausgabestelle=stelle)
    h = Haushalt.objects.create(kundennummer="00078", kundengruppe=g)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Ayla", nachname="Probe",
                          geburtsdatum=dt.date(1975, 3, 12))  # fmt: skip
    # öffentlicher Beispielschlüssel aus RFC 8291 (kein Geheimnis)
    p256dh = (
        "BCVxsr7N_eNgVRqvHtD0zTZsEc6-VV-JvLexhqUzORcxaOzi6-AYWXvTBHm4bjyPjs7Vd8pZGH6SRpkNtoIAiw4"
    )
    seite.context.grant_permissions(["notifications"])
    seite.add_init_script(
        "var P256DH = '"
        + p256dh
        + "';"
        + """
      // Erlaubnis wie nach „Zulassen“ (manche Testbrowser melden sonst immer „blockiert“)
      if (window.Notification) {
        Object.defineProperty(Notification, "permission",
                              { get: function () { return "granted"; } });
        Notification.requestPermission = function () { return Promise.resolve("granted"); };
      }
      if (window.PushManager) {
        PushManager.prototype.getSubscription = function () { return Promise.resolve(null); };
        PushManager.prototype.subscribe = function () {
          return Promise.resolve({ unsubscribe: function () { return Promise.resolve(true); },
            toJSON: function () { return { endpoint: "https://fcm.googleapis.com/fcm/send/probe",
              keys: { p256dh: P256DH, auth: "BTBZMqHH6r4Tts7J_aSIgg" } }; } });
        };
      }"""
    )
    seite.goto(reverse("warten:seite"))
    seite.get_by_label("Kundennummer").fill("00078")
    seite.get_by_label("Geburtsdatum der Hauptperson").fill("1975-03-12")
    seite.get_by_role("button", name="Anmelden").click()
    knopf = seite.get_by_role("button", name=re.compile("Benachrichtigung aufs Handy"))
    expect(knopf).to_be_visible()
    knopf.click()
    status = seite.locator(".push-status")
    expect(status).to_be_visible()
    expect(status).to_contain_text("Benachrichtigung ist an")
    assert HandyZugang.objects.get().push_adresse == "https://fcm.googleapis.com/fcm/send/probe"
    status.get_by_role("button", name="ausschalten").click()
    expect(knopf).to_be_visible()
    seite.wait_for_timeout(300)
    assert HandyZugang.objects.get().push_adresse == ""


def test_pdf_aus_formular_in_der_ipad_app(angemeldet, admin):
    """In der App vom Home-Bildschirm öffnen auch POST-Formulare (Vorschau einer Vorlage) das
    PDF über der Seite statt in einem eigenen Fenster, aus dem man nicht zurückkäme (ADR 0141)."""
    seite = angemeldet(admin)
    seite.add_init_script("Object.defineProperty(navigator, 'standalone', {get: () => true})")
    seite.goto(reverse("serienbriefe:vorlage_neu"))
    seite.locator("#id_name").fill("Probe")
    seite.get_by_label("Betreff").fill("Hallo")
    seite.locator(".editor-flaeche").first.click()
    seite.keyboard.type("Liebe Grüße")
    vorher = len(seite.context.pages)
    seite.get_by_role("button", name="Vorschau (PDF)").click()
    fenster = seite.locator("dialog.pdf-fenster")
    expect(fenster.locator("img.druck-seite").first).to_be_visible()
    expect(fenster.get_by_role("button", name="🖨 Drucken")).to_be_visible()
    assert len(seite.context.pages) == vorher
    fenster.get_by_role("button", name="✕ Schließen").click()
    expect(fenster).to_have_count(0)
    assert seite.url.endswith(reverse("serienbriefe:vorlage_neu"))


def test_nach_oben_knopf(angemeldet, admin):
    """„Nach oben“-Knopf: erscheint nach dem Scrollen und springt zurück an den Seitenanfang."""
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 1024, "height": 420})
    seite.goto(reverse("core:hilfe"))  # das Handbuch ist lang genug zum Scrollen
    knopf = seite.locator("#nach-oben")
    expect(knopf).to_be_hidden()
    seite.mouse.move(500, 200)
    seite.mouse.wheel(0, 1400)
    expect(knopf).to_be_visible()
    knopf.click()
    seite.wait_for_function("(window.scrollY || document.documentElement.scrollTop) < 50")
    expect(knopf).to_be_hidden()


def test_abwesend_melden_bis_springt_mit_und_heute_morgen(angemeldet, admin):
    """Abwesend melden: Stellt man „Von“ auf einen späteren Tag, springt „Bis“ mit (nie „von
    morgen bis heute“); unter beiden Feldern setzen „Heute“ und „Morgen“ das Datum."""
    from apps.kunden.models import Haushalt, KundenEinstellungen, Notiz, Person

    k = KundenEinstellungen.laden()
    k.krankmeldung = True
    k.save()
    h = Haushalt.objects.create(kundennummer="04711")
    Person.objects.create(haushalt=h, vorname="Erika", nachname="Beispiel", ist_hauptperson=True)
    heute = dt.date.today()
    morgen = heute + dt.timedelta(days=1)
    seite = angemeldet(admin)
    seite.goto(reverse("kunden:haushalt", args=["04711"]))
    seite.get_by_text("Abwesend melden …").click()
    von, bis = seite.locator("#krank-von"), seite.locator("#krank-bis")
    expect(von).to_have_value(f"{heute:%d.%m.%Y}")
    felder = seite.locator(".krank-felder .feld")
    felder.nth(1).get_by_role("button", name="Morgen").click()
    expect(von).to_have_value(f"{morgen:%d.%m.%Y}")
    expect(bis).to_have_value(f"{morgen:%d.%m.%Y}")  # springt mit
    # Ein späteres „Bis“ bleibt stehen, wenn „Von“ davor liegt
    spaeter = heute + dt.timedelta(days=9)
    bis.fill(f"{spaeter:%d.%m.%Y}")
    bis.blur()
    felder.nth(1).get_by_role("button", name="Heute").click()
    expect(von).to_have_value(f"{heute:%d.%m.%Y}")
    expect(bis).to_have_value(f"{spaeter:%d.%m.%Y}")
    # Getippt statt getippt-per-Knopf: auch dann springt „Bis“ mit
    weit = heute + dt.timedelta(days=20)
    von.fill(f"{weit:%d.%m.%Y}")
    von.blur()
    expect(bis).to_have_value(f"{weit:%d.%m.%Y}")
    felder.nth(2).get_by_role("button", name="Morgen").click()  # „Bis“ selbst zurückstellen …
    felder.nth(1).get_by_role("button", name="Morgen").click()
    seite.get_by_role("button", name="Abwesenheit speichern").click()
    seite.wait_for_load_state()
    n = Notiz.objects.get(kundennummer="04711")
    assert (n.krank_von, n.krank_bis) == (morgen, morgen)


def test_datum_tippen_und_kalender(angemeldet, admin):
    """Datumsfeld: man kann TT.MM.JJJJ eintippen (kein Zwang zum Kalender); der 📅-Knopf
    (static/js/datum.js) steht als Alternative daneben und schreibt die Kalenderwahl ins Feld."""
    from apps.adressen.models import Adresse

    seite = angemeldet(admin)
    seite.goto(reverse("adressen:neu"))
    seite.locator("#id_art").select_option("person")
    seite.locator("#id_nachname").fill("Tippmann")
    datum = seite.locator("#id_geburtsdatum")
    # JS hat das Feld zum Textfeld gemacht und einen Kalender-Knopf danebengestellt.
    assert datum.get_attribute("type") == "text"
    huelle = datum.locator("xpath=ancestor::span[contains(@class,'datum-feld')]")
    expect(huelle.locator(".datum-kalender")).to_have_count(1)
    # Das echte Kalender-Feld liegt genau über dem Knopf: Ein Tipp auf den Knopf trifft es direkt
    # (nur so öffnet der Kalender auf dem iPad zuverlässig) und übernimmt das getippte Datum.
    datum.fill("03.02.1999")
    mitte = huelle.locator(".datum-kalender").bounding_box()
    oben = seite.evaluate(
        "([x, y]) => document.elementFromPoint(x, y).className",
        [mitte["x"] + mitte["width"] / 2, mitte["y"] + mitte["height"] / 2],
    )
    assert "datum-pick" in oben
    huelle.locator(".datum-pick").dispatch_event("pointerdown")  # der Tipp, ohne Kalenderfenster
    expect(huelle.locator(".datum-pick")).to_have_value("1999-02-03")
    # Alternative Kalender: eine Auswahl im versteckten Kalender-Feld landet im Textfeld.
    seite.evaluate(
        "() => { const p = document.querySelector('#id_geburtsdatum')"
        ".closest('.datum-feld').querySelector('.datum-pick');"
        " p.value = '2001-12-24'; p.dispatchEvent(new Event('change', { bubbles: true })); }"
    )
    expect(datum).to_have_value("24.12.2001")
    # Einfach eintippen – kein Kalender nötig – und speichern.
    datum.fill("15.03.1980")
    seite.get_by_role("button", name="Speichern").click()
    seite.wait_for_url("**/adressen/*/")
    assert Adresse.objects.get(nachname="Tippmann").geburtsdatum == dt.date(1980, 3, 15)


def test_listen_position_bleibt_beim_zurueckgehen(angemeldet, admin):
    """Lange Liste: Wer eine Person öffnet und über „Zurück“ zurückkommt, landet wieder an
    derselben Stelle, nicht ganz oben (static/js/listen_position.js)."""
    from apps.adressen.models import Adresse

    for i in range(40):
        Adresse.objects.create(art=Adresse.Art.PERSON, nachname=f"Person {i:02d}", vorname="Test")
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 1024, "height": 480})
    seite.goto("/adressen/?anzahl=alle")  # alle auf einer Seite: lang genug zum Scrollen
    expect(seite.locator("tbody td a[href^='/adressen/']").first).to_be_visible()
    # Ein Stück nach unten scrollen und die Höhe merken.
    seite.evaluate("window.scrollTo(0, 900)")
    hoehe = seite.evaluate("() => window.scrollY")
    assert hoehe > 300
    # Eine Person öffnen (wie ein Klick in der Liste) …
    pk = Adresse.objects.order_by("nachname").values_list("pk", flat=True)[20]
    seite.evaluate(f"() => {{ location.href = '/adressen/{pk}/'; }}")
    seite.wait_for_url(f"**/adressen/{pk}/")
    # … und über den Zurück-Knopf zurück: wieder dieselbe Höhe, nicht oben.
    seite.go_back()
    seite.wait_for_url("**/adressen/?anzahl=alle")
    seite.wait_for_function(f"() => Math.abs(window.scrollY - {hoehe}) < 12")


def test_aufnahme_angehoerige_ohne_leere_zeilen(angemeldet, admin):
    """Aufnahme-Assistent, Schritt „Angehörige“: Leere Zeilen sind ausgeblendet; „Weitere Person
    hinzufügen“ holt je Klick eine dazu, und die Eingabe wird übernommen."""
    from apps.antraege.models import Antrag, AntragPerson

    a = Antrag.objects.create(
        vorname="Erika", nachname="Beispiel", geburtsdatum=dt.date(1980, 2, 3)
    )
    AntragPerson.objects.create(antrag=a, vorname="Paul", nachname="Beispiel")
    seite = angemeldet(admin)
    seite.goto(reverse("antraege:aufnahme", args=[a.pk]))
    seite.get_by_role("button", name="Weiter", exact=True).click()  # Kunde suchen: neuer Kunde
    seite.get_by_role("button", name="Weiter", exact=True).click()  # Daten abgleichen
    expect(seite.get_by_role("heading", name="3. Angehörige")).to_be_visible()
    zeilen = seite.locator(".person-karte:visible")
    expect(zeilen).to_have_count(1)  # nur Paul, keine leeren Zeilen
    seite.get_by_role("button", name="Weitere Person hinzufügen").click()
    expect(zeilen).to_have_count(2)
    zeilen.nth(1).get_by_label("Vorname").fill("Lina")
    seite.get_by_role("button", name="Weiter", exact=True).click()
    seite.goto(reverse("antraege:aufnahme_schritt", args=[a.pk, "personen"]))
    expect(seite.locator(".person-karte:visible")).to_have_count(2)
    expect(seite.locator("input[value=Lina]")).to_be_visible()


def test_foto_wird_sofort_gespeichert(angemeldet, admin):
    """Foto eines Nachweises: Nach der Aufnahme geht das Formular von selbst ab (kein Knopf
    „speichern“), und das Feld bleibt für die nächste Seite offen."""
    import io

    from PIL import Image

    from apps.kunden.models import HaushaltDokument

    _haushalte(1)
    bild = io.BytesIO()
    Image.new("RGB", (40, 30), "white").save(bild, "PNG")
    seite = angemeldet(admin)
    seite.goto("/kunden/haushalt/00041/")
    seite.get_by_text("Foto aufnehmen").click()
    feld = seite.locator("#foto-dateien")
    feld.set_input_files({"name": "seite1.png", "mimeType": "image/png", "buffer": bild.getvalue()})
    expect(seite.get_by_text("Foto abgelegt:").first).to_be_visible()
    expect(seite).to_have_url(re.compile("foto=1"))
    expect(seite.locator("#foto-dateien")).to_be_visible()  # offen für die nächste Seite
    assert HaushaltDokument.objects.count() == 1


def test_stempeln_am_aushang_monitor(seite, admin, benutzer_mit_rolle):
    """Am Monitor (ADR 0123): „Stempeln“ öffnet ein Fenster mit Name + PIN und QR-Code. Nach der
    PIN erscheinen die passenden Knöpfe; „Kommen“ stempelt und meldet es am Monitor."""
    from apps.aushang import pin
    from apps.aushang.models import Aushang, AushangSeite
    from apps.core.models import TafelEinstellungen
    from apps.dienstplan import beispiel as dp_beispiel
    from apps.personal import arbeitszeit

    t = TafelEinstellungen.laden()
    t.module = ["aushang", "dienstplan"]
    t.save()
    dp_beispiel.anlegen(seed=1)
    stelle = Ausgabestelle.objects.get(name=dp_beispiel.STELLE)
    kim = benutzer_mit_rolle("kim", "Ausgabe")
    kim.first_name, kim.last_name, kim.beschaeftigung = "Kim", "Probe", "fest"
    kim.save()
    pin.setzen(kim, "482915")
    aushang = Aushang.objects.create(name="Monitor Ausgabe")
    AushangSeite.objects.create(aushang=aushang, art="dienstplan", wert=str(stelle.pk), monate=1)
    seite.goto(f"/aushang/zeigen/{aushang.schluessel}/")
    seite.get_by_role("button", name="Stempeln").click()
    fenster = seite.locator("#aushang-dialog")
    expect(fenster.get_by_role("heading", name="Arbeitszeit stempeln")).to_be_visible()
    expect(fenster.locator("[data-stempeln-qr] svg")).to_be_visible()
    fenster.locator("select[name=person]").select_option(label="Kim Probe")
    fenster.locator("input[name=pin]").fill("000000")
    fenster.get_by_role("button", name="Weiter").click()
    expect(fenster.locator(".aushang-fehler")).to_contain_text("PIN stimmt nicht")
    fenster.locator("input[name=pin]").fill("482915")
    fenster.get_by_role("button", name="Weiter").click()
    expect(fenster.locator("[data-stempeln-name]")).to_have_text("Kim Probe")
    fenster.get_by_role("button", name="Kommen", exact=True).click()
    expect(seite.locator("#aushang-meldung")).to_contain_text("Kim Probe: Kommen um")
    expect(fenster).to_be_hidden()
    assert arbeitszeit.laufend(kim)
    # Beim nächsten Mal bietet das Fenster Pause und Gehen an
    seite.get_by_role("button", name="Stempeln").click()
    fenster.locator("select[name=person]").select_option(label="Kim Probe")
    fenster.locator("input[name=pin]").fill("482915")
    fenster.get_by_role("button", name="Weiter").click()
    expect(fenster.get_by_role("button", name="Gehen", exact=True)).to_be_visible()
    expect(fenster.get_by_role("button", name="Pause", exact=True)).to_be_visible()


def test_mail_empfaenger_auswaehlen_speichert_sofort(angemeldet, admin, benutzer_mit_rolle):
    """Zentrale Seite „Wer bekommt welche Mail“ (ADR 0125): Häkchen setzen genügt."""
    from apps.ausgabe import korrekturen

    for name in ("anna", "bert"):
        b = benutzer_mit_rolle(name, rollen.ADMIN)
        b.email = f"{name}@example.org"
        b.save()
    seite = angemeldet(admin)
    seite.goto("/einstellungen/mail/empfaenger/")
    zeile = seite.locator("tr", has_text="Korrekturwunsch vom Einlass")
    expect(zeile.locator("summary")).to_contain_text("Wie vorgesehen")
    zeile.locator("summary").click()
    zeile.locator("label", has_text="anna (anna@example.org)").click()
    expect(zeile.get_by_text("gespeichert")).to_be_visible()
    assert set(korrekturen.empfaenger()) == {"anna@example.org", "bert@example.org"}

    def gespeichert(erwartet):
        """Das Speichern läuft kurz nach dem Klick im Hintergrund: darauf warten."""
        for _ in range(50):
            if korrekturen.empfaenger() == erwartet:
                return True
            seite.wait_for_timeout(100)
        return False

    # ohne „Wie vorgesehen“ bekommt nur Anna die Mail
    zeile.locator("label", has_text="Wie vorgesehen").click()
    expect(zeile.locator("summary")).not_to_contain_text("Wie vorgesehen")
    assert gespeichert(["anna@example.org"])
    # nichts angehakt: niemand
    zeile.locator("label", has_text="anna (anna@example.org)").click()
    expect(zeile.locator("summary")).to_contain_text("niemand")
    assert gespeichert([])


def test_antrag_erst_absenden_wenn_pflichtangaben_da(seite, admin):
    """Fehlen Pflichtangaben, ist der Absende-Knopf sichtbar gesperrt; ein Klick schickt nichts ab,
    sondern markiert die Felder rot und zeigt über dem Knopf, was fehlt (ADR 0024)."""
    from apps.antraege.models import Antrag, AntragEinstellungen

    e = AntragEinstellungen.laden()
    e.aktiv = True
    e.save()
    seite.goto("/antrag/de/")
    knopf = seite.locator(".antrag-absenden")
    expect(knopf).to_have_class(re.compile("knopf-gesperrt"))
    expect(seite.locator(".antrag-noch-offen")).to_contain_text("Pflichtangabe(n) offen")
    knopf.click(force=True)  # „gesperrt“ heißt: Klick erklärt, was fehlt, statt abzuschicken
    kasten = seite.locator("#antrag-pruefung")
    expect(kasten).to_be_visible()
    expect(kasten).to_contain_text("Ihr Antrag wurde noch NICHT abgeschickt!")
    expect(kasten.locator("li", has_text="Vorname")).to_be_visible()
    vorname = seite.locator(".feld", has=seite.locator("#id_vorname"))
    expect(vorname).to_have_class(re.compile("hat-fehler"))
    expect(seite).to_have_url(re.compile("/antrag/de/$"))
    assert not Antrag.objects.exists()
    # Ausfüllen: Markierung verschwindet sofort, am Ende ist der Knopf frei
    seite.fill("#id_vorname", "Erika")
    expect(vorname).not_to_have_class(re.compile("hat-fehler"))
    expect(kasten.locator("li", has_text="Vorname")).to_have_count(0)
    seite.fill("#id_nachname", "Beispiel")
    seite.fill("#id_geburtsdatum", "03.02.1980")
    seite.fill("#id_strasse", "Erfundene Gasse 1")
    seite.fill("#id_plz", "12345")
    seite.fill("#id_ort", "Musterstadt")
    for haken in seite.locator(".antrag-formular .feld-haken input[type=checkbox]").all():
        haken.check()
    art = seite.locator("input[name=art]")
    if art.count():
        art.first.check()
    expect(knopf).not_to_have_class(re.compile("knopf-gesperrt"))
    expect(seite.locator(".antrag-noch-offen")).to_be_hidden()
    knopf.click()
    seite.wait_for_url("**/danke/**")
    assert Antrag.objects.get().vorname == "Erika"


def test_serienbrief_vorlage_live_vorschau(angemeldet, admin):
    """Rechts neben dem Editor erscheint die erste Seite; Briefkopf abwählen lädt sie neu."""
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 1400, "height": 900})
    seite.goto(reverse("serienbriefe:vorlage_neu"))
    bild = seite.locator("img[data-brief-vorschau]")
    expect(bild).to_have_attribute("src", re.compile(r"^blob:"))
    erstes = bild.get_attribute("src")
    seite.get_by_label("Briefkopf").uncheck()
    expect(bild).not_to_have_attribute("src", erstes)
    expect(seite.locator("[data-brief-vorschau-stand]")).to_contain_text("erfundenen Empfänger")
    # schmaler Bildschirm: keine Vorschau
    seite.set_viewport_size({"width": 700, "height": 900})
    expect(seite.locator(".brief-vorschau")).to_be_hidden()


def test_serienbrief_vorlage_grafik_einfuegen(angemeldet, admin, tmp_path):
    """Grafik hochladen, an der Schreibmarke einfügen, Größe ändern, entfernen (ADR 0138)."""
    import io

    from PIL import Image

    from apps.serienbriefe.models import Grafik, Vorlage

    datei = tmp_path / "logo.png"
    puffer = io.BytesIO()
    Image.new("RGB", (300, 100), (232, 113, 10)).save(puffer, "PNG")
    datei.write_bytes(puffer.getvalue())
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 1400, "height": 900})
    seite.goto(reverse("serienbriefe:vorlage_neu"))
    seite.locator("#id_name").fill("Mit Logo")
    seite.get_by_label("Betreff").fill("Hallo")
    editor = seite.locator(".editor", has=seite.locator("#id_text"))
    flaeche = editor.locator(".editor-flaeche")
    flaeche.click()
    seite.keyboard.type("Vorher ")
    editor.locator(".editor-leiste").get_by_role("button", name="Grafik").click()
    dialog = seite.locator("dialog.grafik-dialog")
    expect(dialog.get_by_role("heading", name="Grafik einfügen")).to_be_visible()
    dialog.locator("input[type=file]").set_input_files(str(datei))
    bild = flaeche.locator("img")
    expect(bild).to_have_count(1)
    expect(bild).to_have_attribute("width", "50%")
    expect(dialog).to_be_hidden()
    g = Grafik.objects.get()
    assert flaeche.inner_html().index("Vorher") < flaeche.inner_html().index("<img")
    # Größe ändern über „Grafik ändern“ an der Grafik
    bild.click()
    seite.get_by_role("button", name="Grafik ändern").click()
    expect(dialog.get_by_role("heading", name="Grafik ändern")).to_be_visible()
    dialog.get_by_label("klein").check()
    expect(bild).to_have_attribute("width", "25%")
    dialog.get_by_role("button", name="Schließen").click()
    # noch einmal aus der Liste einfügen und wieder entfernen
    flaeche.click()
    seite.keyboard.press("Control+End")
    editor.locator(".editor-leiste").get_by_role("button", name="Grafik").click()
    dialog.locator(".grafik-wahl").first.click()
    expect(flaeche.locator("img")).to_have_count(2)
    flaeche.locator("img").last.click()
    seite.get_by_role("button", name="Grafik ändern").click()
    dialog.get_by_role("button", name="Grafik entfernen").click()
    expect(flaeche.locator("img")).to_have_count(1)
    seite.get_by_role("button", name="Anlegen").click()
    expect(seite.get_by_text("Vorlage „Mit Logo“ gespeichert.")).to_be_visible()
    text = Vorlage.objects.get(name="Mit Logo").text
    assert f'src="/serienbriefe/grafiken/{g.pk}/"' in text and 'width="25%"' in text


def test_aufnahme_adresse_kopieren(angemeldet, admin):
    """Aufnahme, Schritt „Ausgabestelle“: „Kopieren“ legt die Adresse in die Zwischenablage."""
    from apps.antraege.models import Antrag

    a = Antrag.objects.create(vorname="Erika", nachname="Beispiel", strasse="Weg 1",
                              plz="12345", ort="Musterstadt")  # fmt: skip
    seite = angemeldet(admin)
    seite.context.grant_permissions(["clipboard-read", "clipboard-write"])
    seite.goto(reverse("antraege:aufnahme", args=[a.pk]))
    seite.get_by_role("button", name="Weiter", exact=True).click()  # Kunde suchen: neuer Kunde
    seite.goto(reverse("antraege:aufnahme_schritt", args=[a.pk, "gruppe"]))
    expect(seite.get_by_label("Adresse des Kunden")).to_have_value("Weg 1, Musterstadt")
    seite.get_by_role("button", name="Kopieren").click()
    expect(seite.get_by_role("button", name="✓ Kopiert")).to_be_visible()
    assert seite.evaluate("navigator.clipboard.readText()") == "Weg 1, Musterstadt"


def test_datumsfelder_immer_tt_mm_jjjj(angemeldet, admin):
    """Einfache Kalenderfelder zeigen und nehmen TT.MM.JJJJ – unabhängig von der Sprache des
    Browsers –, an den Server geht weiter JJJJ-MM-TT."""
    seite = angemeldet(admin)
    seite.goto(reverse("statistik:uebersicht") + "?zeitraum=eigen")
    von = seite.get_by_label("von", exact=True)
    expect(von).to_have_attribute("placeholder", "TT.MM.JJJJ")
    expect(von).to_have_value(re.compile(r"^\d{2}\.\d{2}\.\d{4}$"))
    assert seite.locator('input[type="hidden"][name="von"]').count() == 1
    von.fill("1.10.2026")
    with seite.expect_navigation():
        von.press("Tab")  # das Formular schickt sich beim Ändern selbst ab
    assert "von=2026-10-01" in seite.url  # beim Server kommt JJJJ-MM-TT an
    # Falsche Schreibweise wird angemahnt statt still verschluckt
    feld = seite.get_by_label("bis", exact=True)
    feld.fill("10/31/2026")
    assert "TT.MM.JJJJ" in feld.evaluate("f => f.validationMessage")


def test_antrag_ein_status_speichert_sofort(angemeldet, admin):
    """Antragsseite mit Warteliste: nur ein Status; die Auswahl speichert sofort, „Wartezeit“ erst,
    wenn das Datum dazu eingetragen ist."""
    from apps.antraege.models import Antrag
    from apps.core.models import TafelEinstellungen
    from apps.warteliste import ablauf
    from apps.warteliste.models import Wartestand

    t = TafelEinstellungen.laden()
    t.module = ["warteliste"]
    t.save()
    a = Antrag.objects.create(
        vorname="Erika", nachname="Beispiel", geburtsdatum=dt.date(1980, 2, 3)
    )
    Antrag.objects.filter(pk=a.pk).update(eingegangen_am=timezone.now() - dt.timedelta(days=3))
    ablauf.automatik()
    seite = angemeldet(admin)
    seite.goto(reverse("antraege:antrag", args=[a.pk]))
    auswahl = seite.locator("select#status")
    expect(seite.locator(".status.wl-wartend")).to_be_visible()
    with seite.expect_navigation():
        auswahl.select_option("erschienen")
    expect(seite.locator(".status.wl-erschienen")).to_be_visible()
    # „Wartezeit“ wartet auf das Datum
    seite.locator("select#status").select_option("wartezeit")
    datum = seite.locator("#status-wartezeit-bis")
    expect(datum).to_be_visible()
    assert Wartestand.objects.get(antrag=a).status == "erschienen"
    bis = (timezone.localdate() + dt.timedelta(days=30)).strftime("%d.%m.%Y")
    datum.fill(bis)
    with seite.expect_navigation():
        datum.press("Tab")
    expect(seite.locator(".status.wl-wartezeit")).to_contain_text(f"bis {bis}")


def test_eulenpost_fliegt_ein_und_landet(angemeldet, admin):
    """Post der Verwaltung (ADR 0142): Die Eule fliegt bei neuer Post ein und landet in der
    Kopfzeile; wichtige Post öffnet einen Hinweis; neue Post kommt ohne Neuladen an."""
    from apps.kunden import eulenpost
    from apps.kunden.models import PostEmpfang

    mitte = Ausgabestelle.objects.create(name="Mitte")
    admin.gewaehlte_stelle = mitte
    admin.save()
    eulenpost.schreiben([mitte], admin, "Kühlware", "Morgen keine Kühlware.", wichtig=True)
    seite = angemeldet(admin)
    seite.goto(reverse("ausgabe:empfang"))
    expect(seite.locator(".eule-flieger")).to_be_attached()
    expect(seite.locator(".eulen-landeplatz.eule-gelandet")).to_be_visible(timeout=6000)
    dialog = seite.locator("dialog.eulen-dialog")
    expect(dialog).to_be_visible()
    expect(dialog).to_contain_text("Morgen keine Kühlware.")
    dialog.get_by_role("button", name="Später").click()
    expect(dialog).to_have_count(0)
    # beim nächsten Seitenaufruf fliegt sie nicht noch einmal, der Hinweis kommt wieder
    seite.reload()
    expect(seite.locator("dialog.eulen-dialog")).to_be_visible()
    expect(seite.locator(".eule-flieger")).to_have_count(0)
    seite.locator("dialog.eulen-dialog").get_by_role("button", name="✓ Gelesen").click()
    expect(seite.locator(".eulen-landeplatz")).to_have_count(0)
    assert PostEmpfang.objects.get().gelesen_am
    # neue Post kommt ohne Neuladen (Kopfzeile fragt nach; hier sofort ausgelöst)
    eulenpost.schreiben([mitte], admin, "Schlüssel", "Bitte abgeben.")
    kopf = reverse("kunden:post_kopf")
    seite.evaluate(f"htmx.ajax('GET', '{kopf}', {{target: '#eulenpost', swap: 'outerHTML'}})")
    expect(seite.locator(".eulen-landeplatz.eule-gelandet")).to_be_visible(timeout=6000)
    expect(seite.locator(".eulen-zahl")).to_have_text("1")
    # Ton je Gerät abschalten
    seite.locator(".eulen-landeplatz").click()
    knopf = seite.locator("[data-eulenton]")
    expect(knopf).to_contain_text("an")
    knopf.click()
    expect(knopf).to_contain_text("aus")
    assert seite.evaluate("localStorage.getItem('bintafeln-eulenton')") == "aus"


def _tablet(seite, live_server, settings):
    """Kiosk-Tablet einer Ausgabestelle (Druckansicht an), Mailserver und Teilen-Menü nachgebaut:
    ``window.geteilt`` sammelt, was geteilt wurde (Name und Art der Datei)."""
    from apps.core import druckansicht
    from apps.core.models import MailEinstellungen, TafelEinstellungen

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    e = MailEinstellungen.laden()
    e.server, e.absender = "smtp.example.org", "absender@example.org"
    e.save()
    t = TafelEinstellungen.laden()
    t.email = "tafel@example.org"
    t.save()
    seite.context.add_cookies([{"name": druckansicht.COOKIE, "value": "1", "url": live_server.url}])
    seite.context.add_init_script(
        "window.geteilt = []; window.gedruckt = 0; window.print = () => window.gedruckt++;"
        "navigator.canShare = () => true;"
        "navigator.share = (d) => { window.geteilt.push(d.files.map(f => f.name + '|' + f.type));"
        " return Promise.resolve(); };"
    )


def test_pdf_fenster_kassenabschluss_am_tablet(angemeldet, admin, live_server, settings):
    """Kiosk-Tablet bzw. App vom Home-Bildschirm (ADR 0141): Das PDF öffnet nicht in einem neuen
    Fenster, sondern über der Seite; „Drucken“ öffnet das Teilen-Menü mit dem PDF, „Schließen“
    führt zurück, ohne die Seite zu verlassen."""
    seite = angemeldet(admin)
    _tablet(seite, live_server, settings)
    seite.goto(reverse("ausgabe:kasse"))
    vorher = len(seite.context.pages)
    seite.get_by_role("link", name=re.compile("drucken \\(PDF\\)")).click()
    fenster = seite.locator("dialog.pdf-fenster")
    expect(fenster.locator("img.druck-seite").first).to_be_visible()
    assert len(seite.context.pages) == vorher  # kein neues Fenster
    fenster.get_by_role("button", name="🖨 Drucken").click()
    seite.wait_for_function("window.geteilt.length === 1")
    name, art = seite.evaluate("window.geteilt[0][0]").split("|")
    assert name.endswith(".pdf") and art == "application/pdf"
    fenster.locator("summary", has_text="Per E-Mail").click()
    fenster.get_by_role("button", name="Senden").click()
    expect(fenster.get_by_text("Das PDF wurde an tafel@example.org gesendet.")).to_be_visible()
    fenster.get_by_role("button", name="✕ Schließen").click()
    expect(seite.locator("dialog.pdf-fenster")).to_have_count(0)
    assert seite.url.endswith(reverse("ausgabe:kasse"))


def test_druckansicht_als_seite(angemeldet, admin, live_server, settings):
    """Wird ein PDF direkt als Seite geöffnet (ADR 0141): Druckansicht mit Teilen-Menü; gedruckt
    werden nur die Seiten."""
    seite = angemeldet(admin)
    _tablet(seite, live_server, settings)
    seite.goto(reverse("ausgabe:kasse") + "?ansicht=tag&format=pdf")
    expect(seite.locator("img.druck-seite").first).to_be_visible()
    seite.get_by_role("button", name="🖨 Drucken").click()
    seite.wait_for_function("window.geteilt.length === 1")
    seite.emulate_media(media="print")
    expect(seite.locator("header.kopf")).to_be_hidden()
    expect(seite.locator(".druck-leiste")).to_be_hidden()
    expect(seite.locator("img.druck-seite").first).to_be_visible()


def test_uebernahmen_auf_daten_importieren_lesbar(angemeldet, admin):
    """Die Punkte unter „Aus einem anderen Programm übernehmen“ stehen untereinander und sind
    lesbar – als Raster wäre jeder zweite in eine zu schmale Spalte gequetscht."""
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.module = sorted(set(t.module or []) | {"uebernahme"})
    t.save()
    seite = angemeldet(admin)
    seite.set_viewport_size({"width": 1024, "height": 768})
    seite.goto(reverse("datenimport:start"))
    link = seite.get_by_role("link", name="Besuche & Konto nachtragen")
    expect(link).to_be_visible()
    breite = link.evaluate("e => e.closest('li').getBoundingClientRect().width")
    hoehe = link.evaluate("e => e.closest('li').getBoundingClientRect().height")
    assert breite > 300 and hoehe < 150
    link.click()
    assert seite.url.endswith(reverse("uebernahme:besuche_konto"))


def test_fruehere_abgleiche_rechnen_von_selbst_weiter(angemeldet, admin, monkeypatch):
    """„Nachrechnen“ in Portionen: Die Seite ruft sich selbst weiter auf, bis nichts mehr offen
    ist (hier: je Aufruf ein Kunde)."""
    import datetime as dt
    from decimal import Decimal

    from apps.ausgabe import konto
    from apps.core.models import TafelEinstellungen
    from apps.kunden.models import Abholung, Haushalt
    from apps.uebernahme import views

    t = TafelEinstellungen.laden()
    t.module = sorted(set(t.module or []) | {"uebernahme"})
    t.save()
    tag = dt.date(2026, 11, 3)
    for nummer in ("04711", "04712", "04713"):
        h = Haushalt.objects.create(kundennummer=nummer, kontostand=Decimal("0"))
        Abholung.objects.create(haushalt=h, datum=tag, nachgetragen=True)
        grund = f"Abgleich bisheriges Programm (Stand {tag:%d.%m.%Y})"
        konto.korrigieren(h, Decimal("4.50"), grund, "Büro")
    monkeypatch.setattr(views, "NACHRECHNEN_S", 0.000001)
    seite = angemeldet(admin)
    seite.goto(reverse("uebernahme:besuche_konto"))
    expect(seite.locator("#nachrechnen")).to_contain_text("3 Kunden")
    seite.once("dialog", lambda d: d.accept())
    seite.get_by_role("button", name="Nachrechnen", exact=True).click()
    expect(seite.get_by_text("Frühere Abgleiche sind nachgerechnet")).to_be_visible()
    expect(seite.locator("#nachrechnen")).to_have_count(0)
    assert konto.abgleiche_stand()["kunden"] == 0
    assert {h.kontostand for h in Haushalt.objects.all()} == {Decimal("4.50")}


def test_anmerkungen_in_notizen_umwandeln(angemeldet, admin):
    """Anmerkungen-Liste: anhaken, „in Notizen umwandeln“ mit Rückfrage; ohne Haken ein Hinweis."""
    from apps.kunden.models import Bemerkung, Notiz

    h = Haushalt.objects.create(kundennummer="00042")
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster")
    Bemerkung.objects.create(haushalt=h, datum=dt.date(2026, 10, 5), text="Kommt mit Begleitung")
    Bemerkung.objects.create(haushalt=h, datum=dt.date(2026, 9, 1), text="Umzug angekündigt")
    seite = angemeldet(admin)
    seite.goto(reverse("kunden:anmerkungen"))
    knopf = seite.get_by_role("button", name="Angehakte in Notizen umwandeln")
    fragen = []

    def merken(dialog):
        fragen.append(dialog.message)
        dialog.accept()

    seite.once("dialog", merken)
    knopf.click()  # nichts angehakt
    assert "anhaken, die zu Notizen werden sollen" in fragen[-1]
    assert Bemerkung.objects.count() == 2
    zeile = seite.locator("tbody tr", has_text="Kommt mit Begleitung")
    zeile.locator('input[name="id"]').check()
    seite.once("dialog", merken)
    knopf.click()
    expect(seite.get_by_text("1 Anmerkung in Notiz umgewandelt.")).to_be_visible()
    assert fragen[-1].startswith("1 Anmerkung in Notizen umwandeln?")
    assert "Papierkorb" not in fragen[-1]
    assert [b.text for b in Bemerkung.objects.all()] == ["Umzug angekündigt"]
    assert Notiz.objects.get().text == "Kommt mit Begleitung"


def test_aenderungsprotokoll_sucht_beim_tippen(angemeldet, admin):
    """Das Suchfeld im Änderungsprotokoll sucht beim Tippen und bleibt beim Blättern erhalten."""
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    for name in ("Tafel Blaubeerhausen", "Tafel Kirschgarten"):
        t.name = name
        t.save()
    seite = angemeldet(admin)
    seite.goto(reverse("core:protokoll"))
    liste = seite.locator("#protokoll-liste tbody tr")
    vorher = liste.count()
    seite.locator("#q").fill("blaubeer")
    expect(liste).not_to_have_count(vorher)
    expect(seite.locator("#protokoll-liste")).to_contain_text("Blaubeerhausen")
    assert "q=blaubeer" in seite.url
    seite.get_by_role("link", name="Zurücksetzen").click()
    expect(seite.locator("#q")).to_have_value("")
    expect(seite.locator("#protokoll-liste")).to_contain_text("Kirschgarten")  # wieder alles


def test_demo_anmelden_mit_einem_klick(seite, admin, benutzer_mit_rolle, settings):
    """Demo: Die Anmeldeseite nennt Benutzername und Passwort je Zugang; „Anmelden als …“ trägt
    beides ein und meldet an."""
    settings.DEMO, settings.DEMO_PASSWORT = True, "demo-erfunden-1"
    konto = benutzer_mit_rolle("demo-buero", rollen.BUERO)
    konto.set_password(settings.DEMO_PASSWORT)
    konto.save()
    seite.goto(reverse("konten:anmelden"))
    zeile = seite.locator("#demo-zugaenge li", has_text="demo-buero")
    expect(zeile).to_contain_text("demo-erfunden-1")
    zeile.get_by_role("button", name=re.compile("Anmelden als")).click()
    expect(seite.locator("a.angemeldet")).to_be_visible()
    assert "/anmelden" not in seite.url


def test_adresse_mitarbeit_speichert_sofort(angemeldet, admin):
    """Ausgabetage einer Person im Adressbuch anhaken: gespeichert wird sofort am Konto."""
    from apps.adressen.models import Adresse
    from apps.konten import verwaltung

    a = Adresse.objects.create(art="person", vorname="Tilda", nachname="Tagwerk")
    konto = verwaltung.konto_fuer_adresse(admin, a, [rollen.AUSGABE])
    seite = angemeldet(admin)
    seite.goto(reverse("adressen:bearbeiten", args=[a.pk]))
    expect(seite.get_by_label("Benutzername")).to_have_value("tilda.tagwerk")
    seite.get_by_label("Fr", exact=True).check()
    expect(seite.locator(".autosave-ok")).to_be_visible()
    konto.refresh_from_db()
    assert konto.ausgabetage == "Fr"


def test_adresse_stammdaten_speichern_sofort(angemeldet, admin):
    """Stammdaten der Mitarbeit in der Adress-Maske: Notfallkontakt eintragen, sofort gespeichert,
    die Anschrift der Adresse bleibt."""
    from apps.adressen.models import Adresse
    from apps.konten import verwaltung
    from apps.konten.models import Stammdaten

    a = Adresse.objects.create(art="person", vorname="Nora", nachname="Notfall",
                               strasse="Beispielweg 3")  # fmt: skip
    konto = verwaltung.konto_fuer_adresse(admin, a, [rollen.FAHRER])
    seite = angemeldet(admin)
    seite.goto(reverse("adressen:bearbeiten", args=[a.pk]))
    teil = seite.locator("#stammdaten")
    teil.get_by_label("Notfallkontakt: Name").fill("Nils Notfall")
    teil.get_by_label("Notfallkontakt: Telefon").click()
    expect(teil.locator(".autosave-ok")).to_be_visible()
    assert Stammdaten.objects.get(benutzer=konto).notfall_name == "Nils Notfall"
    a.refresh_from_db()
    assert a.strasse == "Beispielweg 3" and a.konto_id == konto.pk


def test_qr_code_zum_stempeln_im_browser_scannen(angemeldet, admin, benutzer_mit_rolle):
    """„Meine Arbeitszeit“ bei „nur am Monitor“: Der Scanner öffnet sich in der Seite, der
    gelesene QR-Code wird im selben Fenster eingelöst, danach erscheint „Kommen“. Die Kamera
    liefert nur ein Testbild, deshalb liest ein Ersatz-Detektor den Code des Monitors."""
    import json

    from apps.aushang import stempeln
    from apps.aushang.models import Aushang, AushangSeite
    from apps.core.models import TafelEinstellungen
    from apps.personal.models import ArbeitszeitEinstellungen

    t = TafelEinstellungen.laden()
    t.module = ["aushang", "dienstplan"]
    t.save()
    e = ArbeitszeitEinstellungen.laden()
    e.aktiv = e.nur_am_monitor = True
    e.save()
    monitor = Aushang.objects.create(name="Monitor Ausgabe")
    AushangSeite.objects.create(aushang=monitor, art="dienstplan", wert="1")
    kim = benutzer_mit_rolle("kim", rollen.AUSGABE)
    kim.beschaeftigung = "fest"
    kim.save()
    seite = angemeldet(kim)
    adresse = reverse("aushang:stempeln_handy", args=[stempeln.marke(monitor)])
    seite.add_init_script(
        "window.BarcodeDetector = class { static async getSupportedFormats() {"
        " return ['code_128', 'qr_code']; }"
        f" async detect() {{ return [{{rawValue: location.origin + {json.dumps(adresse)}}}]; }} }};"
    )
    seite.goto(reverse("personal:meine_arbeitszeit"))
    expect(seite.get_by_role("button", name="Kommen")).to_have_count(0)
    seiten_vorher = len(seite.context.pages)
    seite.get_by_role("button", name=re.compile("QR-Code scannen")).click()
    expect(seite.get_by_text("Vor Ort bestätigt")).to_be_visible()
    expect(seite.get_by_role("button", name="Kommen")).to_be_visible()
    assert len(seite.context.pages) == seiten_vorher  # kein neues Fenster


def test_fahrt_beginnen_und_beenden_am_handy(seite, angemeldet, admin):
    """Unterwegs: Fahrzeug wählen, der letzte Kilometerstand wird vorgeschlagen
    (static/js/fahrt_km.js), Fahrt beginnen und die Tour mit dem Stand bei Ankunft beenden
    (ADR 0151)."""
    from apps.core.models import TafelEinstellungen
    from apps.touren import ablauf
    from apps.touren.models import Fahrt, Fahrzeug, Station, Tour

    t = TafelEinstellungen.laden()
    t.module = ["touren"]
    t.save()
    station = Station.objects.create(kennung="M-1", name="Beispielmarkt", strasse="Musterweg",
                                     hausnummer="1", plz="12345", ort="Musterstadt")  # fmt: skip
    tour = Tour.objects.create(name="Tour 1")
    ablauf.halt_anhaengen(tour, station)
    wagen = Fahrzeug.objects.create(name="Kühlwagen", kennzeichen="MU-ST 1", kilometerstand=1000)
    Fahrzeug.objects.create(name="Transporter", reihenfolge=2)
    angemeldet(admin)
    seite.set_viewport_size({"width": 390, "height": 800})
    seite.goto(reverse("touren:fahren", args=[tour.pk]))
    stand = seite.get_by_label("Kilometerstand bei Abfahrt")
    expect(stand).to_have_value("")
    seite.get_by_label("Fahrzeug").select_option(label="Kühlwagen (MU-ST 1)")
    expect(stand).to_have_value("1000")  # Vorschlag: der Stand dieses Fahrzeugs
    expect(seite.locator("#km-letzter")).to_contain_text("1000 km")
    seite.get_by_label("Fahrzeug").select_option(label="Transporter")
    expect(stand).to_have_value("")  # kein Stand bekannt, Vorschlag wieder weg
    seite.get_by_label("Fahrzeug").select_option(label="Kühlwagen (MU-ST 1)")
    stand.fill("1004")
    # vor dem Beginn noch etwas anderes ansehen: Fahrzeug und Stand bleiben eingetragen
    seite.goto(reverse("touren:heute"))
    seite.goto(reverse("touren:fahren", args=[tour.pk]))
    expect(seite.get_by_label("Fahrzeug")).to_have_value(str(wagen.pk))
    stand = seite.get_by_label("Kilometerstand bei Abfahrt")
    expect(stand).to_have_value("1004")
    seite.get_by_role("button", name="Fahrt beginnen").click()
    expect(seite.locator("section.karte").first).to_contain_text("Unterwegs")
    seite.get_by_label("Kilometerstand bei Ankunft").fill("1050")
    seite.get_by_role("button", name="Tour beenden").click()
    expect(seite.locator(".meldung").first).to_contain_text("46 km gefahren")
    fahrt = Fahrt.objects.get(tour=tour)
    assert (fahrt.km_start, fahrt.km_ende, fahrt.fahrzeug) == (1004, 1050, wagen)
    wagen.refresh_from_db()
    assert wagen.kilometerstand == 1050  # fortgeschrieben
    # 1000 war bekannt, 1004 eingetragen: 4 km stehen als „unbekannt“ im Fahrtenbuch
    seite.goto(reverse("touren:fahrten"))
    luecke = seite.locator("tr.fahrt-unbekannt")
    expect(luecke).to_contain_text("unbekannt")
    expect(luecke).to_contain_text("4 km")


def test_tour_springt_zur_aktuellen_station(seite, angemeldet, admin):
    """„Hier waren wir“ kennzeichnet eine Station; die Tour springt beim Öffnen zur nächsten
    offenen (static/js/tour_aktuell.js, ADR 0152)."""
    from apps.core.models import TafelEinstellungen
    from apps.touren import ablauf
    from apps.touren.models import Anfahrt, Station, Tour

    t = TafelEinstellungen.laden()
    t.module = ["touren"]
    t.save()
    tour = Tour.objects.create(name="Tour 1", datum=timezone.localdate())
    for nr in range(1, 7):
        ablauf.halt_anhaengen(tour, Station.objects.create(
            kennung=f"M-{nr}", name=f"Markt {nr}", strasse="Musterweg", hausnummer=str(nr),
            plz="12345", ort="Musterstadt", anfahrt="Hintereingang, bitte klingeln."))  # fmt: skip
    angemeldet(admin)
    seite.set_viewport_size({"width": 390, "height": 700})
    seite.goto(reverse("touren:fahren", args=[tour.pk]))
    assert seite.evaluate("window.scrollY") == 0  # noch nichts angefahren: oben bleiben
    for nr in (1, 2, 3):
        seite.locator(f"#halt-{nr}").get_by_role("button", name="✓ Hier waren wir").click()
        expect(seite.locator(f"#halt-{nr}")).to_contain_text("zurücknehmen")
    assert Anfahrt.objects.count() == 3
    seite.goto(reverse("touren:fahren", args=[tour.pk]))
    aktuell = seite.locator("#halt-4")
    expect(aktuell).to_have_attribute("data-tour-aktuell", "")
    expect(aktuell).to_be_in_viewport()
    assert seite.evaluate("window.scrollY") > 300
    erste = seite.locator("#halt-1")
    expect(erste).to_have_class(re.compile("tour-erledigt"))  # bleibt stehen
    # Erledigtes ist deutlich gekennzeichnet und eingeklappt, aber wieder aufklappbar
    expect(erste.locator(".tour-erledigt-zeile")).to_contain_text("Erledigt")
    expect(erste.get_by_role("link", name="🧭 Navigation starten")).to_be_hidden()
    erste.locator("summary").click()
    expect(erste.get_by_role("link", name="🧭 Navigation starten")).to_be_visible()
    erste.get_by_role("button", name="zurücknehmen").click()
    expect(seite.locator("#halt-1")).not_to_have_class(re.compile("tour-erledigt"))


def test_kurzfristige_tour_in_einer_maske(seite, angemeldet, admin):
    """Kurzfristige Tour: Stationen beim Tippen suchen, hinzufügen, umsortieren und alles in
    einer Maske anlegen (static/js/stationswahl.js); danach die Suche beim Anhängen."""
    from apps.core.models import TafelEinstellungen
    from apps.touren.models import Station, Tour

    t = TafelEinstellungen.laden()
    t.module = ["touren"]
    t.save()
    for nr, name in enumerate(["Supermarkt Nord", "Bäckerei Probe", "Hofladen Beispiel"], 1):
        Station.objects.create(kennung=f"M-{nr}", name=name, strasse="Musterweg",
                               hausnummer=str(nr), plz="12345", ort="Musterstadt",
                               telefon=f"01234 5550{nr}")  # fmt: skip
    angemeldet(admin)
    seite.goto(reverse("touren:tour_neu") + "?kurz")
    seite.get_by_label("Name").first.fill("Sonderabholung")
    suche = seite.get_by_label("Laden oder Lieferadresse suchen")
    suche.fill("su")
    expect(seite.locator("#station-treffer li")).to_have_count(0)  # erst ab drei Zeichen
    suche.fill("sup")
    seite.get_by_role("button", name="Supermarkt Nord hinzufügen").click()
    suche.fill("55502")  # Telefonnummer
    seite.get_by_role("button", name="Bäckerei Probe hinzufügen").click()
    liste = seite.locator("[data-stationswahl-liste] li")
    expect(liste).to_have_count(2)
    expect(seite.locator("[data-stationswahl-leer]")).to_be_hidden()
    seite.get_by_role("button", name="Bäckerei Probe früher").click()
    expect(liste.first).to_contain_text("Bäckerei Probe")
    suche.fill("hofladen")
    seite.get_by_role("button", name="Hofladen Beispiel hinzufügen").click()
    seite.get_by_role("button", name="Hofladen Beispiel entfernen").click()
    expect(liste).to_have_count(2)
    seite.get_by_role("button", name="Tour anlegen").click()
    expect(seite.locator(".meldung").first).to_contain_text("mit 2 Stationen angelegt")
    tour = Tour.objects.get(name="Sonderabholung")
    assert [h.station.name for h in tour.halte.all()] == ["Bäckerei Probe", "Supermarkt Nord"]
    # auf der Seite der Tour: suchen und anhängen
    seite.get_by_label("Station suchen und anhängen").fill("hofl")
    seite.get_by_role("button", name="Hofladen Beispiel anhängen").click()
    expect(seite.locator("#tour-halte tbody tr")).to_have_count(3)


def test_routenvorschau_in_der_planung(seite, angemeldet, admin):
    """Tourenplanung: Die Google-Karte lädt erst nach „Karte zeigen“, die Wahl bleibt gemerkt
    (static/js/tour_karte.js); in der Maske der kurzfristigen Tour folgt die Vorschau der
    Auswahl (ADR 0154). Google selbst wird im Test nicht aufgerufen."""
    from apps.core import geheimnis
    from apps.core.models import TafelEinstellungen
    from apps.touren import ablauf
    from apps.touren.models import Station, Tour, TourenEinstellungen

    t = TafelEinstellungen.laden()
    t.module = ["touren"]
    t.save()
    e = TourenEinstellungen.laden()
    e.zentrale = "Zentralweg 1, 12345 Musterstadt"
    e.karten_schluessel_verschluesselt = geheimnis.verschluesseln("test-schluessel")
    e.save()
    tour = Tour.objects.create(name="Nordtour")
    for nr, name in enumerate(["Supermarkt Nord", "Bäckerei Probe"], 1):
        ablauf.halt_anhaengen(tour, Station.objects.create(
            kennung=f"M-{nr}", name=name, strasse="Musterweg", hausnummer=str(nr), plz="12345",
            ort="Musterstadt"))  # fmt: skip
    aufrufe = []

    def google(route):
        aufrufe.append(route.request.url)
        route.fulfill(status=200, content_type="text/html", body="<p>Karte</p>")

    seite.route("https://www.google.com/**", google)
    angemeldet(admin)
    seite.goto(reverse("touren:tour", args=[tour.pk]))
    expect(seite.get_by_text("Start und Ziel: Zentralweg 1")).to_be_visible()
    assert not aufrufe and seite.locator(".tour-karte iframe").count() == 0  # erst nach Klick
    seite.get_by_role("button", name="🗺 Karte zeigen").click()
    bild = seite.locator(".tour-karte iframe")
    expect(bild).to_have_count(1)
    expect(bild).to_have_attribute("src", re.compile(r"embed/v1/directions\?key=test-schluessel"))
    expect(bild).to_have_attribute("src", re.compile(r"origin=Zentralweg"))
    seite.reload()  # gemerkt: die Karte kommt von selbst
    expect(seite.locator(".tour-karte iframe")).to_have_count(1)
    seite.get_by_role("button", name="Karte nicht mehr automatisch zeigen").click()
    expect(seite.locator(".tour-karte iframe")).to_have_count(0)
    seite.reload()
    expect(seite.get_by_role("button", name="🗺 Karte zeigen")).to_be_visible()
    # Maske der kurzfristigen Tour: die Vorschau folgt der Auswahl
    seite.goto(reverse("touren:tour_neu") + "?kurz")
    expect(seite.get_by_text("Sobald Stationen gewählt sind")).to_be_visible()
    seite.get_by_label("Laden oder Lieferadresse suchen").fill("super")
    seite.get_by_role("button", name="Supermarkt Nord hinzufügen").click()
    expect(seite.get_by_role("link", name="Route in Google Maps öffnen ↗")).to_be_visible()
    seite.get_by_role("button", name="🗺 Karte zeigen").click()
    expect(seite.locator(".tour-karte iframe")).to_have_attribute(
        "src", re.compile(r"waypoints=Musterweg\+1"))  # fmt: skip
    seite.get_by_role("button", name="Supermarkt Nord entfernen").click()
    expect(seite.get_by_text("Sobald Stationen gewählt sind")).to_be_visible()


def test_lieferschein_am_handy_unterschreiben(seite, angemeldet, admin):
    """Unterwegs: Lieferschein ausfüllen, mit dem Finger unterschreiben, abschicken
    (static/js/unterschrift_feld.js, ADR 0149)."""
    from apps.core.models import TafelEinstellungen
    from apps.touren import ablauf
    from apps.touren.models import Lieferschein, Station, Tour

    t = TafelEinstellungen.laden()
    t.module = ["touren"]
    t.save()
    station = Station.objects.create(kennung="M-1", name="Beispielmarkt", strasse="Musterweg",
                                     hausnummer="1", plz="12345", ort="Musterstadt")  # fmt: skip
    tour = Tour.objects.create(name="Tour 1")
    ablauf.halt_anhaengen(tour, station)
    angemeldet(admin)
    seite.set_viewport_size({"width": 390, "height": 800})
    seite.goto(reverse("touren:fahren", args=[tour.pk]))
    seite.get_by_role("link", name="📝 Lieferschein ausfüllen").click()
    seite.get_by_label("Obst/Gemüse: Menge").fill("4")
    seite.get_by_label("Backwaren: Menge").fill("2,5")
    seite.get_by_label("Backwaren: Einheit").select_option("kg")
    # ohne Unterschrift: Fehler, die Mengen bleiben stehen
    seite.get_by_role("button", name="Unterschreiben und abschicken").click()
    expect(seite.get_by_role("alert")).to_contain_text("Bitte im Feld unterschreiben")
    expect(seite.get_by_label("Obst/Gemüse: Menge")).to_have_value("4")
    flaeche = seite.locator("#unterschrift-flaeche")
    flaeche.scroll_into_view_if_needed()
    kasten = flaeche.bounding_box()
    seite.mouse.move(kasten["x"] + 30, kasten["y"] + 100)
    seite.mouse.down()
    seite.mouse.move(kasten["x"] + 120, kasten["y"] + 40, steps=5)
    seite.mouse.move(kasten["x"] + 250, kasten["y"] + 110, steps=5)
    seite.mouse.up()
    expect(seite.locator("#unterschrift")).to_have_value(re.compile("^data:image/png;base64,"))
    # löschen leert das Feld, danach neu unterschreiben
    seite.get_by_role("button", name="Unterschrift löschen").click()
    expect(seite.locator("#unterschrift")).to_have_value("")
    # auf einem sehr breiten Bildschirm wird das Bild nicht breiter als nötig
    alt = seite.viewport_size
    seite.set_viewport_size({"width": 2600, "height": alt["height"]})
    expect(flaeche).to_have_js_property("width", 1600)
    seite.set_viewport_size(alt)
    flaeche.scroll_into_view_if_needed()
    kasten = flaeche.bounding_box()
    seite.mouse.move(kasten["x"] + 30, kasten["y"] + 60)
    seite.mouse.down()
    seite.mouse.move(kasten["x"] + 200, kasten["y"] + 90, steps=8)
    seite.mouse.up()
    seite.get_by_role("button", name="Unterschreiben und abschicken").click()
    expect(seite).to_have_url(re.compile(rf"/touren/tour/{tour.pk}/"))
    expect(seite.locator(".tour-schein")).to_contain_text("Lieferschein Nr. 1")
    ls = Lieferschein.objects.get()
    assert [p.menge_text for p in ls.positionen.all()] == ["4 Kisten", "2,5 kg"]
    assert not ls.gesendet_am and "ausgeschaltet" in ls.mail_fehler  # Vorgabe: nur speichern


def test_pdf_fenster_am_handy_im_hochformat(angemeldet, admin, live_server):
    """Im Hochformat stand der Dateiname Buchstabe für Buchstabe untereinander, der Knopf
    „Schließen“ ragte aus dem Fenster, und vom PDF war nichts zu sehen."""
    from apps.core import druckansicht

    seite = angemeldet(admin)
    seite.context.add_cookies([{"name": druckansicht.COOKIE, "value": "1", "url": live_server.url}])
    seite.set_viewport_size({"width": 390, "height": 800})
    seite.goto(reverse("ausgabe:kasse"))
    seite.get_by_role("link", name=re.compile("drucken \\(PDF\\)")).click()
    fenster = seite.locator("dialog.pdf-fenster")
    bild = fenster.locator("img.druck-seite").first
    expect(bild).to_be_visible()
    rahmen = fenster.bounding_box()
    kopf = fenster.locator(".pdf-fenster-kopf").bounding_box()
    titel = fenster.locator(".pdf-fenster-kopf strong").bounding_box()
    knopf = fenster.get_by_role("button", name="✕ Schließen").bounding_box()
    # Der Knopf liegt ganz im Fenster, der Name hat Platz neben ihm
    assert knopf["x"] + knopf["width"] <= rahmen["x"] + rahmen["width"]
    assert titel["width"] > 150
    # Der Kopf bleibt eine schmale Leiste; darunter ist das PDF zu sehen
    assert kopf["height"] < 120
    assert bild.bounding_box()["y"] < rahmen["y"] + rahmen["height"]
