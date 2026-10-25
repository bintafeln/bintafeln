"""Kundenliste als CSV-Datei (ADR 0058): Spalten aus den Einstellungen, nur mit Rechten gefüllt.

Exportiert wird genau die gefilterte Liste der eigenen Ausgabestellen (``zugang.filtern``). Jeder
exportierte Haushalt erhält einen Eintrag im Zugriffsprotokoll (``Zugriff.export``).
"""

import csv
import datetime as dt
import io

from apps.ausgabe.ampel import WOCHENTAGE
from apps.kunden.models import Haushalt, KundenEinstellungen, Kundengruppe, Zusatzfeld

# (Schlüssel, Spaltenname, nötiges Recht)
FELDER = [
    ("kundennummer", "Kundennummer", None),
    ("vorname", "Vorname", None),
    ("nachname", "Nachname", None),
    ("kundengruppe", "Kundengruppe", None),
    ("ausgabestelle", "Ausgabestelle", None),
    ("wochentage", "Ausgabetage", None),
    ("uhrzeit", "Uhrzeit", None),
    ("status", "Status", None),
    ("personen", "Personen", None),
    ("erwachsene", "Erwachsene", None),
    ("kinder", "Kinder", None),
    ("ausweis", "Ausweis gültig bis", None),
    ("letzter_besuch", "Letzter Besuch", None),
    ("kontostand", "Kontostand", "kunden.konto"),
    ("strasse", "Straße", "kunden.kontakt"),
    ("plz", "PLZ", "kunden.kontakt"),
    ("ort", "Ort", "kunden.kontakt"),
    ("telefon", "Telefon", "kunden.kontakt"),
    ("email", "E-Mail", "kunden.kontakt"),
]
VORGABE = ["kundennummer", "vorname", "nachname", "kundengruppe", "wochentage", "uhrzeit",
           "personen"]  # fmt: skip


def auswahl() -> list[tuple[str, str]]:
    """Alle wählbaren Spalten: feste Felder und die Zusatzfelder der Haushalte."""
    zusatz = [
        (f"zusatz:{z.schluessel}", f"Zusatzfeld: {z.bezeichnung}")
        for z in Zusatzfeld.objects.filter(aktiv=True, gilt_fuer=Zusatzfeld.GiltFuer.HAUSHALT)
    ]
    return [(k, n) for k, n, _ in FELDER] + zusatz  # fmt: skip


def spalten() -> list[str]:
    gewaehlt = KundenEinstellungen.laden().export_felder or VORGABE
    bekannt = dict(auswahl())
    return [k for k in gewaehlt if k in bekannt]


# --- Ausgabetag ---------------------------------------------------------------------------------


def tage_von(text: str) -> list[str]:
    kuerzel = {t.strip() for t in (text or "").split(",")}
    return [t for t in WOCHENTAGE if t in kuerzel]


def verfuegbare_tage(gruppen) -> list[str]:
    """Tage, an denen eine der Kundengruppen Ausgabe hat (in Wochenreihenfolge)."""
    belegt = {t for g in gruppen for t in tage_von(g.wochentage)}
    return [t for t in WOCHENTAGE if t in belegt]


def standard_tag(benutzer, heute: dt.date, verfuegbar: list[str]) -> str:
    """Eigener Ausgabetag: heute, wenn es einer ist, sonst der erste; ohne Angabe heute; sonst
    „alle“ (leer)."""
    heute_k = WOCHENTAGE[heute.weekday()]
    eigene = [t for t in tage_von(getattr(benutzer, "ausgabetage", "")) if t in verfuegbar]
    if eigene:
        return heute_k if heute_k in eigene else eigene[0]
    return heute_k if heute_k in verfuegbar else ""


def nach_tag(haushalte, tag: str):
    if tag not in WOCHENTAGE:
        return haushalte
    ids = [g.pk for g in Kundengruppe.objects.all() if tag in tage_von(g.wochentage)]
    return haushalte.filter(kundengruppe__in=ids)


# --- CSV ----------------------------------------------------------------------------------------


def _zahl(betrag) -> str:
    return f"{betrag:.2f}".replace(".", ",") if betrag is not None else ""


def _datum(d) -> str:
    return f"{d:%d.%m.%Y}" if d else ""


def zeile(h: Haushalt, keys, darf, zusatzfelder, kind_bis, heute) -> list[str]:
    hp = h.hauptperson
    g = h.kundengruppe
    erwachsene, kinder = h.groesse(kind_bis, heute)
    werte = {
        "kundennummer": h.kundennummer, "vorname": hp.vorname if hp else "",
        "nachname": hp.nachname if hp else "", "kundengruppe": g.name if g else "",
        "ausgabestelle": g.ausgabestelle.name if g and g.ausgabestelle else "",
        "wochentage": g.wochentage if g else "",
        "uhrzeit": f"{g.uhrzeit:%H:%M}" if g and g.uhrzeit else "",
        "status": h.get_status_display(), "personen": erwachsene + kinder,
        "erwachsene": erwachsene, "kinder": kinder, "ausweis": _datum(h.ausweis_gueltig_bis),
        "letzter_besuch": _datum(h.letzter_besuch), "kontostand": _zahl(h.kontostand),
        "strasse": h.strasse, "plz": h.plz, "ort": h.ort, "telefon": h.telefon, "email": h.email,
    }  # fmt: skip
    rechte = {k: r for k, _, r in FELDER}
    ergebnis = []
    for k in keys:
        if k.startswith("zusatz:"):
            feld = zusatzfelder.get(k[7:])
            erlaubt = feld and (
                not feld.besondere_kategorie or "kunden.besondere_kategorie" in darf
            )
            ergebnis.append(feld.wert_anzeigen((h.zusatz or {}).get(feld.schluessel))
                            if erlaubt else "")  # fmt: skip
        elif rechte.get(k) and rechte[k] not in darf:
            ergebnis.append("")
        else:
            ergebnis.append(str(werte.get(k, "")))
    return ergebnis


def csv_text(haushalte, darf, heute: dt.date) -> str:
    """CSV mit Semikolon und BOM, damit Excel Umlaute richtig zeigt."""
    keys = spalten()
    namen = dict(auswahl())
    zusatzfelder = {z.schluessel: z for z in Zusatzfeld.objects.all()}
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";", lineterminator="\r\n")
    schreiber.writerow([namen[k] for k in keys])
    for h in haushalte:
        schreiber.writerow(zeile(h, keys, darf, zusatzfelder, kind_bis, heute))
    return "﻿" + puffer.getvalue()
