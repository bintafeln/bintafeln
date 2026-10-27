"""Notiztexte anzeigen: Zeilenumbrüche und **fett** (z. B. „**NICHT!**“ in Notizen der
Verwaltung). Alles andere wird wie gewohnt maskiert, eigenes HTML wirkt nicht."""

import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe

register = template.Library()
FETT = re.compile(r"\*\*(.+?)\*\*")


@register.filter
def notiz_text(text) -> str:
    html = FETT.sub(r"<strong>\1</strong>", escape(text or ""))
    return mark_safe(html.replace("\n", "<br>"))  # noqa: S308 – vorher maskiert


def ohne_auszeichnung(text: str) -> str:
    """Für PDFs und Mails: **fett** als normaler Text."""
    return FETT.sub(r"\1", text or "")
