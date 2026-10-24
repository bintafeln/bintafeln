"""Import des Kundenstamms nach docs/importformat.md.

Ablauf: ``pruefen()`` liest die hochgeladenen Dateien, erstellt den Prüfbericht und – wenn es
keine Fehler gibt – die bereinigten Daten. ``uebernehmen()`` ersetzt damit den gesamten
Kundenstamm in einer Transaktion. Der Prüfbericht enthält nie Inhalte aus den Dateien, nur Datei,
Zeile und Art des Problems.
"""

import csv
import datetime as dt
import hashlib
import io
from dataclasses import dataclass, field

from auditlog.context import disable_auditlog
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from apps.kunden import historie, werte
from apps.kunden.models import (
    Abholer,
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Bemerkung,
    Einkommensart,
    Haushalt,
    ImportLauf,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Sperre,
    Zusatzfeld,
    abholfrist_beginn,
    verwaiste_notizen_loeschen,
)

FEHLER = "fehler"
WARNUNG = "warnung"

HAUSHALTE = "haushalte.csv"
PERSONEN = "personen.csv"
ABHOLER = "abholer.csv"
SPERREN = "sperren.csv"
BEMERKUNGEN = "bemerkungen.csv"
KUNDENGRUPPEN = "kundengruppen.csv"
ABHOLUNGEN = "abholungen.csv"
AUSNAHMEN = "ausnahmen.csv"

SPALTEN = {
    HAUSHALTE: {
        "pflicht": ["kundennummer", "nachname", "vorname"],
        "optional": [
            "anrede",
            "geburtsdatum",
            "staatsangehoerigkeit",
            "familienstand",
            "status",
            "kundengruppe",
            "ausgabestelle",
            "kunde_seit",
            "ausweis_gueltig_bis",
            "letzter_besuch",
            "einkommensart",
            "strasse",
            "plz",
            "ort",
            "telefon",
            "email",
            "kontostand",
            "anzahl_erwachsene",
            "anzahl_kinder",
        ],
    },
    PERSONEN: {
        "pflicht": ["kundennummer", "nachname", "vorname"],
        "optional": ["anrede", "geburtsdatum", "staatsangehoerigkeit"],
    },
    ABHOLER: {
        "pflicht": ["kundennummer", "nachname", "vorname"],
        "optional": ["geburtsdatum", "eigene_kundennummer"],
    },
    SPERREN: {
        "pflicht": ["kundennummer", "von"],
        "optional": ["bis", "begruendung", "eingetragen_von"],
    },
    BEMERKUNGEN: {
        "pflicht": ["kundennummer", "datum", "text"],
        "optional": ["verfasst_von"],
    },
    KUNDENGRUPPEN: {
        "pflicht": ["kuerzel", "name", "ausgabestelle"],
        "optional": ["wochentage", "uhrzeit", "maximum", "aktiv"],
    },
    ABHOLUNGEN: {
        "pflicht": ["kundennummer", "datum"],
        "optional": ["uhrzeit", "beitrag", "ausgabestelle", "eingetragen_von"],
    },
    AUSNAHMEN: {
        "pflicht": ["kundennummer", "datum"],
        "optional": ["begruendung", "eingetragen_von"],
    },
}

# Spalten, die die Tafel in den Einstellungen abschalten kann.
ABSCHALTBAR = {
    "telefon": "telefon_erfassen",
    "email": "email_erfassen",
    "staatsangehoerigkeit": "staatsangehoerigkeit_erfassen",
    "familienstand": "familienstand_erfassen",
}

WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
MAX_LAENGE = {
    "kundennummer": 20,
    "eigene_kundennummer": 20,
    "anrede": 30,
    "vorname": 100,
    "nachname": 100,
    "staatsangehoerigkeit": 100,
    "familienstand": 50,
    "strasse": 200,
    "plz": 10,
    "ort": 100,
    "telefon": 50,
    "email": 254,
    "kundengruppe": 100,
    "ausgabestelle": 100,
    "einkommensart": 100,
    "eingetragen_von": 100,
    "verfasst_von": 100,
    "kuerzel": 20,
    "name": 100,
    "wochentage": 30,
}


@dataclass
class Ergebnis:
    bericht: list[dict] = field(default_factory=list)
    daten: dict | None = None
    pruefsumme: str = ""
    dateien: list[str] = field(default_factory=list)

    @property
    def fehler(self) -> list[dict]:
        return [m for m in self.bericht if m["stufe"] == FEHLER]

    @property
    def warnungen(self) -> list[dict]:
        return [m for m in self.bericht if m["stufe"] == WARNUNG]


def bericht_gruppiert(bericht: list[dict]) -> list[dict]:
    """Fasst gleiche Meldungen zusammen: je (Stufe, Datei, Text) eine Zeile mit Zeilennummern."""
    gruppen: dict[tuple, dict] = {}
    for m in bericht:
        schluessel = (m["stufe"], m["datei"], m["text"])
        gruppe = gruppen.setdefault(
            schluessel, {"stufe": m["stufe"], "datei": m["datei"], "text": m["text"], "zeilen": []}
        )
        if m["zeile"] is not None:
            gruppe["zeilen"].append(m["zeile"])
    ergebnis = sorted(gruppen.values(), key=lambda g: (g["stufe"] != FEHLER, g["datei"]))
    for g in ergebnis:
        g["anzahl"] = max(len(g["zeilen"]), 1)
        g["zeilen_kurz"] = ", ".join(map(str, g["zeilen"][:15])) + (
            f" … (+{len(g['zeilen']) - 15})" if len(g["zeilen"]) > 15 else ""
        )
    return ergebnis


