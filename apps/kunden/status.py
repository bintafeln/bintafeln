"""Status nach Sperre und Ausweis (ADR 0176).

Ein Kunde ohne gültigen Ausweis ist nicht „aktiv“: Läuft der Ausweis ab, setzt das Programm ihn
auf „pausiert“; wird der Ausweis verlängert, ist er wieder „aktiv“. Eine laufende Sperre
(``Sperre``) geht vor: Wer gesperrt ist, steht auf „gesperrt“, nicht auf „pausiert“; endet die
Sperre, gilt wieder der Ausweis. Zurückgestellt wird nur, wen das Programm selbst umgestellt hat
(``Haushalt.status_automatisch``) – wer von Hand pausiert, gesperrt, beendet oder als verstorben
eingetragen ist, bleibt, wie er ist. Ohne eingetragenes Ablaufdatum gilt ein Ausweis nicht als
abgelaufen (wie in ADR 0061).

Verstorbene Kunden wandern nach ``KundenEinstellungen.verstorben_loeschen_monate`` in den
Papierkorb.
"""

import datetime as dt

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.kunden.models import Haushalt, HaushaltEreignis, KundenEinstellungen, Sperre

S = Haushalt.Status


def an() -> bool:
    return KundenEinstellungen.laden().status_nach_ausweis


def gesperrte(heute: dt.date) -> set[int]:
    """Haushalte (pk) mit einer Sperre, die an dem Tag läuft."""
    return set(
        Sperre.objects.filter(von__lte=heute)
        .filter(Q(bis__isnull=True) | Q(bis__gte=heute))
        .values_list("haushalt_id", flat=True)
    )


def neuer_status(h: Haushalt, heute: dt.date, gesperrt: bool) -> str:
    """Welchen Status der Haushalt nach der Regel haben muss; leer, wenn er bleibt. Eine laufende
    Sperre geht vor dem Ausweis. Angefasst wird nur, wer aktiv ist oder vom Programm umgestellt
    wurde – ein von Hand gesetzter Status bleibt."""
    if h.status != S.AKTIV and not (h.status_automatisch and h.status in (S.PAUSIERT, S.GESPERRT)):
        return ""
    abgelaufen = h.ausweis_gueltig_bis is not None and h.ausweis_gueltig_bis < heute
    soll = S.GESPERRT if gesperrt else S.PAUSIERT if abgelaufen else S.AKTIV
    return "" if soll == h.status else soll


def _grund(h: Haushalt, neu: str) -> str:
    if neu == S.GESPERRT:
        return "Sperre eingetragen"
    if neu == S.PAUSIERT:
        return f"Ausweis abgelaufen am {h.ausweis_gueltig_bis:%d.%m.%Y}"
    return "Sperre beendet" if h.status == S.GESPERRT else "Ausweis wieder gültig"


def betroffene(heute: dt.date | None = None) -> list[tuple[Haushalt, str]]:
    """Alle, deren Status nicht zu Sperre und Ausweis passt, mit dem Status, den sie bekämen."""
    heute = heute or timezone.localdate()
    sperren = gesperrte(heute)
    kandidaten = Haushalt.objects.filter(
        Q(status=S.AKTIV) | Q(status_automatisch=True, status__in=(S.PAUSIERT, S.GESPERRT))
    ).only("kundennummer", "status", "status_automatisch", "ausweis_gueltig_bis")
    return [(h, neu) for h in kandidaten if (neu := neuer_status(h, heute, h.pk in sperren))]


def pruefen(h: Haushalt, heute: dt.date | None = None) -> str:
    """Nach einer Änderung im Programm: stellt den Status sofort um. Liefert den Grund (für eine
    Meldung) oder leer. Die Historie hält der Aufrufer wie bei jeder Änderung fest."""
    heute = heute or timezone.localdate()
    if not an():
        return ""
    neu = neuer_status(h, heute, h.pk in gesperrte(heute))
    if not neu:
        return ""
    grund = _grund(h, neu)
    h.status, h.status_automatisch, h.status_seit = neu, neu != S.AKTIV, heute
    Haushalt.objects.filter(pk=h.pk).update(
        status=neu, status_automatisch=h.status_automatisch, status_seit=heute
    )
    h._status_geladen = neu
    return f"Status {h.get_status_display()}: {grund}"


def regel_anwenden(heute: dt.date | None = None, ereignisse: bool = True) -> int:
    """Täglich (Fristen), beim Import und beim Einschalten: alle, deren Status nicht mehr zu
    Sperre und Ausweis passt. Der Import hält die Historie selbst fest (``ereignisse=False``)."""
    heute = heute or timezone.localdate()
    if not an():
        return 0
    liste = betroffene(heute)
    with transaction.atomic():
        neu_ereignisse = []
        for h, neu in liste:
            alt = h.get_status_display()
            Haushalt.objects.filter(pk=h.pk).update(
                status=neu, status_automatisch=neu != S.AKTIV, status_seit=heute
            )
            if ereignisse:
                neu_ereignisse.append(HaushaltEreignis(
                    kundennummer=h.kundennummer, quelle=HaushaltEreignis.Quelle.AUTOMATIK,
                    text=f"Status: {alt} → {S(neu).label} ({_grund(h, neu)})"[:300],
                ))  # fmt: skip
        HaushaltEreignis.objects.bulk_create(neu_ereignisse, batch_size=1000)
    return len(liste)


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
