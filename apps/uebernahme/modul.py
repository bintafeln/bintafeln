"""Modul „Übernahme aus einem anderen Programm“ für den Modulrahmen (ADR 0049, ADR 0100)."""

from django.urls import reverse

from apps.core.module import Modul
from apps.konten import rollen


def datenimport(request):
    """Die Übernahmen stehen auf der Seite „Daten importieren“ (kein eigener Menüpunkt)."""
    if not rollen.hat_recht(request.user, "kunden.importieren"):
        return []
    return [
        {"titel": "Aus anderem Tafelprogramm übernehmen", "url": reverse("uebernahme:start"),
         "beschreibung": "Die Exportdatei des bisherigen Tafelprogramms (.xlsx) einlesen: "
         "Kundenstamm mit Abgleich, Anträge, Mitarbeitende und Besuche."},
        {"titel": "Besuche & Konto nachtragen",
         "url": reverse("uebernahme:besuche_konto"),
         "beschreibung": "Tagesliste oder Kontostand-Liste einlesen: Besuche nachtragen und die "
         "Kontostände (Guthaben) auf den Stand aus dem bisherigen Programm setzen."},
        {"titel": "Zuordnungen für die Übernahme", "url": reverse("uebernahme:einstellungen"),
         "beschreibung": "Ausgabestellen und Einkommensarten, die im Export nur als Nummer stehen, "
         "den Namen zuordnen."},
    ]  # fmt: skip


MODUL = Modul(
    kennung="uebernahme",
    titel="Übernahme aus einem anderen Programm",
    beschreibung="Daten aus dem bisherigen Tafelprogramm übernehmen: Dessen Export als "
    "mehrblättrige Excel-Datei wird in das Importformat umgewandelt und geht in den normalen "
    "Import mit Abgleich. Zu finden unter „Daten importieren“; welche Blätter und Spalten die "
    "Datei braucht, steht im Handbuch.",
    app_label="uebernahme",
    pfade=("/uebernahme/",),
    kapitel=(
        ("uebernahme", "Aus einem anderen Tafelprogramm übernehmen", ("kunden.importieren",)),
    ),
    datenimport=datenimport,
    sicherung_bereich="einstellungen",
)
