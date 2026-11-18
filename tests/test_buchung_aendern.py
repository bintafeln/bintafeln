"""Einzelne Buchungen im Kundenkonto ändern und löschen; Auszahlung am Einlass (Minus)."""

from decimal import Decimal as D

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe import konto
from apps.ausgabe.models import Buchung
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle, Haushalt

pytestmark = pytest.mark.django_db


@pytest.fixture
def haushalt():
    return Haushalt.objects.create(kundennummer="42", kontostand=D("0.00"))


def stand(h):
    h.refresh_from_db()
    return h.kontostand


def test_auszahlung_mit_minus(haushalt):
    konto.einzahlen(haushalt, D("5.00"), None, "Kasse")
    b = konto.einzahlen(haushalt, D("-3.00"), None, "Kasse")
    # Geld geht bar zurück: Kontostand und Kasse sinken
    assert (b.haben, b.bar, stand(haushalt)) == (D("-3.00"), D("-3.00"), D("2.00"))
    konto.zuruecknehmen(b)
    assert stand(haushalt) == D("5.00")


def test_aendern_zieht_kontostand_nach(haushalt):
    b = konto.einzahlen(haushalt, D("5.00"), None, "Kasse")
    stelle = Ausgabestelle.objects.create(name="Nord")
    konto.aendern(b, haben=D("3.00"), bar=D("3.00"), ausgabestelle=stelle, bemerkung="Tippfehler")
    b.refresh_from_db()
    assert (b.haben, b.bar, b.ausgabestelle, b.bemerkung) == (D("3"), D("3"), stelle, "Tippfehler")
    assert stand(haushalt) == D("3.00")
    konto.aendern(b, bemerkung="nur Text")  # ohne Wirkung bleibt der Kontostand
    assert stand(haushalt) == D("3.00")
    with pytest.raises(konto.KontoFehler):
        konto.aendern(b, datum=None)


def test_aendern_ohne_haushalt():
    b = Buchung.objects.create(kundennummer="7", art=Buchung.Art.EINZAHLUNG, haben=D("2"))
    assert konto.aendern(b, haben=D("1")).haben == D("1")


def test_einlass_bucht_auszahlung(admin_client, haushalt):
    client = admin_client
    ziel = reverse("ausgabe:einzahlung", args=["42"])
    antwort = client.post(ziel, {"betrag": "-3"}, follow=True)
    assert "Auszahlung von 3,00 € gebucht" in antwort.content.decode()
    assert stand(haushalt) == D("-3.00")
    antwort = client.post(ziel, {"betrag": "0"}, follow=True)
    assert "ungleich 0" in antwort.content.decode()
    antwort = client.post(ziel, {"betrag": "4"}, follow=True)
    assert "Einzahlung von 4,00 € gebucht" in antwort.content.decode()


def test_ansicht_aendern_und_loeschen(admin_client, haushalt):
    b = konto.einzahlen(haushalt, D("5.00"), None, "Kasse")
    seite = admin_client.get(reverse("kunden:haushalt", args=["42"])).content.decode()
    aendern = reverse("ausgabe:buchung", args=[b.pk])
    loeschen = reverse("ausgabe:buchung_loeschen", args=[b.pk])
    assert aendern in seite and loeschen in seite
    assert "Buchung ändern" in admin_client.get(aendern).content.decode()
    # ungültig: Seite bleibt, nichts geändert
    antwort = admin_client.post(aendern, {"soll": "x", "haben": "2", "bar": "2"})
    assert antwort.status_code == 200 and stand(haushalt) == D("5.00")
    daten = {"soll": "0", "haben": "2,00", "bar": "2,00", "ausgabestelle": "", "bemerkung": "neu"}
    antwort = admin_client.post(aendern, daten, follow=True)
    assert "Buchung geändert" in antwort.content.decode() and stand(haushalt) == D("2.00")
    assert admin_client.get(loeschen).status_code == 405
    antwort = admin_client.post(loeschen, follow=True)
    assert "Buchung gelöscht" in antwort.content.decode()
    assert stand(haushalt) == D("0.00") and not Buchung.objects.exists()


