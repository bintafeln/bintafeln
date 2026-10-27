"""Kundenstamm ergänzen und aktualisieren statt ersetzen (ADR 0078).

Neben dem Vollaustausch (``importieren.uebernehmen``) kann ein geprüfter Import (Daten aus
``importieren.pruefen``) auch nur neue Haushalte hinzufügen oder vorhandene aktualisieren. Der
Abgleich vergleicht je Haushalt Feld für Feld; was übernommen wird, entscheidet man je Feld
(``apps.datenimport.abgleich``). Verglichen wird nur, was die Datei liefert: fehlt eine Spalte
oder ist die Zelle leer, bleibt der Wert in bintafeln. Nicht mehr gelieferte Haushalte bleiben,
außer man wählt sie einzeln zum Löschen (Papierkorb).
"""

import datetime as dt
from decimal import Decimal

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.datenimport import abgleich
from apps.datenimport.abgleich import Bestandseintrag, Treffer
from apps.datenimport.zuordnung import normalisieren
from apps.kunden import historie
from apps.kunden.importieren import (
    ABHOLER,
    HAUSHALTE,
    PERSONEN,
    SPERREN,
    _abholer,
    _abholung,
    _anlegen,
    _ausnahme,
    _bemerkung,
    _Bezuege,
    _buchung,
    _datum,
    _nach_import,
    _person,
    _sperre,
)
from apps.kunden.models import Haushalt, ImportLauf, Zusatzfeld

AKTIONEN = [("behalten", "behalten"), ("loeschen", "löschen (Papierkorb)")]
MODI = {k: abgleich.MODI[k] for k in (abgleich.NUR_NEUE, abgleich.AKTUALISIEREN)}
HAUSHALT_FELDER = [
    ("status", "Status"),
    ("kundengruppe", "Kundengruppe"),
    ("kunde_seit", "Kunde seit"),
    ("ausweis_gueltig_bis", "Ausweis gültig bis"),
    ("letzter_besuch", "Letzter Besuch"),
    ("einkommensart", "Einkommensart"),
    ("strasse", "Straße"),
    ("plz", "PLZ"),
    ("ort", "Ort"),
    ("telefon", "Telefon"),
    ("email", "E-Mail"),
    ("kontostand", "Kontostand"),
    ("anzahl_erwachsene", "Anzahl Erwachsene"),
    ("anzahl_kinder", "Anzahl Kinder"),
]
PERSON_FELDER = [
    ("anrede", "Anrede"),
    ("vorname", "Vorname"),
    ("nachname", "Nachname"),
    ("geburtsdatum", "Geburtsdatum"),
    ("staatsangehoerigkeit", "Staatsangehörigkeit"),
    ("familienstand", "Familienstand"),
]
LISTEN = [
    ("angehoerige", "Angehörige", PERSONEN),
    ("abholer", "Abholberechtigte", ABHOLER),
    ("sperren", "Sperren", SPERREN),
]
DATUM = {"kunde_seit", "ausweis_gueltig_bis", "letzter_besuch", "hp_geburtsdatum"}


def _d(wert) -> str:
    if not wert:
        return ""
    if isinstance(wert, str):
        wert = dt.date.fromisoformat(wert)
    return wert.strftime("%d.%m.%Y")


def _euro(wert) -> str:
    return "" if wert in (None, "") else f"{Decimal(wert):.2f}".replace(".", ",")


def _z(wert) -> str:
    if wert is None or wert == "":
        return ""
    if isinstance(wert, bool):
        return "ja" if wert else "nein"
    return str(wert)


def _person_text(vor, nach, geb) -> str:
    return f"{vor} {nach}".strip() + (f" ({_d(geb)})" if geb else "")


def _sperre_text(von, bis, grund) -> str:
    return f"{_d(von)} – {_d(bis) or 'unbefristet'}" + (f": {grund}" if grund else "")


def felder(spalten: dict) -> list[tuple[str, str]]:
    """Felder, die verglichen werden: nur solche, deren Spalte bzw. Datei geliefert wurde."""
    kopf = set(spalten.get(HAUSHALTE, []))
    ergebnis = [(k, b) for k, b in HAUSHALT_FELDER if k in kopf]
    ergebnis += [(f"hp_{k}", b) for k, b in PERSON_FELDER if k in kopf]
    for z in Zusatzfeld.objects.filter(aktiv=True):
        if f"zusatz_{z.schluessel}" in kopf:
            if z.gilt_fuer == Zusatzfeld.GiltFuer.HAUSHALT:
                ergebnis.append((f"z_{z.schluessel}", z.bezeichnung))
            else:
                ergebnis.append((f"pz_{z.schluessel}", f"{z.bezeichnung} (Hauptperson)"))
    ergebnis += [(k, b) for k, b, datei in LISTEN if datei in spalten]
    return ergebnis


