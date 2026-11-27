"""Links zu Google Maps für eine Anschrift: auf der Karte zeigen oder die Route von der Tafel.

Nur Links – kein API-Schlüssel, keine eingebettete Karte. An Google geht erst etwas, wenn jemand
den Link antippt (wie bei den Stationen der Touren, ADR 0147). Die Anschrift der Tafel kommt aus
den Tafel-Einstellungen.
"""

from urllib.parse import urlencode

SUCHE = "https://www.google.com/maps/search/?"
ROUTE = "https://www.google.com/maps/dir/?"


def anschrift(strasse: str, plz: str, ort: str) -> str:
    """„Straße 1, 12345 Ort“ – leer, wenn Straße oder Ort fehlen (dann findet die Karte nichts
    Brauchbares)."""
    strasse, ort_teil = (strasse or "").strip(), " ".join(t for t in (plz, ort) if t).strip()
    return f"{strasse}, {ort_teil}" if strasse and ort_teil else ""


def tafel() -> str:
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    return anschrift(t.strasse, t.plz, t.ort)


def zeigen(ziel: str) -> str:
    """Link, der die Anschrift in Google Maps zeigt; leer ohne Anschrift."""
    return SUCHE + urlencode({"api": "1", "query": ziel}) if ziel else ""


def route(ziel: str, von: str | None = None) -> str:
    """Link zur Route von der Tafel (oder ``von``) zur Anschrift – Google Maps nennt dort die
    Entfernung. Leer, wenn eine der beiden Anschriften fehlt."""
    von = tafel() if von is None else von
    if not ziel or not von:
        return ""
    return ROUTE + urlencode({"api": "1", "origin": von, "destination": ziel})
