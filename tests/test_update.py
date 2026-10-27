"""Update aus der Oberfläche (ADR 0043). Der Dienst „updater“ wird durch Dateien nachgestellt."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core import update
from apps.konten import rollen

pytestmark = pytest.mark.django_db
URL = reverse("core:update")


def _zeit(t):
    return timezone.localtime(t).strftime("%Y-%m-%dT%H:%M:%S%z")


@pytest.fixture
def ordner(settings, tmp_path):
    settings.BETRIEB_ORDNER = tmp_path
    (tmp_path / "lebenszeichen.txt").write_text(f"zeit={_zeit(timezone.now())}\n")
    (tmp_path / "versionen.txt").write_text(
        f"abgerufen={_zeit(timezone.now())}\ninstalliert=2026.10.2\nfehler=\n"
        "version=2026.9.1|2026-09-30|Erste Version\t\n"
        "version=2026.10.2|2026-10-20|Statistik\tHandbuch\t\n"
        "version=2026.10.10|2026-10-25|Suche im Seitenkopf\tEinlass klarer\t\n"
        "version=kaputt|x|y\n"
    )
    return tmp_path


def test_stand_lesen(ordner):
    s = update.stand()
    assert s.erreichbar and s.installiert == "2026.10.2" and not s.beschaeftigt
    assert [v.name for v in s.versionen] == ["2026.10.10", "2026.10.2", "2026.9.1"]  # numerisch
    assert s.versionen[0].aenderungen == ["Suche im Seitenkopf", "Einlass klarer"]
    assert s.ist_neuer(s.versionen[0]) and not s.ist_neuer(s.versionen[2])
    spaeter = timezone.now() + dt.timedelta(minutes=5)
    assert not update.stand(spaeter).erreichbar


def test_anfordern(ordner):
    with pytest.raises(update.UpdateFehler, match="nicht verfügbar"):
        update.anfordern("2026.10.99", "chefin")
    update.anfordern("2026.10.10", "chefin\nversion=2020.1.1")
    auftrag = (ordner / "auftrag.txt").read_text()
    assert auftrag.splitlines()[0] == "version=2026.10.10" and "\nversion=2020" not in auftrag
    assert update.stand().beschaeftigt
    with pytest.raises(update.UpdateFehler, match="läuft schon"):
        update.anfordern("2026.10.10", "chefin")
    (ordner / "lebenszeichen.txt").unlink()
    (ordner / "auftrag.txt").unlink()
    with pytest.raises(update.UpdateFehler, match="läuft nicht"):
        update.anfordern("2026.10.10", "chefin")


def test_seite(admin_client, ordner):
    seite = admin_client.get(URL).content.decode()
    assert "Update</a>" in seite and "2026.10.2" in seite and "Neue Version verfügbar" in seite
    assert "2026.10.10 vom 2026-10-25 (neueste)" in seite and "Suche im Seitenkopf" in seite
    assert "2026.9.1 vom 2026-09-30 – älter, zurückgehen" in seite and "every 5s" not in seite
    assert "Neue Version 2026.10.10 verfügbar." in seite
    v = (
        (ordner / "versionen.txt")
        .read_text()
        .replace("installiert=2026.10.2", "installiert=2026.10.10")
    )
    (ordner / "versionen.txt").write_text(v)
    seite = admin_client.get(URL).content.decode()
    assert (
        "bintafeln ist aktuell (Version 2026.10.10)" in seite and "Neue Version 2026" not in seite
    )
    (ordner / "versionen.txt").write_text(
        v.replace("installiert=2026.10.10", "installiert=2026.10.2")
    )
    # ohne Bestätigung kein Auftrag
    antwort = admin_client.post(reverse("core:update_starten"), {"version": "2026.10.10"},
                                follow=True)  # fmt: skip
    assert "ausdrücklich bestätigen" in antwort.content.decode()
    assert not (ordner / "auftrag.txt").exists()
    daten = {"version": "2026.10.10", "bestaetigt": "ja"}
    antwort = admin_client.post(reverse("core:update_starten"), daten, follow=True)
    inhalt = antwort.content.decode()
    assert "angefordert" in inhalt and "every 5s" in inhalt
    assert (ordner / "auftrag.txt").read_text().startswith("version=2026.10.10\nvon=chefin")
    # Der Dienst übernimmt: läuft, dann fertig
    (ordner / "auftrag.txt").unlink()
    (ordner / "status.txt").write_text(
        f"zustand=laeuft\nversion=2026.10.10\nbeginn={_zeit(timezone.now())}\nende=\nmeldung=\n"
    )
    (ordner / "protokoll.txt").write_text("==> Sicherung vor dem Update\n")
    liste = admin_client.get(URL, HTTP_HX_REQUEST="true").content.decode()
    assert "<html" not in liste and "Update auf 2026.10.10 läuft" in liste
    assert "Sicherung vor dem Update" in liste
    (ordner / "status.txt").write_text(
        "zustand=fehler\nversion=2026.10.10\nbeginn=\nende=\n"
        "meldung=Das Update ist fehlgeschlagen.\n"
    )
    seite = admin_client.get(URL).content.decode()
    assert (
        "Das Update ist fehlgeschlagen." in seite
        and '<details id="update-protokoll" open>' in seite
    )
    assert "update_seite.js" in seite  # hält das Protokoll beim Nachladen offen
    antwort = admin_client.post(reverse("core:update_abrufen"))
    assert (ordner / "abrufen.txt").exists()
    seite = admin_client.get(antwort.url).content.decode()
    assert "Suche nach neuen Versionen läuft" in seite and 'hx-trigger="every 2s"' in seite
    assert "Es wird nach neuen Versionen gesucht" not in seite


def test_ohne_dienst(admin_client, settings, tmp_path):
    settings.BETRIEB_ORDNER = tmp_path / "leer"
    seite = admin_client.get(URL).content.decode()
    assert "Der Update-Dienst läuft noch nicht" in seite and "./betrieb update" in seite


def test_rechte_und_demo(client, admin_client, benutzer_mit_rolle, anmelden, settings, ordner):
    settings.DEMO = True
    admin_client.post(reverse("core:update_starten"), {"version": "2026.10.10", "bestaetigt": "ja"})
    assert not (ordner / "auftrag.txt").exists()
    settings.DEMO = False
    admin_client.logout()
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(URL).status_code == 403
    assert client.post(reverse("core:update_starten")).status_code == 403


def test_dienst_loescht_suchauftrag_erst_nach_dem_abruf():
    """Sonst meldet die Seite die Suche als fertig, bevor die neuen Versionen da sind."""
    from pathlib import Path

    skript = Path("docker/updater/updater.sh").read_text(encoding="utf-8")
    schleife = skript[skript.index("while true; do") :]
    assert schleife.index("versionen_abrufen ||") < schleife.index('rm -f "$BETRIEB/abrufen.txt"')