class _Pruefung:
    def __init__(self, dateien: dict[str, bytes], heute: dt.date):
        self.roh = dateien
        self.heute = heute
        self.bericht: list[dict] = []
        self.einstellungen = KundenEinstellungen.laden()
        self.zusatzfelder = {f.schluessel: f for f in Zusatzfeld.objects.filter(aktiv=True)}
        self.inaktive_zusatzfelder = set(
            Zusatzfeld.objects.filter(aktiv=False).values_list("schluessel", flat=True)
        )

    # --- Meldungen --------------------------------------------------------------------

    def melden(self, stufe, datei, zeile, text):
        self.bericht.append({"stufe": stufe, "datei": datei, "zeile": zeile, "text": text})

    def fehler(self, datei, zeile, text):
        self.melden(FEHLER, datei, zeile, text)

    def warnung(self, datei, zeile, text):
        self.melden(WARNUNG, datei, zeile, text)

    # --- Lesen ------------------------------------------------------------------------

    def lesen(self, name) -> list[tuple[int, dict]] | None:
        """Liest eine Datei als Liste (Zeilennummer, {spalte: text}). None bei Formatfehler."""
        try:
            text = self.roh[name].decode("utf-8-sig")
        except UnicodeDecodeError:
            self.fehler(name, None, "Datei ist nicht in UTF-8 gespeichert (in Excel: „CSV UTF-8“).")
            return None
        erste_zeile = text.splitlines()[0] if text.strip() else ""
        if ";" not in erste_zeile:
            self.fehler(name, None, "Kein Semikolon als Trennzeichen in der Kopfzeile erkennbar.")
            return None
        leser = csv.reader(io.StringIO(text, newline=""), delimiter=";")
        kopf = [spalte.strip().lower() for spalte in next(leser)]

        erlaubt = set(SPALTEN[name]["pflicht"]) | set(SPALTEN[name]["optional"])
        for spalte in SPALTEN[name]["pflicht"]:
            if spalte not in kopf:
                self.fehler(name, None, f"Pflichtspalte „{spalte}“ fehlt.")
        if any(m["stufe"] == FEHLER and m["datei"] == name for m in self.bericht):
            return None
        for spalte in kopf:
            if spalte and spalte not in erlaubt and not spalte.startswith("zusatz_"):
                self.warnung(name, None, f"Unbekannte Spalte „{spalte}“ wird ignoriert.")
            if spalte in ABSCHALTBAR and not getattr(self.einstellungen, ABSCHALTBAR[spalte]):
                self.warnung(
                    name,
                    None,
                    f"Spalte „{spalte}“ ist in den Einstellungen abgeschaltet und wird nicht "
                    "gespeichert.",
                )

        zeilen = []
        for nummer, werte_ in enumerate(leser, start=2):
            if not any(w.strip() for w in werte_):
                continue
            zeile = {k: (werte_[i].strip() if i < len(werte_) else "") for i, k in enumerate(kopf)}
            if len(werte_) > len(kopf) and any(w.strip() for w in werte_[len(kopf) :]):
                self.warnung(name, nummer, "Mehr Werte als Spalten; überzählige ignoriert.")
            zeilen.append((nummer, zeile))
        return zeilen

    # --- Einzelwerte ------------------------------------------------------------------

    def text(self, datei, nummer, zeile, spalte, pflicht=False) -> str:
        wert = zeile.get(spalte, "")
        if spalte in ABSCHALTBAR and not getattr(self.einstellungen, ABSCHALTBAR[spalte]):
            return ""
        if pflicht and not wert:
            self.fehler(datei, nummer, f"Pflichtangabe „{spalte}“ ist leer.")
        grenze = MAX_LAENGE.get(spalte)
        if grenze and len(wert) > grenze:
            self.fehler(datei, nummer, f"„{spalte}“ ist zu lang (höchstens {grenze} Zeichen).")
        return wert

    def datum(self, datei, nummer, zeile, spalte, pflicht=False) -> str | None:
        wert = zeile.get(spalte, "")
        if pflicht and not wert:
            self.fehler(datei, nummer, f"Pflichtangabe „{spalte}“ ist leer.")
            return None
        try:
            datum = werte.datum(wert)
        except werte.UngueltigerWert:
            if pflicht:
                self.fehler(datei, nummer, f"„{spalte}“ ist kein gültiges Datum.")
            else:
                self.warnung(datei, nummer, f"„{spalte}“ ist kein gültiges Datum, bleibt leer.")
            return None
        return datum.isoformat() if datum else None

    def geburtsdatum(self, datei, nummer, zeile) -> str | None:
        iso = self.datum(datei, nummer, zeile, "geburtsdatum")
        if iso is None:
            return None
        datum = dt.date.fromisoformat(iso)
        if datum > self.heute or datum.year < self.heute.year - 120:
            self.warnung(datei, nummer, "Geburtsdatum unplausibel, bleibt leer.")
            return None
        return iso

    def uhrzeit(self, datei, nummer, zeile) -> str | None:
        wert = zeile.get("uhrzeit", "")
        try:
            return dt.time.fromisoformat(wert).isoformat("minutes") if wert else None
        except ValueError:
            self.warnung(datei, nummer, "„uhrzeit“ ist keine Uhrzeit, bleibt leer.")
            return None

    def zahl(self, datei, nummer, zeile, spalte) -> int | None:
        wert = zeile.get(spalte, "")
        if not wert:
            return None
        if wert.isdigit():
            return int(wert)
        self.warnung(datei, nummer, f"„{spalte}“ ist keine ganze Zahl, bleibt leer.")
        return None

    def zusatz(self, datei, nummer, zeile, gilt_fuer) -> dict:
        ergebnis = {}
        for spalte, wert in zeile.items():
            if not spalte.startswith("zusatz_"):
                continue
            feld = self.zusatzfelder.get(spalte.removeprefix("zusatz_"))
            if feld is None or feld.gilt_fuer != gilt_fuer:
                continue
            try:
                gelesen = feld.wert_lesen(wert)
            except werte.UngueltigerWert:
                self.warnung(datei, nummer, f"Wert für „{spalte}“ passt nicht, bleibt leer.")
                continue
            if gelesen is not None:
                ergebnis[feld.schluessel] = gelesen
        return ergebnis

    def zusatz_spalten_pruefen(self, datei, kopf, erlaubte_geltung):
        for spalte in kopf:
            if not spalte.startswith("zusatz_"):
                continue
            schluessel = spalte.removeprefix("zusatz_")
            feld = self.zusatzfelder.get(schluessel)
            if schluessel in self.inaktive_zusatzfelder:
                self.warnung(datei, None, f"Zusatzfeld „{spalte}“ ist inaktiv und wird ignoriert.")
            elif feld is None:
                self.warnung(
                    datei,
                    None,
                    f"Zu „{spalte}“ ist kein Zusatzfeld angelegt; Spalte wird ignoriert.",
                )
            elif feld.gilt_fuer not in erlaubte_geltung:
                self.warnung(
                    datei,
                    None,
                    f"Zusatzfeld „{spalte}“ gilt für Haushalte und wird hier ignoriert.",
                )

    def person(self, datei, nummer, zeile) -> dict:
        return {
            "anrede": self.text(datei, nummer, zeile, "anrede"),
            "vorname": self.text(datei, nummer, zeile, "vorname", pflicht=True),
            "nachname": self.text(datei, nummer, zeile, "nachname", pflicht=True),
            "geburtsdatum": self.geburtsdatum(datei, nummer, zeile),
            "staatsangehoerigkeit": self.text(datei, nummer, zeile, "staatsangehoerigkeit"),
            "familienstand": self.text(datei, nummer, zeile, "familienstand"),
            "zusatz": self.zusatz(datei, nummer, zeile, Zusatzfeld.GiltFuer.PERSON),
        }

    # --- Dateien ----------------------------------------------------------------------

    def kundengruppen(self, zeilen) -> list[dict]:
        gruppen, kuerzel_gesehen, namen_gesehen = [], set(), set()
        for nummer, z in zeilen:
            kuerzel = self.text(KUNDENGRUPPEN, nummer, z, "kuerzel", pflicht=True)
            name = self.text(KUNDENGRUPPEN, nummer, z, "name", pflicht=True)
            stelle = self.text(KUNDENGRUPPEN, nummer, z, "ausgabestelle", pflicht=True)
            if kuerzel.lower() in kuerzel_gesehen:
                self.fehler(KUNDENGRUPPEN, nummer, "Kürzel kommt doppelt vor.")
            if name.lower() in namen_gesehen:
                self.fehler(KUNDENGRUPPEN, nummer, "Name kommt doppelt vor.")
            kuerzel_gesehen.add(kuerzel.lower())
            namen_gesehen.add(name.lower())
            andere = Kundengruppe.objects.filter(name__iexact=name).exclude(kuerzel__iexact=kuerzel)
            if kuerzel and andere.exclude(kuerzel="").exists():
                self.fehler(
                    KUNDENGRUPPEN,
                    nummer,
                    "Name ist bereits einer Kundengruppe mit anderem Kürzel zugeordnet.",
                )
            tage = [t.strip().capitalize() for t in z.get("wochentage", "").split(",") if t.strip()]
            if any(t not in WOCHENTAGE for t in tage):
                self.warnung(KUNDENGRUPPEN, nummer, "Unbekannter Wochentag, Angabe bleibt leer.")
                tage = []
            try:
                aktiv = werte.ja_nein(z.get("aktiv") or "ja")
            except werte.UngueltigerWert:
                self.warnung(KUNDENGRUPPEN, nummer, "„aktiv“ ist kein Ja/Nein-Wert, gilt als ja.")
                aktiv = True
            gruppen.append(
                {
                    "kuerzel": kuerzel,
                    "name": name,
                    "ausgabestelle": stelle,
                    "wochentage": ",".join(tage),
                    "uhrzeit": self.uhrzeit(KUNDENGRUPPEN, nummer, z),
                    "maximum": self.zahl(KUNDENGRUPPEN, nummer, z, "maximum"),
                    "aktiv": aktiv,
                }
            )
        return gruppen

    def gruppe_finden(self, text, csv_gruppen) -> dict | None:
        klein = text.lower()
        for g in csv_gruppen:
            if g["kuerzel"].lower() == klein:
                return {"kuerzel": g["kuerzel"], "name": g["name"]}
        for g in csv_gruppen:
            if g["name"].lower() == klein:
                return {"kuerzel": g["kuerzel"], "name": g["name"]}
        vorhanden = (
            Kundengruppe.objects.filter(kuerzel__iexact=text).exclude(kuerzel="").first()
            or Kundengruppe.objects.filter(name__iexact=text).first()
        )
        if vorhanden:
            return {"kuerzel": vorhanden.kuerzel, "name": vorhanden.name}
        return None

    def haushalte(self, zeilen, mit_personen, csv_gruppen):
        haushalte, nummern = [], set()
        neue_gruppen: dict[str, dict] = {}
        bekannte_arten = {
            e.lower() for e in Einkommensart.objects.values_list("bezeichnung", flat=True)
        }
        if (
            zeilen
            and mit_personen
            and ("anzahl_erwachsene" in zeilen[0][1] or "anzahl_kinder" in zeilen[0][1])
        ):
            self.warnung(
                HAUSHALTE,
                None,
                "Anzahl Erwachsene/Kinder wird ignoriert, weil personen.csv geliefert wurde.",
            )
        for nummer, z in zeilen:
            kundennummer = self.text(HAUSHALTE, nummer, z, "kundennummer", pflicht=True)
            if kundennummer and kundennummer in nummern:
                self.fehler(HAUSHALTE, nummer, "Kundennummer kommt doppelt vor.")
            nummern.add(kundennummer)

            status = (z.get("status") or "aktiv").lower()
            if status not in Haushalt.Status.values:
                self.fehler(HAUSHALTE, nummer, "Unbekannter Status.")

            gruppe = None
            gruppen_text = self.text(HAUSHALTE, nummer, z, "kundengruppe")
            stelle = self.text(HAUSHALTE, nummer, z, "ausgabestelle")
            if gruppen_text:
                gruppe = self.gruppe_finden(gruppen_text, csv_gruppen)
                if gruppe is None:
                    if gruppen_text.lower() not in neue_gruppen:
                        self.warnung(
                            HAUSHALTE,
                            nummer,
                            "Kundengruppe unbekannt; wird mit dem angegebenen Namen angelegt.",
                        )
                        neue_gruppen[gruppen_text.lower()] = {
                            "name": gruppen_text,
                            "ausgabestelle": stelle,
                        }
                    gruppe = {"kuerzel": "", "name": neue_gruppen[gruppen_text.lower()]["name"]}

            art = self.text(HAUSHALTE, nummer, z, "einkommensart")
            if art and art.lower() not in bekannte_arten:
                self.warnung(HAUSHALTE, nummer, "Einkommensart unbekannt; wird angelegt.")
                bekannte_arten.add(art.lower())

            telefon = self.text(HAUSHALTE, nummer, z, "telefon")
            if telefon and not telefon.startswith(("0", "+")):
                self.warnung(
                    HAUSHALTE,
                    nummer,
                    "Telefonnummer beginnt nicht mit 0 oder + (führende 0 verloren?).",
                )
            email = self.text(HAUSHALTE, nummer, z, "email")
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    self.warnung(HAUSHALTE, nummer, "E-Mail-Adresse ungültig, bleibt leer.")
                    email = ""

            try:
                kontostand = werte.betrag(z.get("kontostand", ""))
            except werte.UngueltigerWert:
                self.warnung(HAUSHALTE, nummer, "„kontostand“ ist kein Betrag, bleibt leer.")
                kontostand = None

            ausweis = self.datum(HAUSHALTE, nummer, z, "ausweis_gueltig_bis")
            if ausweis and dt.date.fromisoformat(ausweis) < self.heute:
                self.warnung(HAUSHALTE, nummer, "Ausweis ist abgelaufen.")

            haushalte.append(
                {
                    "kundennummer": kundennummer,
                    "status": status,
                    "kundengruppe": gruppe,
                    "kunde_seit": self.datum(HAUSHALTE, nummer, z, "kunde_seit"),
                    "ausweis_gueltig_bis": ausweis,
                    "letzter_besuch": self.datum(HAUSHALTE, nummer, z, "letzter_besuch"),
                    "einkommensart": art,
                    "strasse": self.text(HAUSHALTE, nummer, z, "strasse"),
                    "plz": self.text(HAUSHALTE, nummer, z, "plz"),
                    "ort": self.text(HAUSHALTE, nummer, z, "ort"),
                    "telefon": telefon,
                    "email": email,
                    "kontostand": str(kontostand) if kontostand is not None else None,
                    "anzahl_erwachsene": None
                    if mit_personen
                    else self.zahl(HAUSHALTE, nummer, z, "anzahl_erwachsene"),
                    "anzahl_kinder": None
                    if mit_personen
                    else self.zahl(HAUSHALTE, nummer, z, "anzahl_kinder"),
                    "zusatz": self.zusatz(HAUSHALTE, nummer, z, Zusatzfeld.GiltFuer.HAUSHALT),
                    "hauptperson": self.person(HAUSHALTE, nummer, z),
                }
            )
        return haushalte, nummern, list(neue_gruppen.values())

    def abholdaten(self, gelesen) -> tuple[list[dict], list[dict]]:
        """Abholungen und Ausnahmen; ältere als die Aufbewahrungsfrist werden ausgelassen."""
        beginn = abholfrist_beginn(self.heute).isoformat()
        bekannte_stellen = {
            s.lower() for s in Ausgabestelle.objects.values_list("name", flat=True)
        } | {g["ausgabestelle"].lower() for g in self.csv_gruppen}

        abholungen = []
        for n, z in gelesen.get(ABHOLUNGEN, []):
            datum = self.datum(ABHOLUNGEN, n, z, "datum", pflicht=True)
            stelle = self.text(ABHOLUNGEN, n, z, "ausgabestelle")
            if stelle and stelle.lower() not in bekannte_stellen:
                self.warnung(ABHOLUNGEN, n, "Ausgabestelle unbekannt; wird angelegt.")
                bekannte_stellen.add(stelle.lower())
            try:
                beitrag = werte.betrag(z.get("beitrag", ""))
            except werte.UngueltigerWert:
                self.warnung(ABHOLUNGEN, n, "„beitrag“ ist kein Betrag, bleibt leer.")
                beitrag = None
            eintrag = {
                "kundennummer": z.get("kundennummer", ""),
                "datum": datum,
                "uhrzeit": self.uhrzeit(ABHOLUNGEN, n, z),
                "beitrag": str(beitrag) if beitrag is not None else None,
                "ausgabestelle": stelle,
                "eingetragen_von": self.text(ABHOLUNGEN, n, z, "eingetragen_von"),
            }
            if datum and datum < beginn:
                self.warnung(
                    ABHOLUNGEN, n, "Älter als die Aufbewahrungsfrist; wird nicht übernommen."
                )
            elif datum:
                abholungen.append(eintrag)

        ausnahmen = []
        for n, z in gelesen.get(AUSNAHMEN, []):
            datum = self.datum(AUSNAHMEN, n, z, "datum", pflicht=True)
            eintrag = {
                "kundennummer": z.get("kundennummer", ""),
                "datum": datum,
                "begruendung": z.get("begruendung", ""),
                "eingetragen_von": self.text(AUSNAHMEN, n, z, "eingetragen_von"),
            }
            if datum and datum < beginn:
                self.warnung(
                    AUSNAHMEN, n, "Älter als die Aufbewahrungsfrist; wird nicht übernommen."
                )
            elif datum:
                ausnahmen.append(eintrag)
        return abholungen, ausnahmen

    def zugeordnet(self, datei, zeilen, nummern):
        for nummer, z in zeilen:
            if z.get("kundennummer") and z["kundennummer"] not in nummern:
                self.fehler(datei, nummer, "Kundennummer gibt es nicht in haushalte.csv.")

    def ausfuehren(self) -> dict | None:
        bekannt = {name.lower(): name for name in SPALTEN}
        dateien = {}
        for name, inhalt in self.roh.items():
            schluessel = name.lower()
            if schluessel in bekannt:
                dateien[bekannt[schluessel]] = inhalt
            else:
                self.warnung(name, None, "Unbekannte Datei wird ignoriert.")
        self.roh = dateien
        if HAUSHALTE not in dateien:
            self.fehler(HAUSHALTE, None, "Pflichtdatei haushalte.csv fehlt.")
            return None

        gelesen = {name: self.lesen(name) for name in dateien}
        if any(v is None for v in gelesen.values()):
            return None

        for name, kopf_von in (
            (HAUSHALTE, (Zusatzfeld.GiltFuer.HAUSHALT, Zusatzfeld.GiltFuer.PERSON)),
            (PERSONEN, (Zusatzfeld.GiltFuer.PERSON,)),
        ):
            if gelesen.get(name):
                self.zusatz_spalten_pruefen(name, gelesen[name][0][1].keys(), kopf_von)

        bemerkungen_an = self.einstellungen.bemerkungen_importieren
        if BEMERKUNGEN in gelesen and not bemerkungen_an:
            self.warnung(
                BEMERKUNGEN,
                None,
                "Import von Anmerkungen ist in den Einstellungen abgeschaltet; Datei ignoriert.",
            )
            del gelesen[BEMERKUNGEN]

        vorher = {
            PERSONEN: Person.objects.filter(ist_hauptperson=False).exists(),
            ABHOLER: Abholer.objects.exists(),
            SPERREN: Sperre.objects.exists(),
            BEMERKUNGEN: Bemerkung.objects.exists() and bemerkungen_an,
            ABHOLUNGEN: Abholung.objects.exists(),
            AUSNAHMEN: Ausnahme.objects.exists(),
        }
        for name, modell in ((ABHOLUNGEN, Abholung), (AUSNAHMEN, Ausnahme)):
            erfasst = modell.objects.filter(erfasst_am__isnull=False).count()
            if erfasst:
                self.warnung(
                    name,
                    None,
                    f"{erfasst} am Einlass in bintafeln erfasste Einträge werden durch den "
                    "Import ersetzt und gehen verloren.",
                )
        von_hand = Haushalt.objects.filter(geaendert_am__isnull=False).count()
        if von_hand:
            self.warnung(
                HAUSHALTE,
                None,
                f"In bintafeln von Hand geänderte oder angelegte Haushalte: {von_hand}. "
                "Der Import ersetzt diese Änderungen.",
            )
        # Kontobuchungen gehören zur App ausgabe; späte Einbindung vermeidet einen Kreisbezug.
        from apps.ausgabe.models import Buchung

        buchungen = Buchung.objects.filter(haushalt__isnull=False).count()
        if buchungen:
            self.warnung(
                HAUSHALTE,
                None,
                f"{buchungen} Kontobuchungen aus bintafeln gehören danach zu keinem Haushalt "
                "mehr; der Kontostand kommt aus dem Import. Für die Kasse bleiben sie erhalten.",
            )
        for name, vorhanden in vorher.items():
            if vorhanden and name not in gelesen:
                self.warnung(
                    name,
                    None,
                    "Datei fehlt; die bisher vorhandenen Angaben dieser Art werden entfernt.",
                )

        csv_gruppen = self.csv_gruppen = self.kundengruppen(gelesen.get(KUNDENGRUPPEN, []))
        haushalte, nummern, neue_gruppen = self.haushalte(
            gelesen[HAUSHALTE], PERSONEN in gelesen, csv_gruppen
        )
        for name in (PERSONEN, ABHOLER, SPERREN, BEMERKUNGEN, ABHOLUNGEN, AUSNAHMEN):
            self.zugeordnet(name, gelesen.get(name, []), nummern)

        personen = []
        for nummer, z in gelesen.get(PERSONEN, []):
            p = self.person(PERSONEN, nummer, z)
            if not p["geburtsdatum"]:
                self.warnung(PERSONEN, nummer, "Angehörige Person ohne Geburtsdatum.")
            personen.append({"kundennummer": z.get("kundennummer", ""), **p})

        abholer = [
            {
                "kundennummer": z.get("kundennummer", ""),
                "vorname": self.text(ABHOLER, n, z, "vorname", pflicht=True),
                "nachname": self.text(ABHOLER, n, z, "nachname", pflicht=True),
                "geburtsdatum": self.geburtsdatum(ABHOLER, n, z),
                "eigene_kundennummer": self.text(ABHOLER, n, z, "eigene_kundennummer"),
            }
            for n, z in gelesen.get(ABHOLER, [])
        ]

        sperren = []
        for n, z in gelesen.get(SPERREN, []):
            von = self.datum(SPERREN, n, z, "von", pflicht=True)
            bis = self.datum(SPERREN, n, z, "bis")
            if von and bis and bis < von:
                self.fehler(SPERREN, n, "„bis“ liegt vor „von“.")
            sperren.append(
                {
                    "kundennummer": z.get("kundennummer", ""),
                    "von": von,
                    "bis": bis,
                    "begruendung": z.get("begruendung", ""),
                    "eingetragen_von": self.text(SPERREN, n, z, "eingetragen_von"),
                }
            )

        bemerkungen = [
            {
                "kundennummer": z.get("kundennummer", ""),
                "datum": self.datum(BEMERKUNGEN, n, z, "datum", pflicht=True),
                "text": self.text(BEMERKUNGEN, n, z, "text", pflicht=True),
                "verfasst_von": self.text(BEMERKUNGEN, n, z, "verfasst_von"),
            }
            for n, z in gelesen.get(BEMERKUNGEN, [])
        ]

        abholungen, ausnahmen = self.abholdaten(gelesen)

        if any(m["stufe"] == FEHLER for m in self.bericht):
            return None
        return {
            "kundengruppen": csv_gruppen,
            "neue_gruppen": neue_gruppen,
            "haushalte": haushalte,
            "personen": personen,
            "abholer": abholer,
            "sperren": sperren,
            "bemerkungen": bemerkungen,
            "abholungen": abholungen,
            "ausnahmen": ausnahmen,
        }


