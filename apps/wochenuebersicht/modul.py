"""Beschreibung des Moduls Wochenübersicht für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Wochenübersicht", [
            ("wochenuebersicht.sehen", eintrag("Soll und Ist je Tag", "wochenuebersicht:uebersicht",
                                               genau=True)),
            ("wochenuebersicht.bearbeiten",
             eintrag("Selbstabholer", "wochenuebersicht:selbstabholer")),
            ("wochenuebersicht.bearbeiten",
             eintrag("Reihenfolge", "wochenuebersicht:reihenfolge")),
        ]),
    ]  # fmt: skip


MODUL = Modul(
    kennung="wochenuebersicht",
    titel="Wochenübersicht",
    beschreibung="Soll und Ist der Ausgabestellen je Wochentag mit Selbstabholern, Druck als PDF",
    app_label="wochenuebersicht",
    pfade=("/wochenuebersicht/",),
    rechte=(
        ("wochenuebersicht.sehen", "Wochenübersicht der Ausgabestellen ansehen und drucken",
         "Zeigt nur Summen, keine Personendaten."),
        ("wochenuebersicht.bearbeiten", "Selbstabholer und Reihenfolge der Wochenübersicht pflegen",
         ""),
    ),
    vorgaben={"Büro": ("wochenuebersicht.sehen", "wochenuebersicht.bearbeiten")},
    kapitel=(
        ("wochenuebersicht", "Wochenübersicht der Ausgabestellen", ("wochenuebersicht.sehen",)),
    ),
    menue=menue,
)  # fmt: skip
