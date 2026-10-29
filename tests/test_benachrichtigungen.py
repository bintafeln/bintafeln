"""Benachrichtigungen an Mitarbeitende (ADR 0086): Häufigkeit je Person, Erledigtes entfällt."""

import datetime as dt

import pytest
from django.core import mail as django_mail
from django.core.management import call_command
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe.models import Korrekturwunsch
from apps.core import benachrichtigung as b
from apps.core.models import (
    BenachrichtigungsWahl,
    BenachrichtigungsZeit,
    MailEinstellungen,
    Meldung,
)

pytestmark = pytest.mark.django_db
URL = reverse("konten:benachrichtigungen")


@pytest.fixture
def mailserver(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    e = MailEinstellungen.laden()
    e.server, e.absender = "smtp.example.org", "tafel@example.org"
    e.save()


@pytest.fixture
def chefin(admin):
    admin.email = "chefin@example.org"
    admin.save()
    return admin


def wunsch(**mehr):
    return Korrekturwunsch.objects.create(art="abholung", objekt_id=1, kundennummer="00042",
                                          beschreibung="Abholung", grund="Versehen",
                                          erstellt_von="anton", **mehr)  # fmt: skip


def test_sofort_wie_bisher_und_ohne_konto(mailserver, chefin):
    b.melden("korrekturwunsch", ["chefin@example.org", "helfer@example.org"], "Betreff", "Text")
    assert len(django_mail.outbox) == 1
    assert sorted(django_mail.outbox[0].to) == ["chefin@example.org", "helfer@example.org"]
    assert not Meldung.objects.exists()


def test_nie_und_ohne_mailserver(chefin, mailserver):
    BenachrichtigungsWahl.objects.create(benutzer=chefin, art="korrekturwunsch", haeufigkeit="nie")
    b.melden("korrekturwunsch", ["chefin@example.org"], "Betreff", "Text")
    assert not django_mail.outbox and not Meldung.objects.exists()
    MailEinstellungen.objects.update(server="")
    BenachrichtigungsWahl.objects.all().delete()
    b.melden("korrekturwunsch", ["chefin@example.org"], "Betreff", "Text")
    assert not django_mail.outbox


def test_taeglich_gesammelt_erledigtes_entfaellt(mailserver, chefin):
    BenachrichtigungsWahl.objects.create(benutzer=chefin, art="korrekturwunsch",
                                         haeufigkeit="taeglich")  # fmt: skip
    BenachrichtigungsZeit.objects.create(benutzer=chefin, uhrzeit=dt.time(7, 30))
    offen, erledigt = wunsch(), wunsch()
    b.melden("korrekturwunsch", ["chefin@example.org"], "Wunsch 1", "Text 1", schluessel=offen.pk)
    b.melden("korrekturwunsch", ["chefin@example.org"], "Wunsch 2", "Text 2",
             schluessel=erledigt.pk)  # fmt: skip
    b.melden(
        "korrekturwunsch", ["chefin@example.org"], "Wunsch 3", "Text 3", schluessel=wunsch().pk
    )
    assert not django_mail.outbox and Meldung.objects.count() == 3
    faellig = timezone.localtime(Meldung.objects.first().faellig_am)
    assert (faellig.hour, faellig.minute) == (7, 30) and faellig > timezone.now()
    assert b.senden() == 0  # noch nicht fällig
    erledigt.status = Korrekturwunsch.Status.ABGELEHNT
    erledigt.save()
    assert b.senden(jetzt=faellig) == 1
    gesendet = django_mail.outbox[0]
    assert gesendet.to == ["chefin@example.org"] and gesendet.subject.endswith(
        "2 Benachrichtigungen"
    )
    assert "Wunsch 1" in gesendet.body and "Wunsch 3" in gesendet.body
    assert "Wunsch 2" not in gesendet.body  # inzwischen entschieden
    assert "Mein Konto → Benachrichtigungen" in gesendet.body
    assert not Meldung.objects.exists()


def test_alles_erledigt_keine_mail(mailserver, chefin):
    BenachrichtigungsWahl.objects.create(benutzer=chefin, art="korrekturwunsch",
                                         haeufigkeit="stuendlich")  # fmt: skip
    w = wunsch()
    b.melden("korrekturwunsch", ["chefin@example.org"], "Wunsch", "Text", schluessel=w.pk)
    m = Meldung.objects.get()
    assert m.faellig_am.minute == 0 and m.faellig_am > timezone.now()
    w.delete()
    call_command("benachrichtigungen_senden")
    assert Meldung.objects.exists()  # noch nicht fällig
    assert b.senden(jetzt=m.faellig_am) == 0 and not django_mail.outbox
    assert not Meldung.objects.exists()


def test_woechentlich_und_mailfehler(mailserver, chefin, monkeypatch):
    BenachrichtigungsZeit.objects.create(benutzer=chefin, uhrzeit=dt.time(9, 0), wochentag=4)
    jetzt = timezone.make_aware(dt.datetime(2026, 10, 30, 10, 0))  # Freitag nach 9 Uhr
    ziel = b.faellig_am(chefin, b.WOECHENTLICH, jetzt)
    assert ziel.weekday() == 4 and ziel.date() == dt.date(2026, 11, 6) and ziel.hour == 9
    assert b.faellig_am(chefin, b.TAEGLICH, jetzt).date() == dt.date(2026, 10, 31)
    Meldung.objects.create(benutzer=chefin, art="sicherheitsupdate", betreff="Update",
                           text="x", faellig_am=jetzt)  # fmt: skip

    def kaputt(*a, **k):
        from apps.core.mail import MailFehler

        raise MailFehler("weg")

    monkeypatch.setattr("apps.core.mail.senden", kaputt)
    assert b.senden(jetzt=jetzt) == 0
    assert Meldung.objects.exists()  # beim nächsten Lauf noch einmal


def test_mein_konto_einstellen(admin_client, chefin):
    seite = admin_client.get(reverse("konten:mein_konto")).content.decode()
    assert "Benachrichtigungen" in seite and URL in seite
    seite = admin_client.get(URL).content.decode()
    assert "Korrekturwunsch vom Einlass" in seite and "Sicherheitsupdate verfügbar" in seite
    assert 'name="art_sicherheitsupdate"' in seite
    sicherheit = seite.split('name="art_sicherheitsupdate"')[1].split("</select>")[0]
    assert "nie" not in sicherheit and "stündlich" not in sicherheit  # nur sofort/täglich
    admin_client.post(URL, {"art_korrekturwunsch": "woechentlich", "art_sicherheitsupdate": "nie",
                            "art_antrag_neu": "taeglich", "uhrzeit": "06:45",
                            "wochentag": "2"})  # fmt: skip
    assert b.haeufigkeit(chefin, "korrekturwunsch") == "woechentlich"
    assert b.haeufigkeit(chefin, "sicherheitsupdate") == "sofort"  # „nie“ nicht erlaubt
    assert not BenachrichtigungsWahl.objects.filter(art="antrag_neu").exists()  # nicht für sie
    zeit = BenachrichtigungsZeit.objects.get(benutzer=chefin)
    assert zeit.uhrzeit == dt.time(6, 45) and zeit.wochentag == 2
    admin_client.post(URL, {"art_korrekturwunsch": "sofort", "uhrzeit": "kaputt",
                            "wochentag": "9"})  # fmt: skip
    assert not BenachrichtigungsWahl.objects.filter(art="korrekturwunsch").exists()
    zeit.refresh_from_db()
    assert zeit.uhrzeit == dt.time(6, 45) and zeit.wochentag == 0


def test_ohne_mailadresse_hinweis(client, admin, benutzer_mit_rolle, anmelden):
    anmelden(client, benutzer_mit_rolle("anton", "Ausgabe"))
    seite = client.get(URL).content.decode()
    assert "keine E-Mail-Adresse" in seite


def test_module_bringen_eigene_arten(chefin):
    from apps.core.models import TafelEinstellungen

    assert "dienstplan_ausfall" not in b.arten()
    t = TafelEinstellungen.laden()
    t.module = ["dienstplan", "fahrdienst"]
    t.save()
    alle = b.arten()
    assert {"dienstplan_ausfall", "dienstplan_gesund", "fahrdienst_ausfall"} <= set(alle)
    assert alle["dienstplan_ausfall"].offen("999999") is False
    assert alle["fahrdienst_ausfall"].offen("") is False
