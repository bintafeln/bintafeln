"""Spender eines Jahres aus den eingelesenen Belegen (ADR 0126).

Wie im bisherigen Spendenbelege-Programm: Ein Spender ist, wer denselben Namen trägt. Er steht
nur in der Liste, solange mindestens ein Beleg im Vereinsportal noch nicht versendet ist. Per
E-Mail erreichbar ist, wer in der Liste „Spender mit E-Mail“ steht und nicht „immer per Post“
gewählt hat.
"""

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from decimal import Decimal

from apps.core import privatdateien
from apps.vereinsportal.models import Beleg, Kontakt, PortalEinstellungen, Sammelbescheinigung

GRUPPEN = [
    ("mehrfach_mail", "Mehrfachspender mit E-Mail"),
    ("mehrfach_post", "Mehrfachspender ohne E-Mail"),
    ("einfach_mail", "Einfachspender mit E-Mail"),
    ("einfach_post", "Einfachspender ohne E-Mail"),
]


@dataclass
class Spender:
    name: str
    strasse: str
    plz_ort: str
    email: str = ""
    belege: list = field(default_factory=list)
    kontakt: object = None
    sammel: object = None  # hochgeladene Sammelbescheinigung des Jahres

    @property
    def anzahl(self) -> int:
        return len(self.belege)

    @property
    def summe(self) -> Decimal:
        return sum((b.betrag for b in self.belege), Decimal("0"))

    @property
    def offen(self) -> int:
        return sum(1 for b in self.belege if not b.im_portal_versendet)

    @property
    def mehrfach(self) -> bool:
        return self.anzahl > 1

    @property
    def unbedankt(self) -> list:
        """Belege, für die noch ein Dankesbrief aussteht (nicht im Portal versendet)."""
        return [b for b in self.belege if not b.im_portal_versendet and not b.bedankt_am]

    @property
    def gruppe(self) -> str:
        return f"{'mehrfach' if self.anzahl > 1 else 'einfach'}_{'mail' if self.email else 'post'}"


def spender(jahr: int) -> list[Spender]:
    """Spender des Jahres mit mindestens einem noch nicht versendeten Beleg."""
    kontakte = {k.such_name: k for k in Kontakt.objects.all()}
    sammel = {s.such_name: s for s in Sammelbescheinigung.objects.filter(jahr=jahr)
              .exclude(such_name="").order_by("hochgeladen_am")}  # fmt: skip
    alle: dict[str, Spender] = {}
    for b in Beleg.objects.filter(jahr=jahr).order_by("dateiname"):
        k = kontakte.get(b.such_name)
        s = alle.setdefault(b.such_name, Spender(
            b.name, b.strasse, b.plz_ort, k.email if k and not k.immer_post else "",
            kontakt=k, sammel=sammel.get(b.such_name),
        ))  # fmt: skip
        s.belege.append(b)
    return sorted((s for s in alle.values() if s.offen), key=lambda s: s.name.lower())


def zahlen(liste: list[Spender]) -> list[tuple[str, str, int]]:
    return [(k, titel, sum(1 for s in liste if s.gruppe == k)) for k, titel in GRUPPEN]


def jahre() -> list[int]:
    vorhanden = set(Beleg.objects.values_list("jahr", flat=True))
    return sorted(vorhanden | {dt.date.today().year}, reverse=True)


def csv_text(liste: list[Spender]) -> str:
    """Die Liste für Serienbriefe (Semikolon, mit BOM für Excel)."""
    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(["Name", "Straße", "PLZ und Ort", "E-Mail", "Anzahl Spenden",
                        "Gesamtbetrag", "Noch nicht versendet"])  # fmt: skip
    for s in liste:
        schreiber.writerow([s.name, s.strasse, s.plz_ort, s.email, s.anzahl,
                            f"{s.summe:.2f}".replace(".", ","), s.offen])  # fmt: skip
    return "﻿" + puffer.getvalue()


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Löscht Belege nach der Aufbewahrungszeit; ohne Belege auch die Spenderliste."""
    heute = heute or dt.date.today()
    grenze = heute.year - PortalEinstellungen.laden().aufbewahrung_jahre
    alt = Beleg.objects.filter(jahr__lt=grenze)
    anzahl = alt.count()
    for b in alt:
        privatdateien.loeschen(Beleg.ORDNER, b.datei)
    alt.delete()
    for s in Sammelbescheinigung.objects.filter(jahr__lt=grenze):
        privatdateien.loeschen(Sammelbescheinigung.ORDNER, s.datei)
        s.delete()
    if anzahl and not Beleg.objects.exists():
        Kontakt.objects.all().delete()
    return anzahl
