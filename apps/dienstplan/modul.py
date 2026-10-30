"""Beschreibung des Moduls Dienstplan für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.benachrichtigung import Art
from apps.core.module import Aushangseite, Modul


def menue(eintrag):
    return [
        ("Dienstpläne/Ausgabe", [
            ("dienstplan.sehen", eintrag("Dienstplan der Ausgabe", "dienstplan:plan", genau=True)),
            ("dienstplan.sehen", eintrag("Meine Dienste", "dienstplan:meine")),
        ]),
        ("Einstellungen/Dienstpläne", [
            ("dienstplan.planen", eintrag("Ausgabe: Aufgaben und Helfer",
                                          "dienstplan:einstellungen")),
        ]),
    ]  # fmt: skip


def fristen():
    from apps.dienstplan.plan import fristen_anwenden

    fristen_anwenden()


def auskunft_mitarbeiter(benutzer, pdf):
    from apps.core import ausfall as ausfallregeln
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
            [
                f"{a.von:%d.%m.%Y}",
                f"{a.bis:%d.%m.%Y}",
                a.get_grund_display(),
                " · ".join(filter(None, [a.anmerkung, ausfallregeln.gesund_text(a)])),
            ]
            for a in Ausfall.objects.filter(helfer=h)
        ],
        breiten=[0.2, 0.2, 0.2, 0.4],
    )
    pdf.tabelle(["Eingesprungen am", "Aufgabe"],
                [[f"{e.datum:%d.%m.%Y}", str(e.aufgabe)]
                 for e in Ersatz.objects.filter(helfer=h).select_related("aufgabe")],
                breiten=[0.3, 0.7])  # fmt: skip


def aushang():
    from apps.dienstplan import aushang as seiten

    return [
        Aushangseite(
            "dienstplan",
            "Dienstplan einer Ausgabestelle",
            "dienstplan.planen",
            seiten.auswahl,
            seiten.folien,
            platz=seiten.platz,
            aendern=seiten.aendern,
        )
    ]


def _ausfall_offen(schluessel: str) -> bool:
    """Benachrichtigung zu einem Ausfall: offen, solange ein Platz noch ohne Ersatz ist."""
    from apps.dienstplan.models import Ausfall
    from apps.dienstplan.plan import einsaetze

    a = Ausfall.objects.filter(pk=schluessel or 0).first()
    return bool(a) and any(p.fehlt for p in einsaetze(a.helfer, a.von, a.bis))


def _rechte_entzug(benutzer) -> set:
    """Das Tablet-Konto einer Ausgabestelle (ADR 0059) sieht den Dienstplan nur, wenn ein Admin
    ihn für diese Ausgabestelle ausdrücklich eingeschaltet hat."""
    stelle = getattr(benutzer, "stelle", None)
    if stelle is None or stelle.dienstplan_sichtbar:
        return set()
    return {"dienstplan.sehen", "dienstplan.planen"}


def _darf(*codes):
    def pruefen(benutzer):
        from apps.konten import rollen

        return any(rollen.hat_recht(benutzer, c) for c in codes)

    return pruefen


MODUL = Modul(
    kennung="dienstplan",
    benachrichtigungen=(
        Art("dienstplan_ausfall", "Dienstplan: Ausfall",
            "Entfällt, wenn bis zum Versand für alle betroffenen Plätze Ersatz eingetragen ist.",
            fuer=_darf("dienstplan.planen", "dienstplan.sehen"), offen=_ausfall_offen),
        Art("dienstplan_gesund", "Dienstplan: wieder gesund",
            fuer=_darf("dienstplan.planen", "dienstplan.sehen")),
    ),
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
    aushang=aushang,
    rechte_entzug=_rechte_entzug,
)  # fmt: skip
