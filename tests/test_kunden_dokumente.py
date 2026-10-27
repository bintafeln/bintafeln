"""Dokumente zu Haushalten (ADR 0030). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from auditlog.models import LogEntry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.core import papierkorb, privatdateien
from apps.core.models import PapierkorbEintrag
from apps.konten import rollen
from apps.kunden import importieren
from apps.kunden.models import (
    Dokumentart,
    Haushalt,
    HaushaltDokument,
    Person,
    Zugriff,
    abgelaufene_dokumente_loeschen,
    fristen_anwenden,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def h():
    h = Haushalt.objects.create(kundennummer="3001")
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Probe")
    return h


@pytest.fixture
def bescheid():
    return Dokumentart.objects.get(bezeichnung="Bescheid")


def pdf(inhalt=b"%PDF erfundener Bescheid"):
    return SimpleUploadedFile("b.pdf", inhalt, content_type="application/pdf")


def hochladen(client, h, dokumentart, **daten):
    return client.post(
        reverse("kunden:dokument_hochladen", args=[h.kundennummer]),
        {"art": dokumentart.pk, "titel": "", "datum": "", "datei": pdf(), **daten},
        follow=True,
    )


def test_vorgaben_aus_migration():
    assert {a.bezeichnung: a.aufbewahren_monate for a in Dokumentart.objects.all()} == {
        "Bescheid": 24,
        "Datenschutzeinwilligung": 36,
        "Sonstiges": 12,
    }


def test_hochladen_ansehen_loeschen(admin_client, h, bescheid, django_capture_on_commit_callbacks):
    inhalt = hochladen(admin_client, h, bescheid, datum="2026-03-15").content.decode()
    assert "verschlüsselt gespeichert, wird am 15.03.2028 gelöscht" in inhalt
    d = HaushaltDokument.objects.get()
    assert (d.kundennummer, d.titel, d.typ, d.hochgeladen_von) == (
        "3001", "Bescheid", "application/pdf", "chefin"
    )  # fmt: skip
    datei = privatdateien.pfad(HaushaltDokument.ORDNER, d.datei)
    assert b"erfundener Bescheid" not in datei.read_bytes()

    seite = admin_client.get(reverse("kunden:haushalt", args=["3001"])).content.decode()
    assert "Dokumente" in seite and "15.03.2028" in seite

    vorher = Zugriff.objects.count()
    antwort = admin_client.get(reverse("kunden:dokument", args=[d.pk]))
    assert antwort.content == b"%PDF erfundener Bescheid"
    assert antwort["Content-Type"] == "application/pdf"
    assert Zugriff.objects.count() == vorher + 1
    assert LogEntry.objects.get_for_object(d).filter(action=LogEntry.Action.ACCESS).count() == 1

    admin_client.post(reverse("kunden:dokument_loeschen", args=[d.pk]))
    assert not HaushaltDokument.objects.exists()
    # Die Datei bleibt im Papierkorb, bis er geleert wird (ADR 0073)
    assert datei.exists()
    with django_capture_on_commit_callbacks(execute=True):
        papierkorb.endgueltig_loeschen(PapierkorbEintrag.objects.get())
    assert not datei.exists()
    assert admin_client.get(reverse("kunden:dokument", args=[d.pk])).status_code == 404


def test_eigener_titel_und_fehler(admin_client, h, bescheid):
    hochladen(admin_client, h, bescheid, titel="Wohngeld 2026")
    assert HaushaltDokument.objects.get().titel == "Wohngeld 2026"
    falsch = SimpleUploadedFile("x.txt", b"x", content_type="text/plain")
    inhalt = hochladen(admin_client, h, bescheid, datei=falsch).content.decode()
    assert "PDF" in inhalt
    inhalt = hochladen(admin_client, h, bescheid, art="").content.decode()
    assert "Dokumentart und Datei sind Pflicht" in inhalt
    assert HaushaltDokument.objects.count() == 1


def test_fehlende_datei_gibt_404(admin_client, h, bescheid):
    hochladen(admin_client, h, bescheid)
    d = HaushaltDokument.objects.get()
    privatdateien.loeschen(HaushaltDokument.ORDNER, d.datei)
    assert admin_client.get(reverse("kunden:dokument", args=[d.pk])).status_code == 404


def test_nur_admin_und_buero(client, admin, benutzer_mit_rolle, anmelden, h, bescheid):
    d = HaushaltDokument.objects.create(kundennummer="3001", art=bescheid, titel="T")
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    seite = client.get(reverse("kunden:haushalt", args=["3001"])).content.decode()
    assert "Dokument hochladen" not in seite
    assert client.get(reverse("kunden:dokument", args=[d.pk])).status_code == 403
    assert client.post(reverse("kunden:dokument_loeschen", args=[d.pk])).status_code == 403
    antwort = client.post(reverse("kunden:dokument_hochladen", args=["3001"]))
    assert antwort.status_code == 403

    client.logout()
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert hochladen(client, h, bescheid).status_code == 200
    assert HaushaltDokument.objects.count() == 2


def test_frist_je_dokumentart(h, bescheid):
    heute = dt.date(2026, 10, 24)
    mit_datum = HaushaltDokument.objects.create(
        kundennummer="3001", art=bescheid, titel="alt", datum=dt.date(2024, 10, 24)
    )
    ohne_datum = HaushaltDokument.objects.create(
        kundennummer="3001", art=bescheid, titel="neu",
        hochgeladen_am=timezone.make_aware(dt.datetime(2025, 1, 31, 12)),
    )  # fmt: skip
    assert mit_datum.loeschen_am == dt.date(2026, 10, 24)
    assert ohne_datum.loeschen_am == dt.date(2027, 1, 31)
    assert abgelaufene_dokumente_loeschen(heute) == 1
    assert list(HaushaltDokument.objects.values_list("titel", flat=True)) == ["neu"]

    bescheid.aufbewahren_monate = 1  # eine kürzere Frist gilt auch für Vorhandenes
    bescheid.save()
    assert fristen_anwenden() >= 1
    assert not HaushaltDokument.objects.exists()


def test_monatsende_bei_kurzem_monat(bescheid):
    d = HaushaltDokument(art=bescheid, datum=dt.date(2026, 3, 31))
    bescheid.aufbewahren_monate = 11
    assert d.loeschen_am == dt.date(2027, 2, 28)


def test_import_behaelt_dokumente(h, bescheid):
    HaushaltDokument.objects.create(kundennummer="3001", art=bescheid, titel="T")
    ergebnis = importieren.pruefen({"haushalte.csv": b"kundennummer;nachname;vorname\n9;A;B\n"})
    importieren.uebernehmen(
        ergebnis.daten, benutzer=None, dateien=ergebnis.dateien,
        pruefsumme=ergebnis.pruefsumme, anzahl_warnungen=0,
    )  # fmt: skip
    assert list(Haushalt.objects.values_list("kundennummer", flat=True)) == ["9"]
    assert HaushaltDokument.objects.filter(kundennummer="3001").exists()


def test_haushalt_loeschen_entfernt_dokumente(
    admin_client, h, bescheid, django_capture_on_commit_callbacks
):
    hochladen(admin_client, h, bescheid)
    d = HaushaltDokument.objects.get()
    datei = privatdateien.pfad(HaushaltDokument.ORDNER, d.datei)
    url = reverse("kunden:haushalt_loeschen", args=["3001"])
    assert "Dokumente" in admin_client.get(url).content.decode()
    with django_capture_on_commit_callbacks(execute=True):
        admin_client.post(url)
    assert not HaushaltDokument.objects.exists()
    # Die Datei bleibt im Papierkorb, bis er geleert wird (ADR 0073)
    assert datei.exists()
    with django_capture_on_commit_callbacks(execute=True):
        papierkorb.endgueltig_loeschen(PapierkorbEintrag.objects.get())
    assert not datei.exists()


def test_dokumentarten_pflegen(admin_client):
    inhalt = admin_client.get(reverse("kunden:liste", args=["dokumentarten"])).content.decode()
    assert (
        "Bescheid</a></td>" in inhalt and '<td data-titel="Aufbewahren (Monate)">24</td>' in inhalt
    )
    admin_client.post(
        reverse("kunden:listeneintrag_neu", args=["dokumentarten"]),
        {"bezeichnung": "Mietvertrag", "aufbewahren_monate": 6, "aktiv": "on"},
    )
    assert Dokumentart.objects.get(bezeichnung="Mietvertrag").aufbewahren_monate == 6
    assert "Dokumentarten" in admin_client.get("/").content.decode()


def test_auskunft_nennt_dokumente(admin_client, h, bescheid, pdf_text):
    HaushaltDokument.objects.create(
        kundennummer="3001", art=bescheid, titel="Wohngeldbescheid", datum=dt.date(2026, 3, 1)
    )
    text = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["3001"])))
    assert "Wohngeldbescheid" in text and "01.03.2028" in text


def test_kundennummer_aendern_nimmt_dokumente_mit(admin_client, h, bescheid):
    HaushaltDokument.objects.create(kundennummer="3001", art=bescheid, titel="T")
    admin_client.post(
        reverse("kunden:bearbeiten", args=["3001"]), {"kundennummer": "3009", "status": "aktiv"}
    )
    assert Haushalt.objects.get().kundennummer == "3009"
    assert HaushaltDokument.objects.get().kundennummer == "3009"
