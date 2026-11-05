"""Lokale Ausweisprüfung über die maschinenlesbare Zone (MRZ), ADR 0107.

Liest mit Tesseract (OCR, lokal auf dem Server) die MRZ eines fotografierten Ausweises oder Passes
und wertet sie nach ICAO 9303 aus: ausstellendes Land und Staatsangehörigkeit (als Ländercode mit
Prüfziffern), Dokumentart und Name. Kein externer Dienst, keine KI – das Bild verlässt den Server
nicht. Das Ergebnis ist nur ein Hinweis zur Prüfung durch einen Menschen; nichts läuft automatisch.

Zuverlässig, wenn die MRZ (die zwei bis drei Zeilen aus Großbuchstaben und ``<``) klar
fotografiert ist. Fehlt sie oder ist sie unleserlich, wird nichts geraten (erkannt=False).
"""

import io
import re
import shutil

from apps.core.auswahl import STAATEN

# ISO 3166-1: alpha-2 (wie in STAATEN) → alpha-3 (wie in der MRZ). Nur die in STAATEN geführten
# Länder; Referenzdaten, keine Tafel-Werte.
_ALPHA2_ALPHA3 = {
    "AF": "AFG", "EG": "EGY", "AL": "ALB", "DZ": "DZA", "AD": "AND", "AO": "AGO", "AG": "ATG",
    "GQ": "GNQ", "AR": "ARG", "AM": "ARM", "AZ": "AZE", "ET": "ETH", "AU": "AUS", "BS": "BHS",
    "BH": "BHR", "BD": "BGD", "BB": "BRB", "BY": "BLR", "BE": "BEL", "BZ": "BLZ", "BJ": "BEN",
    "BT": "BTN", "BO": "BOL", "BA": "BIH", "BW": "BWA", "BR": "BRA", "BN": "BRN", "BG": "BGR",
    "BF": "BFA", "BI": "BDI", "CL": "CHL", "CN": "CHN", "CR": "CRI", "CI": "CIV", "DK": "DNK",
    "DE": "DEU", "DM": "DMA", "DO": "DOM", "DJ": "DJI", "EC": "ECU", "SV": "SLV", "ER": "ERI",
    "EE": "EST", "SZ": "SWZ", "FJ": "FJI", "FI": "FIN", "FR": "FRA", "GA": "GAB", "GM": "GMB",
    "GE": "GEO", "GH": "GHA", "GD": "GRD", "GR": "GRC", "GT": "GTM", "GN": "GIN", "GW": "GNB",
    "GY": "GUY", "HT": "HTI", "HN": "HND", "IN": "IND", "ID": "IDN", "IQ": "IRQ", "IR": "IRN",
    "IE": "IRL", "IS": "ISL", "IL": "ISR", "IT": "ITA", "JM": "JAM", "JP": "JPN", "YE": "YEM",
    "JO": "JOR", "KH": "KHM", "CM": "CMR", "CA": "CAN", "CV": "CPV", "KZ": "KAZ", "QA": "QAT",
    "KE": "KEN", "KG": "KGZ", "KI": "KIR", "CO": "COL", "KM": "COM", "CD": "COD", "CG": "COG",
    "XK": "RKS", "HR": "HRV", "CU": "CUB", "KW": "KWT", "LA": "LAO", "LS": "LSO", "LV": "LVA",
    "LB": "LBN", "LR": "LBR", "LY": "LBY", "LI": "LIE", "LT": "LTU", "LU": "LUX", "MG": "MDG",
    "MW": "MWI", "MY": "MYS", "MV": "MDV", "ML": "MLI", "MT": "MLT", "MA": "MAR", "MH": "MHL",
    "MR": "MRT", "MU": "MUS", "MX": "MEX", "FM": "FSM", "MD": "MDA", "MC": "MCO", "MN": "MNG",
    "ME": "MNE", "MZ": "MOZ", "MM": "MMR", "NA": "NAM", "NR": "NRU", "NP": "NPL", "NZ": "NZL",
    "NI": "NIC", "NL": "NLD", "NE": "NER", "NG": "NGA", "KP": "PRK", "MK": "MKD", "NO": "NOR",
    "OM": "OMN", "AT": "AUT", "PK": "PAK", "PS": "PSE", "PW": "PLW", "PA": "PAN", "PG": "PNG",
    "PY": "PRY", "PE": "PER", "PH": "PHL", "PL": "POL", "PT": "PRT", "RW": "RWA", "RO": "ROU",
    "RU": "RUS", "SB": "SLB", "ZM": "ZMB", "WS": "WSM", "SM": "SMR", "ST": "STP", "SA": "SAU",
    "SE": "SWE", "CH": "CHE", "SN": "SEN", "RS": "SRB", "SC": "SYC", "SL": "SLE", "ZW": "ZWE",
    "SG": "SGP", "SK": "SVK", "SI": "SVN", "SO": "SOM", "ES": "ESP", "LK": "LKA", "KN": "KNA",
    "LC": "LCA", "VC": "VCT", "ZA": "ZAF", "SD": "SDN", "KR": "KOR", "SS": "SSD", "SR": "SUR",
    "SY": "SYR", "TJ": "TJK", "TW": "TWN", "TZ": "TZA", "TH": "THA", "TL": "TLS", "TG": "TGO",
    "TO": "TON", "TT": "TTO", "TD": "TCD", "CZ": "CZE", "TN": "TUN", "TR": "TUR", "TM": "TKM",
    "TV": "TUV", "UG": "UGA", "UA": "UKR", "HU": "HUN", "UY": "URY", "UZ": "UZB", "VU": "VUT",
    "VA": "VAT", "VE": "VEN", "AE": "ARE", "US": "USA", "GB": "GBR", "VN": "VNM", "CF": "CAF",
    "CY": "CYP",
}  # fmt: skip
# alpha-3 → deutscher Name (aus STAATEN); dazu MRZ-Besonderheiten (deutsche Pässe: „D"; Kosovo).
ALPHA3_NAME = {_ALPHA2_ALPHA3[code]: name for code, name in STAATEN if code in _ALPHA2_ALPHA3}
ALPHA3_NAME.update(
    {"D": "Deutschland", "XKX": "Kosovo", "XXK": "Kosovo", "GBR": ALPHA3_NAME["GBR"]}
)


