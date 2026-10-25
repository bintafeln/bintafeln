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


def suchen(benutzer, begriff, grenze):
    from django.db.models import Q
    from django.urls import reverse

    from apps.konten import rollen
    from apps.warteliste.models import Termin

    if not rollen.hat_recht(benutzer, "warteliste.sehen"):
        return []
    termine = Termin.objects.filter(Q(ort__icontains=begriff) | Q(anmerkung__icontains=begriff))
    return [(f"Termin {t}", reverse("warteliste:termin", args=[t.pk]), "Warteliste")
            for t in termine[: grenze + 1]]  # fmt: skip


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
    suchen=suchen,
    sicherung_bereich="antraege",
)  # fmt: skip
