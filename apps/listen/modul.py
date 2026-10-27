"""Beschreibung des Moduls Listen für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Ausgabestelle", [
            ("listen.nutzen", eintrag("Kundenliste", "listen:liste", "kunden_stelle")),
        ]),
        ("Auswertungen", [
            ("listen.nutzen", eintrag("Listen", "listen:uebersicht", genau=True)),
        ]),
    ]  # fmt: skip


def suchen(benutzer, begriff, grenze):
    from django.urls import reverse

    from apps.konten import rollen
    from apps.listen.katalog import LISTEN

    if not rollen.hat_recht(benutzer, "listen.nutzen"):
        return []
    klein = begriff.lower()
    darf = rollen.rechte_von(benutzer)
    return [(f"Liste: {liste.titel}", reverse("listen:liste", args=[liste.kennung]),
             liste.beschreibung)
            for liste in LISTEN if (not liste.recht or liste.recht in darf)
            and klein in f"{liste.titel} {liste.beschreibung}".lower()][: grenze + 1]  # fmt: skip


MODUL = Modul(
    kennung="listen",
    titel="Listen",
    beschreibung="Fertige Listen und Zählungen zum Kundenstamm (Ausgabestelle, Alter, "
    "Staatsangehörigkeit, Einkommensart …), Spalten wählbar, Export als CSV und PDF",
    app_label="listen",
    pfade=("/listen/",),
    rechte=(
        ("listen.nutzen", "Listen ansehen, drucken und exportieren",
         "Nur Kunden der eigenen Ausgabestellen; Stammdaten und Kontaktdaten nur mit den Rechten "
         "dazu. Jeder Export steht im Zugriffsprotokoll."),
        ("listen.teilen", "Eigene Listen für alle speichern", ""),
    ),
    vorgaben={"Büro": ("listen.nutzen", "listen.teilen"), "Ausgabe": ("listen.nutzen",)},
    kapitel=(("listen", "Listen", ("listen.nutzen",)),),
    menue=menue,
    suchen=suchen,
    sicherung_bereich="kunden",
)  # fmt: skip
