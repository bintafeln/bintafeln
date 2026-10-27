"""Fotos einstellbar verkleinern, Speicher ansehen, Originale aufräumen (ADR 0064)."""

import datetime as dt
import io

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.core import bilder, privatdateien, sicherung
from apps.core.models import FotoEinstellungen

pytestmark = pytest.mark.django_db
URL = reverse("core:speicher")


def foto(breite=3000, hoehe=2000, art="JPEG", modus="RGB") -> bytes:
    puffer = io.BytesIO()
    Image.effect_noise((breite, hoehe), 40).convert(modus).save(puffer, art, quality=92)
    return puffer.getvalue()


def hochladen(daten, typ="image/jpeg", ordner="test"):
    return privatdateien.speichern(ordner, SimpleUploadedFile("q", daten, content_type=typ),
                                   max_mb=20)  # fmt: skip


def groesse(daten):
    return Image.open(io.BytesIO(daten)).size


def test_foto_verkleinern_behaelt_format():
    jpg = foto()
    klein = bilder.foto_verkleinern(jpg, "image/jpeg", 1000, 70)
    assert groesse(klein) == (1000, 667) and len(klein) < len(jpg) / 3
    grau = Image.open(io.BytesIO(bilder.foto_verkleinern(jpg, "image/jpeg", 1000, 70, True)))
    assert grau.mode == "L"
    png = bilder.foto_verkleinern(foto(1200, 800, "PNG", "RGBA"), "image/png", 600, 70)
    assert Image.open(io.BytesIO(png)).format == "PNG"
    webp = bilder.foto_verkleinern(foto(1200, 800, "WEBP"), "image/webp", 600, 70, True)
    assert Image.open(io.BytesIO(webp)).format == "WEBP"
    assert bilder.foto_verkleinern(jpg, "image/jpeg", 0, 70) is jpg  # nicht verkleinern
    assert bilder.foto_verkleinern(b"%PDF-1.4", "application/pdf", 1000, 70) == b"%PDF-1.4"
    assert bilder.foto_verkleinern(b"kaputt", "image/jpeg", 1000, 70) == b"kaputt"
    klein_genug = foto(200, 100)
    assert bilder.foto_verkleinern(klein_genug, "image/jpeg", 1600, 95) is klein_genug


def test_hochladen_nach_einstellung():
    name = hochladen(foto())
    assert groesse(privatdateien.lesen("test", name)) == (1600, 1067)  # Vorgabe
    e = FotoEinstellungen.laden()
    e.kante = 0
    e.save()
    name = hochladen(foto())
    assert groesse(privatdateien.lesen("test", name)) == (3000, 2000)
    pdf = hochladen(b"%PDF-1.4 erfunden", "application/pdf")
    assert privatdateien.lesen("test", pdf) == b"%PDF-1.4 erfunden"


def test_seite_vorhandene_und_originale(admin_client, monkeypatch):
    e = FotoEinstellungen.laden()
    e.kante = 0
    e.save()
    gross = foto()
    name = hochladen(gross, ordner="quittungen")
    hochladen(b"%PDF-1.4", "application/pdf", ordner="quittungen")
    seite = admin_client.get(URL).content.decode()
    assert "Dateien „quittungen“ (2)" in seite and "Datenbank" in seite
    admin_client.post(URL, {"aktion": "speichern", "kante": "1000", "qualitaet": "60"})
    e.refresh_from_db()
    assert (e.kante, e.qualitaet, e.graustufen) == (1000, 60, False)
    antwort = admin_client.post(URL, {"aktion": "verkleinern"}, follow=True)
    assert "1 Foto(s) verkleinert" in antwort.content.decode()
    assert groesse(privatdateien.lesen("quittungen", name)) == (1000, 667)
    original = privatdateien.pfad("quittungen", name + privatdateien.ORIGINAL)
    assert original.exists()
    # zweiter Klick: nichts mehr zu tun; geänderte Einstellung: neu aus dem Original
    assert "0 Foto(s)" in admin_client.post(URL, {"aktion": "verkleinern"},
                                            follow=True).content.decode()  # fmt: skip
    admin_client.post(URL, {"aktion": "speichern", "kante": "1280", "qualitaet": "60"})
    admin_client.post(URL, {"aktion": "verkleinern"})
    assert groesse(privatdateien.lesen("quittungen", name)) == (1280, 853)
    # Originale löschen nur mit frischer Sicherung
    assert "Aufbewahrte Originale" in admin_client.get(URL).content.decode()
    antwort = admin_client.post(URL, {"aktion": "originale"}, follow=True)
    assert "höchstens 24 Stunden" in antwort.content.decode() and original.exists()
    jetzt = timezone.now()
    monkeypatch.setattr(sicherung, "lese_status", lambda: sicherung.SicherungsStatus(
        sicherung.OK, jetzt - dt.timedelta(hours=2)))  # fmt: skip
    antwort = admin_client.post(URL, {"aktion": "originale"}, follow=True)
    assert "1 Original(e) gelöscht" in antwort.content.decode() and not original.exists()
    assert groesse(privatdateien.lesen("quittungen", name)) == (1280, 853)


