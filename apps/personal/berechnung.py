"""Berechnungen zu Urlaub und Stundenkonto (ADR 0018).

Vereinfachungen, die bewusst sichtbar dokumentiert sind:
- Arbeitstage sind Montag bis Freitag ohne die gesetzlichen Feiertage des Bundeslands aus den
  Tafel-Einstellungen (ADR 0019). Abweichungen (halbe Tage, regionale Feiertage) trägt man bei
  der Abwesenheit bzw. als Korrekturstunden ein.
- Tagessoll = Wochenstunden / 5.
"""

import calendar
import datetime as dt
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from apps.core.feiertage import ist_feiertag
from apps.core.models import TafelEinstellungen
from apps.konten.models import PersonalEinstellungen
from apps.personal.models import Abwesenheit

NULL = Decimal("0")


def bundesland() -> str:
    return TafelEinstellungen.laden().bundesland


def ist_arbeitstag(tag: dt.date, land: str) -> bool:
    return tag.weekday() < 5 and not ist_feiertag(tag, land)


def werktage(von: dt.date, bis: dt.date, land: str | None = None) -> int:
    """Arbeitstage Montag bis Freitag ohne Feiertage im Zeitraum (beide Tage eingeschlossen)."""
    land = bundesland() if land is None else land
    tage = (bis - von).days + 1
    return sum(1 for i in range(max(tage, 0)) if ist_arbeitstag(von + dt.timedelta(days=i), land))


def arbeitstage(abwesenheit, land: str | None = None) -> Decimal:
    if abwesenheit.tage is not None:
        return abwesenheit.tage
    return Decimal(werktage(abwesenheit.von, abwesenheit.bis, land))


def vertrag_am(vertraege, datum):
    return next((v for v in vertraege if v.gilt_am(datum)), None)


def _monatsende(jahr, monat) -> dt.date:
    return dt.date(jahr, monat, calendar.monthrange(jahr, monat)[1])


def anspruch_berechnet(vertraege, jahr: int) -> Decimal:
    """Ein Zwölftel des Jahresurlaubs je vollem Monat mit Vertrag; ab einem halben Tag wird auf
    volle Tage aufgerundet (§ 5 Abs. 2 BUrlG)."""
    summe = NULL
    for monat in range(1, 13):
        anfang, ende = dt.date(jahr, monat, 1), _monatsende(jahr, monat)
        v = next((v for v in vertraege if v.gilt_am(anfang) and v.gilt_am(ende)), None)
        if v:
            summe += v.urlaubstage / 12
    ganz = summe.to_integral_value(rounding="ROUND_FLOOR")
    if summe - ganz >= Decimal("0.5"):
        return ganz + 1
    return summe.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)


def verfall_standard(jahr: int) -> dt.date:
    e = PersonalEinstellungen.laden()
    tag = min(e.urlaub_verfall_tag, calendar.monthrange(jahr, e.urlaub_verfall_monat)[1])
    return dt.date(jahr, e.urlaub_verfall_monat, tag)


@dataclass
class Urlaubsstand:
    jahr: int
    anspruch: Decimal
    uebertrag: Decimal  # Rest aus dem Vorjahr
    verfall_am: dt.date
    genommen: Decimal
    verfaellt: Decimal  # Teil des Übertrags, der am Verfallsdatum verfällt (falls nicht genommen)
    verfallen: Decimal  # davon bereits verfallen (heute liegt nach dem Verfallsdatum)
    rest: Decimal