def _nach_nummer(liste):
    ergebnis: dict[str, list] = {}
    for e in liste:
        ergebnis.setdefault(e["kundennummer"], []).append(e)
    return ergebnis


def _flach_import(h, personen, abholer, sperren, gruppen) -> dict[str, str]:
    hp = h["hauptperson"]
    g = h.get("kundengruppe") or {}
    werte = {
        "kundennummer": h["kundennummer"],
        "status": h["status"],
        "kundengruppe": gruppen.get(
            ((g.get("kuerzel") or "").lower(), g.get("name", "").lower()), g.get("name", "")
        ),
        "kunde_seit": _d(h["kunde_seit"]),
        "ausweis_gueltig_bis": _d(h["ausweis_gueltig_bis"]),
        "letzter_besuch": _d(h["letzter_besuch"]),
        "einkommensart": h["einkommensart"],
        "strasse": h["strasse"],
        "plz": h["plz"],
        "ort": h["ort"],
        "telefon": h["telefon"],
        "email": h["email"],
        "kontostand": _euro(h["kontostand"]),
        "anzahl_erwachsene": _z(h["anzahl_erwachsene"]),
        "anzahl_kinder": _z(h["anzahl_kinder"]),
        "hp_geburtsdatum": _d(hp["geburtsdatum"]),
        "angehoerige": "\n".join(
            sorted(_person_text(p["vorname"], p["nachname"], p["geburtsdatum"]) for p in personen)
        ),
        "abholer": "\n".join(
            sorted(_person_text(a["vorname"], a["nachname"], "") for a in abholer)
        ),
        "sperren": "\n".join(
            sorted(_sperre_text(s["von"], s["bis"], s["begruendung"]) for s in sperren)
        ),
    }
    for k, _ in PERSON_FELDER:
        werte.setdefault(f"hp_{k}", hp.get(k) or "")
    werte.update({f"z_{k}": _z(v) for k, v in h["zusatz"].items()})
    werte.update({f"pz_{k}": _z(v) for k, v in hp["zusatz"].items()})
    return werte


def _flach_bestand(h: Haushalt) -> dict[str, str]:
    personen = list(h.personen.all())
    hp = next((p for p in personen if p.ist_hauptperson), None)
    werte = {
        "kundennummer": h.kundennummer,
        "status": h.status,
        "kundengruppe": h.kundengruppe.name if h.kundengruppe else "",
        "kunde_seit": _d(h.kunde_seit),
        "ausweis_gueltig_bis": _d(h.ausweis_gueltig_bis),
        "letzter_besuch": _d(h.letzter_besuch),
        "einkommensart": h.einkommensart.bezeichnung if h.einkommensart else "",
        "strasse": h.strasse,
        "plz": h.plz,
        "ort": h.ort,
        "telefon": h.telefon,
        "email": h.email,
        "kontostand": _euro(h.kontostand),
        "anzahl_erwachsene": _z(h.anzahl_erwachsene),
        "anzahl_kinder": _z(h.anzahl_kinder),
        "angehoerige": "\n".join(
            sorted(
                _person_text(p.vorname, p.nachname, p.geburtsdatum)
                for p in personen
                if not p.ist_hauptperson
            )
        ),
        "abholer": "\n".join(
            sorted(_person_text(a.vorname, a.nachname, "") for a in h.abholer.all())
        ),
        "sperren": "\n".join(
            sorted(_sperre_text(s.von, s.bis, s.begruendung) for s in h.sperren.all())
        ),
    }
    for k, _ in PERSON_FELDER:
        wert = getattr(hp, k) if hp else ""
        werte[f"hp_{k}"] = _d(wert) if k == "geburtsdatum" else (wert or "")
    werte.update({f"z_{k}": _z(v) for k, v in (h.zusatz or {}).items()})
    if hp:
        werte.update({f"pz_{k}": _z(v) for k, v in (hp.zusatz or {}).items()})
    return werte


