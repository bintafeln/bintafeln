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
        assert not form.is_valid() and "Nur ein Ordner unter /media" in str(form.errors)


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


# --- Fernsicherung über rclone (ADR 0106) ------------------------------------------------------

FERN_KONFIG = "[fern]\ntype = sftp\nhost = backup.example\nuser = tafel\npass = geheim123\n"


def test_fernsicherung_verschluesselt_und_remotes():
    from apps.core.models import Fernsicherung

    f = Fernsicherung.laden()
    f.konfig_setzen(FERN_KONFIG)
    f.save()
    f = Fernsicherung.laden()
    assert f.eingerichtet and f.konfig == FERN_KONFIG
    assert "geheim123" not in f.konfig_verschluesselt  # nicht im Klartext gespeichert
    assert f.remotes() == ["fern"]


def test_fernsicherung_schreibt_rclone_conf(tmp_path, monkeypatch):
    import stat

    from apps.core import fernsicherung
    from apps.core.models import Fernsicherung

    monkeypatch.setattr(fernsicherung, "KONFIG_PFAD", tmp_path)
    f = Fernsicherung.laden()
    f.konfig_setzen(FERN_KONFIG)
    f.save()
    assert fernsicherung.schreiben() is True
    datei = tmp_path / "rclone.conf"
    assert datei.read_text().startswith("[fern]") and "geheim123" in datei.read_text()
    assert stat.S_IMODE(datei.stat().st_mode) == 0o600
    # Entfernen löscht die Datei wieder
    f.konfig_setzen("")
    f.save()
    assert fernsicherung.schreiben() is False and not datei.exists()


def test_rclone_obscure_roundtrip():
    from apps.core import rclone

    verschleiert = rclone.obscure("geheim123")
    assert verschleiert != "geheim123" and "=" not in verschleiert  # kein Klartext/Füllzeichen
    assert rclone.reveal(verschleiert) == "geheim123"
    # Zufälliger IV: zweimal verschleiern ergibt verschiedene Texte, beide lesbar
    assert rclone.obscure("geheim123") != verschleiert
    assert rclone.block_parsen("[fern]\ntype = sftp\nhost = a.example\n") == {
        "type": "sftp", "host": "a.example"}  # fmt: skip


def test_fernablage_gefuehrt_sftp_passwort(admin_client, tmp_path, monkeypatch):
    """SFTP mit Passwort: Block wird gebaut, Passwort rclone-verschleiert (nicht im Klartext)."""
    from apps.core import fernsicherung, rclone
    from apps.core.models import Fernsicherung

    monkeypatch.setattr(fernsicherung, "KONFIG_PFAD", tmp_path)
    url = reverse("core:sicherung_fernablage")
    admin_client.post(url, {"art": "sftp", "sftp_host": "backup.example", "sftp_port": "2222",
                            "sftp_user": "tafel", "sftp_pass": "geheim123"})  # fmt: skip
    werte = rclone.block_parsen(Fernsicherung.laden().konfig)
    assert werte["type"] == "sftp" and werte["host"] == "backup.example"
    assert werte["port"] == "2222" and werte["user"] == "tafel"
    assert werte["pass"] != "geheim123" and rclone.reveal(werte["pass"]) == "geheim123"
    assert (tmp_path / "rclone.conf").exists()
    # Leeres Passwort bei gleicher Art: gespeichertes Geheimnis bleibt erhalten
    admin_client.post(url, {"art": "sftp", "sftp_host": "backup.example", "sftp_user": "tafel"})
    neu = rclone.block_parsen(Fernsicherung.laden().konfig)
    assert rclone.reveal(neu["pass"]) == "geheim123"


def test_fernablage_gefuehrt_sftp_schluesseldatei(admin_client, tmp_path, monkeypatch):
    """SFTP mit Schlüsseldatei: key_file im Block, Schlüssel verschlüsselt gespeichert."""
    from io import BytesIO

    from apps.core import fernsicherung, rclone
    from apps.core.models import Fernsicherung

    monkeypatch.setattr(fernsicherung, "KONFIG_PFAD", tmp_path)
    url = reverse("core:sicherung_fernablage")
    schluessel = b"-----BEGIN OPENSSH PRIVATE KEY-----\nerfundenerschluessel\n-----END-----\n"
    datei = BytesIO(schluessel)
    datei.name = "id_ed25519"
    admin_client.post(url, {"art": "sftp", "sftp_host": "backup.example", "sftp_user": "tafel",
                            "sftp_key": datei})  # fmt: skip
    f = Fernsicherung.laden()
    werte = rclone.block_parsen(f.konfig)
    assert werte["key_file"] == rclone.SCHLUESSELDATEI_PFAD and "pass" not in werte
    assert f.schluessel.strip() == schluessel.decode().strip()
    assert "erfundenerschluessel" not in f.schluessel_verschluesselt  # nicht im Klartext
    # schreiben() legt die Schlüsseldatei mit strengen Rechten an
    import stat

    schl_datei = tmp_path / "sftp_key"
    assert schl_datei.exists() and stat.S_IMODE(schl_datei.stat().st_mode) == 0o600


