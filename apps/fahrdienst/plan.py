"""Regeln des Fahrdienstes (ADR 0074): Plan je Tag, freie Leute für einen Ersatz, Benachrichtigung.

Ein Platz ist an einem Tag mit der Person der festen Besetzung belegt, außer ein Ersatz ist für
diesen Tag eingetragen. Fällt die Person aus, die den Platz an dem Tag hat, ist er „offen“.
"""

import datetime as dt
import logging
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.core import ausfall as ausfallregeln
from apps.core.feiertage import ist_feiertag
from apps.fahrdienst.models import (
    Ausfall,
    Besetzung,
    Ersatz,
    FahrdienstEinstellungen,
    Springer,
    Tour,
    platz_name,
)
from apps.konten import rollen

log = logging.getLogger(__name__)

# LEER: freier Gästeplatz über der Mindestbesetzung; UNBESETZT: Pflichtplatz ohne Person
OK, ERSETZT, OFFEN, LEER, UNBESETZT = "ok", "ersetzt", "offen", "leer", "unbesetzt"


@dataclass
class Platz:
    datum: dt.date
    tour: Tour
    platz: int
    stamm: object = None  # Benutzer der festen Besetzung
    ersatz: Ersatz | None = None
    ausfall: Ausfall | None = None  # der Person, die den Platz an dem Tag hat

    @property
    def wer(self):
        """Wer den Platz an diesem Tag hat (Benutzer; ein Gast hat kein Konto)."""
        return self.ersatz.benutzer if self.ersatz else self.stamm

    @property
    def gast(self) -> str:
        return self.ersatz.gast if self.ersatz and not self.ersatz.benutzer_id else ""

    @property
    def status(self) -> str:
        if self.gast:
            return ERSETZT
        if self.wer is None:
            return LEER if self.platz > self.tour.mindestbesetzung else UNBESETZT
        if self.ausfall:
            return OFFEN
        return ERSETZT if self.ersatz else OK

    @property
    def fehlt(self) -> bool:
        """Muss noch jemand gefunden werden?"""
        return self.status in (OFFEN, UNBESETZT)

    @property
    def name(self) -> str:
        return platz_name(self.platz)


def kuerzel(datum: dt.date) -> str:
    return WOCHENTAGE[datum.weekday()]


def faehrt(datum: dt.date, e: FahrdienstEinstellungen, land: str = "") -> bool:
    """Fahren die Touren an diesem Tag?"""
    if kuerzel(datum) not in wochentage(e.fahrtage):
        return False
    return not (e.feiertage_frei and land and ist_feiertag(datum, land))


def fahrtage(von: dt.date, bis: dt.date, e: FahrdienstEinstellungen | None = None) -> list:
    from apps.core.models import TafelEinstellungen

    e = e or FahrdienstEinstellungen.laden()
    land = TafelEinstellungen.laden().bundesland
    tage = [von + dt.timedelta(days=i) for i in range((bis - von).days + 1)]
    return [t for t in tage if faehrt(t, e, land)]


def _ausfall(ausfaelle, benutzer_id, datum, ersatz=None) -> Ausfall | None:
    return next((a for a in ausfaelle
                 if a.benutzer_id == benutzer_id and ausfallregeln.betrifft(a, datum, ersatz)),
                None)  # fmt: skip


def touren(von: dt.date, bis: dt.date) -> list[Tour]:
    """Aktive Touren, die zwischen ``von`` und ``bis`` an mindestens einem Tag fahren
    („fährt ab … bis …“; leer = schon immer bzw. dauerhaft)."""
    return [t for t in Tour.objects.filter(aktiv=True)
            if (t.ab is None or t.ab <= bis) and (t.bis is None or von <= t.bis)]  # fmt: skip


def tage(tage_liste: list[dt.date]) -> list[tuple[dt.date, list[tuple[Tour, list[Platz]]]]]:
    """Plan für die angegebenen Tage: je Tag die Touren mit ihren Plätzen. An Tagen außerhalb
    von „fährt ab … bis …“ hat eine Tour keine Plätze (im Plan ein Strich)."""
    if not tage_liste:
        return []
    touren_ = touren(min(tage_liste), max(tage_liste))
    besetzung = {(b.tour_id, b.wochentag, b.platz): b.benutzer
                 for b in Besetzung.objects.select_related("benutzer")}  # fmt: skip
    von, bis = min(tage_liste), max(tage_liste)
    eingetragen = Ersatz.objects.filter(datum__range=(von, bis)).select_related("benutzer")
    ersatz = {(x.datum, x.tour_id, x.platz): x for x in eingetragen}
    ausfaelle = list(Ausfall.objects.filter(von__lte=bis, bis__gte=von))
    ergebnis = []
    for datum in tage_liste:
        zeile = []
        for tour in touren_:
            plaetze = []
            for nr in range(1, (tour.plaetze if tour.faehrt_am(datum) else 0) + 1):
                p = Platz(datum, tour, nr, stamm=besetzung.get((tour.pk, kuerzel(datum), nr)),
                          ersatz=ersatz.get((datum, tour.pk, nr)))  # fmt: skip
                if p.wer is not None:
                    p.ausfall = _ausfall(ausfaelle, p.wer.pk, datum, p.ersatz)
                plaetze.append(p)
            zeile.append((tour, plaetze))
        ergebnis.append((datum, zeile))
    return ergebnis