def _gruppen_namen() -> dict[tuple, str]:
    """(Kürzel, Name) aus dem Import → Name der vorhandenen Kundengruppe, damit „gleich“ auch
    bei anderer Schreibweise des Namens gleich ist."""
    from apps.kunden.models import Kundengruppe

    ergebnis = {}
    for g in Kundengruppe.objects.all():
        if g.kuerzel:
            for name in ("", g.name.lower()):
                ergebnis[(g.kuerzel.lower(), name)] = g.name
        ergebnis[("", g.name.lower())] = g.name
    return ergebnis


def _name(werte) -> str:
    return (
        f"{werte['kundennummer']} – {werte.get('hp_vorname', '')} "
        f"{werte.get('hp_nachname', '')}".strip()
    )


def planen(daten: dict) -> dict:
    """Abgleich im Format von ``apps.datenimport.abgleich`` (Schlüssel: Kundennummer)."""
    personen, abholer = _nach_nummer(daten["personen"]), _nach_nummer(daten["abholer"])
    sperren, gruppen = _nach_nummer(daten["sperren"]), _gruppen_namen()
    saetze = [
        {
            "zeile": i + 2,
            "werte": _flach_import(
                h,
                personen.get(h["kundennummer"], []),
                abholer.get(h["kundennummer"], []),
                sperren.get(h["kundennummer"], []),
                gruppen,
            ),
        }
        for i, h in enumerate(daten["haushalte"])
    ]
    bestand = []
    for h in (
        Haushalt.objects.select_related("kundengruppe", "einkommensart")
        .prefetch_related("personen", "abholer", "sperren")
        .order_by("kundennummer")
    ):
        lokal = ""
        if h.aufgenommen_am:
            lokal = "in bintafeln aufgenommen"
        elif h.geaendert_am:
            lokal = f"in bintafeln geändert am {timezone.localtime(h.geaendert_am):%d.%m.%Y}"
        werte = _flach_bestand(h)
        bestand.append(
            Bestandseintrag(
                id=h.kundennummer,
                name=_name(werte),
                werte=werte,
                lokal=lokal,
                link=reverse("kunden:haushalt", args=[h.kundennummer]),
            )
        )
    nummern = {b.id for b in bestand}
    nach_person: dict[str, str] = {}
    for b in bestand:
        if b.werte["hp_geburtsdatum"]:
            nach_person.setdefault(
                normalisieren(b.werte["hp_vorname"] + b.werte["hp_nachname"])
                + b.werte["hp_geburtsdatum"],
                b.id,
            )

    def treffer(werte):
        if werte["kundennummer"] in nummern:
            return Treffer(werte["kundennummer"], True)
        if werte["hp_geburtsdatum"]:
            schluessel = normalisieren(werte["hp_vorname"] + werte["hp_nachname"])
            gleich = nach_person.get(schluessel + werte["hp_geburtsdatum"])
            if gleich:
                return Treffer(
                    gleich,
                    False,
                    "andere Kundennummer, gleicher Name und Geburtsdatum der Hauptperson",
                )
        return None

    # Nur Nachgereichtes (ohne haushalte.csv): keine Frage nach fehlenden Haushalten
    ausnehmen = nummern if daten.get("nur_ergaenzen") else ()
    return abgleich.abgleichen(
        saetze,
        bestand,
        felder=felder(daten.get("spalten", {})),
        treffer=treffer,
        name=_name,
        fehlt_ausnehmen=ausnehmen,
    ).als_dict()


