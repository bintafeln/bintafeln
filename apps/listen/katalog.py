"""Katalog der fertigen Listen (ADR 0063).

Eine Liste legt fest: Grundlage (Haushalte oder Personen), welche Filter sie anbietet, deren
Vorgaben, die Spalten, Sortierung und Gruppierung beim ersten Öffnen und welches Recht sie
zusätzlich braucht (z. B. Stammdaten für Staatsangehörigkeit). Alles lässt sich auf der Seite
ändern; eigene Einstellungen speichert man als „eigene Liste“.
"""

import datetime as dt
from dataclasses import dataclass, field

from apps.listen.spalten import STAMMDATEN


@dataclass(frozen=True)
class Liste:
    kennung: str
    bereich: str
    titel: str
    beschreibung: str
    basis: str = "haushalt"  # oder "person"
    filter: tuple[str, ...] = ("stelle", "gruppe", "status")
    vorgaben: dict = field(default_factory=dict)  # Filterwerte beim ersten Öffnen
    spalten: tuple[str, ...] = ("kundennummer", "nachname", "vorname", "kundengruppe",
                                "personen")  # fmt: skip
    sort: str = "nachname"
    gruppe: str = ""
    summen: bool = False  # nur Gruppen mit Anzahl und Summen
    recht: str | None = None


def _monatsanfang(heute):
    return heute.replace(day=1)


def _vormonat(heute):
    ende = heute.replace(day=1) - dt.timedelta(days=1)
    return ende.replace(day=1), ende


KUNDEN, PERSONEN, ZAHLEN = "Kunden", "Personen", "Zählungen"
H_SPALTEN = ("kundennummer", "nachname", "vorname", "kundengruppe", "personen", "ausweis")

