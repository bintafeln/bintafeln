"""Die Ausgabestelle, an der jemand gerade arbeitet (ADR 0067).

Konten einer Ausgabestelle (ADR 0059) haben ihre Stelle fest. Alle anderen wählen sie oben im
Menü; die Wahl steht am Benutzer und gilt auch nach der nächsten Anmeldung. Einlass, Nachrichten
und Abrechnung nehmen diese Stelle, die Kopfzeile zeigt dazu den Fortschritt des Tages.
"""

import datetime as dt
from dataclasses import dataclass

from django.utils import timezone

from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.models import Abholung, Ausgabestelle, Haushalt


def waehlbar(benutzer) -> list[Ausgabestelle]:
    """Ausgabestellen, die das Konto wählen darf; die eigene bei Konten einer Ausgabestelle."""
    if benutzer.stelle_id:
        return [benutzer.stelle]
    eigene = zugang.stellen(benutzer)
    return list(eigene) if eigene is not None else list(Ausgabestelle.objects.order_by("name"))


def aktuelle(benutzer) -> Ausgabestelle | None:
    if not getattr(benutzer, "is_authenticated", False):
        return None
    if benutzer.stelle_id:
        return benutzer.stelle
    stellen = waehlbar(benutzer)
    if benutzer.gewaehlte_stelle_id and any(s.pk == benutzer.gewaehlte_stelle_id for s in stellen):
        return benutzer.gewaehlte_stelle
    return stellen[0] if len(stellen) == 1 else None


def waehlen(benutzer, pk) -> Ausgabestelle | None:
    """Merkt die Stelle am Benutzer; eine nicht erlaubte oder leere Wahl hebt sie auf."""
    stelle = next((s for s in waehlbar(benutzer) if str(s.pk) == str(pk)), None)
    if not benutzer.stelle_id:
        benutzer.gewaehlte_stelle = stelle
        benutzer.save(update_fields=["gewaehlte_stelle"])
    return stelle


@dataclass
class Fortschritt:
    abgeholt: int
    erwartet: int
    gruppen: list[str]  # Namen der Kundengruppen, die heute hier dran sind


def fortschritt(stelle, heute: dt.date) -> Fortschritt | None:
    """Heute an der Stelle: abgeholt / erwartet. Erwartet sind die aktiven Haushalte aller
    Kundengruppen dieser Stelle, die heute ihren Ausgabetag haben; abgeholt alle Haushalte mit
    einer heute hier eingetragenen Abholung (auch mit Ausnahme). None, wenn heute kein
    Ausgabetag ist."""
    if stelle is None:
        return None
    from apps.ausgabe import ausgabetag

    gruppen = ausgabetag.gruppen_am(stelle, heute)  # auch Sonderausgaben (ADR 0072)
    if not gruppen:
        return None
    erwartet = Haushalt.objects.filter(
        status=Haushalt.Status.AKTIV, kundengruppe__in=gruppen
    ).count()
    abgeholt = (
        Abholung.objects.filter(datum=heute, ausgabestelle=stelle)
        .values("haushalt").distinct().count()
    )  # fmt: skip
    return Fortschritt(abgeholt, erwartet, [g.name for g in gruppen])


def kontext(request) -> dict:
    """Für die Vorlage base.html (über den Kontextprozessor)."""
    benutzer = request.user
    if not rollen.hat_recht(benutzer, "einlass.nutzen"):
        return {}
    stelle = aktuelle(benutzer)
    return {
        "ausgabestelle": stelle,
        "ausgabestellen_wahl": [] if benutzer.stelle_id else waehlbar(benutzer),
        "ausgabe_fortschritt": fortschritt(stelle, timezone.localdate()),
    }
