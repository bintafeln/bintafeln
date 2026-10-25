"""Blättern in Listen: ``{% blaettern seite %}`` steht oben und unten; Links behalten die Filter."""

from urllib.parse import urlencode

from django import template

register = template.Library()


@register.inclusion_tag("includes/blaettern.html", takes_context=True)
def blaettern(context, seite, abfrage=None, ziel="", zusatz="", zurueck="← zurück",
              weiter="weiter →"):  # fmt: skip
    """``abfrage``: Filter als URL-Text; ohne Angabe die aktuellen GET-Werte ohne „seite“.
    ``ziel``: HTMX-Ziel, dann wird nur die Liste ausgetauscht. ``zusatz``: Wort hinter der Anzahl
    (z. B. „Anträge“)."""
    if abfrage is None:
        werte = context["request"].GET.copy()
        werte.pop("seite", None)
        abfrage = werte.urlencode()
    vorne = f"?{abfrage}&" if abfrage else "?"

    def link(nummer):
        return f"{vorne}{urlencode({'seite': nummer})}"

    return {
        "seite": seite, "ziel": ziel, "zusatz": zusatz, "zurueck_text": zurueck,
        "weiter_text": weiter,
        "zurueck": link(seite.previous_page_number()) if seite.has_previous() else "",
        "weiter": link(seite.next_page_number()) if seite.has_next() else "",
    }  # fmt: skip
