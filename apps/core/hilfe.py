"""Handbuch im Programm (ADR 0038): Kapitel je nach Rechten des Kontos.

Jedes Kapitel ist ein Template ``templates/hilfe/<kennung>.html``. Ein Kapitel erscheint, wenn das
Konto mindestens eines seiner Rechte hat; ohne Rechte ist es für alle. Innerhalb eines Kapitels
können Absätze mit ``{% if "recht" in rechte %}`` weiter eingeschränkt werden.
"""

from dataclasses import dataclass

from apps.konten import rollen


@dataclass(frozen=True)
class Kapitel:
    kennung: str
    titel: str
    teil: str
    rechte: tuple[str, ...] = ()


GRUNDLAGEN = "Grundlagen"
EINLASS = "Einlass und Kasse"
KUNDEN = "Kunden"
ANTRAEGE = "Anträge"
ADRESSEN = "Adressen und Verein"
TEAM = "Team (Ehrenamtliche und Angestellte)"
VERWALTUNG = "Einstellungen und Verwaltung"

KAPITEL = [
    Kapitel("erste-schritte", "Erste Schritte: Anmelden, Menü, Mein Konto", GRUNDLAGEN),
    Kapitel("suche", "Suchen: Kunden, Notizen, Anmerkungen und mehr", GRUNDLAGEN),
    Kapitel("zwei-faktor", "Zwei-Faktor-Anmeldung und Passwort", GRUNDLAGEN),
    Kapitel("datenschutz", "Datenschutz im Alltag", GRUNDLAGEN),
    Kapitel("papierkorb", "Papierkorb: Gelöschtes wiederherstellen", GRUNDLAGEN),
    Kapitel("einlass", "Der Einlass Schritt für Schritt", EINLASS, ("einlass.nutzen",)),
    Kapitel("scannen", "Kundennummer scannen: Handscanner, Kamera, Tippen", EINLASS,
            ("einlass.nutzen",)),
    Kapitel("ampel", "Die Ampel verstehen", EINLASS, ("einlass.nutzen",)),
    Kapitel("bezahlen", "Beitrag, Zahlung und Kundenkonto", EINLASS,
            ("einlass.abholung", "einlass.zahlung")),
    Kapitel("notizen", "Notizen und Notiz-Knöpfe", EINLASS, ("kunden.notizen",)),
    Kapitel("sonderaktionen-einlass", "Sonderaktionen am Einlass", EINLASS,
            ("einlass.sonderaktion",)),
    Kapitel("korrigieren", "Ein Versehen korrigieren", EINLASS,
            ("einlass.abholung", "einlass.zahlung", "einlass.sonderaktion")),
    Kapitel("ausnahme", "Ausnahme für heute erteilen", EINLASS, ("einlass.ausnahme",)),
    Kapitel("korrekturen", "Korrekturwünsche entscheiden", EINLASS, ("korrekturen.entscheiden",)),
    Kapitel("nachtragen", "Abholungen nachtragen (Papierliste)", EINLASS,
            ("einlass.nachtragen", "einlass.nachtragen_alle")),
    Kapitel("kasse", "Die Kasse", EINLASS, ("kasse.sehen",)),
    Kapitel("kunden-finden", "Kunden finden und ansehen", KUNDEN,
            ("kunden.liste", "kunden.ansehen")),
    Kapitel("kunden-bearbeiten", "Haushalte anlegen, bearbeiten und löschen", KUNDEN,
            ("kunden.bearbeiten", "kunden.loeschen")),
    Kapitel("ausgabestellen", "Ausgabestellen: Anschrift, Zeiten, Ansprechpartner", KUNDEN,
            ("kunden.liste",)),
    Kapitel("dokumente", "Dokumente zum Haushalt", KUNDEN, ("kunden.dokumente",)),
    Kapitel("ausweis", "Kundenausweise drucken", KUNDEN, ("kunden.ausweis",)),
    Kapitel("auskunft", "Auskunft, Historie und Zugriffsprotokoll", KUNDEN,
            ("kunden.auskunft", "kunden.historie", "kunden.zugriffsprotokoll")),
    Kapitel("import", "Kundenstamm importieren", KUNDEN, ("kunden.importieren",)),
    Kapitel("datenimport", "Daten importieren: Excel und CSV zuordnen", VERWALTUNG,
            ("kunden.importieren", "einstellungen.listen", "mitarbeitende.verwalten",
             "adressen.importieren", "mitglieder.bearbeiten")),
    Kapitel("antraege", "Anträge bearbeiten", ANTRAEGE, ("antraege.sehen",)),
    Kapitel("aufnahme", "Einen Antrag in den Kundenstamm aufnehmen", ANTRAEGE,
            ("antraege.aufnehmen",)),
    Kapitel("sonderaktionen", "Sonderaktionen anlegen und auswerten", EINLASS,
            ("sonderaktionen.verwalten",)),
    Kapitel("adressbuch", "Adressbuch: Spender, Märkte, Partner", ADRESSEN, ("adressen.sehen",)),
    Kapitel("mitglieder", "Mitglieder und Beiträge", ADRESSEN,
            ("mitglieder.sehen", "einstellungen.mitglieder")),
    Kapitel("serienbriefe", "Serienbriefe und Serien-E-Mails", ADRESSEN,
            ("serienbriefe.erstellen",)),
    Kapitel("spenden", "Spenden erfassen", ADRESSEN, ("spenden.sehen", "spenden.erfassen")),
    Kapitel("zuwendungsbestaetigungen", "Zuwendungsbestätigungen (Spendenquittungen)", ADRESSEN,
            ("spenden.bestaetigen", "einstellungen.spenden")),
    Kapitel("statistik", "Statistik", VERWALTUNG, ("statistik.sehen",)),
    Kapitel("arbeitszeit", "Meine Arbeitszeit (Stempeln)", TEAM),
    Kapitel("mitarbeitende", "Ehrenamtliche und Angestellte verwalten", TEAM,
            ("mitarbeitende.verwalten",)),
    Kapitel("personal", "Verträge & Zeiten: Verträge, Urlaub, Stunden", TEAM, ("personal.sehen",)),
    Kapitel("rollen", "Rollen und Rechte", VERWALTUNG, ("einstellungen.rollen",)),
    Kapitel("einstellungen", "Einstellungen der Tafel", VERWALTUNG,
            ("einstellungen.tafel", "einstellungen.mail", "einstellungen.kundenstamm",
             "einstellungen.listen", "einstellungen.ausweis", "einstellungen.ausgabe",
             "einstellungen.antraege", "einstellungen.personal", "einstellungen.arbeitszeit")),
    Kapitel("sicherungen", "Sicherungen: jetzt sichern, Aufträge und externe Ziele", VERWALTUNG,
            ("system.sicherung", "system.status")),
    Kapitel("datensicherung", "Datensicherung: exportieren und zurücklesen", VERWALTUNG,
            ("daten.exportieren", "daten.importieren")),
    Kapitel("protokoll", "Änderungsprotokoll", VERWALTUNG, ("protokoll.sehen",)),
    Kapitel("update", "Update: neue Version einspielen", VERWALTUNG, ("system.update",)),
    Kapitel("produktivstart", "Produktivstart: Testdaten löschen und mit Echtdaten starten",
            VERWALTUNG, ("system.produktivstart",)),
    Kapitel("betrieb", "Betrieb auf dem Server", VERWALTUNG, ("system.status",)),
]  # fmt: skip


