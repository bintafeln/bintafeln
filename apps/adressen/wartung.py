"""Einmalige Datenpflege fürs Adressbuch (ADR 0097)."""

from apps.adressen.models import Adresse


def personen_art_heilen() -> int:
    """Adressen, die eigentlich Personen sind, aber als „Organisation" gespeichert wurden, auf
    „Person" setzen – sonst fehlen sie in allen Personen-Listen (z. B. „Liste zusammenstellen"
    und der Mitarbeitenden-Druckliste, die nur Personen zeigen).

    Zwei sichere Fälle:

    * Ein **Konto** gehört immer zu einer Person (ADR 0097); eine Adresse mit Konto muss „Person"
      sein. Frühere Umbauten konnten ein Konto an eine vorhandene „Organisation"-Adresse hängen,
      ohne die Art zu korrigieren.
    * Eine „Organisation" **ohne Organisationsnamen, aber mit Nachnamen** ist in Wahrheit eine
      Person (eine echte Organisation hat immer einen Organisationsnamen).

    Gibt die Zahl der geänderten Einträge zurück.
    """
    person = Adresse.Art.PERSON
    mit_konto = Adresse.objects.filter(konto__isnull=False).exclude(art=person).update(art=person)
    person_ohne_org = (
        Adresse.objects.filter(art=Adresse.Art.ORGANISATION, organisation="")
        .exclude(nachname="")
        .update(art=person)
    )
    return mit_konto + person_ohne_org