def pruefen(dateien: dict[str, bytes], heute: dt.date | None = None) -> Ergebnis:
    pruefsumme = hashlib.sha256()
    for name in sorted(dateien):
        pruefsumme.update(name.encode())
        pruefsumme.update(hashlib.sha256(dateien[name]).digest())
    pruefung = _Pruefung(dateien, heute or timezone.localdate())
    daten = pruefung.ausfuehren()
    return Ergebnis(
        bericht=pruefung.bericht,
        daten=daten,
        pruefsumme=pruefsumme.hexdigest(),
        dateien=sorted(dateien),
    )


def _datum(iso):
    return dt.date.fromisoformat(iso) if iso else None


MAX_ABGLEICH = 300  # so viele Haushalte je Gruppe zeigt die Vorschau einzeln


def _vergleichswerte_import(h: dict, anzahl_angehoerige: int) -> dict[str, str]:
    hp = h.get("hauptperson") or {}
    g = h.get("kundengruppe") or {}
    return {
        "Status": h.get("status") or "",
        "Kundengruppe": g.get("name") or "",
        "Ausweis gültig bis": h.get("ausweis_gueltig_bis") or "",
        "Einkommensart": h.get("einkommensart") or "",
        "Name": f"{hp.get('vorname', '')} {hp.get('nachname', '')}".strip(),
        "Geburtsdatum": hp.get("geburtsdatum") or "",
        "Anschrift": " ".join(x for x in (h.get("strasse"), h.get("plz"), h.get("ort")) if x),
        "Telefon": h.get("telefon") or "",
        "E-Mail": h.get("email") or "",
        "Personen": str(1 + anzahl_angehoerige),
    }


