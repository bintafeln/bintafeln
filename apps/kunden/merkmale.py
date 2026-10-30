"""Merkmale wie „Schwerbehindert“ oder „Vegetarier“ (ADR 0071): Zusatzfelder Ja/Nein, die der
Einlass sieht und die als Symbol auf den Ausweis kommen können. Gezeigt wird nur, was „ja“ ist;
leer gilt als „nein“."""

from apps.core.auswahl import (
    FESTE_MERKMALE,
    GDB_STUFEN,
    gdb_text,
    merkzeichen_liste,
    merkzeichen_text,
)
from apps.konten import rollen
from apps.kunden.models import Zusatzfeld


def feste_anlegen() -> None:
    """Mitgelieferte Merkmale anlegen, die fehlen (z. B. nach dem Zurücksetzen der Demo); die
    Migration 0029 macht dasselbe beim Update."""
    for i, (schluessel, bezeichnung, art9, ausweis) in enumerate(FESTE_MERKMALE):
        Zusatzfeld.objects.get_or_create(schluessel=schluessel, defaults={
            "bezeichnung": bezeichnung, "gilt_fuer": Zusatzfeld.GiltFuer.PERSON,
            "typ": Zusatzfeld.Typ.JA_NEIN, "besondere_kategorie": art9, "reihenfolge": 100 + i,
            "einlass": True, "ausweis": ausweis,
        })  # fmt: skip


def _felder(**filter_) -> list[Zusatzfeld]:
    return list(Zusatzfeld.objects.filter(aktiv=True, typ=Zusatzfeld.Typ.JA_NEIN, **filter_))


def _ja(feld, haushalt, personen) -> list:
    """Wer bei diesem Feld „ja“ hat: Personen, beim Haushaltsfeld der Haushalt selbst (None)."""
    if feld.gilt_fuer == Zusatzfeld.GiltFuer.HAUSHALT:
        return [None] if (haushalt.zusatz or {}).get(feld.schluessel) is True else []
    return [p for p in personen if (p.zusatz or {}).get(feld.schluessel) is True]


def einlass(haushalt, benutzer) -> tuple[list[dict], bool]:
    """Für den Einlass: [{"name", "merkmale"}] je Person (Name leer = ganzer Haushalt) und ob
    eine Angabe der besonderen Kategorie (Art. 9) dabei ist (für das Zugriffsprotokoll)."""
    darf_art9 = rollen.hat_recht(benutzer, "kunden.besondere_kategorie")
    personen = sorted(haushalt.personen.all(), key=lambda p: (not p.ist_hauptperson, p.pk))
    je = {}
    art9 = False
    for feld in _felder(einlass=True):
        if feld.besondere_kategorie and not darf_art9:
            continue
        for wer in _ja(feld, haushalt, personen):
            je.setdefault(wer.pk if wer else None, (wer, []))[1].append(feld.bezeichnung)
            art9 = art9 or feld.besondere_kategorie
    reihenfolge = [None] + [p.pk for p in personen]
    zeilen = [je[k] for k in reihenfolge if k in je]
    return [{"name": f"{p.vorname} {p.nachname}".strip() if p else "", "merkmale": m}
            for p, m in zeilen], art9  # fmt: skip


def ausweis(haushalt) -> list[tuple[str, str]]:
    """Symbole für den Ausweis: [("rollstuhl", "") oder ("kuerzel", "V")], jedes nur einmal."""
    personen = list(haushalt.personen.all())
    symbole = []
    for feld in _felder(ausweis__in=["rollstuhl", "kuerzel"]):
        symbol = (feld.ausweis, feld.kuerzel if feld.ausweis == "kuerzel" else "")
        if symbol not in symbole and _ja(feld, haushalt, personen):
            symbole.append(symbol)
    return symbole


GDB_FELD = "gdb"
AUSWEIS_FELD = "sb_ausweis"  # Schwerbehindertenausweis vorgelegt (ADR 0092)


def gilt_schwerbehindert(gdb, merkzeichen, vorgelegt, einstellungen=None) -> bool:
    """Ob eine Person mit diesem GdB als „schwerbehindert“ gilt: nach den Bedingungen der Tafel
    (``KundenEinstellungen.sb_*``, ADR 0092). Blind, Taub, Stumm bleiben eigene Merkmale."""
    from apps.kunden.models import KundenEinstellungen

    e = einstellungen or KundenEinstellungen.laden()
    if gdb is None or gdb == "" or int(gdb) < e.sb_ab_gdb:
        return False
    noetig = merkzeichen_liste(e.sb_merkzeichen)
    if noetig and not set(noetig) & set(merkzeichen_liste(merkzeichen or "")):
        return False
    return bool(vorgelegt) or not e.sb_ausweis_vorgelegt


def _ausweis_feld() -> None:
    Zusatzfeld.objects.get_or_create(schluessel=AUSWEIS_FELD, defaults={
        "bezeichnung": "Schwerbehindertenausweis vorgelegt",
        "gilt_fuer": Zusatzfeld.GiltFuer.PERSON, "typ": Zusatzfeld.Typ.JA_NEIN,
        "besondere_kategorie": True, "reihenfolge": 99, "einlass": False,
    })  # fmt: skip


MERKZEICHEN_FELD = "merkzeichen"
# Merkzeichen, die ein mitgeliefertes Merkmal (Einlass, Ausweis) mit sich bringen; „Gl“
# (gehörlos) setzt bewusst nicht „Taub“, das meint am Einlass etwas anderes
MERKZEICHEN_MERKMAL = {"Bl": "blind", "TBl": "blind"}


