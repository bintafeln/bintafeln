"""Bilder für das Handbuch: Verwaltung – Einstellungen, Rollen, Mitarbeitende, Personal,
Arbeitszeit, Sicherungen, Export, Änderungsprotokoll und Update (Werkzeug und Anleitung in
``hilfe_bilder.py``)."""

import datetime as dt
import re
from decimal import Decimal as D

from django.urls import reverse
from django.utils import timezone
from playwright.sync_api import expect

from apps.konten import rollen
from tests.e2e.hilfe_bilder import Marke, aufnehmen, oeffnen


def _zeit(tag: dt.date, uhr: str) -> dt.datetime:
    stunde, minute = map(int, uhr.split(":"))
    return dt.datetime.combine(tag, dt.time(stunde, minute), timezone.get_current_timezone())


def _kim(benutzer_mit_rolle):
    """Erfundene Festangestellte „Kim Probe“ mit der Rolle Ausgabe."""
    kim = benutzer_mit_rolle("kim", rollen.AUSGABE)
    kim.first_name, kim.last_name, kim.beschaeftigung = "Kim", "Probe", "fest"
    kim.save()
    return kim


def _arbeitstage(heute: dt.date, anzahl: int) -> list[dt.date]:
    """Die letzten Werktage vor heute im laufenden Monat (am Monatsanfang ggf. weniger)."""
    tage, tag = [], heute - dt.timedelta(days=1)
    while len(tage) < anzahl and tag.month == heute.month:
        if tag.weekday() < 5:
            tage.append(tag)
        tag -= dt.timedelta(days=1)
    return sorted(tage)


# --- Einstellungen ----------------------------------------------------------------------------


def test_hilfe_bild_einstellungen(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("core:einstellungen"))
    menue = seite.locator("details.menue-bereich[open]")
    tafel = menue.locator("details.menue-gruppe[open]")
    name, farbe = seite.locator("#id_name"), seite.locator("#id_farbe")
    titel = seite.locator("section.karte h1").first
    aufnehmen(seite, "einstellungen-uebersicht", [menue, titel, name, farbe],
              Marke(menue.locator("summary").first, nummer=1, von="rechts", laenge=25),
              Marke(tafel.get_by_role("link", name="Tafel und Module"), nummer=2,
                    von="rechts", laenge=25),
              Marke(name, nummer=3, von="unten", laenge=50),
              Marke(farbe, nummer=4, von="rechts", laenge=60))  # fmt: skip

    ort = seite.locator("#id_ort")
    ort.fill("Musterstadt")
    ort.press("Tab")
    ok = seite.locator(".autosave-ok").first
    aufnehmen(seite, "einstellungen-sofort",
              [seite.locator("#id_strasse"), seite.locator("#id_plz"), ort, ok],
              Marke(ort, nummer=1, von="oben", laenge=50),
              Marke(ok, "rahmen", 2))  # fmt: skip

    module = seite.get_by_text("Zusätzliche Module", exact=True)
    aufruf = seite.get_by_label("Aufruf", exact=False).first
    liste = seite.locator("input[name=module]").last
    aufnehmen(seite, "einstellungen-module", [module, aufruf, liste],
              Marke(aufruf, nummer=1, von="links", laenge=45))  # fmt: skip


# --- Rollen und Rechte ------------------------------------------------------------------------


