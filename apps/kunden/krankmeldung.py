"""Krankmeldung eines Kunden (ADR 0075): eine Notiz mit Zeitraum und grobem Grund.

Zuschaltbar in den Einstellungen des Kundenstamms. Krank, Reha oder Krankenhaus sind
Gesundheitsdaten: Die Notiz verschwindet nach dem Ende aus der Anzeige und wird beim nächsten
täglichen Lauf gelöscht (``verwaiste_notizen_loeschen``). Wer in der Zeit für den Kunden abholen
darf, legt allein die Verwaltung beim Haushalt fest (Abholer), nicht die Krankmeldung.
"""

import datetime as dt

from django.utils import timezone

from apps.kunden.models import Haushalt, KundenEinstellungen, Notiz

LAENGSTENS_TAGE = 365


class Fehler(ValueError):
    pass


def eingeschaltet() -> bool:
    return KundenEinstellungen.laden().krankmeldung


def text(von: dt.date, bis: dt.date, grund_text: str, anmerkung: str = "") -> str:
    zeit = f"am {von:%d.%m.%Y}" if von == bis else f"vom {von:%d.%m.%Y} bis {bis:%d.%m.%Y}"
    satz = f"**Krank gemeldet** ({grund_text}) {zeit}."
    return f"{satz}\n{anmerkung}" if anmerkung else satz


def melden(h: Haushalt, benutzer, von, bis, grund: str, anmerkung: str = "") -> Notiz:
    """Legt die Krankmeldung an; prüft Zeitraum und Grund."""
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
        text=text(von, bis, gruende[grund], anmerkung), krank_von=von, krank_bis=bis,
        krank_grund=grund,
    )  # fmt: skip


def aktuelle(kundennummer: str, heute: dt.date | None = None) -> Notiz | None:
    """Die Krankmeldung, die heute gilt (die am längsten laufende)."""
    heute = heute or timezone.localdate()
    return (Notiz.objects.filter(kundennummer=kundennummer, krank_von__lte=heute,
                                 krank_bis__gte=heute).order_by("-krank_bis").first())  # fmt: skip
