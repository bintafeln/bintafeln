"""Merkmale wie „Schwerbehindert“ oder „Vegetarier“ (ADR 0071): Zusatzfelder Ja/Nein, die der
Einlass sieht und die als Symbol auf den Ausweis kommen können. Gezeigt wird nur, was „ja“ ist;
leer gilt als „nein“."""

from apps.core.auswahl import FESTE_MERKMALE
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
