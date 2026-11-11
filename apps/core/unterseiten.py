"""Seiten, die nur über einen Knopf erreichbar sind – für die Suche (ADR 0121).

Die Suche oben im Seitenkopf findet Menüpunkte. Seiten, die nicht im Menü stehen, sondern hinter
einem Knopf auf einer anderen Seite liegen (z. B. „Online-Zugänge freigeben“ bei den
Mitarbeitenden), stehen hier, damit die Suche auch sie zeigt – mit dem Weg dorthin.

Neue Seiten mit eigenem Knopf hier eintragen; ``tests/test_suche.py`` prüft, dass jede Adresse
existiert und nur mit dem genannten Recht erreichbar ist.
"""

from dataclasses import dataclass

from django.urls import NoReverseMatch, reverse


@dataclass(frozen=True)
class Unterseite:
    titel: str
    url_name: str
    rechte: tuple[str, ...]  # eines davon genügt; leer = alle Angemeldeten
    weg: str  # wo der Knopf steht, z. B. „Verein › Team › Mitarbeitende“
    stichworte: str = ""  # weitere Suchwörter
    modul: str = ""  # nur wenn dieses Modul eingeschaltet ist


UNTERSEITEN = [
    Unterseite(
        "Online-Zugänge freigeben",
        "konten:zugaenge_freigeben",
        ("mitarbeitende.verwalten",),
        "Verein › Team › Mitarbeitende",
        "Onlinezugang Zugang freischalten Startpasswort Anmeldung erlauben",
    ),
    Unterseite(
        "Archiv der Mitarbeitenden",
        "konten:mitarbeitende_archiv",
        ("mitarbeitende.verwalten",),
        "Verein › Team › Mitarbeitende",
        "gesperrte ehemalige ausgeschiedene Konten",
    ),
    Unterseite(
        "Neue Mitarbeiterin / neuer Mitarbeiter",
        "konten:mitarbeiter_neu",
        ("mitarbeitende.verwalten",),
        "Verein › Team › Mitarbeitende",
        "Mitarbeiter anlegen Konto anlegen Helfer hinzufügen",
    ),
    Unterseite(
        "Mein Konto",
        "konten:mein_konto",
        (),
        "oben rechts: Ihr Name",
        "eigene Daten vertraute Geräte",
    ),
    Unterseite(
        "Passwort ändern", "konten:passwort_aendern", (), "Mein Konto", "Kennwort neues Passwort"
    ),
    Unterseite(
        "Benachrichtigungen einstellen",
        "konten:benachrichtigungen",
        (),
        "Mein Konto",
        "Mail Häufigkeit Meldungen abbestellen",
    ),
    Unterseite(
        "Ausweisprüfung der Anträge",
        "antraege:ausweis_pruefung_liste",
        ("antraege.bearbeiten",),
        "Anträge und Warteliste › Anträge",
        "Staatsangehörigkeit laut Ausweis Abweichung prüfen",
    ),
    Unterseite(
        "Anträge importieren",
        "antraege:antraege_importieren",
        ("antraege.bearbeiten",),
        "Anträge und Warteliste › Anträge",
        "CSV Anträge einlesen übernehmen",
    ),
    Unterseite(
        "Nachweise importieren",
        "antraege:nachweise_importieren",
        ("antraege.bearbeiten",),
        "Anträge und Warteliste › Anträge",
        "Nachweise Dateien einlesen hochladen",
    ),
    Unterseite(
        "Jahresbericht",
        "statistik:jahresbericht",
        ("statistik.sehen",),
        "Auswertungen › Statistik",
        "Bericht Jahr PDF Zahlen",
    ),
    Unterseite(
        "Sicherung: Fernablage",
        "core:sicherung_fernablage",
        ("system.sicherung",),
        "Einstellungen › Sicherungen",
        "Sicherungsziel SFTP entfernte Ablage Backup",
    ),
    Unterseite(
        "Gespeicherte Dateien",
        "core:dateien",
        ("einstellungen.tafel",),
        "Einstellungen › Speicher",
        "Speicherplatz Dateien Belegung",
    ),
    Unterseite(
        "Neue Ausgabestelle",
        "kunden:ausgabestelle_neu",
        ("einstellungen.listen",),
        "Einstellungen › Ausgabestellen",
        "Ausgabestelle anlegen hinzufügen",
    ),
    Unterseite(
        "Besuche & Konto nachtragen",
        "uebernahme:besuche_konto",
        ("kunden.importieren",),
        "Aus anderem Tafelprogramm übernehmen",
        "Kontostand Guthaben Abholungen Tagesliste Altprogramm einlesen",
        modul="uebernahme",
    ),
]


def fuer(benutzer_rechte, module_an) -> list[tuple[Unterseite, str]]:
    """Die Unterseiten, die das Konto öffnen darf, mit ihrer Adresse."""
    ergebnis = []
    for u in UNTERSEITEN:
        if u.modul and u.modul not in module_an:
            continue
        if u.rechte and not any(r in benutzer_rechte for r in u.rechte):
            continue
        try:
            ergebnis.append((u, reverse(u.url_name)))
        except NoReverseMatch:  # Modul nicht geladen
            continue
    return ergebnis