def _vergleichswerte_bestand(h: Haushalt) -> dict[str, str]:
    hp = next((p for p in h.personen.all() if p.ist_hauptperson), None)
    return {
        "Status": h.status,
        "Kundengruppe": h.kundengruppe.name if h.kundengruppe else "",
        "Ausweis gültig bis": h.ausweis_gueltig_bis.isoformat() if h.ausweis_gueltig_bis else "",
        "Einkommensart": h.einkommensart.bezeichnung if h.einkommensart else "",
        "Name": f"{hp.vorname} {hp.nachname}".strip() if hp else "",
        "Geburtsdatum": hp.geburtsdatum.isoformat() if hp and hp.geburtsdatum else "",
        "Anschrift": " ".join(x for x in (h.strasse, h.plz, h.ort) if x),
        "Telefon": h.telefon,
        "E-Mail": h.email,
        "Personen": str(len(h.personen.all())),
    }


def abgleich(daten: dict) -> dict:
    """Was der Import gegenüber dem jetzigen Kundenstamm ändert.

    neu: nur im Import; entfallen: nur im Bestand; geaendert: in beiden, mit Unterschieden je
    Angabe. „lokal“ heißt: in bintafeln geändert oder aufgenommen; dort fragt die Vorschau,
    ob der bintafeln-Stand bleiben soll.
    """
    angehoerige: dict[str, int] = {}
    for p in daten["personen"]:
        angehoerige[p["kundennummer"]] = angehoerige.get(p["kundennummer"], 0) + 1
    importiert = {h["kundennummer"]: h for h in daten["haushalte"]}
    bestand = {
        h.kundennummer: h
        for h in Haushalt.objects.select_related("kundengruppe", "einkommensart").prefetch_related(
            "personen"
        )
    }
    ergebnis = {"neu": [], "entfallen": [], "geaendert": [], "unveraendert": 0}
    for nummer, h in importiert.items():
        if nummer not in bestand:
            name = _vergleichswerte_import(h, 0)["Name"]
            ergebnis["neu"].append({"kundennummer": nummer, "name": name})
    for nummer, h in bestand.items():
        lokal = bool(h.geaendert_am or h.aufgenommen_am)
        alt = _vergleichswerte_bestand(h)
        eintrag = {"kundennummer": nummer, "name": alt["Name"], "lokal": lokal,
                   "aufgenommen": bool(h.aufgenommen_am)}  # fmt: skip
        if nummer not in importiert:
            ergebnis["entfallen"].append(eintrag)
            continue
        neu = _vergleichswerte_import(importiert[nummer], angehoerige.get(nummer, 0))
        unterschiede = [(k, alt[k], neu[k]) for k in alt if alt[k] != neu[k]]
        if unterschiede:
            ergebnis["geaendert"].append({**eintrag, "unterschiede": unterschiede})
        else:
            ergebnis["unveraendert"] += 1
    for liste in ("neu", "entfallen", "geaendert"):
        ergebnis[liste].sort(key=lambda e: (not e.get("lokal"), e["kundennummer"]))
    ergebnis["fragen"] = [e for e in ergebnis["entfallen"] + ergebnis["geaendert"] if e["lokal"]]
    return ergebnis


