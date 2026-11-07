"""Lokale Ausweisprüfung über die maschinenlesbare Zone (MRZ), ADR 0107.

Liest lokal auf dem Server die MRZ eines fotografierten Ausweises oder Passes und wertet sie nach
ICAO 9303 aus: ausstellendes Land und Staatsangehörigkeit (als Ländercode mit Prüfziffern),
Dokumentart und Name. Kein externer Dienst, keine KI – das Bild verlässt den Server nicht. Das
Ergebnis ist nur ein Hinweis zur Prüfung durch einen Menschen; nichts läuft automatisch.

Erkennung in zwei Stufen:

1. **PassportEye** (bevorzugt): findet die MRZ-Zone selbstständig im Foto (auch neben Gesicht und
   Rand), schneidet nur dieses Band aus, vergrößert es und liest es mit Tesseract. Die zeichenweise
   Auswertung berücksichtigt, an welcher Stelle der MRZ Buchstaben bzw. Ziffern stehen, und
   korrigiert typische OCR-Verwechslungen (O/0, B/8). Das macht die Prüfung auf echten, nicht
   perfekt geraden Fotos erst brauchbar – das bloße Lesen des ganzen Bildes (Stufe 2) scheiterte
   dort meist.
2. **Tesseract über das ganze Bild** mit dem ``mrz``-Parser als Rückfall, falls PassportEye kein
   Band findet.

Fehlt die MRZ oder ist sie unleserlich, wird nichts geraten (erkannt=False).
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
# Deutscher Ländername (kleingeschrieben) → alpha-3-Code, für die Erkennung am Textfeld
# „Staatsangehörigkeit" (ohne MRZ). Erster Code je Name.
NAME_ALPHA3 = {name.casefold(): code for code, name in ALPHA3_NAME.items() if len(code) == 3}


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


def pruefen_datei(inhalt: bytes, typ: str, erwartete_staatsangehoerigkeit: str = "") -> dict:
    """Einen Nachweis prüfen – Bild direkt, PDF Seite für Seite gerendert (ADR 0107). Viele laden
    ihren Ausweis als PDF hoch; diese Bilder werden so einbezogen."""
    typ = (typ or "").lower()
    if "pdf" in typ:
        from apps.antraege import pdf_bilder

        letzter = {"erkannt": False}
        for bild in pdf_bilder.seiten_bilder(inhalt):
            bericht = pruefen(bild, erwartete_staatsangehoerigkeit)
            if bericht.get("erkannt"):
                return bericht
            letzter = bericht
        return letzter
    if "image" in typ:
        return pruefen(inhalt, erwartete_staatsangehoerigkeit)
    return {"erkannt": False}


def _passporteye(bild_bytes: bytes) -> dict | None:
    """Stufe 1: PassportEye findet und liest das MRZ-Band selbst. Liefert die neutralen Werte
    (gleiche Form wie die Rückfallstufe) oder None, wenn kein Band gefunden wurde."""
    import warnings

    from passporteye import read_mrz

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")  # skimage-Deprecation-Warnungen nicht ins Log
        try:
            mrz = read_mrz(io.BytesIO(bild_bytes))
        except Exception:
            return None
    if mrz is None:
        return None
    d = mrz.to_dict()
    if not (d.get("nationality") or d.get("country")):
        return None
    return {
        "dokument": _dokumentart(d.get("type") or d.get("mrz_type")),
        "country": (d.get("country") or "").strip("<"),
        "nationality": (d.get("nationality") or "").strip("<"),
        "name": f"{d.get('names', '')} {d.get('surname', '')}".strip(),
        # valid_score == 100 heißt: alle Prüfziffern stimmen
        "gueltig": int(d.get("valid_score") or 0) >= 100,
    }


def _rueckfall(bild_bytes: bytes) -> dict | None:
    """Stufe 2: ganzes Bild per Tesseract lesen und mit dem ``mrz``-Parser auswerten."""
    try:
        text = _ocr(bild_bytes)
    except Exception:
        return None
    checker, felder = _auswerten(_mrz_zeilen(text))
    if felder is None:
        return None
    return {
        "dokument": _dokumentart(felder.document_type),
        "country": (felder.country or "").strip("<"),
        "nationality": (felder.nationality or "").strip("<"),
        "name": f"{felder.name} {felder.surname}".strip(),
        "gueltig": bool(checker),
    }


# Beschriftungen des Staatsangehörigkeits-Feldes (klein verglichen). Die MRZ steht nur auf einer
# Seite; liegt die andere vor, steht die Staatsangehörigkeit im Klartext unter dieser Beschriftung.
NATIONALITAET_WOERTER = (
    "staatsangehörigkeit", "staatsangehorigkeit", "staatsangehoerigkeit",
    "nationality", "nationalité", "nationalite", "nationalität", "nationalitat",
)  # fmt: skip
# Nationalitäts-Adjektiv → alpha-3-Code. Nur das mit Abstand häufigste (deutsche Ausweise);
# für alles andere greifen Ländercode und -name.
ADJEKTIV_CODE = {"deutsch": "DEU"}
# alpha-3-Codes, die als englische/deutsche Alltagswörter auftreten und darum zu viele Fehltreffer
# brächten („and", „are") – am Nationalitätsfeld werden sie nicht als Code gewertet.
_CODE_SPERRE = {"AND", "ARE"}


def _code_aus_fenster(fenster: str) -> str:
    """Aus dem Textausschnitt hinter der Feldbeschriftung einen alpha-3-Ländercode, einen deutschen
    Ländernamen oder das Adjektiv „deutsch" zu einem Code machen. Leer, wenn nichts Gültiges."""
    # Drei Großbuchstaben, die NICHT Teil eines längeren Buchstabenworts sind – also auch ein Code,
    # der (wie in der MRZ) direkt an Ziffern klebt, z. B. „…662UKR100…". Eine Wortgrenze (\b) gäbe
    # es zwischen Ziffer und Buchstabe nicht, darum scheiterte die Erkennung dort bisher. In echtem
    # Text greift es trotzdem nicht in Wörter hinein („DEUTSCHLAND" liefert kein „DEU").
    for wort in re.findall(r"(?<![A-Z])[A-Z]{3}(?![A-Z])", fenster.upper()):
        if wort in ALPHA3_NAME and wort not in _CODE_SPERRE:
            return wort
    klein = fenster.casefold()
    for name, code in NAME_ALPHA3.items():
        if len(name) >= 4 and re.search(rf"\b{re.escape(name)}\b", klein):
            return code
    for adjektiv, code in ADJEKTIV_CODE.items():
        if re.search(rf"\b{adjektiv}\b", klein):
            return code
    return ""


