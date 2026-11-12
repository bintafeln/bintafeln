"""Beschreibung des Moduls für den Modulrahmen (ADR 0049, ADR 0126). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Verein/Spenden", [
            ("vereinsportal.nutzen", eintrag("Aus dem Vereinsportal einlesen",
                                             "vereinsportal:start", genau=True)),
            ("vereinsportal.nutzen", eintrag("Abruf aus dem Vereinsportal",
                                             "vereinsportal:abruf")),
        ]),
        ("Einstellungen/Verein", [
            ("vereinsportal.nutzen", eintrag("Vereinsportal", "vereinsportal:einstellungen")),
        ]),
    ]  # fmt: skip


MODUL = Modul(
    kennung="vereinsportal",
    titel="Spendenbelege aus dem Vereinsportal",
    beschreibung="Für Tafeln, die ihre Spendenbescheinigungen im Vereinsportal ausstellen: "
    "Finanzexport und die Liste der Spender mit E-Mail einlesen (von Hand oder automatisch). Die "
    "Spenden kommen in die Spendenliste, die Spender ins Adressbuch; bintafeln stellt für sie "
    "keine zweite Bestätigung aus, erstellt aber Sammelbestätigungen für Mehrfachspender.",
    app_label="vereinsportal",
    pfade=("/vereinsportal/",),
    rechte=(
        ("vereinsportal.nutzen", "Spenden aus dem Vereinsportal einlesen",
         "Finanzexport und Spenderliste einlesen (von Hand oder mit dem automatischen Abruf) "
         "und die Einstellungen dazu ändern. Dabei entstehen Spenden und Adressen."),
    ),
    vorgaben={"Büro": ("vereinsportal.nutzen",)},
    kapitel=(("vereinsportal", "Spendenbelege aus dem Vereinsportal",
              ("vereinsportal.nutzen",)),),
    menue=menue,
    sicherung_bereich="adressen",
)  # fmt: skip
