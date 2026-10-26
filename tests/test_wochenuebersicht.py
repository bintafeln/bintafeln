"""Modul Wochenübersicht (ADR 0054): Soll/Ist je Ausgabestelle und Tag, Selbstabholer, PDF."""

import datetime as dt
import re

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Abholung, Ausgabestelle, Haushalt, Kundengruppe, Person
from apps.wochenuebersicht import auswertung
from apps.wochenuebersicht.models import Selbstabholer, StellenReihenfolge

pytestmark = pytest.mark.django_db
STICHTAG = dt.date(2026, 10, 21)  # Mittwoch


def gruppe(name, stelle, tage, maximum=None):
    return Kundengruppe.objects.create(name=name, ausgabestelle=stelle, wochentage=tage,
                                       maximum=maximum)  # fmt: skip


def haushalt(nummer, g, kinder=0, erwachsene=1, status=Haushalt.Status.AKTIV):
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=g, status=status)
    for i in range(erwachsene):
        Person.objects.create(haushalt=h, ist_hauptperson=i == 0, vorname="Erika",
                              nachname=f"Muster{i}", geburtsdatum=dt.date(1980, 1, 1))  # fmt: skip
    for i in range(kinder):
        Person.objects.create(haushalt=h, vorname="Kim", nachname=f"Muster{i}",
                              geburtsdatum=dt.date(2020, 1, 1))  # fmt: skip
    return h


@pytest.fixture
def daten():
    zentrale = Ausgabestelle.objects.create(name="Zentrale")
    nord = Ausgabestelle.objects.create(name="Nord")
    z1 = gruppe("Zentrale Mi 12:30", zentrale, "Mi", 10)
    z2 = gruppe("Zentrale Mi 13:00", zentrale, "Mi", 8)
    n = gruppe("Nord Mo/Do", nord, "Mo, Do")  # ohne Maximum, an zwei Tagen
    frei = gruppe("Sondergruppe", None, "Mi", 5)
    gruppe("Alt", zentrale, "Mi", 99).__class__.objects.filter(name="Alt").update(aktiv=False)
    haushalt("1", z1, kinder=2)
    haushalt("2", z1)
    haushalt("3", z2, erwachsene=2, kinder=1)
    haushalt("4", z2, status=Haushalt.Status.BEENDET)
    haushalt("5", n, kinder=1)
    haushalt("6", frei)
    return zentrale, nord


def test_soll_ist_je_tag(daten):
    d = auswertung.uebersicht(STICHTAG)
    tage = {t.kurz: t for t in d["tage"]}
    assert list(tage) == ["Mo", "Di", "Mi", "Do", "Fr"]  # Sa/So nur, wenn belegt
    mi = tage["Mi"]
    assert [z.name for z in mi.zeilen] == ["Zentrale", "Sondergruppe"]
    zentrale = mi.zeilen[0]
    assert (zentrale.soll, zentrale.haushalte, zentrale.erwachsene, zentrale.kinder) == (
        18,
        3,
        4,
        3,
    )
    assert zentrale.personen == 7 and zentrale.gruppen == ["Zentrale Mi 12:30", "Zentrale Mi 13:00"]
    assert (mi.summe.soll, mi.summe.haushalte, mi.summe.personen) == (23, 4, 8)
    # Nord zählt an beiden Tagen, ohne Maximum bleibt Soll leer
    for kurz in ("Mo", "Do"):
        nord = tage[kurz].zeilen[0]
        assert (nord.name, nord.soll, nord.haushalte, nord.kinder) == ("Nord", None, 1, 1)
    assert tage["Di"].zeilen == [] and tage["Di"].summe.soll is None
    assert d["gesamt"].personen == 8 + 2 + 2
    assert d["alle_personen"] == 12 and d["woche"] is None


def test_selbstabholer_und_samstag(daten):
    Selbstabholer.objects.create(name="Frauenhaus", tage="Mi, Sa", personen=12)
    Selbstabholer.objects.create(name="Alt", tage="Mi", personen=99, aktiv=False)
    d = auswertung.uebersicht(STICHTAG)
    tage = {t.kurz: t for t in d["tage"]}
    assert "Sa" in tage and "So" not in tage
    assert tage["Mi"].selbst_personen == 12 and tage["Mi"].summe.personen == 8
    assert d["selbst_gesamt"] == 24 and d["alle_personen"] == 12 + 24


def test_reihenfolge(daten):
    zentrale, nord = daten
    gruppe("Nord Mi", nord, "Mi")
    mi = next(t for t in auswertung.uebersicht(STICHTAG)["tage"] if t.kurz == "Mi")
    assert [z.name for z in mi.zeilen] == ["Nord", "Zentrale", "Sondergruppe"]
    StellenReihenfolge.objects.create(ausgabestelle=zentrale, reihenfolge=1)
    mi = next(t for t in auswertung.uebersicht(STICHTAG)["tage"] if t.kurz == "Mi")
    assert [z.name for z in mi.zeilen] == ["Zentrale", "Nord", "Sondergruppe"]


