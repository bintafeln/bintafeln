"""Außentemperatur und Wetter der Ausgabestelle für die Kopfzeile (ADR 0053).

Quelle ist Open-Meteo (kostenlos, ohne Schlüssel). Übermittelt werden nur PLZ und Ort der
Ausgabestelle, keine Personendaten. Der Server fragt höchstens alle ``GUELTIG`` je Ausgabestelle
und nach einem Fehler erst wieder nach ``PAUSE``; die Seite wartet nie darauf (Nachladen per HTMX).
"""

import datetime as dt
import json
import logging
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from django.utils import timezone

from apps.kunden.models import Ausgabestelle
from apps.wetter.models import WetterStand
from bintafeln import programm

log = logging.getLogger(__name__)

SUCHE = "https://geocoding-api.open-meteo.com/v1/search"
WETTER = "https://api.open-meteo.com/v1/forecast"
GUELTIG = dt.timedelta(minutes=30)
PAUSE = dt.timedelta(minutes=10)
HOECHSTENS_ALT = dt.timedelta(hours=3)  # älteres Wetter wird nicht mehr gezeigt
ZEIT = 4  # Sekunden je Anfrage

# WMO-Wettercodes → (Symbol am Tag, Symbol in der Nacht, kurzer Text)
CODES = {
    0: ("☀️", "🌙", "klar"),
    1: ("🌤️", "🌙", "überwiegend klar"),
    2: ("⛅", "☁️", "teils bewölkt"),
    3: ("☁️", "☁️", "bedeckt"),
    45: ("🌫️", "🌫️", "Nebel"),
    48: ("🌫️", "🌫️", "Reifnebel"),
    51: ("🌦️", "🌧️", "leichter Niesel"),
    53: ("🌦️", "🌧️", "Niesel"),
    55: ("🌧️", "🌧️", "starker Niesel"),
    56: ("🌧️", "🌧️", "gefrierender Niesel"),
    57: ("🌧️", "🌧️", "gefrierender Niesel"),
    61: ("🌦️", "🌧️", "leichter Regen"),
    63: ("🌧️", "🌧️", "Regen"),
    65: ("🌧️", "🌧️", "starker Regen"),
    66: ("🌧️", "🌧️", "gefrierender Regen"),
    67: ("🌧️", "🌧️", "gefrierender Regen"),
    71: ("🌨️", "🌨️", "leichter Schneefall"),
    73: ("🌨️", "🌨️", "Schneefall"),
    75: ("❄️", "❄️", "starker Schneefall"),
    77: ("🌨️", "🌨️", "Schneegriesel"),
    80: ("🌦️", "🌧️", "Regenschauer"),
    81: ("🌧️", "🌧️", "Regenschauer"),
    82: ("🌧️", "🌧️", "heftige Schauer"),
    85: ("🌨️", "🌨️", "Schneeschauer"),
    86: ("🌨️", "🌨️", "Schneeschauer"),
    95: ("⛈️", "⛈️", "Gewitter"),
    96: ("⛈️", "⛈️", "Gewitter mit Hagel"),
    99: ("⛈️", "⛈️", "Gewitter mit Hagel"),
}


class WetterFehler(Exception):
    pass


def _json(adresse: str, werte: dict) -> dict:
    # Nur die festen https-Adressen oben, nie Eingaben von außen
    anfrage = Request(f"{adresse}?{urlencode(werte)}", headers={"User-Agent": programm.NAME})  # noqa: S310
    with urlopen(anfrage, timeout=ZEIT) as antwort:  # noqa: S310
        return json.load(antwort)


def ort_von(stelle) -> str:
    return f"{stelle.plz} {stelle.ort}".strip()


def stelle_fuer(benutzer):
    """Die Ausgabestelle, der die Person zugeordnet ist; sonst die erste mit PLZ oder Ort."""
    mit_ort = Ausgabestelle.objects.filter(aktiv=True).exclude(plz="", ort="").order_by("name")
    return mit_ort.filter(pk__in=benutzer.ausgabestellen.all()).first() or mit_ort.first()


