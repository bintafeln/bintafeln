"""Beschreibung des Moduls Links für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Einstellungen/Tafel", [
            ("einstellungen.links", eintrag("Links auf der Startseite", "links:liste")),
        ]),
    ]  # fmt: skip


def startseite(request):
    from apps.links.links import startseite as kacheln

    return kacheln(request)


def suchen(benutzer, begriff, grenze):
    from apps.links.links import sichtbar

    klein = begriff.lower()
    return [
        (link.titel, link.adresse, f"Link · {link.untertitel or link.ziel}")
        for _, links in sichtbar(benutzer)
        for link in links
        if klein in f"{link.titel} {link.untertitel} {link.beschreibung}".lower()
    ][: grenze + 1]


MODUL = Modul(
    kennung="links",
    titel="Links",
    beschreibung="Kacheln mit Links auf der Startseite (z. B. Monitor, Kiosk, Webseite, "
    "Werkzeuge), je nach Recht sichtbar",
    app_label="links",
    pfade=("/links/",),
    rechte=(("einstellungen.links", "Links auf der Startseite pflegen", ""),),
    kapitel=(("links", "Links auf der Startseite", ()),),
    menue=menue,
    startseite=startseite,
    suchen=suchen,
)  # fmt: skip
