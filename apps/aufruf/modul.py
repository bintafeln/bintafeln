"""Beschreibung des Moduls Aufruf für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def einlass(haushalt, heute, stelle):
    from apps.aufruf import ablauf

    return ablauf.einlass(haushalt, heute, stelle)


def ausweis_qr(haushalt):
    from apps.aufruf import handy

    return handy.ausweis_qr(haushalt)


def auskunft_haushalt(haushalt, pdf):
    from django.utils import timezone

    from apps.aufruf.models import HandyCode, HandyZugang

    handys = HandyZugang.objects.filter(kundennummer=haushalt.kundennummer)
    code = HandyCode.objects.filter(kundennummer=haushalt.kundennummer).first()
    if not handys and not code:
        return
    pdf.ueberschrift("Wartezeit aufs Handy")
    if handys:
        pdf.tabelle(["Eingerichtet", "Zuletzt angesehen", "Gerät"], [
            [f"{timezone.localtime(z.eingerichtet_am):%d.%m.%Y}",
             f"{timezone.localtime(z.zuletzt_am):%d.%m.%Y %H:%M}" if z.zuletzt_am else "–",
             z.geraet or "–"] for z in handys
        ], breiten=[0.2, 0.25, 0.55])  # fmt: skip
    if code:
        pdf.absatz(f"QR-Code auf dem Ausweis, erzeugt am "
                   f"{timezone.localtime(code.erstellt_am):%d.%m.%Y}.")  # fmt: skip


def menue(eintrag):
    return [
        ("Einstellungen/Ausgabe", [
            ("einstellungen.aufruf", eintrag("Aufruf, Monitor und Kiosk", "aufruf:einstellungen")),
        ]),
    ]  # fmt: skip


MODUL = Modul(
    kennung="aufruf",
    titel="Aufruf",
    beschreibung="Kundennummern der Reihe nach aufrufen: Monitor, Handy-Steuerung, Kiosk",
    app_label="aufruf",
    pfade=("/aufruf/", "/warten/"),
    weitere_urls=(("/warten/", "apps.aufruf.urls_warten"),),
    rechte=(
        ("aufruf.steuern", "Kunden aufrufen (Steuerung, Handy), zu spät Gekommene einsortieren",
         "Sieht nur Kundennummern, keine Namen."),
        ("einstellungen.aufruf", "Aufruf einstellen: Monitor, Infos, Anzeige-Links", ""),
    ),
    vorgaben={"Büro": ("aufruf.steuern",), "Ausgabe": ("aufruf.steuern",)},
    kapitel=(
        ("aufruf", "Aufruf: Kundennummern aufrufen, Monitor und Kiosk",
         ("aufruf.steuern", "einstellungen.aufruf")),
    ),
    menue=menue,
    einlass=einlass,
    ausweis_qr=ausweis_qr,
    auskunft_haushalt=auskunft_haushalt,
    seitenleiste="aufruf/_leiste_platz.html",
    sicherung_bereich="kunden",
    sicherung_ausgenommen=("aufruf.aufruftag", "aufruf.kioskmeldung"),
)  # fmt: skip
