"""Export des bisherigen Programms (mehrblättriges Excel) → Importformat (ADR 0006, ADR 0100).

Reine Umwandlung ohne Datenbankzugriff: ``umwandeln(bytes)`` liest die Excel-Datei des
bisherigen Tafelprogramms, verbindet die Blätter über ihre Schlüssel und liefert die Dateien des
neutralen Importformats als Bytes zurück (Kundenstamm, Anträge, Mitarbeitende). Gespeichert wird
nichts: Die erzeugten Dateien gehen anschließend durch den normalen Import mit Abgleich.

Was je Tafel verschieden ist, kommt nicht aus festen Werten im Code:
* Ausgabestellen aus dem Blatt ``offices`` (Nummer → Name), ergänzt um die Zuordnung aus den
  Modul-Einstellungen;
* Einkommensarten aus den Modul-Einstellungen (im Export stehen sie nur als Nummer).
Fest sind nur die herstellerweiten Tabellen in ``codes.py`` (Anrede, Wochentag, Staaten).
"""

import csv
import datetime as dt
import io
import json
import re
from dataclasses import dataclass, field

import openpyxl

from apps.uebernahme import codes

KUNDENNUMMER_BREITE = (
    5  # Das bisherige Programm zeigt die Haushaltsnummer fünfstellig mit führenden Nullen
)

# Mitgelieferte Ja/Nein-Merkmale, die der Umwandler aus dem Export füllt (zusatz_<schlüssel>).
# Vor dem Import stellt die Ansicht sicher, dass diese Merkmale angelegt und aktiv sind,
# damit die Spalte nicht stillschweigend übersprungen wird (ADR 0071, ADR 0100).
GELIEFERTE_MERKMALE = ("schwerbehindert",)


class UebernahmeFehler(Exception):
    """Die hochgeladene Datei ist keine lesbare Excel-Datei des bisherigen Programms."""


# --- Zellwerte --------------------------------------------------------------------------

_STEUERZEICHEN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def _text(wert) -> str:
    # Steuerzeichen (vor allem NUL) kann PostgreSQL nicht als Text speichern; Tab/Umbruch bleiben.
    return "" if wert is None else _STEUERZEICHEN.sub("", str(wert)).strip()


def _name(wert) -> str:
    """Namen lesbar machen: komplett GROSS geschriebene Namen aus dem Altsystem (z. B. „BRÜGGE“,
    „BUERS“) werden in Titelfall gewandelt (Brügge, Buers). Namen mit Kleinbuchstaben – auch
    „McDonald“ oder „van Berg“ – bleiben unverändert, damit bewusste Schreibweisen erhalten
    bleiben."""
    text = _text(wert)
    buchstaben = [c for c in text if c.isalpha()]
    if buchstaben and not any(c.islower() and c.isascii() for c in buchstaben):
        return text.title()
    return text


def _zahl(wert):
    if wert is None or wert == "":
        return None
    try:
        return int(str(wert).strip())
    except (ValueError, TypeError):
        return None


def _dmy(d) -> str:
    # Jahr immer vierstellig: strftime("%Y") liefert für Jahre vor 1000 nur drei Stellen, die
    # danach nicht mehr als Datum lesbar wären (manche Kunden tippen im Antrag z. B. „962“).
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d}"


def _datum(wert) -> str:
    """Beliebiges Datum aus dem Export → 'TT.MM.JJJJ' (oder '')."""
    if wert is None or wert == "":
        return ""
    if isinstance(wert, (dt.datetime, dt.date)):
        return _dmy(wert)
    text = str(wert).strip()
    if not text or text.startswith(("0000", "-")):
        return ""
    text = text[:10]  # 'JJJJ-MM-TT HH:MM:SS' → 'JJJJ-MM-TT'
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return _dmy(dt.datetime.strptime(text, fmt))
        except ValueError:
            continue
    return ""


def _uhrzeit(wert) -> str:
    if wert is None or wert == "":
        return ""
    if isinstance(wert, (dt.time, dt.datetime)):
        return wert.strftime("%H:%M")
    teile = str(wert).strip().split(":")
    if len(teile) >= 2 and teile[0].isdigit() and teile[1].isdigit():
        return f"{int(teile[0]):02d}:{int(teile[1]):02d}"
    return ""