LISTEN = [
    Liste("kunden_stelle", KUNDEN, "Kundenliste einer Ausgabestelle",
          "Alle aktiven Haushalte einer Ausgabestelle, nach Kundengruppe gegliedert.",
          spalten=H_SPALTEN, gruppe="kundengruppe", vorgaben={"status": "aktiv"}),
    Liste("alle_kunden", KUNDEN, "Alle Kunden", "Alle Haushalte mit Status und Ausgabestelle.",
          spalten=("kundennummer", "nachname", "vorname", "ausgabestelle", "kundengruppe",
                   "status", "personen"), sort="kundennummer"),
    Liste("einkommensart", KUNDEN, "Kunden nach Einkommensart",
          "Haushalte gegliedert nach Einkommensart (z. B. Bürgergeld, Rente, Wohngeld).",
          filter=("stelle", "gruppe", "status", "einkommensart"), recht=STAMMDATEN,
          spalten=("kundennummer", "nachname", "vorname", "einkommensart", "personen"),
          gruppe="einkommensart", vorgaben={"status": "aktiv"}),
    Liste("buergergeld", KUNDEN, "Bürgergeld", "Haushalte mit der Einkommensart Bürgergeld.",
          filter=("stelle", "gruppe", "status", "einkommensart"), recht=STAMMDATEN,
          spalten=H_SPALTEN, vorgaben={"status": "aktiv", "einkommensart": "bürgergeld"}),
    Liste("rente", KUNDEN, "Rentnerinnen und Rentner",
          "Haushalte mit der Einkommensart Rente (siehe auch „Seniorinnen und Senioren“).",
          filter=("stelle", "gruppe", "status", "einkommensart"), recht=STAMMDATEN,
          spalten=H_SPALTEN, vorgaben={"status": "aktiv", "einkommensart": "rente"}),
    Liste("ausweis_ablauf", KUNDEN, "Ausweis läuft ab",
          "Haushalte, deren Ausweis bis zum gewählten Tag abläuft oder schon abgelaufen ist.",
          filter=("stelle", "gruppe", "status", "ausweis_bis"),
          vorgaben={"status": "aktiv", "ausweis_bis": lambda h: h + dt.timedelta(days=30)},
          spalten=("kundennummer", "nachname", "vorname", "kundengruppe", "ausweis",
                   "letzter_besuch"), sort="ausweis"),
    Liste("lange_nicht", KUNDEN, "Lange nicht gekommen",
          "Haushalte, die seit dem gewählten Tag nicht abgeholt haben (oder noch nie).",
          filter=("stelle", "gruppe", "status", "besuch_vor"),
          vorgaben={"status": "aktiv", "besuch_vor": lambda h: h - dt.timedelta(days=56)},
          spalten=("kundennummer", "nachname", "vorname", "kundengruppe", "letzter_besuch"),
          sort="letzter_besuch"),
    Liste("neue_kunden", KUNDEN, "Neue Kunden", "Haushalte, die seit dem gewählten Tag Kunde sind.",
          filter=("stelle", "gruppe", "status", "seit_ab"), recht=STAMMDATEN,
          vorgaben={"seit_ab": _monatsanfang},
          spalten=("kundennummer", "nachname", "vorname", "kundengruppe", "kunde_seit",
                   "personen"), sort="kunde_seit"),
    Liste("grosse_haushalte", KUNDEN, "Große Haushalte",
          "Haushalte ab einer gewählten Zahl von Personen.",
          filter=("stelle", "gruppe", "status", "personen_ab"),
          vorgaben={"status": "aktiv", "personen_ab": 5},
          spalten=("kundennummer", "nachname", "vorname", "kundengruppe", "personen",
                   "erwachsene", "kinder"), sort="-personen"),
    Liste("familien_kleinkinder", KUNDEN, "Haushalte mit Kindern unter 6",
          "Haushalte, in denen mindestens ein Kind unter 6 Jahren lebt (z. B. für Babynahrung).",
          filter=("stelle", "gruppe", "status", "kinder_unter_6"),
          vorgaben={"status": "aktiv", "kinder_unter_6": "1"},
          spalten=("kundennummer", "nachname", "vorname", "kundengruppe", "unter_6", "kinder")),
    Liste("ohne_gruppe", KUNDEN, "Kunden ohne Kundengruppe",
          "Haushalte ohne Kundengruppe, z. B. nach abgelaufenem Ausweis oder Pause.",
          filter=("stelle", "status", "ohne_gruppe"), vorgaben={"ohne_gruppe": "1"},
          spalten=("kundennummer", "nachname", "vorname", "status", "ausweis",
                   "letzter_besuch")),
    Liste("nicht_aktiv", KUNDEN, "Pausiert, gesperrt oder beendet",
          "Haushalte, die nicht aktiv sind, nach Status gegliedert.",
          filter=("stelle", "gruppe", "status"), vorgaben={"status": "nicht_aktiv"},
          spalten=("kundennummer", "nachname", "vorname", "status", "ausweis"),
          gruppe="status"),
    Liste("abholungen", KUNDEN, "Abholungen im Zeitraum",
          "Wie oft jeder Haushalt im Zeitraum abgeholt hat (Vorgabe: Vormonat).",
          filter=("stelle", "gruppe", "status", "zeitraum"),
          vorgaben={"von": lambda h: _vormonat(h)[0], "bis": lambda h: _vormonat(h)[1]},
          spalten=("kundennummer", "nachname", "vorname", "kundengruppe", "abholungen",
                   "letzter_besuch"), sort="-abholungen"),
    Liste("negativer_kontostand", KUNDEN, "Offene Beträge (Kontostand im Minus)",
          "Haushalte, deren Kundenkonto im Minus ist (angeschrieben).", recht="kunden.konto",
          filter=("stelle", "gruppe", "status", "kontostand_minus"),
          vorgaben={"kontostand_minus": "1"},
          spalten=("kundennummer", "nachname", "vorname", "kundengruppe", "kontostand",
                   "letzter_besuch"), sort="kontostand"),
    Liste("anschriften", KUNDEN, "Anschriftenliste",
          "Haushalte mit Anschrift und Telefon, z. B. für Rückfragen.",
          filter=("stelle", "gruppe", "status"), recht="kunden.kontakt",
          vorgaben={"status": "aktiv"},
          spalten=("kundennummer", "nachname", "vorname", "strasse", "plz", "ort", "telefon")),
    # --- Personen ---
    Liste("nationalitaet", PERSONEN, "Personen nach Staatsangehörigkeit",
          "Alle Personen der Haushalte, gegliedert nach Staatsangehörigkeit.",
          basis="person", recht=STAMMDATEN,
          filter=("stelle", "gruppe", "status", "staatsangehoerigkeit", "alter"),
          vorgaben={"status": "aktiv"},
          spalten=("kundennummer", "nachname", "vorname", "alter", "staatsangehoerigkeit"),
          gruppe="staatsangehoerigkeit"),
    Liste("kinder_unter_6", PERSONEN, "Kinder unter 6 Jahren",
          "Alle Kinder bis 5 Jahre mit Geburtsdatum.", basis="person",
          filter=("stelle", "gruppe", "status", "alter"),
          vorgaben={"status": "aktiv", "alter_von": 0, "alter_bis": 5},
          spalten=("kundennummer", "nachname", "vorname", "geburtsdatum", "alter",
                   "kundengruppe"), sort="geburtsdatum"),
    Liste("kinder", PERSONEN, "Kinder und Jugendliche (Alter von–bis)",
          "Kinder und Jugendliche in einem frei wählbaren Alter (Vorgabe 0–17).", basis="person",
          filter=("stelle", "gruppe", "status", "alter"),
          vorgaben={"status": "aktiv", "alter_von": 0, "alter_bis": 17},
          spalten=("kundennummer", "nachname", "vorname", "geburtsdatum", "alter"),
          sort="alter", gruppe="altersgruppe"),
    Liste("schulanfaenger", PERSONEN, "Schulanfängerinnen und Schulanfänger",
          "Kinder von 5 bis 6 Jahren, z. B. für Schultüten oder Schulranzen.", basis="person",
          filter=("stelle", "gruppe", "status", "alter"),
          vorgaben={"status": "aktiv", "alter_von": 5, "alter_bis": 6},
          spalten=("kundennummer", "nachname", "vorname", "geburtsdatum", "alter",
                   "kundengruppe"), sort="geburtsdatum"),
    Liste("senioren", PERSONEN, "Seniorinnen und Senioren",
          "Personen ab 67 Jahren (Alter wählbar).", basis="person",
          filter=("stelle", "gruppe", "status", "alter"),
          vorgaben={"status": "aktiv", "alter_von": 67},
          spalten=("kundennummer", "nachname", "vorname", "geburtsdatum", "alter",
                   "kundengruppe"), sort="-alter"),
    Liste("altersgruppen", PERSONEN, "Personen nach Altersgruppen",
          "Alle Personen, gegliedert nach Altersgruppen (0–2, 3–5, 6–13 … ab 67).",
          basis="person", filter=("stelle", "gruppe", "status", "alter"),
          vorgaben={"status": "aktiv"},
          spalten=("kundennummer", "nachname", "vorname", "alter", "rolle"),
          sort="alter", gruppe="altersgruppe"),
    Liste("alle_personen", PERSONEN, "Alle Personen",
          "Alle Personen der Haushalte mit Geburtsdatum und Alter.", basis="person",
          filter=("stelle", "gruppe", "status", "alter"), vorgaben={"status": "aktiv"},
          spalten=("kundennummer", "nachname", "vorname", "rolle", "geburtsdatum", "alter"),
          sort="kundennummer"),
    # --- Zählungen ---
    Liste("zahl_nationalitaet", ZAHLEN, "Anzahl je Staatsangehörigkeit",
          "Wie viele Personen welche Staatsangehörigkeit haben.", basis="person",
          recht=STAMMDATEN, filter=("stelle", "gruppe", "status"), vorgaben={"status": "aktiv"},
          spalten=("anzahl",), gruppe="staatsangehoerigkeit", summen=True),
    Liste("zahl_alter", ZAHLEN, "Anzahl je Altersgruppe",
          "Wie viele Personen in welcher Altersgruppe sind.", basis="person",
          filter=("stelle", "gruppe", "status"), vorgaben={"status": "aktiv"},
          spalten=("anzahl",), gruppe="altersgruppe", sort="alter", summen=True),
    Liste("zahl_stellen", ZAHLEN, "Haushalte und Personen je Ausgabestelle",
          "Haushalte, Personen, Erwachsene und Kinder je Ausgabestelle.",
          filter=("stelle", "status"), vorgaben={"status": "aktiv"},
          spalten=("personen", "erwachsene", "kinder", "unter_6", "ab_67"),
          gruppe="ausgabestelle", summen=True),
    Liste("zahl_gruppen", ZAHLEN, "Haushalte und Personen je Kundengruppe",
          "Wie voll die Kundengruppen sind.", filter=("stelle", "status"),
          vorgaben={"status": "aktiv"}, spalten=("personen", "erwachsene", "kinder"),
          gruppe="kundengruppe", summen=True),
    Liste("zahl_groesse", ZAHLEN, "Haushalte nach Größe",
          "Wie viele Haushalte 1, 2, 3 … Personen haben.", filter=("stelle", "gruppe", "status"),
          vorgaben={"status": "aktiv"}, spalten=("personen",), gruppe="groesse", sort="personen",
          summen=True),
    Liste("zahl_neue", ZAHLEN, "Neue Kunden je Monat",
          "Wie viele Haushalte in welchem Monat Kunde geworden sind.", recht=STAMMDATEN,
          filter=("stelle", "gruppe", "status", "seit_ab"),
          vorgaben={"seit_ab": lambda h: h.replace(year=h.year - 1, day=1)},
          spalten=("personen",), gruppe="seit_monat", sort="kunde_seit", summen=True),
    Liste("zahl_einkommen", ZAHLEN, "Haushalte je Einkommensart",
          "Wie viele Haushalte von welcher Einkommensart leben.", recht=STAMMDATEN,
          filter=("stelle", "gruppe", "status"), vorgaben={"status": "aktiv"},
          spalten=("personen",), gruppe="einkommensart", summen=True),
]  # fmt: skip

NACH_KENNUNG = {liste.kennung: liste for liste in LISTEN}
BEREICHE = [KUNDEN, PERSONEN, ZAHLEN]


def vorgaben(liste: Liste, heute: dt.date) -> dict:
    """Filtervorgaben mit ausgerechneten Daten (Funktionen bekommen „heute“)."""
    werte = {}
    for name, wert in liste.vorgaben.items():
        wert = wert(heute) if callable(wert) else wert
        werte[name] = wert.isoformat() if isinstance(wert, dt.date) else str(wert)
    return werte
