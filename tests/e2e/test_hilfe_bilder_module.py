"""Bilder für das Handbuch der zuschaltbaren Module: Dienstplan, Fahrdienst, Aufruf, Aushang,
Warteliste, Wochenübersicht, Links, Abrechnung, Listen (Werkzeug und Anleitung in
``hilfe_bilder.py``)."""

import datetime as dt

from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect

from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle
from tests.e2e.hilfe_bilder import Marke, aufnehmen, oeffnen


def _module(*namen):
    t = TafelEinstellungen.laden()
    t.module = list(namen)
    t.bundesland = "NW"
    t.save()


NACHNAMEN = [
    "Beispiel",
    "Probe",
    "Sommer",
    "Winter",
    "Feld",
    "Berg",
    "Ufer",
    "Stein",
    "Linde",
    "Wald",
    "Brook",
    "Kurz",
    "Lang",
    "Nord",
    "Busch",
    "Heide",
]
VORNAMEN = ["Kim", "Alex", "Sam", "Robin", "Jule", "Toni", "Mika", "Luca"]


def _haushalte(gruppe, anzahl, start=101):
    """Erfundene Haushalte mit Hauptperson, jeder zweite mit einem Kind."""
    from apps.kunden.models import Haushalt, Person

    heute = timezone.localdate()
    for n in range(anzahl):
        h = Haushalt.objects.create(
            kundennummer=f"{start + n:05d}",
            kundengruppe=gruppe,
            ausweis_gueltig_bis=heute + dt.timedelta(days=40 + 9 * n),
        )
        nachname = NACHNAMEN[n % len(NACHNAMEN)]
        Person.objects.create(
            haushalt=h,
            ist_hauptperson=True,
            vorname=VORNAMEN[n % 8],
            nachname=nachname,
            geburtsdatum=dt.date(1950 + 3 * n, 1 + n % 12, 5),
        )
        if n % 2:
            Person.objects.create(
                haushalt=h,
                vorname="Ben",
                nachname=nachname,
                geburtsdatum=dt.date(2012 + n % 12, 3, 9),
            )


def _dienstplan():
    """Beispiel-Dienstplan an der Ausgabestelle Mitte; am nächsten Freitag fällt eine Helferin
    beim Obst aus (noch offen), beim Gemüse springt jemand ein."""
    from apps.dienstplan import beispiel, plan
    from apps.dienstplan.models import Ausfall, DienstStelle, Ersatz

    beispiel.anlegen(seed=3)
    mitte = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    DienstStelle.objects.filter(ausgabestelle__name=beispiel.STELLE).update(ausgabestelle=mitte)
    Ausgabestelle.objects.filter(name=beispiel.STELLE).delete()
    stelle = DienstStelle.objects.get(ausgabestelle=mitte)
    heute = timezone.localdate()
    freitag = plan.ausgabetage(stelle, heute, heute + dt.timedelta(days=14), "Fr")[0]
    aufgaben = stelle.aufgaben.filter(wochentag="Fr")
    obst = aufgaben.filter(name="Obst").first()
    gemuese = aufgaben.filter(name="Gemüse").first()
    for a in (obst, gemuese):
        Ausfall.objects.create(
            helfer=a.besetzung.helfer,
            von=freitag,
            bis=freitag,
            grund="krank",
            eingetragen_von="Clara Beispiel",
        )
    ersatz = plan.verfuegbar(freitag)[0]
    Ersatz.objects.create(
        datum=freitag, aufgabe=gemuese, helfer=ersatz, eingetragen_von="Clara Beispiel"
    )
    return stelle, freitag, obst


