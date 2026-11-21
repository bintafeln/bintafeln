"""Stationen ins Adressbuch übertragen (ADR 0147).

Einmalig: Die Station bekommt einen Eintrag im Adressbuch (Organisation) und merkt ihn sich in
``Station.adresse``. Gibt es dort schon eine Organisation mit gleichem Namen und gleicher PLZ,
wird die verknüpft statt einer zweiten angelegt. Spätere Änderungen an der Station ändern den
Eintrag im Adressbuch nicht – das Adressbuch gehört dem Büro (Spenden, Serienbriefe).
"""

from django.db import transaction
from django.utils import timezone

from apps.adressen.models import Adresse, AdressKategorie
from apps.touren.models import Station


def vorhandene(station: Station) -> Adresse | None:
    """Organisation im Adressbuch mit gleichem Namen und gleicher PLZ (ohne eigene Station)."""
    return (Adresse.objects.filter(art=Adresse.Art.ORGANISATION,
                                   organisation__iexact=station.name.strip(),
                                   plz=station.plz.strip(), station__isnull=True)
            .order_by("pk").first())  # fmt: skip


@transaction.atomic
def uebertragen(station: Station, von: str) -> tuple[Adresse, bool]:
    """Rückgabe: der Eintrag im Adressbuch und ob er neu angelegt wurde."""
    station = Station.objects.select_for_update().get(pk=station.pk)
    if station.adresse_id:
        return station.adresse, False
    adresse = vorhandene(station)
    neu = adresse is None
    if neu:
        email = station.email or station.email_lieferschein
        weitere = station.email_lieferschein if station.email_lieferschein != email else ""
        adresse = Adresse(
            art=Adresse.Art.ORGANISATION, organisation=station.name,
            ansprechperson=station.ansprechpartner, strasse=station.strasse_hausnummer,
            plz=station.plz, ort=station.ort, telefon=station.telefon, email=email,
            email_weitere=weitere, geaendert_am=timezone.now(), geaendert_von=von,
        )  # fmt: skip
        adresse.clean()
        adresse.save()
        if station.art != Station.Art.SONSTIGES:
            kategorie, _ = AdressKategorie.objects.get_or_create(name=station.get_art_display())
            if kategorie.aktiv:
                adresse.kategorien.add(kategorie)
    station.adresse = adresse
    station.save(update_fields=["adresse"])
    return adresse, neu
