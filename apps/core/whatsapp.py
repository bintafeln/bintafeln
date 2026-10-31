"""WhatsApp-Nachricht per „Klick zum Chat“ (wa.me).

Kein automatischer Versand und keine WhatsApp-Business-Schnittstelle: bintafeln baut nur einen
Link, der auf dem Gerät WhatsApp mit vorgefülltem Text zu einer Person öffnet. Abgeschickt wird
erst mit einem Tippen in WhatsApp. So lassen sich einzelne Helfer bei einer Plan-Änderung schnell
erreichen, ohne dass echte Nummern oder Texte das Haus verlassen.
"""

import re
from urllib.parse import quote


def nummer_bereinigen(roh: str, vorwahl: str = "49") -> str:
    """Handynummer für wa.me: nur Ziffern in internationaler Form ohne „+“.

    „+49 171 …“ und „0049 171 …“ → „49171…“; „0171 …“ → Ländervorwahl + „171…“.
    Leer, wenn keine brauchbare Nummer übrig bleibt.
    """
    n = re.sub(r"[^0-9+]", "", roh or "")
    if n.startswith("+"):
        n = n[1:]
    elif n.startswith("00"):
        n = n[2:]
    elif n.startswith("0"):
        vorwahl = re.sub(r"[^0-9]", "", vorwahl or "")
        n = vorwahl + n[1:]
    return n if n else ""


def link(nummer: str, text: str = "", vorwahl: str = "49") -> str:
    """wa.me-Link zu einer Nummer mit vorgefülltem Text; leer bei unbrauchbarer Nummer."""
    n = nummer_bereinigen(nummer, vorwahl)
    if not n:
        return ""
    ziel = f"https://wa.me/{n}"
    if text:
        ziel += f"?text={quote(text)}"
    return ziel


def fuer_person(person, text: str = "") -> str:
    """wa.me-Link zur Handynummer einer Adresse, mit der Ländervorwahl der Tafel.
    Leer, wenn keine Person oder keine Handynummer vorhanden ist."""
    if person is None or not getattr(person, "mobil", ""):
        return ""
    from apps.core.models import TafelEinstellungen

    return link(person.mobil, text, TafelEinstellungen.laden().laendervorwahl)
