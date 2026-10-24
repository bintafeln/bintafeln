"""Anzeige-Hilfen für die Aufnahme (Zwischenstand liegt als Text in der Sitzung)."""

import datetime as dt

from django import template

register = template.Library()


@register.filter
def datum_de(wert):
    """Ein ISO-Datum („2026-03-12“) als „12.03.2026“; alles andere unverändert."""
    if isinstance(wert, str) and len(wert) == 10:
        try:
            return dt.date.fromisoformat(wert).strftime("%d.%m.%Y")
        except ValueError:
            pass
    return wert
