"""Korrekturwünsche vom Einlass (ADR 0035). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.core import mail as django_mail
from django.urls import reverse

from apps.ausgabe.models import Buchung, Korrekturwunsch
from apps.core.models import MailEinstellungen
from apps.konten import rollen
from apps.kunden.models import Abholung, Ausgabestelle, Haushalt, Kundengruppe, Person

pytestmark = pytest.mark.django_db
HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def h():
    stelle = Ausgabestelle.objects.create(name="Mitte")
    gruppe = Kundengruppe.objects.create(name="Jeden Tag", ausgabestelle=stelle)
    h = Haushalt.objects.create(kundennummer="42", kundengruppe=gruppe,
                                ausweis_gueltig_bis=dt.date(2099, 1, 1))  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Probe")
    return h


@pytest.fixture
def mailserver(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    e = MailEinstellungen.laden()
    e.server, e.absender = "smtp.example.org", "tafel@example.org"
    e.save()


def test_ausgabe_beantragt_admin_entscheidet(
    client, admin, benutzer_mit_rolle, anmelden, h, mailserver, django_capture_on_commit_callbacks
):
    admin.email = "chefin@example.org"
    admin.save()
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    client.post(reverse("ausgabe:eintragen", args=["42"]), {"bar": "1,50"}, **HX)
    a = Abholung.objects.get()
    seite = client.get(reverse("ausgabe:empfang"), {"nummer": "42"}, **HX).content.decode()
    assert "Korrektur beantragen" in seite and "Versehentlich gebucht" in seite
    assert client.post(reverse("ausgabe:zuruecknehmen", args=[a.pk])).status_code == 403

    url = reverse("ausgabe:korrektur_beantragen", args=["abholung", a.pk])
    assert "Bitte einen Grund wählen" in client.post(url, {"grund": ""}, **HX).content.decode()
    with django_capture_on_commit_callbacks(execute=True):
        seite = client.post(url, {"grund": "Falscher Kunde aufgerufen",
                                  "anmerkung": "war Nr. 24"}, **HX).content.decode()  # fmt: skip
    assert "Korrekturwunsch gesendet" in seite and "wartet auf Entscheidung" in seite
    assert (
        "schon ein Korrekturwunsch offen"
        in client.post(url, {"grund": "Doppelt gebucht"}, **HX).content.decode()
    )
    k = Korrekturwunsch.objects.get()
    assert (k.kundennummer, k.grund, k.anmerkung, k.erstellt_von) == (
        "42", "Falscher Kunde aufgerufen", "war Nr. 24", "anton")  # fmt: skip
    assert k.beschreibung.startswith("Abholung am ")
    assert assert_mail_an("chefin@example.org")
    assert client.get(reverse("ausgabe:korrekturen")).status_code == 403

    client.logout()
    anmelden(client, admin)
    start = client.get("/").content.decode()
    assert "Korrekturwünsche offen: 1" in start and "Korrekturwünsche</a>" in start
    seite = client.get(reverse("ausgabe:korrekturen")).content.decode()
    assert "Falscher Kunde aufgerufen" in seite and "war Nr. 24" in seite
    client.post(reverse("ausgabe:korrektur_entscheiden", args=[k.pk]),
                {"entscheidung": "zuruecknehmen", "antwort": "ok"})  # fmt: skip
    k.refresh_from_db()
    assert k.status == "zurueckgenommen" and k.entschieden_von == "chefin"
    assert not Abholung.objects.exists() and not Buchung.objects.filter(abholung=a.pk).exists()
    seite = client.post(reverse("ausgabe:korrektur_entscheiden", args=[k.pk]),
                        {"entscheidung": "ablehnen"}, follow=True).content.decode()  # fmt: skip
    assert "schon entschieden" in seite


def assert_mail_an(adresse) -> bool:
    return any(adresse in m.to for m in django_mail.outbox)


def test_ablehnen_laesst_alles(admin_client, h):
    from apps.ausgabe import korrekturen

    a = Abholung.objects.create(haushalt=h, datum=dt.date(2026, 10, 1))
    k = korrekturen.beantragen("abholung", a.pk, grund="Sonstiges", anmerkung="", von="anton")
    admin_client.post(reverse("ausgabe:korrektur_entscheiden", args=[k.pk]),
                      {"entscheidung": "ablehnen", "antwort": "stimmt so"})  # fmt: skip
    k.refresh_from_db()
    assert k.status == "abgelehnt" and k.antwort == "stimmt so"
    assert Abholung.objects.filter(pk=a.pk).exists()


def test_eintrag_gibt_es_nicht_mehr(admin_client, h):
    from apps.ausgabe import korrekturen

    a = Abholung.objects.create(haushalt=h, datum=dt.date(2026, 10, 1))
    k = korrekturen.beantragen("abholung", a.pk, grund="Sonstiges", anmerkung="", von="anton")
    a.delete()
    seite = admin_client.post(reverse("ausgabe:korrektur_entscheiden", args=[k.pk]),
                              {"entscheidung": "zuruecknehmen"}, follow=True)  # fmt: skip
    assert "den Eintrag gab es nicht mehr" in seite.content.decode()
    with pytest.raises(korrekturen.KorrekturFehler):
        korrekturen.beantragen("abholung", a.pk, grund="Sonstiges", anmerkung="", von="x")


def test_recht_zum_entscheiden_und_zuruecknehmen(client, admin, benutzer_mit_rolle, anmelden, h,
                                                 recht_geben):  # fmt: skip
    recht_geben(rollen.BUERO, "korrekturen.entscheiden", "einlass.zuruecknehmen")
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(reverse("ausgabe:korrekturen")).status_code == 200
    client.post(reverse("ausgabe:eintragen", args=["42"]), {"bar": "1,50"}, **HX)
    seite = client.get(reverse("ausgabe:empfang"), {"nummer": "42"}, **HX).content.decode()
    assert "Abholung von" in seite and "zurücknehmen</button>" in seite
    assert "Korrektur beantragen" not in seite


def test_ungueltige_art(client, admin, benutzer_mit_rolle, anmelden):
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    url = reverse("ausgabe:korrektur_beantragen", args=["gibtsnicht", 1])
    assert client.post(url, {"grund": "Sonstiges"}).status_code == 404
    url = reverse("ausgabe:korrektur_beantragen", args=["abholung", 999])
    assert client.post(url, {"grund": "Sonstiges"}).status_code == 404


def test_entschiedene_korrekturen_auf_der_einlass_karte(admin_client, h):
    from apps.ausgabe import korrekturen

    a = Abholung.objects.create(haushalt=h, datum=dt.date(2026, 10, 1))
    b = Abholung.objects.create(haushalt=h, datum=dt.date(2026, 10, 8))
    k1 = korrekturen.beantragen("abholung", a.pk, grund="Versehentlich gebucht", anmerkung="",
                                von="anton")  # fmt: skip
    k2 = korrekturen.beantragen("abholung", b.pk, grund="Sonstiges", anmerkung="", von="anton")
    korrekturen.entscheiden(k1, annehmen=True, von="chefin")
    korrekturen.entscheiden(k2, annehmen=False, von="chefin", antwort="war richtig")
    seite = admin_client.get(reverse("ausgabe:empfang"), {"nummer": "42"}, **HX).content.decode()
    assert "Korrekturen der letzten 14 Tage" in seite
    assert "zurückgenommen" in seite and "Versehentlich gebucht" in seite
    assert "abgelehnt" in seite and "Antwort: war richtig" in seite and "von chefin" in seite
    # Ältere Entscheidungen erscheinen nicht mehr
    Korrekturwunsch.objects.update(entschieden_am=dt.datetime(2020, 1, 1, tzinfo=dt.UTC))
    seite = admin_client.get(reverse("ausgabe:empfang"), {"nummer": "42"}, **HX).content.decode()
    assert "Korrekturen der letzten" not in seite
