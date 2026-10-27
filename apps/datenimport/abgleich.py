"""Abgleich einer Importdatei mit dem Bestand und die Entscheidungen dazu (ADR 0078).

Ein Ziel (Ausgabestellen, Mitarbeitende, Kundenstamm) liefert bereinigte Sätze ``{"zeile": n,
"werte": {feld: text}}`` und seinen Bestand. ``abgleichen()`` sortiert daraus

- **neu**: in der Datei, nicht im Bestand; bei einer möglichen Dublette mit Hinweis,
- **geaendert**: in beiden, mit den Unterschieden je Feld – „konflikt“ (beide gefüllt,
  verschieden) oder „ergaenzung“ (im Bestand leer),
- **gleich**: Anzahl ohne Unterschiede,
- **fehlt**: im Bestand, aber nicht in der Datei,
- **doppelt**: Sätze, die in der Datei mehrfach vorkommen (zusammengeführt, Widersprüche
  markiert).

Eine leere Zelle überschreibt nie etwas. Unsichere Treffer (z. B. nur gleicher Name) werden nicht
stillschweigend zusammengeführt: Man wählt „dieselbe“, „neu anlegen“ oder „auslassen“.

``vorgaben()`` setzt je Modus die Voreinstellung jeder Wahl, ``entscheiden()`` liest die Wahl
aus dem abgeschickten Formular. Das Ergebnis ist reines JSON und wird in der Importsitzung
gespeichert; angewandt wird es vom Ziel.
"""

from dataclasses import dataclass, field

NUR_NEUE = "neu"
AKTUALISIEREN = "aktualisieren"
ERSETZEN = "ersetzen"
MODI = {
    NUR_NEUE: (
        "Nur neue hinzufügen",
        "Neue Einträge werden angelegt. Vorhandene bleiben, wie sie sind; Unterschiede werden "
        "angezeigt und lassen sich einzeln trotzdem übernehmen.",
    ),
    AKTUALISIEREN: (
        "Hinzufügen und aktualisieren",
        "Neue Einträge werden angelegt, Unterschiede bei vorhandenen übernommen (je Feld "
        "abwählbar). Leere Zellen überschreiben nichts, gelöscht wird nichts.",
    ),
    ERSETZEN: (
        "Ersetzen",
        "Wie „Hinzufügen und aktualisieren“; zusätzlich ist vorgeschlagen, Einträge, die nicht "
        "mehr in der Datei stehen, zu entfernen – je Eintrag abwählbar.",
    ),
}
MAX_ANZEIGE = 500  # so viele Einträge je Gruppe stehen einzeln auf der Seite


@dataclass
class Bestandseintrag:
    id: str
    name: str
    werte: dict[str, str]
    lokal: str = ""  # z. B. „in bintafeln geändert am …“: Konflikte sind dann nicht vorgewählt
    link: str = ""


@dataclass
class Treffer:
    id: str
    sicher: bool
    grund: str = ""


@dataclass
class Plan:
    neu: list[dict] = field(default_factory=list)
    geaendert: list[dict] = field(default_factory=list)
    gleich: int = 0
    fehlt: list[dict] = field(default_factory=list)
    doppelt: list[dict] = field(default_factory=list)

    def als_dict(self) -> dict:
        return {
            "neu": self.neu,
            "geaendert": self.geaendert,
            "gleich": self.gleich,
            "fehlt": self.fehlt,
            "doppelt": self.doppelt,
        }


def unterschiede(alt: dict[str, str], neu: dict[str, str], felder) -> list[dict]:
    ergebnis = []
    for schluessel, bezeichnung in felder:
        a, n = (alt.get(schluessel) or "").strip(), (neu.get(schluessel) or "").strip()
        if not n or a == n:
            continue
        ergebnis.append(
            {
                "feld": schluessel,
                "bezeichnung": bezeichnung,
                "alt": a,
                "neu": n,
                "art": "konflikt" if a else "ergaenzung",
            }
        )
    return ergebnis


def _gleich(text: str) -> str:
    return " ".join(text.split()).casefold()


def zusammenfuehren(saetze: list[dict], schluessel, felder) -> tuple[list[dict], list[dict]]:
    """Sätze mit gleichem Schlüssel zu einem: spätere füllen Lücken, Widersprüche werden
    gemeldet (der erste Wert gilt)."""
    bezeichnung = dict(felder)
    erste: dict[str, dict] = {}
    doppelt: dict[str, dict] = {}
    ergebnis = []
    for satz in saetze:
        k = schluessel(satz["werte"])
        if not k:
            ergebnis.append(satz)
            continue
        if k not in erste:
            erste[k] = satz
            ergebnis.append(satz)
            continue
        ziel = erste[k]
        eintrag = doppelt.setdefault(k, {"zeilen": [ziel["zeile"]], "widersprueche": []})
        eintrag["zeilen"].append(satz["zeile"])
        for f, wert in satz["werte"].items():
            if not wert:
                continue
            if not ziel["werte"].get(f):
                ziel["werte"][f] = wert
            elif _gleich(ziel["werte"][f]) != _gleich(wert):
                eintrag["widersprueche"].append(
                    {
                        "feld": bezeichnung.get(f, f),
                        "gilt": ziel["werte"][f],
                        "auch": wert,
                        "zeile": satz["zeile"],
                    }
                )
    gemeldet = [{"name": k, **v} for k, v in doppelt.items()]
    return ergebnis, gemeldet


