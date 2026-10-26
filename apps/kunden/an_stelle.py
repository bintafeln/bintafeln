"""Notizen der Verwaltung an eine Ausgabestelle (z. B. „Neuer Ausweis ist gedruckt …“).

Nur ausdrücklich gewählte Notizen gehen an die Ausgabestelle (``Notiz.an_stelle``): ein Haken
beim Schreiben, oder automatisch als Antwort, wenn die Ausgabestelle „Neuen Ausweis drucken“
gemeldet hat und der Ausweis gedruckt wird. Sie stehen auf der Startseite aller, die dort am
Einlass arbeiten, bis jemand „gelesen“ klickt; die Notiz selbst bleibt am Haushalt.
"""

import datetime as dt

from django.db.models import Q
from django.utils import timezone

from apps.kunden.models import Haushalt, Nachricht, Notiz, NotizVorlage

AUSWEIS = "ausweis"  # Anliegen „Neuen Ausweis drucken“ (apps/core/auswahl.py)


def offene(stelle):
    """Ungelesene Notizen an diese Ausgabestelle, älteste zuerst."""
    if stelle is None:
        return Notiz.objects.none()
    nummern = Haushalt.objects.filter(kundengruppe__ausgabestelle=stelle).values("kundennummer")
    fuer = Q(fuer_stelle=stelle) | Q(fuer_stelle__isnull=True, kundennummer__in=nummern)
    return Notiz.objects.filter(fuer, an_stelle=True, gelesen_am__isnull=True).order_by(
        "erstellt_am")  # fmt: skip


def gelesen(notiz: Notiz, benutzer) -> None:
    notiz.gelesen_am = timezone.now()
    notiz.gelesen_von = (benutzer.get_full_name() or benutzer.get_username())[:150]
    notiz.save(update_fields=["gelesen_am", "gelesen_von"])


def ausweis_text(h: Haushalt) -> str:
    stelle = h.kundengruppe.ausgabestelle if h.kundengruppe else None
    if stelle and stelle.ausweise_hier:
        return "Neuer Ausweis ist gedruckt und liegt im Schrank."
    return "Neuer Ausweis ist gedruckt und wird zur Ausgabestelle geschickt."


def ausweis_gedruckt(haushalte, benutzer) -> int:
    """Beim Ausweisdruck: Wer „Neuen Ausweis drucken“ gemeldet hat, bekommt die Antwort-Notiz;
    die Meldung ist erledigt, die gemeldete Notiz (Vorlage mit diesem Anliegen) gestrichen."""
    nummern = {h.kundennummer: h for h in haushalte}
    offen = list(Nachricht.objects.filter(kundennummer__in=nummern, anliegen=AUSWEIS,
                                          erledigt_am__isnull=True))  # fmt: skip
    if not offen:
        return 0
    jetzt = timezone.now()
    von = (benutzer.get_full_name() or benutzer.get_username())[:100]
    texte = list(NotizVorlage.objects.filter(melden=AUSWEIS).values_list("text", flat=True))
    beantwortet = set()
    for n in offen:
        if n.kundennummer not in beantwortet:
            beantwortet.add(n.kundennummer)
            h = nummern[n.kundennummer]
            seit = min(m.erstellt_am for m in offen if m.kundennummer == n.kundennummer)
            seit -= dt.timedelta(minutes=5)
            Notiz.objects.filter(kundennummer=h.kundennummer, text__in=texte,
                                 erstellt_am__gte=seit).delete()  # fmt: skip
            Notiz.objects.create(kundennummer=h.kundennummer, text=ausweis_text(h),
                                 verfasst_von=von, benutzer=benutzer, an_stelle=True)  # fmt: skip
    Nachricht.objects.filter(pk__in=[n.pk for n in offen]).update(
        erledigt_am=jetzt, erledigt_von=benutzer.get_username()[:150])  # fmt: skip
    return len(beantwortet)


def antworten(nachricht: Nachricht, text: str, benutzer) -> Notiz:
    """Antwort der Verwaltung auf eine Nachricht: Notiz an die Ausgabestelle, die geschrieben hat
    (Startseite); die Nachricht ist damit erledigt."""
    von = (benutzer.get_full_name() or benutzer.get_username())[:100]
    notiz = Notiz.objects.create(
        kundennummer=nachricht.kundennummer,
        verfasst_von=von,
        benutzer=benutzer,
        an_stelle=True,
        fuer_stelle=nachricht.stelle,
        text=f"Antwort zu „{nachricht.get_anliegen_display()}“: {text.strip()}"[:1000],
    )
    nachricht.erledigt_am = timezone.now()
    nachricht.erledigt_von = benutzer.get_username()[:150]
    nachricht.save(update_fields=["erledigt_am", "erledigt_von"])
    return notiz
