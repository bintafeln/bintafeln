"""Stationen suchen (beim Anhängen an eine Tour): über alle Angaben einer Station – Name, Kette,
Anschrift, Telefon, Ansprechpartner, E-Mail, Kennung, Notiz … Jedes Wort des Suchbegriffs muss
irgendwo vorkommen („rewe haupt“ findet den REWE in der Hauptstraße)."""

from django.db.models import Q

from apps.touren.models import Station

MINDESTENS = 3  # Zeichen, ab denen gesucht wird
FELDER = ["name", "kette", "filialnummer", "kennung", "strasse", "hausnummer", "plz", "ort",
          "ortsteil", "telefon", "ansprechpartner", "email", "email_lieferschein",
          "oeffnungszeiten", "abholzeit", "anfahrt", "notiz"]  # fmt: skip


def stationen(begriff: str, ohne_tour=None, grenze: int = 25) -> list[Station]:
    """Aktive Stationen zum Suchbegriff; ``ohne_tour``: Stationen dieser Tour nicht anbieten."""
    begriff = (begriff or "").strip()
    if len(begriff) < MINDESTENS:
        return []
    treffer = Station.objects.filter(aktiv=True)
    if ohne_tour is not None:
        treffer = treffer.exclude(halte__tour=ohne_tour)
    for wort in begriff.split()[:6]:
        bedingung = Q()
        for feld in FELDER:
            bedingung |= Q(**{f"{feld}__icontains": wort})
        treffer = treffer.filter(bedingung)
    return list(treffer.order_by("name", "ort")[:grenze])