def test_hilfe_bild_dienstplan(angemeldet, admin, muster, benutzer_mit_rolle, recht_geben):
    from apps.dienstplan.models import Besetzung, Helfer

    _module("dienstplan")
    stelle, freitag, obst = _dienstplan()
    seite = oeffnen(angemeldet, admin, reverse("dienstplan:plan"), breite=1400)
    karte = seite.locator("section.karte")
    tabelle = seite.locator("table.dp-plan")
    zeilen = tabelle.locator("tbody tr")
    offen = tabelle.locator(".fd-offen").first
    ersetzt = tabelle.locator(".fd-ersetzt").first
    aufnehmen(
        seite,
        "dienstplan-plan",
        [karte.locator("h1"), zeilen.nth(13)],
        Marke(seite.locator("form.fd-monat"), "rahmen", 1),
        Marke(offen, "rahmen", 2),
        Marke(ersetzt, "rahmen", 3),
        Marke(seite.get_by_role("link", name="Ich kann nicht – Ausfall melden"), "rahmen", 4),
    )

    # Als Planerin auf einen Namen tippen: Ausfall ohne Ersatz oder gleich den Ersatz eintragen
    kasse = stelle.aufgaben.get(wochentag="Fr", name="Kasse")
    seite.goto(reverse("dienstplan:platz", args=[f"{freitag:%Y-%m-%d}", kasse.pk]))
    seite.select_option("#dp-grund", "krank")
    aufnehmen(
        seite,
        "dienstplan-platz",
        seite.locator("section.karte"),
        Marke(seite.locator("#dp-dauer"), nummer=1, von="rechts"),
        Marke(
            seite.get_by_role("button", name="Ausfall melden (ohne Ersatz)"), nummer=2, von="rechts"
        ),
        Marke(seite.locator("#helfer"), nummer=3, von="rechts"),
        Marke(seite.get_by_role("button", name="Ersatz eintragen"), nummer=4, von="rechts"),
    )

    # Helferin mit Konto: Meine Dienste mit „kann nicht“
    recht_geben(rollen.AUSGABE, "dienstplan.sehen")
    ines = benutzer_mit_rolle("ines", rollen.AUSGABE)
    ines.first_name, ines.last_name = "Ines", "Probe"
    ines.save()
    helferin = Helfer.objects.create(benutzer=ines)
    b = Besetzung.objects.filter(aufgabe__stelle=stelle, aufgabe__name="Brot")
    b.update(helfer=helferin)
    seite.context.clear_cookies()
    seite = oeffnen(angemeldet, ines, reverse("dienstplan:meine"))
    karte = seite.locator("section.karte")
    aufnehmen(
        seite,
        "dienstplan-meine",
        karte,
        Marke(
            karte.get_by_role("link", name="kann nicht", exact=True).first, nummer=1, von="rechts"
        ),
        Marke(karte.get_by_role("link", name="Ich kann nicht – Ausfall melden"), "rahmen", 2),
    )
    expect(karte).to_contain_text("Brot")


def _fahrdienst():
    """Beispiel-Fahrerplan; am dritten Fahrtag des Monats fällt ein Fahrer aus (offen), am
    vierten springt ein Springer ein."""
    from apps.fahrdienst import beispiel, plan
    from apps.fahrdienst.models import Ausfall, Ersatz

    beispiel.anlegen(seed=3)
    erster = timezone.localdate().replace(day=1)
    tage = plan.fahrtage(erster, erster + dt.timedelta(days=27))
    eintraege = []
    for datum in tage[2:4]:
        p = next(p for _, plaetze in plan.tage([datum])[0][1] for p in plaetze if p.wer)
        Ausfall.objects.create(
            benutzer=p.wer, von=datum, bis=datum, grund="krank", eingetragen_von="Clara Beispiel"
        )
        eintraege.append((datum, p))
    datum, p = eintraege[1]
    springer = plan.verfuegbar(datum)[0][0]
    Ersatz.objects.create(
        datum=datum, tour=p.tour, platz=p.platz, benutzer=springer, eingetragen_von="Clara Beispiel"
    )


