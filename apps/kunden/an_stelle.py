"""Notizen der Verwaltung an eine Ausgabestelle (z. B. „Neuer Ausweis ist gedruckt …“).

Nur ausdrücklich gewählte Notizen gehen an die Ausgabestelle (``Notiz.an_stelle``): ein Haken
beim Schreiben, oder automatisch als Antwort, wenn die Ausgabestelle „Neuen Ausweis drucken“
gemeldet hat und der Ausweis gedruckt wird. Sie stehen auf der Startseite aller, die dort am
Einlass arbeiten, bis jemand „gelesen“ klickt; die Notiz selbst bleibt am Haushalt.
"""

import datetime as dt

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.kunden.models import Ausweisdruck, Haushalt, Nachricht, Notiz, NotizVorlage

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


AUSWEIS_TEXTE = (
    "Neuer Ausweis ist gedruckt und liegt im Schrank.",
    "Neuer Ausweis ist gedruckt und wird zur Ausgabestelle geschickt.",
)


def ausweis_notiz_bis(ab: dt.date | None = None) -> dt.date | None:
    """Wann die Notiz „Neuer Ausweis ist gedruckt“ von selbst in den Papierkorb geht; None, wenn
    die Tafel sie stehen lässt (``KundenEinstellungen.ausweis_notiz_tage`` = 0)."""
    from apps.kunden.models import KundenEinstellungen

    tage = KundenEinstellungen.laden().ausweis_notiz_tage
    return (ab or timezone.localdate()) + dt.timedelta(days=tage) if tage else None


def ausweis_text(h: Haushalt) -> str:
    stelle = h.kundengruppe.ausgabestelle if h.kundengruppe else None
    if stelle and stelle.ausweise_hier:
        return AUSWEIS_TEXTE[0]
    return AUSWEIS_TEXTE[1]


def ausweis_gedruckt(haushalte, benutzer, merken: bool = False) -> int:
    """Beim Ausweisdruck: Wer „Neuen Ausweis drucken“ gemeldet hat, bekommt die Antwort-Notiz;
    die Meldung ist erledigt, die gemeldete Notiz (Vorlage mit diesem Anliegen) gestrichen.
    ``merken``: den Druck als ``Ausweisdruck`` festhalten, damit er sich zurücknehmen lässt."""
    nummern = {h.kundennummer: h for h in haushalte}
    offen = list(Nachricht.objects.filter(kundennummer__in=nummern, anliegen=AUSWEIS,
                                          erledigt_am__isnull=True))  # fmt: skip
    if not offen:
        return 0
    jetzt = timezone.now()
    von = (benutzer.get_full_name() or benutzer.get_username())[:100]
    texte = list(NotizVorlage.objects.filter(melden=AUSWEIS).values_list("text", flat=True))
    beantwortet, antworten, gestrichen = set(), [], []
    bis = ausweis_notiz_bis()
    for n in offen:
        if n.kundennummer not in beantwortet:
            beantwortet.add(n.kundennummer)
            h = nummern[n.kundennummer]
            seit = min(m.erstellt_am for m in offen if m.kundennummer == n.kundennummer)
            seit -= dt.timedelta(minutes=5)
            alt = Notiz.objects.filter(kundennummer=h.kundennummer, text__in=texte,
                                       erstellt_am__gte=seit)  # fmt: skip
            gestrichen += [
                {"kundennummer": a.kundennummer, "text": a.text, "verfasst_von": a.verfasst_von,
                 "erstellt_am": a.erstellt_am.isoformat(), "benutzer": a.benutzer_id}
                for a in alt
            ]  # fmt: skip
            alt.delete()
            antwort = Notiz.objects.create(kundennummer=h.kundennummer, text=ausweis_text(h),
                                           verfasst_von=von, benutzer=benutzer,
                                           an_stelle=True, loeschen_am=bis)  # fmt: skip
            antworten.append(antwort.pk)
    Nachricht.objects.filter(pk__in=[n.pk for n in offen]).update(
        erledigt_am=jetzt, erledigt_von=benutzer.get_username()[:150])  # fmt: skip
    if merken:
        Ausweisdruck.objects.create(
            von=von,
            benutzer=benutzer,
            kundennummern=sorted(beantwortet),
            nachrichten=[n.pk for n in offen],
            antworten=antworten,
            gestrichen=gestrichen,
        )
    return len(beantwortet)


