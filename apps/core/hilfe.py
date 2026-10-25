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
TEAM = "Mitarbeitende und Personal"
VERWALTUNG = "Einstellungen und Verwaltung"

KAPITEL = [
    Kapitel("erste-schritte", "Erste Schritte: Anmelden, Menü, Mein Konto", GRUNDLAGEN),
    Kapitel("suche", "Suchen: Kunden, Notizen, Anmerkungen und mehr", GRUNDLAGEN),
    Kapitel("zwei-faktor", "Zwei-Faktor-Anmeldung und Passwort", GRUNDLAGEN),
    Kapitel("datenschutz", "Datenschutz im Alltag", GRUNDLAGEN),
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
    Kapitel("mitarbeitende", "Mitarbeitende verwalten", TEAM, ("mitarbeitende.verwalten",)),
    Kapitel("personal", "Personal: Verträge, Urlaub, Stunden", TEAM, ("personal.sehen",)),
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
    Kapitel("betrieb", "Betrieb auf dem Server", VERWALTUNG, ("system.status",)),
]  # fmt: skip


def sichtbar(benutzer) -> list[Kapitel]:
    return [k for k in KAPITEL if not k.rechte or rollen.hat_recht(benutzer, *k.rechte)]


def gegliedert(kapitel: list[Kapitel]) -> list[tuple[str, list[Kapitel]]]:
    teile: dict[str, list[Kapitel]] = {}
    for k in kapitel:
        teile.setdefault(k.teil, []).append(k)
    return list(teile.items())