def test_hilfe_bild_fahrdienst(angemeldet, admin, muster):
    from django.contrib.auth import get_user_model

    from apps.fahrdienst import plan
    from apps.fahrdienst.models import Tour

    _module("fahrdienst")
    _fahrdienst()
    seite = oeffnen(angemeldet, admin, reverse("fahrdienst:plan"), breite=1400)
    karte = seite.locator("section.karte")
    tabelle = seite.locator("table.fd-plan")
    aufnehmen(
        seite,
        "fahrdienst-plan",
        [karte.locator("h1"), tabelle.locator("tbody tr").nth(4)],
        Marke(seite.locator("form.fd-monat"), "rahmen", 1),
        Marke(tabelle.locator(".fd-offen").first, "rahmen", 2),
        Marke(tabelle.locator(".fd-ersetzt").first, "rahmen", 3),
        Marke(tabelle.locator("thead a").first, "rahmen", 4),
        Marke(seite.get_by_role("link", name="Ich kann nicht – Ausfall melden"), "rahmen", 5),
    )

    # Als Fahrdienstleitung auf einen Namen tippen
    heute = timezone.localdate()
    datum = plan.fahrtage(heute, heute + dt.timedelta(days=14))[0]
    tour = Tour.objects.order_by("reihenfolge").first()
    seite.goto(reverse("fahrdienst:platz", args=[f"{datum:%Y-%m-%d}", tour.pk, 1]))
    aufnehmen(
        seite,
        "fahrdienst-platz",
        seite.locator("section.karte"),
        Marke(seite.locator("#ausfall-dauer"), nummer=1, von="rechts"),
        Marke(
            seite.get_by_role("button", name="Ausfall melden (ohne Ersatz)"), nummer=2, von="rechts"
        ),
        Marke(seite.locator("#benutzer"), nummer=3, von="rechts"),
        Marke(seite.get_by_role("button", name="Ersatz eintragen"), nummer=4, von="rechts"),
    )

    # Ein Fahrer trägt sich selbst aus: „Meine Einsätze“ → „kann nicht“
    kai = get_user_model().objects.get(username="beispiel-fd-kai-nordmann")
    assert plan.einsaetze(kai, heute, heute + dt.timedelta(days=27))
    seite.context.clear_cookies()
    seite = oeffnen(angemeldet, kai, reverse("fahrdienst:meine"))
    seite.get_by_role("link", name="kann nicht", exact=True).first.click()
    karte = seite.locator("section.karte")
    seite.select_option("#id_dauer", "14")
    seite.select_option("#id_grund", "urlaub")
    aufnehmen(
        seite,
        "fahrdienst-ausfall",
        karte,
        Marke(seite.locator("#id_von"), nummer=1, laenge=50),
        Marke(seite.locator("#id_dauer"), nummer=2, von="rechts"),
        Marke(seite.locator("#id_grund"), nummer=3, von="rechts"),
        Marke(
            karte.get_by_role("button", name="Ausfall melden"), nummer=4, von="rechts", laenge=50
        ),
    )


def _aufruf(muster):
    """Zwölf weitere erfundene Haushalte in der Gruppe A; der Aufruf läuft seit gut einer halben
    Stunde, einige haben sich am Kiosk gemeldet."""
    from apps.aufruf import ablauf
    from apps.aufruf.models import AufrufEinstellungen

    heute = timezone.localdate()
    _haushalte(muster.kundengruppe, 12)
    stelle = muster.kundengruppe.ausgabestelle
    e = AufrufEinstellungen.laden(stelle)
    e.anzahl = 3
    e.spaetzuender_versatz = 15
    e.save()
    ablauf.starten(stelle, heute)
    ablauf.weiter(stelle, heute)
    tag = ablauf.weiter(stelle, heute)
    jetzt = timezone.now()
    for schritt, minuten in zip(tag.stand["rueckgaengig"], (35, 8), strict=True):
        schritt["zeitpunkt"] = (jetzt - dt.timedelta(minutes=minuten)).isoformat()
        schritt["zeit"] = timezone.localtime(jetzt - dt.timedelta(minutes=minuten)).strftime(
            "%H:%M"
        )
    tag.save()
    d = ablauf.stand_fuer_anzeige(tag, e, heute)
    ablauf.kiosk_melden(stelle, heute, d["current_numbers"][0])
    ablauf.kiosk_melden(stelle, heute, d["current_numbers"][2])
    return stelle, tag.stand["rueckgaengig"][0]["nummern"][0]


