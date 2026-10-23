"""Hilfsfunktionen zum Lesen der Konfiguration aus Umgebungsvariablen (.env)."""

import os

from django.core.exceptions import ImproperlyConfigured

WAHR = {"1", "true", "yes", "ja", "on"}
FALSCH = {"0", "false", "no", "nein", "off", ""}


def text(name: str, standard: str | None = None) -> str:
    """Liest eine Variable; ohne Standardwert ist sie Pflicht."""
    wert = os.environ.get(name, "").strip()
    if wert:
        return wert
    if standard is None:
        raise ImproperlyConfigured(f"Umgebungsvariable {name} fehlt (siehe .env.example).")
    return standard


def schalter(name: str, standard: bool = False) -> bool:
    wert = os.environ.get(name)
    if wert is None:
        return standard
    wert = wert.strip().lower()
    if wert in WAHR:
        return True
    if wert in FALSCH:
        return False
    raise ImproperlyConfigured(f"{name} muss true oder false sein, nicht {wert!r}.")


def liste(name: str, standard: list[str] | None = None) -> list[str]:
    wert = os.environ.get(name, "").strip()
    if not wert:
        return list(standard or [])
    return [teil.strip() for teil in wert.split(",") if teil.strip()]
