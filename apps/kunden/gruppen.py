"""Kundengruppe nur mit gültigem Ausweis (ADR 0061).

Wer pausiert, gesperrt oder beendet ist oder dessen Ausweis abgelaufen ist, fällt aus der
Kundengruppe, damit das Maximum einer Gruppe nie überschritten wird. Eine Tafel kann das in den
Kunden-Einstellungen abschalten (``gruppe_behalten``). Bei einer Änderung im Programm greift die
Regel sofort, ein abgelaufener Ausweis wird bei den täglichen Fristen erkannt.

Daneben führt ``Gruppenzeit`` je Kundennummer, von wann bis wann ein Kunde in welcher Gruppe war.
``zeiten_abgleichen()`` vergleicht dafür den Kundenstamm mit den offenen Zeiten; es läuft nach
jeder Änderung, nach dem Import und täglich.
"""

import datetime as dt

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.kunden.models import (
    Gruppenzeit,
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
)

RAUS = {Haushalt.Status.PAUSIERT, Haushalt.Status.GESPERRT, Haushalt.Status.BEENDET}


def grund(h: Haushalt, heute: dt.date) -> str:
    """Warum der Haushalt keine Kundengruppe haben darf; leer, wenn er darf."""
    if h.status in RAUS:
        return f"Status {h.get_status_display()}"
    if h.ausweis_gueltig_bis and h.ausweis_gueltig_bis < heute:
        return f"Ausweis abgelaufen am {h.ausweis_gueltig_bis:%d.%m.%Y}"
    return ""


def _aktiv() -> bool:
    return not KundenEinstellungen.laden().gruppe_behalten


def pruefen(h: Haushalt, heute: dt.date | None = None) -> str:
    """Nach einer Änderung im Programm: nimmt die Gruppe sofort weg. Liefert den Grund (für eine
    Meldung) oder leer. Die Historie hält der Aufrufer wie bei jeder Änderung fest."""
    heute = heute or timezone.localdate()
    text = grund(h, heute) if h.kundengruppe_id and _aktiv() else ""
    if text:
        Haushalt.objects.filter(pk=h.pk).update(kundengruppe=None)
        h.kundengruppe = None
    zeiten_abgleichen([h.kundennummer], heute, text)
    return text


def regel_anwenden(heute: dt.date | None = None, ereignisse: bool = True) -> int:
    """Täglich (Fristen) und beim Import: alle, die keine Gruppe haben dürfen. Der Import hält
    die Historie selbst fest (``ereignisse=False``), sonst stünde jede Änderung doppelt da."""
    heute = heute or timezone.localdate()
    if not _aktiv():
        zeiten_abgleichen(heute=heute)
        return 0
    betroffen = [h for h in Haushalt.objects.filter(kundengruppe__isnull=False)
                 .select_related("kundengruppe") if grund(h, heute)]  # fmt: skip
    with transaction.atomic():
        for h in betroffen:
            text = grund(h, heute)
            if ereignisse:
                HaushaltEreignis.objects.create(
                    kundennummer=h.kundennummer, quelle=HaushaltEreignis.Quelle.AUTOMATIK,
                    text=f"Kundengruppe: {h.kundengruppe.name} → – ({text})"[:300],
                )  # fmt: skip
            Haushalt.objects.filter(pk=h.pk).update(kundengruppe=None)
            zeiten_abgleichen([h.kundennummer], heute, text)
        zeiten_abgleichen(heute=heute)
    return len(betroffen)


def zeiten_abgleichen(kundennummern=None, heute: dt.date | None = None, ende: str = "") -> int:
    """Schließt offene Zeiten, deren Gruppe nicht mehr stimmt, und öffnet neue. ``kundennummern``
    None = alle (auch Kunden, die nicht mehr im Kundenstamm sind). Liefert die Zahl der
    Änderungen."""
    heute = heute or timezone.localdate()
    haushalte = Haushalt.objects.select_related("kundengruppe")
    offen = Gruppenzeit.objects.filter(bis__isnull=True)
    if kundennummern is not None:
        haushalte = haushalte.filter(kundennummer__in=kundennummern)
        offen = offen.filter(kundennummer__in=kundennummern)
    jetzt = {h.kundennummer: h.kundengruppe for h in haushalte}
    offene = {}
    for z in offen:
        offene.setdefault(z.kundennummer, []).append(z)
    schliessen, neu = [], []
    for nummer in jetzt.keys() | offene.keys():
        gruppe = jetzt.get(nummer)
        passend = False
        for z in offene.get(nummer, []):
            if gruppe and z.kundengruppe_id == gruppe.pk and not passend:
                passend = True
                continue
            z.bis = heute
            z.grund = (ende or ("nicht mehr im Kundenstamm" if nummer not in jetzt
                                else f"Wechsel nach {gruppe.name}" if gruppe
                                else "aus der Kundengruppe genommen"))[:200]  # fmt: skip
            schliessen.append(z)
        if gruppe and not passend:
            neu.append(Gruppenzeit(kundennummer=nummer, kundengruppe=gruppe,
                                   gruppe_name=gruppe.name, von=heute))  # fmt: skip
    Gruppenzeit.objects.bulk_update(schliessen, ["bis", "grund"], batch_size=1000)
    Gruppenzeit.objects.bulk_create(neu, batch_size=1000)
    return len(schliessen) + len(neu)


def zeiten(kundennummer: str) -> list[Gruppenzeit]:
    return list(Gruppenzeit.objects.filter(kundennummer=kundennummer)
                .order_by(F("von").desc(nulls_last=True), "-pk"))  # fmt: skip