def test_hilfe_bild_aufruf(angemeldet, admin, muster):
    _module("aufruf")
    stelle, zu_spaet = _aufruf(muster)
    seite = oeffnen(angemeldet, admin, reverse("ausgabe:empfang"))
    leiste = seite.locator(".aufruf-leiste")
    expect(leiste).to_contain_text("Bitte eintreten")
    aufnehmen(
        seite,
        "aufruf-leiste",
        leiste,
        Marke(leiste.locator("h2 a"), nummer=1, von="rechts"),
        Marke(leiste.locator(".aufruf-leiste-nummern span").last, nummer=2, von="rechts"),
        Marke(leiste.get_by_role("button", name="Nächste 3 hereinrufen"), nummer=3, von="rechts"),
        Marke(leiste.locator(".aufruf-leiste-danach"), nummer=4, von="rechts", laenge=50),
    )

    # Am Einlass: Der Kunde war vor 35 Minuten dran
    seite.get_by_label("Kundennummer scannen oder eingeben").fill(zu_spaet)
    seite.get_by_role("button", name="Prüfen").click()
    hinweis = seite.locator(".modul-hinweis").first
    expect(hinweis).to_contain_text("Zu spät")
    knopf = seite.get_by_role("button", name="15 Nummern verschieben")
    ampel = seite.locator("aside.ampel-grafik")
    aufnehmen(
        seite,
        "aufruf-einlass",
        [seite.locator(".einlass-leiste"), ampel, knopf],
        Marke(ampel, "rahmen", 1),
        Marke(hinweis.locator(".."), "rahmen", 2),
        Marke(knopf, nummer=3, von="rechts"),
    )

    # Handy-Steuerung
    seite.set_viewport_size({"width": 400, "height": 860})
    seite.goto(reverse("aufruf:mobil", args=[stelle.pk]))
    knopf = seite.locator("#nextBtn")
    expect(knopf.locator(".nr-da").first).to_be_visible()
    titel = seite.locator(".card-title")
    aufnehmen(
        seite,
        "aufruf-handy",
        [seite.locator("#undoBtn"), seite.locator(".abfrage-row")],
        Marke(knopf, "rahmen", 1),
        Marke(titel.filter(has_text="Nächste Kunden"), nummer=2, von="rechts", laenge=50),
        Marke(titel.filter(has_text="Kundennummer-Abfrage"), nummer=3, von="rechts", laenge=40),
    )


def test_hilfe_bild_aushang(angemeldet, admin, muster, benutzer_mit_rolle, recht_geben):
    from apps.aushang import pin
    from apps.aushang.models import Aushang, AushangSeite
    from apps.dienstplan.models import Besetzung, Helfer

    _module("aushang", "dienstplan")
    stelle, freitag, _ = _dienstplan()
    recht_geben(rollen.AUSGABE, "dienstplan.sehen")
    ines = benutzer_mit_rolle("ines", rollen.AUSGABE)
    ines.first_name, ines.last_name = "Ines", "Probe"
    ines.save()
    helferin = Helfer.objects.create(benutzer=ines)
    brot = stelle.aufgaben.get(wochentag="Fr", name="Brot")
    Besetzung.objects.filter(aufgabe=brot).update(helfer=helferin)
    pin.setzen(ines, "482915")
    aushang = Aushang.objects.create(name="Monitor Ausgaberaum", sekunden=20)
    AushangSeite.objects.create(
        aushang=aushang, art="dienstplan", wert=str(stelle.ausgabestelle_id), wochen=5
    )

    # Einrichten: Seiten und Link
    seite = oeffnen(angemeldet, admin, reverse("aushang:bearbeiten", args=[aushang.pk]))
    seiten = seite.locator("section.karte", has=seite.get_by_role("heading", name="Seiten"))
    link = seite.locator(
        "section.karte", has=seite.get_by_role("heading", name="Link für den Monitor")
    )
    # Im Bild eine neutrale Adresse statt des Testservers
    seite.evaluate("""() => { const f = document.getElementById('aushang-link');
        f.value = f.value.replace(/^https?:\\/\\/[^/]+/, 'https://tafel.example'); }""")
    aufnehmen(
        seite,
        "aushang-einrichten",
        [seiten, link],
        Marke(seiten.locator("ol.aushang-seiten"), "rahmen", 1),
        Marke(seiten.get_by_role("button", name="Seite hinzufügen"), nummer=2, von="rechts"),
        Marke(seite.locator("#aushang-link"), "rahmen", 3),
    )

    # Am Monitor: Freitag groß, dann auf den eigenen Namen tippen
    seite.context.clear_cookies()
    seite.set_viewport_size({"width": 1280, "height": 760})
    seite.goto(reverse("aushang:anzeige", args=[aushang.schluessel]))
    folie = seite.locator(".aushang-folie", has_text="Freitag").first
    nr = folie.get_attribute("data-nr")
    seite.evaluate(f"() => document.querySelector('.aushang-folie[data-nr=\"{nr}\"]').click()")
    expect(seite.locator("body.aushang-gross")).to_have_count(1)
    platz = seite.locator(
        f'.aushang-folie.sichtbar [data-platz="dienstplan|{freitag:%Y-%m-%d}|{brot.pk}"]'
    )
    # Platz über dem Monitor für die Nummern der Marken (der Monitor füllt sonst den Bildschirm)
    seite.evaluate("""() => { document.body.style.boxSizing = 'border-box';
        document.body.style.padding = '40px 0 0 16px'; }""")
    aufnehmen(
        seite,
        "aushang-monitor",
        seite.locator("body"),
        Marke(seite.locator("#aushang-reiter"), "rahmen", 1),
        Marke(platz, nummer=2, von="rechts", laenge=60),
        Marke(seite.locator(".aushang-folie.sichtbar .aushang-qr"), "rahmen", 3),
        Marke(seite.get_by_role("button", name="Übersicht"), "rahmen", 4),
        rand=0,
    )
    platz.click()
    dialog = seite.locator("#aushang-dialog")
    expect(dialog).to_contain_text("Ich bin Ines Probe und kann nicht")
    aktion = dialog.locator("form.aushang-aktion").first
    aktion.locator("select[name=dauer]").select_option(index=1)
    aktion.get_by_label("Meine PIN").fill("482915")
    # Pfeile und Rahmen liegen nicht über einem modalen Dialog; fürs Bild ohne Abdunklung zeigen
    seite.evaluate(
        "() => { const d = document.getElementById('aushang-dialog'); d.close(); d.show(); }"
    )
    aufnehmen(
        seite,
        "aushang-dialog",
        dialog,
        Marke(aktion.locator("select[name=grund]"), nummer=1),
        Marke(aktion.locator("select[name=dauer]"), nummer=2, von="rechts"),
        Marke(aktion.get_by_label("Meine PIN"), nummer=3),
        Marke(aktion.get_by_role("button", name="Austragen"), nummer=4, von="rechts"),
    )


