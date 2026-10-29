"""Gemeinsame Regeln für Ausfälle in Dienstplan und Fahrdienst (ADR 0085).

Ein Ausfall gilt von ``von`` bis ``bis``. Meldet sich jemand vorher wieder gesund, bekommt der
Ausfall ``gesund_ab``: Ab dann kann die Person wieder einspringen, ihre festen Plätze bleiben
aber frei (bzw. beim Ersatz). Sie wird nie automatisch wieder eingetragen.
"""

import datetime as dt

from django.db.models import Q

from apps.core.auswahl import AUSFALL_DAUER

LAENGSTENS = dt.timedelta(days=366)


def bis_berechnen(von: dt.date, dauer: str, bis_text: str = "") -> dt.date:
    """Letzter Tag des Ausfalls aus der Wahl am Monitor; ``ValueError`` mit Meldung."""
    if dauer in ("", "tag"):
        return von
    if dauer == "bis":
        try:
            bis = dt.date.fromisoformat(bis_text)
        except ValueError:
            raise ValueError("Bitte das Datum wählen, bis wann der Ausfall gilt.") from None
        if bis < von:
            raise ValueError("Das Datum „bis“ liegt vor dem Tag des Ausfalls.")
        if bis - von > LAENGSTENS:
            raise ValueError("Bitte höchstens ein Jahr im Voraus eintragen.")
        return bis
    if dauer in dict(AUSFALL_DAUER) and dauer.startswith("w"):
        return von + dt.timedelta(days=7 * int(dauer[1:]) - 1)
    raise ValueError("Bitte wählen, wie lange der Ausfall gilt.")


def deckt(ausfall, datum: dt.date, nur_krank: bool = False) -> bool:
    """Gilt der Ausfall an ``datum``? ``nur_krank``: nur, solange die Person nicht wieder gesund
    gemeldet ist (für „kann einspringen“); sonst auch danach (der feste Platz bleibt frei)."""
    if not ausfall.von <= datum <= ausfall.bis:
        return False
    return not (nur_krank and ausfall.gesund_ab and datum >= ausfall.gesund_ab)


def betrifft(ausfall, datum: dt.date, ersatz=None) -> bool:
    """Fällt die Person auf diesem Platz aus? Auf dem festen Platz: im ganzen Zeitraum, auch nach
    „wieder gesund“. Als Ersatz: solange sie krank ist; ein Einspringen, das schon vor der
    Krankmeldung eingetragen war, bleibt aber abgesagt (nie automatisch zurück)."""
    if ersatz is None or (ersatz.eingetragen_am and ausfall.eingetragen_am
                          and ersatz.eingetragen_am <= ausfall.eingetragen_am):  # fmt: skip
        return deckt(ausfall, datum)
    return deckt(ausfall, datum, nur_krank=True)


def krank_am(datum: dt.date) -> Q:
    """Filter: Ausfälle, wegen derer jemand an ``datum`` nicht einspringen kann."""
    return Q(von__lte=datum, bis__gte=datum) & (Q(gesund_ab__isnull=True) | Q(gesund_ab__gt=datum))


def gesund_text(ausfall) -> str:
    return f"wieder da ab {ausfall.gesund_ab:%d.%m.%Y}" if ausfall.gesund_ab else ""