def test_hilfe_bild_rollen(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("konten:rollen"))
    karte = seite.locator("section.karte").first
    aufnehmen(seite, "rollen-liste", karte,
              Marke(seite.get_by_role("link", name="Neue Rolle"), nummer=1, von="links",
                    laenge=40),
              Marke(karte.get_by_role("link", name="Ausgabe", exact=True), nummer=2,
                    von="links", laenge=40))  # fmt: skip

    seite.get_by_role("link", name="Neue Rolle").click()
    seite.fill("#id_name", "Lager")
    seite.fill("#id_beschreibung", "Warenannahme und Sortieren")
    seite.get_by_label("Braucht Belehrung nach Infektionsschutzgesetz").check()
    kopf = seite.locator("section.karte").first
    bereich = seite.locator("fieldset.rechte-bereich").first
    alle = bereich.get_by_role("button", name="alle")
    zuruecknehmen = bereich.get_by_role(
        "checkbox", name=re.compile("Abholungen, Zahlungen und Sonderaktionen selbst")
    )
    aufnehmen(seite, "rollen-bearbeiten", [kopf, bereich],
              Marke(seite.locator("#id_name"), nummer=1, von="oben", laenge=40),
              Marke(seite.locator("#id_zwei_faktor_pflicht"), nummer=2, von="links",
                    laenge=40),
              Marke(alle, nummer=3, von="links", laenge=40),
              Marke(zuruecknehmen, nummer=4, von="links", laenge=45))  # fmt: skip


# --- Mitarbeitende ----------------------------------------------------------------------------


def test_hilfe_bild_mitarbeitende(angemeldet, admin, muster, benutzer_mit_rolle):
    kim = _kim(benutzer_mit_rolle)
    seite = oeffnen(angemeldet, admin, reverse("konten:mitarbeitende"))
    karte = seite.locator("section.karte").first
    anlegen = seite.get_by_role("link", name="Konto anlegen")
    aufnehmen(seite, "mitarbeitende-liste", karte,
              Marke(anlegen, nummer=1, von="links", laenge=40),
              Marke(seite.get_by_role("link", name="Archiv (gesperrt)"), "rahmen", 2),
              Marke(seite.get_by_role("link", name="Ausgabestellen", exact=True), nummer=3,
                    von="rechts", laenge=50))  # fmt: skip

    anlegen.click()
    seite.fill("#id_username", "jonas.probe")
    seite.fill("#id_first_name", "Jonas")
    seite.fill("#id_last_name", "Probe")
    seite.get_by_label("Ausgabestelle Nord").check()
    seite.get_by_label("Ausgabe", exact=True).check()
    ausgabestellen = seite.locator("#id_ausgabestellen").locator("xpath=..")
    rollenwahl = seite.locator("#id_rollen").locator("xpath=..")
    aufnehmen(seite, "mitarbeitende-neu", seite.locator("section.karte").first,
              Marke(seite.locator("#id_username"), nummer=1, von="oben", laenge=30),
              Marke(ausgabestellen, "rahmen", 2),
              Marke(rollenwahl, "rahmen", 3),
              Marke(seite.get_by_role("button", name="Anlegen"), nummer=4, von="rechts",
                    laenge=50))  # fmt: skip

    seite.goto(reverse("konten:mitarbeiter", args=[kim.pk]))
    zugang = seite.locator("section.karte", has=seite.get_by_role("heading", name="Zugang"))
    aufnehmen(seite, "mitarbeitende-zugang", zugang,
              Marke(zugang.get_by_role("button", name="Passwort zurücksetzen"), nummer=1,
                    von="unten", laenge=40),
              Marke(zugang.get_by_role("button", name="Werkseinstellungen"), nummer=2,
                    von="unten", laenge=40),
              Marke(zugang.get_by_role("button", name="Sperren"), nummer=3, von="rechts",
                    laenge=50))  # fmt: skip


# --- Personal ---------------------------------------------------------------------------------


