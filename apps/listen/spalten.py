"""Spalten der Listen (ADR 0063): je Grundlage (Haushalt oder Person) Schlüssel, Titel, nötiges
Recht und eine Funktion, die den Wert liefert. Werte bleiben roh (Zahl, Datum, Text), damit sie
sich richtig sortieren und summieren lassen; ``text()`` macht daraus die Anzeige."""

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal

from apps.kunden.models import Zusatzfeld

STAMMDATEN = "kunden.stammdaten"
KONTAKT = "kunden.kontakt"
KONTO = "kunden.konto"

# Altersgruppen für Zählungen und Gruppierung: (bis einschließlich, Titel)
ALTERSGRUPPEN = [(2, "0–2"), (5, "3–5"), (13, "6–13"), (17, "14–17"), (24, "18–24"),
                 (49, "25–49"), (66, "50–66"), (200, "ab 67")]  # fmt: skip


def altersgruppe(alter: int | None) -> str:
    if alter is None:
        return "unbekannt"
    return next(titel for bis, titel in ALTERSGRUPPEN if alter <= bis)


@dataclass(frozen=True)
class Spalte:
    schluessel: str
    titel: str
    wert: object  # wert(objekt, kontext) -> roher Wert
    recht: str | None = None
    zahl: bool = False  # wird bei Gruppen summiert


def _hp(h):
    """Hauptperson aus den vorab geladenen Personen (ohne weitere Abfrage)."""
    personen = list(h.personen.all())
    return next((p for p in personen if p.ist_hauptperson), personen[0] if personen else None)


def _gruppe(h):
    return h.kundengruppe


def _stelle(h):
    g = h.kundengruppe
    return g.ausgabestelle.name if g and g.ausgabestelle else ""


def _alter_liste(h, k):
    return [p.alter(k["heute"]) for p in h.personen.all()]


def _kinder_unter(h, k, grenze):
    return sum(1 for a in _alter_liste(h, k) if a is not None and a < grenze)


HAUSHALT = [
    Spalte("kundennummer", "Kundennummer", lambda h, k: h.kundennummer),
    Spalte("anrede", "Anrede", lambda h, k: (_hp(h).anrede if _hp(h) else "")),
    Spalte("vorname", "Vorname", lambda h, k: (_hp(h).vorname if _hp(h) else "")),
    Spalte("nachname", "Nachname", lambda h, k: (_hp(h).nachname if _hp(h) else "")),
    Spalte("geburtsdatum", "Geburtsdatum", lambda h, k: (_hp(h).geburtsdatum if _hp(h) else None)),
    Spalte("kundengruppe", "Kundengruppe", lambda h, k: _gruppe(h).name if _gruppe(h) else ""),
    Spalte("ausgabestelle", "Ausgabestelle", lambda h, k: _stelle(h)),
    Spalte("wochentage", "Ausgabetage", lambda h, k: _gruppe(h).wochentage if _gruppe(h) else ""),
    Spalte("uhrzeit", "Uhrzeit", lambda h, k: _gruppe(h).uhrzeit if _gruppe(h) else None),
    Spalte("status", "Status", lambda h, k: h.get_status_display()),
    Spalte("personen", "Personen", lambda h, k: sum(h.groesse(k["kind_bis"], k["heute"])),
           zahl=True),
    Spalte("erwachsene", "Erwachsene", lambda h, k: h.groesse(k["kind_bis"], k["heute"])[0],
           zahl=True),
    Spalte("kinder", "Kinder", lambda h, k: h.groesse(k["kind_bis"], k["heute"])[1], zahl=True),
    Spalte("unter_6", "Kinder unter 6", lambda h, k: _kinder_unter(h, k, 6), zahl=True),
    Spalte("ab_67", "Personen ab 67",
           lambda h, k: sum(1 for a in _alter_liste(h, k) if a is not None and a >= 67), zahl=True),
    Spalte("ausweis", "Ausweis gültig bis", lambda h, k: h.ausweis_gueltig_bis),
    Spalte("letzter_besuch", "Letzter Besuch", lambda h, k: h.letzter_besuch),
    Spalte("abholungen", "Abholungen im Zeitraum", lambda h, k: k["abholungen"].get(h.pk, 0),
           zahl=True),
    Spalte("kunde_seit", "Kunde seit", lambda h, k: h.kunde_seit, STAMMDATEN),
    Spalte("einkommensart", "Einkommensart",
           lambda h, k: h.einkommensart.bezeichnung if h.einkommensart else "", STAMMDATEN),
    Spalte("staatsangehoerigkeit", "Staatsangehörigkeit (Hauptperson)",
           lambda h, k: (_hp(h).staatsangehoerigkeit if _hp(h) else ""), STAMMDATEN),
    Spalte("kontostand", "Kontostand", lambda h, k: h.kontostand, KONTO, zahl=True),
    Spalte("strasse", "Straße", lambda h, k: h.strasse, KONTAKT),
    Spalte("plz", "PLZ", lambda h, k: h.plz, KONTAKT),
    Spalte("ort", "Ort", lambda h, k: h.ort, KONTAKT),
    Spalte("telefon", "Telefon", lambda h, k: h.telefon, KONTAKT),
    Spalte("email", "E-Mail", lambda h, k: h.email, KONTAKT),
]  # fmt: skip

