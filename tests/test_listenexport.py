"""Listen als PDF herunterladen und per E-Mail senden (ADR 0096)."""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core import geheimnis, listenexport
from apps.core.models import MailEinstellungen

pytestmark = pytest.mark.django_db

CSV = "﻿Name;Ort\r\nErika Beispiel;Musterstadt\r\n"


def _mailserver():
    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()


def test_pdf_aus_csv_ist_pdf():
    assert listenexport.pdf_aus_csv("Testliste", CSV)[:4] == b"%PDF"


def test_liste_als_pdf(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "pdf"})
    assert antwort.status_code == 200
    assert antwort["Content-Type"] == "application/pdf" and antwort.content[:4] == b"%PDF"


def test_liste_als_csv_unveraendert(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "csv"})
    assert "text/csv" in antwort["Content-Type"] and b"Beispiel" in antwort.content


def test_liste_per_mail_mit_pdf_und_csv(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    _mailserver()
    antwort = admin_client.get(
        reverse("adressen:liste"),
        {"aktion": "mail", "email": "buero@example.org", "weiter": reverse("adressen:liste")},
    )
    assert antwort.status_code == 302
    assert len(django_mail.outbox) == 1
    gesendet = django_mail.outbox[0]
    assert gesendet.to == ["buero@example.org"]
    namen = [anhang[0] for anhang in gesendet.attachments]
    assert len(namen) == 2
    assert any(n.endswith(".pdf") for n in namen) and any(n.endswith(".csv") for n in namen)


def test_mail_ohne_adresse_sendet_nicht(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    _mailserver()
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "mail", "email": ""})
    assert antwort.status_code == 302 and not django_mail.outbox


def test_pdf_laesst_ausgeblendete_spalten_weg(pdf_text):
    """Das PDF zeigt nur die Spalten, die nicht ausgeblendet sind; ohne Angabe alle."""
    from django.http import HttpResponse

    def text(*ohne):
        return pdf_text(
            HttpResponse(
                listenexport.pdf_aus_csv("Testliste", CSV, *ohne), content_type="application/pdf"
            )
        )

    alles = text()
    assert "Erika Beispiel" in alles and "Musterstadt" in alles
    ohne = text({"Ort"})
    assert "Erika Beispiel" in ohne and "Musterstadt" not in ohne and "Ort" not in ohne
    # blendet jemand alles aus, kommt lieber die ganze Liste als ein leeres Blatt
    assert "Musterstadt" in text({"Name", "Ort"})


def _pdf_woerter(pdf_text, antwort) -> str:
    """Der Text eines Listen-PDFs ohne Leerzeichen und Umbrüche: Schmale Spalten brechen Wörter
    mitten im Wort um, deshalb alle Textstücke aneinanderhängen."""
    import re

    return "".join(re.findall(r"\(((?:[^()\\]|\\.)*)\) Tj", pdf_text(antwort))).replace(" ", "")


def test_spaltenauswahl_gilt_im_pdf_jeder_liste(admin_client, admin, pdf_text, benutzer_mit_rolle):
    """In jeder Liste mit Spaltenauswahl folgt das PDF der eigenen Auswahl; die CSV-Datei behält
    alle Spalten."""
    from apps.konten import rollen
    from apps.kunden.models import Haushalt, Person
    from apps.mitglieder.models import Mitglied
    from apps.spenden.models import Spende

    # Team-Liste: Benutzername ausgeblendet
    benutzer_mit_rolle("erna.eifrig", rollen.AUSGABE)
    admin.listen_spalten_aus = {"mitarbeitende": ["benutzername", "rollen"],
                                "adressen": ["ort"], "mitglieder": ["art"],
                                "spenden": ["bezeichnung"]}  # fmt: skip
    admin.kundenliste_aus = ["nachname"]
    admin.antraege_liste_aus = ["email"]
    admin.save()
    url = reverse("konten:ehrenamtliche")
    text = _pdf_woerter(pdf_text, admin_client.get(url, {"aktion": "pdf"}))
    assert "Nachname" in text and "erna.eifrig" not in text and "Benutzername" not in text
    assert "Rollen" not in text and "Zwei-Faktor" in text  # sichtbare Spalte ist jetzt im Export
    csv_text = admin_client.get(url, {"aktion": "csv"}).content.decode("utf-8-sig")
    assert "Benutzername" in csv_text and "erna.eifrig" in csv_text  # CSV bleibt vollständig

    # Adressbuch: Ort ausgeblendet
    a = Adresse.objects.create(art="person", vorname="Otto", nachname="Ortlos", ort="Musterstadt",
                               strasse="Beispielweg 3")  # fmt: skip
    text = _pdf_woerter(pdf_text, admin_client.get(reverse("adressen:liste"), {"aktion": "pdf"}))
    assert "Ortlos" in text and "Beispielweg3" in text and "Musterstadt" not in text

    # Mitglieder: Art ausgeblendet
    Mitglied.objects.create(adresse=a, nummer="7", art="Fördermitglied", eintritt="2024-01-01")
    text = _pdf_woerter(pdf_text, admin_client.get(reverse("mitglieder:liste"), {"aktion": "pdf"}))
    assert "Ortlos" in text and "Fördermitglied" not in text

    # Spenden: Bezeichnung/Zweck ausgeblendet
    import datetime as dt

    Spende.objects.create(adresse=a, datum=dt.date.today(), art="geld", betrag=25,
                          beschreibung="Kollekte", zweck="Jugendarbeit")  # fmt: skip
    text = _pdf_woerter(pdf_text, admin_client.get(reverse("spenden:liste"), {"aktion": "pdf"}))
    assert "Ortlos" in text and "Kollekte" not in text and "Jugendarbeit" not in text

    # Kundenliste: Nachname ausgeblendet
    h = Haushalt.objects.create(kundennummer="00042")
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Geheimname")
    text = _pdf_woerter(
        pdf_text, admin_client.get(reverse("kunden:exportieren"), {"aktion": "pdf"})
    )
    assert "00042" in text and "Erika" in text and "Geheimname" not in text

    # Anträge: E-Mail ausgeblendet
    from apps.antraege.models import Antrag

    Antrag.objects.create(vorname="Anna", nachname="Antrag", email="anna@example.org")
    text = _pdf_woerter(pdf_text, admin_client.get(reverse("antraege:export"), {"aktion": "pdf"}))
    assert "Antrag" in text and "anna@example.org" not in text