def _aendern(h: Haushalt, felder_neu: set[str], imp: dict, gruppiert, bezuege, benutzer):
    """Übernimmt die gewählten Felder ``felder_neu`` aus dem Import-Haushalt ``imp``."""
    from apps.ausgabe import konto

    nummer = imp["kundennummer"]
    geaendert = []
    for k, _ in HAUSHALT_FELDER:
        if k not in felder_neu or k == "kontostand":
            continue
        if k == "kundengruppe":
            h.kundengruppe = bezuege.gruppe(imp["kundengruppe"])
        elif k == "einkommensart":
            h.einkommensart = bezuege.art(imp["einkommensart"])
        elif k in DATUM:
            setattr(h, k, _datum(imp[k]))
        else:
            setattr(h, k, imp[k])
        geaendert.append(k)
    zusatz = {k[2:] for k in felder_neu if k.startswith("z_")}
    for k in zusatz:
        h.zusatz = {**(h.zusatz or {}), k: imp["zusatz"][k]}
    h.importiert_am = timezone.now()
    h.save()
    if "kontostand" in felder_neu and imp["kontostand"] is not None:
        unterschied = Decimal(imp["kontostand"]) - (h.kontostand or Decimal(0))
        if unterschied:
            konto.korrigieren(
                h,
                unterschied,
                "Kontostand aus dem Import übernommen",
                benutzer.get_username() if benutzer else "Import",
            )
    person_felder = {k[3:] for k in felder_neu if k.startswith("hp_")}
    person_zusatz = {k[3:] for k in felder_neu if k.startswith("pz_")}
    if person_felder or person_zusatz:
        hp = h.personen.filter(ist_hauptperson=True).first() or _person(h, imp["hauptperson"], True)
        for k in person_felder:
            wert = imp["hauptperson"][k]
            setattr(hp, k, _datum(wert) if k == "geburtsdatum" else wert)
        for k in person_zusatz:
            hp.zusatz = {**(hp.zusatz or {}), k: imp["hauptperson"]["zusatz"][k]}
        hp.save()
    if "angehoerige" in felder_neu:
        h.personen.filter(ist_hauptperson=False).delete()
        h.personen.model.objects.bulk_create(
            _person(h, p, False) for p in gruppiert["personen"].get(nummer, [])
        )
    if "abholer" in felder_neu:
        h.abholer.all().delete()
        h.abholer.model.objects.bulk_create(
            _abholer(h, a) for a in gruppiert["abholer"].get(nummer, [])
        )
    if "sperren" in felder_neu:
        h.sperren.all().delete()
        h.sperren.model.objects.bulk_create(
            _sperre(h, s) for s in gruppiert["sperren"].get(nummer, [])
        )


def _gleich(text) -> str:
    return " ".join(str(text or "").split()).casefold()


def _hinzufuegen(nummern: set[str], daten, bezuege, listen_auch: set[str]) -> int:
    """Fügt Zeilen zu vorhandenen Haushalten hinzu, die es dort noch nicht gibt: Abholungen,
    Ausnahmen, Anmerkungen und Kontobuchungen; für Haushalte in ``listen_auch`` (nicht in
    haushalte.csv, also nachgereicht) auch Angehörige, Abholberechtigte und Sperren.
    Alles mengenweise, damit auch zehntausende Zeilen schnell gehen."""
    from apps.ausgabe.models import Buchung
    from apps.kunden.models import Abholer, Abholung, Ausnahme, Bemerkung, Person, Sperre

    haushalte = {h.kundennummer: h for h in Haushalt.objects.filter(kundennummer__in=nummern)}
    if not haushalte:
        return 0
    filter_ = {"haushalt__kundennummer__in": list(haushalte)}
    nr = "haushalt__kundennummer"
    arten = [
        ("abholungen", Abholung, lambda e: (e["kundennummer"], e["datum"]),
         Abholung.objects.filter(**filter_).values_list(nr, "datum"),
         lambda t: (t[0], t[1].isoformat()), lambda h, e: _abholung(h, e, bezuege)),
        ("ausnahmen", Ausnahme, lambda e: (e["kundennummer"], e["datum"]),
         Ausnahme.objects.filter(**filter_).values_list(nr, "datum"),
         lambda t: (t[0], t[1].isoformat()), _ausnahme),
        ("bemerkungen", Bemerkung, lambda e: (e["kundennummer"], e["datum"], _gleich(e["text"])),
         Bemerkung.objects.filter(**filter_).values_list(nr, "datum", "text"),
         lambda t: (t[0], t[1].isoformat(), _gleich(t[2])), _bemerkung),
        ("buchungen", Buchung,
         lambda e: (e["kundennummer"], e["datum"], Decimal(e["betrag"]), e["art"]),
         Buchung.objects.filter(importiert=True, **filter_).values_list(
             nr, "datum", "haben", "soll", "art"),
         lambda t: (t[0], t[1].isoformat(), t[2] - t[3], t[4]),
         lambda h, e: _buchung(h, e, bezuege)),
    ]  # fmt: skip
    if listen_auch:
        arten += [
            ("personen", Person,
             lambda e: (e["kundennummer"], _gleich(e["vorname"]), _gleich(e["nachname"]),
                        e["geburtsdatum"] or ""),
             Person.objects.filter(**filter_).values_list(nr, "vorname", "nachname",
                                                         "geburtsdatum"),
             lambda t: (t[0], _gleich(t[1]), _gleich(t[2]), t[3].isoformat() if t[3] else ""),
             lambda h, e: _person(h, e, False)),
            ("abholer", Abholer,
             lambda e: (e["kundennummer"], _gleich(e["vorname"]), _gleich(e["nachname"])),
             Abholer.objects.filter(**filter_).values_list(nr, "vorname", "nachname"),
             lambda t: (t[0], _gleich(t[1]), _gleich(t[2])), _abholer),
            ("sperren", Sperre, lambda e: (e["kundennummer"], e["von"]),
             Sperre.objects.filter(**filter_).values_list(nr, "von"),
             lambda t: (t[0], t[1].isoformat()), _sperre),
        ]  # fmt: skip
    anzahl = 0
    for schluessel, modell, von_import, vorhanden_qs, von_bestand, bauen in arten:
        vorhanden = {von_bestand(t) for t in vorhanden_qs}
        neue = []
        for e in daten.get(schluessel, []):
            if e["kundennummer"] not in haushalte:
                continue
            if schluessel in ("personen", "abholer", "sperren") and (
                e["kundennummer"] not in listen_auch
            ):
                continue
            k = von_import(e)
            if k in vorhanden:
                continue
            vorhanden.add(k)
            neue.append(bauen(haushalte[e["kundennummer"]], e))
        modell.objects.bulk_create(neue, batch_size=5000)
        anzahl += len(neue)
    return anzahl


