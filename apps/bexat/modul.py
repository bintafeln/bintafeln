"""Beschreibung des Moduls „Bexat-Import“ für den Modulrahmen (ADR 0049, ADR 0100)."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Einstellungen/Systemsteuerung", [
            ("kunden.importieren", eintrag("Aus Bexat übernehmen", "bexat:start")),
            ("kunden.importieren", eintrag("Besuche & Konto nachtragen", "bexat:besuche_konto")),
            ("kunden.importieren", eintrag("Bexat-Zuordnungen", "bexat:einstellungen")),
        ]),
    ]  # fmt: skip


MODUL = Modul(
    kennung="bexat",
    titel="Bexat-Import",
    beschreibung="Daten aus dem Bexat-Tafelprogramm (tafelarbeit.de) übernehmen: Die Exportdatei "
    "wird in das Importformat umgewandelt und geht in den normalen Import mit Abgleich.",
    app_label="bexat",
    pfade=("/bexat/",),
    kapitel=(("bexat", "Aus Bexat übernehmen", ("kunden.importieren",)),),
    menue=menue,
    sicherung_bereich="einstellungen",
)