def test_hilfe_bild_personal(angemeldet, admin, muster, benutzer_mit_rolle):
    from apps.core.models import TafelEinstellungen
    from apps.personal.models import Abwesenheit, Arbeitsvertrag, Zeitbuchung

    t = TafelEinstellungen.laden()
    t.bundesland = "NW"
    t.save()
    kim = _kim(benutzer_mit_rolle)
    heute = timezone.localdate()
    beginn = heute.replace(day=1)
    Arbeitsvertrag.objects.create(benutzer=kim, beginn=beginn, wochenstunden=D("30"),
                                  urlaubstage=D("30"), taetigkeit="Lagerleitung")  # fmt: skip
    urlaub = heute + dt.timedelta(days=14)  # geplanter Urlaub
    Abwesenheit.objects.create(benutzer=kim, art=Abwesenheit.Art.URLAUB, von=urlaub,
                               bis=urlaub + dt.timedelta(days=4))  # fmt: skip
    for tag in _arbeitstage(heute, 31) + ([heute] if heute.weekday() < 5 else []):
        Zeitbuchung.objects.create(benutzer=kim, beginn=_zeit(tag, "08:00"),
                                   ende=_zeit(tag, "14:00"))  # fmt: skip

    seite = oeffnen(angemeldet, admin, reverse("personal:person", args=[kim.pk]))
    karten = seite.locator("section.karte")
    urlaubskarte = karten.filter(has=seite.get_by_role("heading", name=f"Urlaub {heute.year}"))
    stand = karten.filter(has=seite.get_by_role("heading", name=f"Stundenkonto {heute.year}"))
    aufnehmen(seite, "personal-person", [karten.first, urlaubskarte, stand.locator("p").first],
              Marke(seite.get_by_role("link", name="Arbeitszeiten"), nummer=1, von="links",
                    laenge=45),
              Marke(seite.get_by_text("Arbeitsvertrag eintragen"), nummer=2, von="links",
                    laenge=45),
              Marke(seite.get_by_text("Urlaub oder Krankheit eintragen"), nummer=3,
                    von="links", laenge=45))  # fmt: skip

    seite.get_by_role("link", name="Arbeitszeiten").click()
    seite.get_by_role("link", name="Zeit nachtragen").click()
    tag = heute - dt.timedelta(days=1)
    seite.fill("#id_datum", tag.isoformat())
    seite.fill("#id_kommen", "08:00")
    seite.fill("#id_pause_von", "12:00")
    seite.fill("#id_pause_bis", "12:30")
    seite.fill("#id_gehen", "15:00")
    seite.fill("#id_bemerkung", "Stempeln vergessen")
    pause = [seite.locator(f"#id_pause_{n}").locator("xpath=..") for n in ("von", "bis")]
    aufnehmen(seite, "personal-zeit-nachtragen", seite.locator("section.karte").first,
              Marke(seite.locator("#id_kommen"), nummer=1, von="unten", laenge=25),
              Marke(pause[0], "rahmen", 2), Marke(pause[1], "rahmen", 2),
              Marke(seite.locator("#id_bemerkung"), nummer=3, von="rechts", laenge=50),
              Marke(seite.get_by_role("button", name="Speichern"), nummer=4, von="rechts",
                    laenge=50))  # fmt: skip


# --- Meine Arbeitszeit ------------------------------------------------------------------------


def test_hilfe_bild_arbeitszeit(angemeldet, admin, muster):
    from apps.personal.models import Zeitbuchung

    admin.beschaeftigung = "fest"
    admin.save()
    heute = timezone.localdate()
    for tag in _arbeitstage(heute, 3):
        Zeitbuchung.objects.create(benutzer=admin, beginn=_zeit(tag, "08:00"),
                                   ende=_zeit(tag, "12:00"))  # fmt: skip
        Zeitbuchung.objects.create(benutzer=admin, beginn=_zeit(tag, "12:30"),
                                   ende=_zeit(tag, "15:15"))  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("personal:meine_arbeitszeit"))
    seite.get_by_role("button", name="Kommen").click()
    karte = seite.locator("section.karte").first
    menue = seite.locator("nav.seitenmenue a", has_text="Meine Arbeitszeit")
    aufnehmen(seite, "arbeitszeit-stempeln", [seite.locator("ul.meldungen"), menue, karte],
              Marke(menue, nummer=1, von="rechts", laenge=25),
              Marke(seite.get_by_role("button", name="Pause"), nummer=2, von="links",
                    laenge=30),
              Marke(seite.get_by_role("button", name="Gehen"), nummer=3, von="rechts",
                    laenge=50))  # fmt: skip

    zeiten = seite.locator("section.karte", has=seite.get_by_role("heading", name="Meine Zeiten"))
    aufnehmen(seite, "arbeitszeit-monat", zeiten,
              Marke(zeiten.locator("table"), nummer=1, von="links", laenge=45),
              Marke(zeiten.get_by_role("link", name="← früher"), nummer=2, von="links",
                    laenge=45))  # fmt: skip