@transaction.atomic
def ergaenzen(
    daten: dict, entscheidung, *, modus, benutzer, dateien, pruefsumme, anzahl_warnungen
) -> tuple[ImportLauf, dict]:
    """Legt die gewählten neuen Haushalte an, übernimmt die gewählten Felder und löscht die
    gewählten fehlenden Haushalte in den Papierkorb."""
    from apps.kunden.entfernen import haushalt_loeschen

    imp = {h["kundennummer"]: h for h in daten["haushalte"]}
    neu = {w["kundennummer"] for w in entscheidung.anlegen}
    bezuege = _Bezuege()
    vorher = historie.schnappschuesse()
    bezuege.gruppen_einspielen(daten, nur_neue=modus == abgleich.NUR_NEUE)
    teil = {
        k: [e for e in v if e.get("kundennummer") in neu]
        if isinstance(v, list) and k not in ("kundengruppen", "neue_gruppen")
        else v
        for k, v in daten.items()
    }
    teil["haushalte"] = [h for h in daten["haushalte"] if h["kundennummer"] in neu]
    _anlegen(teil, bezuege)

    gruppiert = {k: _nach_nummer(daten[k]) for k in ("personen", "abholer", "sperren")}
    geaendert = 0
    for nummer, felder_neu in entscheidung.aendern.items():
        h = Haushalt.objects.filter(kundennummer=nummer).first()
        herkunft = entscheidung.quellen.get(nummer, {}).get("kundennummer", nummer)
        quelle = imp.get(herkunft)
        if h is None or quelle is None:
            continue
        _aendern(h, set(felder_neu), quelle, gruppiert, bezuege, benutzer)
        geaendert += 1
    # Zu vorhandenen Haushalten nur hinzufügen, was es noch nicht gibt (auch Nachgereichtes
    # ohne haushalte.csv); vorhandene Einträge bleiben unverändert.
    alle = {e["kundennummer"] for k, v in daten.items() if isinstance(v, list)
            and k not in ("kundengruppen", "neue_gruppen") for e in v} - neu  # fmt: skip
    verlauf = _hinzufuegen(alle, daten, bezuege, listen_auch=alle - set(imp))
    geloescht = 0
    for nummer, aktion in entscheidung.fehlt.items():
        h = Haushalt.objects.filter(kundennummer=nummer).first()
        if h and aktion == "loeschen":
            haushalt_loeschen(benutzer, h)
            geloescht += 1
    _nach_import(vorher, benutzer)
    lauf = ImportLauf.objects.create(
        benutzer=benutzer,
        dateien=dateien,
        pruefsumme=pruefsumme,
        art=modus,
        anzahl_haushalte=len(neu) + geaendert,
        anzahl_personen=len(teil["haushalte"]) + len(teil["personen"]),
        anzahl_abholer=len(teil["abholer"]),
        anzahl_sperren=len(teil["sperren"]),
        anzahl_bemerkungen=len(teil["bemerkungen"]),
        anzahl_abholungen=len(teil.get("abholungen", [])),
        anzahl_ausnahmen=len(teil.get("ausnahmen", [])),
        anzahl_buchungen=len(teil.get("buchungen", [])),
        anzahl_warnungen=anzahl_warnungen,
    )
    return lauf, {
        "neu": len(neu),
        "geaendert": geaendert,
        "geloescht": geloescht,
        "verlauf": verlauf,
        "ausgelassen": entscheidung.ausgelassen,
    }
