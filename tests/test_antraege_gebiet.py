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


class _Fake:
    def __init__(self, plz, ort):
        self.plz, self.ort = plz, ort


def test_grund_nennt_was_ausserhalb_liegt():
    e = einstellungen(plz="12000-12999", orte="Musterstadt")
    assert gebiet.grund(e, _Fake("12345", "Musterstadt")) == ""
    assert gebiet.grund(e, _Fake("54321", "Musterstadt")) == "PLZ außerhalb des Gebiets"
    # Nur den Ort korrigiert übrig: nach PLZ-Korrektur bleibt der Ort als Grund (der gemeldete Bug)
    assert gebiet.grund(e, _Fake("12345", "Anderswo")) == "Ort außerhalb des Gebiets"
    assert gebiet.grund(e, _Fake("54321", "Anderswo")) == "PLZ und Ort außerhalb des Gebiets"
    # Nur eine Liste konfiguriert
    assert gebiet.grund(einstellungen(plz="12000-12999"), _Fake("54321", "x")) \
        == "PLZ außerhalb des Gebiets"
    assert gebiet.grund(einstellungen(orte="Musterstadt"), _Fake("54321", "x")) \
        == "Ort außerhalb des Gebiets"
    assert gebiet.grund(einstellungen(), _Fake("54321", "x")) == ""


def test_korrektur_entfernt_markierung(admin_client, offen):
    """Nach dem Korrigieren der PLZ verschwindet die Markierung bzw. nennt den Rest-Grund."""
    offen.gebiet_pruefen, offen.gebiet_orte = Gebiet.HINWEIS, ""  # nur PLZ prüfen
    offen.save()
    a = Antrag.objects.create(vorname="Kai", nachname="Muster", plz="54321", ort="Anderswo")
    detail = reverse("antraege:antrag", args=[a.pk])
    assert "PLZ außerhalb des Gebiets" in admin_client.get(detail).content.decode()
    a.plz = "12345"  # in den Bereich korrigiert
    a.save()
    assert "außerhalb des Gebiets" not in admin_client.get(detail).content.decode()


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
