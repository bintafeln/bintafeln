"""Tickets (ADR 0087), nur erfundene Daten."""

import datetime as dt

import pytest
from django.contrib.auth.models import Group
from django.core import mail as django_mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.core import privatdateien
from apps.core.models import MailEinstellungen, PapierkorbEintrag, TafelEinstellungen
from apps.konten import rollen
from apps.tickets import ablauf
from apps.tickets.models import Anhang, Kategorie, Ticket, TicketEinstellungen

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def modul(settings):
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    t = TafelEinstellungen.laden()
    t.module = ["tickets"]
    t.save()
    e = MailEinstellungen.laden()
    e.server, e.absender = "smtp.example.org", "tafel@example.org"
    e.save()


@pytest.fixture
def leute(admin, benutzer_mit_rolle):
    melder = benutzer_mit_rolle("anton", rollen.AUSGABE)
    technik = benutzer_mit_rolle("theo", rollen.AUSGABE)
    fremd = benutzer_mit_rolle("frieda", rollen.AUSGABE)
    for b, mail in ((melder, "anton@example.org"), (technik, "theo@example.org"),
                    (fremd, "frieda@example.org")):  # fmt: skip
        b.email = mail
        b.save()
    k = Kategorie.objects.create(name="Technik und Geräte")
    k.personen.add(technik)
    k.rollen.add(Group.objects.get(name=rollen.BUERO))
    return melder, technik, fremd, k


def test_eroeffnen_benachrichtigt_kategorie(
    client, anmelden, leute, django_capture_on_commit_callbacks
):
    melder, technik, fremd, k = leute
    anmelden(client, melder)
    seite = client.get(reverse("tickets:neu")).content.decode()
    assert "Technik und Geräte" in seite and 'name="dateien"' in seite
    foto = SimpleUploadedFile("kuehlung.pdf", b"%PDF-1.4 erfunden", content_type="application/pdf")
    with django_capture_on_commit_callbacks(execute=True):
        antwort = client.post(reverse("tickets:neu"), {
            "kategorie": k.pk, "titel": "Kühlschrank 2 brummt", "beschreibung": "Seit Montag laut.",
            "dateien": [foto]})  # fmt: skip
    t = Ticket.objects.get()
    assert antwort.status_code == 302 and t.erstellt_von == melder and t.status == "offen"
    a = Anhang.objects.get()
    assert privatdateien.lesen(Anhang.ORDNER, a.datei) == b"%PDF-1.4 erfunden"
    assert b"%PDF" not in privatdateien.pfad(Anhang.ORDNER, a.datei).read_bytes()  # verschlüsselt
    gesendet = django_mail.outbox[0]
    assert gesendet.to == ["theo@example.org"]  # Kategorie, nicht die meldende Person
    assert "Kühlschrank 2 brummt" in gesendet.subject and "/tickets/" in gesendet.body
    assert client.get(reverse("tickets:anhang", args=[a.pk])).content == b"%PDF-1.4 erfunden"

    # Fremde sehen das Ticket nicht
    anmelden(client, fremd)
    assert "Kühlschrank" not in client.get(reverse("tickets:liste")).content.decode()
    assert client.get(reverse("tickets:ticket", args=[t.pk])).status_code == 404
    assert client.get(reverse("tickets:anhang", args=[a.pk])).status_code == 404


