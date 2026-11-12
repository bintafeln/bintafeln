"""Beschreibung des Moduls für den Modulrahmen (ADR 0049, ADR 0131). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Kunden", [
            ("angebote.verwalten", eintrag("Angebote mit Anmeldung", "angebote:liste")),
        ]),
    ]  # fmt: skip


def einlass(haushalt, heute, stelle=None):
    from apps.angebote import ablauf

    return ablauf.einlass(haushalt, heute, stelle)


def fristen():
    from apps.angebote import ablauf

    ablauf.fristen_anwenden()


def auskunft_haushalt(haushalt, pdf):
    from django.utils import timezone

    from apps.angebote.models import Interesse

    eintraege = Interesse.objects.filter(
        kundennummer=haushalt.kundennummer).select_related("angebot")  # fmt: skip
    if not eintraege:
        return
    pdf.ueberschrift("Angebote mit Anmeldung")
    pdf.tabelle(
        ["Angebot", "Person", "Eingetragen am", "Stand"],
        [[str(e.angebot), e.name, f"{timezone.localtime(e.eingetragen_am):%d.%m.%Y}",
          e.get_stand_display()] for e in eintraege],
        breiten=[0.35, 0.3, 0.17, 0.18],
    )  # fmt: skip


MODUL = Modul(
    kennung="angebote",
    titel="Angebote mit Anmeldung",
    beschreibung="Für Angebote mit begrenzten Plätzen, z. B. einen Kochkurs: Am Einlass werden "
    "interessierte Kunden eingetragen, bis die Liste voll ist; das Büro vergibt die Plätze.",
    app_label="angebote",
    pfade=("/angebote/",),
    rechte=(
        ("angebote.verwalten", "Angebote anlegen, Interessierte sehen, Plätze vergeben",
         "Angebote mit Anmeldung pflegen, die Liste der Interessierten mit Telefon sehen und "
         "ausgeben, Plätze vergeben."),
        ("angebote.eintragen", "Am Einlass Interesse eintragen",
         "Am Einlass Personen eines Haushalts für ein Angebot eintragen und wieder austragen."),
    ),
    vorgaben={"Büro": ("angebote.verwalten", "angebote.eintragen"),
              "Ausgabe": ("angebote.eintragen",)},
    kapitel=(("angebote", "Angebote mit Anmeldung",
              ("angebote.verwalten", "angebote.eintragen")),),
    menue=menue,
    einlass=einlass,
    fristen=fristen,
    auskunft_haushalt=auskunft_haushalt,
    sicherung_bereich="kunden",
)  # fmt: skip
