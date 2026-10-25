"""Zuschaltbare Module (ADR 0049).

Ein Modul ist eine eigene App unter ``apps/`` mit einer Datei ``modul.py``, die ein Objekt
``MODUL`` (``Modul``) bereitstellt. Darin stehen Rechte, Menüeinträge, Handbuch-Kapitel und die
Adressen des Moduls. Der übrige Code kennt Module nur über diese Datei: Rechtekatalog, Menü und
Handbuch sammeln die Beiträge ein, die ``ModulMiddleware`` sperrt die Adressen ausgeschalteter
Module (404).

Welche Module es gibt, steht in ``settings.BINTAFELN_MODULE``; welche eingeschaltet sind, legt
jede Tafel in den Tafel-Einstellungen fest (``TafelEinstellungen.module``). Ausgeschaltete Module
behalten ihre Daten; ihre Tabellen bleiben bestehen, damit Updates und Sicherungen gleich laufen.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from importlib import import_module

from django.conf import settings
from django.http import Http404


@dataclass(frozen=True)
class Modul:
    kennung: str
    titel: str
    beschreibung: str
    app_label: str
    # Adressanfänge, die nur bei eingeschaltetem Modul erreichbar sind (z. B. "/aufruf/")
    pfade: tuple[str, ...] = ()
    # (code, bezeichnung, hilfe) – Bereich im Rechtekatalog ist der Titel des Moduls
    rechte: tuple[tuple[str, str, str], ...] = ()
    # Rechte der mitgelieferten Rollen beim ersten Anlegen (wie rechte.VORGABEN)
    vorgaben: dict[str, tuple[str, ...]] = field(default_factory=dict)
    # (kennung, titel, rechte) – Vorlage ``hilfe/<kennung>.html`` liegt in der App
    kapitel: tuple[tuple[str, str, tuple[str, ...]], ...] = ()
    # menue(eintrag) -> [(bereich, [(recht, eintrag), …]), …]; "Einstellungen/<Gruppe>" hängt
    # die Einträge an ein Untermenü der Einstellungen (z. B. "Einstellungen/Ausgabe"), jeder
    # andere Bereich wird als eigener Bereich nach „Ausgabe“ eingefügt.
    menue: Callable | None = None
    # Datensicherung (ADR 0037): Bereich der Modelle und vorübergehende Modelle ("app.modell")
    sicherung_bereich: str = "einstellungen"
    sicherung_ausgenommen: tuple[str, ...] = ()
    # Hinweise für die Einlass-Karte eines Haushalts: einlass(haushalt, heute, stelle) ->
    # [{"text": …, "farbe": "gruen" | "gelb" | "rot" | "info"}]
    einlass: Callable | None = None
    # Auskunft nach Art. 15 zu einem Antrag: auskunft_antrag(antrag, pdf) schreibt eigene
    # Abschnitte. Läuft auch bei ausgeschaltetem Modul (die Daten sind ja gespeichert).
    auskunft_antrag: Callable | None = None
    # Fristen und Automatik (z. B. Status nach Tagen, Löschfristen); läuft wie die Fristen der
    # übrigen Apps beim Aufruf der Startseite, nur bei eingeschaltetem Modul. Aufruf ohne Argumente.
    fristen: Callable | None = None


@cache
def alle() -> tuple[Modul, ...]:
    """Alle installierten Module in der Reihenfolge von ``settings.BINTAFELN_MODULE``."""
    return tuple(import_module(f"{app}.modul").MODUL for app in settings.BINTAFELN_MODULE)


def eingeschaltet() -> set[str]:
    from apps.core.models import TafelEinstellungen

    gewaehlt = set(TafelEinstellungen.laden().module or [])
    return {m.kennung for m in alle() if m.kennung in gewaehlt}


def aktiv(kennung: str) -> bool:
    return kennung in eingeschaltet()


def ausgeschaltete_rechte() -> set[str]:
    an = eingeschaltet()
    return {code for m in alle() if m.kennung not in an for code, _, _ in m.rechte}


def einlass_hinweise(haushalt, heute, stelle) -> list[dict]:
    """Hinweise der eingeschalteten Module für die Einlass-Karte, je mit Titel des Moduls."""
    an = eingeschaltet()
    return [{**h, "modul": m.titel} for m in alle() if m.kennung in an and m.einlass
            for h in m.einlass(haushalt, heute, stelle)]  # fmt: skip


def auskunft_antrag(antrag, pdf) -> None:
    for m in alle():
        if m.auskunft_antrag:
            m.auskunft_antrag(antrag, pdf)


def fristen_anwenden() -> None:
    """Fristen aller eingeschalteten Module."""
    an = eingeschaltet()
    for m in alle():
        if m.kennung in an and m.fristen:
            m.fristen()


def auswahl() -> list[tuple[str, str]]:
    """Für das Auswahlfeld in den Tafel-Einstellungen."""
    return [(m.kennung, f"{m.titel} – {m.beschreibung}") for m in alle()]


class ModulMiddleware:
    """Adressen ausgeschalteter Module gibt es nicht (404)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        for m in alle():
            if request.path.startswith(m.pfade) and not aktiv(m.kennung):
                raise Http404("Dieses Modul ist ausgeschaltet.")
        return self.get_response(request)
