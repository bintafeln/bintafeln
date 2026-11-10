"""Beschreibung des Moduls „Bexat-Import“ für den Modulrahmen (ADR 0049, ADR 0100)."""

from django.urls import reverse

from apps.core.module import Modul
from apps.konten import rollen


def datenimport(request):
    """Die Bexat-Übernahmen stehen auf der Seite „Daten importieren“ (kein eigener Menüpunkt)."""
    if not rollen.hat_recht(request.user, "kunden.importieren"):
        return []
    return [
        {"titel": "Aus Bexat übernehmen (tafelarbeit.de)", "url": reverse("bexat:start"),
         "beschreibung": "Die Exportdatei des Bexat-Tafelprogramms (.xlsx) einlesen: Kundenstamm "
         "mit Abgleich, Anträge, Mitarbeitende und Besuche."},
        {"titel": "Besuche & Konto nachtragen (tafelarbeit.de)",
         "url": reverse("bexat:besuche_konto"),
         "beschreibung": "Tagesliste oder Kontostand-Liste einlesen: Besuche nachtragen und die "
         "Kontostände (Guthaben) auf den Stand aus tafelarbeit.de setzen."},
        {"titel": "Bexat-Zuordnungen", "url": reverse("bexat:einstellungen"),
         "beschreibung": "Ausgabestellen und Einkommensarten, die Bexat nur als Nummer kennt, "
         "den Namen zuordnen."},
    ]  # fmt: skip


MODUL = Modul(
    kennung="bexat",
    titel="Bexat-Import",
    beschreibung="Daten aus dem Bexat-Tafelprogramm (tafelarbeit.de) übernehmen: Die Exportdatei "
    "wird in das Importformat umgewandelt und geht in den normalen Import mit Abgleich. Zu finden "
    "unter „Daten importieren“.",
    app_label="bexat",
    pfade=("/bexat/",),
    kapitel=(("bexat", "Aus Bexat übernehmen", ("kunden.importieren",)),),
    datenimport=datenimport,
    sicherung_bereich="einstellungen",
)