class DruckFehler(ValueError):
    pass


ZURUECK_TAGE = 14  # so lange steht ein Druck zum Zurücknehmen auf der Nachrichtenseite
ZURUECK_ANZAHL = 5


def letzte_drucke():
    """Die letzten Drucke gemeldeter Ausweise, die sich noch zurücknehmen lassen (ADR 0180):
    nicht zurückgenommen, nicht ausgeblendet, höchstens 14 Tage alt, der neueste zuerst."""
    seit = timezone.now() - dt.timedelta(days=ZURUECK_TAGE)
    offen = Ausweisdruck.objects.filter(bestaetigt_am__isnull=True, gedruckt_am__gte=seit,
                                        zurueckgenommen_am__isnull=True)  # fmt: skip
    return offen[:ZURUECK_ANZAHL]


def gemeldete(benutzer=None):
    """(alle, mit Rollstuhl-Ausweis): Haushalte mit offener Meldung „Neuen Ausweis drucken“ und
    davon die, die den anderen Ausweis für Schwerbehinderte bekommen."""
    from apps.kunden import merkmale, zugang

    nummern = Nachricht.objects.filter(anliegen=AUSWEIS, erledigt_am__isnull=True).values(
        "kundennummer"
    )
    alle = Haushalt.objects.filter(kundennummer__in=nummern)
    if benutzer is not None:
        alle = zugang.filtern(alle, benutzer)
    return alle, merkmale.mit_rollstuhl_ausweis(alle)


def _entscheiden(druck: Ausweisdruck, benutzer) -> Ausweisdruck:
    druck = Ausweisdruck.objects.select_for_update().get(pk=druck.pk)
    if not druck.offen:
        raise DruckFehler("Zu diesem Druck wurde schon entschieden.")
    druck.entschieden_von = (benutzer.get_full_name() or benutzer.get_username())[:150]
    return druck


@transaction.atomic
def druck_bestaetigen(druck: Ausweisdruck, benutzer) -> None:
    """Der Druck ist in Ordnung und soll nicht mehr zum Zurücknehmen angeboten werden."""
    druck = _entscheiden(druck, benutzer)
    druck.bestaetigt_am = timezone.now()
    druck.save()


@transaction.atomic
def druck_zuruecknehmen(druck: Ausweisdruck, benutzer) -> int:
    """Der Drucker hat nichts (oder nicht alles) ausgegeben: Die Meldungen sind wieder offen,
    die Notiz „Neuer Ausweis ist gedruckt …“ verschwindet bei den Ausgabestellen, die gestrichene
    Notiz „Neuen Ausweis drucken“ steht wieder am Haushalt. Liefert die Zahl der Meldungen."""
    from django.utils.dateparse import parse_datetime

    druck = _entscheiden(druck, benutzer)
    anzahl = Nachricht.objects.filter(pk__in=druck.nachrichten, anliegen=AUSWEIS).update(
        erledigt_am=None, erledigt_von="")  # fmt: skip
    Notiz.objects.filter(pk__in=druck.antworten).delete()
    for g in druck.gestrichen:
        Notiz.objects.create(
            kundennummer=g["kundennummer"],
            text=g["text"],
            verfasst_von=g.get("verfasst_von", ""),
            erstellt_am=parse_datetime(g.get("erstellt_am") or "") or timezone.now(),
            benutzer_id=g.get("benutzer") if _konto_gibt_es(g.get("benutzer")) else None,
        )
    druck.zurueckgenommen_am = timezone.now()
    druck.save()
    return anzahl


def _konto_gibt_es(pk) -> bool:
    from django.contrib.auth import get_user_model

    return bool(pk) and get_user_model().objects.filter(pk=pk).exists()


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
