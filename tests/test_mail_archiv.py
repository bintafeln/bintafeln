"""Archiv der gesendeten Mails (ADR 0124)."""

import datetime as dt
import smtplib

import pytest
from auditlog.models import LogEntry
from django.core import mail as djmail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core import mail
from apps.core.models import GesendeteMail, MailEinstellungen
from apps.konten import rollen

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def mailserver():
    e = MailEinstellungen.laden()
    e.server, e.absender = "mail.example.org", "tafel@example.org"
    e.save()


def test_gesendete_mail_steht_im_archiv():
    """Empfänger, Betreff, Text und Art; Anhänge nur mit Name und Größe."""
    mail.senden("Einladung", "Guten Tag,\nbitte kommen Sie am Montag.", ["erika@example.org"],
                anhaenge=[("termin.pdf", b"%PDF-1.4 abc", "application/pdf")],
                art="warteliste")  # fmt: skip
    assert len(djmail.outbox) == 1
    m = GesendeteMail.objects.get()
    assert (m.an, m.betreff, m.art, m.fehler) == (
        "erika@example.org",
        "Einladung",
        "warteliste",
        "",
    )
    assert "am Montag" in m.text and not m.vertraulich
    assert m.anhaenge == [{"name": "termin.pdf", "groesse": 12, "typ": "application/pdf"}]
    assert "%PDF" not in str(m.anhaenge)  # der Inhalt des Anhangs bleibt draußen


def test_zugangsdaten_ohne_inhalt():
    mail.senden("Neues Passwort", "Ihr Link: https://tafel.example.org/geheim/abc",
                ["max@example.org"], art="zugang", vertraulich=True)  # fmt: skip
    m = GesendeteMail.objects.get()
    assert m.vertraulich and m.text == "" and m.betreff == "Neues Passwort"


def test_fehlschlag_wird_festgehalten(monkeypatch):
    def kaputt(self, *a, **k):
        raise smtplib.SMTPRecipientsRefused({})

    monkeypatch.setattr("django.core.mail.EmailMultiAlternatives.send", kaputt)
    with pytest.raises(mail.MailFehler):
        mail.senden("Dank", "Vielen Dank", ["weg@example.org"], art="spenden")
    assert "Empfängeradresse abgelehnt" in GesendeteMail.objects.get().fehler
    # Ohne eingerichteten Mailserver ebenso
    e = MailEinstellungen.laden()
    e.server = ""
    e.save()
    with pytest.raises(mail.MailFehler):
        mail.senden("Dank", "Vielen Dank", ["weg@example.org"])
    assert GesendeteMail.objects.filter(fehler__contains="kein Mailserver").exists()


def test_frist_und_archiv_aus():
    mail.senden("Alt", "x", ["a@example.org"])
    mail.senden("Neu", "x", ["a@example.org"])
    alt = GesendeteMail.objects.get(betreff="Alt")
    GesendeteMail.objects.filter(pk=alt.pk).update(
        gesendet_am=timezone.now() - dt.timedelta(days=91)
    )
    assert mail.fristen_anwenden() == 1
    assert list(GesendeteMail.objects.values_list("betreff", flat=True)) == ["Neu"]
    # 0 Tage: nichts festhalten, Vorhandenes verschwindet
    e = MailEinstellungen.laden()
    e.archiv_tage = 0
    e.save()
    mail.senden("Ohne Archiv", "x", ["a@example.org"])
    assert not GesendeteMail.objects.filter(betreff="Ohne Archiv").exists()
    mail.fristen_anwenden()
    assert not GesendeteMail.objects.exists()


def test_archiv_seite_suche_filter_und_abruf_protokolliert(admin_client, admin):
    mail.senden("Einladung zum Termin", "Bitte kommen.", ["erika@example.org"], art="warteliste")
    mail.senden("Danke für Ihre Spende", "Vielen Dank.", ["max@example.org"], art="spenden")
    url = reverse("core:mails")
    seite = admin_client.get(url).content.decode()
    assert "Einladung zum Termin" in seite and "Danke für Ihre Spende" in seite
    assert "Bitte kommen." not in seite  # der Wortlaut erst nach dem Klick
    assert (
        "Einladung" not in admin_client.get(url, {"q": "max@"}).content.decode().split("<tbody>")[1]
    )
    nur = admin_client.get(url, {"art": "warteliste"}).content.decode()
    assert "Einladung zum Termin" in nur and "Danke für Ihre Spende" not in nur
    assert "Keine Mail passt" in admin_client.get(url, {"fehler": "1"}).content.decode()
    m = GesendeteMail.objects.get(art="warteliste")
    detail = admin_client.get(reverse("core:mail", args=[m.pk])).content.decode()
    assert "Bitte kommen." in detail and "erika@example.org" in detail
    eintrag = LogEntry.objects.get(object_pk=str(m.pk), action=LogEntry.Action.ACCESS)
    assert eintrag.actor == admin
    # Das Archiv selbst steht nicht im Änderungsprotokoll (sonst überlebte der Inhalt die Frist)
    assert not LogEntry.objects.filter(action=LogEntry.Action.CREATE,
                                       content_type=eintrag.content_type).exists()  # fmt: skip


def test_archiv_nur_mit_recht(anmelden, benutzer_mit_rolle, admin, recht_geben):
    mail.senden("Einladung", "x", ["erika@example.org"])
    c = anmelden(Client(), benutzer_mit_rolle("eva", rollen.BUERO))
    m = GesendeteMail.objects.get()
    assert c.get(reverse("core:mails")).status_code == 403
    assert c.get(reverse("core:mail", args=[m.pk])).status_code == 403
    assert "Gesendete Mails" not in c.get(reverse("core:start")).content.decode()
    recht_geben(rollen.BUERO, "system.mails")
    assert c.get(reverse("core:mails")).status_code == 200


def test_frist_in_den_mail_einstellungen(admin_client):
    seite = admin_client.get(reverse("core:mail_einstellungen")).content.decode()
    assert "Gesendete Mails aufbewahren" in seite
