"""Beschreibung des Moduls Warteliste für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Warteliste", [
            ("warteliste.sehen", eintrag("Warteliste", "warteliste:liste", genau=True)),
            ("warteliste.sehen", eintrag("Termine", "warteliste:termine")),
            ("warteliste.bearbeiten", eintrag("Abgleich mit Kundenstamm", "warteliste:abgleich")),
            ("warteliste.bearbeiten", eintrag("Doppelte Anträge", "warteliste:dubletten")),
            ("warteliste.sehen", eintrag("Streichungsliste", "warteliste:streichungsliste")),
        ]),
        ("Einstellungen/Kunden", [
            ("einstellungen.warteliste",
             eintrag("Warteliste und Einladungen", "warteliste:einstellungen")),
        ]),
    ]  # fmt: skip


def fristen():
    from apps.warteliste import ablauf

    ablauf.automatik()


def auskunft_antrag(antrag, pdf):
    from apps.warteliste import ablauf

    ablauf.auskunft(antrag, pdf)


MODUL = Modul(
    kennung="warteliste",
    titel="Warteliste",
    beschreibung="Anträge zu Terminen einladen: Wartestatus, Einladungen, Absagen, Streichungen",
    app_label="warteliste",
    pfade=("/warteliste/",),
    rechte=(
        ("warteliste.sehen", "Warteliste, Termine, Druckliste und Streichungsliste ansehen", ""),
        ("warteliste.bearbeiten", "Einladen, absagen, Status setzen, Termine anlegen, "
         "Dubletten und Abgleich mit dem Kundenstamm", "Verschickt Mails an Antragsteller."),
        ("einstellungen.warteliste", "Warteliste einstellen: Mailtexte, Fristen, Sperrzeit", ""),
    ),
    vorgaben={"Büro": ("warteliste.sehen", "warteliste.bearbeiten")},
    kapitel=(
        ("warteliste", "Warteliste: einladen, Termine, Streichungen",
         ("warteliste.sehen", "einstellungen.warteliste")),
    ),
    menue=menue,
    fristen=fristen,
    auskunft_antrag=auskunft_antrag,
    sicherung_bereich="antraege",
)  # fmt: skip