def _staat_aus_text(bild_bytes: bytes) -> dict | None:
    """Stufe 3 (Rückfall ohne MRZ): den freien Text lesen und unter der Beschriftung
    „Staatsangehörigkeit / Nationality" den Ländercode bzw. -namen erkennen. Liegt nur die Seite
    ohne MRZ vor, hebt das die Trefferquote deutlich. Nur gültige Länder werden gewertet."""
    try:
        text = _ocr_text(bild_bytes)
    except Exception:
        return None
    zeilen = [z.strip() for z in text.splitlines() if z.strip()]
    for i, zeile in enumerate(zeilen):
        if not any(w in zeile.casefold() for w in NATIONALITAET_WOERTER):
            continue
        # Rest der Beschriftungszeile und die nächsten beiden Zeilen (der Wert steht dahinter)
        code = _code_aus_fenster(" ".join(zeilen[i : i + 3]))
        if code:
            return {"dokument": "Dokument", "country": "", "nationality": code,
                    "name": "", "gueltig": False, "nur_feld": True}  # fmt: skip
    return None


def pruefen(bild_bytes: bytes, erwartete_staatsangehoerigkeit: str = "") -> dict:
    """Wertet das Bild aus. Liefert einen Bericht: erkannt (bool), bei Erfolg Dokumentart,
    ausstellendes Land, Staatsangehörigkeit (deutscher Name und Code), Name, Gültigkeit der
    Prüfziffern und – wenn eine Staatsangehörigkeit angegeben wurde – ob sie passt."""
    if not tesseract_vorhanden():
        return {"erkannt": False, "fehler": "OCR (Tesseract) ist nicht installiert."}
    try:
        from PIL import Image

        Image.open(io.BytesIO(bild_bytes)).verify()  # ist es überhaupt ein lesbares Bild?
    except Exception:
        return {"erkannt": False, "fehler": "Das Bild konnte nicht gelesen werden."}
    # Stufe 1/2 lesen die MRZ; findet keine der beiden eine, liest Stufe 3 das Feld
    # „Staatsangehörigkeit" im Klartext (die Seite ohne MRZ).
    roh = _passporteye(bild_bytes) or _rueckfall(bild_bytes) or _staat_aus_text(bild_bytes)
    if roh is None:
        return {"erkannt": False}
    # Nur ein echtes Land aus der Länderliste gilt als erkannte Staatsangehörigkeit bzw. als
    # ausstellendes Land. OCR liest aus der MRZ oft Müll (z. B. „E<E“, „OSI“, „662“); solche
    # Lesungen dürfen NIE als Staat angezeigt werden – sonst stehen Phantasie-Staaten im Ergebnis.
    staat = _staat_name(roh["nationality"])
    bericht = {
        "erkannt": True,
        "gueltig": roh["gueltig"],
        "dokument": roh["dokument"],
        "ausstellland": _staat_name(roh["country"]),  # leer, wenn kein gültiges Land (kein Müll)
        "staatsangehoerigkeit": staat,  # nur ein gültiges Land; sonst leer, nie die Rohlesung
        "code_staat": roh["nationality"] if staat else "",  # Code nur zu einem gültigen Land zeigen
        "name": roh["name"],
        # Nur aus dem Textfeld gelesen (keine MRZ geprüft) – schwächerer Hinweis.
        "nur_feld": roh.get("nur_feld", False),
    }
    erwartet = (erwartete_staatsangehoerigkeit or "").strip()
    if erwartet and staat:
        bericht["passt"] = staat.casefold() == erwartet.casefold()
        bericht["erwartet"] = erwartet
    return bericht


