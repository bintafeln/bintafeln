"""Abholungen nachtragen (ADR 0091): Kunden, die da waren, aber am Einlass nicht eingetragen
werden konnten (Technik, Papierliste).

Mit ``einlass.nachtragen`` geht das für heute und gestern an den eigenen Ausgabestellen und nur,
wenn die Ampel an dem Tag nicht Rot gezeigt hätte. ``einlass.nachtragen_alle`` (Admin) erlaubt
jeden vergangenen Tag und auch rote Fälle. Der Betrag ist das, was bar gezahlt wurde; Buchung und
Kasse laufen wie am Einlass über ``konto.abholung_buchen`` mit dem Tag der Abholung.
"""

import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.ausgabe import ampel, ausgabetag, konto
from apps.ausgabe.models import AusgabeEinstellungen
from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.models import Abholung, Haushalt, KundenEinstellungen

TAGE_OHNE_ADMIN = 1  # heute und gestern


class NachtragFehler(Exception):
    pass


@dataclass
class Zeile:
    h: Haushalt
    beitrag: Decimal
    bewertung: ampel.Bewertung
    schon: list = field(default_factory=list)  # Abholungen an dem Tag
    gruppe: str = ""

    @property
    def rot(self) -> bool:
        return not self.bewertung.darf_abholen

    @property
    def hauptperson(self):
        return next((p for p in self.h.personen.all() if p.ist_hauptperson), None)

    @property
    def gruende(self) -> str:
        return "; ".join(m.text for m in self.bewertung.meldungen if m.farbe == ampel.ROT)


def alle_tage(benutzer) -> bool:
    return rollen.hat_recht(benutzer, "einlass.nachtragen_alle")


def fruehester_tag(benutzer, heute: dt.date | None = None) -> dt.date | None:
    """Frühester erlaubter Tag; None = unbegrenzt."""
    heute = heute or timezone.localdate()
    return None if alle_tage(benutzer) else heute - dt.timedelta(days=TAGE_OHNE_ADMIN)


def tag_pruefen(benutzer, datum: dt.date) -> None:
    heute = timezone.localdate()
    if datum > heute:
        raise NachtragFehler("Abholungen in der Zukunft lassen sich nicht nachtragen.")
    frueh = fruehester_tag(benutzer, heute)
    if frueh and datum < frueh:
        raise NachtragFehler("Nur heute und gestern lassen sich nachtragen; ältere Tage trägt "
                             "ein Admin nach.")  # fmt: skip


def _haushalte():
    return Haushalt.objects.select_related("kundengruppe__ausgabestelle").prefetch_related(
        "personen", "sperren", "ausnahmen", "abholungen__ausgabestelle")  # fmt: skip


def zeile(h: Haushalt, datum: dt.date, stelle) -> Zeile:
    e = AusgabeEinstellungen.laden()
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    return Zeile(
        h=h,
        beitrag=e.beitrag_fuer(h, datum, kind_bis),
        bewertung=ampel.bewerten(h, datum, stelle, e),
        schon=[a for a in h.abholungen.all() if a.datum == datum],
        gruppe=h.kundengruppe.name if h.kundengruppe else "",
    )


def liste(benutzer, stelle, datum: dt.date) -> list[Zeile]:
    """Alle aktiven Haushalte der Kundengruppen, die an dem Tag dran waren, dazu alle, die an dem
    Tag an der Stelle schon eingetragen sind."""
    gruppen = ausgabetag.gruppen_am(stelle, datum)
    haushalte = zugang.filtern(_haushalte().filter(
        Q(kundengruppe__in=gruppen, status=Haushalt.Status.AKTIV)
        | Q(abholungen__datum=datum, abholungen__ausgabestelle=stelle)
    ).distinct(), benutzer).order_by("kundennummer")  # fmt: skip
    return [zeile(h, datum, stelle) for h in haushalte]


def einzeln(benutzer, kundennummer: str, stelle, datum: dt.date) -> Zeile:
    h = zugang.haushalt(benutzer, kundennummer, _haushalte())
    return zeile(h, datum, stelle)


@transaction.atomic
def eintragen(benutzer, z: Zeile, datum: dt.date, stelle, betrag: Decimal, von: str) -> Abholung:
    """Trägt eine Abholung nach; ``betrag`` = bar gezahlt (zugleich der Beitrag)."""
    tag_pruefen(benutzer, datum)
    if betrag is None or betrag < 0:
        raise NachtragFehler("Bitte einen Betrag eintragen (auch 0).")
    if z.rot and not alle_tage(benutzer):
        raise NachtragFehler(f"Die Ampel hätte Rot gezeigt ({z.gruende}); das trägt ein Admin "
                             "nach.")  # fmt: skip
    abholung = Abholung.objects.create(
        haushalt=z.h, datum=datum, beitrag=betrag, ausgabestelle=stelle, eingetragen_von=von,
        erfasst_am=timezone.now(), nachgetragen=True,
    )  # fmt: skip
    konto.abholung_buchen(abholung, betrag, betrag, AusgabeEinstellungen.laden(), stelle, von)
    Haushalt.objects.filter(pk=z.h.pk).filter(
        Q(letzter_besuch__isnull=True) | Q(letzter_besuch__lt=datum)
    ).update(letzter_besuch=datum)  # fmt: skip
    return abholung
