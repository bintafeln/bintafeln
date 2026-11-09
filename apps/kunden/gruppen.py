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
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.kunden.models import (
    Gruppenzeit,
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Kundengruppe,
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


def reservierte_zugaenge() -> dict[int, int]:
    """Je Kundengruppe die Zahl der geplanten, noch nicht ausgeführten Zuzüge (``GeplanterWechsel``,
    z. B. beim Schließen einer Ausgabestelle, ADR 0118). Diese Plätze sind bis zum Stichtag
    reserviert, damit sie nicht doppelt vergeben werden."""
    from apps.kunden.models import GeplanterWechsel

    return dict(
        GeplanterWechsel.objects.filter(erledigt_am__isnull=True)
        .values("ziel_gruppe")
        .annotate(n=Count("pk"))
        .values_list("ziel_gruppe", "n")
    )


def mit_plaetzen(haushalt: Haushalt | None = None) -> list[dict]:
    """Alle aktiven Kundengruppen mit Belegung (Haushalte ohne beendete), Maximum und freien
    Plätzen, sortiert nach Ausgabestelle und Name. ``eigene`` markiert die aktuelle Gruppe des
    Haushalts. ``reserviert`` zählt geplante Zuzüge, die den Platz schon belegen (ADR 0118); sie
    zählen bei ``frei`` mit. Anders als ``aufnahme.freie_gruppen`` werden auch volle Gruppen
    gezeigt."""
    belegt = Count("haushalte", filter=~Q(haushalte__status=Haushalt.Status.BEENDET))
    reserviert = reservierte_zugaenge()
    ergebnis = []
    for g in (
        Kundengruppe.objects.filter(aktiv=True)
        .select_related("ausgabestelle")
        .annotate(belegt=belegt)
        .order_by("ausgabestelle__name", "name")
    ):
        res = reserviert.get(g.pk, 0)
        frei = None if g.maximum is None else g.maximum - g.belegt - res
        ergebnis.append({
            "gruppe": g, "belegt": g.belegt, "reserviert": res, "maximum": g.maximum, "frei": frei,
            "eigene": haushalt is not None and haushalt.kundengruppe_id == g.pk,
        })  # fmt: skip
    return ergebnis


def kapazitaet() -> dict:
    """Überblick über die Belegung aller aktiven Kundengruppen für eine kompakte Anzeige (z. B.
    oben auf der Warteliste): je Gruppe Belegung, freie Plätze und Auslastung in Prozent, dazu die
    Summen über alle Gruppen mit Maximum. Gruppen mit Maximum zuerst, die volleren oben; Gruppen
    ohne Maximum (unbegrenzt) ans Ende."""
    zeilen = []
    belegt_gesamt = maximum_gesamt = frei_gesamt = mit_platz = 0
    for x in mit_plaetzen():
        if x["gruppe"].intern:  # interne Park-Gruppen gehören nicht in die Kapazitätsübersicht
            continue
        prozent = round(100 * x["belegt"] / x["maximum"]) if x["maximum"] else None
        zeilen.append({**x, "prozent": prozent})
        if x["maximum"]:
            belegt_gesamt += x["belegt"]
            maximum_gesamt += x["maximum"]
            frei_gesamt += max(0, x["frei"])
            if x["frei"] > 0:
                mit_platz += 1
    zeilen.sort(key=lambda z: (z["prozent"] is None, -(z["prozent"] or 0), z["gruppe"].name))
    return {
        "gruppen": zeilen,
        "belegt_gesamt": belegt_gesamt,
        "maximum_gesamt": maximum_gesamt,
        "frei_gesamt": frei_gesamt,
        "mit_platz": mit_platz,
        "prozent_gesamt": round(100 * belegt_gesamt / maximum_gesamt) if maximum_gesamt else None,
    }


def zeiten(kundennummer: str) -> list[Gruppenzeit]:
    return list(Gruppenzeit.objects.filter(kundennummer=kundennummer)
                .order_by(F("von").desc(nulls_last=True), "-pk"))  # fmt: skip
