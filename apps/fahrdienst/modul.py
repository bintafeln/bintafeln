"""Beschreibung des Moduls Fahrdienst für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.benachrichtigung import Art
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
    from apps.adressen.models import Adresse
    from apps.core import ausfall as ausfallregeln
    from apps.fahrdienst.models import Ausfall, Besetzung, Ersatz, Springer, platz_name

    person = Adresse.objects.filter(konto=benutzer).first()
    if person is None:
        return
    feste = Besetzung.objects.filter(person=person).select_related("tour")
    ausfaelle = Ausfall.objects.filter(person=person)
    ersatz = Ersatz.objects.filter(person=person).select_related("tour")
    springer = Springer.objects.filter(person=person).first()
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


def _ausfall_offen(schluessel: str) -> bool:
    """Benachrichtigung zu einem Ausfall: offen, solange ein Platz noch ohne Ersatz ist."""
    from apps.fahrdienst.models import Ausfall
    from apps.fahrdienst.plan import einsaetze

    a = Ausfall.objects.filter(pk=schluessel or 0).first()
    return bool(a) and any(p.fehlt for p in einsaetze(a.person, a.von, a.bis))


def _darf(*codes):
    def pruefen(benutzer):
        from apps.konten import rollen

        return any(rollen.hat_recht(benutzer, c) for c in codes)

    return pruefen


MODUL = Modul(
    kennung="fahrdienst",
    benachrichtigungen=(
        Art("fahrdienst_ausfall", "Fahrdienst: Ausfall",
            "Entfällt, wenn bis zum Versand für alle betroffenen Plätze Ersatz eingetragen ist.",
            fuer=_darf("fahrdienst.planen", "fahrdienst.sehen"), offen=_ausfall_offen),
        Art("fahrdienst_gesund", "Fahrdienst: wieder gesund",
            fuer=_darf("fahrdienst.planen", "fahrdienst.sehen")),
    ),
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
