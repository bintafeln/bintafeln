"""Einen Haushalt mit allem, was an seiner Kundennummer hängt, in den Papierkorb legen."""

from apps.core import papierkorb


def haushalt_loeschen(benutzer, h):
    """Wie „Haushalt löschen“ in der Oberfläche (ADR 0073); Kontobuchungen bleiben ohne Haushalt,
    aber mit Kundennummer für die Kasse."""
    from apps.ausgabe.models import Teilnahme
    from apps.kunden.models import HaushaltDokument, HaushaltEreignis, Notiz

    nummer = h.kundennummer
    hp = h.hauptperson
    return papierkorb.loeschen(
        benutzer, "Haushalt", f"{nummer}{f' – {hp.vorname} {hp.nachname}' if hp else ''}",
        h, Notiz.objects.filter(kundennummer=nummer),
        HaushaltEreignis.objects.filter(kundennummer=nummer),
        Teilnahme.objects.filter(kundennummer=nummer),
        HaushaltDokument.objects.filter(kundennummer=nummer),
        recht="kunden.loeschen", kundennummer=nummer,
    )  # fmt: skip