# Wörter, die ein behördliches Dokument (Bescheid) statt eines Ausweises anzeigen (ADR 0112).
# Kleingeschrieben; der OCR-Text wird ebenfalls kleingeschrieben verglichen. Bewusst knapp und
# eindeutig gehalten – die Einordnung erleichtert nur die Arbeit, sie entscheidet nichts.
AMTSDOKUMENT_WOERTER = (
    "bescheid", "grundsicherung", "bürgergeld", "buergergeld", "arbeitslosengeld",
    "jobcenter", "job center", "wohngeld", "sozialamt", "sozialhilfe", "regelbedarf",
    "regelleistung", "leistungsbescheid", "rentenbescheid", "familienkasse",
    "bundesagentur für arbeit", "sgb ii", "sgb xii", "asylbewerberleistung",
)  # fmt: skip


def _ocr_text(bild_bytes: bytes) -> str:
    """Freier OCR-Text eines Bildes (Deutsch+Englisch, ohne MRZ-Whitelist) – für die Erkennung von
    Amtsdokumenten am Textinhalt. Fällt bei fehlender deutscher Sprachdatei auf Englisch zurück."""
    import pytesseract
    from PIL import Image, ImageOps

    bild = ImageOps.exif_transpose(Image.open(io.BytesIO(bild_bytes))).convert("L")
    if max(bild.size) < 1600:
        faktor = 1600 / max(bild.size)
        bild = bild.resize((round(bild.width * faktor), round(bild.height * faktor)))
    try:
        return pytesseract.image_to_string(bild, lang="deu+eng")
    except pytesseract.TesseractError:
        return pytesseract.image_to_string(bild)  # ohne deutsche Sprachdatei