def test_abholungen_der_woche(daten):
    zentrale, nord = daten
    woche = auswertung.montag(STICHTAG)
    h1, h2 = Haushalt.objects.get(kundennummer="1"), Haushalt.objects.get(kundennummer="2")
    Abholung.objects.create(haushalt=h1, datum=STICHTAG, ausgabestelle=zentrale)
    Abholung.objects.create(haushalt=h2, datum=STICHTAG, ausgabestelle=zentrale)
    Abholung.objects.create(haushalt=h1, datum=STICHTAG - dt.timedelta(days=7),
                            ausgabestelle=zentrale)  # fmt: skip
    Abholung.objects.create(haushalt=h2, datum=STICHTAG)  # ohne Ausgabestelle: zählt nicht
    d = auswertung.uebersicht(STICHTAG, woche)
    mi = next(t for t in d["tage"] if t.kurz == "Mi")
    assert mi.zeilen[0].abgeholt == 2 and mi.zeilen[1].abgeholt is None
    assert mi.summe.abgeholt == 2 and d["gesamt"].abgeholt == 2
    mo = next(t for t in d["tage"] if t.kurz == "Mo")
    assert mo.zeilen[0].abgeholt == 0


@pytest.fixture
def modul_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["wochenuebersicht"]
    t.save()


def test_seiten_und_pdf(modul_an, admin_client, daten, pdf_text):
    seite = admin_client.get(reverse("wochenuebersicht:uebersicht")).content.decode()
    assert "Wochenübersicht der Ausgabestellen" in seite and "Zentrale" in seite
    assert "Abgeholt" not in seite
    seite = admin_client.get(reverse("wochenuebersicht:uebersicht"),
                             {"abholungen": "1", "kw": "2026-W43"}).content.decode()  # fmt: skip
    assert "Abgeholt" in seite and "KW 43" in seite
    seite = admin_client.get(reverse("wochenuebersicht:uebersicht"),
                             {"abholungen": "1", "kw": "kaputt"})  # fmt: skip
    assert seite.status_code == 200
    hoch = pdf_text(admin_client.get(reverse("wochenuebersicht:pdf", args=["hoch"]),
                                     {"abholungen": "1", "kw": "2026-W43"}))  # fmt: skip
    assert "Mittwoch" in hoch and "GESAMT ALLE PERSONEN" in hoch and "Abgeholt" in hoch
    Selbstabholer.objects.create(name="Frauenhaus", tage="Mi", personen=12)
    quer = pdf_text(admin_client.get(reverse("wochenuebersicht:pdf", args=["quer"])))
    assert "Verteilstelle" in quer and "Selbstabholer: Frauenhaus" in quer
    assert "Alle Personen 24" in quer
    hoch = pdf_text(admin_client.get(reverse("wochenuebersicht:pdf", args=["hoch"])))
    assert "Selbstabholer: Frauenhaus" in hoch and "(+12)" in hoch


def test_selbstabholer_pflegen(modul_an, admin_client):
    antwort = admin_client.post(reverse("wochenuebersicht:selbstabholer_neu"), {
        "name": "Frauenhaus", "tage": ["Mo", "Mi"], "personen": 12, "aktiv": "on", "notiz": "",
    })  # fmt: skip
    assert antwort.status_code == 302
    s = Selbstabholer.objects.get()
    assert s.tage == "Mo, Mi" and s.tage_liste == ["Mo", "Mi"]
    seite = admin_client.get(reverse("wochenuebersicht:selbstabholer_bearbeiten", args=[s.pk]))
    assert re.search(r'value="Mi"[^>]*checked', seite.content.decode())
    assert (
        "Frauenhaus" in admin_client.get(reverse("wochenuebersicht:selbstabholer")).content.decode()
    )
    admin_client.post(reverse("wochenuebersicht:selbstabholer_loeschen", args=[s.pk]))
    assert not Selbstabholer.objects.exists()


def test_reihenfolge_pflegen(modul_an, admin_client, daten):
    zentrale, nord = daten
    admin_client.post(reverse("wochenuebersicht:reihenfolge"),
                      {f"r_{zentrale.pk}": "5", f"r_{nord.pk}": "x"})  # fmt: skip
    assert StellenReihenfolge.objects.get(ausgabestelle=zentrale).reihenfolge == 5
    assert not StellenReihenfolge.objects.filter(ausgabestelle=nord).exists()
    seite = admin_client.get(reverse("wochenuebersicht:reihenfolge")).content.decode()
    inhalt = seite[seite.index("<main") :]  # oben im Menü stehen die Stellen nach Namen
    assert inhalt.index("Zentrale") < inhalt.index("Nord")


def test_rechte_und_modulschalter(admin, benutzer_mit_rolle, anmelden, daten):
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    url = reverse("wochenuebersicht:uebersicht")
    assert c.get(url).status_code == 404  # Modul aus
    TafelEinstellungen.objects.update(module=["wochenuebersicht"])
    assert c.get(url).status_code == 403
    b = anmelden(Client(), benutzer_mit_rolle("berta", rollen.BUERO))
    assert b.get(url).status_code == 200
    assert "Soll und Ist je Tag" in b.get(reverse("core:start")).content.decode()