# --- Sicherungen ------------------------------------------------------------------------------


def test_hilfe_bild_sicherungen(angemeldet, admin, muster):
    from apps.core.models import SicherungsAuftrag, SicherungsDienst

    jetzt = timezone.now()
    d = SicherungsDienst.laden()
    d.letzter_kontakt, d.schluessel_ok = jetzt, True
    d.ziele = "/media/usb-platte|402653184|976762584"  # KiB frei|gesamt
    d.save()
    gestern = timezone.localtime(jetzt - dt.timedelta(days=1)).replace(hour=2, minute=30)
    stand = gestern.strftime("%Y-%m-%d_%H%M%S")
    SicherungsAuftrag.objects.filter(standard=True).update(
        letzter_versuch=gestern, letzte_erfolgreiche=gestern, ergebnis="ok",
        meldung=f"Sicherung {stand} erstellt.", staende=f"{stand}|52480")  # fmt: skip
    seite = oeffnen(angemeldet, admin, reverse("core:sicherungen"))
    auftrag = seite.locator("section.karte").nth(1)
    aufnehmen(seite, "sicherungen-liste", [seite.locator("section.karte").first, auftrag],
              Marke(auftrag.get_by_role("button", name="Jetzt sichern"), nummer=1, von="unten",
                    laenge=40),
              Marke(auftrag.get_by_role("link", name="Bearbeiten"), nummer=2, von="rechts",
                    laenge=50),
              Marke(seite.get_by_role("link", name="Neuer Sicherungsauftrag"), nummer=3,
                    von="rechts", laenge=50))  # fmt: skip

    seite.get_by_role("link", name="Neuer Sicherungsauftrag").click()
    seite.fill("#id_name", "USB-Platte im Büro")
    seite.select_option("#id_ziel", "/media/usb-platte")
    for tag in ("Mo", "Di", "Mi", "Do", "Fr", "Sa"):
        seite.get_by_label(tag, exact=True).uncheck()
    seite.fill("#id_uhrzeit", "22:00")
    seite.fill("#id_anzahl", "8")
    wochentage = seite.locator("#id_wochentage")
    aufnehmen(seite, "sicherungen-auftrag", seite.locator("section.karte").first,
              Marke(seite.locator("#id_ziel"), nummer=1, von="oben", laenge=40),
              Marke(wochentage.locator("label", has_text="So"), nummer=2, von="rechts",
                    laenge=45),
              Marke(seite.locator("#id_uhrzeit"), nummer=3, von="unten", laenge=30),
              Marke(seite.locator("#id_anzahl"), nummer=4, von="rechts", laenge=45))  # fmt: skip


# --- Export und Zurücklesen -------------------------------------------------------------------


def test_hilfe_bild_datensicherung(angemeldet, admin, muster):
    seite = oeffnen(angemeldet, admin, reverse("core:datensicherung"))
    export = seite.locator("section.karte", has=seite.get_by_role("heading", name="Exportieren"))
    passwort = export.locator("input[type=password]")
    passwort.nth(0).fill("Beispiel-Passwort-123")
    passwort.nth(1).fill("Beispiel-Passwort-123")
    aufnehmen(seite, "datensicherung-export", export,
              Marke(export.locator("fieldset").first, nummer=1, von="links", laenge=45),
              Marke(passwort.nth(0), nummer=2, von="links", laenge=45),
              Marke(export.get_by_role("button", name="Export herunterladen"), nummer=3,
                    von="rechts", laenge=50))  # fmt: skip

    zurueck = seite.locator("section.karte", has=seite.get_by_role("heading", name="Zurücklesen"))
    aufnehmen(seite, "datensicherung-zuruecklesen", zurueck,
              Marke(zurueck.locator("input[type=file]"), nummer=1, von="oben", laenge=30),
              Marke(zurueck.locator("input[type=password]"), nummer=2, von="links", laenge=45),
              Marke(zurueck.get_by_role("button", name="Prüfen (noch nichts ändern)"), nummer=3,
                    von="rechts", laenge=50))  # fmt: skip