def test_warteliste_spalten_passen_zum_export():
    """Die Spaltenauswahl der Warteliste trifft im PDF nur, wenn die Überschriften der Liste auch
    die des Exports sind."""
    from apps.core import listen
    from apps.warteliste import views

    assert {titel for _, titel in views.SPALTEN} <= set(views.EXPORT_KOPF)

    class Person:
        listen_spalten_aus = {"warteliste": ["wohnort", "termin"]}

    assert listen.pdf_ohne(Person(), "warteliste", dict(views.SPALTEN)) == {"Wohnort", "Termin"}


def test_listen_merken_filter_und_suche(admin_client, admin, benutzer_mit_rolle):
    """Wer aus einer Liste einen Eintrag öffnet und über „Zurück“ oder das Menü wiederkommt,
    findet Filter, Suche und Sortierung wie verlassen – bis „Zurücksetzen“."""
    from apps.core.models import TafelEinstellungen
    from apps.konten import rollen

    tafel = TafelEinstellungen.laden()
    tafel.module = ["tickets"]
    tafel.save()
    benutzer_mit_rolle("erna.eifrig", rollen.AUSGABE)
    faelle = [
        (reverse("adressen:liste"), "adressen", {"q": "Muster", "art": "person", "sort": "ort"},
         "sort=ort"),
        (reverse("mitglieder:liste"), "mitglieder", {"stand": "", "q": "Muster", "sort": "-name"},
         "sort=-name"),
        (reverse("spenden:liste"), "spenden", {"art": "geld", "q": "Muster", "sort": "betrag"},
         "sort=betrag"),
        (reverse("antraege:liste"), "antraege", {"ansicht": "alle", "suche": "Muster"},
         "ansicht=alle"),
        (reverse("konten:ehrenamtliche"), "team-ehrenamtliche", {"q": "erna", "sort": "ort"}, ""),
        (reverse("tickets:liste"), "tickets", {"status": "erledigt", "kategorie": ""}, ""),
    ]  # fmt: skip
    for url, liste, filter_, bleibt in faelle:
        assert admin_client.get(url).status_code == 200, liste  # noch nichts gemerkt
        seite = admin_client.get(url, filter_)
        assert seite.status_code == 200, liste
        assert "filter=zuruecksetzen" in seite.content.decode(), liste
        zurueck = admin_client.get(url)  # „Zurück“ oder Menü: ohne Angaben
        assert zurueck.status_code == 302, liste
        for name, wert in filter_.items():
            assert f"{name}={wert}" in zurueck.url, (liste, name)
        # die Suche beim Tippen (htmx) wird nie umgeleitet
        assert admin_client.get(url, HTTP_HX_REQUEST="true").status_code == 200, liste
        # „Zurücksetzen“ vergisst die Filter; was der Knopf behält (Sortierung), bleibt
        behalten = dict(p.split("=") for p in bleibt.split("&") if p)
        antwort = admin_client.get(url, {**behalten, "filter": "zuruecksetzen"})
        assert antwort.url == (f"{url}?{bleibt}" if bleibt else url), liste
        admin.refresh_from_db()
        assert admin.listen_filter.get(liste, "") == bleibt, liste
    # eine andere Person hat ihre eigenen Filter
    andere = get_user_model().objects.get(username="erna.eifrig")
    assert "adressen" not in (andere.listen_filter or {})