def test_hilfe_bild_wetter(angemeldet, admin, muster, monkeypatch):
    from apps.wetter import wetter

    def holen(adresse, werte):  # statt Open-Meteo: erfundener Ort, bedeckt, 12 °C
        if adresse == wetter.SUCHE:
            return {
                "results": [
                    {
                        "name": "Musterstadt",
                        "latitude": 51.5,
                        "longitude": 7.1,
                        "postcodes": ["12345"],
                    }
                ]
            }
        return {"current": {"temperature_2m": 12.4, "weather_code": 3, "is_day": 1}}

    monkeypatch.setattr(wetter, "_json", holen)
    _module("wetter")
    Ausgabestelle.objects.filter(name="Ausgabestelle Mitte").update(
        strasse="Hauptstr. 1", plz="12345", ort="Musterstadt"
    )
    seite = oeffnen(angemeldet, admin, "/")
    platz = seite.locator(".kopf-wetter")
    expect(platz).to_contain_text("12 °C")
    aufnehmen(seite, "wetter-kopf", seite.locator(".kopf"), Marke(platz, "rahmen", 1))


def test_hilfe_bild_links(angemeldet, admin, muster):
    from apps.links.models import Link, LinkGruppe

    _module("links")
    anzeigen = LinkGruppe.objects.create(titel="Anzeigen im Wartebereich", reihenfolge=1)
    werkzeuge = LinkGruppe.objects.create(titel="Werkzeuge", reihenfolge=2)
    Link.objects.create(
        titel="Monitor",
        untertitel="Wartebereich",
        adresse="/aufruf/einstellungen/",
        symbol="📺",
        gruppe=anzeigen,
        neuer_tab=False,
        beschreibung="Links für Monitor und Kiosk",
    )
    Link.objects.create(
        titel="Webseite der Tafel", adresse="https://tafel.example", symbol="🌐", gruppe=anzeigen
    )
    Link.objects.create(
        titel="Serververwaltung",
        adresse="https://server.tafel.example",
        symbol="🖥️",
        gruppe=werkzeuge,
        warnung="Nur für die Technik",
        recht="einstellungen.links",
    )
    seite = oeffnen(angemeldet, admin, "/")
    bereich = seite.locator("section.link-bereich")
    aufnehmen(
        seite,
        "links-start",
        bereich,
        Marke(bereich.locator("a.link-kachel").first, "rahmen", 1),
        Marke(bereich.locator("a.link-warnung"), "rahmen", 2),
    )


