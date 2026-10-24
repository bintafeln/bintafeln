import smtplib
import socket
import ssl

import pytest
from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse

from apps.core import geheimnis, mail
from apps.core.models import MailEinstellungen, TafelEinstellungen
from apps.konten import rollen

pytestmark = pytest.mark.django_db

MAIL_SEITE = reverse("core:mail_einstellungen")
VERGESSEN = reverse("konten:passwort_vergessen")


@pytest.fixture(autouse=True)
def leerer_cache():
    cache.clear()


@pytest.fixture
def mailserver():
    """Erfundener Mailserver; in Tests landen Mails im Speicher (django.core.mail.outbox)."""
    e = MailEinstellungen.laden()
    e.server, e.benutzer, e.absender = "smtp.example.org", "tafel", "tafel@example.org"
    e.passwort_verschluesselt = geheimnis.verschluesseln("nur-test")
    e.save()
    return e


def link_aus(nachricht):
    return next(z for z in nachricht.body.splitlines() if "/konten/passwort/setzen/" in z).strip()


# --- Verschlüsselung -------------------------------------------------------------------


def test_geheimnis_hin_und_zurueck():
    text = geheimnis.verschluesseln("geheim")
    assert text and "geheim" not in text
    assert geheimnis.entschluesseln(text) == "geheim"
    assert geheimnis.verschluesseln("") == "" and geheimnis.entschluesseln("") == ""


def test_geheimnis_mit_anderem_schluessel_unlesbar():
    text = geheimnis.verschluesseln("geheim")
    with override_settings(SECRET_KEY="ein-anderer-schluessel-nur-fuer-tests"):
        assert geheimnis.entschluesseln(text) is None


# --- Senden ------------------------------------------------------------------------------


def test_absender_faellt_auf_tafel_zurueck():
    e = MailEinstellungen.laden()
    e.server = "smtp.example.org"
    assert not e.eingerichtet and str(e) == "E-Mail-Einstellungen"
    t = TafelEinstellungen.laden()
    t.email = "info@example.org"
    t.save()
    assert e.absenderadresse == "info@example.org" and e.eingerichtet


def test_senden(mailserver, monkeypatch):
    benutzt = {}
    echt = mail.get_connection

    def verbindung(**kwargs):
        benutzt.update(kwargs)
        return echt(**kwargs)

    monkeypatch.setattr(mail, "get_connection", verbindung)
    mail.senden("Betreff", "Text", ["kim@example.org"])
    assert django_mail.outbox[0].from_email == "tafel@example.org"
    assert (benutzt["password"], benutzt["use_tls"], benutzt["use_ssl"]) == (
        "nur-test",
        True,
        False,
    )


def test_senden_ohne_mailserver():
    with pytest.raises(mail.MailFehler, match="kein Mailserver"):
        mail.senden("B", "T", ["kim@example.org"])
    assert not mail.eingerichtet()


def test_senden_mit_unlesbarem_passwort(mailserver):
    mailserver.passwort_verschluesselt = "kaputt"
    mailserver.save()
    with pytest.raises(mail.MailFehler, match="nicht mehr lesbar"):
        mail.senden("B", "T", ["kim@example.org"])


@pytest.mark.parametrize(
    ("fehler", "text"),
    [
        (smtplib.SMTPAuthenticationError(535, b"nein"), "Benutzername und Passwort"),
        (smtplib.SMTPRecipientsRefused({}), "Empfängeradresse abgelehnt"),
        (ssl.SSLError("x"), "Port und Verschlüsselung"),
        (socket.gaierror("x"), "nicht erreichbar"),
        (ConnectionRefusedError(), "nicht erreichbar"),
        (smtplib.SMTPServerDisconnected(), "SMTPServerDisconnected"),
    ],
)
def test_verstaendliche_fehler(mailserver, monkeypatch, fehler, text):
    def scheitern(self, *args, **kwargs):
        raise fehler

    monkeypatch.setattr(mail.EmailMessage, "send", scheitern)
    with pytest.raises(mail.MailFehler, match=text):
        mail.senden("B", "T", ["kim@example.org"])


# --- Einstellungsseite ------------------------------------------------------------------


def test_nur_admin(client, admin, benutzer_mit_rolle, anmelden):
    anmelden(client, benutzer_mit_rolle("b", rollen.BUERO))
    assert client.get(MAIL_SEITE).status_code == 403