def _text_ist_amtsdokument(text: str) -> bool:
    klein = (text or "").casefold()
    return any(wort in klein for wort in AMTSDOKUMENT_WOERTER)


def ist_amtsdokument(inhalt: bytes, typ: str) -> bool:
    """True, wenn im Nachweis (Bild oder PDF) typische Wörter eines behördlichen Bescheids stehen
    (ADR 0112). Nur als Einordnung gedacht; prüft höchstens die ersten PDF-Seiten."""
    typ = (typ or "").lower()
    try:
        if "pdf" in typ:
            from apps.antraege import pdf_bilder

            for i, bild in enumerate(pdf_bilder.seiten_bilder(inhalt)):
                if i >= 2:  # erste Seiten genügen
                    break
                if _text_ist_amtsdokument(_ocr_text(bild)):
                    return True
            return False
        if "image" in typ:
            return _text_ist_amtsdokument(_ocr_text(inhalt))
    except Exception:  # noqa: BLE001 – nur eine Einordnung, nie kritisch
        return False
    return False


def _bild_bytes(inhalt: bytes, typ: str) -> bytes | None:
    """Rohbytes eines Bildes: ein Bild direkt, bei einem PDF die erste gerenderte Seite."""
    typ = (typ or "").lower()
    if "pdf" in typ:
        from apps.antraege import pdf_bilder

        seiten = pdf_bilder.seiten_bilder(inhalt, max_seiten=1)
        return seiten[0] if seiten else None
    if "image" in typ:
        return inhalt
    return None


def land_aus_ausschnitt(inhalt: bytes, typ: str, x: float, y: float, b: float, h: float) -> dict:
    """Liest nur einen vom Menschen gewählten **Ausschnitt** des Nachweises (Rechteck als Anteile
    0–1 des Bildes) und sucht darin eine gültige Staatsangehörigkeit (ADR 0107). Für klar lesbare
    Ausweise, bei denen die Voll-Automatik scheitert. Liefert ``{"land": name, "code": code}`` oder
    ``{"land": ""}``."""
    import io as _io

    from PIL import Image, ImageOps

    rohbild = _bild_bytes(inhalt, typ)
    if rohbild is None:
        return {"land": ""}
    try:
        bild = ImageOps.exif_transpose(Image.open(_io.BytesIO(rohbild)))
    except Exception:
        return {"land": ""}
    breite, hoehe = bild.size
    # Rechteck auf 0–1 begrenzen und in Pixel umrechnen; zu kleine Auswahl → nichts.
    x, y = max(0.0, min(1.0, x)), max(0.0, min(1.0, y))
    b, h = max(0.0, min(1.0 - x, b)), max(0.0, min(1.0 - y, h))
    if b < 0.02 or h < 0.02:
        return {"land": ""}
    kasten = (round(x * breite), round(y * hoehe), round((x + b) * breite), round((y + h) * hoehe))
    puffer = _io.BytesIO()
    bild.crop(kasten).save(puffer, format="PNG")
    ausschnitt = puffer.getvalue()
    # Zuerst normaler OCR-Text (deu+eng); wenn das keinen Code ergibt, die MRZ-Lesung (nur
    # Großbuchstaben/Ziffern/„<") versuchen – ein um die MRZ gezogenes Rechteck liest sie so
    # zuverlässiger (z. B. „…UKR…" zwischen Ziffern).
    code = ""
    for leser in (_ocr_text, _ocr):
        try:
            code = _code_aus_fenster(leser(ausschnitt))
        except Exception:
            code = ""
        if code:
            break
    return {"land": _staat_name(code), "code": code} if code else {"land": ""}
