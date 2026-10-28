"""Seiten des Fahrdienstes für Aushang-Monitore (ADR 0080): je Monat eine Folie wie der
Fahrerplan, nur mit Namen."""

import datetime as dt

from django.template.loader import render_to_string
from django.utils import timezone

from apps.fahrdienst import plan


def auswahl() -> list[tuple[str, str]]:
    return []  # nur ein Fahrerplan


def folien(wert, von, bis) -> list[tuple[str, str]]:
    from apps.fahrdienst.views import MONATE

    ergebnis = []
    erster = von
    while erster <= bis:
        folgemonat = (erster.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
        ende = min(bis, folgemonat - dt.timedelta(days=1))
        tage = plan.tage(plan.fahrtage(erster, ende))
        if tage:
            html = render_to_string("fahrdienst/_aushang.html", {
                "tage": tage, "touren": plan.touren(tage[0][0], tage[-1][0]),
                "heute": timezone.localdate(),
            })  # fmt: skip
            ergebnis.append((f"Fahrerplan {MONATE[erster.month - 1]} {erster.year}", html))
        erster = ende + dt.timedelta(days=1)
    return ergebnis
