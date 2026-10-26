import datetime as dt
from decimal import Decimal as D

import pytest
from django.urls import reverse

from apps.ausgabe import konto
from apps.ausgabe.models import AusgabeEinstellungen
from apps.core.feiertage import BUNDESLAENDER, feiertage, ist_feiertag, ostersonntag
from apps.core.models import TafelEinstellungen
from apps.kunden.models import Haushalt, Kundengruppe
from apps.personal import berechnung
from apps.personal.models import Arbeitsvertrag


@pytest.fixture
def land(db):
    def setzen(kuerzel):
        e = TafelEinstellungen.laden()
        e.bundesland = kuerzel
        e.save()

    return setzen


@pytest.mark.parametrize(
    "ostern",
    [dt.date(2000, 4, 23), dt.date(2024, 3, 31), dt.date(2025, 4, 20), dt.date(2026, 4, 5),
     dt.date(2027, 3, 28), dt.date(2038, 4, 25)],
)  # fmt: skip
def test_ostersonntag(ostern):
    assert ostersonntag(ostern.year) == ostern


@pytest.mark.parametrize(
    ("kuerzel", "anzahl"),
    [("BW", 12), ("BY", 12), ("BE", 10), ("BB", 12), ("HB", 10), ("HH", 10), ("HE", 10),
     ("MV", 11), ("NI", 10), ("NW", 11), ("RP", 11), ("SL", 12), ("SN", 11), ("ST", 11),
     ("SH", 10), ("TH", 11)],
)  # fmt: skip
def test_anzahl_je_bundesland_2026(kuerzel, anzahl):
    assert len(feiertage(2026, kuerzel)) == anzahl
    assert len(BUNDESLAENDER) == 16


def test_nordrhein_westfalen_2026():
    tage = feiertage(2026, "NW")
    assert tage[dt.date(2026, 4, 3)] == "Karfreitag"
    assert tage[dt.date(2026, 6, 4)] == "Fronleichnam"
    assert tage[dt.date(2026, 11, 1)] == "Allerheiligen"
    assert dt.date(2026, 10, 31) not in tage
    assert list(tage)[0] == dt.date(2026, 1, 1)  # sortiert


@pytest.mark.parametrize(
    ("kuerzel", "datum", "gilt"),
    [
        ("BE", dt.date(2018, 3, 8), False),
        ("BE", dt.date(2019, 3, 8), True),
        ("MV", dt.date(2022, 3, 8), False),
        ("MV", dt.date(2023, 3, 8), True),
        ("NI", dt.date(2016, 10, 31), False),
        ("NI", dt.date(2017, 10, 31), True),  # einmalig bundesweit
        ("NW", dt.date(2017, 10, 31), True),
        ("NI", dt.date(2018, 10, 31), True),
        ("TH", dt.date(2018, 9, 20), False),
        ("TH", dt.date(2019, 9, 20), True),
        ("SN", dt.date(2026, 11, 18), True),  # Buß- und Bettag
        ("SN", dt.date(2023, 11, 22), True),
        ("BB", dt.date(2026, 4, 5), True),  # Ostersonntag
        ("", dt.date(2026, 12, 25), False),  # ohne Bundesland keine Feiertage
    ],
)
def test_einzelne_feiertage(kuerzel, datum, gilt):
    assert ist_feiertag(datum, kuerzel) is gilt


# --- Wirkung auf Urlaub und Stundenkonto --------------------------------------------------


def test_werktage_ohne_feiertage(land):
    woche = (dt.date(2026, 6, 1), dt.date(2026, 6, 5))  # Fronleichnam am Donnerstag
    assert berechnung.werktage(*woche) == 5
    land("NW")
    assert berechnung.werktage(*woche) == 4
    assert berechnung.werktage(*woche, land="HB") == 5


@pytest.mark.django_db
def test_stundenkonto_ohne_feiertage(land, benutzer_mit_rolle):
    p = benutzer_mit_rolle("kim")
    Arbeitsvertrag.objects.create(benutzer=p, beginn=dt.date(2026, 6, 1), wochenstunden=D("40"))
    heute = dt.date(2026, 6, 5)
    assert berechnung.stundenkonto(p, 2026, heute).monate[0].soll == D("40")
    land("NW")
    assert berechnung.stundenkonto(p, 2026, heute).monate[0].soll == D("32")


@pytest.mark.django_db
def test_seite_nennt_bundesland(admin_client, land, benutzer_mit_rolle):
    p = benutzer_mit_rolle("kim")
    seite = reverse("personal:person", args=[p.pk])
    assert "Kein Bundesland eingestellt" in admin_client.get(seite).content.decode()
    land("NW")
    assert "Feiertage in Nordrhein-Westfalen" in admin_client.get(seite).content.decode()


# --- Wirkung auf den Vorschlag für Vorauszahlungen ----------------------------------------


@pytest.mark.django_db
def test_vorschlag_laesst_feiertage_aus(land):
    gruppe = Kundengruppe.objects.create(kuerzel="DF", name="Do+Fr", wochentage="Do,Fr")
    h = Haushalt.objects.create(kundennummer="1", kundengruppe=gruppe)
    e = AusgabeEinstellungen.laden()
    e.max_abholungen = 0
    heute = dt.date(2026, 12, 17)  # Donnerstag; 25.12.2026 ist ein Freitag
    rest = konto.vorschlaege(h, heute, e, D("1"))[0][0]
    assert len(rest.tage) == 5 and "kein Bundesland gewählt" in rest.erklaerung[-1]
    land("NW")
    rest = konto.vorschlaege(h, heute, e, D("1"))[0][0]
    assert dt.date(2026, 12, 25) not in rest.tage and len(rest.tage) == 4
    assert "Nicht gezählt, weil Feiertag: Fr 25.12. (1. Weihnachtstag)." in rest.erklaerung
    assert "Betriebsferien" in rest.erklaerung[-1]