def _koordinaten(stelle) -> tuple[float, float]:
    name = stelle.ort.strip() or stelle.plz.strip()
    daten = _json(SUCHE, {"name": name, "count": 10, "language": "de", "format": "json"})
    treffer = daten.get("results") or []
    if not treffer:
        raise WetterFehler(f"Ort „{name}“ nicht gefunden")
    plz = stelle.plz.strip()
    passend = next((t for t in treffer if plz and plz in (t.get("postcodes") or [])), treffer[0])
    return float(passend["latitude"]), float(passend["longitude"])


def _abrufen(stand: WetterStand, stelle) -> None:
    if stand.breite is None or stand.laenge is None:
        stand.breite, stand.laenge = _koordinaten(stelle)
    daten = _json(WETTER, {"latitude": stand.breite, "longitude": stand.laenge,
                           "current": "temperature_2m,weather_code,is_day",
                           "timezone": "auto"})  # fmt: skip
    jetzt = daten["current"]
    stand.temperatur = float(jetzt["temperature_2m"])
    stand.code = int(jetzt["weather_code"])
    stand.tag = bool(jetzt.get("is_day", 1))


def anzeige(benutzer) -> dict:
    """Für die Kopfzeile: {"wetter": …} oder {"grund": …}, warum nichts angezeigt wird."""
    stelle = stelle_fuer(benutzer)
    if stelle is None:
        return {"grund": "Keine aktive Ausgabestelle mit PLZ oder Ort – bitte unter "
                         "Einstellungen → Ausgabestellen eintragen."}  # fmt: skip
    daten = aktuell(stelle)
    if daten:
        return {"wetter": daten}
    stand = WetterStand.objects.filter(ausgabestelle=stelle).first()
    grund = stand.fehler if stand and stand.fehler else "Noch kein aktuelles Wetter abgerufen."
    return {"grund": f"Wetter für {stelle.name}: {grund}"}


def aktuell(stelle) -> dict | None:
    """Wetter für die Kopfzeile oder None (keine Anschrift, Dienst nicht erreichbar)."""
    if stelle is None or not ort_von(stelle):
        return None
    jetzt = timezone.now()
    stand, _ = WetterStand.objects.get_or_create(ausgabestelle=stelle)
    if stand.ort != ort_von(stelle):
        stand.ort, stand.breite, stand.laenge = ort_von(stelle), None, None
        stand.temperatur = stand.code = stand.abgerufen_am = stand.fehler_am = None
        stand.fehler = ""
    frisch = stand.abgerufen_am and jetzt - stand.abgerufen_am < GUELTIG
    pause = stand.fehler_am and jetzt - stand.fehler_am < PAUSE
    if not frisch and not pause:
        try:
            _abrufen(stand, stelle)
            stand.abgerufen_am, stand.fehler_am, stand.fehler = jetzt, None, ""
        except WetterFehler as fehler:
            log.warning("Wetter für %s nicht abrufbar: %s", stand.ort, fehler)
            stand.fehler_am, stand.fehler = (
                jetzt,
                f"{fehler} – PLZ und Ort der Ausgabestelle prüfen."[:200],
            )
        except (OSError, ValueError, KeyError, TypeError) as fehler:
            log.warning("Wetter für %s nicht abrufbar: %s", stand.ort, fehler)
            stand.fehler_am = jetzt
            stand.fehler = (f"Wetterdienst nicht erreichbar ({str(fehler)[:80]}). Braucht "
                            "Internetzugang des Servers zu open-meteo.com.")  # fmt: skip
        stand.save()
    if stand.temperatur is None or not stand.abgerufen_am:
        return None
    if jetzt - stand.abgerufen_am > HOECHSTENS_ALT:
        return None
    symbol_tag, symbol_nacht, text = CODES.get(stand.code, ("🌡️", "🌡️", ""))
    return {
        "temperatur": round(stand.temperatur),
        "symbol": symbol_tag if stand.tag else symbol_nacht,
        "text": text,
        "stelle": stelle.name,
        "ort": stand.ort,
        "stand": stand.abgerufen_am,
    }
