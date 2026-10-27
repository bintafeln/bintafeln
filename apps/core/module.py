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
    # die Einträge an ein Untermenü der Einstellungen (z. B. "Einstellungen/Ausgabe"). Sonst
    # "Bereich" oder "Bereich/Abschnitt" des Menüs (Ausgabestelle, Kunden, Verein, Auswertungen,
    # apps/core/menue.py); ein unbekannter Bereich kommt als eigener Bereich dazu.
    menue: Callable | None = None
    # Datensicherung (ADR 0037): Bereich der Modelle und vorübergehende Modelle ("app.modell")
    sicherung_bereich: str = "einstellungen"
    sicherung_ausgenommen: tuple[str, ...] = ()
    # Hinweise für die Einlass-Karte eines Haushalts: einlass(haushalt, heute, stelle) ->
    # [{"text": …, "farbe": "gruen" | "gelb" | "rot" | "info", optional "ampel": Text für die
    # Bewertung und "wort": Wort unter der Ampel (z. B. zu früh: Gelb blinkt zur Farbe dazu),
    # "knopf": {"recht", "url", "text", "erklaerung"} (kleiner POST-Knopf mit Erklärungsblase)}]
    einlass: Callable | None = None
    # Auskunft nach Art. 15 zu einem Antrag: auskunft_antrag(antrag, pdf) schreibt eigene
    # Abschnitte. Läuft auch bei ausgeschaltetem Modul (die Daten sind ja gespeichert).
    auskunft_antrag: Callable | None = None
    # Fristen und Automatik (z. B. Status nach Tagen, Löschfristen); läuft wie die Fristen der
    # übrigen Apps beim Aufruf der Startseite, nur bei eingeschaltetem Modul. Aufruf ohne Argumente.
    fristen: Callable | None = None
    # Vorlage, die angemeldeten Personen rechts in der Kopfzeile erscheint (z. B. Wetter).
    # Sie sollte ihren Inhalt nachladen (hx-trigger="load"), damit die Seite nicht wartet.
    kopfzeile: str = ""
    # Vorlage unter dem Menü links (z. B. Aufruf-Steuerung); prüft selbst Rechte und lädt nach.
    seitenleiste: str = ""
    # Suche im Seitenkopf (Bereich „Listen und Einstellungen“): suchen(benutzer, begriff, grenze)
    # -> [(Titel, Adresse, Zusatz)]; das Modul prüft selbst die Rechte.
    suchen: Callable | None = None
    # Beitrag zur Startseite unter der Begrüßung: startseite(request) -> HTML (render_to_string)
    startseite: Callable | None = None


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


def suchen(benutzer, begriff: str, grenze: int) -> list:
    """Treffer der eingeschalteten Module für die Suche im Seitenkopf."""
    from apps.core.suche import Treffer

    an = eingeschaltet()
    return [Treffer(*t) for m in alle() if m.kennung in an and m.suchen
            for t in m.suchen(benutzer, begriff, grenze)]  # fmt: skip


def startseite(request) -> list[str]:
    """HTML-Beiträge der eingeschalteten Module für die Startseite (leere fallen weg)."""
    an = eingeschaltet()
    teile = [m.startseite(request) for m in alle() if m.kennung in an and m.startseite]
    return [t for t in teile if t]


def kopfzeile() -> list[str]:
    """Vorlagen der eingeschalteten Module für die Kopfzeile."""
    an = eingeschaltet()
    return [m.kopfzeile for m in alle() if m.kennung in an and m.kopfzeile]


def seitenleiste() -> list[str]:
    """Vorlagen der eingeschalteten Module unter dem Menü links."""
    an = eingeschaltet()
    return [m.seitenleiste for m in alle() if m.kennung in an and m.seitenleiste]


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
