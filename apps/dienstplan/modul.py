"""Beschreibung des Moduls Dienstplan für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Ausgabestelle", [
            ("dienstplan.sehen", eintrag("Dienstplan", "dienstplan:plan", genau=True)),
            ("dienstplan.sehen", eintrag("Meine Dienste", "dienstplan:meine")),
        ]),
        ("Einstellungen/Mitarbeitende", [
            ("dienstplan.planen", eintrag("Dienstplan: Aufgaben und Helfer",
                                          "dienstplan:einstellungen")),
        ]),
    ]  # fmt: skip


def fristen():
    from apps.dienstplan.plan import fristen_anwenden

    fristen_anwenden()


def auskunft_mitarbeiter(benutzer, pdf):
    from apps.dienstplan.models import Ausfall, Besetzung, Ersatz, Helfer

    h = Helfer.objects.filter(benutzer=benutzer).first()
    if h is None:
        return
    pdf.ueberschrift("Dienstplan der Ausgabe")
    pdf.absatz(f"Helfer: {h.anzeige}{', Telefon ' + h.telefon if h.telefon else ''}"
               f"{', E-Mail ' + h.email if h.email else ''}.")  # fmt: skip
    feste = Besetzung.objects.filter(helfer=h).select_related("aufgabe__stelle__ausgabestelle")
    pdf.tabelle(["Feste Besetzung", "Ausgabestelle", "Wochentag"],
                [[str(b.aufgabe), str(b.aufgabe.stelle), b.aufgabe.wochentag] for b in feste],
                breiten=[0.4, 0.4, 0.2])  # fmt: skip
    pdf.tabelle(
        ["Ausfall von", "bis", "Grund", "Anmerkung"],
        [
            [f"{a.von:%d.%m.%Y}", f"{a.bis:%d.%m.%Y}", a.get_grund_display(), a.anmerkung]
            for a in Ausfall.objects.filter(helfer=h)
        ],
        breiten=[0.2, 0.2, 0.2, 0.4],
    )
    pdf.tabelle(["Eingesprungen am", "Aufgabe"],
                [[f"{e.datum:%d.%m.%Y}", str(e.aufgabe)]
                 for e in Ersatz.objects.filter(helfer=h).select_related("aufgabe")],
                breiten=[0.3, 0.7])  # fmt: skip


MODUL = Modul(
    kennung="dienstplan",
    titel="Dienstplan der Ausgabe",
    beschreibung="Dienstplan je Ausgabestelle und Ausgabetag: Aufgaben, feste Besetzung, Ausfälle "
    "und Ersatz, Teamleitung wird benachrichtigt, PDF zum Aushängen",
    app_label="dienstplan",
    pfade=("/dienstplan/",),
    rechte=(
        ("dienstplan.sehen", "Dienstplan und eigene Dienste sehen",
         "Ausfall selbst melden, wenn in den Einstellungen des Dienstplans erlaubt."),
        ("dienstplan.planen", "Dienstplan planen: Ersatz, Ausfälle, Aufgaben, Helfer",
         "Bekommt Ausfälle per E-Mail, wenn für den Tag keine Teamleitung eingetragen ist."),
    ),
    vorgaben={"Büro": ("dienstplan.sehen", "dienstplan.planen"), "Ausgabe": ("dienstplan.sehen",)},
    kapitel=(("dienstplan", "Dienstplan der Ausgabe", ("dienstplan.sehen", "dienstplan.planen")),),
    menue=menue,
    fristen=fristen,
    auskunft_mitarbeiter=auskunft_mitarbeiter,
    sicherung_bereich="mitarbeitende",
)  # fmt: skip
