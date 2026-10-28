"""Überraschungen auf der Anmeldeseite an Festtagen (ADR 0079)."""

import datetime as dt

import pytest
from django.urls import reverse

from apps.core.anlaesse import anlass, szene
from apps.konten.models import AnmeldeEinstellungen

ANMELDEN = reverse("konten:anmelden")


@pytest.mark.parametrize(
    ("tag", "erwartet"),
    [
        (dt.date(2026, 10, 23), None),
        (dt.date(2026, 10, 24), "halloween"),
        (dt.date(2026, 10, 31), "halloween"),
        (dt.date(2026, 11, 1), None),
        (dt.date(2026, 12, 5), "nikolaus"),
        (dt.date(2026, 12, 6), "nikolaus"),
        (dt.date(2026, 12, 7), None),
        (dt.date(2026, 12, 20), "weihnachten"),
        (dt.date(2026, 12, 26), "weihnachten"),
        (dt.date(2026, 12, 27), None),
        # Ostern 2027 ist am 28. März: Palmsonntag 21.3. bis Ostermontag 29.3.
        (dt.date(2027, 3, 20), None),
        (dt.date(2027, 3, 21), "ostern"),
        (dt.date(2027, 3, 29), "ostern"),
        (dt.date(2027, 3, 30), None),
        # Karneval 2027: Weiberfastnacht 4.2. bis Veilchendienstag 9.2.
        (dt.date(2027, 2, 3), None),
        (dt.date(2027, 2, 4), "karneval"),
        (dt.date(2027, 2, 9), "karneval"),
        (dt.date(2027, 2, 10), None),
    ],
)
def test_anlass_je_tag(tag, erwartet):
    assert anlass(tag) == erwartet


def test_szene_mit_punkt_statt_komma():
    """Die Werte landen in CSS; ein deutsches Komma würde die Animation unsichtbar machen."""
    for name in ("halloween", "karneval", "ostern", "nikolaus"):
        for teil in szene(name).values():
            for f in teil:
                assert all("," not in str(v) for v in f.values())


@pytest.fixture
def heute(monkeypatch):
    def setzen(tag):
        monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: tag)

    return setzen


def test_anmeldeseite_an_halloween(client, admin, heute):
    heute(dt.date(2026, 10, 31))
    inhalt = client.get(ANMELDEN).content.decode()
    assert "anlass-halloween" in inhalt and "anlass-fledermaus" in inhalt
    assert 'aria-hidden="true"' in inhalt
    heute(dt.date(2026, 11, 2))
    assert "anlass-" not in client.get(ANMELDEN).content.decode()


def test_abschaltbar_und_vorschau(client, admin, heute):
    heute(dt.date(2026, 12, 24))
    e = AnmeldeEinstellungen.laden()
    e.ueberraschungen = False
    e.save()
    assert "anlass-" not in client.get(ANMELDEN).content.decode()
    # Vorschau zum Ausprobieren, unabhängig von Tag und Einstellung; Unbekanntes wird ignoriert
    assert "anlass-ostern" in client.get(ANMELDEN + "?anlass=ostern").content.decode()
    assert "anlass-" not in client.get(ANMELDEN + "?anlass=<script>").content.decode()