def test_hilfe_bild_listen(angemeldet, admin, muster):
    _module("listen")
    _haushalte(muster.kundengruppe, 6)
    seite = oeffnen(angemeldet, admin, reverse("listen:liste", args=["kunden_stelle"]))
    seite.select_option("#f-stelle", label="Ausgabestelle Mitte")
    tabelle = seite.locator("table.tabelle")
    expect(tabelle).to_contain_text("Beispiel")
    filter_ = seite.locator("form.listen-filter")
    aufnehmen(
        seite,
        "listen-filter",
        [seite.locator("h1"), filter_],
        Marke(filter_.locator(".feld", has=seite.locator("#f-stelle")), "rahmen", 1),
        Marke(filter_.locator(".feld", has=seite.locator("#f-gliedern")), "rahmen", 2),
        Marke(filter_.locator("details.spalten-wahl summary"), nummer=3, von="unten", laenge=40),
    )
    tabelle.locator("tbody input[type=checkbox]").nth(1).check()
    tabelle.locator("tbody input[type=checkbox]").nth(3).check()
    aktionen = seite.locator(".liste-aktionen")
    aufnehmen(
        seite,
        "listen-tabelle",
        [aktionen, tabelle.locator("tbody tr").nth(4)],
        Marke(tabelle.locator("thead input[type=checkbox]"), nummer=1, laenge=50),
        Marke(tabelle.locator("thead a.sortieren").nth(2), "rahmen", 2),
        Marke(
            aktionen.get_by_role("button", name="⬇ CSV (Excel)"), nummer=3, von="oben", laenge=40
        ),
        Marke(
            aktionen.get_by_role("button", name="🖨 PDF drucken"), nummer=4, von="oben", laenge=40
        ),
    )


def test_hilfe_bild_wochenuebersicht(angemeldet, admin, muster):
    from apps.kunden.models import Kundengruppe
    from apps.wochenuebersicht.models import Selbstabholer

    _module("wochenuebersicht")
    Kundengruppe.objects.filter(pk=muster.kundengruppe.pk).update(wochentage="Di, Fr", maximum=40)
    nord = Ausgabestelle.objects.get(name="Ausgabestelle Nord")
    b = Kundengruppe.objects.create(
        kuerzel="B", name="Gruppe B", ausgabestelle=nord, wochentage="Di", maximum=25
    )
    _haushalte(muster.kundengruppe, 9)
    _haushalte(b, 6, start=201)
    Selbstabholer.objects.create(name="Kinderhaus Sonnenschein", tage="Di", personen=18)
    seite = oeffnen(angemeldet, admin, reverse("wochenuebersicht:uebersicht"))
    karte = seite.locator("section.karte")
    erste = karte.locator(".tabelle-rahmen", has=seite.locator("tr.wochen-selbst"))
    aufnehmen(
        seite,
        "wochenuebersicht-tag",
        [karte.locator("h1"), erste],
        Marke(karte.locator("label", has_text="mit Abholungen der Woche"), "rahmen", 1),
        Marke(karte.get_by_role("link", name="PDF Querformat"), nummer=2, von="rechts", laenge=50),
        Marke(erste.locator("thead th").nth(1), "rahmen", 3),
        Marke(erste.locator("tr.wochen-selbst"), "rahmen", 4),
    )


