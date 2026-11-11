"""Beschreibung des Moduls Warteliste für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.mailuebersicht import Mail
from apps.core.module import Modul


def menue(eintrag):
    from apps.warteliste import vorberechnung

    # Zahl der offenen Fälle als Abzeichen – nur aus dem Cache (ohne teure Neuberechnung); so sieht
    # man schon im Menü, wie viel bei „Abgleich“ bzw. „Doppelte Anträge“ zur Bearbeitung ansteht.
    abgleich = eintrag("Abgleich mit Kundenstamm", "warteliste:abgleich")
    if offen := vorberechnung.anzahl_abgleich():
        abgleich["zahl"] = offen
        abgleich["zahl_titel"] = "Anträge mit möglichem Treffer im Kundenstamm"
    doppelte = eintrag("Doppelte Anträge", "warteliste:dubletten")
    if offen := vorberechnung.anzahl_dubletten():
        doppelte["zahl"] = offen
        doppelte["zahl_titel"] = "mögliche Dubletten-Paare"
    # Liegt noch kein Ergebnis im Cache (z. B. nach einer Entscheidung, die ihn verwirft), schon
    # beim Blick aufs Menü im Hintergrund vorrechnen – dann ist die Seite beim Öffnen meist da,
    # auch wenn man direkt über das Abzeichen hinspringt (ergänzt den periodischen Warmlauf).
    if vorberechnung.kalt():
        vorberechnung.vorwaermen()
    return [
        ("Anträge und Warteliste", [
            ("warteliste.sehen", eintrag("Warteliste", "warteliste:liste", genau=True)),
            ("warteliste.sehen", eintrag("Termine", "warteliste:termine")),
            ("warteliste.bearbeiten", abgleich),
            ("warteliste.bearbeiten", doppelte),
            ("warteliste.sehen", eintrag("Streichungsliste", "warteliste:streichungsliste")),
        ]),
        ("Einstellungen/Kunden", [
            ("einstellungen.warteliste",
             eintrag("Warteliste und Einladungen", "warteliste:einstellungen")),
        ]),
    ]  # fmt: skip


def fristen():
    from apps.warteliste import ablauf

    ablauf.automatik()


def auskunft_antrag(antrag, pdf):
    from apps.warteliste import ablauf

    ablauf.auskunft(antrag, pdf)


def antrag_abschnitt(request, a):
    """Warteliste-Abschnitt auf der ganzen Antragsseite (ADR 0115): Status, Einladen und die
    Einladungs-/Absage-Historie sowie – nachgeladen – ähnliche Haushalte. Nur wenn der Antrag auf
    der Warteliste steht und man sie sehen darf."""
    from django.template.loader import render_to_string

    from apps.konten import rollen
    from apps.warteliste import ablauf
    from apps.warteliste.forms import EinladenForm, StatusForm
    from apps.warteliste.models import Wartestand

    if not rollen.hat_recht(request.user, "warteliste.sehen"):
        return ""
    ws = Wartestand.objects.filter(antrag=a).select_related("termin").first()
    if ws is None:
        return ""
    return render_to_string("warteliste/_antrag_panel.html", {
        "a": a, "ws": ws, "darf": rollen.hat_recht(request.user, "warteliste.bearbeiten"),
        "form": StatusForm(initial={"status": ws.status, "wartezeit_bis": ws.wartezeit_bis}),
        "einladen": EinladenForm(termine=ablauf.kommende_termine()),
        "einladungen": a.einladungen.all(),
    }, request=request)  # fmt: skip


def suchen(benutzer, begriff, grenze):
    from django.db.models import Q
    from django.urls import reverse

    from apps.konten import rollen
    from apps.warteliste.models import Termin

    if not rollen.hat_recht(benutzer, "warteliste.sehen"):
        return []
    termine = Termin.objects.filter(Q(ort__icontains=begriff) | Q(anmerkung__icontains=begriff))
    return [(f"Termin {t}", reverse("warteliste:termin", args=[t.pk]), "Warteliste")
            for t in termine[: grenze + 1]]  # fmt: skip


MODUL = Modul(
    kennung="warteliste",
    mails=(
        Mail("Warteliste: Einladung, Absage, Erinnerung",
             "Wenn jemand in der Warteliste einlädt, absagt oder streicht – mit dem Text der "
             "jeweiligen Sprache.",
             "Die antragstellende Person.",
             ("Warteliste und Einladungen", "warteliste:einstellungen",
              "einstellungen.warteliste")),
    ),
    titel="Warteliste",
    beschreibung="Anträge zu Terminen einladen: Wartestatus, Einladungen, Absagen, Streichungen",
    app_label="warteliste",
    pfade=("/warteliste/",),
    rechte=(
        ("warteliste.sehen", "Warteliste, Termine, Druckliste und Streichungsliste ansehen", ""),
        ("warteliste.bearbeiten", "Einladen, absagen, Status setzen, Termine anlegen, "
         "Dubletten und Abgleich mit dem Kundenstamm", "Verschickt Mails an Antragsteller."),
        ("einstellungen.warteliste", "Warteliste einstellen: Mailtexte, Fristen, Sperrzeit", ""),
    ),
    vorgaben={"Büro": ("warteliste.sehen", "warteliste.bearbeiten")},
    kapitel=(
        ("warteliste", "Warteliste: einladen, Termine, Streichungen",
         ("warteliste.sehen", "einstellungen.warteliste")),
    ),
    menue=menue,
    fristen=fristen,
    auskunft_antrag=auskunft_antrag,
    antrag=antrag_abschnitt,
    suchen=suchen,
    sicherung_bereich="antraege",
)  # fmt: skip
