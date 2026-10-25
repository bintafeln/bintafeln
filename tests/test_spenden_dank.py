"""Dankesbriefe an Spender und hochgeladene Belege (ADR 0056). Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.core import mail as postfach
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core import geheimnis
from apps.core.models import MailEinstellungen
from apps.core.pdf import Pdf
from apps.konten import rollen
from apps.serienbriefe.models import Versand, Vorlage
from apps.spenden import dank
from apps.spenden.models import Spende, SpendenBeleg, SpendenEinstellungen

pytestmark = pytest.mark.django_db
JAHR = 2025


def pdf_datei(name, text="Beleg aus dem Vereinsportal"):
    doc = Pdf(text)
    return SimpleUploadedFile(name, doc.erzeugen(), content_type="application/pdf")


@pytest.fixture
def einstellungen():
    e = SpendenEinstellungen.laden()
    e.zwecke = "mildtätiger Zwecke im Sinne des § 53 AO"
    e.finanzamt, e.steuernummer = "Musterstadt", "12/345/67890"
    e.bescheid_vom, e.veranlagungszeitraum = dt.date(2025, 3, 1), "2021 bis 2023"
    e.unterzeichnet_von = "Erika Muster, Kassenwartin"
    e.save()
    return e


@pytest.fixture
def vorlage():
    return Vorlage.objects.create(name="Dank", betreff="Danke für Ihre Spende",
                                  text="{anrede}\n\nvielen Dank für {anzahl_spenden} Spende(n) am "
                                       "{spendendaten} über {spendensumme}.")  # fmt: skip


@pytest.fixture
def spender():
    einmal = Adresse.objects.create(art="person", anrede="Herr", vorname="Max", nachname="Probe",
                                    strasse="Weg 2", plz="12345", ort="Musterstadt")  # fmt: skip
    oft = Adresse.objects.create(art="person", anrede="Frau", vorname="Erika", nachname="Muster",
                                 strasse="Weg 3", plz="12345", ort="Musterstadt",
                                 email="erika@example.org",
                                 einwilligung_email=dt.date(2025, 1, 1))  # fmt: skip
    Spende.objects.create(adresse=einmal, datum=dt.date(JAHR, 3, 1), betrag=Decimal("50"),
                          belegnummer="MV-000123")  # fmt: skip
    for monat in (1, 2):
        Spende.objects.create(adresse=oft, datum=dt.date(JAHR, monat, 15), betrag=Decimal("25"))
    Spende.objects.create(adresse=oft, datum=dt.date(JAHR - 1, 5, 1), betrag=Decimal("9"))
    return einmal, oft


def test_auswahl(spender):
    einmal, oft = spender
    assert [d.adresse for d in dank.auswahl(JAHR)] == [oft, einmal]
    assert [d.adresse for d in dank.auswahl(JAHR, "einfach")] == [einmal]
    mehrfach = dank.auswahl(JAHR, "mehrfach")
    assert [d.adresse for d in mehrfach] == [oft] and mehrfach[0].anzahl_im_jahr == 2
    assert mehrfach[0].per_mail and not dank.auswahl(JAHR, "einfach")[0].per_mail
    Spende.objects.filter(adresse=oft, datum__month=1).update(bedankt_am=dt.date(JAHR, 2, 1))
    d = dank.auswahl(JAHR, "mehrfach")[0]
    assert len(d.spenden) == 1 and d.anzahl_im_jahr == 2  # zählt weiter als Mehrfachspender
    assert len(dank.auswahl(JAHR, "mehrfach", nur_offen=False)[0].spenden) == 2
    e = dank.werte(d, JAHR)
    assert e.werte["anzahl_spenden"] == 2 and e.werte["spendendaten"] == "15.02.2025"


def test_belege_zuordnen(admin_client, spender):
    einmal, oft = spender
    assert dank.zuordnen("Spendenbeleg_000123.pdf").adresse == einmal
    assert dank.zuordnen("ohne-nummer.pdf") is None
    assert dank.zuordnen("Beleg_999.pdf") is None
    url = reverse("spenden:belege") + f"?jahr={JAHR}"
    antwort = admin_client.post(url, {"aktion": "hochladen", "dateien": [
        pdf_datei("Spendenbeleg_000123.pdf"), pdf_datei("Sammelbescheinigung_Muster.pdf"),
        SimpleUploadedFile("bild.png", b"x", content_type="image/png"),
    ]}, follow=True)  # fmt: skip
    seite = antwort.content.decode()
    assert "1 Beleg(e) über die Belegnummer zugeordnet, 1 bitte von Hand" in seite
    assert "bild.png" in seite  # Fehlermeldung
    zugeordnet = SpendenBeleg.objects.get(dateiname="Spendenbeleg_000123.pdf")
    assert zugeordnet.adresse == einmal and zugeordnet.spende.belegnummer == "MV-000123"
    offen = SpendenBeleg.objects.get(adresse__isnull=True)
    assert offen.jahr == JAHR and "Noch zuzuordnen" in seite
    admin_client.post(url, {"aktion": "zuordnen", "beleg": offen.pk, "adresse": oft.pk})
    offen.refresh_from_db()
    assert offen.adresse == oft
    admin_client.post(url, {"aktion": "zuordnen", "beleg": offen.pk, "adresse": ""})
    offen.refresh_from_db()
    assert offen.adresse == oft  # ohne Auswahl keine Änderung
    antwort = admin_client.get(reverse("spenden:beleg", args=[offen.pk]))
    assert antwort["Content-Type"] == "application/pdf"
    admin_client.post(url, {"aktion": "loeschen", "beleg": zugeordnet.pk})
    assert not SpendenBeleg.objects.filter(pk=zugeordnet.pk).exists()
    SpendenBeleg.objects.filter(pk=offen.pk).update(datei="fehlt.bin")
    assert admin_client.get(reverse("spenden:beleg", args=[offen.pk])).status_code == 404
    assert "Belege hochladen" in admin_client.get(url).content.decode()


def test_dankesbriefe_als_pdf(admin_client, einstellungen, vorlage, spender, pdf_text):
    einmal, oft = spender
    admin_client.post(
        reverse("spenden:belege") + f"?jahr={JAHR}",
        {"aktion": "hochladen", "dateien": [pdf_datei("Spendenbeleg_123.pdf")]},
    )
    SpendenBeleg.objects.create(adresse=einmal, jahr=JAHR, dateiname="kaputt",
                                datei=_kaputt())  # fmt: skip
    url = reverse("spenden:dank")
    assert "Dankesbriefe an Spender" in admin_client.get(url).content.decode()
    daten = {"vorlage": vorlage.pk, "jahr": JAHR, "art": "alle", "nur_offen": "on",
             "mit_bestaetigungen": "on", "mit_belegen": "on"}  # fmt: skip
    seite = admin_client.post(url, daten | {"schritt": "vorschau"}).content.decode()
    assert "2 Spender" in seite and "wird ausgestellt" in seite and "2 Briefe als PDF" in seite
    antwort = admin_client.post(url, daten | {"schritt": "pdf"})
    text = pdf_text(antwort)
    assert "Sehr geehrte Frau Muster" in text and "2 Spende(n) am 15.01.2025, 15.02.2025" in text
    assert "Sammelbest" in text and "Beleg aus dem Vereinsportal" in text
    assert Spende.objects.filter(datum__year=JAHR, bedankt_am__isnull=True).count() == 0
    assert not Spende.objects.filter(datum__year=JAHR, bestaetigung__isnull=True).exists()
    assert SpendenBeleg.objects.get(dateiname="Spendenbeleg_123.pdf").beigelegt_am is not None
    v = Versand.objects.get()
    assert v.anzahl == 2 and v.art == Versand.Art.BRIEF and "Dankesbriefe 2025" in v.auswahl
    seite = admin_client.post(url, daten | {"schritt": "vorschau"}).content.decode()
    assert "0 Spender" in seite and "Keine passenden Spenden" in seite
    auskunft = pdf_text(admin_client.get(reverse("adressen:auskunft", args=[einmal.pk])))
    assert "Hochgeladene Spendenbelege" in auskunft and "Spendenbeleg_123.pdf" in auskunft


def _kaputt():
    from apps.core import privatdateien

    return privatdateien.speichern(SpendenBeleg.ORDNER, SimpleUploadedFile(
        "k.pdf", b"kein pdf", content_type="application/pdf"))  # fmt: skip


def test_kaputter_beleg_gibt_warnung(einstellungen, vorlage, spender):
    einmal, _ = spender
    SpendenBeleg.objects.create(adresse=einmal, jahr=JAHR, dateiname="kaputt", datei=_kaputt())
    danke = dank.auswahl(JAHR, "einfach")
    inhalt, warnungen = dank.briefe(danke, vorlage, JAHR, mit_bestaetigungen=False)
    assert inhalt.startswith(b"%PDF") and warnungen == [
        "Max Probe: „kaputt.pdf“ ist kein lesbares PDF."
    ]
    assert dank.anlagen(danke[0], False, False) == []


def test_fehlende_angaben(admin_client, vorlage, spender):
    daten = {"vorlage": vorlage.pk, "jahr": JAHR, "art": "alle", "nur_offen": "on",
             "mit_bestaetigungen": "on", "schritt": "pdf"}  # fmt: skip
    seite = admin_client.post(reverse("spenden:dank"), daten).content.decode()
    assert "fehlen noch Angaben" in seite
    assert not Spende.objects.filter(bedankt_am__isnull=False).exists()
    # ohne Bestätigungen geht es trotzdem
    del daten["mit_bestaetigungen"]
    antwort = admin_client.post(reverse("spenden:dank"), daten)
    assert antwort["Content-Type"] == "application/pdf"


def test_per_mail_mit_anhang(admin_client, einstellungen, vorlage, spender):
    einmal, oft = spender
    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()
    daten = {"vorlage": vorlage.pk, "jahr": JAHR, "art": "alle", "nur_offen": "on",
             "mit_bestaetigungen": "on", "mit_belegen": "on", "mail": "on"}  # fmt: skip
    seite = admin_client.post(reverse("spenden:dank"), daten | {"schritt": "vorschau"})
    seite = seite.content.decode()
    assert "1 E-Mail senden" in seite and "1 Brief als PDF" in seite
    seite = admin_client.post(reverse("spenden:dank"), daten | {"schritt": "senden"})
    assert "1 Dankesbrief per E-Mail gesendet" in seite.content.decode()
    nachricht = postfach.outbox[0]
    assert nachricht.to == ["erika@example.org"] and "Sehr geehrte Frau Muster" in nachricht.body
    assert nachricht.attachments[0][0].startswith("Zuwendungsbestaetigung-")
    assert (
        Spende.objects.filter(adresse=oft, datum__year=JAHR, bedankt_am__isnull=True).count() == 0
    )
    assert Spende.objects.filter(adresse=einmal, bedankt_am__isnull=True).count() == 1
    assert Versand.objects.get().art == Versand.Art.EMAIL


def test_mailfehler(admin_client, einstellungen, vorlage, spender, monkeypatch):
    from apps.core import mail

    MailEinstellungen.objects.update(
        server="mail.example.org",
        port=587,
        benutzer="x",
        absender="t@example.org",
        passwort_verschluesselt=geheimnis.verschluesseln("x"),
    )

    def kaputt(*a, **k):
        raise mail.MailFehler("Mailserver nicht erreichbar.")

    monkeypatch.setattr(mail, "senden", kaputt)
    Adresse.objects.update(email="a@example.org", einwilligung_email=dt.date(2025, 1, 1))
    daten = {"vorlage": vorlage.pk, "jahr": JAHR, "art": "alle", "nur_offen": "on", "mail": "on",
             "schritt": "senden"}  # fmt: skip
    seite = admin_client.post(reverse("spenden:dank"), daten).content.decode()
    assert "Nicht gesendet" in seite and not Versand.objects.exists()


def test_mail_ohne_mailserver(admin_client, vorlage, spender):
    daten = {"vorlage": vorlage.pk, "jahr": JAHR, "art": "alle", "nur_offen": "on", "mail": "on",
             "schritt": "vorschau"}  # fmt: skip
    seite = admin_client.post(reverse("spenden:dank"), daten).content.decode()
    assert "zuerst unter „Einstellungen → Tafel → E-Mail“" in seite


def test_rechte(admin, benutzer_mit_rolle, anmelden):
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    for name in ("spenden:dank", "spenden:belege"):
        assert c.get(reverse(name)).status_code == 403
    b = anmelden(Client(), benutzer_mit_rolle("berta", rollen.BUERO))
    assert b.get(reverse("spenden:dank")).status_code == 200