# --- Änderungsprotokoll -----------------------------------------------------------------------


def test_hilfe_bild_protokoll(angemeldet, admin, muster):
    from auditlog.context import set_actor
    from auditlog.models import LogEntry

    LogEntry.objects.all().delete()
    erika = muster.personen.get(vorname="Erika")
    with set_actor(admin):
        erika.nachname = "Muster-Beispiel"
        erika.save()
        max_ = muster.personen.get(vorname="Max")
        max_.vorname = "Maximilian"
        max_.save()
        muster.ausweis_gueltig_bis = muster.ausweis_gueltig_bis + dt.timedelta(days=365)
        muster.save()
    seite = oeffnen(angemeldet, admin, reverse("core:protokoll"))
    auswahl = seite.locator("#modell")
    auswahl.select_option(label="Person")
    zeilen = seite.locator("#protokoll-liste tbody tr")
    expect(zeilen).to_have_count(2)
    zeile = zeilen.first
    aufnehmen(seite, "protokoll-liste", seite.locator("section.karte").first,
              Marke(auswahl, nummer=1, von="rechts", laenge=50),
              Marke(zeile, "rahmen", 2))  # fmt: skip


# --- Update -----------------------------------------------------------------------------------


def test_hilfe_bild_update(angemeldet, admin, muster, settings, tmp_path):
    """Nur die Seite: Der Dienst „updater“ wird durch Dateien nachgestellt, es startet nichts."""
    from apps.core.models import SicherungsDienst

    d = SicherungsDienst.laden()
    d.letzter_kontakt, d.schluessel_ok = timezone.now(), True
    d.save()
    settings.BETRIEB_ORDNER = tmp_path
    jetzt = timezone.localtime().strftime("%Y-%m-%dT%H:%M:%S%z")
    (tmp_path / "lebenszeichen.txt").write_text(f"zeit={jetzt}\n")
    (tmp_path / "versionen.txt").write_text(
        f"abgerufen={jetzt}\ninstalliert=2026.10.2\nfehler=\n"
        "stufe=2026.10.10|neu\n"
        "version=2026.10.2|2026-10-20|Statistik als CSV\t\n"
        "version=2026.10.10|2026-10-25|Suche im Seitenkopf\tEinlass zeigt Notizen größer\t\n"
    )
    seite = oeffnen(angemeldet, admin, reverse("core:update"))
    karten = seite.locator("section.karte")
    neu = karten.filter(has=seite.get_by_role("heading", name="Neue Version verfügbar"))
    was = karten.filter(has=seite.get_by_role("heading", name="Was ist neu?"))
    banner = seite.get_by_text("Neue Version 2026.10.10 verfügbar.")
    aufnehmen(seite, "update-seite", [banner, neu, was],
              Marke(banner.locator("xpath=.."), nummer=1, von="links", laenge=45),
              Marke(seite.get_by_role("button", name="Jetzt nach neuen Versionen suchen"),
                    nummer=2, von="rechts", laenge=50),
              Marke(neu.locator("select"), nummer=3, von="rechts", laenge=30),
              Marke(neu.locator("input[type=checkbox]"), nummer=4, von="links", laenge=40),
              Marke(neu.get_by_role("button", name="Update starten"), nummer=5, von="rechts",
                    laenge=50))  # fmt: skip