def test_fernablage_gefuehrt_webdav_s3_ftp(admin_client, tmp_path, monkeypatch):
    from apps.core import fernsicherung, rclone
    from apps.core.models import Fernsicherung

    monkeypatch.setattr(fernsicherung, "KONFIG_PFAD", tmp_path)
    url = reverse("core:sicherung_fernablage")
    # Nextcloud/WebDAV: Anbieter als vendor, Passwort verschleiert
    admin_client.post(url, {"art": "webdav", "dav_vendor": "owncloud",
                            "dav_url": "https://cloud.example/remote.php/dav/files/tafel/",
                            "dav_user": "tafel", "dav_pass": "app-pw"})  # fmt: skip
    w = rclone.block_parsen(Fernsicherung.laden().konfig)
    assert w["type"] == "webdav" and w["vendor"] == "owncloud"
    assert rclone.reveal(w["pass"]) == "app-pw"
    # S3: Secret im Klartext (rclone verschleiert S3-Secrets nicht)
    admin_client.post(url, {"art": "s3", "s3_provider": "Backblaze", "s3_key": "KID",
                            "s3_secret": "SECRET", "s3_endpoint": "s3.example"})  # fmt: skip
    w = rclone.block_parsen(Fernsicherung.laden().konfig)
    assert w["type"] == "s3" and w["access_key_id"] == "KID" and w["secret_access_key"] == "SECRET"
    # FTP mit FTPS
    admin_client.post(url, {"art": "ftp", "ftp_host": "ftp.example", "ftp_user": "tafel",
                            "ftp_pass": "pw", "ftp_tls": "on"})  # fmt: skip
    w = rclone.block_parsen(Fernsicherung.laden().konfig)
    assert w["type"] == "ftp" and w["explicit_tls"] == "true" and rclone.reveal(w["pass"]) == "pw"


def test_fernablage_block_und_entfernen(admin_client, tmp_path, monkeypatch):
    from apps.core import fernsicherung
    from apps.core.models import Fernsicherung

    monkeypatch.setattr(fernsicherung, "KONFIG_PFAD", tmp_path)
    url = reverse("core:sicherung_fernablage")
    admin_client.post(url, {"art": "block", "konfig": FERN_KONFIG})
    assert Fernsicherung.laden().konfig.strip() == FERN_KONFIG.strip()
    assert (tmp_path / "rclone.conf").exists()
    admin_client.post(url, {"art": "block", "konfig": ""})  # leer = unverändert
    assert Fernsicherung.laden().konfig.strip() == FERN_KONFIG.strip()
    admin_client.post(url, {"entfernen": "on"})
    assert not Fernsicherung.laden().eingerichtet and not (tmp_path / "rclone.conf").exists()
    # Das Geheimnis wird nicht in die Seite zurückgeschrieben
    f = Fernsicherung.laden()
    f.konfig_setzen(FERN_KONFIG)
    f.save()
    assert "geheim123" not in admin_client.get(URL).content.decode()


def test_fernablage_vorbelegung(admin_client):
    """Beim erneuten Öffnen stehen Art und die nicht-geheimen Werte wieder im Formular."""
    from apps.core.forms import FernsicherungForm
    from apps.core.models import Fernsicherung

    f = Fernsicherung.laden()
    f.konfig_setzen(FERN_KONFIG)
    f.save()
    form = FernsicherungForm(instanz=f)
    assert form.initial["art"] == "sftp" and form.initial["sftp_host"] == "backup.example"
    assert form.initial["sftp_user"] == "tafel"
    seite = admin_client.get(URL).content.decode()
    assert 'value="backup.example"' in seite  # vorbelegt sichtbar
    assert "geheim123" not in seite  # Geheimnis nie


def test_fernablage_als_sicherungsziel_waehlbar(admin_client):
    from apps.core.models import Fernsicherung

    f = Fernsicherung.laden()
    f.konfig_setzen(FERN_KONFIG)
    f.save()
    seite = admin_client.get(reverse("core:sicherungsauftrag_neu")).content.decode()
    assert "fern:bintafeln" in seite and "Fernablage außer Haus „fern“" in seite
    admin_client.post(reverse("core:sicherungsauftrag_neu"), {
        "name": "Außer Haus", "ziel": "fern:bintafeln", "aktiv": "on",
        "wochentage": ["1"], "uhrzeit": "02:30", "anzahl": "14",
    })  # fmt: skip
    assert SicherungsAuftrag.objects.get(name="Außer Haus").ziel == "fern:bintafeln"