def gdb_setzen(person, gdb, merkzeichen: str = "") -> None:
    """Grad der Behinderung aus dem Antrag an der Person (ohne Speichern): als Zusatzfeld
    „Grad der Behinderung“ (Art. 9, wird beim ersten Mal angelegt), ab GdB 50 das Merkmal
    „Schwerbehindert“, die Merkzeichen (G, aG, B …) als Zusatzfeld „Merkzeichen“ (mit Bedeutung) und
    Bl/TBl als Merkmal „Blind“. Leer (keine Angabe) ändert nichts."""
    if gdb is None or gdb == "":
        return
    gdb = int(gdb)
    Zusatzfeld.objects.get_or_create(schluessel=GDB_FELD, defaults={
        "bezeichnung": "Grad der Behinderung", "gilt_fuer": Zusatzfeld.GiltFuer.PERSON,
        "typ": Zusatzfeld.Typ.AUSWAHL, "besondere_kategorie": True, "reihenfolge": 99,
        "optionen": "\n".join(gdb_text(n) for n in [0, *GDB_STUFEN]),
    })  # fmt: skip
    zusatz = dict(person.zusatz or {})
    zusatz[GDB_FELD] = gdb_text(gdb)
    codes = merkzeichen_liste(merkzeichen) if gdb else []
    zusatz["schwerbehindert"] = gilt_schwerbehindert(gdb, ", ".join(codes),
                                                     zusatz.get(AUSWEIS_FELD))  # fmt: skip
    if codes or zusatz.get(MERKZEICHEN_FELD):
        Zusatzfeld.objects.get_or_create(schluessel=MERKZEICHEN_FELD, defaults={
            "bezeichnung": "Merkzeichen (Schwerbehindertenausweis)",
            "gilt_fuer": Zusatzfeld.GiltFuer.PERSON, "typ": Zusatzfeld.Typ.TEXT,
            "besondere_kategorie": True, "reihenfolge": 99,
        })  # fmt: skip
        zusatz[MERKZEICHEN_FELD] = merkzeichen_text(", ".join(codes))
    for code in codes:
        if code in MERKZEICHEN_MERKMAL:
            zusatz[MERKZEICHEN_MERKMAL[code]] = True
    person.zusatz = zusatz


# Felder, die im Kundenstamm nicht als einzelne Häkchen erscheinen: Sie ergeben sich aus dem
# Grad der Behinderung und den Merkzeichen (Formulare „Neuer Haushalt“ und „Person bearbeiten“);
# „Taub“ und „Stumm“ bleiben Merkmale für den Einlass, gespeicherte Werte bleiben erhalten
BEHINDERUNG_FELDER = ("schwerbehindert", "blind", "taub", "stumm", GDB_FELD, MERKZEICHEN_FELD,
                      AUSWEIS_FELD)  # fmt: skip


def gdb_von(person) -> int | None:
    """Grad der Behinderung aus dem Zusatzfeld („GdB 80“, „keine Behinderung“), sonst None."""
    text = (person.zusatz or {}).get(GDB_FELD, "")
    return next((n for n in [0, *GDB_STUFEN] if gdb_text(n) == text), None)


def behinderung_aendern(person, gdb, codes, vorgelegt=None) -> None:
    """GdB, Merkzeichen und „Ausweis vorgelegt“ aus dem Formular (ohne Speichern). Ohne Angabe
    fallen alle weg und „Schwerbehindert“ wird nein; „Blind“ folgt den Merkzeichen Bl/TBl."""
    zusatz = dict(person.zusatz or {})
    if vorgelegt is not None and gdb is not None:
        if vorgelegt or AUSWEIS_FELD in zusatz:
            _ausweis_feld()
            zusatz[AUSWEIS_FELD] = bool(vorgelegt)
        person.zusatz = zusatz
    if gdb is None:
        zusatz.pop(GDB_FELD, None)
        zusatz.pop(MERKZEICHEN_FELD, None)
        zusatz.pop(AUSWEIS_FELD, None)
        if "schwerbehindert" in zusatz:
            zusatz["schwerbehindert"] = False
        person.zusatz = zusatz
        return
    gdb_setzen(person, gdb, ", ".join(codes))
    blind = any(c in MERKZEICHEN_MERKMAL for c in merkzeichen_liste(", ".join(codes)) if gdb)
    if blind or "blind" in person.zusatz:
        person.zusatz["blind"] = blind


def neu_bewerten() -> int:
    """Nach geänderten Bedingungen: „Schwerbehindert“ bei allen Personen mit GdB neu setzen.
    Personen ohne GdB (z. B. von Hand oder aus dem Import) behalten ihren Wert. Liefert die
    Zahl der geänderten Personen."""
    from apps.kunden.models import KundenEinstellungen, Person

    e = KundenEinstellungen.laden()
    geaendert = 0
    for person in Person.objects.filter(zusatz__has_key=GDB_FELD):
        z = person.zusatz
        neu = gilt_schwerbehindert(gdb_von(person), z.get(MERKZEICHEN_FELD, ""),
                                   z.get(AUSWEIS_FELD), e)  # fmt: skip
        if bool(z.get("schwerbehindert")) != neu:
            person.zusatz = {**z, "schwerbehindert": neu}
            person.save(update_fields=["zusatz"])
            geaendert += 1
    return geaendert