def urlaub(benutzer, jahr: int, heute: dt.date) -> Urlaubsstand:
    """Stand des Urlaubs im Jahr. Genommene Tage verbrauchen zuerst den Übertrag aus dem Vorjahr,
    soweit sie bis zum Verfallsdatum beginnen; danach verfällt der übrige Übertrag."""
    vertraege = list(benutzer.vertraege.all())
    urlaube = [a for a in benutzer.abwesenheiten.all() if a.art == Abwesenheit.Art.URLAUB]
    abweichend = {u.jahr: u for u in benutzer.urlaubsjahre.all()}
    jahre = [v.beginn.year for v in vertraege] + [a.von.year for a in urlaube]
    land = bundesland()
    uebertrag = NULL
    stand = None
    for j in range(min(jahre, default=jahr), jahr + 1):
        a = abweichend.get(j)
        anspruch = a.anspruch if a and a.anspruch is not None else anspruch_berechnet(vertraege, j)
        verfall = a.verfall_am if a and a.verfall_am else verfall_standard(j)
        im_jahr = [u for u in urlaube if u.von.year == j]
        genommen = sum((arbeitstage(u, land) for u in im_jahr), NULL)
        bis_verfall = sum((arbeitstage(u, land) for u in im_jahr if u.von <= verfall), NULL)
        verfaellt = uebertrag - min(uebertrag, bis_verfall)
        verfallen = verfaellt if heute > verfall else NULL
        stand = Urlaubsstand(
            jahr=j,
            anspruch=anspruch,
            uebertrag=uebertrag,
            verfall_am=verfall,
            genommen=genommen,
            verfaellt=verfaellt,
            verfallen=verfallen,
            rest=anspruch + uebertrag - genommen - verfallen,
        )
        # Zum Jahresende ist der Übertrag auf jeden Fall verfallen.
        uebertrag = max(anspruch + uebertrag - genommen - verfaellt, NULL)
    return stand


@dataclass
class Monat:
    monat: dt.date
    soll: Decimal
    ist: Decimal
    urlaub: Decimal
    krank: Decimal

    @property
    def saldo(self) -> Decimal:
        return self.ist + self.urlaub + self.krank - self.soll


def _monat(jahr, monat, vertraege, abwesenheiten, stunden, heute, land) -> Monat:
    anfang, ende = dt.date(jahr, monat, 1), min(_monatsende(jahr, monat), heute)
    soll = NULL
    for i in range((ende - anfang).days + 1):
        tag = anfang + dt.timedelta(days=i)
        v = vertrag_am(vertraege, tag)
        if v and ist_arbeitstag(tag, land):
            soll += v.tagessoll
    gutschrift = {Abwesenheit.Art.URLAUB: NULL, Abwesenheit.Art.KRANK: NULL}
    for a in abwesenheiten:
        if anfang <= a.von <= ende:
            v = vertrag_am(vertraege, a.von)
            if v:
                gutschrift[a.art] += arbeitstage(a, land) * v.tagessoll
    ist = sum((s.stunden for s in stunden if anfang <= s.datum <= ende), NULL)
    return Monat(
        monat=anfang,
        soll=soll,
        ist=ist,
        urlaub=gutschrift[Abwesenheit.Art.URLAUB],
        krank=gutschrift[Abwesenheit.Art.KRANK],
    )


@dataclass
class Stundenkonto:
    vorjahre: Decimal  # Saldo bis Ende des Vorjahres
    monate: list[Monat]

    @property
    def saldo(self) -> Decimal:
        return self.vorjahre + sum((m.saldo for m in self.monate), NULL)


def stundenkonto(benutzer, jahr: int, heute: dt.date) -> Stundenkonto:
    """Soll, Ist und Gutschriften für Urlaub und Krankheit je Monat bis heute, mit Vorjahren."""
    vertraege = list(benutzer.vertraege.all())
    abwesenheiten = list(benutzer.abwesenheiten.all())
    stunden = list(benutzer.stunden.all())
    erstes = min((v.beginn for v in vertraege), default=None)
    vorjahre, monate = NULL, []
    if erstes is None:
        return Stundenkonto(vorjahre, monate)
    land = bundesland()
    j, m = erstes.year, erstes.month
    while (j, m) <= (jahr, 12) and dt.date(j, m, 1) <= heute:
        werte = _monat(j, m, vertraege, abwesenheiten, stunden, heute, land)
        if j < jahr:
            vorjahre += werte.saldo
        else:
            monate.append(werte)
        j, m = (j + 1, 1) if m == 12 else (j, m + 1)
    return Stundenkonto(vorjahre, monate)
