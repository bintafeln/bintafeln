"""Einzugsgebiet: Anschrift im Antrag gegen PLZ und Orte prüfen."""

import pytest
from django.urls import reverse

from apps.antraege import gebiet
from apps.antraege.models import Antrag, AntragEinstellungen
from tests.test_antraege import FORMULAR, daten

Gebiet = AntragEinstellungen.Gebiet


def einstellungen(pruefen=Gebiet.HINWEIS, plz="", orte="", name=""):
    return AntragEinstellungen(gebiet_pruefen=pruefen, gebiet_plz=plz, gebiet_orte=orte,
                               gebiet_name=name)  # fmt: skip


def test_plz_bereiche_und_orte_lesen():
    assert gebiet.plz_bereiche("12000-12999, 13500;x 14100–14000 1a-2") == [
        (12000, 12999), (13500, 13500), (14000, 14100)]  # fmt: skip
    assert gebiet.orte(" Musterstadt ,\nBeispieldorf;;") == ["musterstadt", "beispieldorf"]


@pytest.mark.parametrize(
    ("plz", "ort", "erwartet"),
    [
        ("12345", "Musterstadt", True),
        ("12345", "musterstadt-Nord", True),
        ("12345", "Musterstadt (Ost)", True),
        ("12345", "Musterstädtchen", False),
        ("19999", "Musterstadt", False),
        ("", "Musterstadt", False),
        ("12a45", "Musterstadt", False),
        ("", "", None),
    ],
)
def test_passt_mit_plz_und_ort(plz, ort, erwartet):
    e = einstellungen(plz="12000-12999", orte="Musterstadt")
    assert gebiet.passt(e, plz, ort) is erwartet


def test_passt_nur_eine_liste_oder_keine():
    assert gebiet.passt(einstellungen(plz="12345"), "12345", "Irgendwo") is True
    assert gebiet.passt(einstellungen(orte="Musterstadt"), "99999", "Musterstadt") is True
    assert gebiet.passt(einstellungen(), "12345", "Musterstadt") is None
    aus = einstellungen(Gebiet.AUS, plz="1", orte="Musterstadt")
    assert gebiet.passt(aus, "99999", "Anderswo") is None


def test_name_des_gebiets():
    assert gebiet.name(einstellungen(name=" Musterstadt ", orte="A")) == "Musterstadt"
    assert gebiet.name(einstellungen(orte="A, B")) == "A, B"
    assert gebiet.name(einstellungen(plz="12000-12999")) == "12000-12999"


@pytest.fixture
def offen(admin):
    e = AntragEinstellungen.laden()
    e.aktiv = True
    e.gebiet_plz, e.gebiet_orte, e.gebiet_name = "12000-12999", "Musterstadt", "Musterstadt"
    e.save()
    return e


def test_sperren_lehnt_antrag_ab(client, offen):
    offen.gebiet_pruefen = Gebiet.SPERREN
    offen.save()
    antwort = client.post(FORMULAR, daten(plz="54321", ort="Anderswo"))
    text = antwort.content.decode()
    assert "nur Anträge von Menschen annehmen, die in Musterstadt wohnen" in text
    assert not Antrag.objects.exists()
    englisch = client.post(reverse("antrag:formular", args=["en"]), daten(plz="54321"))
    assert "people who live in Musterstadt" in englisch.content.decode()
    client.post(FORMULAR, daten())
    assert Antrag.objects.count() == 1


def test_hinweis_nimmt_an_und_markiert(client, admin_client, offen):
    offen.gebiet_pruefen = Gebiet.HINWEIS
    offen.save()
    client.post(FORMULAR, daten(plz="54321", ort="Anderswo"))
    client.post(FORMULAR, daten(vorname="Lina"))
    draussen = Antrag.objects.get(plz="54321")
    drinnen = Antrag.objects.get(vorname="Lina")
    liste = admin_client.get(reverse("antraege:liste")).content.decode()
    assert liste.count("außerhalb des Gebiets") == 1
    seite = admin_client.get(reverse("antraege:antrag", args=[draussen.pk])).content.decode()
    assert "außerhalb des Gebiets" in seite
    seite = admin_client.get(reverse("antraege:antrag", args=[drinnen.pk])).content.decode()
    assert "außerhalb des Gebiets" not in seite
    url = reverse("antraege:aufnahme_schritt", args=[draussen.pk, "kunde"])
    assert "nicht im Einzugsgebiet" in admin_client.get(url).content.decode()
    url = reverse("antraege:aufnahme_schritt", args=[drinnen.pk, "kunde"])
    assert "nicht im Einzugsgebiet" not in admin_client.get(url).content.decode()


def test_einstellungen_speichern(admin_client, offen):
    seite = admin_client.get(reverse("antraege:einstellungen")).content.decode()
    assert "Anschrift prüfen (Einzugsgebiet)" in seite and 'name="gebiet_plz"' in seite
