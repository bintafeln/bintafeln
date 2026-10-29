"""Bilder im Handbuch (ADR 0038): ``{% hilfe_bild "einlass-kunde" "Beschreibung" %}``.

Die Bilder liegen in ``static/hilfe/bilder/<name>.png`` und entstehen automatisch mit
erfundenen Daten (``tests/e2e/test_hilfe_bilder.py``); Pfeile und Rahmen sind eingezeichnet.
"""

from functools import lru_cache

from django import template
from django.conf import settings
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()
ORDNER = "hilfe/bilder"


@lru_cache(maxsize=256)
def _groesse(name: str) -> tuple[int, int] | None:
    from PIL import Image

    pfad = settings.BASE_DIR / "static" / ORDNER / f"{name}.png"
    try:
        with Image.open(pfad) as bild:
            return bild.size
    except OSError:
        return None


@register.simple_tag
def hilfe_bild(name: str, beschreibung: str):
    """Bild mit Unterschrift; ein Klick zeigt es groß. Breite und Höhe stehen dabei, damit die
    Seite beim Laden nicht springt."""
    groesse = _groesse(name)
    if groesse is None:
        return ""
    url = static(f"{ORDNER}/{name}.png")
    return format_html(
        '<figure class="hilfe-bild"><a href="{}" target="_blank" rel="noopener" '
        'title="Bild groß zeigen"><img src="{}" alt="{}" width="{}" height="{}" loading="lazy">'
        "</a><figcaption>{}</figcaption></figure>",
        url, url, beschreibung, *groesse, beschreibung,
    )  # fmt: skip
