"""Adresskategorien zusammenführen: zwei Kategorien, die dasselbe meinen, werden eine.

Alle Adressen der wegfallenden Kategorie bekommen die bleibende; die wegfallende geht samt ihren
Zuordnungen in den Papierkorb und lässt sich von dort zurückholen. Kategorien, die bintafeln selbst
setzt, können nicht wegfallen – das Programm legte sie sonst beim nächsten Anlass wieder an.
"""

from django.db import transaction

from apps.adressen.models import SPENDER, AdressKategorie
from apps.core import papierkorb


class Fehler(Exception):
    pass


def feste() -> set[str]:
    """Namen der Kategorien, die bintafeln selbst setzt."""
    from apps.konten.verwaltung import EHEMALIGE_KATEGORIE, HELFER_KATEGORIE

    return {SPENDER, HELFER_KATEGORIE, EHEMALIGE_KATEGORIE}


def pruefen(weg: AdressKategorie, bleibt: AdressKategorie) -> None:
    if weg.pk == bleibt.pk:
        raise Fehler("Bitte zwei verschiedene Kategorien wählen.")
    if weg.name in feste():
        raise Fehler(
            f"„{weg.name}“ setzt bintafeln selbst und kann nicht wegfallen. Sie kann aber die "
            "Kategorie sein, die bleibt."
        )


def betroffen(weg: AdressKategorie, bleibt: AdressKategorie) -> dict:
    """Wie viele Adressen die wegfallende Kategorie haben und wie viele davon die bleibende
    schon tragen."""
    ids = list(weg.adressen.values_list("pk", flat=True))
    return {"adressen": len(ids), "schon": bleibt.adressen.filter(pk__in=ids).count()}


def zusammenfuehren(benutzer, weg: AdressKategorie, bleibt: AdressKategorie) -> int:
    """Gibt allen Adressen von ``weg`` die Kategorie ``bleibt`` und legt ``weg`` in den
    Papierkorb. Rückgabe: Zahl der Adressen, die ``weg`` hatten."""
    pruefen(weg, bleibt)
    with transaction.atomic():
        adressen = list(weg.adressen.all())
        bleibt.adressen.add(*adressen)
        papierkorb.loeschen(
            benutzer,
            "Adresskategorie",
            f"{weg.name} (zusammengeführt mit „{bleibt.name}“)",
            weg,
            recht="einstellungen.listen",
        )
    return len(adressen)