def test_zustaendige_antworten_und_status(
    client, anmelden, leute, django_capture_on_commit_callbacks
):
    melder, technik, fremd, k = leute
    t = Ticket.objects.create(kategorie=k, titel="Waage defekt", beschreibung="Zeigt nichts.",
                              erstellt_von=melder)  # fmt: skip
    anmelden(client, technik)
    url = reverse("tickets:ticket", args=[t.pk])
    seite = client.get(url).content.decode()
    assert "Waage defekt" in seite and 'name="aendern"' in seite and 'name="zustaendig"' in seite
    with django_capture_on_commit_callbacks(execute=True):
        client.post(url, {"kommentar": "1", "text": "Schaue ich mir Donnerstag an."})
        client.post(url, {"aendern": "1", "status": "in_arbeit", "zustaendig": technik.pk})
    t.refresh_from_db()
    assert t.status == "in_arbeit" and t.zustaendig == technik
    assert [m.to for m in django_mail.outbox] == [["anton@example.org"], ["anton@example.org"]]
    assert "Donnerstag" in django_mail.outbox[0].body and "in Arbeit" in django_mail.outbox[1].body
    assert ablauf.ticket_offen(str(t.pk)) is False  # übernommen: „neu“-Meldung entfällt

    # Meldende Person darf antworten, aber nicht den Status ändern
    anmelden(client, melder)
    seite = client.get(url).content.decode()
    assert 'name="aendern"' not in seite and "Schaue ich mir Donnerstag an." in seite
    assert client.post(url, {"aendern": "1", "status": "erledigt"}).status_code == 404
    with django_capture_on_commit_callbacks(execute=True):
        client.post(url, {"kommentar": "1", "text": "Danke!"})
    assert django_mail.outbox[-1].to == ["theo@example.org"]  # Zuständiger erfährt die Antwort


def test_buero_sieht_alle_und_loescht_in_papierkorb(client, anmelden, leute, benutzer_mit_rolle):
    melder, _, _, k = leute
    t = Ticket.objects.create(
        kategorie=k, titel="Tür klemmt", beschreibung="x", erstellt_von=melder
    )
    buero = benutzer_mit_rolle("berta", rollen.BUERO)
    anmelden(client, buero)
    assert "Tür klemmt" in client.get(reverse("tickets:liste")).content.decode()
    client.post(reverse("tickets:loeschen", args=[t.pk]))
    assert not Ticket.objects.exists() and PapierkorbEintrag.objects.get().art == "Ticket"


def test_erledigte_nach_frist_geloescht(leute):
    melder, _, _, k = leute
    alt = Ticket.objects.create(kategorie=k, titel="alt", beschreibung="x", status="erledigt",
                                erledigt_am=timezone.now() - dt.timedelta(days=400))  # fmt: skip
    Ticket.objects.create(kategorie=k, titel="neu", beschreibung="x", status="erledigt",
                          erledigt_am=timezone.now())  # fmt: skip
    Ticket.objects.create(kategorie=k, titel="offen", beschreibung="x")
    assert ablauf.fristen_anwenden() == 1
    assert not Ticket.objects.filter(pk=alt.pk).exists() and Ticket.objects.count() == 2
    e = TicketEinstellungen.laden()
    e.loeschen_nach_tagen = 0
    e.save()
    assert ablauf.fristen_anwenden(timezone.localdate() + dt.timedelta(days=1)) == 1


def test_kategorien_nur_mit_recht(client, admin, anmelden, leute):
    melder, technik, _, k = leute
    anmelden(client, melder)
    assert client.get(reverse("tickets:kategorien")).status_code == 403
    admin_client = anmelden(client, admin)  # derselbe Client, jetzt als Admin
    seite = admin_client.get(reverse("tickets:kategorien")).content.decode()
    assert "Technik und Geräte" in seite and "Büro" in seite
    admin_client.post(reverse("tickets:kategorie_neu"), {
        "name": "Fahrzeuge", "beschreibung": "Transporter", "personen": [technik.pk],
        "aktiv": "on", "reihenfolge": "1"})  # fmt: skip
    neu = Kategorie.objects.get(name="Fahrzeuge")
    assert list(neu.personen.all()) == [technik]
    seite = admin_client.get(reverse("tickets:kategorie", args=[neu.pk])).content.decode()
    assert "data-mehrfach" in seite  # Personen und Rollen als Auswahlmenü


def test_benachrichtigung_einstellbar_und_auskunft(client, anmelden, leute, pdf_text):
    melder, technik, _, k = leute
    anmelden(client, technik)
    seite = client.get(reverse("konten:benachrichtigungen")).content.decode()
    assert "Neues Ticket in meiner Kategorie" in seite
    Ticket.objects.create(
        kategorie=k, titel="Licht im Lager", beschreibung="x", erstellt_von=melder
    )
    anmelden(client, melder)
    text = pdf_text(client.get(reverse("konten:meine_auskunft")))
    assert "Tickets" in text and "Licht im Lager" in text
