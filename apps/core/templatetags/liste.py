"""Blättern in Listen: ``{% blaettern seite %}`` steht oben und unten; Links behalten die Filter."""

from urllib.parse import urlencode

from django import template
from django.utils.html import format_html

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


@register.inclusion_tag("includes/auswahl_formular.html", takes_context=True)
def auswahl_formular(context, aktion, extra=""):
    """Formular für die Auswahlkästchen einer Liste (``form="auswahl"``): schickt die aktuellen
    Filter mit, ohne Seitenzahl. ``extra`` (z. B. „csv=1“) kommt dazu."""
    werte = context["request"].GET.copy()
    for name in ("seite", "id"):
        werte.pop(name, None)
    felder = [(k, v) for k in werte for v in werte.getlist(k)]
    if extra:
        k, _, v = extra.partition("=")
        felder.append((k, v))
    return {"aktion": aktion, "felder": felder}


@register.inclusion_tag("includes/sortkopf.html", takes_context=True)
def sortkopf(context, titel, schluessel="", sort="", klasse=""):
    """Ein Spaltenkopf für eine Liste – überall gleich: anklickbar und mit Pfeil für die aktuelle
    Sortierrichtung (▲/▼), sonst ↕. Erster Klick sortiert aufsteigend, der nächste absteigend.

    ``schluessel`` leer → schlichter Kopf ohne Sortieren. ``sort`` ist der tatsächlich verwendete
    Sortierwert (aus der Ansicht, siehe ``apps/core/listen.py``); ohne Angabe wird ``?sort=…`` aus
    der Adresse genommen. ``klasse`` z. B. „zahl“ für rechtsbündige Zahlenspalten. Der Link behält
    alle Filter und tauscht nur den Listenbereich ``id="ergebnis"`` aus (htmx)."""
    aktuell = sort or context["request"].GET.get("sort", "")
    richtung = "auf" if aktuell == schluessel else "ab" if aktuell == f"-{schluessel}" else ""
    werte = context["request"].GET.copy()
    werte.pop("seite", None)
    werte["sort"] = f"-{schluessel}" if aktuell == schluessel else schluessel
    return {"titel": titel, "schluessel": schluessel, "klasse": klasse, "richtung": richtung,
            "abfrage": werte.urlencode()}  # fmt: skip


@register.simple_tag(takes_context=True)
def live_suche(context, mindestens=2):
    """Attribute für ein Suchfeld: sucht beim Tippen ab ``mindestens`` Zeichen (und wenn es leer
    wird) und tauscht nur den Bereich ``id="ergebnis"`` der Seite aus; „Suchen“ geht weiter."""
    return format_html(
        'hx-get="{}" hx-include="closest form" hx-target="#ergebnis" hx-select="#ergebnis" '
        'hx-swap="outerHTML" hx-push-url="true" hx-sync="this:replace" autocomplete="off" '
        'hx-trigger="input[this.value.trim().length >= {} || !this.value] changed delay:400ms, '
        'search"',
        context["request"].path,
        mindestens,
    )
