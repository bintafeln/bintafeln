"""Beschreibung des Moduls Wetter für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul

MODUL = Modul(
    kennung="wetter",
    titel="Wetter",
    beschreibung="Außentemperatur und Wetter der Ausgabestelle in der Kopfzeile "
    "(Open-Meteo; übermittelt werden nur PLZ und Ort)",
    app_label="wetter",
    pfade=("/wetter/",),
    kapitel=(("wetter", "Wetter in der Kopfzeile", ()),),
    kopfzeile="wetter/_kopf_platz.html",
    sicherung_ausgenommen=("wetter.wetterstand",),
)
