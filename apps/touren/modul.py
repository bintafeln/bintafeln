"""Beschreibung des Moduls Touren für den Modulrahmen (ADR 0049, ADR 0147, ADR 0148). Ohne
Datenbankzugriff."""

from apps.core.benachrichtigung import Art
from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Dienstpläne/Touren", [
            ("touren.fahren", eintrag("Touren heute", "touren:heute", genau=True)),
            ("touren.stationen", eintrag("Stationen", "touren:stationen")),
        ]),
        ("Einstellungen/Dienstpläne", [
            ("touren.planen", eintrag("Touren: Stationsfolgen und kurzfristige Touren",
                                      "touren:touren")),
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

    wege = []
    if rollen.hat_recht(request.user, "touren.stationen_bearbeiten"):
        wege.append({"titel": "Stationen der Touren", "url": reverse("touren:importieren"),
                     "beschreibung": "Märkte, Bäckereien, Lieferanten und andere Stationen aus "
                     "einer CSV-Datei (stationen.csv) anlegen oder aktualisieren."})  # fmt: skip
    if rollen.hat_recht(request.user, "touren.planen"):
        wege.append({"titel": "Stationsfolgen der Touren",
                     "url": reverse("touren:touren_importieren"),
                     "beschreibung": "Welche Stationen jede Tour in welcher Reihenfolge anfährt "
                     "(tourstationen.csv)."})  # fmt: skip
    return wege


def startseite(request):
    """Wer heute eine Tour fährt, hat sie auf der Startseite: ein Tipp bis zur Navigation."""
    from django.template.loader import render_to_string
    from django.utils import timezone

    from apps.konten import rollen
    from apps.touren import ablauf

    if not rollen.hat_recht(request.user, "touren.fahren"):
        return ""
    touren = ablauf.meine(request.user, timezone.localdate())
    if not touren:
        return ""
    return render_to_string("touren/_startseite.html", {"touren": touren}, request=request)


def fristen():
    from apps.touren import ablauf

    ablauf.fristen_anwenden()


def auskunft_mitarbeiter(benutzer, pdf):
    from apps.touren.models import Tour

    touren = Tour.objects.filter(personen__konto=benutzer).distinct()
    if not touren:
        return
    pdf.ueberschrift("Touren")
    pdf.tabelle(
        ["Tour", "Am", "Geschickt am"],
        [[t.name, f"{t.datum:%d.%m.%Y}" if t.datum else "regelmäßig",
          f"{t.gesendet_am:%d.%m.%Y}" if t.gesendet_am else ""] for t in touren],
        breiten=[0.5, 0.25, 0.25],
    )  # fmt: skip


def _faehrt(benutzer):
    from apps.konten import rollen

    return rollen.hat_recht(benutzer, "touren.fahren")


def _tour_offen(schluessel):
    from apps.touren import ablauf

    return ablauf.tour_offen(schluessel)


MODUL = Modul(
    kennung="touren",
    titel="Touren",
    beschreibung="Abholtouren fürs Handy: Stationen (Märkte, Bäckereien, Lieferanten …) in "
    "Fahrtreihenfolge mit Navigation in Google Maps; Besetzung aus dem Fahrerplan oder eigene "
    "und kurzfristige Touren, die den Fahrern per E-Mail geschickt werden; Import aus CSV",
    app_label="touren",
    pfade=("/touren/",),
    rechte=(
        ("touren.fahren", "Touren sehen und fahren",
         "Die Touren des Tages mit Stationen, Besetzung und Navigation."),
        ("touren.stationen", "Stationen sehen und hinnavigieren",
         "Liste und Angaben der Stationen mit Anfahrt und Navigation (Google Maps)."),
        ("touren.planen", "Touren planen",
         "Stationsfolgen festlegen, eigene und kurzfristige Touren anlegen und an die Fahrer "
         "schicken, Stationsfolgen importieren."),
        ("touren.stationen_bearbeiten", "Stationen anlegen, bearbeiten, importieren und löschen",
         "Ins Adressbuch übertragen nur zusammen mit „Adressen anlegen und bearbeiten“."),
    ),
    vorgaben={"Büro": ("touren.fahren", "touren.stationen", "touren.planen",
                       "touren.stationen_bearbeiten"),
              "Fahrer": ("touren.fahren", "touren.stationen"),
              "Beifahrer": ("touren.fahren", "touren.stationen")},
    kapitel=(("touren", "Touren: unterwegs, Stationen, Planung",
              ("touren.fahren", "touren.stationen")),),
    benachrichtigungen=(
        Art("touren_tour", "Touren: Tour für Sie eingetragen",
            "Die Stationen der Tour mit einem Link zur Navigation.",
            fuer=_faehrt, offen=_tour_offen,
            wann="Wenn die Fahrdienstleitung bei einer eigenen oder kurzfristigen Tour „An die "
            "Fahrer schicken“ drückt.",
            an="Die Personen, die bei der Tour unter „Wer fährt“ gewählt sind."),
    ),
    menue=menue,
    suchen=suchen,
    datenimport=datenimport,
    startseite=startseite,
    fristen=fristen,
    auskunft_mitarbeiter=auskunft_mitarbeiter,
    sicherung_bereich="mitarbeitende",
)  # fmt: skip
