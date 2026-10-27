"""Wer an einem Tag an einer Ausgabestelle dran ist (ADR 0072).

Regulär: die Kundengruppen der Ausgabestelle, deren Wochentage den Tag enthalten. Gibt es für
den Tag eine Sonderausgabe, gilt nur sie: die Kundengruppen des gewählten Wochentags und die
einzeln gewählten Kundengruppen. Ampel, Fortschritt in der Kopfzeile, Aufruf und Kundenliste
fragen nur hier nach.
"""

import datetime as dt

from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.ausgabe.models import Sonderausgabe
from apps.kunden.models import Kundengruppe


def sonderausgabe(stelle, datum: dt.date) -> Sonderausgabe | None:
    if stelle is None:
        return None
    return Sonderausgabe.objects.filter(ausgabestelle=stelle, datum=datum).first()


def _nach_tag(stelle, kuerzel: str) -> list[Kundengruppe]:
    gruppen = Kundengruppe.objects.filter(ausgabestelle=stelle, aktiv=True)
    return [g for g in gruppen if kuerzel in wochentage(g.wochentage)]


def gruppen_am(stelle, datum: dt.date) -> list[Kundengruppe]:
    """Aktive Kundengruppen, die an dem Tag an der Stelle dran sind (nach Uhrzeit sortiert)."""
    s = sonderausgabe(stelle, datum)
    if s is None:
        gruppen = _nach_tag(stelle, WOCHENTAGE[datum.weekday()])
    else:
        gruppen = _nach_tag(stelle, s.wie_wochentag) if s.wie_wochentag else []
        gruppen += [g for g in s.kundengruppen.filter(aktiv=True) if g not in gruppen]
    return sorted(gruppen, key=lambda g: (g.uhrzeit is None, g.uhrzeit or dt.time(), g.name))


def dran(gruppe: Kundengruppe, datum: dt.date, stelle=None) -> tuple[bool, Sonderausgabe | None]:
    """Ob die Kundengruppe an dem Tag dran ist, und die Sonderausgabe, nach der das gilt.
    ``stelle``: die Ausgabestelle am Einlass; sonst die der Kundengruppe."""
    s = sonderausgabe(stelle or gruppe.ausgabestelle, datum)
    if s is None:
        return WOCHENTAGE[datum.weekday()] in wochentage(gruppe.wochentage), None
    return gruppe in gruppen_am(s.ausgabestelle, datum), s
