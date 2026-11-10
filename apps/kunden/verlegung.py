"""Verlegung von Kunden und Schließen von Ausgabestellen (ADR 0118).

Schließt eine Ausgabestelle, wird sie mit einem Enddatum (``Ausgabestelle.schliesst_am``) versehen;
ab dem Tag danach schiebt ``stellen_schliessen`` sie automatisch ins Archiv (``aktiv=False``) und
setzt ihre Kundengruppen inaktiv. Die Kunden verteilt man vorher je Haushalt auf andere
Kundengruppen: ``planen`` legt einen ``GeplanterWechsel`` zu einem Stichtag an, ``anwenden`` führt
am Stichtag alle fälligen Wechsel aus. Beide Funktionen laufen täglich über
``kunden.models.fristen_anwenden`` (Startseite).
"""

import datetime as dt

from django.utils import timezone


def offener(haushalt):
    """Der noch nicht ausgeführte geplante Wechsel eines Haushalts (oder None)."""
    from apps.kunden.models import GeplanterWechsel

    if haushalt is None:
        return None
    return (
        GeplanterWechsel.objects.filter(haushalt=haushalt, erledigt_am__isnull=True)
        .select_related("ziel_gruppe")
        .first()
    )


def planen(haushalt, ziel_gruppe, ab: dt.date, von: str = ""):
    """Plant die Verlegung eines Haushalts in ``ziel_gruppe`` zum Stichtag ``ab``. Ein schon
    vorhandener offener Plan wird ersetzt (je Haushalt höchstens einer)."""
    from apps.kunden.models import GeplanterWechsel

    GeplanterWechsel.objects.filter(haushalt=haushalt, erledigt_am__isnull=True).delete()
    return GeplanterWechsel.objects.create(
        haushalt=haushalt, ziel_gruppe=ziel_gruppe, ab=ab, eingetragen_von=von[:150]
    )


def entfernen(haushalt) -> int:
    """Nimmt einen geplanten, noch nicht ausgeführten Wechsel wieder zurück."""
    from apps.kunden.models import GeplanterWechsel

    return GeplanterWechsel.objects.filter(haushalt=haushalt, erledigt_am__isnull=True).delete()[0]


def anwenden(heute: dt.date | None = None) -> int:
    """Führt alle fälligen Verlegungen aus (Stichtag erreicht): setzt die neue Kundengruppe, hält
    es in der Historie fest und markiert den Plan als erledigt. Eine inzwischen inaktive Zielgruppe
    bleibt offen (wird nicht ausgeführt). Liefert die Zahl der verlegten Haushalte."""
    from apps.kunden import gruppen, historie
    from apps.kunden.models import GeplanterWechsel, HaushaltEreignis, Notiz

    heute = heute or timezone.localdate()
    faellig = GeplanterWechsel.objects.filter(
        erledigt_am__isnull=True, ab__lte=heute
    ).select_related("haushalt", "ziel_gruppe")
    anzahl = 0
    for wechsel in faellig:
        if not wechsel.ziel_gruppe.aktiv:
            continue
        h = wechsel.haushalt
        vorher = historie.schnappschuss(h)
        h.kundengruppe = wechsel.ziel_gruppe
        h.geaendert_am = timezone.now()
        h.geaendert_von = "automatisch"
        h.save(update_fields=["kundengruppe", "geaendert_am", "geaendert_von"])
        gruppen.pruefen(h, heute)  # ohne gültigen Ausweis keine Kundengruppe (ADR 0061)
        historie.festhalten(
            h.kundennummer, vorher, historie.schnappschuss(h),
            quelle=HaushaltEreignis.Quelle.AUTOMATIK, von="automatisch",
            zusatz="Verlegung (Ausgabestelle schließt)",
        )  # fmt: skip
        # Nach dem Umzug braucht der Haushalt einen neuen Ausweis (neue Ausgabestelle/Gruppe):
        # als Notiz vermerken, damit beim nächsten Einlass ein neuer Ausweis gedruckt wird.
        Notiz.objects.create(
            kundennummer=h.kundennummer,
            text=f"Ausweis drucken (Umzug zu {wechsel.ziel_gruppe.name})"[:1000],
            verfasst_von="automatisch",
        )
        wechsel.erledigt_am = heute
        wechsel.save(update_fields=["erledigt_am"])
        anzahl += 1
    return anzahl


def stellen_schliessen(heute: dt.date | None = None) -> int:
    """Archiviert Ausgabestellen, deren letzter Tag (``schliesst_am``) vorbei ist: setzt sie auf
    inaktiv und ihre Kundengruppen ebenfalls, damit sie nirgends mehr auftauchen. Liefert die Zahl
    der geschlossenen Stellen."""
    from apps.kunden.models import Ausgabestelle, Kundengruppe

    heute = heute or timezone.localdate()
    faellig = Ausgabestelle.objects.filter(
        aktiv=True, schliesst_am__isnull=False, schliesst_am__lt=heute
    )
    anzahl = 0
    for stelle in faellig:
        Kundengruppe.objects.filter(ausgabestelle=stelle, aktiv=True).update(aktiv=False)
        stelle.aktiv = False
        stelle.save(update_fields=["aktiv"])
        anzahl += 1
    return anzahl
