"""Verbandsstatistik: jährliche Abfrage des Dachverbands aus den Zahlen in bintafeln.
Alle Namen und Daten sind erfunden."""

import datetime as dt

import pytest
from django.urls import reverse

from apps.konten import rollen
from apps.konten.models import Stammdaten
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Einkommensart,
    Haushalt,
    KundenEinstellungen,
    Person,
)
from apps.statistik import verband

pytestmark = pytest.mark.django_db
URL = reverse("statistik:verband")


def haushalt(nr, einkommen, *geburtstage, staat="Deutschland", **abholung):
    h = Haushalt.objects.create(kundennummer=nr, einkommensart=einkommen)
    for i, geb in enumerate(geburtstage):
        Person.objects.create(haushalt=h, ist_hauptperson=i == 0, vorname=f"V{i}",
                              nachname=f"N{nr}", geburtsdatum=geb,
                              staatsangehoerigkeit=staat)  # fmt: skip
    return h


@pytest.fixture
def daten():
    e = KundenEinstellungen.laden()
    e.abholungen_aufbewahren_jahre = 3
    e.save()
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    buerger = Einkommensart.objects.create(bezeichnung="Bürgergeld")
    rente = Einkommensart.objects.create(bezeichnung="Grundsicherung im Alter")
    # Juni 2026: zwei Haushalte mit 1 Kind, 2 Erwachsenen, 1 Seniorin; einer aus der Ukraine
    a = haushalt("1", buerger, dt.date(1990, 5, 1), dt.date(2015, 3, 3), dt.date(2008, 7, 1))
    b = haushalt("2", rente, dt.date(1950, 1, 1), None, staat="Ukraine")
    c = haushalt("3", buerger, dt.date(1980, 1, 1))  # nur 2025
    for h, stelle, tage in ((a, mitte, [3, 10]), (b, nord, [17])):
        for t in tage:
            Abholung.objects.create(haushalt=h, datum=dt.date(2026, 6, t), ausgabestelle=stelle)
    for h in (a, c):
        Abholung.objects.create(haushalt=h, datum=dt.date(2025, 6, 5), ausgabestelle=mitte)
    Abholung.objects.create(haushalt=c, datum=dt.date(2026, 7, 1), ausgabestelle=mitte)
    return mitte, nord


def test_stufen_wie_im_fragebogen():
    assert [verband.stufe(p) for p in (-30, -25, -20, -15, -10, -5, 0, 4.99, 5, 14.99, 15,
                                       24.99, 25, 80)] == [
        -3, -3, -2, -2, -1, -1, 0, 0, 1, 1, 2, 2, 3, 3]  # fmt: skip


def test_zahlen_des_stichmonats_und_vergleich(daten, benutzer_mit_rolle):
    jetzt, vorher, fragen = verband.fragen(2026, 6)
    assert (jetzt.haushalte, jetzt.personen, jetzt.ukraine) == (2, 5, 2)
    # Stichtag 30.06.2026: geboren 2008-07-01 ist noch 17 → Kind
    assert (jetzt.kinder, jetzt.erwachsene, jetzt.mittlere, jetzt.senioren) == (2, 2, 1, 1)
    assert jetzt.ohne_geburtsdatum == 1
    assert dict(jetzt.einkommen) == {"Bürgergeld": 1, "Grundsicherung im Alter": 1}
    assert (vorher.haushalte, vorher.personen) == (2, 4)
    nach = {f.nummer: f for f in fragen}
    assert nach["2.1"].zeilen == [["Kund:innen insgesamt", 5]]
    assert nach["2.3"].zeilen[0] == ["Kinder und Jugendliche unter 18 Jahren", 2, "40,00 %"]
    assert "ohne Geburtsdatum" in nach["2.3"].hinweis
    assert nach["2.6"].zeilen == [["Staatsangehörigkeit Ukraine", 2, "40,00 %"]]
    # Kund:innen 4 → 5: +25 % → Stufe +3; Haushalte 2 → 2: 0
    assert nach["2.7"].zeilen[0] == ["Kund:innen insgesamt", 4, 5, "+25,00 %", 3]
    assert nach["3.3"].zeilen[0] == ["Haushalte insgesamt", 2, 2, "+0,00 %", 0]
    assert ["Grundsicherung im Alter", 0, 1, "–", None] in nach["3.3"].zeilen
    # Nur eine Ausgabestelle
    jetzt, _, _ = verband.fragen(2026, 6, [daten[1]])
    assert (jetzt.haushalte, jetzt.personen) == (1, 2)


def test_aktive(daten, benutzer_mit_rolle, django_user_model):
    erika = benutzer_mit_rolle("erika", rollen.AUSGABE)
    erika.first_name, erika.last_name = "V0", "N1"  # wie die Hauptperson von Haushalt 1
    erika.save()
    Stammdaten.objects.create(benutzer=erika, anrede="Frau", geburtsdatum=dt.date(1990, 5, 1))
    alt = benutzer_mit_rolle("otto", rollen.AUSGABE)
    Stammdaten.objects.create(benutzer=alt, anrede="Herr", geburtsdatum=dt.date(1955, 1, 1))
    fest = benutzer_mit_rolle("fest", rollen.BUERO)
    fest.beschaeftigung = django_user_model.Beschaeftigung.FEST
    fest.save()
    benutzer_mit_rolle("weg", rollen.AUSGABE).__class__.objects.filter(username="weg").update(
        is_active=False)  # fmt: skip
    a = verband.aktive(dt.date(2026, 6, 30))
    assert (a.gesamt, a.ehrenamtlich, a.beschaeftigt) == (3, 2, 1)
    assert (a.ehrenamt_ab_63, a.ehrenamt_bis_35, a.ehrenamt_weiblich) == (1, 0, 1)
    assert a.selbst_kunden == 1


def test_vorjahr_nach_loeschfrist_ohne_vergleich(daten):
    e = KundenEinstellungen.laden()
    e.abholungen_aufbewahren_jahre = 0
    e.save()
    _, vorher, fragen = verband.fragen(2026, 6)
    assert not vorher.vollstaendig
    f = next(f for f in fragen if f.nummer == "2.7")
    assert "Löschfrist" in f.hinweis and f.zeilen[0][1] == "–" and f.zeilen[0][4] is None


def test_seite_csv_pdf_und_recht(daten, admin_client, client, anmelden, benutzer_mit_rolle,
                                 pdf_text):  # fmt: skip
    html = admin_client.get(URL, {"jahr": 2026, "monat": 6}).content.decode()
    assert "Verbandsstatistik Juni 2026" in html and "Juni 2025" in html
    assert "<strong>+3</strong>" in html and "mindestens 25 % mehr" in html
    csv = admin_client.get(URL, {"jahr": 2026, "monat": 6, "format": "csv"})
    inhalt = csv.content.decode("utf-8-sig")
    assert "verbandsstatistik-2026-06.csv" in csv["Content-Disposition"]
    assert "2.1 Anzahl der direkten Kund:innen" in inhalt and "Kund:innen insgesamt;5" in inhalt
    pdf = pdf_text(admin_client.get(URL, {"jahr": 2026, "monat": 6, "format": "pdf"}))
    assert "Verbandsstatistik Juni 2026" in pdf and "Legende der Stufen" in pdf
    # Unsinnige Werte: Vorgabe-Jahr und Juni
    assert admin_client.get(URL, {"jahr": "x", "monat": "13"}).status_code == 200
    anmelden(client, benutzer_mit_rolle("ohne", rollen.AUSGABE))
    assert client.get(URL).status_code == 403
