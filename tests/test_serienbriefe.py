"""Serienbriefe (ADR 0047). Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.core import mail as django_mail
from django.urls import reverse

from apps.adressen.models import Adresse, AdressKategorie
from apps.core.models import MailEinstellungen
from apps.konten import rollen
from apps.kunden.models import Haushalt, Person
from apps.mitglieder.models import Mitglied
from apps.serienbriefe import empfaenger as emp
from apps.serienbriefe.models import Versand, Vorlage
from apps.spenden.models import Spende

pytestmark = pytest.mark.django_db
URL = reverse("serienbriefe:erstellen")
JAHR = dt.date.today().year


@pytest.fixture
def daten():
    spender = AdressKategorie.objects.get(name="Spender")
    erika = Adresse.objects.create(art="person", anrede="Frau", vorname="Erika", nachname="Muster",
                                   strasse="Weg 1", plz="12345", ort="Musterstadt",
                                   email="erika@example.org", einwilligung_post=dt.date(2026, 1, 1),
                                   einwilligung_email=dt.date(2026, 1, 1))  # fmt: skip
    erika.kategorien.add(spender)
    baeckerei = Adresse.objects.create(
        organisation="Bäckerei Probe", strasse="Markt 2", plz="12345", ort="Musterstadt"
    )  # ohne Einwilligung
    baeckerei.kategorien.add(spender)
    Spende.objects.create(adresse=erika, datum=dt.date(JAHR, 2, 1), betrag=Decimal("150"))
    Spende.objects.create(adresse=baeckerei, datum=dt.date(JAHR, 3, 1), betrag=Decimal("20"))
    Mitglied.objects.create(adresse=baeckerei, nummer="7", art="Fördermitglied",
                            eintritt=dt.date(2020, 1, 1), jahresbeitrag=Decimal("60"))  # fmt: skip
    h = Haushalt.objects.create(kundennummer="1001", strasse="Kundenweg 3", plz="12345",
                                ort="Musterstadt")  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, anrede="Herr", vorname="Max",
                          nachname="Kunde")  # fmt: skip
    return erika, baeckerei


def test_anrede_und_platzhalter():
    assert emp.briefanrede("Frau", "Erika", "Muster", False) == "Sehr geehrte Frau Muster,"
    assert emp.briefanrede("Herr", "", "Probe", False) == "Sehr geehrter Herr Probe,"
    assert emp.briefanrede("", "Kim", "Test", False) == "Guten Tag Kim Test,"
    assert emp.briefanrede("", "", "", True) == "Sehr geehrte Damen und Herren,"
    e = emp.Empfaenger("a:1", "X", [], werte={"name": "Erika"})
    assert emp.einsetzen("Hallo {name}, {unbekannt} {", e, {"jahr": 2026}) == (
        "Hallo Erika, {unbekannt} {")  # fmt: skip


def test_quellen(daten, admin):
    erika, baeckerei = daten
    d = {"jahr": JAHR, "versandart": "brief", "nur_einwilligung": True,
         "kategorien": [AdressKategorie.objects.get(name="Spender")]}  # fmt: skip
    assert [e.name for e in emp.suchen("adressen", d)] == ["Erika Muster"]
    assert len(emp.suchen("adressen", d | {"nur_einwilligung": False})) == 2
    spender = emp.suchen("spender", d | {"mindestbetrag": Decimal("100")})
    assert [e.name for e in spender] == ["Erika Muster"]
    assert spender[0].werte["spendensumme"] == "150,00 €"
    mitglieder = emp.suchen("mitglieder", d | {"nur_offen": True})
    assert [e.werte["mitgliedsnummer"] for e in mitglieder] == ["7"]
    assert mitglieder[0].werte["beitrag_offen"] == "60,00 €"
    assert mitglieder[0].werte["anrede"] == "Sehr geehrte Damen und Herren,"
    kunden = emp.suchen("kunden", d, admin)
    assert kunden[0].werte["anrede"] == "Sehr geehrter Herr Kunde,"
    assert kunden[0].anschrift == ["Herr Max Kunde", "Kundenweg 3", "12345 Musterstadt"]
    ok, ohne = emp.aufteilen(kunden, "email")
    assert not ok and ohne


def test_pdf_und_vermerk(admin_client, daten, pdf_text):
    vorlage = Vorlage.objects.get(name="Dank für Spenden")
    daten_form = {"vorlage": vorlage.pk, "quelle": "spender", "versandart": "brief",
                  "jahr": JAHR, "nur_einwilligung": "on"}  # fmt: skip
    vorschau = admin_client.post(URL, daten_form).content.decode()
    assert "1 Empfänger" in vorschau and "Sehr geehrte Frau Muster," in vorschau
    assert "150,00 €" in vorschau and "PDF mit 1 Brief erzeugen" in vorschau
    antwort = admin_client.post(URL, daten_form | {"schritt": "pdf"})
    text = pdf_text(antwort)
    assert "Sehr geehrte Frau Muster," in text and "Weg 1" in text and "150,00" in text
    v = Versand.objects.get()
    assert (v.art, v.anzahl, v.empfaenger) == ("brief", 1, [f"a:{daten[0].pk}"])
    auskunft = pdf_text(admin_client.get(reverse("adressen:auskunft", args=[daten[0].pk])))
    assert "Serienbriefe" in auskunft and "Herzlichen Dank" in auskunft
    seite = admin_client.get(reverse("serienbriefe:vorlagen")).content.decode()
    assert "Spender eines Jahres" in seite


def test_email(admin_client, daten):
    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    vorlage = Vorlage.objects.get(name="Dank für Spenden")
    form = {"vorlage": vorlage.pk, "quelle": "adressen", "versandart": "email", "jahr": JAHR,
            "nur_einwilligung": "on", "schritt": "senden"}  # fmt: skip
    antwort = admin_client.post(URL, form, follow=True)
    assert "1 E-Mail gesendet" in antwort.content.decode()
    assert len(django_mail.outbox) == 1 and django_mail.outbox[0].to == ["erika@example.org"]
    assert "Sehr geehrte Frau Muster," in django_mail.outbox[0].body
    assert Versand.objects.get().art == "email"


def test_vorlagen_pflegen(admin_client):
    neu = reverse("serienbriefe:vorlage_neu")
    assert "{spendensumme}" in admin_client.get(neu).content.decode()
    admin_client.post(neu, {"name": "Test", "betreff": "Hallo", "text": "{anrede}\n\nText"})
    v = Vorlage.objects.get(name="Test")
    admin_client.post(reverse("serienbriefe:vorlage_loeschen", args=[v.pk]))
    assert not Vorlage.objects.filter(name="Test").exists()


def test_rechte(client, admin, benutzer_mit_rolle, anmelden, daten):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    seite = client.get(URL).content.decode()
    assert "Spender eines Jahres" in seite and "Kunden (Haushalte)" not in seite
    client.logout()
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(URL).status_code == 403