def test_einstellungen_speichern_verschluesselt(admin_client):
    assert "Noch kein Mailserver" in admin_client.get(MAIL_SEITE).content.decode()
    daten = {"server": "smtp.example.org", "port": "465", "verschluesselung": "ssl",
             "benutzer": "tafel", "absender": "tafel@example.org"}  # fmt: skip
    admin_client.post(MAIL_SEITE, {**daten, "passwort": "Sehr-geheim-1"})
    e = MailEinstellungen.laden()
    assert "Sehr-geheim-1" not in e.passwort_verschluesselt
    assert geheimnis.entschluesseln(e.passwort_verschluesselt) == "Sehr-geheim-1"
    inhalt = admin_client.get(MAIL_SEITE).content.decode()
    assert "Eingerichtet" in inhalt and "verschlüsselt gespeichert" in inhalt
    assert "Sehr-geheim-1" not in inhalt
    admin_client.post(MAIL_SEITE, daten)  # leer = behalten
    assert geheimnis.entschluesseln(MailEinstellungen.laden().passwort_verschluesselt)
    admin_client.post(MAIL_SEITE, {**daten, "passwort_loeschen": "on"})
    assert MailEinstellungen.laden().passwort_verschluesselt == ""


def test_hinweise_auf_der_seite(admin_client, mailserver):
    mailserver.absender = ""
    mailserver.passwort_verschluesselt = "kaputt"
    mailserver.save()
    inhalt = admin_client.get(MAIL_SEITE).content.decode()
    assert "Es fehlt eine Absenderadresse" in inhalt and "nicht mehr lesbar" in inhalt


def test_testmail(admin_client, admin, mailserver, monkeypatch):
    seite = admin_client.get(MAIL_SEITE).content.decode()
    assert "Verbindung prüfen" in seite and "Testmail senden an" in seite
    seite = admin_client.post(MAIL_SEITE, {"testmail": "1"}, follow=True).content.decode()
    assert "gültige Empfängeradresse" in seite and not django_mail.outbox
    seite = admin_client.post(MAIL_SEITE, {"testmail": "1", "an": "test@example.org"},
                              follow=True).content.decode()  # fmt: skip
    assert "Testmail an test@example.org gesendet." in seite
    assert django_mail.outbox[0].to == ["test@example.org"]
    admin.email = "chefin@example.org"
    admin.save()
    assert 'value="chefin@example.org"' in admin_client.get(MAIL_SEITE).content.decode()
    admin_client.post(MAIL_SEITE, {"testmail": "1"})
    assert django_mail.outbox[1].to == ["chefin@example.org"]

    def scheitern(*args, **kwargs):
        raise mail.MailFehler("Mailserver nicht erreichbar.")

    monkeypatch.setattr(mail, "senden", scheitern)
    seite = admin_client.post(MAIL_SEITE, {"testmail": "1"}, follow=True).content.decode()
    assert "Testmail nicht gesendet: Mailserver nicht erreichbar." in seite


def test_verbindung_pruefen(admin_client, mailserver, monkeypatch):
    seite = admin_client.post(MAIL_SEITE, {"pruefen": "1"}, follow=True).content.decode()
    assert "Verbindung und Anmeldung am Mailserver klappen." in seite
    assert not django_mail.outbox  # es wird nichts gesendet

    class Kaputt:
        def open(self):
            raise smtplib.SMTPAuthenticationError(535, b"nein")

        def close(self):
            pass

    monkeypatch.setattr(mail, "get_connection", lambda **kwargs: Kaputt())
    seite = admin_client.post(MAIL_SEITE, {"pruefen": "1"}, follow=True).content.decode()
    assert "Verbindung fehlgeschlagen: Anmeldung am Mailserver fehlgeschlagen." in seite


def test_test_erst_nach_einrichtung(admin_client):
    assert (
        "sobald Server und Absender gespeichert sind"
        in admin_client.get(MAIL_SEITE).content.decode()
    )
    with pytest.raises(mail.MailFehler, match="kein Mailserver"):
        mail.verbindung_pruefen()


# --- Einladung beim Anlegen -------------------------------------------------------------


def neu(client, **daten):
    werte = {"username": "kim", "first_name": "Kim", "beschaeftigung": "ehrenamtlich",
             "rollen": [rollen.AUSGABE], **daten}  # fmt: skip
    return client.post(reverse("konten:mitarbeiter_neu"), werte)


def test_ohne_mailserver_keine_wahl(admin_client):
    assert (
        "Einladung per Mail"
        not in admin_client.get(reverse("konten:mitarbeiter_neu")).content.decode()
    )


