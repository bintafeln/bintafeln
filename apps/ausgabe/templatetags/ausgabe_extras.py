"""Kleine Template-Hilfen für den Einlass."""

from django import template

register = template.Library()


@register.filter
def korrektur(offen, art):
    """Offene Korrekturwünsche (dict nach (Art, Datensatz)) auf eine Art einschränken."""
    return {pk: k for (a, pk), k in (offen or {}).items() if a == art}


@register.filter
def korrektur_fuer(je_art, pk):
    return (je_art or {}).get(pk)