MODULE = "Zusätzliche Module"


def _modul_kapitel() -> dict[str, list[Kapitel]]:
    """Kapitel der zuschaltbaren Module (ADR 0049) je Modul; Vorlagen liegen in der App."""
    from apps.core import module

    return {m.kennung: [Kapitel(k, titel, MODULE, rechte) for k, titel, rechte in m.kapitel]
            for m in module.alle()}  # fmt: skip


def alle_kapitel() -> list[Kapitel]:
    """Grundkapitel und die Kapitel aller installierten Module (auch ausgeschalteter)."""
    return KAPITEL + [k for liste in _modul_kapitel().values() for k in liste]


def sichtbar(benutzer) -> list[Kapitel]:
    from apps.core import module

    an = module.eingeschaltet()
    kapitel = KAPITEL + [k for kennung, liste in _modul_kapitel().items() if kennung in an
                         for k in liste]  # fmt: skip
    return [k for k in kapitel if not k.rechte or rollen.hat_recht(benutzer, *k.rechte)]


def gegliedert(kapitel: list[Kapitel]) -> list[tuple[str, list[Kapitel]]]:
    teile: dict[str, list[Kapitel]] = {}
    for k in kapitel:
        teile.setdefault(k.teil, []).append(k)
    return list(teile.items())


