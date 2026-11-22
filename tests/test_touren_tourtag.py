# ruff: noqa: F811 (Fixtures aus test_touren_zusatz)
"""Modul Touren: einen ganzen Tourtag zurücksetzen (ADR 0162). Alle Daten sind erfunden."""

from decimal import Decimal

import pytest
from django.urls import reverse

from apps.core import papierkorb
from apps.core.models import PapierkorbEintrag
from apps.touren import anfahrten, fahrten, lieferscheine, meldungen, tourtag, zusatz
from apps.touren.models import (
    Anfahrt,
    Fahrt,
    Fahrzeug,
    Fahrzeugmeldung,
    Lieferschein,
    Station,
    Tour,
    Zusatzstopp,
)
from tests.test_touren_lieferscheine import unterschrift
from tests.test_touren_zusatz import lage, module_an, station  # noqa: F401 (Fixtures)

pytestmark = pytest.mark.django_db


@pytest.fixture
def gefahren(lage):
    """Die Nordtour ist gefahren: Fahrt mit Kilometern, ein Lieferschein, eine Anfahrt, ein
    Zusatzstopp, eine Meldung zum Fahrzeug. Die Südtour hat einen eigenen Lieferschein."""
    nord, sued, fritz, heute = lage["nord"], lage["sued"], lage["fritz"], lage["heute"]
    wagen = Fahrzeug.objects.create(name="Kühlwagen", kilometerstand=5000)
    fahrt = fahrten.beginnen(nord, fritz, "5010", wagen.pk)
    eins, zwei = Station.objects.get(kennung="M-1"), Station.objects.get(kennung="M-2")
    bild = lieferscheine.unterschrift_lesen(unterschrift())
    lieferscheine.erstellen(eins, fritz, [("Obst/Gemüse", Decimal("4"), "kisten")], bild, "", nord)
    anfahrten.markieren(nord, zwei, fritz)
    zusatz.einfuegen(nord, heute, fritz, station(20, name="Hofladen"))
    meldungen.melden(fahrt, fritz, "mangel", "Lampe defekt")
    fahrten.beenden(fahrt, fritz, "5060")
    neun = Station.objects.get(kennung="M-9")
    zeilen = [("Obst/Gemüse", Decimal("2"), "kisten")]
    fremd = lieferscheine.erstellen(neun, lage["klaus"], zeilen, bild, "", sued)
    return {**lage, "wagen": wagen, "fremd": fremd}


def test_inhalt_und_zuruecksetzen(gefahren, admin):
    nord, heute, wagen = gefahren["nord"], gefahren["heute"], gefahren["wagen"]
    assert dict(tourtag.inhalt(nord, heute)) == {
        "Fahrt": 1, "Lieferschein": 1, "„Hier waren wir“": 1, "Zusatzstopp": 1,
        "Meldung zum Fahrzeug": 1,
    }  # fmt: skip
    weg = tourtag.zuruecksetzen(nord, heute, admin)
    assert dict(weg)["Lieferschein"] == 1 and tourtag.inhalt(nord, heute) == []
    assert not Fahrt.objects.exists() and not Anfahrt.objects.exists()
    assert not Zusatzstopp.objects.exists() and not Fahrzeugmeldung.objects.exists()
    # die andere Tour, die Tour selbst und ihre Stationen bleiben
    assert list(Lieferschein.objects.all()) == [gefahren["fremd"]]
    assert Tour.objects.filter(pk=nord.pk).exists() and nord.halte.count() == 3
    wagen.refresh_from_db()
    assert wagen.kilometerstand == 5000  # wie vor der Testtour
    # ein Eintrag im Papierkorb; von dort kommt alles gemeinsam zurück
    eintrag = PapierkorbEintrag.objects.get(art="Tourtag")
    assert "Nordtour" in eintrag.bezeichnung and eintrag.recht == "touren.lieferscheine"
    papierkorb.wiederherstellen(eintrag, admin)
    assert dict(tourtag.inhalt(nord, heute))["Fahrt"] == 1
    assert Lieferschein.objects.count() == 2 and Fahrzeugmeldung.objects.count() == 1
    assert tourtag.zuruecksetzen(gefahren["sued"], heute, admin)  # nur der Lieferschein
    assert tourtag.zuruecksetzen(gefahren["sued"], heute, admin) == []  # nichts mehr da


def test_statistik_stimmt_danach(gefahren, admin):
    from apps.touren import statistik

    jahr = gefahren["heute"].year
    vorher = statistik.kennzahlen(statistik.Daten(jahr))
    tourtag.zuruecksetzen(gefahren["nord"], gefahren["heute"], admin)
    assert statistik.kennzahlen(statistik.Daten(jahr)) != vorher


def test_knopf_und_rechte(client, anmelden, gefahren, admin, recht_geben):
    nord, heute = gefahren["nord"], gefahren["heute"]
    seite_url = reverse("touren:fahren", args=[nord.pk])
    ziel = reverse("touren:tourtag_zuruecksetzen", args=[nord.pk])
    # die Mannschaft sieht den Knopf nicht und darf es nicht
    anmelden(client, gefahren["fritz"])
    assert "Tourtag zurücksetzen" not in client.get(seite_url).content.decode()
    assert client.post(ziel, {"tag": heute.isoformat()}).status_code == 403
    # nur das Fahrtenbuch reicht nicht: Lieferscheine sind Belege
    recht_geben("Fahrer", "touren.fahrten")
    assert client.post(ziel, {"tag": heute.isoformat()}).status_code == 403
    assert Fahrt.objects.exists()
    # mit beiden Rechten: Der Knopf zeigt, was verschwindet
    anmelden(client, admin)
    seite = client.get(seite_url).content.decode()
    assert "Diesen Tourtag zurücksetzen" in seite and "1 × Lieferschein" in seite
    antwort = client.post(ziel, {"tag": heute.isoformat()}, follow=True)
    text = antwort.content.decode()
    assert "Zurückgesetzt und in den Papierkorb gelegt" in text and "1 × Fahrt" in text
    assert "Diesen Tourtag zurücksetzen" not in text  # nichts mehr da: kein Knopf
    assert not Fahrt.objects.exists()
    antwort = client.post(ziel, {"tag": "kein Datum"}, follow=True)
    assert "nichts eingetragen" in antwort.content.decode()