def platz(datum: dt.date, tour: Tour, nr: int) -> Platz:
    for t, plaetze in tage([datum])[0][1]:
        if t.pk == tour.pk:
            return plaetze[nr - 1]
    return Platz(datum, tour, nr)


def eingesetzt(datum: dt.date) -> set[int]:
    """Benutzer, die an dem Tag schon einen Platz haben (fest oder als Ersatz; nicht, wer
    ausfällt)."""
    return {p.wer.pk for _, zeile in tage([datum]) for _, plaetze in zeile for p in plaetze
            if p.wer is not None and not p.ausfall}  # fmt: skip


def verfuegbar(datum: dt.date) -> tuple[list, list]:
    """Wer an dem Tag einspringen kann: (Springer, weitere Fahrer und Beifahrer).

    Nicht dabei: wer ausfällt oder an dem Tag schon einen Platz hat."""
    belegt = eingesetzt(datum)
    belegt |= set(Ausfall.objects.filter(ausfallregeln.krank_am(datum))
                  .values_list("benutzer_id", flat=True))  # fmt: skip
    tag = kuerzel(datum)
    springer = [s.benutzer for s in Springer.objects.select_related("benutzer")
                if s.benutzer.is_active and s.benutzer.pk not in belegt
                and (not s.wochentage.strip() or tag in wochentage(s.wochentage))]  # fmt: skip
    # Springer stehen nur an ihren Tagen zur Wahl, auch nicht unter „weitere“
    schon = set(Springer.objects.values_list("benutzer_id", flat=True)) | belegt
    weitere = [b for b in get_user_model().objects.filter(
                   is_active=True, groups__name__in=[rollen.FAHRER, rollen.BEIFAHRER])
               .distinct().order_by("last_name", "first_name", "username")
               if b.pk not in schon]  # fmt: skip
    springer.sort(key=lambda b: (b.last_name, b.first_name, b.username))
    return springer, weitere


def ersatz_eintragen(datum, tour, nr, benutzer, von, gast: str = "") -> Ersatz | None:
    """Ersatz für einen Platz an einem Tag: ein Konto oder ein Gast mit Namen; ohne beides wird
    er zurückgenommen."""
    Ersatz.objects.filter(datum=datum, tour=tour, platz=nr).delete()
    gast = gast.strip()[:100]
    if benutzer is None and not gast:
        return None
    return Ersatz.objects.create(datum=datum, tour=tour, platz=nr, benutzer=benutzer,
                                 gast="" if benutzer else gast, eingetragen_von=von)  # fmt: skip


def einsaetze(benutzer, von: dt.date, bis: dt.date) -> list[Platz]:
    """Alle Plätze, die die Person zwischen ``von`` und ``bis`` hat (fest oder als Ersatz)."""
    return [p for _, zeile in tage(fahrtage(von, bis)) for _, plaetze in zeile for p in plaetze
            if p.wer is not None and p.wer.pk == benutzer.pk]  # fmt: skip


def darf_selbst_melden(benutzer) -> bool:
    return (FahrdienstEinstellungen.laden().selbst_melden
            and rollen.hat_recht(benutzer, "fahrdienst.sehen"))  # fmt: skip


def empfaenger() -> list[str]:
    """Mailadressen für Ausfälle: die eingestellten Personen, sonst alle, die planen dürfen."""
    gewaehlt = FahrdienstEinstellungen.laden().benachrichtigen.filter(is_active=True)
    if gewaehlt.exists():
        return sorted({b.email for b in gewaehlt if b.email})
    konten = get_user_model().objects.filter(is_active=True).exclude(email="")
    konten = konten.filter(Q(is_superuser=True) | Q(groups__rolle__isnull=False)).distinct()
    return sorted({k.email for k in konten if rollen.hat_recht(k, "fahrdienst.planen")})