def tesseract_vorhanden() -> bool:
    return shutil.which("tesseract") is not None


def aktiv(einstellungen) -> bool:
    """Zuschaltbar (Einstellung) und technisch möglich (Tesseract installiert)."""
    return bool(getattr(einstellungen, "ausweis_pruefen", False)) and tesseract_vorhanden()


def _staat_name(code: str) -> str:
    code = (code or "").strip("<").strip().upper()
    return ALPHA3_NAME.get(code, "")


def _dokumentart(typ: str) -> str:
    t = (typ or "").strip("<").upper()
    if t.startswith("P"):
        return "Reisepass"
    if t and t[0] in "IAC":
        return "Ausweis/Aufenthaltstitel"
    return "Dokument"


def _ocr(bild_bytes: bytes) -> str:
    import pytesseract
    from PIL import Image, ImageOps

    bild = ImageOps.exif_transpose(Image.open(io.BytesIO(bild_bytes))).convert("L")
    if max(bild.size) < 1600:  # kleine Fotos vergrößern hilft der OCR
        faktor = 1600 / max(bild.size)
        bild = bild.resize((round(bild.width * faktor), round(bild.height * faktor)))
    konfig = "--psm 6 -c tessedit_char_whitelist=ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789<"
    return pytesseract.image_to_string(bild, config=konfig)


def _mrz_zeilen(text: str) -> list[str]:
    zeilen = []
    for roh in text.splitlines():
        z = roh.strip().replace(" ", "")
        if len(z) >= 28 and "<" in z and re.fullmatch(r"[A-Z0-9<]+", z):
            zeilen.append(z)
    return zeilen


def _norm(zeile: str, laenge: int) -> str:
    return (zeile + "<" * laenge)[:laenge]


def _versuch(Checker, code):
    """Eine MRZ in einem Format auswerten; None, wenn sie nicht passt (OCR liefert oft Müll)."""
    try:
        checker = Checker(code, check_expiry=False)
        felder = checker.fields()
    except Exception:
        return None
    return (checker, felder) if (felder.nationality or felder.country) else None


def _auswerten(zeilen: list[str]):
    """Liefert (checker, fields) der ersten passenden MRZ oder (None, None)."""
    from mrz.checker.td1 import TD1CodeChecker
    from mrz.checker.td2 import TD2CodeChecker
    from mrz.checker.td3 import TD3CodeChecker

    for Checker, anzahl, laenge in ((TD3CodeChecker, 2, 44), (TD2CodeChecker, 2, 36),
                                    (TD1CodeChecker, 3, 30)):  # fmt: skip
        for i in range(len(zeilen) - anzahl + 1):
            teil = zeilen[i : i + anzahl]
            if not all(laenge - 5 <= len(z) <= laenge + 5 for z in teil):
                continue
            ergebnis = _versuch(Checker, "\n".join(_norm(z, laenge) for z in teil))
            if ergebnis:
                return ergebnis
    return None, None


def pruefen(bild_bytes: bytes, erwartete_staatsangehoerigkeit: str = "") -> dict:
    """Wertet das Bild aus. Liefert einen Bericht: erkannt (bool), bei Erfolg Dokumentart,
    ausstellendes Land, Staatsangehörigkeit (deutscher Name und Code), Name, Gültigkeit der
    Prüfziffern und – wenn eine Staatsangehörigkeit angegeben wurde – ob sie passt."""
    if not tesseract_vorhanden():
        return {"erkannt": False, "fehler": "OCR (Tesseract) ist nicht installiert."}
    try:
        text = _ocr(bild_bytes)
    except Exception:
        return {"erkannt": False, "fehler": "Das Bild konnte nicht gelesen werden."}
    checker, felder = _auswerten(_mrz_zeilen(text))
    if felder is None:
        return {"erkannt": False}
    staat = _staat_name(felder.nationality)
    bericht = {
        "erkannt": True,
        "gueltig": bool(checker),
        "dokument": _dokumentart(felder.document_type),
        "ausstellland": _staat_name(felder.country) or (felder.country or "").strip("<"),
        "staatsangehoerigkeit": staat or (felder.nationality or "").strip("<"),
        "code_staat": (felder.nationality or "").strip("<"),
        "name": f"{felder.name} {felder.surname}".strip(),
    }
    erwartet = (erwartete_staatsangehoerigkeit or "").strip()
    if erwartet and staat:
        bericht["passt"] = staat.casefold() == erwartet.casefold()
        bericht["erwartet"] = erwartet
    return bericht
