import runpy
from pathlib import Path

import pytest
from django.core.exceptions import ImproperlyConfigured

from bintafeln import umgebung

SETTINGS = Path(__file__).resolve().parent.parent / "bintafeln" / "settings.py"


def laden(monkeypatch, **werte):
    for name, wert in werte.items():
        if wert is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, wert)
    return runpy.run_path(str(SETTINGS))


def test_entwicklungsmodus_ohne_domain(monkeypatch):
    s = laden(monkeypatch, BINTAFELN_DOMAIN="", DJANGO_ALLOWED_HOSTS=None)
    assert s["PRODUKTION"] is False
    assert s["ALLOWED_HOSTS"] == ["*"]
    assert "SESSION_COOKIE_SECURE" not in s


def test_produktionsmodus_mit_domain(monkeypatch):
    s = laden(
        monkeypatch,
        BINTAFELN_DOMAIN="tafel.example.org",
        DJANGO_ALLOWED_HOSTS=None,
        DJANGO_CSRF_TRUSTED_ORIGINS=None,
    )
    assert s["PRODUKTION"] is True
    assert s["ALLOWED_HOSTS"] == ["tafel.example.org"]
    assert s["CSRF_TRUSTED_ORIGINS"] == ["https://tafel.example.org"]
    assert s["SESSION_COOKIE_SECURE"] is True
    assert s["CSRF_COOKIE_SECURE"] is True
    assert s["SECURE_HSTS_SECONDS"] > 0


def test_ohne_secret_key_startet_nichts(monkeypatch):
    with pytest.raises(ImproperlyConfigured, match="DJANGO_SECRET_KEY"):
        laden(monkeypatch, DJANGO_SECRET_KEY="")


@pytest.mark.parametrize(("wert", "erwartet"), [("true", True), ("Ja", True), ("0", False)])
def test_schalter(monkeypatch, wert, erwartet):
    monkeypatch.setenv("X_SCHALTER", wert)
    assert umgebung.schalter("X_SCHALTER") is erwartet


def test_schalter_standard_und_fehler(monkeypatch):
    monkeypatch.delenv("X_SCHALTER", raising=False)
    assert umgebung.schalter("X_SCHALTER", True) is True
    monkeypatch.setenv("X_SCHALTER", "vielleicht")
    with pytest.raises(ImproperlyConfigured):
        umgebung.schalter("X_SCHALTER")


def test_liste(monkeypatch):
    monkeypatch.setenv("X_LISTE", " a.example, ,b.example ")
    assert umgebung.liste("X_LISTE") == ["a.example", "b.example"]
    monkeypatch.delenv("X_LISTE")
    assert umgebung.liste("X_LISTE", ["c"]) == ["c"]


def test_ganzzahl(monkeypatch):
    monkeypatch.setenv("X_ZAHL", " 7 ")
    assert umgebung.ganzzahl("X_ZAHL", 3) == 7
    monkeypatch.setenv("X_ZAHL", "")
    assert umgebung.ganzzahl("X_ZAHL", 3) == 3
    monkeypatch.delenv("X_ZAHL")
    assert umgebung.ganzzahl("X_ZAHL", 3) == 3
    monkeypatch.setenv("X_ZAHL", "keine-zahl")
    with pytest.raises(ImproperlyConfigured):
        umgebung.ganzzahl("X_ZAHL", 3)


def test_ausweis_ressourcen_einstellungen(monkeypatch):
    s = laden(monkeypatch, BINTAFELN_AUSWEIS_NICE="5", BINTAFELN_AUSWEIS_SPEICHER_MB="800")
    assert s["AUSWEIS_NICE"] == 5
    assert s["AUSWEIS_SPEICHER_MB"] == 800
    s = laden(monkeypatch, BINTAFELN_AUSWEIS_NICE=None, BINTAFELN_AUSWEIS_SPEICHER_MB=None)
    assert s["AUSWEIS_NICE"] == 10  # Vorgabe
    assert s["AUSWEIS_SPEICHER_MB"] == 0  # Vorgabe: kein Deckel
