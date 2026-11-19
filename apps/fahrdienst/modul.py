"""Beschreibung des Moduls Fahrdienst für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.benachrichtigung import Art, Empfaengerwahl
from apps.core.module import Aushangseite, Modul


def menue(eintrag):
    return [
        ("Dienstpläne/Fahrdienst", [
            ("fahrdienst.sehen", eintrag("Fahrerplan", "fahrdienst:plan", genau=True)),
        ]),
        ("Einstellungen/Dienstpläne", [
            ("fahrdienst.planen", eintrag("Fahrdienst: Touren und Springer",
                                          "fahrdienst:einstellungen")),
        ]),
    ]  # fmt: skip


def meine_einsaetze(request):
    """Abschnitt „Fahrdienst“ auf „Meine Einsätze“: eigene Fahrten der nächsten vier Wochen und
    eigene Ausfälle."""
    import datetime as dt

    from django.template.loader import render_to_string
    from django.utils import timezone

    from apps.fahrdienst import plan
    from apps.fahrdienst.models import Ausfall
    from apps.konten import rollen

    if not rollen.hat_recht(request.user, "fahrdienst.sehen"):
        return ""
    heute = timezone.localdate()
    ich = plan.person_von(request.user)
    return render_to_string("fahrdienst/_meine.html", {
        "einsaetze": plan.einsaetze(ich, heute, heute + dt.timedelta(days=27)),
        "ausfaelle": Ausfall.objects.filter(person=ich, bis__gte=heute) if ich else [],
        "darf_melden": plan.darf_selbst_melden(request.user),
        "planen": rollen.hat_recht(request.user, "fahrdienst.planen"),
    }, request=request)  # fmt: skip


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


def _berechtigte():
    from apps.fahrdienst.plan import duerfen_planen

    return duerfen_planen()


def _wahl_lesen():
    from apps.fahrdienst.models import FahrdienstEinstellungen

    return FahrdienstEinstellungen.laden().benachrichtigen.values_list("pk", flat=True)


def _wahl_speichern(konten) -> None:
    from apps.fahrdienst.models import FahrdienstEinstellungen

    FahrdienstEinstellungen.laden().benachrichtigen.set(konten)


MODUL = Modul(
    kennung="fahrdienst",
    benachrichtigungen=(
        Art("fahrdienst_ausfall", "Fahrdienst: Ausfall",
            "Entfällt, wenn bis zum Versand für alle betroffenen Plätze Ersatz eingetragen ist.",
            fuer=_darf("fahrdienst.planen", "fahrdienst.sehen"), offen=_ausfall_offen,
            wann="Sobald für eine Fahrerin oder einen Fahrer ein Ausfall eingetragen wird.",
            wahl=Empfaengerwahl(_berechtigte, "alle, die den Fahrdienst planen dürfen",
                                _wahl_lesen, _wahl_speichern)),
        Art("fahrdienst_gesund", "Fahrdienst: wieder gesund",
            fuer=_darf("fahrdienst.planen", "fahrdienst.sehen"),
            wann="Sobald sich jemand vor dem Ende des Ausfalls wieder gesund meldet.",
            wahl=Empfaengerwahl(_berechtigte, "dieselben Personen wie beim Ausfall", fest=False)),
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
    meine_einsaetze=meine_einsaetze,
    einsaetze_recht="fahrdienst.sehen",
    fristen=fristen,
    auskunft_mitarbeiter=auskunft_mitarbeiter,
    sicherung_bereich="mitarbeitende",
    aushang=aushang,
)  # fmt: skip