def test_einladung_und_passwort_festlegen(admin_client, client, mailserver):
    assert neu(admin_client, zugang="einladung").context["form"].errors["email"]
    antwort = neu(admin_client, zugang="einladung", email="kim@example.org")
    kim = get_user_model().objects.get(username="kim")
    assert antwort.url == reverse("konten:mitarbeiter", args=[kim.pk])
    assert not kim.has_usable_password() and not kim.passwort_aendern
    nachricht = django_mail.outbox[0]
    assert nachricht.to == ["kim@example.org"] and "Benutzername: kim" in nachricht.body

    client.logout()
    link = link_aus(nachricht)
    formular = client.get(link, follow=True)
    assert "Benutzername: <strong>kim</strong>" in formular.content.decode()
    neu_pw = {"new_password1": "Eigenes-Passwort-5", "new_password2": "Eigenes-Passwort-5"}
    fertig = client.post(formular.redirect_chain[-1][0], neu_pw)
    assert fertig.url == reverse("konten:anmelden")
    kim.refresh_from_db()
    assert kim.check_password("Eigenes-Passwort-5")
    # Ein benutzter Link gilt nicht mehr.
    assert "abgelaufen oder wurde schon benutzt" in client.get(link, follow=True).content.decode()


def test_einladung_scheitert_dann_startpasswort(admin_client, mailserver, monkeypatch):
    def scheitern(*args, **kwargs):
        raise mail.MailFehler("Mailserver nicht erreichbar.")

    monkeypatch.setattr(mail, "senden", scheitern)
    antwort = neu(admin_client, zugang="einladung", email="kim@example.org")
    inhalt = antwort.content.decode()
    assert "Die Einladung konnte nicht gesendet werden" in inhalt
    assert antwort.context["passwort"] and "Startpasswort" in inhalt
    assert get_user_model().objects.get(username="kim").passwort_aendern


def test_link_senden_durch_admin(admin_client, benutzer_mit_rolle, mailserver):
    ziel = benutzer_mit_rolle("kim", rollen.AUSGABE)
    url = reverse("konten:link_senden", args=[ziel.pk])
    seite = reverse("konten:mitarbeiter", args=[ziel.pk])
    assert "Link zum neuen Passwort per Mail" not in admin_client.get(seite).content.decode()
    assert "keine E-Mail-Adresse" in admin_client.post(url, follow=True).content.decode()
    ziel.email = "kim@example.org"
    ziel.save()
    assert "Link zum neuen Passwort per Mail" in admin_client.get(seite).content.decode()
    assert "gesendet" in admin_client.post(url, follow=True).content.decode()
    assert "Neues Passwort für" in django_mail.outbox[0].subject


# --- Passwort vergessen ------------------------------------------------------------------


def test_vergessen_nur_mit_mailserver(client, admin):
    assert client.get(VERGESSEN).status_code == 404
    assert "Passwort vergessen?" not in client.get(reverse("konten:anmelden")).content.decode()


def test_vergessen(client, admin, benutzer_mit_rolle, mailserver):
    kim = benutzer_mit_rolle("kim", rollen.AUSGABE)
    kim.email = "kim@example.org"
    kim.save()
    assert "Passwort vergessen?" in client.get(reverse("konten:anmelden")).content.decode()
    assert "Link anfordern" in client.get(VERGESSEN).content.decode()
    for eingabe in ("niemand", "", "KIM@example.org", "kim"):
        antwort = client.post(VERGESSEN, {"eingabe": eingabe}, follow=True)
        assert "Falls es dazu ein Konto" in antwort.content.decode()
    # Unbekannt und leer senden nichts; der zweite Treffer kommt in die Fünf-Minuten-Sperre.
    assert len(django_mail.outbox) == 1
    assert django_mail.outbox[0].to == ["kim@example.org"]


def test_vergessen_mailfehler_bleibt_unsichtbar(client, admin, mailserver, monkeypatch, caplog):
    admin.email = "chefin@example.org"
    admin.save()

    def scheitern(*args, **kwargs):
        raise mail.MailFehler("weg")

    monkeypatch.setattr(mail, "senden", scheitern)
    antwort = client.post(VERGESSEN, {"eingabe": "chefin"}, follow=True)
    assert "Falls es dazu ein Konto" in antwort.content.decode()
    assert "Mail zum Zurücksetzen nicht gesendet" in caplog.text


@pytest.mark.parametrize(
    ("fehler", "text"),
    [
        (OSError(101, "Network is unreachable"), "fehlgeschlagen (Network is unreachable)"),
        (smtplib.SMTPDataError(554, b"abgelehnt"), "SMTPDataError: (554"),
    ],
)
def test_unbekannte_fehler_verstaendlich(fehler, text):
    assert text in mail._verstaendlich(fehler)


def test_imap_server_wird_abgelehnt(admin_client, admin):
    daten = {"server": "imap.example.org", "port": 465, "verschluesselung": "ssl"}
    seite = admin_client.post(MAIL_SEITE, daten).content.decode()
    assert "Server zum Abholen von Mails" in seite and "smtp.example.org" in seite