def test_hilfe_bild_abrechnung(angemeldet, admin, muster, benutzer_mit_rolle):
    from decimal import Decimal as D

    from apps.abrechnung.models import Monatsabrechnung, Posten
    from apps.ausgabe.models import Buchung

    _module("abrechnung")
    mitte = Ausgabestelle.objects.get(name="Ausgabestelle Mitte")
    heute = timezone.localdate()
    erster = heute.replace(day=1)
    for tag, bar in ((2, "38.50"), (9, "41.00"), (16, "36.50")):
        Buchung.objects.create(
            art=Buchung.Art.ABHOLUNG,
            soll=D(bar),
            haben=D(bar),
            bar=D(bar),
            datum=erster + dt.timedelta(days=tag),
            ausgabestelle=mitte,
        )
    abr = Monatsabrechnung.objects.create(stelle=mitte, monat=erster)
    Posten.objects.create(
        abrechnung=abr,
        datum=erster + dt.timedelta(days=3),
        betrag=D("18.90"),
        art="Reinigung",
        empfaenger="Drogerie am Markt",
        quittung="erfunden",
        quittung_typ="image/jpeg",
    )
    Posten.objects.create(
        abrechnung=abr,
        datum=erster + dt.timedelta(days=10),
        betrag=D("6.00"),
        art="Fahrtkosten",
        empfaenger="Parkhaus",
    )
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.first_name, anton.last_name = "Anton", "Probe"
    anton.save()
    anton.ausgabestellen.set([mitte])
    seite = oeffnen(angemeldet, anton, reverse("abrechnung:uebersicht"))
    karte = seite.locator("section.karte")
    ausgaben = karte.locator(".tabelle-rahmen")
    aufnehmen(
        seite,
        "abrechnung-monat",
        [karte.locator("h1"), ausgaben],
        Marke(
            karte.locator("table.tabelle").first.locator("td.zahl").last,
            nummer=1,
            von="rechts",
            laenge=60,
        ),
        Marke(ausgaben.locator(".marke-warnung"), nummer=2, von="rechts", laenge=60),
        Marke(karte.get_by_role("link", name="PDF", exact=True), "rahmen", 3),
    )
    seite.fill("#id_betrag", "12,50")
    seite.select_option("#id_art", "Verbrauchsmaterial")
    seite.fill("#id_empfaenger", "Großmarkt Musterstadt")
    titel = karte.get_by_role("heading", name="Ausgabe eintragen")
    knopf = karte.get_by_role("button", name="Ausgabe speichern")
    aufnehmen(
        seite,
        "abrechnung-eintragen",
        [titel, knopf],
        Marke(seite.locator("#id_betrag"), nummer=1, von="rechts", laenge=50),
        Marke(seite.locator("#id_foto"), nummer=2, von="rechts", laenge=50),
        Marke(knopf, nummer=3, von="rechts", laenge=50),
    )


def test_hilfe_bild_warteliste(angemeldet, admin, muster):
    from apps.antraege.models import Antrag
    from apps.warteliste import ablauf
    from apps.warteliste.models import Termin

    _module("warteliste")
    antraege = []
    for i, (vorname, nachname) in enumerate(
        [
            ("Jana", "Beispiel"),
            ("Omar", "Probe"),
            ("Lea", "Sommer"),
            ("Pavel", "Winter"),
            ("Rana", "Feld"),
        ]
    ):
        a = Antrag.objects.create(
            vorname=vorname,
            nachname=nachname,
            telefon=f"0123 4567{i:02d}" if i % 2 else "",
            email="" if i % 2 else f"{vorname.lower()}@example.org",
            staatsangehoerigkeit=["deutsch", "syrisch", "ukrainisch"][i % 3],
        )
        Antrag.objects.filter(pk=a.pk).update(
            eingegangen_am=timezone.now() - dt.timedelta(days=20 - 3 * i)
        )
        antraege.append(a)
    ablauf.automatik()
    termin = Termin.objects.create(
        datum=timezone.localdate() + dt.timedelta(days=7), von=dt.time(10), bis=dt.time(12)
    )
    ablauf.einladen(antraege[:2], termin, "Clara Beispiel")

    seite = oeffnen(angemeldet, admin, reverse("warteliste:liste"), breite=1400)
    karte = seite.locator("section.karte").first
    for a in antraege[2:4]:
        karte.locator(f'input[name=ids][value="{a.pk}"]').check()
    einladen = karte.locator("fieldset", has_text="Ausgewählte einladen")
    aufnehmen(
        seite,
        "warteliste-liste",
        [karte.locator(".liste-kopf"), einladen],
        Marke(karte.locator("nav.reiter"), "rahmen", 1),
        Marke(karte.locator(f'input[name=ids][value="{antraege[2].pk}"]'), nummer=2, laenge=50),
        Marke(einladen.locator("select").first, nummer=3),
        Marke(einladen.get_by_role("button", name="Einladen"), nummer=4, von="rechts", laenge=50),
    )

    # Nach dem Termin: erschienen oder entschuldigt
    seite.goto(reverse("warteliste:termin", args=[termin.pk]))
    karte = seite.locator("section.karte").first
    karte.locator(f'input[name=ids][value="{antraege[0].pk}"]').check()
    status = karte.locator("fieldset", has_text="Status der Ausgewählten setzen")
    status.locator("select").first.select_option(label="erschienen")
    aufnehmen(
        seite,
        "warteliste-termin",
        [karte.locator("h1"), status],
        Marke(karte.locator(f'input[name=ids][value="{antraege[0].pk}"]'), nummer=1, laenge=50),
        Marke(status.locator("select").first, nummer=2),
        Marke(
            status.get_by_role("button", name="Status setzen"), nummer=3, von="rechts", laenge=50
        ),
    )
