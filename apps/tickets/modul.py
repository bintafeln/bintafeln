"""Beschreibung des Moduls Tickets für den Modulrahmen (ADR 0049). Ohne Datenbankzugriff."""

from apps.core.benachrichtigung import Art
from apps.core.module import Modul


def menue(eintrag):
    return [
        ("Tickets", [
            (None, eintrag("Tickets", "tickets:liste", genau=True)),
            (None, eintrag("Ticket eröffnen", "tickets:neu")),
        ]),
        ("Einstellungen/Tafel", [
            ("einstellungen.tickets", eintrag("Ticket-Kategorien", "tickets:kategorien")),
        ]),
    ]  # fmt: skip


def fristen():
    from apps.tickets.ablauf import fristen_anwenden

    fristen_anwenden()


def _ticket_offen(schluessel):
    from apps.tickets.ablauf import ticket_offen

    return ticket_offen(schluessel)


def _zustaendig(benutzer):
    from apps.konten import rollen
    from apps.tickets.models import Kategorie

    return rollen.hat_recht(benutzer, "tickets.bearbeiten") or Kategorie.objects.filter(
        personen=benutzer).exists() or Kategorie.objects.filter(
        rollen__in=benutzer.groups.all()).exists()  # fmt: skip


def auskunft_mitarbeiter(benutzer, pdf):
    from apps.tickets.models import Ticket

    eigene = Ticket.objects.filter(erstellt_von=benutzer).select_related("kategorie")
    if not eigene.exists():
        return
    pdf.ueberschrift("Tickets")
    pdf.tabelle(["Nr.", "Gemeldet am", "Kategorie", "Titel", "Status"],
                [[str(t.pk), f"{t.erstellt_am:%d.%m.%Y}", str(t.kategorie), t.titel,
                  t.get_status_display()] for t in eigene],
                breiten=[0.08, 0.16, 0.2, 0.4, 0.16])  # fmt: skip


MODUL = Modul(
    kennung="tickets",
    titel="Tickets",
    beschreibung="Meldungen der Mitarbeitenden (defektes Gerät, Fehler im Programm, Lager …) "
    "mit Kategorie; die eingestellten Personen und Rollen werden benachrichtigt",
    app_label="tickets",
    pfade=("/tickets/",),
    rechte=(
        ("tickets.bearbeiten", "Alle Tickets sehen und bearbeiten",
         "Ohne das Recht sieht man eigene Tickets und die der Kategorien, für die man "
         "eingetragen ist."),
        ("einstellungen.tickets", "Ticket-Kategorien und Zuständige einstellen", ""),
    ),
    vorgaben={"Büro": ("tickets.bearbeiten",)},
    kapitel=(("tickets", "Tickets: etwas melden", ()),),
    menue=menue,
    fristen=fristen,
    auskunft_mitarbeiter=auskunft_mitarbeiter,
    sicherung_bereich="mitarbeitende",
    benachrichtigungen=(
        Art("ticket_neu", "Neues Ticket in meiner Kategorie",
            "Entfällt, wenn es bis zum Versand schon jemand übernommen oder erledigt hat.",
            fuer=_zustaendig, offen=_ticket_offen),
        Art("ticket_antwort", "Antwort oder neuer Status zu meinem Ticket"),
    ),
)  # fmt: skip