def _benachrichtigen(ausfall: Ausfall, adresse: str) -> None:
    """E-Mail (mit Grund) und Telegram (ohne Grund) an die Fahrdienstleitung."""
    from apps.core import mail, telegram

    e = FahrdienstEinstellungen.laden()
    an = empfaenger() if mail.eingerichtet() else []
    if not an and not telegram.eingerichtet(e):
        return
    zeilen = []
    for p in einsaetze(ausfall.benutzer, ausfall.von, ausfall.bis):
        springer, _ = verfuegbar(p.datum)
        frei = ", ".join(str(b) for b in springer) or "keiner frei"
        zeilen.append(f"- {WOCHENTAGE[p.datum.weekday()]} {p.datum:%d.%m.%Y}, Tour {p.tour}, "
                      f"{p.name}. Freie Springer: {frei}")  # fmt: skip
    zeit = (f"am {ausfall.von:%d.%m.%Y}" if ausfall.von == ausfall.bis
            else f"vom {ausfall.von:%d.%m.%Y} bis {ausfall.bis:%d.%m.%Y}")  # fmt: skip
    einsaetze_text = ("Betroffene Einsätze:\n" + "\n".join(zeilen) if zeilen
                      else "Keine Einsätze in diesem Zeitraum.")  # fmt: skip
    link = f"\n\nErsatz eintragen: {adresse}" if adresse else ""
    # Telegram läuft über fremde Server: ohne Grund und Anmerkung (z. B. „krank“)
    telegram.benachrichtigen(e, f"🟨 Fahrdienst: {ausfall.benutzer} fällt aus {zeit}.\n\n"
                                + einsaetze_text + link)  # fmt: skip
    if not an:
        return
    text = (
        f"{ausfall.benutzer} fällt im Fahrdienst aus: {zeit} ({ausfall.get_grund_display()}).\n"
        + (f"Anmerkung: {ausfall.anmerkung}\n" if ausfall.anmerkung else "")
        + f"Eingetragen von: {ausfall.eingetragen_von}\n\n"
        + einsaetze_text
        + link
    )
    try:
        mail.senden(f"Fahrdienst: Ausfall {ausfall.benutzer} {zeit}", text, an)
    except mail.MailFehler as fehler:  # Der Ausfall steht trotzdem im Plan
        log.warning("Fahrdienst-Ausfall %s: Mail nicht gesendet: %s", ausfall.pk, fehler)


def ausfall_melden(benutzer, von, bis, grund, anmerkung, eingetragen_von,
                   adresse: str = "") -> Ausfall:  # fmt: skip
    """Ausfall eintragen und die Fahrdienstleitung benachrichtigen. ``adresse``: Link zum Plan."""
    a = Ausfall.objects.create(benutzer=benutzer, von=von, bis=bis or von, grund=grund,
                               anmerkung=anmerkung, eingetragen_von=eingetragen_von)  # fmt: skip
    transaction.on_commit(lambda: _benachrichtigen(a, adresse))
    return a


def gesund_melden(a: Ausfall, ab: dt.date, adresse: str = "") -> bool:
    """Wieder gesund ab ``ab`` (ADR 0085): Die Person kann einspringen, ihre festen Plätze bleiben
    frei. False, wenn der Ausfall dann schon vorbei ist."""
    if ab > a.bis or a.gesund_ab:
        return False
    a.gesund_ab = max(ab, a.von)
    a.save(update_fields=["gesund_ab"])  # wer es war, hält das Änderungsprotokoll fest
    transaction.on_commit(lambda: _gesund_benachrichtigen(a, adresse))
    return True


def _gesund_benachrichtigen(a: Ausfall, adresse: str) -> None:
    from apps.core import mail, telegram

    e = FahrdienstEinstellungen.laden()
    frei = [p for p in einsaetze(a.benutzer, a.gesund_ab, a.bis) if p.fehlt]
    text = (f"{a.benutzer} ist ab {a.gesund_ab:%d.%m.%Y} wieder da und kann einspringen. Die "
            "eigenen Touren bis " f"{a.bis:%d.%m.%Y} bleiben frei bzw. beim Ersatz"
            + (f" ({len(frei)} noch ohne Ersatz)" if frei else "") + "."
            + (f"\n\nPlan: {adresse}" if adresse else ""))  # fmt: skip
    telegram.benachrichtigen(e, f"🟩 Fahrdienst: {text}")
    an = empfaenger() if mail.eingerichtet() else []
    if an:
        try:
            mail.senden(f"Fahrdienst: {a.benutzer} wieder da", text, an)
        except mail.MailFehler as fehler:
            log.warning("Fahrdienst-Gesundmeldung %s: Mail nicht gesendet: %s", a.pk, fehler)


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Alte Ausfälle und Ersatz-Einträge löschen (Datensparsamkeit)."""
    heute = heute or timezone.localdate()
    monate = FahrdienstEinstellungen.laden().aufbewahren_monate
    jahr, monat = divmod(heute.year * 12 + heute.month - 1 - monate, 12)
    grenze = dt.date(jahr, monat + 1, 1)
    weg = Ausfall.objects.filter(bis__lt=grenze).delete()[0]
    return weg + Ersatz.objects.filter(datum__lt=grenze).delete()[0]