# Welches Hilfe-Kapitel passt zu welcher Programmseite (für das „?“ oben rechts auf jeder Seite)?
# Zuerst die genaue Adresse „Namespace:Name“, sonst das Standardkapitel der App, sonst – bei einem
# zuschaltbaren Modul – dessen erstes Kapitel. Bleibt es leer, führt das „?“ zur Handbuch-Übersicht.
# Eine unbekannte Kennung ist harmlos: der Anker fehlt dann nur, die Hilfe öffnet ganz oben.
_SEITE = {
    "ausgabe:empfang": "einlass",
    "ausgabe:kasse": "kasse",
    "ausgabe:nachtragen": "nachtragen",
    "ausgabe:korrekturen": "korrekturen",
    "ausgabe:sonderaktionen": "sonderaktionen",
    "ausgabe:sonderaktion": "sonderaktionen",
    "ausgabe:sonderaktion_neu": "sonderaktionen",
    "ausgabe:einstellungen": "einstellungen",
    "kunden:uebersicht": "kunden-finden",
    "kunden:haushalt": "kunden-finden",
    "kunden:verlaengern": "kunden-finden",
    "kunden:nachrichten": "notizen",
    "kunden:haushalt_neu": "kunden-bearbeiten",
    "kunden:bearbeiten": "kunden-bearbeiten",
    "kunden:ausgabestellen": "ausgabestellen",
    "kunden:ausweis_gestalten": "ausweis",
    "kunden:zugriffe": "auskunft",
    "kunden:einstellungen": "einstellungen",
    "antraege:liste": "antraege",
    "antraege:aufnahme": "aufnahme",
    "antraege:einstellungen": "einstellungen",
    "adressen:liste": "adressbuch",
    "mitglieder:liste": "mitglieder",
    "mitglieder:einstellungen": "mitglieder",
    "spenden:liste": "spenden",
    "spenden:bestaetigungen": "zuwendungsbestaetigungen",
    "spenden:einstellungen": "zuwendungsbestaetigungen",
    "serienbriefe:erstellen": "serienbriefe",
    "serienbriefe:vorlagen": "serienbriefe",
    "statistik:uebersicht": "statistik",
    "statistik:verband": "statistik",
    "datenimport:start": "datenimport",
    "konten:mitarbeitende": "mitarbeitende",
    "konten:rollen": "rollen",
    "konten:stellen": "einstellungen",
    "konten:personal_einstellungen": "einstellungen",
    "konten:anmelde_einstellungen": "einstellungen",
    "konten:mein_konto": "erste-schritte",
    "personal:liste": "personal",
    "personal:meine_arbeitszeit": "arbeitszeit",
    "personal:arbeitszeit_einstellungen": "einstellungen",
    "core:start": "erste-schritte",
    "core:suche": "suche",
    "core:einstellungen": "einstellungen",
    "core:rechtstexte": "einstellungen",
    "core:mail_einstellungen": "einstellungen",
    "core:protokoll": "protokoll",
    "core:papierkorb": "papierkorb",
    "core:sicherungen": "sicherungen",
    "core:datensicherung": "datensicherung",
    "core:update": "update",
    "core:produktivstart": "produktivstart",
    "core:verzeichnis": "betrieb",
}
_APP = {
    "ausgabe": "einlass",
    "kunden": "kunden-finden",
    "antraege": "antraege",
    "adressen": "adressbuch",
    "mitglieder": "mitglieder",
    "spenden": "spenden",
    "serienbriefe": "serienbriefe",
    "statistik": "statistik",
    "datenimport": "datenimport",
    "personal": "personal",
}


def kennung_fuer(view_name: str, app_name: str = "") -> str:
    """Kapitel-Kennung für die aktuelle Seite (``Namespace:Name``); leer = Handbuch-Übersicht."""
    if view_name in _SEITE:
        return _SEITE[view_name]
    if app_name in _APP:
        return _APP[app_name]
    # Zuschaltbares Modul: sein erstes Kapitel (Modul-Kennung = URL-Namespace der App).
    kapitel = _modul_kapitel().get(app_name)
    return kapitel[0].kennung if kapitel else ""
