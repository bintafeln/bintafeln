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
from apps.kunden.models import Abholung, Ausgabestelle, Ausnahme, Haushalt, Kundengruppe


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
class Zeile:
    name: str  # Kundengruppe, oder „ohne Kundengruppe von heute“
    erwartet: int
    abgeholt: int
    ausnahmen: int  # davon mit Ausnahme abgeholt
    geplant: bool = True  # heute laut Plan (Wochentag oder Sonderausgabe) dran

    @property
    def offen(self) -> int:
        return max(self.erwartet - self.abgeholt, 0)


@dataclass
class Fortschritt:
    abgeholt: int
    erwartet: int
    gruppen: list[str]  # Namen der Kundengruppen, die heute hier dran sind
    zeilen: list[Zeile]  # je Kundengruppe: erwartet, abgeholt, mit Ausnahme
    ausnahmen: int = 0

    @property
    def offen(self) -> int:
        return sum(z.offen for z in self.zeilen)


def fortschritt(stelle, heute: dt.date) -> Fortschritt | None:
    """Heute an der Stelle: abgeholt / erwartet, auch je Kundengruppe.

    Gezählt werden alle Kundengruppen, die heute hier dran sind (regulär oder per Sonderausgabe,
    ADR 0072), und dazu jede Kundengruppe, aus der heute hier jemand abgeholt hat – etwa wenn die
    regulären Kunden trotz Sonderausgabe kommen. Erwartet sind die aktiven Haushalte dieser
    Gruppen; wer hier abgeholt hat, zählt immer mit, auch ohne passende Gruppe. So ist „abgeholt“
    nie größer als „erwartet“. None, wenn heute weder Ausgabetag ist noch abgeholt wurde."""
    if stelle is None:
        return None
    from apps.ausgabe import ausgabetag

    geplant = ausgabetag.gruppen_am(stelle, heute)  # auch Sonderausgaben (ADR 0072)
    abholungen = Abholung.objects.filter(datum=heute, ausgabestelle=stelle)
    abgeholt = dict(abholungen.values_list("haushalt_id", "haushalt__kundengruppe_id"))
    if not geplant and not abgeholt:
        return None
    mit_ausnahme = set(
        Ausnahme.objects.filter(datum=heute, haushalt_id__in=abgeholt).values_list(
            "haushalt_id", flat=True
        )
    )
    dazu = set(abgeholt.values()) - {g.pk for g in geplant} - {None}
    gruppen = geplant + sorted(Kundengruppe.objects.filter(pk__in=dazu), key=ausgabetag.reihenfolge)
    aktive = dict(
        Haushalt.objects.filter(status=Haushalt.Status.AKTIV, kundengruppe__in=gruppen)
        .values_list("pk", "kundengruppe_id")
    )  # fmt: skip
    zeilen = []
    for g in gruppen:
        hier = {h for h, k in aktive.items() if k == g.pk} | {
            h for h, k in abgeholt.items() if k == g.pk
        }
        geholt = hier & abgeholt.keys()
        zeilen.append(Zeile(g.name, len(hier), len(geholt), len(geholt & mit_ausnahme),
                            g in geplant))  # fmt: skip
    ohne = {h for h, k in abgeholt.items() if k is None or k not in {g.pk for g in gruppen}}
    if ohne:
        zeilen.append(Zeile("ohne Kundengruppe", len(ohne), len(ohne), len(ohne & mit_ausnahme),
                            False))  # fmt: skip
    return Fortschritt(
        abgeholt=len(abgeholt), erwartet=sum(z.erwartet for z in zeilen),
        gruppen=[g.name for g in gruppen], zeilen=zeilen, ausnahmen=len(mit_ausnahme),
    )  # fmt: skip


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
