"""Kleine Hilfen für die Formular-Vorlagen (``formular_abschnitte.html``, ``feld.html``)."""

from django import template

register = template.Library()


@register.filter
def zeigen_bei(feld) -> str:
    """Die ``data-zeigen-bei``-Regel eines Feld-Widgets, damit das ganze ``.feld`` (mit Label) nur
    bei passender Auswahl erscheint – nicht nur das Eingabefeld. Leer, wenn keine Regel gesetzt ist.
    Das Formular setzt die Regel wie gewohnt über ``widget.attrs['data-zeigen-bei']``."""
    try:
        return feld.field.widget.attrs.get("data-zeigen-bei", "")
    except AttributeError:
        return ""