def _ohne(liste: list[dict], nummern: set[str]) -> list[dict]:
    return [e for e in liste if e.get("kundennummer") not in nummern]


@transaction.atomic
def uebernehmen(
    daten: dict, *, benutzer, dateien, pruefsumme, anzahl_warnungen, behalten=frozenset()
) -> ImportLauf:
    """Ersetzt den Kundenstamm durch ``daten`` (Ergebnis von ``pruefen``).

    Haushalte in ``behalten`` (Kundennummern) bleiben mit ihrem bintafeln-Stand stehen; ihre
    Zeilen aus dem Import werden ausgelassen (Import-Abgleich, ADR 0028).
    """
    behalten = set(behalten)
    if behalten:
        daten = {k: _ohne(v, behalten) if isinstance(v, list) and k not in (
            "kundengruppen", "neue_gruppen") else v for k, v in daten.items()}  # fmt: skip
    stellen: dict[str, Ausgabestelle] = {}

    def stelle(name):
        if not name:
            return None
        if name.lower() not in stellen:
            stellen[name.lower()] = Ausgabestelle.objects.filter(
                name__iexact=name
            ).first() or Ausgabestelle.objects.create(name=name)
        return stellen[name.lower()]

    vorher = historie.schnappschuesse()
    with disable_auditlog():
        Haushalt.objects.exclude(kundennummer__in=behalten).delete()

        for g in daten["kundengruppen"]:
            gruppe = (
                Kundengruppe.objects.filter(kuerzel__iexact=g["kuerzel"]).first()
                or Kundengruppe.objects.filter(name__iexact=g["name"]).first()
                or Kundengruppe()
            )
            # Platzhalter ohne Kürzel mit gleichem Namen (z. B. aus einem früheren Import ohne
            # kundengruppen.csv) weichen; Haushalte hängen zu diesem Zeitpunkt keine mehr daran.
            Kundengruppe.objects.filter(
                name__iexact=g["name"], kuerzel="", haushalte__isnull=True
            ).exclude(pk=gruppe.pk).delete()
            gruppe.kuerzel, gruppe.name = g["kuerzel"], g["name"]
            gruppe.ausgabestelle = stelle(g["ausgabestelle"])
            gruppe.wochentage = g["wochentage"]
            gruppe.uhrzeit = dt.time.fromisoformat(g["uhrzeit"]) if g["uhrzeit"] else None
            gruppe.maximum, gruppe.aktiv = g["maximum"], g["aktiv"]
            gruppe.save()
        for g in daten["neue_gruppen"]:
            if not Kundengruppe.objects.filter(name__iexact=g["name"]).exists():
                Kundengruppe.objects.create(
                    name=g["name"], ausgabestelle=stelle(g["ausgabestelle"])
                )

        # Zuordnung über das Kürzel, wenn vorhanden (übersteht Umbenennungen), sonst den Namen.
        gruppen = {}
        for g in Kundengruppe.objects.all():
            gruppen[("n", g.name.lower())] = g
            if g.kuerzel:
                gruppen[("k", g.kuerzel.lower())] = g

        def gruppe(bezug):
            if not bezug:
                return None
            if bezug["kuerzel"]:
                return gruppen.get(("k", bezug["kuerzel"].lower()))
            return gruppen.get(("n", bezug["name"].lower()))

        arten: dict[str, Einkommensart] = {}

        def art(name):
            if not name:
                return None
            if name.lower() not in arten:
                arten[name.lower()] = Einkommensart.objects.filter(
                    bezeichnung__iexact=name
                ).first() or Einkommensart.objects.create(bezeichnung=name)
            return arten[name.lower()]

        jetzt = timezone.now()
        haushalte = Haushalt.objects.bulk_create(
            Haushalt(
                kundennummer=h["kundennummer"],
                status=h["status"],
                kundengruppe=gruppe(h["kundengruppe"]),
                kunde_seit=_datum(h["kunde_seit"]),
                ausweis_gueltig_bis=_datum(h["ausweis_gueltig_bis"]),
                letzter_besuch=_datum(h["letzter_besuch"]),
                einkommensart=art(h["einkommensart"]),
                strasse=h["strasse"],
                plz=h["plz"],
                ort=h["ort"],
                telefon=h["telefon"],
                email=h["email"],
                kontostand=h["kontostand"],
                anzahl_erwachsene=h["anzahl_erwachsene"],
                anzahl_kinder=h["anzahl_kinder"],
                zusatz=h["zusatz"],
                importiert_am=jetzt,
            )
            for h in daten["haushalte"]
        )
        nach_nummer = {h.kundennummer: h for h in haushalte}

        def person(haushalt, p, hauptperson):
            return Person(
                haushalt=haushalt,
                ist_hauptperson=hauptperson,
                anrede=p["anrede"],
                vorname=p["vorname"],
                nachname=p["nachname"],
                geburtsdatum=_datum(p["geburtsdatum"]),
                staatsangehoerigkeit=p["staatsangehoerigkeit"],
                familienstand=p["familienstand"],
                zusatz=p["zusatz"],
            )

        Person.objects.bulk_create(
            [
                person(nach_nummer[h["kundennummer"]], h["hauptperson"], True)
                for h in daten["haushalte"]
            ]
            + [person(nach_nummer[p["kundennummer"]], p, False) for p in daten["personen"]]
        )
        Abholer.objects.bulk_create(
            Abholer(
                haushalt=nach_nummer[a["kundennummer"]],
                vorname=a["vorname"],
                nachname=a["nachname"],
                geburtsdatum=_datum(a["geburtsdatum"]),
                eigene_kundennummer=a["eigene_kundennummer"],
            )
            for a in daten["abholer"]
        )
        Sperre.objects.bulk_create(
            Sperre(
                haushalt=nach_nummer[s["kundennummer"]],
                von=_datum(s["von"]),
                bis=_datum(s["bis"]),
                begruendung=s["begruendung"],
                eingetragen_von=s["eingetragen_von"],
            )
            for s in daten["sperren"]
        )
        Bemerkung.objects.bulk_create(
            Bemerkung(
                haushalt=nach_nummer[b["kundennummer"]],
                datum=_datum(b["datum"]),
                text=b["text"],
                verfasst_von=b["verfasst_von"],
            )
            for b in daten["bemerkungen"]
        )
        Abholung.objects.bulk_create(
            Abholung(
                haushalt=nach_nummer[a["kundennummer"]],
                datum=_datum(a["datum"]),
                uhrzeit=dt.time.fromisoformat(a["uhrzeit"]) if a["uhrzeit"] else None,
                beitrag=a["beitrag"],
                ausgabestelle=stelle(a["ausgabestelle"]),
                eingetragen_von=a["eingetragen_von"],
            )
            for a in daten.get("abholungen", [])
        )
        Ausnahme.objects.bulk_create(
            Ausnahme(
                haushalt=nach_nummer[a["kundennummer"]],
                datum=_datum(a["datum"]),
                begruendung=a["begruendung"],
                eingetragen_von=a["eingetragen_von"],
            )
            for a in daten.get("ausnahmen", [])
        )

    verwaiste_notizen_loeschen()  # Notizen bleiben, solange es die Kundennummer noch gibt
    historie.import_festhalten(
        vorher, historie.schnappschuesse(), benutzer.get_username() if benutzer else ""
    )
    # Außerhalb von disable_auditlog: Der Import selbst erscheint im Änderungsprotokoll.
    return ImportLauf.objects.create(
        benutzer=benutzer,
        dateien=dateien,
        pruefsumme=pruefsumme,
        anzahl_haushalte=len(daten["haushalte"]),
        anzahl_personen=len(daten["haushalte"]) + len(daten["personen"]),
        anzahl_abholer=len(daten["abholer"]),
        anzahl_sperren=len(daten["sperren"]),
        anzahl_bemerkungen=len(daten["bemerkungen"]),
        anzahl_abholungen=len(daten.get("abholungen", [])),
        anzahl_ausnahmen=len(daten.get("ausnahmen", [])),
        anzahl_warnungen=anzahl_warnungen,
    )
