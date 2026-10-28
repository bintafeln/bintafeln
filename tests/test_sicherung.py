from datetime import UTC, datetime, timedelta

import pytest
from django.urls import reverse

from apps.core import sicherung
from apps.konten import rollen

JETZT = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def schreiben(pfad, ergebnis, erfolgreich="", meldung="Text"):
    pfad.write_text(
        "letzter_versuch=2026-03-01T02:30:00+0100\n"
        f"ergebnis={ergebnis}\nmeldung={meldung}\nletzte_erfolgreiche={erfolgreich}\n",
        encoding="utf-8",
    )
    return pfad


def test_ohne_datei_unbekannt(tmp_path):
    status = sicherung.lese_status(tmp_path / "fehlt.txt", JETZT)
    assert status.zustand == sicherung.UNBEKANNT
    assert not status.in_ordnung


def test_aktuelle_sicherung_ok(tmp_path):
    pfad = schreiben(tmp_path / "s.txt", "ok", "2026-03-01T02:30:00+0100")
    status = sicherung.lese_status(pfad, JETZT)
    assert status.zustand == sicherung.OK
    assert status.in_ordnung
    assert status.letzte_erfolgreiche == datetime(2026, 3, 1, 1, 30, tzinfo=UTC)


def test_alte_sicherung_gelb_und_veraltet(tmp_path):
    pfad = schreiben(tmp_path / "s.txt", "ok", "2026-02-26T02:30:00+0100")
    assert sicherung.lese_status(pfad, JETZT).zustand == sicherung.OK  # bis 5 Tage grün
    pfad = schreiben(tmp_path / "s.txt", "ok", "2026-02-20T02:30:00+0100")
    assert sicherung.lese_status(pfad, JETZT).zustand == sicherung.ALT  # bis 10 Tage gelb
    pfad = schreiben(tmp_path / "s.txt", "ok", "2026-02-15T02:30:00+0100")
    assert sicherung.lese_status(pfad, JETZT).zustand == sicherung.VERALTET


@pytest.mark.parametrize(
    ("ergebnis", "erfolgreich", "zustand"),
    [
        ("fehler", "2026-03-01T02:30:00+0100", sicherung.FEHLER),
        ("nicht_eingerichtet", "", sicherung.NICHT_EINGERICHTET),
        ("ok", "kaputt", sicherung.UNBEKANNT),
        ("ok", "", sicherung.UNBEKANNT),
    ],
)
def test_weitere_zustaende(tmp_path, ergebnis, erfolgreich, zustand):
    pfad = schreiben(tmp_path / "s.txt", ergebnis, erfolgreich)
    assert sicherung.lese_status(pfad, JETZT).zustand == zustand


def test_standardpfad_aus_settings(settings, tmp_path):
    settings.SICHERUNG_STATUSDATEI = schreiben(tmp_path / "s.txt", "nicht_eingerichtet")
    assert sicherung.lese_status().zustand == sicherung.NICHT_EINGERICHTET


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("ergebnis", "erfolgreich", "text"),
    [
        ("ok", "jetzt", "Letzte Sicherung am"),
        ("ok", "alt", "mehr als 5 Tage her"),
        ("ok", "uralt", "älter als 10 Tage"),
        ("fehler", "jetzt", "Kaputt gegangen"),
        ("fehler", "", "Kaputt gegangen"),
        ("nicht_eingerichtet", "", "./betrieb schluessel"),
    ],
)
def test_startseite_zeigt_status_fuer_admin(
    admin_client, settings, tmp_path, ergebnis, erfolgreich, text
):
    zeitpunkte = {
        "jetzt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "alt": (datetime.now(UTC) - timedelta(days=6)).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "uralt": (datetime.now(UTC) - timedelta(days=11)).strftime("%Y-%m-%dT%H:%M:%S%z"),
        "": "",
    }
    settings.SICHERUNG_STATUSDATEI = schreiben(
        tmp_path / "s.txt", ergebnis, zeitpunkte[erfolgreich], "Kaputt gegangen"
    )
    inhalt = admin_client.get(reverse("core:start")).content.decode()
    assert text in inhalt


@pytest.mark.django_db
def test_startseite_ohne_statusdatei(admin_client, settings, tmp_path):
    settings.SICHERUNG_STATUSDATEI = tmp_path / "fehlt.txt"
    inhalt = admin_client.get(reverse("core:start")).content.decode()
    assert "Läuft der Dienst" in inhalt


@pytest.mark.django_db
def test_startseite_ohne_status_fuer_andere_rollen(client, admin, benutzer_mit_rolle, anmelden):
    anmelden(client, benutzer_mit_rolle("buero", rollen.BUERO))
    inhalt = client.get(reverse("core:start")).content.decode()
    assert "Sicherung:" not in inhalt