def _datum_zeit(wert) -> str:
    """Datum mit Uhrzeit → 'TT.MM.JJJJ HH:MM' (oder '' / nur Datum ohne Uhrzeit)."""
    if wert is None or wert == "":
        return ""
    if isinstance(wert, dt.datetime):
        return f"{_dmy(wert)} {wert:%H:%M}"
    if isinstance(wert, dt.date):
        return _dmy(wert)
    roh = str(wert).strip()
    tag = _datum(roh)
    if not tag:
        return ""
    m = re.search(r"(\d{1,2}):(\d{2})", roh[10:])
    return f"{tag} {int(m.group(1)):02d}:{m.group(2)}" if m else tag


def _kundennummer(hid) -> str:
    return str(hid).zfill(KUNDENNUMMER_BREITE)


def _janein(wert) -> str:
    """field6 (Schwerbehindert): beginnt der Text mit „ja“ → ja, sonst nein."""
    return "ja" if _text(wert).lower().startswith("ja") else "nein"


def _vor(d1: str, d2: str) -> bool:
    """True, wenn Datum d1 vor d2 liegt (beide 'TT.MM.JJJJ'); Leeres nie."""
    try:
        return dt.datetime.strptime(d1, "%d.%m.%Y") < dt.datetime.strptime(d2, "%d.%m.%Y")
    except ValueError:
        return False


def _erste_office(roh):
    """offices-Feld einer Kundengruppe (JSON-Liste oder Zahl) → erste Ausgabestellennummer."""
    if not roh:
        return None
    try:
        liste = json.loads(roh)
        return _zahl(liste[0]) if liste else None
    except (ValueError, TypeError):
        return _zahl(roh)


class _Blatt:
    """Ein Excel-Blatt als Liste von dicts (Spaltenkopf → Wert); gelöschte Zeilen (``deleted_at``
    gesetzt) werden ausgelassen."""

    def __init__(self, ws=None):
        self.zeilen: list[dict] = []
        if ws is None:
            return
        rows = ws.iter_rows(values_only=True)
        try:
            kopf = [str(k).strip() if k is not None else "" for k in next(rows)]
        except StopIteration:
            return
        hat_del = "deleted_at" in kopf
        di = kopf.index("deleted_at") if hat_del else -1
        for r in rows:
            if r is None or all(z is None for z in r) or r[0] is None:
                continue
            if hat_del and di < len(r) and r[di] not in (None, ""):
                continue  # gelöscht → nicht übernehmen
            self.zeilen.append(dict(zip(kopf, r, strict=False)))

    def nach(self, schluessel) -> dict:
        return {z.get(schluessel): z for z in self.zeilen}


def _csv_bytes(spalten: list[str], zeilen: list[dict]) -> bytes:
    puffer = io.StringIO()
    schreiber = csv.DictWriter(puffer, fieldnames=spalten, delimiter=";", extrasaction="ignore")
    schreiber.writeheader()
    schreiber.writerows(zeilen)
    return puffer.getvalue().encode("utf-8-sig")


@dataclass
class Umwandlung:
    kundenstamm: dict[str, bytes] = field(default_factory=dict)
    antraege: bytes = b""
    mitarbeitende: bytes = b""
    zusammenfassung: dict[str, int] = field(default_factory=dict)
    hinweise: list[str] = field(default_factory=list)


@dataclass
class BesucheUmwandlung:
    abholungen: bytes = b""
    anzahl: int = 0
    hinweise: list[str] = field(default_factory=list)


def _betrag_report(wert) -> str:
    """Beitrag aus dem Tagesreport ('3 €', '1,5 €', 3) → '3' / '1,5' (Komma als Dezimaltrenner,
    ohne €). Punkt als Dezimaltrenner wird zu Komma, damit es wie beim großen Konverter aussieht."""
    if wert is None or wert == "":
        return ""
    text = str(wert).replace("€", "").replace("EUR", "").strip().replace(" ", "")
    if "," not in text and text.count(".") == 1:
        text = text.replace(".", ",")
    return text