def abgleichen(
    saetze: list[dict],
    bestand: list[Bestandseintrag],
    *,
    felder,
    treffer,
    name,
    schluessel=None,
    fehlt_ausnehmen=(),
) -> Plan:
    """``treffer(werte) -> Treffer | None`` sucht den passenden Bestandseintrag, ``name(werte)``
    beschreibt einen Satz, ``schluessel(werte)`` erkennt Doppelte in der Datei."""
    plan = Plan()
    if schluessel:
        saetze, plan.doppelt = zusammenfuehren(saetze, schluessel, felder)
    nach_id = {b.id: b for b in bestand}
    gesehen: set[str] = set()
    for i, satz in enumerate(saetze):
        werte = satz["werte"]
        t = treffer(werte)
        b = nach_id.get(t.id) if t else None
        if t and b and t.sicher and t.id in gesehen:
            # zweiter Satz für denselben Bestandseintrag (z. B. gleiche E-Mail): nicht still
            # doppelt ändern, sondern als unsicher zur Wahl stellen
            t = Treffer(t.id, False, "passt zu einem Eintrag, den schon eine andere Zeile ändert")
        if b is None:
            plan.neu.append({"i": i, "zeile": satz["zeile"], "name": name(werte), "werte": werte})
            continue
        if not t.sicher:
            plan.neu.append(
                {
                    "i": i,
                    "zeile": satz["zeile"],
                    "name": name(werte),
                    "werte": werte,
                    "dublette": {
                        "id": b.id,
                        "name": b.name,
                        "grund": t.grund,
                        "link": b.link,
                        "felder": unterschiede(b.werte, werte, felder),
                    },
                }
            )
            continue
        gesehen.add(b.id)
        diff = unterschiede(b.werte, werte, felder)
        if not diff:
            plan.gleich += 1
            continue
        plan.geaendert.append(
            {
                "i": i,
                "zeile": satz["zeile"],
                "id": b.id,
                "name": b.name,
                "link": b.link,
                "lokal": b.lokal,
                "felder": diff,
            }
        )
    ausgenommen = set(fehlt_ausnehmen)
    for b in bestand:
        if (
            b.id not in gesehen
            and b.id not in ausgenommen
            and not any(e.get("dublette", {}).get("id") == b.id for e in plan.neu)
        ):
            plan.fehlt.append({"id": b.id, "name": b.name, "link": b.link, "lokal": b.lokal})
    return plan


def vorgaben(plan: dict, modus: str, aktionen: list[tuple[str, str]]) -> dict:
    """Ergänzt den Plan um die Voreinstellung jeder Wahl im gewählten Modus (für die Seite)."""
    uebernehmen = modus in (AKTUALISIEREN, ERSETZEN)
    for e in plan["geaendert"]:
        for f in e["felder"]:
            f["an"] = uebernehmen and (f["art"] == "ergaenzung" or not e.get("lokal"))
    for e in plan["neu"]:
        if e.get("dublette"):
            # Unsicherer Treffer: lieber nichts anlegen, bis man es angesehen hat
            e["wahl"] = "aus"
            for f in e["dublette"]["felder"]:
                f["an"] = uebernehmen
    entfernen = aktionen[-1][0] if modus == ERSETZEN and len(aktionen) > 1 else aktionen[0][0]
    for e in plan["fehlt"]:
        e["wahl"] = aktionen[0][0] if e.get("lokal") else entfernen
    return plan


@dataclass
class Entscheidung:
    anlegen: list[dict] = field(default_factory=list)  # Werte neuer Sätze
    aendern: dict[str, dict[str, str]] = field(default_factory=dict)  # Bestand-ID → Felder
    fehlt: dict[str, str] = field(default_factory=dict)  # Bestand-ID → Aktion
    quellen: dict[str, dict] = field(default_factory=dict)  # Bestand-ID → Satz bei Dubletten
    ausgelassen: int = 0


def entscheiden(plan: dict, modus: str, daten, aktionen: list[tuple[str, str]]) -> Entscheidung:
    """Liest die Wahl aus ``daten`` (request.POST). Was nicht auf der Seite stand (mehr als
    ``MAX_ANZEIGE`` je Gruppe), bekommt die Voreinstellung des Modus."""
    plan = vorgaben(plan, modus, aktionen)
    erlaubt = {a for a, _ in aktionen}
    ergebnis = Entscheidung()

    def an(name, nummer, vorgabe):
        return daten.get(name) == "1" if nummer < MAX_ANZEIGE else vorgabe

    for nummer, e in enumerate(plan["neu"]):
        if not e.get("dublette"):
            ergebnis.anlegen.append(e["werte"])
            continue
        wahl = daten.get(f"n-{e['i']}", e["wahl"]) if nummer < MAX_ANZEIGE else e["wahl"]
        if wahl == "neu":
            ergebnis.anlegen.append(e["werte"])
        elif wahl == "gleich":
            felder = {
                f["feld"]: f["neu"]
                for f in e["dublette"]["felder"]
                if an(f"f-{e['i']}-{f['feld']}", nummer, f["an"])
            }
            ergebnis.aendern.setdefault(e["dublette"]["id"], {}).update(felder)
            ergebnis.quellen[e["dublette"]["id"]] = e["werte"]
        else:
            ergebnis.ausgelassen += 1
    for nummer, e in enumerate(plan["geaendert"]):
        felder = {
            f["feld"]: f["neu"]
            for f in e["felder"]
            if an(f"f-{e['i']}-{f['feld']}", nummer, f["an"])
        }
        if felder:
            ergebnis.aendern.setdefault(e["id"], {}).update(felder)
    for nummer, e in enumerate(plan["fehlt"]):
        wahl = daten.get(f"w-{nummer}", e["wahl"]) if nummer < MAX_ANZEIGE else e["wahl"]
        if wahl in erlaubt and wahl != aktionen[0][0]:
            ergebnis.fehlt[e["id"]] = wahl
    return ergebnis
