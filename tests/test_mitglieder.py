"""Mitglieder (ADR 0046). Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.konten import rollen
from apps.mitglieder.models import Mitglied, MitgliederEinstellungen, naechste_nummer
from apps.spenden.models import Spende

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def erika():
    return Adresse.objects.create(art="person", vorname="Erika", nachname="Muster",
                                  strasse="Weg 1", plz="12345", ort="Musterstadt")  # fmt: skip


def mitglied(adresse, **mehr):
    werte = {"nummer": "1", "art": "Ordentliches Mitglied", "eintritt": dt.date(2025, 4, 15),
             "jahresbeitrag": D("36")} | mehr  # fmt: skip
    return Mitglied.objects.create(adresse=adresse, **werte)


def test_soll_monate_und_gezahlt(erika):
    m = mitglied(erika, austritt=dt.date(2026, 6, 30))
    assert m.monate(2024) == 0 and m.monate(2025) == 9 and m.monate(2026) == 6
    assert m.soll(2025, anteilig=False) == D("36") and m.soll(2025, anteilig=True) == D("27.00")
    assert m.soll(2027, anteilig=False) == 0
    assert m.ist_mitglied(dt.date(2026, 6, 30)) and not m.ist_mitglied(dt.date(2026, 7, 1))
    Spende.objects.create(adresse=erika, datum=dt.date(2025, 5, 1), betrag=D("20"),
                          mitgliedsbeitrag=True)  # fmt: skip
    Spende.objects.create(adresse=erika, datum=dt.date(2025, 6, 1), betrag=D("100"))  # Spende
    assert m.gezahlt(2025) == D("20")


def test_nummern():
    e = MitgliederEinstellungen.laden()
    e.naechste_nummer = 5
    e.save()
    mitglied(Adresse.objects.create(organisation="Verein X"), nummer="6")
    assert naechste_nummer() == "5" and naechste_nummer() == "7"


def test_anlegen_liste_beitraege(admin_client, erika):
    neu = reverse("mitglieder:neu")
    seite = admin_client.get(neu, {"adresse": erika.pk}).content.decode()
    assert f'<option value="{erika.pk}" selected>' in seite and "Fördermitglied" in seite
    assert 'value="1"' in seite  # vorgeschlagene Nummer
    daten = {"adresse": erika.pk, "nummer": "1", "art": "Fördermitglied",
             "eintritt": "2026-02-01", "jahresbeitrag": "36,00", "zahlweise": "jährlich",
             "zahlungsart": "Überweisung"}  # fmt: skip
    antwort = admin_client.post(neu, daten)
    m = Mitglied.objects.get()
    assert antwort.url == reverse("mitglieder:mitglied", args=[m.pk])
    assert MitgliederEinstellungen.laden().naechste_nummer == 2
    # Austritt braucht einen Grund
    fehlt = admin_client.post(reverse("mitglieder:bearbeiten", args=[m.pk]),
                              daten | {"austritt": "2026-12-31"})  # fmt: skip
    assert "Grund des Austritts" in fehlt.content.decode()
    # Beitragsseite mit Link zur Zahlung (Spende als Mitgliedsbeitrag, vorbelegt)
    seite = admin_client.get(antwort.url).content.decode()
    assert "Zahlung erfassen" in seite and "betrag=36.00" in seite
    spende = admin_client.get(
        reverse("spenden:neu"), {"adresse": erika.pk, "mitgliedsbeitrag": "1", "betrag": "36.00"}
    )
    formular = spende.content.decode()
    assert 'name="mitgliedsbeitrag" id="id_mitgliedsbeitrag" checked' in formular
    assert 'value="36,00"' in formular
    Spende.objects.create(adresse=erika, datum=dt.date(2026, 3, 1), betrag=D("36"),
                          mitgliedsbeitrag=True)  # fmt: skip
    liste = admin_client.get(reverse("mitglieder:liste"), {"jahr": "2026"}).content.decode()
    assert "Erika Muster" in liste and "36,00 €" in liste
    offen = admin_client.get(reverse("mitglieder:liste"), {"jahr": "2026", "nur_offen": "1"})
    assert "Erika Muster" not in offen.content.decode()
    csv = admin_client.get(reverse("mitglieder:liste"), {"jahr": "2026", "csv": "1"})
    assert "1;Erika Muster;Weg 1, 12345 Musterstadt" in csv.content.decode()
    # Adresse zeigt die Mitgliedschaft und ist nicht löschbar
    adresse = admin_client.get(reverse("adressen:adresse", args=[erika.pk])).content.decode()
    assert "Mitglied Nr. 1" in adresse
    admin_client.post(reverse("adressen:loeschen", args=[erika.pk]))
    assert Adresse.objects.filter(pk=erika.pk).exists()
    admin_client.post(reverse("mitglieder:loeschen", args=[m.pk]))
    assert not Mitglied.objects.exists() and Spende.objects.exists()


def test_auskunft(admin_client, erika, pdf_text):
    mitglied(erika)
    text = pdf_text(admin_client.get(reverse("adressen:auskunft", args=[erika.pk])))
    assert "Mitgliedschaft" in text and "Ordentliches Mitglied" in text


def test_rechte(client, admin, benutzer_mit_rolle, anmelden, erika):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(reverse("mitglieder:liste")).status_code == 200
    assert client.get(reverse("mitglieder:einstellungen")).status_code == 403
    client.logout()
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(reverse("mitglieder:liste")).status_code == 403
