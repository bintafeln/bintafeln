"""Status nach dem Ausweis (ADR 0176).

Ein Kunde ohne gültigen Ausweis ist nicht „aktiv“: Läuft der Ausweis ab, setzt das Programm ihn
auf „pausiert“; wird der Ausweis verlängert, ist er wieder „aktiv“. Das gilt nur für Kunden, die
das Programm selbst pausiert hat (``Haushalt.status_automatisch``) – wer von Hand pausiert,
gesperrt, beendet oder als verstorben eingetragen ist, bleibt, wie er ist. Ohne eingetragenes
Ablaufdatum bleibt ein Kunde aktiv (unbekannt ist nicht abgelaufen, wie in ADR 0061).

Verstorbene Kunden wandern nach ``KundenEinstellungen.verstorben_loeschen_monate`` in den
Papierkorb.
"""

import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.kunden.models import Haushalt, HaushaltEreignis, KundenEinstellungen

S = Haushalt.Status


def an() -> bool:
    return KundenEinstellungen.laden().status_nach_ausweis


def neuer_status(h: Haushalt, heute: dt.date) -> str:
    """Welchen Status der Haushalt nach der Regel haben muss; leer, wenn er bleibt."""
    abgelaufen = h.ausweis_gueltig_bis is not None and h.ausweis_gueltig_bis < heute
    if h.status == S.AKTIV and abgelaufen:
        return S.PAUSIERT
    if h.status == S.PAUSIERT and h.status_automatisch and not abgelaufen:
        return S.AKTIV
    return ""


def _grund(h: Haushalt, neu: str) -> str:
    if neu == S.PAUSIERT:
        return f"Ausweis abgelaufen am {h.ausweis_gueltig_bis:%d.%m.%Y}"
    return "Ausweis wieder gültig"


def betroffene(heute: dt.date | None = None):
    """Aktive Kunden mit abgelaufenem Ausweis – die die Regel jetzt pausieren würde."""
    heute = heute or timezone.localdate()
    return Haushalt.objects.filter(status=S.AKTIV, ausweis_gueltig_bis__lt=heute)


def pruefen(h: Haushalt, heute: dt.date | None = None) -> str:
    """Nach einer Änderung im Programm: stellt den Status sofort um. Liefert den Grund (für eine
    Meldung) oder leer. Die Historie hält der Aufrufer wie bei jeder Änderung fest."""
    heute = heute or timezone.localdate()
    neu = neuer_status(h, heute) if an() else ""
    if not neu:
        return ""
    grund = _grund(h, neu)
    h.status, h.status_automatisch, h.status_seit = neu, neu == S.PAUSIERT, heute
    Haushalt.objects.filter(pk=h.pk).update(
        status=neu, status_automatisch=h.status_automatisch, status_seit=heute
    )
    h._status_geladen = neu
    return f"Status {h.get_status_display()}: {grund}"


def regel_anwenden(heute: dt.date | None = None, ereignisse: bool = True) -> int:
    """Täglich (Fristen), beim Import und beim Einschalten: alle, deren Status nicht mehr zum
    Ausweis passt. Der Import hält die Historie selbst fest (``ereignisse=False``)."""
    heute = heute or timezone.localdate()
    if not an():
        return 0
    kandidaten = list(betroffene(heute)) + [
        h for h in Haushalt.objects.filter(status=S.PAUSIERT, status_automatisch=True)
        if neuer_status(h, heute)
    ]  # fmt: skip
    with transaction.atomic():
        neu_ereignisse = []
        for h in kandidaten:
            neu = neuer_status(h, heute)
            alt = h.get_status_display()
            Haushalt.objects.filter(pk=h.pk).update(
                status=neu, status_automatisch=neu == S.PAUSIERT, status_seit=heute
            )
            if ereignisse:
                neu_ereignisse.append(HaushaltEreignis(
                    kundennummer=h.kundennummer, quelle=HaushaltEreignis.Quelle.AUTOMATIK,
                    text=f"Status: {alt} → {S(neu).label} ({_grund(h, neu)})"[:300],
                ))  # fmt: skip
        HaushaltEreignis.objects.bulk_create(neu_ereignisse, batch_size=1000)
    return len(kandidaten)


def verstorbene_entfernen(heute: dt.date | None = None) -> int:
    """Verstorbene Kunden nach der eingestellten Frist in den Papierkorb (wiederherstellbar)."""
    from apps.kunden import entfernen

    monate = KundenEinstellungen.laden().verstorben_loeschen_monate
    if not monate:
        return 0
    heute = heute or timezone.localdate()
    grenze = heute - dt.timedelta(days=round(monate * 30.44))
    anzahl = 0
    for h in Haushalt.objects.filter(status=S.VERSTORBEN, status_seit__lte=grenze):
        entfernen.haushalt_loeschen(None, h, still=True, von="automatisch")
        anzahl += 1
    return anzahl