def besuche_umwandeln(daten: bytes) -> BesucheUmwandlung:
    """Tagesliste „kunden die da waren“ (ein Blatt, deutsche Spaltenköpfe, nur Nummern –
    keine Namen) → ``abholungen.csv`` des Importformats. Der Beitrag kommt als ``beitrag`` in die
    Abholung; der Kontostand ist eine Momentaufnahme (keine Buchung) und wird nicht übernommen.
    Die Datei spielt man anschließend über „Kundenstamm importieren → ergänzen“ ein.
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(daten), read_only=True, data_only=True)
    except Exception as fehler:  # noqa: BLE001 – openpyxl wirft je nach Datei Verschiedenes
        raise UebernahmeFehler(
            "Die Datei ließ sich nicht als Excel-Datei (.xlsx) öffnen. Bitte die Liste „kunden die "
            "da waren“ aus dem bisherigen Programm unverändert hochladen."
        ) from fehler
    ws = wb[wb.sheetnames[0]]
    rows = ws.iter_rows(values_only=True)
    kopf = None
    for r in rows:  # eine Titelzeile steht vor der Kopfzeile
        if r and any(_text(c).lower() == "kundennummer" for c in r):
            kopf = [_text(c).lower() for c in r]
            break
    if kopf is None:
        raise UebernahmeFehler(
            "In der Datei wurde keine Spalte „Kundennummer“ gefunden. Bitte die Liste „kunden die "
            "da waren“ aus dem bisherigen Programm unverändert als Excel-Datei (.xlsx) hochladen."
        )

    def spalte(*namen) -> int:
        for n in namen:
            if n in kopf:
                return kopf.index(n)
        return -1

    i_knr = spalte("kundennummer", "nummer")
    i_datum = spalte("letzter besuch", "besuch", "datum")
    i_zeit = spalte("uhrzeit", "zeit")
    i_beitrag = spalte("beitrag")

    abholungen, ohne_datum = [], 0
    for r in rows:
        if r is None or not (0 <= i_knr < len(r)):
            continue
        roh = r[i_knr]
        knr = str(roh).zfill(KUNDENNUMMER_BREITE) if isinstance(roh, int) else _text(roh)
        if not knr:
            continue
        datum = _datum(r[i_datum]) if 0 <= i_datum < len(r) else ""
        if not datum:
            ohne_datum += 1
            continue
        abholungen.append({
            "kundennummer": knr,
            "datum": datum,
            "uhrzeit": _uhrzeit(r[i_zeit]) if 0 <= i_zeit < len(r) else "",
            "beitrag": _betrag_report(r[i_beitrag]) if 0 <= i_beitrag < len(r) else "",
        })  # fmt: skip

    if not abholungen:
        raise UebernahmeFehler(
            "In der Datei standen keine Besuche mit Datum. Bitte prüfen, ob es die Liste „kunden "
            "die da waren“ mit den Spalten „Kundennummer“ und „Letzter Besuch“ ist."
        )
    hinweise = []
    if ohne_datum:
        hinweise.append(f"{ohne_datum} Zeile(n) ohne Datum („Letzter Besuch“) übersprungen.")
    csv_bytes = _csv_bytes(["kundennummer", "datum", "uhrzeit", "beitrag"], abholungen)
    return BesucheUmwandlung(abholungen=csv_bytes, anzahl=len(abholungen), hinweise=hinweise)


def umwandeln(
    daten: bytes,
    einkommensarten: dict | None = None,
    ausgabestellen: dict | None = None,
) -> Umwandlung:
    """Wandelt den Export (Bytes der .xlsx) in die Dateien des Importformats um.

    ``einkommensarten`` und ``ausgabestellen`` sind die Zuordnungen aus den Modul-Einstellungen
    (Nummer → Text), die im Export nur als Nummer stehen. Beide dürfen leer sein.
    """
    try:
        wb = openpyxl.load_workbook(io.BytesIO(daten), read_only=True, data_only=True)
    except Exception as fehler:  # noqa: BLE001 – openpyxl wirft je nach Datei Verschiedenes
        raise UebernahmeFehler(
            "Die Datei ließ sich nicht als Excel-Datei (.xlsx) öffnen. Bitte den Export aus dem "
            "bisherigen Tafelprogramm unverändert hochladen."
        ) from fehler
    namen = set(wb.sheetnames)

    def blatt(name: str) -> _Blatt:
        return _Blatt(wb[name]) if name in namen else _Blatt()

    personen = blatt("persons")
    haushalte = blatt("households")
    hp = blatt("household_person")
    receptions = blatt("receptions")
    locks = blatt("locks")
    exceptions = blatt("exceptions")
    notes = blatt("notes")
    clientgroups = blatt("clientgroups")
    offices = blatt("offices")
    applications = blatt("applications")
    staff = blatt("staff")
    staff_offices = blatt("staff_offices")

    if not haushalte.zeilen and not personen.zeilen:
        raise UebernahmeFehler(
            "In der Datei stehen keine Haushalte und Personen. Fehlt das Blatt „households“ bzw. "
            "„persons“? Bitte den vollständigen Export hochladen."
        )

    hinweise: list[str] = []
    ea_map = {str(_zahl(k)): v for k, v in (einkommensarten or {}).items() if _zahl(k) is not None}
    stellen = {str(_zahl(k)): v for k, v in (ausgabestellen or {}).items() if _zahl(k) is not None}
    for o in offices.zeilen:  # das Blatt gewinnt über die Einstellung
        oid, titel = _zahl(o.get("id")), _text(o.get("title"))
        if oid is not None and titel:
            stellen[str(oid)] = titel

    def stelle(oid) -> str:
        z = _zahl(oid)
        return stellen.get(str(z), "") if z is not None else ""

    def staat(nid) -> str:
        return codes.STAATSANGEHOERIGKEIT.get(_zahl(nid), "")

    def einkommen(iid) -> str:
        z = _zahl(iid)
        return ea_map.get(str(z), "") if z is not None else ""

    def anrede(titel) -> str:
        return codes.ANREDE.get(_text(titel).lower(), "")

    def wochentag(w) -> str:
        return codes.WOCHENTAG.get(_text(w).lower(), "")

    person_nach_id = personen.nach("id")
    gruppe_nach_id = clientgroups.nach("id")

    # Haushaltsvorstand, Angehörige und Abholberechtigte stehen in household_person über den type:
    # „householder“ = Vorstand, „relative“ = Angehörige, „collector“ = Abholberechtigte.
    # households.person_id ist unbrauchbar (zeigt bei allen auf dieselbe Person).
    hp_nach_haushalt: dict = {}
    for v in hp.zeilen:
        hp_nach_haushalt.setdefault(_zahl(v.get("household_id")), []).append(
            (_zahl(v.get("person_id")), _text(v.get("type")).lower())
        )

    def personen_mit_typ(hid, typ) -> list:
        return [pid for pid, t in hp_nach_haushalt.get(hid, []) if t == typ and pid]

    haushalte_zeilen, personen_zeilen, abholer_zeilen = [], [], []
    for h in haushalte.zeilen:
        hid = _zahl(h.get("id"))
        if hid is None:
            continue
        knr = _kundennummer(hid)
        kopf = personen_mit_typ(hid, "householder")
        haupt = person_nach_id.get(kopf[0], {}) if kopf else {}
        g = gruppe_nach_id.get(_zahl(h.get("clientgroup_id")), {})
        haushalte_zeilen.append({
            "kundennummer": knr,
            "nachname": _name(haupt.get("lastname")),
            "vorname": _name(haupt.get("firstname")),
            "anrede": anrede(haupt.get("title")),
            "geburtsdatum": _datum(haupt.get("birthday")),
            "staatsangehoerigkeit": staat(haupt.get("nationality_id")),
            "status": "aktiv",
            "kundengruppe": _text(g.get("short")),
            "ausgabestelle": stelle(_erste_office(g.get("offices"))),
            "kunde_seit": _datum(h.get("household_since")),
            "ausweis_gueltig_bis": _datum(h.get("valid")),
            "letzter_besuch": _datum(h.get("lastvisit")),
            "einkommensart": einkommen(h.get("income_id")),
            "strasse": _text(haupt.get("street")),
            "plz": _text(haupt.get("zipcode")),
            "ort": _text(haupt.get("city")),
            "telefon": _text(haupt.get("telprivat")) or _text(haupt.get("telmobil")),
            "email": _text(haupt.get("email")),
            "zusatz_schwerbehindert": _janein(h.get("field6")),
        })  # fmt: skip
        for pid in personen_mit_typ(hid, "relative"):
            p = person_nach_id.get(pid)
            if p:
                personen_zeilen.append({
                    "kundennummer": knr,
                    "nachname": _name(p.get("lastname")),
                    "vorname": _name(p.get("firstname")),
                    "anrede": anrede(p.get("title")),
                    "geburtsdatum": _datum(p.get("birthday")),
                    "staatsangehoerigkeit": staat(p.get("nationality_id")),
                })  # fmt: skip
        for pid in personen_mit_typ(hid, "collector"):
            p = person_nach_id.get(pid)
            if p:
                abholer_zeilen.append({
                    "kundennummer": knr,
                    "nachname": _name(p.get("lastname")),
                    "vorname": _name(p.get("firstname")),
                    "geburtsdatum": _datum(p.get("birthday")),
                })  # fmt: skip

    # Abholungen/Sperren/Ausnahmen/Bemerkungen nur zu exportierten Haushalten. Gelöschte Haushalte
    # kommen (Datensparsamkeit) nicht mit; ihre Zeilen zeigten sonst auf eine fehlende Kundennummer.
    exportierte = {z["kundennummer"] for z in haushalte_zeilen}

    def zu_haushalt(hid) -> str:
        z = _zahl(hid)
        knr = _kundennummer(z) if z is not None else ""
        return knr if knr in exportierte else ""

    abholungen = []
    for r in receptions.zeilen:
        knr = zu_haushalt(r.get("household_id"))
        if knr:
            abholungen.append({
                "kundennummer": knr,
                "datum": _datum(r.get("date")),
                "uhrzeit": _uhrzeit(r.get("time")),
                "beitrag": _text(r.get("fee")).replace(".", ","),
                "ausgabestelle": stelle(r.get("office_id")),
            })  # fmt: skip

    sperren = []
    for s in locks.zeilen:
        knr = zu_haushalt(s.get("household_id"))
        if not knr:
            continue
        von, bis = _datum(s.get("lock_from")), _datum(s.get("lock_until"))
        if not von:
            von, bis = bis, ""  # ohne Beginn: das vorhandene Datum als Beginn nehmen
        if von and bis and _vor(bis, von):
            von, bis = bis, von  # „bis vor von“ (im Altsystem vertauscht): Daten tauschen
        if von:
            sperren.append(
                {"kundennummer": knr, "von": von, "bis": bis, "begruendung": _text(s.get("reason"))}
            )

    ausnahmen = []
    for a in exceptions.zeilen:
        knr = zu_haushalt(a.get("household_id"))
        if knr:
            ausnahmen.append({
                "kundennummer": knr,
                "datum": _datum(a.get("date")),
                "begruendung": _text(a.get("reason")),
            })  # fmt: skip

    bemerkungen = []
    for n in notes.zeilen:
        knr = zu_haushalt(n.get("household_id"))
        if knr and _text(n.get("text")):
            bemerkungen.append({
                "kundennummer": knr,
                "datum": _datum(n.get("created_at")),
                "text": _text(n.get("text")),
            })  # fmt: skip

    gruppen = []
    for g in clientgroups.zeilen:
        gruppen.append({
            "kuerzel": _text(g.get("short")),
            "name": _text(g.get("title")),
            "ausgabestelle": stelle(_erste_office(g.get("offices"))),
            "wochentage": wochentag(g.get("weekday")),
            "uhrzeit": _text(g.get("description")),  # „Mittwoch 12:30-13:00“ o. Ä.
            "maximum": _text(_zahl(g.get("max")) or ""),
        })  # fmt: skip

    # Anträge: nur offene (status 0)
    antraege = []
    for a in applications.zeilen:
        if _zahl(a.get("status")) != 0:
            continue
        # „Weitere Angehörige“: nameRelatives enthält die Namen (teils je Zeile „Vorname
        # TT.MM.JJJJ“), relatives oft nur Freitext/Anzahl.
        ang = _text(a.get("nameRelatives")) or _text(a.get("relatives"))
        if ang.lower() in ("keine anhörige", "keine angehörige", "-", "0"):
            ang = ""
        antraege.append({
            "laufnummer": _text(_zahl(a.get("id")) or ""),
            "eingegangen_am": _datum_zeit(a.get("created_at")),
            "vorname": _name(a.get("firstname")),
            "nachname": _name(a.get("lastname")),
            "anrede": anrede(a.get("title")) or _text(a.get("title")),
            "geburtsdatum": _datum(a.get("birthday")),
            "strasse": _text(a.get("street")),
            "plz": _text(a.get("zipcode")),
            "ort": _text(a.get("city")),
            "telefon": _text(a.get("telmobil")),
            "email": _text(a.get("email")),
            "staatsangehoerigkeit": staat(a.get("nationality_id")),
            "wochentage": wochentag(a.get("weekday")),
            "nachricht": _text(a.get("message")),
            "anmerkung": _text(a.get("comment")),
            "angehoerige": ang,
        })  # fmt: skip

    # Mitarbeitende: aktive Konten mit Anschrift
    stellen_je_staff: dict = {}
    for r in staff_offices.zeilen:
        stellen_je_staff.setdefault(_zahl(r.get("staff_id")), []).append(stelle(r.get("office_id")))
    mitarbeitende = []
    for s in staff.zeilen:
        if _zahl(s.get("active")) == 0:
            continue
        p = person_nach_id.get(_zahl(s.get("person_id")))
        if not p:
            continue
        namen = stellen_je_staff.get(_zahl(s.get("id")), [])
        heim = stelle(s.get("office_id"))
        if heim and heim not in namen:
            namen = [heim, *namen]
        mitarbeitende.append({
            "anrede": anrede(p.get("title")),
            "vorname": _name(p.get("firstname")),
            "nachname": _name(p.get("lastname")),
            "geburtsdatum": _datum(p.get("birthday")),
            "strasse": _text(p.get("street")),
            "plz": _text(p.get("zipcode")),
            "ort": _text(p.get("city")),
            "telefon": _text(p.get("telprivat")),
            "handy": _text(p.get("telmobil")),
            "email": _text(p.get("email")),
            "eintritt": _datum(s.get("staff_since")),
            "beschaeftigung": "ehrenamtlich",
            "ausgabestellen": ", ".join(dict.fromkeys(n for n in namen if n)),
        })  # fmt: skip

    if not stellen:
        hinweise.append(
            "Es wurden keine Ausgabestellen erkannt. Tragen Sie die Ausgabestellen in den "
            "Einstellungen des Moduls ein (Nummer → Name) oder legen Sie sie vorher an; sonst "
            "bleibt die Ausgabestelle bei Haushalten und Gruppen leer."
        )
    if not ea_map and any(_zahl(h.get("income_id")) for h in haushalte.zeilen):
        hinweise.append(
            "Es sind Einkommensarten als Nummer vorhanden, aber keine Zuordnung hinterlegt. "
            "Tragen Sie die Einkommensarten in den Einstellungen des Moduls ein (Nummer → Text), "
            "sonst bleibt die Einkommensart leer."
        )

    kundenstamm = {
        "haushalte.csv": _csv_bytes(
            ["kundennummer", "nachname", "vorname", "anrede", "geburtsdatum",
             "staatsangehoerigkeit", "status", "kundengruppe", "ausgabestelle", "kunde_seit",
             "ausweis_gueltig_bis", "letzter_besuch", "einkommensart", "strasse", "plz", "ort",
             "telefon", "email", *[f"zusatz_{m}" for m in GELIEFERTE_MERKMALE]],
            haushalte_zeilen,
        ),
        "personen.csv": _csv_bytes(
            ["kundennummer", "nachname", "vorname", "anrede", "geburtsdatum",
             "staatsangehoerigkeit"],
            personen_zeilen,
        ),
        "abholer.csv": _csv_bytes(
            ["kundennummer", "nachname", "vorname", "geburtsdatum"], abholer_zeilen
        ),
        "abholungen.csv": _csv_bytes(
            ["kundennummer", "datum", "uhrzeit", "beitrag", "ausgabestelle"], abholungen
        ),
        "sperren.csv": _csv_bytes(["kundennummer", "von", "bis", "begruendung"], sperren),
        "ausnahmen.csv": _csv_bytes(["kundennummer", "datum", "begruendung"], ausnahmen),
        "bemerkungen.csv": _csv_bytes(["kundennummer", "datum", "text"], bemerkungen),
        "kundengruppen.csv": _csv_bytes(
            ["kuerzel", "name", "ausgabestelle", "wochentage", "uhrzeit", "maximum"], gruppen
        ),
    }  # fmt: skip
    antraege_bytes = _csv_bytes(
        ["laufnummer", "eingegangen_am", "vorname", "nachname", "anrede", "geburtsdatum",
         "strasse", "plz", "ort", "telefon", "email", "staatsangehoerigkeit", "wochentage",
         "nachricht", "anmerkung", "angehoerige"],
        antraege,
    )  # fmt: skip
    mitarbeitende_bytes = _csv_bytes(
        ["anrede", "vorname", "nachname", "geburtsdatum", "strasse", "plz", "ort", "telefon",
         "handy", "email", "eintritt", "beschaeftigung", "ausgabestellen"],
        mitarbeitende,
    )  # fmt: skip

    return Umwandlung(
        kundenstamm=kundenstamm,
        antraege=antraege_bytes,
        mitarbeitende=mitarbeitende_bytes,
        zusammenfassung={
            "haushalte": len(haushalte_zeilen),
            "personen": len(personen_zeilen),
            "abholer": len(abholer_zeilen),
            "abholungen": len(abholungen),
            "sperren": len(sperren),
            "ausnahmen": len(ausnahmen),
            "bemerkungen": len(bemerkungen),
            "kundengruppen": len(gruppen),
            "antraege": len(antraege),
            "mitarbeitende": len(mitarbeitende),
        },
        hinweise=hinweise,
    )
