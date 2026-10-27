"""Statistik (ADR 0036). Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.ausgabe.models import Buchung
from apps.konten import rollen
from apps.kunden.models import Abholung, Ausgabestelle, Haushalt, Kundengruppe, Person
from apps.statistik import auswertung as aw
from apps.statistik import diagramme as dg

pytestmark = pytest.mark.django_db
URL = reverse("statistik:uebersicht")


@pytest.fixture
def daten():
    mitte = Ausgabestelle.objects.create(name="Ausgabestelle Mitte")
    nord = Ausgabestelle.objects.create(name="Ausgabestelle Nord")
    g1 = Kundengruppe.objects.create(name="Montag", ausgabestelle=mitte, maximum=4)
    g2 = Kundengruppe.objects.create(name="Dienstag", ausgabestelle=nord)
    h1 = Haushalt.objects.create(kundennummer="1", kundengruppe=g1, kunde_seit=dt.date(2026, 2, 1))
    h2 = Haushalt.objects.create(kundennummer="2", kundengruppe=g2, status="pausiert")
    for h, geburtstage in ((h1, [dt.date(1980, 1, 1), dt.date(2020, 5, 5)]),
                           (h2, [dt.date(1950, 3, 3)])):  # fmt: skip
        for i, g in enumerate(geburtstage):
            Person.objects.create(haushalt=h, ist_hauptperson=i == 0, vorname="Erika",
                                  nachname="Probe", geburtsdatum=g)  # fmt: skip
    for tag, h, stelle in ((dt.date(2026, 1, 5), h1, mitte), (dt.date(2026, 1, 12), h1, mitte),
                           (dt.date(2026, 2, 3), h2, nord)):  # fmt: skip
        Abholung.objects.create(
            haushalt=h, datum=tag, uhrzeit=dt.time(10, 15), ausgabestelle=stelle
        )
    Buchung.objects.create(haushalt=h1, datum=dt.date(2026, 1, 5), art="abholung",
                           bar=Decimal("1.50"), ausgabestelle=mitte)  # fmt: skip
    return mitte, nord


Z = aw.Zeitraum(dt.date(2026, 1, 1), dt.date(2026, 3, 31))


def test_zeitraeume_und_perioden():
    v = aw.zeitraeume(dt.date(2026, 10, 25))
    assert (v["jahr"].von, v["vorjahr"].bis) == (dt.date(2026, 1, 1), dt.date(2025, 12, 31))
    assert (v["vormonat"].von, v["vormonat"].bis) == (dt.date(2026, 9, 1), dt.date(2026, 9, 30))
    assert v["12monate"].von == dt.date(2025, 11, 1) and v["30tage"].einheit == "tag"
    assert Z.einheit == "woche"
    assert aw.perioden(aw.Zeitraum(dt.date(2025, 11, 1), dt.date(2026, 2, 1)))[0][1] == "KW 44"
    jahr = aw.Zeitraum(dt.date(2025, 11, 1), dt.date(2026, 10, 31))
    assert [n for _, n in aw.perioden(jahr)][:3] == ["Nov 25", "Dez 25", "Jan 26"]


def test_auswertungen(daten):
    mitte, _ = daten
    monate = aw.Zeitraum(dt.date(2025, 12, 1), dt.date(2026, 4, 30))
    assert aw.verlauf(aw.abholungen(monate), monate) == [0, 2, 1, 0, 0]
    assert aw.verlauf(aw.abholungen(monate, [mitte]), monate) == [0, 2, 0, 0, 0]
    assert aw.je_stelle(Z) == [("Ausgabestelle Mitte", 2), ("Ausgabestelle Nord", 1)]
    assert dict(aw.je_wochentag(Z))["Mo"] == 2 and dict(aw.je_wochentag(Z))["Di"] == 1
    assert aw.je_stunde(Z) == [("10 Uhr", 3)]
    serien = aw.verlauf_je_stelle(monate)
    assert [(s.name, s.summe, s.farbe) for s in serien] == [
        ("Ausgabestelle Mitte", 2, 0), ("Ausgabestelle Nord", 1, 1)]  # fmt: skip
    heute = dt.date(2026, 10, 25)
    assert dict(aw.haushaltsgroessen(heute))["2"] == 1  # nur aktive Haushalte
    alter = dict(aw.altersgruppen(heute))
    assert alter["6–13"] == 1 and alter["25–49"] == 1 and alter["65 und älter"] == 0
    assert dict(aw.status())["pausiert"] == 1
    auslastung = {a.name: a for a in aw.auslastung()}
    assert auslastung["Montag"].prozent == 25.0 and auslastung["Dienstag"].prozent is None
    k = aw.kennzahlen(Z)
    assert (k.abholungen, k.haushalte, k.personen, k.einnahmen) == (3, 2, 5, Decimal("1.50"))
    assert k.neue_kunden == 1 and k.aktive_haushalte == 1


def test_mehr_als_acht_stellen_werden_andere():
    for i in range(10):
        stelle = Ausgabestelle.objects.create(name=f"Stelle {i:02d}")
        h = Haushalt.objects.create(kundennummer=f"S{i}")
        for _ in range(i + 1):
            Abholung.objects.create(haushalt=h, datum=dt.date(2026, 1, 5), ausgabestelle=stelle)
    serien = aw.verlauf_je_stelle(Z)
    assert len(serien) == 8 and serien[-1].name == "Andere" and serien[-1].summe == 1 + 2 + 3
    assert sorted(s.farbe for s in serien) == list(range(8))


def test_diagramme_escapen_und_skala():
    svg = dg.saeulen([("<script>", 3), ("b", 0)], "Titel & mehr")
    assert (
        "<script>" not in svg and "&lt;script&gt;" in svg and 'aria-label="Titel &amp; mehr"' in svg
    )
    assert dg._skala(352)[0] == 400 and dg._skala(3)[0] == 4 and dg._skala(0)[0] == 4
    assert dg.saeulen([], "x") == "" and dg.balken([], "x") == "" and dg.linien([], [], "x") == ""
    assert "1.618" in dg.balken([("Nord", 1618)], "x")


def test_seite_und_rechte(client, admin_client, benutzer_mit_rolle, anmelden, daten):
    seite = admin_client.get(URL, {"zeitraum": "eigen", "von": "2026-01-01", "bis": "2026-03-31"})
    inhalt = seite.content.decode()
    assert "Abholungen je Woche" in inhalt and "<svg" in inhalt and "Zahlen als Tabelle" in inhalt
    assert "Abholungen je Ausgabestelle und Woche" in inhalt and "Statistik</a>" in inhalt
    csv = admin_client.get(URL, {"zeitraum": "eigen", "von": "2026-01-01", "bis": "2026-03-31",
                                 "csv": "stellen"})  # fmt: skip
    assert csv["Content-Type"].startswith("text/csv")
    assert "Ausgabestelle Mitte;2" in csv.content.decode("utf-8-sig")
    # ungültiger eigener Zeitraum: Vorgabe „Letzte 12 Monate“
    assert (
        "Letzte 12 Monate"
        in admin_client.get(URL, {"zeitraum": "eigen", "von": "x"}).content.decode()
    )

    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))  # derselbe Client
    assert client.get(URL).status_code == 403
    client.logout()
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(URL).status_code == 200


def test_ausgabestelle_sieht_nur_eigene_zahlen(client, admin, benutzer_mit_rolle, anmelden,
                                              recht_geben, daten):  # fmt: skip
    mitte, nord = daten
    recht_geben(rollen.AUSGABE, "statistik.sehen")
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    anmelden(client, b)
    zeit = {"zeitraum": "eigen", "von": "2026-01-01", "bis": "2026-03-31"}
    inhalt = client.get(URL, zeit).content.decode()
    assert "alle meine" in inhalt and "Ausgabestelle Nord" not in inhalt
    kacheln = inhalt.split('<div class="kacheln">')[1].split("statistik-sprung")[0]
    assert "Anträge" not in kacheln  # keine Kachel „Anträge“ für die Ausgabe
    csv = client.get(URL, {**zeit, "csv": "stellen"}).content.decode("utf-8-sig")
    assert "Mitte;2" in csv and "Nord" not in csv
    # Eine fremde Ausgabestelle lässt sich nicht wählen
    csv = client.get(URL, {**zeit, "stelle": nord.pk, "csv": "stellen"}).content.decode("utf-8-sig")
    assert "Nord" not in csv


@pytest.fixture
def verein():
    from apps.adressen.models import Adresse
    from apps.mitglieder.models import Mitglied
    from apps.spenden.models import Spende

    erika = Adresse.objects.create(art="person", vorname="Erika", nachname="Muster")
    firma = Adresse.objects.create(organisation="Bäckerei Probe")
    for tag, betrag, zweck in ((dt.date(2026, 1, 10), "50", "Weihnachten"),
                               (dt.date(2026, 2, 10), "20", ""),
                               (dt.date(2026, 2, 20), "30", "Weihnachten")):  # fmt: skip
        Spende.objects.create(adresse=erika, datum=tag, betrag=Decimal(betrag), zweck=zweck)
    Spende.objects.create(adresse=erika, datum=dt.date(2026, 1, 15), betrag=Decimal("36"),
                          mitgliedsbeitrag=True)  # fmt: skip
    Spende.objects.create(adresse=firma, datum=dt.date(2026, 3, 1), art="sach",
                          beschreibung="Brot", betrag=Decimal("15"))  # fmt: skip
    Spende.objects.create(adresse=firma, datum=dt.date(2025, 3, 1), betrag=Decimal("999"))
    Mitglied.objects.create(adresse=erika, nummer="1", art="Ordentliches Mitglied",
                            eintritt=dt.date(2026, 2, 1))  # fmt: skip
    Mitglied.objects.create(adresse=firma, nummer="2", art="Fördermitglied",
                            eintritt=dt.date(2020, 1, 1), austritt=dt.date(2026, 3, 15),
                            austrittsgrund="Kündigung")  # fmt: skip


def test_spenden_und_mitglieder_auswertungen(verein):
    s = aw.spendenzahlen(Z)
    assert (s.geld, s.geldspenden, s.sachspenden, s.sachwert, s.spender, s.beitraege) == (
        Decimal("100"), 3, 1, Decimal("15"), 2, Decimal("36"))  # fmt: skip
    assert aw.spenden_nach_zweck(Z) == [("Weihnachten", 80.0), ("ohne Zweck", 20.0)]
    monate = aw.Zeitraum(dt.date(2026, 1, 1), dt.date(2026, 4, 30))
    ein, aus = aw.mitglieder_ein_und_austritte(monate)
    assert ein.werte == [0, 1, 0, 0] and aus.werte == [0, 0, 1, 0]
    assert aw.mitglieder_nach_art(dt.date(2026, 3, 1)) == [
        ("Fördermitglied", 1), ("Ordentliches Mitglied", 1)]  # fmt: skip
    assert aw.mitglieder_nach_art(dt.date(2026, 3, 31)) == [("Ordentliches Mitglied", 1)]


def test_spenden_und_mitglieder_auf_der_seite(client, admin_client, benutzer_mit_rolle, anmelden,
                                              recht_geben, daten, verein):  # fmt: skip
    from apps.mitglieder.models import MitgliederEinstellungen

    zeit = {"zeitraum": "eigen", "von": "2026-01-01", "bis": "2026-03-31"}
    inhalt = admin_client.get(URL, zeit).content.decode()
    assert "Geldspenden je Woche" in inhalt and "Geldspenden nach Zweck" in inhalt
    assert "100,00 €" in inhalt and "Eintritte und Austritte je Woche" in inhalt
    assert "Mitglieder nach Art" in inhalt and "Mitgliedsbeiträge" not in inhalt  # Beiträge aus
    csv = admin_client.get(URL, {**zeit, "csv": "spenden_zweck"}).content.decode("utf-8-sig")
    assert "Weihnachten;80,00" in csv
    e = MitgliederEinstellungen.laden()
    e.beitraege = True
    e.save()
    assert "36,00 €" in admin_client.get(URL, zeit).content.decode()
    # Mit gewählter Ausgabestelle: nichts vom Verein
    mitte, _ = daten
    inhalt = admin_client.get(URL, {**zeit, "stelle": mitte.pk}).content.decode()
    assert "Geldspenden" not in inhalt and "Mitglieder nach Art" not in inhalt
    # Ohne die Rechte des Bereichs: nichts vom Verein
    recht_geben(rollen.AUSGABE, "statistik.sehen")
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    inhalt = client.get(URL, zeit).content.decode()
    assert "Geldspenden" not in inhalt and "Mitglieder nach Art" not in inhalt


def test_jahresbericht(client, admin_client, benutzer_mit_rolle, anmelden, recht_geben, daten,
                       verein, pdf_text):  # fmt: skip
    from django.utils import timezone

    seite = admin_client.get(URL).content.decode()
    assert "Jahresbericht (PDF)" in seite
    antwort = admin_client.get(reverse("statistik:jahresbericht"), {"jahr": "2026"})
    assert antwort["Content-Type"] == "application/pdf"
    text = pdf_text(antwort)
    for wort in ("Jahresbericht 2026", "Kennzahlen", "Abholungen je Monat",
                 "Geldspenden nach Zweck", "Weihnachten", "Mitglieder nach Art"):  # fmt: skip
        assert wort in text, wort
    assert "Erika" not in text and "Muster" not in text  # keine Personendaten
    # ungültiges Jahr: laufendes Jahr
    text = pdf_text(admin_client.get(reverse("statistik:jahresbericht"), {"jahr": "1800"}))
    assert f"Jahresbericht {timezone.localdate().year}" in text
    # Ausgabestelle: nur deren Zahlen, ohne Verein
    mitte, nord = daten
    recht_geben(rollen.AUSGABE, "statistik.sehen")
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    anmelden(client, b)
    text = pdf_text(client.get(reverse("statistik:jahresbericht"), {"jahr": "2026",
                                                                   "stelle": nord.pk}))  # fmt: skip
    assert "Ausgabestelle Nord" not in text and "Geldspenden" not in text
    client.logout()
    anmelden(client, benutzer_mit_rolle("kurt", rollen.KIOSK))
    assert client.get(reverse("statistik:jahresbericht")).status_code == 403


def test_jahresbericht_zahlen_und_leere_diagramme():
    from apps.statistik import jahresbericht as jb

    assert jb._zahl("1.234,50") == 1234.5 and jb._zahl(3) == 3.0 and jb._zahl("25,0 %") == 25.0
    assert jb._zahl("–") is None
    assert jb.saeulen([("Jan", 0)], 100, "#000000") is None
    assert jb.saeulen([("Jan", 2)], 100, "#000000") is not None
    z = jb.zeitraum(2026, dt.date(2026, 10, 25))
    assert (z.von, z.bis) == (dt.date(2026, 1, 1), dt.date(2026, 10, 25))
