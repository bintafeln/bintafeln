"""Spendenentwicklung als Grafik. Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal as D

import pytest
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.konten import rollen
from apps.spenden import entwicklung as ew
from apps.spenden.models import Spende

pytestmark = pytest.mark.django_db
HEUTE = dt.date(2025, 4, 20)  # laufendes Jahr bis April


def adresse(name):
    return Adresse.objects.create(art="person", nachname=name, strasse="Weg 1", plz="12345",
                                  ort="Musterstadt")  # fmt: skip


@pytest.fixture
def daten():
    erika, otto, firma = adresse("Beispiel"), adresse("Muster"), adresse("Probe")
    for a, tag, betrag in [
        (erika, dt.date(2024, 1, 10), "20"), (otto, dt.date(2024, 3, 5), "100"),
        (erika, dt.date(2024, 11, 2), "50"),
        (erika, dt.date(2025, 1, 15), "20"), (erika, dt.date(2025, 3, 1), "30"),
        (firma, dt.date(2025, 3, 20), "750"), (otto, dt.date(2025, 4, 2), "100"),
    ]:  # fmt: skip
        Spende.objects.create(adresse=a, datum=tag, betrag=D(betrag))
    # zählen nicht: Sachspende und Geldspende ohne Betrag
    Spende.objects.create(adresse=firma, datum=dt.date(2025, 2, 1), betrag=D("500"),
                          art=Spende.Art.SACH, beschreibung="Lebensmittel")  # fmt: skip
    Spende.objects.create(adresse=otto, datum=dt.date(2025, 2, 1), betrag=D("0"))


def test_rechnen(daten):
    assert ew.je_monat(2025)[:4] == [20.0, 0.0, 780.0, 100.0]
    assert ew.anzahl_je_monat(2025)[:4] == [1, 0, 2, 1]
    assert ew.laufend([1.0, 2.0, 3.0, 4.0], 3) == [1.0, 3.0, 6.0]
    grenzen = ("10", "10.01", "25", "25.01", "50", "50.01", "100", "500", "500.01")
    assert [ew.stufe(D(b)) for b in grenzen] == [
        "bis 10 €", "10,01 – 25 €", "10,01 – 25 €", "25,01 – 50 €", "25,01 – 50 €",
        "50,01 – 100 €", "50,01 – 100 €", "100,01 – 500 €", "über 500 €"]  # fmt: skip


def test_abschnitte(daten):
    verlauf = ew.abschnitt_verlauf(2025, HEUTE)
    assert verlauf["zeilen"] == [
        ["Jan", "20,00 €", "20,00 €"], ["Feb", "20,00 €", "20,00 €"],
        ["Mär", "800,00 €", "120,00 €"], ["Apr", "900,00 €", "120,00 €"],
    ]  # fmt: skip
    assert "Bis Ende Apr: 900,00 €; im Vorjahr bis dahin 120,00 €" in verlauf["text"]
    assert "im ganzen Vorjahr 170,00 €" in verlauf["text"] and "<svg" in verlauf["svg"]
    # ein abgeschlossenes Jahr: alle zwölf Monate, ohne Hinweis auf „bis Ende“
    assert len(ew.abschnitt_verlauf(2024, HEUTE)["zeilen"]) == 12
    monate = ew.abschnitt_monate(2025, HEUTE)
    assert monate["zeilen"][2] == ["Mär", "780,00 €", "100,00 €"] and "<svg" in monate["svg"]
    hoehe = ew.abschnitt_hoehe(2025)
    assert hoehe["zeilen"] == [
        ["bis 10 €", 0, "0,00 €"], ["10,01 – 25 €", 1, "20,00 €"],
        ["25,01 – 50 €", 1, "30,00 €"], ["50,01 – 100 €", 1, "100,00 €"],
        ["100,01 – 500 €", 0, "0,00 €"], ["über 500 €", 1, "750,00 €"],
    ]  # fmt: skip
    spender = ew.abschnitt_spender(2025)
    assert dict(spender["zeilen"]) == {"einmal gespendet": 2, "mehrfach gespendet": 1,
                                       "neu (im Vorjahr nicht dabei)": 1,
                                       "wieder dabei (auch im Vorjahr)": 2}  # fmt: skip
    jahre = ew.abschnitt_jahre()
    assert jahre["zeilen"] == [[2024, "170,00 €", 3, 2], [2025, "900,00 €", 4, 3]]
    k = ew.kennzahlen(2025, HEUTE)
    assert (k["summe"], k["anzahl"], k["spender"], k["schnitt"], k["vergleich"]) == (
        "900,00 €", 4, 3, "225,00 €", 650)  # fmt: skip


def test_ohne_spenden_keine_grafik():
    teile = ew.abschnitte(2025, HEUTE)
    assert all(t["svg"] == "" for t in teile)
    assert ew.kennzahlen(2025, HEUTE)["vergleich"] is None
    assert ew.kennzahlen(2025, HEUTE)["schnitt"] == "–"


def test_seite_csv_und_rechte(daten, admin_client, admin, benutzer_mit_rolle, anmelden, client):
    url = reverse("spenden:entwicklung")
    seite = admin_client.get(url, {"jahr": 2025}).content.decode()
    assert "Spendenentwicklung 2025" in seite and "Spendensumme im Jahresverlauf" in seite
    assert seite.count('class="karte statistik-abschnitt"') == 6 and "Zahlen als Tabelle" in seite
    assert url in admin_client.get(reverse("core:start")).content.decode()
    csv = admin_client.get(url, {"jahr": 2025, "csv": "hoehe"})
    assert csv["Content-Disposition"].endswith('spendenentwicklung-hoehe-2025.csv"')
    assert "über 500 €;1;750,00 €" in csv.content.decode("utf-8-sig")
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(url).status_code == 403
