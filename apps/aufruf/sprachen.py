"""Staatsangehörigkeit → Sprache für den Kiosk (zweisprachige Anzeige), wie im bisherigen System.

Die Anzeige zeigt neben Deutsch die Sprache, die zur Staatsangehörigkeit der Hauptperson passt.
Das ist nur eine Annahme für die Anzeige; gespeichert wird nichts.
"""

LAND_ZU_SPRACHE = {
    # Arabisch
    "syrien": "ar", "irak": "ar", "libanon": "ar", "jordanien": "ar", "ägypten": "ar",
    "marokko": "ar", "tunesien": "ar", "algerien": "ar", "libyen": "ar", "palästina": "ar",
    "jemen": "ar", "sudan": "ar", "saudi-arabien": "ar", "kuwait": "ar", "katar": "ar",
    "vereinigte arabische emirate": "ar",
    # Türkisch / Kurdisch
    "türkei": "tr", "aserbaidschan": "tr", "kurdistan": "ku",
    # Osteuropa
    "ukraine": "uk", "russland": "ru", "russische föderation": "ru", "belarus": "ru",
    "kasachstan": "ru", "polen": "pl", "rumänien": "ro", "moldau": "ro", "republik moldau": "ro",
    "bulgarien": "bg", "tschechien": "cs", "slowakei": "cs", "ungarn": "hu",
    # Balkan
    "albanien": "sq", "kosovo": "sq", "serbien": "sr", "montenegro": "sr",
    "bosnien und herzegowina": "bs", "bosnien": "bs", "kroatien": "hr", "nordmazedonien": "mk",
    "griechenland": "el",
    # Persisch
    "afghanistan": "fa", "iran": "fa",
    # West- und Südeuropa
    "spanien": "es", "italien": "it", "frankreich": "fr", "portugal": "pt", "brasilien": "pt",
    "niederlande": "nl", "belgien": "fr",
    # Asien
    "vietnam": "vi", "china": "zh", "pakistan": "ur", "indien": "en", "sri lanka": "en",
    "bangladesch": "en", "georgien": "en", "armenien": "en",
    # Afrika
    "somalia": "so", "eritrea": "en", "äthiopien": "en", "nigeria": "en", "ghana": "en",
    "gambia": "en", "kenia": "en", "guinea": "fr", "senegal": "fr", "kamerun": "fr",
    "kongo": "fr", "demokratische republik kongo": "fr", "komoren": "fr", "elfenbeinküste": "fr",
    "côte d’ivoire": "fr", "togo": "fr", "mali": "fr",
    # Deutsch / Englisch
    "deutschland": "de", "österreich": "de", "schweiz": "de", "liechtenstein": "de",
    "vereinigtes königreich": "en", "irland": "en", "vereinigte staaten": "en", "usa": "en",
}  # fmt: skip

# Für Teiltreffer („Arabische Republik Syrien“): längste Namen zuerst, sehr kurze nicht
_NACH_LAENGE = sorted((k for k in LAND_ZU_SPRACHE if len(k) >= 4), key=len, reverse=True)


def sprachcode(staatsangehoerigkeit: str) -> str | None:
    s = (staatsangehoerigkeit or "").strip().lower()
    if not s:
        return None
    if s in LAND_ZU_SPRACHE:
        return LAND_ZU_SPRACHE[s]
    return next((LAND_ZU_SPRACHE[k] for k in _NACH_LAENGE if k in s), None)