def test_ohne_recht_gesperrt(admin, anmelden, client, haushalt, benutzer_mit_rolle):
    anmelden(client, benutzer_mit_rolle(rollen.AUSGABE))
    b = konto.einzahlen(haushalt, D("5.00"), None, "Kasse")
    assert client.get(reverse("ausgabe:buchung", args=[b.pk])).status_code == 403
    assert client.post(reverse("ausgabe:buchung_loeschen", args=[b.pk])).status_code == 403
    assert Buchung.objects.count() == 1


def test_bearbeiten_speichert_sofort_anlegen_mit_knopf(admin_client, haushalt):
    """Vorhandenes bearbeiten: Formular mit data-autosave; Neues: Knopf „Anlegen“ (ADR 0145)."""
    b = konto.einzahlen(haushalt, D("5.00"), None, "Kasse")
    for ziel in (
        reverse("kunden:bearbeiten", args=["42"]),
        reverse("ausgabe:buchung", args=[b.pk]),
    ):
        assert "data-autosave" in admin_client.get(ziel).content.decode()
    seite = admin_client.get(reverse("kunden:bearbeiten", args=["42"])).content.decode()
    assert "data-autosave-folgen" in seite and "data-autosave-spaet" in seite
    neu = admin_client.get(reverse("kunden:teil_neu", args=["42", "abholer"])).content.decode()
    assert "data-autosave" not in neu and ">Anlegen<" in neu
    for art in ("beitragsfrei", "schliesszeiten"):
        neu = admin_client.get(reverse("kunden:listeneintrag_neu", args=[art])).content.decode()
        assert "data-autosave" not in neu and ">Anlegen<" in neu
    neu = admin_client.get(reverse("ausgabe:sonderaktion_neu")).content.decode()
    assert "data-autosave" not in neu and ">Anlegen<" in neu


def test_vorhandener_eintrag_speichert_sofort(admin_client, haushalt):
    from apps.ausgabe.models import Sonderaktion
    from apps.kunden.models import Abholer

    a = Abholer.objects.create(haushalt=haushalt, vorname="Erika", nachname="Beispiel")
    seite = admin_client.get(reverse("kunden:teil", args=["42", "abholer", a.pk])).content.decode()
    assert "data-autosave" in seite and ">Anlegen<" not in seite
    heute = timezone.localdate()
    aktion = Sonderaktion.objects.create(bezeichnung="Aktion", von=heute, bis=heute)
    seite = admin_client.get(reverse("ausgabe:sonderaktion_bearbeiten", args=[aktion.pk]))
    assert "data-autosave" in seite.content.decode()


def test_mitarbeitende_und_personal_speichern_sofort(admin_client, admin, benutzer_mit_rolle):
    """Teil 2 von ADR 0145: Konto, Stammdaten, Rolle, Benachrichtigungen, Arbeitszeit."""
    from apps.konten.models import Rolle

    person = benutzer_mit_rolle(rollen.AUSGABE)
    rolle = Rolle.objects.first()
    for ziel in (
        reverse("konten:mitarbeiter", args=[person.pk]),
        reverse("konten:stammdaten", args=[person.pk]),
        reverse("konten:rolle", args=[rolle.pk]),
        reverse("personal:arbeitszeit_einstellungen"),
    ):
        assert "data-autosave" in admin_client.get(ziel).content.decode(), ziel
    konto_seite = admin_client.get(reverse("konten:mitarbeiter", args=[person.pk]))
    assert "data-autosave-spaet" in konto_seite.content.decode()
    for ziel in (reverse("konten:mitarbeiter_neu"), reverse("konten:rolle_neu")):
        seite = admin_client.get(ziel).content.decode()
        # „data-autosave-spaet“ am Benutzernamen zählt nicht: es wirkt nur mit data-autosave
        assert " data-autosave>" not in seite and ">Anlegen<" in seite, ziel


def test_spenden_mitglieder_statistik_speichern_sofort(admin_client):
    """Teil 3 von ADR 0145: vorhandene Einträge ohne Knopf, neue mit „Anlegen“."""
    for ziel in (reverse("statistik:einstellungen"),):
        assert " data-autosave>" in admin_client.get(ziel).content.decode(), ziel
    neu = admin_client.get(reverse("spenden:neu")).content.decode()
    assert " data-autosave>" not in neu and ">Anlegen<" in neu and ">Abbrechen<" in neu
