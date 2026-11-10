"""Vorübergehende Sperre nach zu vielen falschen Passwörtern (ADR 0093, ADR 0120).

Gezählt wird je Benutzername im gemeinsamen Cache. Wie viele Fehlversuche erlaubt sind und wie
lange die Sperre dauert, stellt die Tafel unter „Einstellungen → Anmeldung“ ein
(``AnmeldeEinstellungen.fehlversuche`` / ``sperre_minuten``). Ein Admin kann die Sperre einer
Person sofort aufheben.
"""

from django.core.cache import cache


def _schluessel(benutzername: str) -> str:
    return f"anmelden-fehler:{benutzername.lower()}"


def _grenzen() -> tuple[int, int]:
    from apps.konten.models import AnmeldeEinstellungen

    e = AnmeldeEinstellungen.laden()
    return e.fehlversuche, e.sperre_minuten


def ist_gesperrt(benutzername: str) -> bool:
    """Hat der Benutzername die erlaubte Zahl falscher Passwörter erreicht?"""
    return (cache.get(_schluessel(benutzername)) or 0) >= _grenzen()[0]


def fehlversuch(benutzername: str) -> None:
    """Ein falsches Passwort zählen; die Zählung verfällt nach der eingestellten Sperrdauer."""
    schluessel = _schluessel(benutzername)
    cache.add(schluessel, 0, _grenzen()[1] * 60)
    cache.incr(schluessel)


def aufheben(benutzername: str) -> None:
    """Zählung löschen: nach erfolgreicher Anmeldung oder wenn ein Admin die Sperre aufhebt."""
    cache.delete(_schluessel(benutzername))


def minuten() -> int:
    return _grenzen()[1]
