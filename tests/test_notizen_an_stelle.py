"""Notizen der Verwaltung an die Ausgabestelle, z. B. nach dem Ausweisdruck (erfundene Daten)."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.konten import rollen
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    Kundengruppe,
    Nachricht,
    Notiz,
    NotizVorlage,
)

pytestmark = pytest.mark.django_db
START = reverse("core:start")


@pytest.fixture
def mitte():
    return Ausgabestelle.objects.create(name="Mitte")


@pytest.fixture
def zentrale():
    return Ausgabestelle.objects.create(name="Zentrale", ausweise_hier=True)


def haushalt(nummer, stelle):
    gruppe, _ = Kundengruppe.objects.get_or_create(name=f"Gruppe {stelle}", ausgabestelle=stelle)
    return Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe)


@pytest.fixture
def ausgabe(mitte, benutzer_mit_rolle, anmelden):
    konto = benutzer_mit_rolle("anton", rollen.AUSGABE)
    konto.ausgabestellen.set([mitte])
    return anmelden(Client(), konto)


def test_ausweis_drucken_beantwortet_die_meldung(admin_client, ausgabe, mitte, zentrale):
    h = haushalt("501", mitte)
    z = haushalt("502", zentrale)
    vorlage = NotizVorlage.objects.get(melden="ausweis")  # feste Vorlage aus der Migration
    # Die Ausgabestelle meldet mit dem Notiz-Knopf „Neuen Ausweis drucken“
    ausgabe.post(reverse("ausgabe:notiz", args=["501"]), {"text": vorlage.text})
    assert Nachricht.objects.filter(kundennummer="501", anliegen="ausweis").exists()
    Nachricht.objects.create(kundennummer="502", anliegen="ausweis")
    # Ohne Meldung passiert beim Druck nichts
    haushalt("503", mitte)
    admin_client.get(reverse("kunden:ausweis", args=["503"]))
    assert not Notiz.objects.filter(an_stelle=True).exists()
    # Druck: Notiz an die Ausgabestelle, Meldung erledigt, gemeldete Notiz gestrichen
    admin_client.get(reverse("kunden:ausweis", args=["501"]))
    antwort = Notiz.objects.get(kundennummer="501")
    assert antwort.an_stelle and antwort.text == (
        "Neuer Ausweis ist gedruckt und wird zur Ausgabestelle geschickt."
    )
    assert not Nachricht.objects.filter(kundennummer="501", erledigt_am__isnull=True).exists()
    # Zweiter Druck: keine zweite Antwort
    admin_client.get(reverse("kunden:ausweis", args=["501"]))
    assert Notiz.objects.filter(kundennummer="501").count() == 1
    # Sammeldruck, Zentrale: „liegt im Schrank“
    admin_client.get(reverse("kunden:ausweise"))
    assert Notiz.objects.get(kundennummer="502").text == (
        "Neuer Ausweis ist gedruckt und liegt im Schrank."
    )
    assert h and z


def test_startseite_und_gelesen(admin_client, ausgabe, mitte):
    haushalt("601", mitte)
    haushalt("602", mitte)
    andere = haushalt("701", Ausgabestelle.objects.create(name="Nord"))
    seite = ausgabe.get(START).content.decode()
    assert "Notiz der Verwaltung" not in seite
    # Ohne Haken: nur eine Notiz am Haushalt, nichts auf der Startseite
    admin_client.post(reverse("kunden:notiz_neu", args=["601"]), {"text": "Nur intern"})
    assert "Nur intern" not in ausgabe.get(START).content.decode()
    # Mit Haken: eine Notiz steht ganz auf der Startseite
    admin_client.post(reverse("kunden:notiz_neu", args=["601"]),
                      {"text": "Bitte Bescheid mitbringen", "an_stelle": "1"})  # fmt: skip
    seite = ausgabe.get(START).content.decode()
    assert "Notiz der Verwaltung" in seite and "Bitte Bescheid mitbringen" in seite
    # Mehrere: Link zur Sammelseite
    admin_client.post(reverse("kunden:notiz_neu", args=["602"]),
                      {"text": "Neue Anschrift eingetragen", "an_stelle": "1"})  # fmt: skip
    admin_client.post(reverse("kunden:notiz_neu", args=[andere.kundennummer]),
                      {"text": "Für Nord", "an_stelle": "1"})  # fmt: skip
    seite = ausgabe.get(START).content.decode()
    assert "2 neue Notizen der Verwaltung" in seite
    sammel = ausgabe.get(reverse("kunden:notizen_an_stelle")).content.decode()
    assert "Bitte Bescheid mitbringen" in sammel and "Für Nord" not in sammel
    # „gelesen“ nimmt sie von der Startseite; fremde Ausgabestellen können nichts abhaken
    n = Notiz.objects.get(text="Bitte Bescheid mitbringen")
    ausgabe.post(reverse("kunden:notiz_gelesen", args=[n.pk]), {"zurueck": "https://boese.example"})
    n.refresh_from_db()
    assert n.gelesen_am and n.gelesen_von == "anton"
    nord = Notiz.objects.get(text="Für Nord")
    assert ausgabe.post(reverse("kunden:notiz_gelesen", args=[nord.pk])).status_code == 404
    seite = ausgabe.get(START).content.decode()
    assert "Neue Anschrift eingetragen" in seite and "Bitte Bescheid mitbringen" not in seite
    # Am Haushalt steht, ob gelesen
    seite = admin_client.get(reverse("kunden:haushalt", args=["601"])).content.decode()
    assert "An die Ausgabestelle · gelesen" in seite


def test_sammelseite_ohne_stelle(admin_client, mitte):
    Ausgabestelle.objects.create(name="Nord")
    seite = admin_client.get(reverse("kunden:notizen_an_stelle")).content.decode()
    assert "Ausgabestelle wählen" in seite


def test_verwaltung_antwortet_auf_nachricht(admin_client, ausgabe, mitte):
    """Antwort auf eine Nachricht: an die schreibende Ausgabestelle, auch bei fremden Kunden."""
    fremd = haushalt("801", Ausgabestelle.objects.create(name="Nord"))
    n = Nachricht.objects.create(kundennummer=fremd.kundennummer, anliegen="adresse",
                                 stelle=mitte, von="anton", text="Neue Anschrift?")  # fmt: skip
    seite = admin_client.get(reverse("kunden:nachrichten")).content.decode()
    assert "Antwort an Mitte" in seite
    admin_client.post(
        reverse("kunden:nachrichten"), {"nachricht": n.pk, "antwort": "Ist erledigt."}
    )
    n.refresh_from_db()
    assert n.erledigt_am is not None
    notiz = Notiz.objects.get(kundennummer="801")
    assert notiz.text == "Antwort zu „Neue Anschrift oder Telefon“: Ist erledigt."
    assert notiz.an_stelle and notiz.fuer_stelle == mitte
    assert "Ist erledigt." in ausgabe.get(START).content.decode()  # bei Mitte, nicht bei Nord
    # Ohne Antworttext bleibt es beim Abhaken
    m = Nachricht.objects.create(kundennummer="801", anliegen="sonstiges", stelle=mitte, text="x")
    admin_client.post(reverse("kunden:nachrichten"), {"nachricht": m.pk, "antwort": "  "})
    m.refresh_from_db()
    assert m.erledigt_am and Notiz.objects.count() == 1
