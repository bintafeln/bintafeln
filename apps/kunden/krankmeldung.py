"""Abwesenheit eines Kunden (ADR 0075): eine Notiz mit Zeitraum und grobem Grund.

Zuschaltbar in den Einstellungen des Kundenstamms. Der Grund kann krank, Reha oder Krankenhaus
(Gesundheitsdaten, Anzeige „Krank gemeldet“) oder Urlaub, verhindert bzw. sonstiges (Anzeige
„Abwesend“) sein. Die Notiz verschwindet in allen Fällen nach dem Ende aus der Anzeige und wird
beim nächsten täglichen Lauf gelöscht (``verwaiste_notizen_loeschen``); kommt der Kunde innerhalb
der Zeit wieder, gilt sie als überholt. Wer in der Zeit für den Kunden abholen darf, legt allein
die Verwaltung beim Haushalt fest (Abholer), nicht die Abwesenheitsmeldung.
"""

import datetime as dt

from django.db.models import Exists, OuterRef
from django.utils import timezone

from apps.kunden.models import Abholung, Haushalt, KundenEinstellungen, Notiz

LAENGSTENS_TAGE = 365


class Fehler(ValueError):
    pass


def eingeschaltet() -> bool:
    return KundenEinstellungen.laden().krankmeldung


def _gesundheit(grund: str) -> bool:
    from apps.core.auswahl import KRANK_GRUENDE

    return grund in {wert for wert, _ in KRANK_GRUENDE}


def text(von: dt.date, bis: dt.date, grund: str, grund_text: str, anmerkung: str = "") -> str:
    zeit = f"am {von:%d.%m.%Y}" if von == bis else f"vom {von:%d.%m.%Y} bis {bis:%d.%m.%Y}"
    titel = "Krank gemeldet" if _gesundheit(grund) else "Abwesend"
    satz = f"**{titel}** ({grund_text}) {zeit}."
    return f"{satz}\n{anmerkung}" if anmerkung else satz


def melden(h: Haushalt, benutzer, von, bis, grund: str, anmerkung: str = "") -> Notiz:
    """Legt die Abwesenheitsmeldung an; prüft Zeitraum und Grund."""
    gruende = dict(Notiz._meta.get_field("krank_grund").choices)
    if grund not in gruende:
        raise Fehler("Bitte einen Grund wählen.")
    if von is None or bis is None:
        raise Fehler("Bitte Beginn und Ende angeben.")
    if bis < von:
        raise Fehler("Das Ende liegt vor dem Beginn.")
    if bis < timezone.localdate():
        raise Fehler("Das Ende liegt in der Vergangenheit.")
    if (bis - von).days >= LAENGSTENS_TAGE:
        raise Fehler(f"Höchstens {LAENGSTENS_TAGE} Tage.")
    anmerkung = anmerkung.strip()[:300]
    return Notiz.objects.create(
        kundennummer=h.kundennummer, benutzer=benutzer,
        verfasst_von=(benutzer.get_full_name() or benutzer.get_username())[:100],
        text=text(von, bis, grund, gruende[grund], anmerkung), krank_von=von, krank_bis=bis,
        krank_grund=grund,
    )  # fmt: skip


def aktuelle(kundennummer: str, heute: dt.date | None = None) -> Notiz | None:
    """Die Krankmeldung, die heute gilt (die am längsten laufende).

    Fällt weg, sobald der Kunde seit dem Beginn schon einmal abgeholt hat: Wer wieder kommt,
    ist offenbar nicht mehr krank, dann muss niemand die Meldung von Hand löschen.
    """
    heute = heute or timezone.localdate()
    return (Notiz.objects.filter(kundennummer=kundennummer, krank_von__lte=heute,
                                 krank_bis__gte=heute).exclude(_ueberholt())
            .order_by("-krank_bis").first())  # fmt: skip


def _ueberholt():
    """Bedingung: Es gibt seit ``krank_von`` schon eine Abholung desselben Haushalts."""
    abgeholt = Abholung.objects.filter(
        haushalt__kundennummer=OuterRef("kundennummer"), datum__gte=OuterRef("krank_von")
    )
    return Exists(abgeholt)