def test_grenze_je_klick_und_rechte(admin_client, benutzer_mit_rolle, anmelden):
    from django.test import Client

    e = FotoEinstellungen.laden()
    e.kante = 0
    e.save()
    for _ in range(3):
        hochladen(foto(800, 600))
    e.kante = 400
    e.save()
    ergebnis = privatdateien.vorhandene_verkleinern(grenze=2)
    assert ergebnis["verkleinert"] == 2 and ergebnis["offen"] == 1
    c = anmelden(Client(), benutzer_mit_rolle("berta", "Büro"))
    assert c.get(URL).status_code == 403


def test_alle_dateien_und_verwaiste(admin_client, monkeypatch):
    import os

    from apps.core.models import PapierkorbEintrag
    from apps.kunden.models import Dokumentart, HaushaltDokument

    art, _ = Dokumentart.objects.get_or_create(bezeichnung="Bescheid")
    ordner = HaushaltDokument.ORDNER
    da = hochladen(b"%PDF-1.4 da", "application/pdf", ordner=ordner)
    HaushaltDokument.objects.create(kundennummer="4711", art=art, titel="Bescheid 2026", datei=da)
    weg = hochladen(b"%PDF-1.4 weg", "application/pdf", ordner=ordner)
    korb = hochladen(b"%PDF-1.4 korb", "application/pdf", ordner=ordner)
    PapierkorbEintrag.objects.create(art="Dokument", bezeichnung="x", recht="kunden.bearbeiten",
                                     dateien=[[ordner, korb]])  # fmt: skip
    fremd = hochladen(b"%PDF-1.4 fremd", "application/pdf", ordner="irgendwas")
    alt = (timezone.now() - dt.timedelta(days=2)).timestamp()
    for name, o in ((weg, ordner), (korb, ordner), (fremd, "irgendwas")):
        os.utime(privatdateien.pfad(o, name), (alt, alt))

    status = {d["name"]: d["status"] for d in privatdateien.verzeichnis()}
    assert status == {da: "ok", weg: "verwaist", korb: "papierkorb", fremd: "unbekannt"}
    url = reverse("core:dateien")
    seite = admin_client.get(url).content.decode()
    assert "Dokumente zu Haushalten" in seite and "4 Dateien" in seite
    assert "1 Datei (" in seite and "verwaist" in seite
    gefiltert = admin_client.get(url, {"bereich": "Dokumente zu Haushalten"}).content.decode()
    assert "3 Dateien" in gefiltert
    # Löschen nur mit frischer Sicherung; nur die verwaiste
    antwort = admin_client.post(url, {"aktion": "verwaiste"}, follow=True)
    assert "höchstens 24 Stunden" in antwort.content.decode()
    monkeypatch.setattr(sicherung, "lese_status", lambda: sicherung.SicherungsStatus(
        sicherung.OK, timezone.now() - dt.timedelta(hours=2)))  # fmt: skip
    antwort = admin_client.post(url, {"aktion": "verwaiste"}, follow=True)
    assert "1 verwaiste Datei(en) gelöscht" in antwort.content.decode()
    assert not privatdateien.pfad(ordner, weg).exists()
    assert all(privatdateien.pfad(o, n).exists()
               for o, n in ((ordner, da), (ordner, korb), ("irgendwas", fremd)))  # fmt: skip
    # Eine gerade hochgeladene Datei ohne Datensatz bleibt (Datensatz kommt gleich)
    neu = hochladen(b"%PDF-1.4 neu", "application/pdf", ordner=ordner)
    assert privatdateien.verwaiste_loeschen() == (0, 0)
    assert privatdateien.pfad(ordner, neu).exists()


def test_alle_dateien_nur_mit_recht(client, admin, benutzer_mit_rolle, anmelden):
    from apps.konten import rollen

    anmelden(client, benutzer_mit_rolle("buero", rollen.BUERO))
    assert client.get(reverse("core:dateien")).status_code == 403
