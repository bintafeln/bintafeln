"""Sicherungsaufträge in der Oberfläche (ADR 0042). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core import sicherung
from apps.core.forms import SicherungsAuftragForm
from apps.core.models import SicherungsAuftrag, SicherungsDienst
from apps.konten import rollen

pytestmark = pytest.mark.django_db
URL = reverse("core:sicherungen")


@pytest.fixture
def dienst():
    d = SicherungsDienst.laden()
    d.letzter_kontakt = timezone.now()
    d.schluessel_ok = True
    d.ziele = "/media/usb|1048576|2097152\n/mnt/nas|10|20"
    d.save()
    return d


def standard():
    return SicherungsAuftrag.objects.get(standard=True)


def test_standard_auftrag_aus_migration():
    a = standard()
    assert (a.uhrzeit, a.anzahl, a.tage, a.ziel, a.aktiv) == (dt.time(2, 30), 14, None, "", True)
    assert a.tage_namen == "täglich"
    a.wochentage = "12345"
    assert a.tage_namen == "Mo–Fr"
    a.wochentage = "67"
    assert a.tage_namen == "Sa, So"
    a.staende = "2026-10-25_023000|2048\n2026-10-24_023000|1024"
    assert a.staende_liste == [("2026-10-25_023000", 2048 * 1024), ("2026-10-24_023000", 1024**2)]


def test_dienst_status(dienst):
    assert sicherung.dienst_status().erreichbar
    spaeter = timezone.now() + dt.timedelta(minutes=5)
    assert not sicherung.dienst_status(spaeter).erreichbar
    assert dienst.ziele_liste()[0] == ("/media/usb", 1024**3, 2 * 1024**3)
    SicherungsDienst.objects.all().delete()
    assert sicherung.dienst_status() == sicherung.DienstStatus(False, None, False)


def test_seite_und_jetzt(admin_client, admin, dienst):
    seite = admin_client.get(URL).content.decode()
    assert "Tägliche Sicherung auf dem Server" in seite and "Sicherungen</a>" in seite
    assert "meldet sich nicht" not in seite and "every 5s" not in seite
    antwort = admin_client.post(reverse("core:sicherung_jetzt", args=[standard().pk]), follow=True)
    inhalt = antwort.content.decode()
    assert "startet in wenigen Sekunden" in inhalt and "every 5s" in inhalt
    a = standard()
    assert a.angefordert_am and a.angefordert_von == "chefin"
    # Mit HTMX nur die Liste (für das Nachladen alle 5 Sekunden)
    liste = admin_client.get(URL, HTTP_HX_REQUEST="true").content.decode()
    assert "<html" not in liste and "startet gleich" in liste and "disabled" in liste
    a.angefordert_am, a.laeuft_seit = None, timezone.now()
    a.save()
    assert "Sicherung läuft seit" in admin_client.get(URL).content.decode()
    a.laeuft_seit, a.ergebnis, a.meldung = None, "fehler", "Platte voll"
    a.letzter_versuch = timezone.now()
    a.save()
    assert "Platte voll" in admin_client.get(URL).content.decode()


def test_hinweise_ohne_dienst_oder_schluessel(admin_client, dienst):
    dienst.schluessel_ok = False
    dienst.save()
    assert "noch kein Sicherungsschlüssel" in admin_client.get(URL).content.decode()
    dienst.letzter_kontakt = timezone.now() - dt.timedelta(hours=1)
    dienst.save()
    assert "meldet sich nicht" in admin_client.get(URL).content.decode()


def test_auftrag_anlegen_bearbeiten_loeschen(admin_client, dienst):
    neu = reverse("core:sicherungsauftrag_neu")
    formular = admin_client.get(neu).content.decode()
    assert "/media/usb (frei: 1,0" in formular and "/mnt/nas" in formular
    daten = {"name": "USB", "ziel": "/media/usb", "aktiv": "on", "wochentage": ["1", "5"],
             "uhrzeit": "21:15", "anzahl": "", "tage": "30"}  # fmt: skip
    antwort = admin_client.post(neu, daten)
    assert antwort.status_code == 302
    a = SicherungsAuftrag.objects.get(name="USB")
    assert (a.ziel, a.wochentage, a.uhrzeit, a.tage, a.anzahl) == (
        "/media/usb", "15", dt.time(21, 15), 30, None)  # fmt: skip
    # Je Ziel nur ein Auftrag; Aufbewahrung Pflicht
    zweiter = admin_client.post(neu, {**daten, "name": "Noch einer"}).content.decode()
    assert "schon der Auftrag „USB“" in zweiter
    ohne = admin_client.post(neu, {**daten, "ziel": "/mnt/nas", "tage": ""}).content.decode()
    assert "wie lange Sicherungen aufbewahrt werden" in ohne
    # Ein nicht angeschlossenes Ziel bleibt wählbar
    SicherungsDienst.objects.update(ziele="")
    seite = admin_client.get(reverse("core:sicherungsauftrag", args=[a.pk])).content.decode()
    assert "/media/usb (zurzeit nicht angeschlossen)" in seite
    admin_client.post(reverse("core:sicherungsauftrag_loeschen", args=[a.pk]))
    assert not SicherungsAuftrag.objects.filter(name="USB").exists()
    # Der Standard-Auftrag hat kein Ziel-Feld und lässt sich nicht löschen
    seite = admin_client.get(reverse("core:sicherungsauftrag", args=[standard().pk]))
    assert 'name="ziel"' not in seite.content.decode()
    loeschen = reverse("core:sicherungsauftrag_loeschen", args=[standard().pk])
    assert admin_client.post(loeschen).status_code == 404


def test_ziel_nur_unter_media_und_mnt():
    for ziel in ["/etc/passwd", "/media/../etc"]:
        form = SicherungsAuftragForm(
            {"name": "x", "ziel": ziel, "wochentage": ["1"], "uhrzeit": "22:00", "anzahl": "3"},
            instance=SicherungsAuftrag(),
            ziele=[(ziel, 1, 1)],
        )
        assert not form.is_valid() and "Nur Ordner unter /media" in str(form.errors)


def test_startseite_zeigt_fehlgeschlagene_auftraege(admin_client):
    SicherungsAuftrag.objects.create(name="NAS", ziel="/mnt/nas", uhrzeit="22:00", anzahl=3,
                                     ergebnis="fehler", meldung="Ziel nicht erreichbar",
                                     letzter_versuch=timezone.now())  # fmt: skip
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert "Sicherungsauftrag „NAS“ fehlgeschlagen" in seite and "Ziel nicht erreichbar" in seite


def test_rechte(client, benutzer_mit_rolle, anmelden, settings, admin_client):
    settings.DEMO = True
    assert (
        admin_client.post(reverse("core:sicherung_jetzt", args=[standard().pk])).status_code == 302
    )
    assert standard().angefordert_am is None  # in der Demo gesperrt
    settings.DEMO = False
    admin_client.logout()
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(URL).status_code == 403
    assert client.post(reverse("core:sicherung_jetzt", args=[standard().pk])).status_code == 403