PERSON = [
    Spalte("kundennummer", "Kundennummer", lambda p, k: p.haushalt.kundennummer),
    Spalte("anrede", "Anrede", lambda p, k: p.anrede),
    Spalte("vorname", "Vorname", lambda p, k: p.vorname),
    Spalte("nachname", "Nachname", lambda p, k: p.nachname),
    Spalte("rolle", "Im Haushalt",
           lambda p, k: "Hauptperson" if p.ist_hauptperson else "Angehörige"),
    Spalte("geburtsdatum", "Geburtsdatum", lambda p, k: p.geburtsdatum),
    Spalte("alter", "Alter", lambda p, k: p.alter(k["heute"])),
    Spalte("altersgruppe", "Altersgruppe", lambda p, k: altersgruppe(p.alter(k["heute"]))),
    Spalte("kundengruppe", "Kundengruppe", lambda p, k: _gruppe(p.haushalt).name
           if _gruppe(p.haushalt) else ""),
    Spalte("ausgabestelle", "Ausgabestelle", lambda p, k: _stelle(p.haushalt)),
    Spalte("status", "Status", lambda p, k: p.haushalt.get_status_display()),
    Spalte("anzahl", "Anzahl", lambda p, k: 1, zahl=True),
    Spalte("staatsangehoerigkeit", "Staatsangehörigkeit", lambda p, k: p.staatsangehoerigkeit,
           STAMMDATEN),
    Spalte("familienstand", "Familienstand", lambda p, k: p.familienstand, STAMMDATEN),
    Spalte("einkommensart", "Einkommensart (Haushalt)",
           lambda p, k: p.haushalt.einkommensart.bezeichnung if p.haushalt.einkommensart else "",
           STAMMDATEN),
    Spalte("plz", "PLZ", lambda p, k: p.haushalt.plz, KONTAKT),
    Spalte("ort", "Ort", lambda p, k: p.haushalt.ort, KONTAKT),
]  # fmt: skip


def zusatzspalten(gilt_fuer: str) -> list[Spalte]:
    """Aktive Zusatzfelder als Spalten; Art.-9-Felder nur mit dem Recht dazu."""
    spalten = []
    for z in Zusatzfeld.objects.filter(aktiv=True, gilt_fuer=gilt_fuer):
        recht = "kunden.besondere_kategorie" if z.besondere_kategorie else None
        spalten.append(Spalte(f"zusatz:{z.schluessel}", z.bezeichnung,
                              lambda o, k, z=z: z.wert_anzeigen((o.zusatz or {}).get(z.schluessel)),
                              recht))  # fmt: skip
    return spalten


def alle(basis: str) -> list[Spalte]:
    if basis == "person":
        return PERSON + zusatzspalten(Zusatzfeld.GiltFuer.PERSON)
    return HAUSHALT + zusatzspalten(Zusatzfeld.GiltFuer.HAUSHALT)


def erlaubte(basis: str, darf) -> list[Spalte]:
    return [s for s in alle(basis) if not s.recht or s.recht in darf]


def text(wert) -> str:
    """Anzeige und Export: Datum deutsch, Beträge mit Komma, leer statt None."""
    if wert is None:
        return ""
    if isinstance(wert, dt.datetime):
        return f"{wert:%d.%m.%Y %H:%M}"
    if isinstance(wert, dt.date):
        return f"{wert:%d.%m.%Y}"
    if isinstance(wert, dt.time):
        return f"{wert:%H:%M}"
    if isinstance(wert, Decimal):
        return f"{wert:.2f}".replace(".", ",")
    return str(wert)


def sortschluessel(wert):
    """Leere Werte immer hinten, Texte ohne Groß/Klein, sonst der Wert selbst."""
    if wert is None or wert == "":
        return (1, "")
    if isinstance(wert, str):
        return (0, wert.casefold())
    return (0, wert)
