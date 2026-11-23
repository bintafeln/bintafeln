"""Beschreibung des Moduls Touren für den Modulrahmen (ADR 0049, ADR 0147, ADR 0148). Ohne
Datenbankzugriff."""

from apps.core.benachrichtigung import Art
from apps.core.mailuebersicht import Mail
from apps.core.module import Modul


def menue(eintrag):
    """Alles zu den Touren steht im eigenen Hauptbereich „Touren“ – auch das, was die
    Fahrdienstleitung einrichtet. Unter „Einstellungen → Touren“ bleibt nur, was der Admin
    entscheidet (Mailversand, Karte, Aufbewahrung)."""
    from apps.touren.models import TourenEinstellungen

    eco = []
    if TourenEinstellungen.laden().eco_link:
        # „fremd“: führt zu einer fremden Seite. Das PDF-Fenster der App (pdf_fenster.js) lässt
        # solche Links in Ruhe, sonst versuchte es, die fremde Seite als PDF zu laden.
        eco = [("touren.fahren", eintrag("ECO-Plattform", "touren:eco", extern=True) | {
            "fremd": True})]  # fmt: skip
    return [
        ("Touren", [
            ("touren.fahren", eintrag("Touren heute", "touren:heute", genau=True)),
            ("touren.planen", eintrag("Touren planen", "touren:touren")),
            ("touren.stationen", eintrag("Stationen", "touren:stationen")),
            ("touren.lieferscheine", eintrag("Lieferscheine", "touren:lieferscheine")),
            ("touren.fahrten", eintrag("Fahrtenbuch", "touren:fahrten", genau=True)),
            ("touren.fahrten", eintrag("Meldungen zum Fahrzeug", "touren:meldungen")),
            ("touren.statistik", eintrag("Statistik", "touren:statistik")),
            ("touren.planen", eintrag("Einrichten: Warengruppen, Fahrzeuge, Zentrale",
                                      "touren:einrichten")),
            *eco,
        ]),
        ("Einstellungen/Touren", [
            ("einstellungen.touren", eintrag("Mailversand, Karte und Aufbewahrung",
                                             "touren:einstellungen")),
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
    """Wer heute eine Tour fährt, hat sie auf der Startseite: ein Tipp bis zur Navigation. Die
    Fahrdienstleitung sieht dort die offenen Meldungen zum Fahrzeug (ADR 0155)."""
    from django.template.loader import render_to_string
    from django.utils import timezone

    from apps.konten import rollen
    from apps.touren import ablauf, meldungen

    touren, offen = [], []
    if rollen.hat_recht(request.user, "touren.fahren"):
        touren = ablauf.meine(request.user, timezone.localdate())
    if rollen.hat_recht(request.user, "touren.fahrten"):  # Fahrdienstleitung
        offen = list(meldungen.offene()[:20])
    if not touren and not offen:
        return ""
    return render_to_string("touren/_startseite.html", {"touren": touren, "meldungen": offen},
                            request=request)  # fmt: skip


def fristen():
    from apps.touren import (
        ablauf,
        anfahrten,
        fahrten,
        lieferscheine,
        meldungen,
        nachrichten,
        start,
        zusatz,
    )

    fahrten.fristen_anwenden()
    zusatz.fristen_anwenden()
    meldungen.fristen_anwenden()
    anfahrten.fristen_anwenden()
    ablauf.fristen_anwenden()
    lieferscheine.fristen_anwenden()
    start.fristen_anwenden()
    nachrichten.fristen_anwenden()


def auskunft_mitarbeiter(benutzer, pdf):
    from django.db.models import Q

    from apps.touren.models import Fahrt, Fahrzeugmeldung, Lieferschein, Tour

    touren = Tour.objects.filter(personen__konto=benutzer).distinct()
    scheine = Lieferschein.objects.filter(erstellt_von=benutzer)
    fahrten = Fahrt.objects.filter(Q(begonnen_von=benutzer) | Q(beendet_von=benutzer))
    gemeldet = Fahrzeugmeldung.objects.filter(gemeldet_von=benutzer)
    if not touren and not scheine and not fahrten and not gemeldet:
        return
    pdf.ueberschrift("Touren")
    pdf.tabelle(
        ["Zum Fahrzeug gemeldet", "Fahrzeug", "Meldung"],
        [[f"{x.gemeldet_am:%d.%m.%Y}", x.fahrzeug_name, f"{x.get_art_display()}: {x.text}"]
         for x in gemeldet],
        breiten=[0.25, 0.25, 0.5],
    )  # fmt: skip
    pdf.tabelle(
        ["Fahrt begonnen oder beendet", "Tour", "Fahrzeug", "km"],
        [[f"{x.datum:%d.%m.%Y}", x.tour_name, x.fahrzeug_name,
          "" if x.km is None else str(x.km)] for x in fahrten],
        breiten=[0.3, 0.3, 0.25, 0.15],
    )  # fmt: skip
    pdf.tabelle(
        ["Lieferschein unterschrieben", "Datum", "Station"],
        [[f"Nr. {ls.nummer}", f"{ls.datum:%d.%m.%Y}", ls.station_name] for ls in scheine],
        breiten=[0.3, 0.2, 0.5],
    )
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
    "und kurzfristige Touren; Lieferscheine mit Unterschrift am Handy, als PDF per E-Mail an "
    "die Station; Import aus CSV",
    app_label="touren",
    pfade=("/touren/",),
    rechte=(
        ("touren.fahren", "Touren sehen und fahren",
         "Die Touren des Tages mit Stationen, Besetzung und Navigation."),
        ("touren.besetzung", "Besetzung jeder Tour beim Start bestätigen und ändern",
         "Ohne dieses Recht geht das nur für Touren, auf denen man an dem Tag selbst eingetragen "
         "ist. Eine Änderung steht für den Tag als Ersatz im Fahrerplan."),
        ("touren.stationen", "Stationen sehen und hinnavigieren",
         "Liste und Angaben der Stationen mit Anfahrt und Navigation (Google Maps)."),
        ("touren.planen", "Touren planen",
         "Stationsfolgen festlegen, eigene und kurzfristige Touren anlegen und an die Fahrer "
         "schicken, Stationsfolgen importieren."),
        ("touren.stationen_bearbeiten", "Stationen anlegen, bearbeiten, importieren und löschen",
         "Ins Adressbuch übertragen nur zusammen mit „Adressen anlegen und bearbeiten“."),
        ("touren.lieferschein", "Lieferscheine ausfüllen und unterschreiben",
         "An einer Station den Lieferschein ausfüllen; die eigenen Lieferscheine ansehen."),
        ("touren.lieferscheine", "Alle Lieferscheine ansehen, nachsenden und löschen", ""),
        ("touren.fahrten", "Fahrtenbuch und Meldungen zum Fahrzeug",
         "Alle Fahrten mit Fahrzeug, Besetzung und Kilometerstand ansehen und berichtigen; "
         "Meldungen der Fahrer zum Fahrzeug auf der Startseite sehen und abhaken."),
        ("touren.statistik", "Statistik der Touren ansehen",
         "Mengen, Fahrten und Kilometer je Monat, Tour, Station und Fahrzeug – nie je Person."),
        ("einstellungen.touren", "Touren einstellen: Mailversand, Karte und Aufbewahrung",
         "Warengruppen, Fahrzeuge und die Zentrale richtet ein, wer Touren plant."),
    ),
    vorgaben={"Büro": ("touren.fahren", "touren.besetzung", "touren.stationen", "touren.planen",
                       "touren.stationen_bearbeiten", "touren.lieferschein",
                       "touren.lieferscheine", "touren.fahrten", "touren.statistik"),
              "Fahrer": ("touren.fahren", "touren.stationen", "touren.lieferschein"),
              "Beifahrer": ("touren.fahren", "touren.stationen", "touren.lieferschein")},
    mails=(
        Mail("Touren: Lieferschein",
             "Sobald unterwegs ein Lieferschein unterschrieben wird, oder beim Nachsenden.",
             "Die Station: ihre „E-Mail für Lieferscheine“, sonst ihre E-Mail. Sonst niemand.",
             ("Touren: Mailversand, Karte und Aufbewahrung", "touren:einstellungen",
              "einstellungen.touren")),
    ),
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
    kopfzeile="touren/_heuler_platz.html",
    fristen=fristen,
    auskunft_mitarbeiter=auskunft_mitarbeiter,
    sicherung_bereich="mitarbeitende",
)  # fmt: skip
