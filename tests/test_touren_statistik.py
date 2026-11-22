"""Modul Touren: Statistik aus Lieferscheinen und Fahrtenbuch (ADR 0157).
Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TafelEinstellungen
from apps.touren import lieferscheine, statistik
from apps.touren.models import Fahrt, Fahrzeug, Station, Tour, TourenEinstellungen, Warengruppe
from tests.test_touren_lieferscheine import unterschrift

pytestmark = pytest.mark.django_db
JAHR = 2026


@pytest.fixture(autouse=True)
def module_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["touren"]
    t.save()


def station(nr, **mehr):
    daten = {"kennung": f"M-{nr}", "art": "markt", "name": f"Markt {nr}", "strasse": "Musterweg",
             "hausnummer": str(nr), "plz": "12345", "ort": "Musterstadt", "lieferschein": True,
             **mehr}  # fmt: skip
    return Station.objects.create(**daten)


def schein(admin, wo, tour, tag, *positionen):
    zeichnung = lieferscheine.unterschrift_lesen(unterschrift())
    return lieferscheine.erstellen(wo, admin, list(positionen), zeichnung, "", tour, tag)


def fahrt(tour, tag, km, wagen, stunden=3.0, am_handy=True):
    beginn = timezone.make_aware(dt.datetime.combine(tag, dt.time(8, 0)))
    return Fahrt.objects.create(
        tour=tour, tour_name=tour.name, datum=tag, fahrzeug=wagen, fahrzeug_name=str(wagen),
        km_start=1000, km_ende=1000 + km, begonnen_am=beginn,
        beendet_am=beginn + dt.timedelta(hours=stunden),
        beendet_von_name="fritz" if am_handy else "")  # fmt: skip


@pytest.fixture
def lage(admin):
    """Zwei Touren, zwei Stationen (eine mit Kette), Lieferscheine in März und April und im
    Vorjahr; Kisten wiegen allgemein 10 kg, Backwaren 4 kg."""
    Warengruppe.objects.filter(name="Backwaren").update(kiste_kg=Decimal("4"))
    a, b = station(1, kette="Beispielkette"), station(2)
    station(3, name="Nie besucht")
    station(4, name="Ohne Schein", lieferschein=False)
    nord, sued = Tour.objects.create(name="Nordtour"), Tour.objects.create(name="Südtour")
    wagen = Fahrzeug.objects.create(name="Kühlwagen")
    schein(admin, a, nord, dt.date(JAHR, 3, 2), ("Obst/Gemüse", Decimal("5"), "kisten"),
           ("Backwaren", Decimal("10"), "kisten"))  # fmt: skip
    schein(admin, b, nord, dt.date(JAHR, 3, 9), ("Obst/Gemüse", Decimal("25.5"), "kg"))
    schein(admin, a, sued, dt.date(JAHR, 4, 1), ("Backwaren", Decimal("2"), "kisten"))
    schein(admin, a, nord, dt.date(JAHR - 1, 3, 5), ("Obst/Gemüse", Decimal("4"), "kisten"))
    fahrt(nord, dt.date(JAHR, 3, 2), 62, wagen)
    fahrt(nord, dt.date(JAHR, 3, 9), 58, wagen, stunden=2.5)
    fahrt(sued, dt.date(JAHR, 4, 1), 40, wagen, am_handy=False)  # im Büro nachgetragen
    return {"a": a, "b": b, "nord": nord, "sued": sued, "wagen": wagen}


def abschnitt(daten, kennung):
    return next(a for a in statistik.abschnitte(daten) if a["id"] == kennung)


def test_kisten_werden_in_kg_umgerechnet(lage):
    d = statistik.Daten(JAHR)
    # März: 5 Kisten Obst × 10 kg + 10 Kisten Backwaren × 4 kg + 25,5 kg gewogen = 115,5 kg
    assert d.monat[3]["kg"] == Decimal("115.5") and d.monat[3]["kisten"] == 15
    assert d.monat[3]["gewogen"] == Decimal("25.5") and len(d.monat[3]["scheine"]) == 2
    assert d.monat[4]["kg"] == 8 and d.vorjahr_kg[3] == 40
    k = statistik.kennzahlen(d)
    assert (k["kg"], k["kisten"], k["scheine"], k["stationen"]) == ("124", "17", 3, 2)
    assert (k["fahrten"], k["km"], k["stunden"]) == (3, "160", "6")  # 3 h + 2,5 h am Handy
    assert k["vergleich"] == 209  # 123,5 kg gegenüber 40 kg im Vorjahr
    # allgemeines Gewicht geändert: nur die Gruppen ohne eigenen Wert folgen
    e = TourenEinstellungen.laden()
    e.kiste_kg = Decimal("20")
    e.save()
    assert statistik.Daten(JAHR).monat[3]["kg"] == Decimal("165.5")


def test_abschnitte(lage):
    d = statistik.Daten(JAHR)
    mengen = abschnitt(d, "mengen")
    assert mengen["kopf"][-1] == f"kg {JAHR - 1}" and "<svg" in mengen["svg"]
    assert mengen["zeilen"][2] == ["Mär", 2, "15", "25,5", "116", "40"]
    gruppen = abschnitt(d, "warengruppen")["zeilen"]
    assert [z[0] for z in gruppen] == ["Obst/Gemüse", "Backwaren"]
    assert gruppen[1] == ["Backwaren", 2, "12", "0", "48"]
    touren = abschnitt(d, "touren")
    assert touren["kopf"] == ["Tour", "Fahrten", "km", "Stunden", "Lieferscheine", "kg gesamt"]
    assert touren["zeilen"] == [["Nordtour", 2, "120", "5,5", 2, "116"],
                                ["Südtour", 1, "40", "0,0", 1, "8"]]  # fmt: skip
    assert abschnitt(d, "fahrten")["zeilen"][3] == ["Apr", 1, "40", "0,0"]
    assert abschnitt(d, "fahrzeuge")["zeilen"] == [["Kühlwagen", 3, "160"]]
    assert [z[0] for z in abschnitt(d, "stationen")["zeilen"]] == ["Markt 1", "Markt 2"]
    ketten = {z[0]: z[-1] for z in abschnitt(d, "ketten")["zeilen"]}
    assert ketten == {"Beispielkette": "98", "ohne Angabe": "26"}
    ohne = abschnitt(d, "ohne")
    assert [z[0] for z in ohne["zeilen"]] == ["Nie besucht"] and ohne["svg"] == ""
    # keine Auswertung je Person: kein Abschnitt und keine Spalte nennt jemanden
    alles = str(statistik.abschnitte(d)) + str(statistik.kennzahlen(d))
    assert "fritz" not in alles and "chefin" not in alles
    assert not any("fahrer" in a["id"] or "person" in a["id"] for a in statistik.abschnitte(d))


def test_leeres_jahr():
    d = statistik.Daten(2019)
    assert statistik.kennzahlen(d)["vergleich"] is None and statistik.kennzahlen(d)["kg"] == "0"
    for a in statistik.abschnitte(d):
        assert a["svg"] == "" and a["zeilen"] == [], a["id"]


def test_seite_csv_und_rechte(client, anmelden, benutzer_mit_rolle, lage):
    anmelden(client, benutzer_mit_rolle("bernd", "Büro"))
    adresse = reverse("touren:statistik")
    seite = client.get(adresse, {"jahr": JAHR}).content.decode()
    assert f"Statistik der Touren {JAHR}" in seite and "124 kg" in seite and "160 km" in seite
    assert "Menge je Warengruppe" in seite and "je Person gibt es bewusst nicht" in seite
    assert f'<option value="{JAHR - 1}"' in seite  # Jahre mit Daten stehen zur Wahl
    datei = client.get(adresse, {"jahr": JAHR, "csv": "touren"})
    assert datei["Content-Type"].startswith("text/csv")
    text = datei.content.decode("utf-8-sig")
    assert "Tour;Fahrten;km;Stunden;Lieferscheine;kg gesamt" in text
    assert "Nordtour;2;120;5,5;2;116" in text
    # unbekanntes Jahr: das laufende
    heute = timezone.localdate().year
    assert f"Statistik der Touren {heute}" in client.get(adresse, {"jahr": "1999"}).content.decode()
    client.logout()
    anmelden(client, benutzer_mit_rolle("fritz", "Fahrer"))
    assert client.get(adresse).status_code == 403


def test_kg_je_kiste_einrichten(admin_client):
    seite = admin_client.get(reverse("touren:einrichten")).content.decode()
    assert "Durchschnittsgewicht einer Kiste" in seite and "kg je Kiste" in seite
    admin_client.post(reverse("touren:einrichten"), {
        "einrichten": "1", "mail_text": "Hallo", "zentrale": "", "kiste_kg": "8,5"})  # fmt: skip
    assert TourenEinstellungen.laden().kiste_kg == Decimal("8.5")
