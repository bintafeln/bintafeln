"""Beschreibung des Moduls Aufruf für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def einlass(haushalt, heute, stelle):
    from apps.aufruf import ablauf

    return ablauf.einlass(haushalt, heute, stelle)


def menue(eintrag):
    return [
        ("Kundennummernanzeige", [
            ("aufruf.steuern", eintrag("Kundennummernanzeige", "aufruf:start", extern=True)),
        ]),
        ("Einstellungen/Ausgabe", [
            ("einstellungen.aufruf", eintrag("Aufruf, Monitor und Kiosk", "aufruf:einstellungen")),
        ]),
    ]  # fmt: skip


MODUL = Modul(
    kennung="aufruf",
    titel="Aufruf",
    beschreibung="Kundennummern der Reihe nach aufrufen: Monitor, Handy-Steuerung, Kiosk",
    app_label="aufruf",
    pfade=("/aufruf/",),
    rechte=(
        ("aufruf.steuern", "Kunden aufrufen (Steuerung, Handy), zu spät Gekommene einsortieren",
         "Sieht nur Kundennummern, keine Namen."),
        ("einstellungen.aufruf", "Aufruf einstellen: Monitor, Infos, Anzeige-Links", ""),
    ),
    vorgaben={"Büro": ("aufruf.steuern",), "Ausgabe": ("aufruf.steuern",)},
    kapitel=(
        ("aufruf", "Aufruf: Kundennummern aufrufen, Monitor und Kiosk",
         ("aufruf.steuern", "einstellungen.aufruf")),
    ),
    menue=menue,
    einlass=einlass,
    seitenleiste="aufruf/_leiste_platz.html",
    sicherung_bereich="kunden",
    sicherung_ausgenommen=("aufruf.aufruftag",),
)  # fmt: skip
