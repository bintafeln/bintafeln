"""Beschreibung des Moduls Fahrdienst für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Aushangseite, Modul


def menue(eintrag):
    return [
        ("Dienstpläne/Fahrdienst", [
            ("fahrdienst.sehen", eintrag("Fahrerplan", "fahrdienst:plan", genau=True)),
            ("fahrdienst.sehen", eintrag("Meine Einsätze", "fahrdienst:meine")),
        ]),
        ("Einstellungen/Dienstpläne", [
            ("fahrdienst.planen", eintrag("Fahrdienst: Touren und Springer",
                                          "fahrdienst:einstellungen")),
        ]),
    ]  # fmt: skip


def fristen():
    from apps.fahrdienst.plan import fristen_anwenden

    fristen_anwenden()


def auskunft_mitarbeiter(benutzer, pdf):
    from apps.core import ausfall as ausfallregeln
    from apps.fahrdienst.models import Ausfall, Besetzung, Ersatz, Springer, platz_name

    feste = Besetzung.objects.filter(benutzer=benutzer).select_related("tour")
    ausfaelle = Ausfall.objects.filter(benutzer=benutzer)
    ersatz = Ersatz.objects.filter(benutzer=benutzer).select_related("tour")
    springer = Springer.objects.filter(benutzer=benutzer).first()
    if not (feste or ausfaelle or ersatz or springer):
        return
    pdf.ueberschrift("Fahrdienst")
    if springer:
        pdf.absatz(f"Springer{f' ({springer.wochentage})' if springer.wochentage else ''}.")
    pdf.tabelle(["Feste Besetzung", "Wochentag", "Platz"],
                [[b.tour.name, b.wochentag, platz_name(b.platz)] for b in feste],
                breiten=[0.5, 0.25, 0.25])  # fmt: skip
    pdf.tabelle(["Ausfall von", "bis", "Grund", "Anmerkung"],
                [[f"{a.von:%d.%m.%Y}", f"{a.bis:%d.%m.%Y}", a.get_grund_display(),
              " · ".join(filter(None, [a.anmerkung, ausfallregeln.gesund_text(a)]))]
                 for a in ausfaelle], breiten=[0.2, 0.2, 0.2, 0.4])  # fmt: skip
    pdf.tabelle(["Eingesprungen am", "Tour", "Platz"],
                [[f"{e.datum:%d.%m.%Y}", e.tour.name, platz_name(e.platz)] for e in ersatz],
                breiten=[0.3, 0.4, 0.3])  # fmt: skip


def aushang():
    from apps.fahrdienst import aushang as seiten

    return [
        Aushangseite(
            "fahrdienst",
            "Fahrerplan",
            "fahrdienst.planen",
            seiten.auswahl,
            seiten.folien,
            platz=seiten.platz,
            aendern=seiten.aendern,
        )
    ]


MODUL = Modul(
    kennung="fahrdienst",
    titel="Fahrdienst",
    beschreibung="Fahrerplan mit Touren, fester Besetzung und Springern; Ausfälle melden, Ersatz "
    "eintragen, Benachrichtigung per E-Mail",
    app_label="fahrdienst",
    pfade=("/fahrdienst/",),
    rechte=(
        ("fahrdienst.sehen", "Fahrerplan und eigene Einsätze sehen",
         "Ausfall selbst melden, wenn in den Einstellungen des Fahrdienstes erlaubt."),
        ("fahrdienst.planen", "Fahrdienst planen: Ersatz eintragen, Ausfälle, Touren, Springer",
         "Bekommt Ausfälle per E-Mail, wenn in den Einstellungen niemand gewählt ist."),
    ),
    vorgaben={"Büro": ("fahrdienst.sehen", "fahrdienst.planen"),
              "Fahrer": ("fahrdienst.sehen",), "Beifahrer": ("fahrdienst.sehen",)},
    kapitel=(("fahrdienst", "Fahrdienst: Fahrerplan, Ausfälle und Ersatz",
              ("fahrdienst.sehen", "fahrdienst.planen")),),
    menue=menue,
    fristen=fristen,
    auskunft_mitarbeiter=auskunft_mitarbeiter,
    sicherung_bereich="mitarbeitende",
    aushang=aushang,
)  # fmt: skip
