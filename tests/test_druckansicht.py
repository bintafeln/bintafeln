"""Druckansicht für PDFs auf Tablets im Kiosk-Modus (ADR 0141). Alle Daten sind erfunden."""

import base64

import pytest
from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.test import Client
from django.urls import reverse

from apps.core import druckansicht
from apps.core.models import MailEinstellungen, TafelEinstellungen
from apps.kunden.models import Ausgabestelle

pytestmark = pytest.mark.django_db
AUSKUNFT = reverse("konten:meine_auskunft")  # ein PDF, das jedes persönliche Konto öffnen darf
SENDEN = reverse("core:druck_senden")
UMSCHALTEN = reverse("core:druck_umschalten")


@pytest.fixture
def mailserver(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    e = MailEinstellungen.laden()
    e.server, e.absender = "smtp.example.org", "absender@example.org"
    e.save()
    t = TafelEinstellungen.laden()
    t.name, t.email = "Muster-Tafel", "tafel@example.org"
    t.save()


def test_vorgabe_direkt_und_umschalten_je_geraet(admin_client):
    # persönliches Konto: wie bisher das PDF
    assert admin_client.get(AUSKUNFT)["Content-Type"] == "application/pdf"
    assert "direkt als PDF" in admin_client.get(reverse("konten:mein_konto")).content.decode()
    antwort = admin_client.post(UMSCHALTEN, {"an": "1", "zurueck": "https://boese.example/"})
    assert antwort.url == "/" and antwort.cookies[druckansicht.COOKIE].value == "1"
    seite = admin_client.get(AUSKUNFT)
    assert seite["Content-Type"].startswith("text/html")
    inhalt = seite.content.decode()
    assert "🖨 Drucken" in inhalt and "druck-seite" in inhalt and "data:image/png;base64," in inhalt
    assert 'download="' in inhalt and "← Zurück" in inhalt
    # nicht als Seite geöffnet (eingebettet) oder ausdrücklich roh: das PDF
    eingebettet = admin_client.get(AUSKUNFT, headers={"Sec-Fetch-Dest": "iframe"})
    assert eingebettet["Content-Type"] == "application/pdf"
    assert admin_client.get(AUSKUNFT, {"_pdf": "roh"})["Content-Type"] == "application/pdf"
    admin_client.post(UMSCHALTEN, {"an": "0"})
    assert admin_client.get(AUSKUNFT)["Content-Type"] == "application/pdf"


def test_ausgabestellen_konto_sieht_die_druckansicht(admin, anmelden):
    stelle = Ausgabestelle.objects.create(name="Mitte", email="mitte@example.org")
    konto = get_user_model().objects.create_user(username="tablet-mitte", stelle=stelle)
    c = anmelden(Client(), konto)
    request = type("R", (), {"COOKIES": {}, "user": konto})()
    assert druckansicht.aktiv(request)
    request.COOKIES = {druckansicht.COOKIE: "0"}
    assert not druckansicht.aktiv(request)
    assert "im Fenster über der Seite" in c.get(reverse("konten:mein_konto")).content.decode()


def test_mail_nur_mit_echtem_pdf_und_angebotener_adresse(admin_client, mailserver):
    admin_client.cookies[druckansicht.COOKIE] = "1"
    seite = admin_client.get(AUSKUNFT)
    kontext = seite.context_data
    adressen = [a for a, _ in kontext["empfaenger"]]
    assert adressen == ["tafel@example.org"] and kontext["mail_bereit"]
    pdf = base64.b64decode(kontext["pdf"])
    daten = {"pdf": kontext["pdf"], "signatur": kontext["signatur"],
             "dateiname": kontext["dateiname"], "an": "tafel@example.org"}  # fmt: skip
    antwort = admin_client.post(SENDEN, daten)
    assert "wurde an tafel@example.org gesendet" in antwort.content.decode()
    gesendet = django_mail.outbox[-1]
    assert gesendet.to == ["tafel@example.org"]
    assert gesendet.attachments[0][1] == pdf and gesendet.attachments[0][2] == "application/pdf"
    # nur angebotene Adressen, nur unverändert von bintafeln erzeugte PDFs
    fremd = admin_client.post(SENDEN, {**daten, "an": "jemand@example.org"})
    assert "angebotenen Adressen" in fremd.content.decode()
    falsch = base64.b64encode(pdf + b"x").decode()
    for kaputt in (falsch, "%%"):
        antwort = admin_client.post(SENDEN, {**daten, "pdf": kaputt})
        assert "nicht mehr gültig" in antwort.content.decode()
    assert len(django_mail.outbox) == 1


def test_grosse_oder_kaputte_pdfs_bleiben_pdfs(monkeypatch):
    assert druckansicht.seiten(b"kein pdf") is None
    from apps.core.pdf import Pdf

    doc = Pdf("Test", "zwei Seiten")
    for _ in range(80):
        doc.absatz("Zeile " * 40)
    inhalt = doc.erzeugen()
    assert len(druckansicht.seiten(inhalt)) >= 2
    monkeypatch.setattr(druckansicht, "HOECHSTENS_SEITEN", 1)
    assert druckansicht.seiten(inhalt) is None
    assert druckansicht.pruefen(inhalt, druckansicht.signieren(inhalt))
    assert not druckansicht.pruefen(inhalt, "falsch")


def test_pdf_fenster_holt_pdf_vorschau_und_mail(admin_client, mailserver):
    """PDF im Fenster über der Seite (App, Kiosk): abholen mit Signatur, Vorschau, Mail."""
    from django.core.files.uploadedfile import SimpleUploadedFile

    antwort = admin_client.get(
        AUSKUNFT, headers={"X-Bintafeln-Pdf": "1", "Sec-Fetch-Dest": "empty"}
    )
    assert antwort["Content-Type"] == "application/pdf"
    pdf, signatur = antwort.content, antwort["X-Pdf-Signatur"]
    assert druckansicht.pruefen(pdf, signatur) and antwort["X-Pdf-Name"].endswith(".pdf")
    # ohne die Kopfzeile: keine Signatur
    assert "X-Pdf-Signatur" not in admin_client.get(AUSKUNFT)

    def datei(inhalt=pdf):
        return SimpleUploadedFile("auskunft.pdf", inhalt, content_type="application/pdf")

    vorschau = reverse("core:druck_vorschau")
    seite = admin_client.post(vorschau, {"datei": datei(), "signatur": signatur})
    html = seite.content.decode()
    assert seite.status_code == 200 and "data-pdf-drucken" in html and "druck-seite" in html
    assert "tafel@example.org" in html  # Mail-Auswahl
    assert (
        admin_client.post(vorschau, {"datei": datei(pdf + b"x"), "signatur": signatur}).status_code
        == 400
    )
    daten = {
        "datei": datei(),
        "signatur": signatur,
        "dateiname": "a.pdf",
        "an": "tafel@example.org",
    }
    gesendet = admin_client.post(SENDEN, daten)
    assert "wurde an tafel@example.org gesendet" in gesendet.content.decode()
    assert django_mail.outbox[-1].attachments[0][1] == pdf


def test_pdf_fenster_kennzeichen_im_body(admin_client):
    assert 'data-pdf-fenster="1"' not in admin_client.get("/").content.decode()
    admin_client.cookies[druckansicht.COOKIE] = "1"
    seite = admin_client.get("/").content.decode()
    assert 'data-pdf-fenster="1"' in seite and reverse("core:druck_vorschau") in seite
