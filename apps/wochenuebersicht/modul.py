"""Beschreibung des Moduls Wochenübersicht für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Ausgabestelle/Wochenübersicht", [
            ("wochenuebersicht.sehen", eintrag("Soll und Ist je Tag", "wochenuebersicht:uebersicht",
                                               genau=True)),
            ("wochenuebersicht.bearbeiten",
             eintrag("Selbstabholer", "wochenuebersicht:selbstabholer")),
            ("wochenuebersicht.bearbeiten",
             eintrag("Reihenfolge", "wochenuebersicht:reihenfolge")),
        ]),
    ]  # fmt: skip


def suchen(benutzer, begriff, grenze):
    from django.urls import reverse

    from apps.konten import rollen
    from apps.wochenuebersicht.models import Selbstabholer

    if not rollen.hat_recht(benutzer, "wochenuebersicht.bearbeiten"):
        return []
    from django.db.models import Q

    liste = Selbstabholer.objects.filter(
        Q(name__icontains=begriff) | Q(kontakte__name__icontains=begriff)
    ).distinct()[: grenze + 1]  # auch über die Ansprechpersonen
    return [(s.name, reverse("wochenuebersicht:selbstabholer_bearbeiten", args=[s.pk]),
             f"Selbstabholer · {s.tage}" if s.tage else "Selbstabholer")
            for s in liste]  # fmt: skip


MODUL = Modul(
    kennung="wochenuebersicht",
    titel="Wochenübersicht",
    beschreibung="Soll und Ist der Ausgabestellen je Wochentag mit Selbstabholern, Druck als PDF",
    app_label="wochenuebersicht",
    pfade=("/wochenuebersicht/",),
    rechte=(
        ("wochenuebersicht.sehen", "Wochenübersicht der Ausgabestellen ansehen und drucken",
         "Zeigt nur Summen, keine Personendaten."),
        ("wochenuebersicht.bearbeiten", "Selbstabholer und Reihenfolge der Wochenübersicht pflegen",
         ""),
    ),
    vorgaben={"Büro": ("wochenuebersicht.sehen", "wochenuebersicht.bearbeiten")},
    kapitel=(
        ("wochenuebersicht", "Wochenübersicht der Ausgabestellen", ("wochenuebersicht.sehen",)),
    ),
    menue=menue,
    suchen=suchen,
)  # fmt: skip
