"""Abholungen nachtragen (ADR 0091)."""

import datetime as dt
from decimal import Decimal as D

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe import kasse
from apps.ausgabe.models import Buchung
from apps.kunden.models import Abholung, Ausgabestelle, Haushalt, Kundengruppe, Person

pytestmark = pytest.mark.django_db

SEITE = reverse("ausgabe:nachtragen")
HEUTE = timezone.localdate()
GESTERN = HEUTE - dt.timedelta(days=1)
ALLE_TAGE = "Mo Di Mi Do Fr Sa So"


@pytest.fixture
def tafel():
    """Erfundene Ausgabestelle mit einer Gruppe, die jeden Tag dran ist, und drei Haushalten."""
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    g = Kundengruppe.objects.create(name="A", ausgabestelle=mitte, wochentage=ALLE_TAGE)
    gueltig = HEUTE + dt.timedelta(days=200)
    haushalte = {}
    for nummer, ausweis in (("00001", gueltig), ("00002", gueltig),
                            ("00003", HEUTE - dt.timedelta(days=30))):  # fmt: skip
        h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=g,
                                    ausweis_gueltig_bis=ausweis)  # fmt: skip
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Eva", nachname="Probe")
        haushalte[nummer] = h
    return mitte, nord, haushalte


@pytest.fixture
def ausgabe(client, admin, benutzer_mit_rolle, anmelden):
    return anmelden(client, benutzer_mit_rolle("theke", "Ausgabe"))


@pytest.fixture
def chefin(client, admin, anmelden):
    return anmelden(client, admin)


def test_liste_des_tages_mit_beitrag_und_rot(chefin, tafel):
    mitte, _, _ = tafel
    antwort = chefin.get(SEITE, {"datum": HEUTE.isoformat(), "stelle": mitte.pk})
    text = antwort.content.decode()
    assert antwort.status_code == 200
    assert "00001" in text and "00003" in text
    assert 'name="betrag_00001" value="1,50"' in text and "Probe, Eva" in text
    assert "Ausweis abgelaufen" in text
    # Die Kundennummer ist zum Kunden verlinkt (mit Recht kunden.ansehen)
    assert f'href="{reverse("kunden:haushalt", args=["00001"])}"' in text


def test_angehakte_nachtragen_mit_eigenem_betrag(chefin, tafel):
    mitte, _, hh = tafel
    antwort = chefin.post(SEITE, {
        "datum": GESTERN.isoformat(), "stelle": mitte.pk, "nummer": ["00001", "00002"],
        "betrag_00001": "1,50", "betrag_00002": "0",
    }, follow=True)  # fmt: skip
    assert "2 Abholungen am" in antwort.content.decode()
    a = Abholung.objects.get(haushalt=hh["00001"])
    assert a.datum == GESTERN and a.nachgetragen and a.ausgabestelle == mitte and a.uhrzeit is None
    assert Abholung.objects.get(haushalt=hh["00002"]).beitrag == D("0")
    s = kasse.summe(Buchung.objects.filter(datum=GESTERN, ausgabestelle=mitte))
    assert s["abholungen"] == 1 and s["beitraege_bar"] == D("1.50")
    hh["00001"].refresh_from_db()
    assert hh["00001"].letzter_besuch == GESTERN and hh["00001"].kontostand == D("0")
    # noch einmal abgeschickt: nichts doppelt
    chefin.post(SEITE, {"datum": GESTERN.isoformat(), "stelle": mitte.pk, "nummer": ["00001"]})
    assert Abholung.objects.filter(haushalt=hh["00001"]).count() == 1
    text = chefin.get(SEITE, {"datum": GESTERN.isoformat(), "stelle": mitte.pk}).content.decode()
    assert "schon eingetragen (nachgetragen)" in text


def test_einzeln_nachtragen_ohne_betrag_nimmt_beitrag(chefin, tafel):
    _, nord, hh = tafel
    chefin.post(SEITE, {"datum": HEUTE.isoformat(), "stelle": nord.pk, "einzeln": "1",
                        "kundennummer": "00002", "betrag": ""})  # fmt: skip
    a = Abholung.objects.get(haushalt=hh["00002"])
    assert a.beitrag == D("1.50") and a.ausgabestelle == nord
    antwort = chefin.post(SEITE, {"datum": HEUTE.isoformat(), "stelle": nord.pk, "einzeln": "1",
                                  "kundennummer": "99999"}, follow=True)  # fmt: skip
    assert "keinen Kunden mit dieser Nummer" in antwort.content.decode()


def test_admin_darf_alte_tage_und_rot(chefin, tafel):
    mitte, _, hh = tafel
    vor_monat = HEUTE - dt.timedelta(days=40)
    chefin.post(SEITE, {"datum": vor_monat.isoformat(), "stelle": mitte.pk,
                        "nummer": ["00003"], "betrag_00003": "2"})  # fmt: skip
    assert Abholung.objects.get(haushalt=hh["00003"]).datum == vor_monat


def test_ausgabe_nur_heute_und_gestern_und_nicht_rot(ausgabe, tafel):
    mitte, _, hh = tafel
    alt = (HEUTE - dt.timedelta(days=2)).isoformat()
    assert "ältere Tage" in ausgabe.get(SEITE, {"datum": alt, "stelle": mitte.pk}).content.decode()
    ausgabe.post(SEITE, {"datum": alt, "stelle": mitte.pk, "nummer": ["00001"]})
    assert not Abholung.objects.exists()
    text = ausgabe.get(SEITE, {"datum": GESTERN.isoformat(), "stelle": mitte.pk}).content.decode()
    assert 'value="00003" aria-label="00003 nachtragen" disabled' in text
    antwort = ausgabe.post(SEITE, {"datum": GESTERN.isoformat(), "stelle": mitte.pk,
                                   "nummer": ["00001", "00003"]}, follow=True)  # fmt: skip
    assert "trägt ein Admin" in antwort.content.decode()
    assert list(Abholung.objects.values_list("haushalt__kundennummer", flat=True)) == ["00001"]
    morgen = (HEUTE + dt.timedelta(days=1)).isoformat()
    ausgabe.post(SEITE, {"datum": morgen, "stelle": mitte.pk, "einzeln": "1",
                         "kundennummer": "00002"})  # fmt: skip
    assert Abholung.objects.count() == 1


def test_nur_mit_recht(client, admin, benutzer_mit_rolle, anmelden, tafel):
    c = anmelden(client, benutzer_mit_rolle("kiosk", "Kiosk"), zwei_faktor=False)
    assert c.get(SEITE).status_code == 403
