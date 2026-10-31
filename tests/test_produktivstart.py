"""Produktivstart: gewählte Testdaten löschen, Einrichtung behalten (ADR 0095)."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.antraege.models import Antrag
from apps.core import produktivstart as ps
from apps.konten import rollen
from apps.konten.models import Benutzer
from apps.kunden.models import Abholung, Ausgabestelle, Haushalt, Kundengruppe
from apps.mitglieder.models import Mitglied
from apps.spenden.models import Spende

pytestmark = pytest.mark.django_db

URL = reverse("core:produktivstart")
AUSFUEHREN = reverse("core:produktivstart_ausfuehren")
PASSWORT = "sehr-sicheres-passwort"
ALLE = ["kunden", "antraege", "verein", "module", "protokoll", "konten"]


def _testdaten():
    stelle = Ausgabestelle.objects.create(name="Mitte")
    gruppe = Kundengruppe.objects.create(kuerzel="X1", name="Gruppe", ausgabestelle=stelle)
    h = Haushalt.objects.create(kundennummer="1001")
    Abholung.objects.create(haushalt=h, datum=dt.date(2026, 1, 5))
    Antrag.objects.create(vorname="Erika", nachname="Test")
    a = Adresse.objects.create(art="person", nachname="Spender")
    Spende.objects.create(adresse=a, datum=dt.date(2026, 1, 5), betrag=Decimal("50"))
    Mitglied.objects.create(
        adresse=a, nummer="M1", art="Fördermitglied", eintritt=dt.date(2020, 1, 1)
    )
    return stelle, gruppe


def test_durchfuehren_loescht_gewaehltes_behaelt_einrichtung(admin, django_user_model):
    stelle, gruppe = _testdaten()
    anderer = django_user_model.objects.create_user(username="kollege", password="Sicher-genug-123")
    ps.durchfuehren(admin, ALLE)
    assert not Haushalt.objects.exists()
    assert not Abholung.objects.exists()
    assert not Antrag.objects.exists()
    assert not Spende.objects.exists()
    assert not Mitglied.objects.exists()
    assert not Adresse.objects.exists()
    # Einrichtung bleibt
    assert Ausgabestelle.objects.filter(pk=stelle.pk).exists()
    assert Kundengruppe.objects.filter(pk=gruppe.pk).exists()
    # Konten: nur der Admin bleibt
    assert list(Benutzer.objects.values_list("pk", flat=True)) == [admin.pk]
    assert not Benutzer.objects.filter(pk=anderer.pk).exists()


def test_nur_gewaehlter_bereich_wird_geleert(admin, django_user_model):
    """Nur „verein“ gewählt: Spenden/Mitglieder/Adressen weg, Kunden/Anträge/Konten bleiben."""
    _testdaten()
    anderer = django_user_model.objects.create_user(username="kollege", password="Sicher-genug-123")
    ps.durchfuehren(admin, {"verein"})
    assert not Spende.objects.exists() and not Mitglied.objects.exists()
    assert not Adresse.objects.exists()
    assert Haushalt.objects.exists() and Antrag.objects.exists()
    assert Benutzer.objects.filter(pk=anderer.pk).exists()  # Konten nicht gewählt


def test_ohne_auswahl_fehler(admin):
    _testdaten()
    with pytest.raises(ps.ProduktivstartFehler):
        ps.durchfuehren(admin, set())
    assert Haushalt.objects.exists()


def test_vorschau_zaehlt(admin):
    _testdaten()
    zahlen = {z["key"]: z["zahl"] for z in ps.vorschau(admin)}
    assert zahlen["kunden"] >= 2  # Haushalt + Abholung
    assert zahlen["verein"] >= 3  # Spende + Mitglied + Adresse


def test_seite_nur_mit_recht(admin_client, client, benutzer_mit_rolle, anmelden):
    assert admin_client.get(URL).status_code == 200
    konto = benutzer_mit_rolle("otto", rollen.AUSGABE)
    assert anmelden(client, konto).get(URL).status_code == 403


def test_ausfuehren_sichert_und_loescht(admin_client):
    stelle, _ = _testdaten()
    antwort = admin_client.post(
        AUSFUEHREN,
        {
            "passwort": PASSWORT,
            "passwort2": PASSWORT,
            "bestaetigung": "PRODUKTIVSTART",
            "bereiche": ALLE,
        },
    )
    assert antwort.status_code == 200
    assert antwort["Content-Disposition"].startswith("attachment")
    assert len(antwort.content) > 0  # die Sicherung
    assert not Haushalt.objects.exists()
    assert Ausgabestelle.objects.filter(pk=stelle.pk).exists()


def test_ausfuehren_ohne_bereiche_loescht_nichts(admin_client):
    _testdaten()
    antwort = admin_client.post(
        AUSFUEHREN,
        {"passwort": PASSWORT, "passwort2": PASSWORT, "bestaetigung": "PRODUKTIVSTART"},
    )
    assert antwort.status_code == 302
    assert Haushalt.objects.exists()


def test_ausfuehren_ohne_bestaetigung_loescht_nichts(admin_client):
    _testdaten()
    antwort = admin_client.post(
        AUSFUEHREN,
        {"passwort": PASSWORT, "passwort2": PASSWORT, "bestaetigung": "nein", "bereiche": ALLE},
    )
    assert antwort.status_code == 302
    assert Haushalt.objects.exists()
