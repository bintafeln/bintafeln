"""Produktivstart: beim Umstieg von Test-/Phantasiedaten auf Echtdaten die ausgewählten
Bewegungs- und Testdaten löschen, die Einrichtung aber behalten (ADR 0095).

Der Admin wählt je Bereich, was gelöscht wird (``GRUPPEN``). Erhalten bleiben in jedem Fall:
alle Einstellungen und Listen (Tafel, Ausgabestellen, Kundengruppen, Einkommensarten, Vorlagen,
Ausweis …), Rollen und Rechte sowie das Konto, das den Produktivstart auslöst.

Gelöscht wird nur, was in einem gewählten Bereich ausdrücklich aufgeführt ist – so kann ein
vergessenes Einrichtungs-Modell nie versehentlich gelöscht werden. Die Oberfläche sichert vorher
automatisch (siehe views_produktivstart).
"""

from auditlog.context import disable_auditlog
from django.apps import apps
from django.db import transaction
from django.db.models import ProtectedError

# Je Bereich: Schlüssel, Titel, Beschreibung, Modell-Labels. Reihenfolge der Modelle egal:
# gegenseitige Fremdschlüssel löst der Mehrfach-Durchlauf in durchfuehren() auf. Einrichtung,
# Rollen, Ausgabestellen, Kundengruppen, Vorlagen und Modul-Einstellungen stehen bewusst nirgends.
GRUPPEN = [
    (
        "kunden",
        "Kunden und Ausgabe",
        "Haushalte (Kundenstamm), Abholungen, Kundenkonto, Teilnahmen, Zugriffsprotokoll, Notizen, "
        "Dokumente, Historie",
        [
            "core.papierkorbeintrag",
            "kunden.haushalt",
            "kunden.person",
            "kunden.abholer",
            "kunden.sperre",
            "kunden.bemerkung",
            "kunden.notiz",
            "kunden.nachricht",
            "kunden.haushaltdokument",
            "kunden.haushaltereignis",
            "kunden.abholung",
            "kunden.ausnahme",
            "kunden.zugriff",
            "kunden.importlauf",
            "ausgabe.buchung",
            "ausgabe.teilnahme",
            "ausgabe.sonderaktionauswahl",
            "ausgabe.sonderaktion",
            "ausgabe.korrekturwunsch",
        ],
    ),
    (
        "antraege",
        "Anträge und Warteliste",
        "Anträge, Einladungen, Wartestände, Streichungen",
        [
            "antraege.antrag",
            "antraege.antragperson",
            "antraege.antraganhang",
            "antraege.antraganmerkung",
            "warteliste.termin",
            "warteliste.wartestand",
            "warteliste.einladung",
            "warteliste.streichung",
            "warteliste.dubletteignoriert",
            "warteliste.abgleichentscheidung",
        ],
    ),
    (
        "verein",
        "Spenden, Mitglieder, Adressbuch",
        "Spenden, Zuwendungsbestätigungen, Mitglieder, Adressen, Serienbrief-Versände",
        [
            "spenden.spende",
            "spenden.zuwendungsbestaetigung",
            "spenden.spendenbeleg",
            "mitglieder.mitglied",
            "adressen.adresse",
            "serienbriefe.versand",
        ],
    ),
    (
        "module",
        "Modul-Bewegungsdaten",
        "Aufruf-Handyzugänge, Wochenübersicht, Abrechnungen, Fahrdienst-/Dienstplan-Ausfälle, Tickets",
        [
            "aufruf.handycode",
            "aufruf.handyzugang",
            "wochenuebersicht.selbstabholernotiz",
            "wochenuebersicht.selbstabholerkontakt",
            "wochenuebersicht.selbstabholer",
            "abrechnung.posten",
            "abrechnung.monatsabrechnung",
            "fahrdienst.ersatz",
            "fahrdienst.ausfall",
            "dienstplan.ersatz",
            "dienstplan.ausfall",
            "tickets.anhang",
            "tickets.kommentar",
            "tickets.ticket",
        ],
    ),
    ("protokoll", "Änderungsprotokoll", "Wer hat wann was geändert", ["auditlog.logentry"]),
    (
        "konten",
        "Andere Konten und Personal",
        "Alle Konten außer Ihrem Admin-Konto – mit ihren Personaldaten (Verträge, Abwesenheiten, "
        "Stunden, Schulungen, Dokumente)",
        [
            "konten.stammdaten",
            "konten.schulung",
            "konten.dokument",
            "personal.arbeitsvertrag",
            "personal.abwesenheit",
            "personal.urlaubsjahr",
            "personal.stunden",
            "personal.zeitbuchung",
        ],
    ),
]
SCHLUESSEL = [g[0] for g in GRUPPEN]


class ProduktivstartFehler(RuntimeError):
    pass


def vorschau(admin) -> list[dict]:
    """Je Bereich Titel, Beschreibung und Zahl der Datensätze – für die Auswahlseite."""
    from apps.konten.models import Benutzer

    zeilen = []
    for key, titel, beschreibung, labels in GRUPPEN:
        zahl = sum(apps.get_model(label).objects.count() for label in labels)
        if key == "konten":
            zahl += Benutzer.objects.exclude(pk=admin.pk).count()
        zeilen.append({"key": key, "titel": titel, "beschreibung": beschreibung, "zahl": zahl})
    return zeilen


def durchfuehren(admin, gewaehlt) -> None:
    """Löscht die Daten der gewählten Bereiche; die Einrichtung bleibt. ``gewaehlt`` ist eine
    Menge von Bereichsschlüsseln (siehe ``SCHLUESSEL``). Läuft in einer Transaktion: Schlägt
    etwas fehl, wird nichts gelöscht.
    """
    gewaehlt = {g for g in gewaehlt if g in SCHLUESSEL}
    if not gewaehlt:
        raise ProduktivstartFehler("Bitte mindestens einen Bereich auswählen.")
    labels = [label for key, _, _, labels in GRUPPEN if key in gewaehlt for label in labels]
    with disable_auditlog(), transaction.atomic():
        from apps.konten.models import Benutzer

        rest = [apps.get_model(label) for label in labels]
        konten_offen = "konten" in gewaehlt
        while rest or konten_offen:
            fortschritt = False
            uebrig = []
            for modell in rest:
                try:
                    with transaction.atomic():  # Sicherungspunkt je Modell
                        modell._default_manager.all().delete()
                    fortschritt = True
                except ProtectedError:
                    uebrig.append(modell)  # schützt noch ein anderes Modell – später erneut
            if konten_offen:
                try:
                    with transaction.atomic():
                        Benutzer.objects.exclude(pk=admin.pk).delete()
                    konten_offen = False
                    fortschritt = True
                except ProtectedError:
                    pass
            if not fortschritt:
                namen = ", ".join(m._meta.label for m in uebrig) or "Konten"
                raise ProduktivstartFehler(
                    f"Diese Daten ließen sich nicht löschen, weil andere darauf verweisen: {namen}."
                    " Bitte die zugehörigen Bereiche zusätzlich auswählen."
                )
            rest = uebrig
