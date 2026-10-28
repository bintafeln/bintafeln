"""Von der Tafel selbst geschriebenes HTML (Texte des Antragsformulars, Antwortmail).

Erlaubt sind übliche Gestaltungs-Elemente, Links und Bilder; Skripte, Ereignisse wie
``onclick`` und ``javascript:``-Links werden entfernt (nh3). So kann ein Admin-Konto, das in
falsche Hände gerät, über diese Texte keine Besucher angreifen.
"""

import re
from html import unescape

import nh3
from django.utils.html import escape, linebreaks
from django.utils.safestring import SafeString, mark_safe

TAGS = {
    "a", "b", "blockquote", "br", "div", "em", "footer", "h1", "h2", "h3", "h4", "header", "hr",
    "i", "img", "li", "nav", "ol", "p", "section", "small", "span", "strong", "sub", "sup",
    "table", "tbody", "td", "th", "thead", "tr", "u", "ul",
}  # fmt: skip
ATTRIBUTE = {
    "*": {"style", "class", "lang", "dir"},
    "a": {"href", "title", "target"},
    "img": {"src", "alt", "width", "height"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
}
STILE = {
    "color", "background-color", "font-size", "font-weight", "font-style", "text-align",
    "text-decoration", "margin", "margin-top", "margin-bottom", "margin-left", "margin-right",
    "padding", "padding-top", "padding-bottom", "padding-left", "padding-right", "border",
    "border-radius", "width", "max-width", "height", "display", "line-height", "font-family",
    "flex-grow", "flex-shrink", "flex-wrap", "justify-content", "align-items", "gap",
    "vertical-align", "letter-spacing", "text-transform",
}  # fmt: skip


def bereinigen(html: str) -> SafeString:
    return mark_safe(  # noqa: S308 – durch nh3 bereinigt
        nh3.clean(
            html or "",
            tags=TAGS,
            attributes=ATTRIBUTE,
            url_schemes={"http", "https", "mailto", "tel"},
            filter_style_properties=STILE,
            link_rel="noopener noreferrer",
        )
    )


def einsetzen(text: str, **werte) -> str:
    """Ersetzt Platzhalter wie {nummer}; andere geschweifte Klammern bleiben stehen."""
    for name, wert in werte.items():
        text = text.replace("{" + name + "}", str(wert))
    return text


def ist_html(text: str) -> bool:
    return bool(re.search(r"<[a-zA-Z/][^>]*>", text or ""))


def anzeigen(eigen: str, standard: str, **werte) -> SafeString:
    """Eigener Text oder der mitgelieferte, mit Platzhaltern.

    Eigener Text mit HTML-Elementen wird bereinigt übernommen; reiner Text (auch ältere
    eigene Texte) behält seine Zeilenumbrüche.
    """
    text = eigen if eigen and eigen.strip() else standard
    if ist_html(text):
        return bereinigen(einsetzen(text, **{k: escape(v) for k, v in werte.items()}))
    return mark_safe(linebreaks(escape(einsetzen(text, **werte))))  # noqa: S308 – maskiert


def als_text(html: str) -> str:
    """Klartext-Fassung für Mailprogramme ohne HTML."""
    text = re.sub(r"(?i)<br\s*/?>|</(p|div|h[1-4]|li|tr)>", "\n", html)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", unescape(text)).strip()


def css_bereinigen(css: str) -> SafeString:
    """Eigenes CSS darf den <style>-Block nicht verlassen; CSS braucht kein „<“."""
    return mark_safe((css or "").replace("<", ""))  # noqa: S308
