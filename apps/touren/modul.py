"""Beschreibung des Moduls Touren für den Modulrahmen (ADR 0049, ADR 0147). Ohne
Datenbankzugriff."""

from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Dienstpläne/Touren", [
            ("touren.stationen", eintrag("Stationen", "touren:stationen")),
        ]),
    ]  # fmt: skip


def suchen(benutzer, begriff, grenze):
    from django.db.models import Q
    from django.urls import reverse

    from apps.konten import rollen
    from apps.touren.models import Station

    if not rollen.hat_recht(benutzer, "touren.stationen"):
        return []
    treffer = Station.objects.filter(
        Q(name__icontains=begriff)
        | Q(kette__icontains=begriff)
        | Q(strasse__icontains=begriff)
        | Q(ort__icontains=begriff)
        | Q(ortsteil__icontains=begriff)
        | Q(kennung__iexact=begriff)
    )[: grenze + 1]
    return [(s.name, reverse("touren:station", args=[s.pk]),
             f"Station · {s.get_art_display()} · {s.anschrift}") for s in treffer]  # fmt: skip


def datenimport(request):
    """Der Import der Stationen steht auf der Seite „Daten importieren“."""
    from django.urls import reverse

    from apps.konten import rollen

    if not rollen.hat_recht(request.user, "touren.stationen_bearbeiten"):
        return []
    return [{"titel": "Stationen der Touren", "url": reverse("touren:importieren"),
             "beschreibung": "Märkte, Bäckereien, Lieferanten und andere Stationen aus einer "
             "CSV-Datei (stationen.csv) anlegen oder aktualisieren."}]  # fmt: skip


MODUL = Modul(
    kennung="touren",
    titel="Touren",
    beschreibung="Stationen der Abholtouren (Märkte, Bäckereien, Lieferanten …) mit Anfahrt, "
    "Abholtagen und Navigation mit Google Maps; Import aus einer CSV-Datei, Übertragen ins "
    "Adressbuch",
    app_label="touren",
    pfade=("/touren/",),
    rechte=(
        ("touren.stationen", "Stationen sehen und hinnavigieren",
         "Liste und Angaben der Stationen mit Anfahrt und Navigation (Google Maps)."),
        ("touren.stationen_bearbeiten", "Stationen anlegen, bearbeiten, importieren und löschen",
         "Ins Adressbuch übertragen nur zusammen mit „Adressen anlegen und bearbeiten“."),
    ),
    vorgaben={"Büro": ("touren.stationen", "touren.stationen_bearbeiten"),
              "Fahrer": ("touren.stationen",), "Beifahrer": ("touren.stationen",)},
    kapitel=(("touren", "Touren: Stationen", ("touren.stationen",)),),
    menue=menue,
    suchen=suchen,
    datenimport=datenimport,
    sicherung_bereich="adressen",
)  # fmt: skip
