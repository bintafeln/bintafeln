"""Seiten des Dienstplans für Aushang-Monitore (ADR 0080): je Ausgabetag der Stelle eine Folie
wie der Plan auf Papier, nur mit Namen."""

from django.template.loader import render_to_string
from django.utils import timezone

from apps.ausgabe.ampel import wochentage
from apps.dienstplan import plan
from apps.dienstplan.models import Diensttag


def auswahl() -> list[tuple[str, str]]:
    return [(str(s.ausgabestelle_id), str(s)) for s in plan.stellen()]


def folien(wert, von, bis) -> list[tuple[str, str]]:
    from apps.dienstplan.views import TAGNAME

    stelle = plan.stellen().filter(ausgabestelle_id=wert).first() if str(wert).isdigit() else None
    if stelle is None:
        return []
    ergebnis = []
    for tag in wochentage(stelle.tage):
        daten, zeilen = plan.monat(stelle, tag, von, bis)
        if not daten or not zeilen:
            continue
        html = render_to_string("dienstplan/_aushang.html", {
            "daten": daten, "zeilen": zeilen, "heute": timezone.localdate(),
            "diensttag": Diensttag.objects.filter(stelle=stelle, wochentag=tag).first(),
        })  # fmt: skip
        ergebnis.append((f"Dienstplan {stelle} · {TAGNAME[tag]}", html))
    return ergebnis
