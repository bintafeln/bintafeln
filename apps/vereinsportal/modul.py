"""Beschreibung des Moduls für den Modulrahmen (ADR 0049, ADR 0126). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Verein/Spenden", [
            ("vereinsportal.nutzen", eintrag("Belege aus dem Vereinsportal",
                                             "vereinsportal:start", genau=True)),
        ]),
        ("Einstellungen/Verein", [
            ("vereinsportal.nutzen", eintrag("Vereinsportal", "vereinsportal:einstellungen")),
        ]),
    ]  # fmt: skip


def fristen():
    from apps.vereinsportal import auswertung

    auswertung.fristen_anwenden()


MODUL = Modul(
    kennung="vereinsportal",
    titel="Spendenbelege aus dem Vereinsportal",
    beschreibung="Für Tafeln, die ihre Spendenbescheinigungen im Vereinsportal ausstellen: "
    "Finanzexport und die Liste der Spender mit E-Mail einlesen und sehen, welche Einfach- und "
    "Mehrfachspender noch keine Bescheinigung bekommen haben. Eine Alternative zu den Spenden "
    "in bintafeln; beide lassen sich nebeneinander nutzen.",
    app_label="vereinsportal",
    pfade=("/vereinsportal/",),
    rechte=(
        ("vereinsportal.nutzen", "Spendenbelege aus dem Vereinsportal einlesen und auswerten",
         "Finanzexport und Spenderliste einlesen, Belege ansehen, Listen exportieren und die "
         "Einstellungen dazu ändern."),
    ),
    vorgaben={"Büro": ("vereinsportal.nutzen",)},
    kapitel=(("vereinsportal", "Spendenbelege aus dem Vereinsportal",
              ("vereinsportal.nutzen",)),),
    menue=menue,
    fristen=fristen,
    sicherung_bereich="adressen",
)  # fmt: skip
