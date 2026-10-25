"""Rechte von bintafeln (ADR 0033).

Jede Rolle (Django-Gruppe mit ``konten.Rolle``) bekommt eine Auswahl dieser Rechte. Ansichten
prüfen nur noch Rechte, nie Rollennamen. Die Rolle Admin hat immer alle Rechte.

Neue Rechte hier ergänzen: Code, Bereich, Bezeichnung; dazu in ``VORGABEN`` festlegen, welche
mitgelieferte Rolle es bekommt (gilt nur beim ersten Anlegen der Rolle; bestehende Rollen
erhalten neue Rechte über eine Datenmigration).
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Recht:
    code: str
    bereich: str
    bezeichnung: str
    hilfe: str = ""


EINLASS = "Einlass und Kasse"
KUNDEN = "Kunden"
ANTRAEGE = "Anträge"
STATISTIK = "Statistik und Daten"
TEAM = "Mitarbeitende und Personal"
EINSTELLUNGEN = "Einstellungen"

KATALOG = [
    # Einlass und Kasse
    Recht("einlass.nutzen", EINLASS, "Einlass öffnen und Kunden aufrufen (Ampel)"),
    Recht("einlass.abholung", EINLASS, "Abholungen buchen"),
    Recht("einlass.zahlung", EINLASS, "Zahlungen ohne Abholung buchen"),
    Recht("einlass.ausnahme", EINLASS, "Ausnahme für heute erteilen"),
    Recht("einlass.sonderaktion", EINLASS, "Teilnahme an Sonderaktionen eintragen"),
    Recht("einlass.zuruecknehmen", EINLASS,
          "Abholungen, Zahlungen und Sonderaktionen selbst zurücknehmen",
          "Auch an späteren Tagen. Ohne dieses Recht geht am Einlass nur ein Korrekturwunsch."),
    Recht("korrekturen.entscheiden", EINLASS, "Korrekturwünsche vom Einlass entscheiden",
          "Wer dieses Recht hat, bekommt neue Korrekturwünsche per Mail."),
    Recht("kasse.sehen", EINLASS, "Kasse und Kassenbericht ansehen"),
    Recht("kasse.einzelbuchungen", EINLASS, "In der Kasse Einzelbuchungen mit Kundennummer sehen"),
    Recht("konto.korrektur", EINLASS, "Kundenkonto korrigieren"),
    Recht("sonderaktionen.verwalten", EINLASS, "Sonderaktionen anlegen, ändern und auswerten"),
    # Kunden
    Recht("kunden.liste", KUNDEN, "Kundenliste und Suche"),
    Recht("kunden.alle_ausgabestellen", KUNDEN, "Kunden aller Ausgabestellen aufrufen",
          "Ohne dieses Recht sieht, wer einer Ausgabestelle zugeordnet ist, nur deren Kunden."),
    Recht("kunden.ansehen", KUNDEN, "Seite eines Haushalts ansehen (Grundangaben)",
          "Kundennummer, Personen, Haushaltsgröße, Ausgabestelle, Ausweis, aktive Sperren, "
          "letzte Abholungen, Notizen"),
    Recht("kunden.stammdaten", KUNDEN, "Status, Kunde seit, Einkommensart, Staatsangehörigkeit, "
          "Familienstand sehen"),
    Recht("kunden.kontakt", KUNDEN, "Anschrift, Telefon und E-Mail sehen"),
    Recht("kunden.besondere_kategorie", KUNDEN, "Angaben der besonderen Kategorie (Art. 9) sehen"),
    Recht("kunden.sperren_alle", KUNDEN, "Alle Sperren und Ausnahmen sehen (auch vergangene)"),
    Recht("kunden.abholungen_alle", KUNDEN, "Alle Abholungen mit Beitrag und Erfasser sehen"),
    Recht("kunden.konto", KUNDEN, "Kundenkonto und Buchungen sehen"),
    Recht("kunden.anmerkungen", KUNDEN, "Interne Anmerkungen sehen"),
    Recht("kunden.notizen", KUNDEN, "Notizen schreiben und eigene vom selben Tag löschen"),
    Recht("kunden.notizen_loeschen", KUNDEN, "Alle Notizen löschen"),
    Recht("kunden.dokumente", KUNDEN, "Dokumente ansehen"),
    Recht("kunden.dokumente_verwalten", KUNDEN, "Dokumente hochladen und löschen"),
    Recht("kunden.historie", KUNDEN, "Historie sehen"),
    Recht("kunden.ausweis", KUNDEN, "Kundenausweise drucken"),
    Recht("kunden.auskunft", KUNDEN, "Auskunft nach Art. 15 erstellen"),
    Recht("kunden.importieren", KUNDEN, "Kundenstamm importieren"),
    Recht("kunden.bearbeiten", KUNDEN, "Haushalte anlegen und bearbeiten"),
    Recht("kunden.loeschen", KUNDEN, "Haushalte löschen"),
    Recht("kunden.zugriffsprotokoll", KUNDEN, "Zugriffsprotokoll ansehen"),
    # Anträge
    Recht("antraege.sehen", ANTRAEGE, "Anträge, Anhänge und Auskunft ansehen, CSV-Export"),
    Recht("antraege.bearbeiten", ANTRAEGE, "Anträge bearbeiten, Status, Anmerkungen, Papierkorb"),
    Recht("antraege.aufnehmen", ANTRAEGE, "Anträge in den Kundenstamm aufnehmen"),
    Recht("antraege.loeschen", ANTRAEGE, "Anträge endgültig löschen"),
    # Statistik und Daten
    Recht("statistik.sehen", STATISTIK, "Statistik ansehen und als CSV herunterladen",
          "Nur Summen, keine Personendaten. Wer einer Ausgabestelle zugeordnet ist, sieht nur "
          "deren Zahlen."),
    Recht("daten.exportieren", STATISTIK, "Alle Daten exportieren (Datensicherung)",
          "Die Datei enthält sämtliche Personendaten, verschlüsselt mit einem Passwort."),
    Recht("daten.importieren", STATISTIK, "Daten aus einer Exportdatei zurücklesen",
          "Kann Daten überschreiben; „Vollständig ersetzen“ löscht alles andere."),
    # Mitarbeitende und Personal
    Recht("mitarbeitende.verwalten", TEAM, "Mitarbeitende anlegen, bearbeiten, sperren",
          "Rollen vergeben kann man nur, wenn man selbst alle Rechte der Rolle hat; "
          "Admin-Konten bearbeitet nur ein Admin."),
    Recht("personal.sehen", TEAM, "Personal: Verträge, Abwesenheiten, Stunden, Arbeitszeiten, "
          "vertrauliche Dokumente"),
    # Einstellungen
    Recht("einstellungen.tafel", EINSTELLUNGEN, "Tafel (Name, Farbe, Anschrift, Anmeldung)"),
    Recht("einstellungen.mail", EINSTELLUNGEN, "E-Mail-Versand"),
    Recht("einstellungen.kundenstamm", EINSTELLUNGEN, "Kundenstamm und Zusatzfelder"),
    Recht("einstellungen.listen", EINSTELLUNGEN, "Kundengruppen, Ausgabestellen, Einkommensarten, "
          "Notiz-Vorlagen, Dokumentarten, beitragsfreie Zeiträume"),
    Recht("einstellungen.ausweis", EINSTELLUNGEN, "Kundenausweis gestalten"),
    Recht("einstellungen.ausgabe", EINSTELLUNGEN, "Ausgabe, Ampel und Beiträge"),
    Recht("einstellungen.antraege", EINSTELLUNGEN, "Antragsformular und Texte"),
    Recht("einstellungen.personal", EINSTELLUNGEN, "Mitarbeitende und Dokumentkategorien"),
    Recht("einstellungen.arbeitszeit", EINSTELLUNGEN, "Arbeitszeit"),
    Recht("einstellungen.rollen", EINSTELLUNGEN, "Rollen und Rechte",
          "Nur Rechte, die man selbst hat, lassen sich weitergeben."),
    Recht("protokoll.sehen", EINSTELLUNGEN, "Änderungsprotokoll ansehen"),
    Recht("system.status", EINSTELLUNGEN, "Sicherungsstand und Version sehen"),
]  # fmt: skip

NACH_CODE = {r.code: r for r in KATALOG}
ALLE = frozenset(NACH_CODE)

_EINLASS = ["einlass.nutzen", "einlass.abholung", "einlass.zahlung", "einlass.sonderaktion",
            "kasse.sehen", "kunden.liste", "kunden.ansehen", "kunden.notizen"]  # fmt: skip

# Rechte der mitgelieferten Rollen: genau das Verhalten vor ADR 0033.
VORGABEN = {
    "Büro": _EINLASS + [
        "einlass.ausnahme", "kasse.einzelbuchungen", "konto.korrektur",
        "kunden.alle_ausgabestellen", "sonderaktionen.verwalten", "kunden.stammdaten",
        "kunden.kontakt",
        "kunden.besondere_kategorie", "kunden.sperren_alle", "kunden.abholungen_alle",
        "kunden.konto", "kunden.anmerkungen", "kunden.notizen_loeschen", "kunden.dokumente",
        "kunden.dokumente_verwalten", "kunden.historie", "kunden.ausweis", "kunden.auskunft",
        "kunden.importieren", "antraege.sehen", "antraege.bearbeiten", "antraege.aufnehmen",
        "statistik.sehen",
    ],
    "Ausgabe": list(_EINLASS),
    "Kiosk": [],
    "Fahrer": [],
    "Beifahrer": [],
    "Personal": ["personal.sehen", "einstellungen.arbeitszeit"],
}  # fmt: skip


def bereiche(codes=None) -> list[tuple[str, list[Recht]]]:
    """Katalog nach Bereich gruppiert, in fester Reihenfolge (für die Oberfläche)."""
    gruppen: dict[str, list[Recht]] = {}
    for r in KATALOG:
        if codes is None or r.code in codes:
            gruppen.setdefault(r.bereich, []).append(r)
    return list(gruppen.items())
