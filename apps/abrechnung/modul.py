"""Beschreibung des Moduls Abrechnung für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Abrechnung", [
            ("abrechnung.fuehren", eintrag("Abrechnung", "abrechnung:uebersicht")),
            ("abrechnung.pruefen", eintrag("Abrechnung", "abrechnung:uebersicht")),
        ]),
        ("Einstellungen/Ausgabe", [
            ("abrechnung.pruefen", eintrag("Abrechnung", "abrechnung:einstellungen")),
        ]),
    ]  # fmt: skip


def fristen():
    from apps.abrechnung import ablauf

    ablauf.fristen_anwenden()


MODUL = Modul(
    kennung="abrechnung",
    titel="Abrechnung",
    beschreibung="Monatsabrechnung je Ausgabestelle: Einnahmen aus der Kasse, eigene Ausgaben "
    "mit Foto der Quittung, Prüfung im Büro",
    app_label="abrechnung",
    pfade=("/abrechnung/",),
    rechte=(
        ("abrechnung.fuehren", "Abrechnung der eigenen Ausgabestelle führen",
         "Ausgaben mit Quittung eintragen und die Monatsabrechnung einreichen; nur für die "
         "zugeordneten Ausgabestellen."),
        ("abrechnung.pruefen", "Abrechnungen aller Ausgabestellen prüfen",
         "Bestätigen, zurückgeben, Quittungen herunterladen und Einstellungen der Abrechnung."),
    ),
    vorgaben={"Ausgabe": ("abrechnung.fuehren",),
              "Büro": ("abrechnung.fuehren", "abrechnung.pruefen")},
    kapitel=(("abrechnung", "Abrechnung der Ausgabestellen",
              ("abrechnung.fuehren", "abrechnung.pruefen")),),
    menue=menue,
    fristen=fristen,
    sicherung_bereich="kunden",
)  # fmt: skip
