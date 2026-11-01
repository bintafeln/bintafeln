"""Regeln des Fahrdienstes (ADR 0074): Plan je Tag, freie Leute für einen Ersatz, Benachrichtigung.

Ein Platz ist an einem Tag mit der Person der festen Besetzung belegt, außer ein Ersatz ist für
diesen Tag eingetragen. Fällt die Person aus, die den Platz an dem Tag hat, ist er „offen“.
"""

import datetime as dt
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.adressen.models import Adresse
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

# LEER: freier Gästeplatz über der Mindestbesetzung; UNBESETZT: Pflichtplatz ohne Person
OK, ERSETZT, OFFEN, LEER, UNBESETZT = "ok", "ersetzt", "offen", "leer", "unbesetzt"


@dataclass
class Platz:
    datum: dt.date
    tour: Tour
    platz: int
    stamm: Adresse | None = None  # Person der festen Besetzung
    ersatz: Ersatz | None = None
    ausfall: Ausfall | None = None  # der Person, die den Platz an dem Tag hat

    @property
    def wer(self) -> Adresse | None:
        """Wer den Platz an diesem Tag hat (Person; ein Gast hat keinen Eintrag)."""
        return self.ersatz.person if self.ersatz else self.stamm

    @property
    def gast(self) -> str:
        return self.ersatz.gast if self.ersatz and not self.ersatz.person_id else ""

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


def _ausfall(ausfaelle, person_id, datum, ersatz=None) -> Ausfall | None:
    return next((a for a in ausfaelle
                 if a.person_id == person_id and ausfallregeln.betrifft(a, datum, ersatz)),
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
    besetzung = {(b.tour_id, b.wochentag, b.platz): b.person
                 for b in Besetzung.objects.select_related("person")}  # fmt: skip
    von, bis = min(tage_liste), max(tage_liste)
    eingetragen = Ersatz.objects.filter(datum__range=(von, bis)).select_related("person")
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


def verfuegbar(datum: dt.date, nur_fahrer: bool = False) -> tuple[list, list]:
    """Wer an dem Tag einspringen kann: (Springer, weitere Fahrdienst-Personen).

    Nicht dabei: wer ausfällt, an dem Tag schon einen Platz hat, inaktiv ist oder dessen Konto
    gesperrt ist. ``nur_fahrer``: nur Personen, die fahren dürfen (für einen Fahrerplatz)."""
    belegt = eingesetzt(datum)
    belegt |= set(Ausfall.objects.filter(ausfallregeln.krank_am(datum))
                  .values_list("person_id", flat=True))  # fmt: skip
    tag = kuerzel(datum)
    # Pool über die Rolle (ADR 0097): Fahrer oder Beifahrer; für einen Fahrerplatz nur Fahrer.
    namen = [rollen.FAHRER] if nur_fahrer else [rollen.FAHRER, rollen.BEIFAHRER]
    pool = (Adresse.objects.filter(konto__is_active=True, konto__groups__name__in=namen)
            .distinct().order_by("nachname", "vorname"))  # fmt: skip
    springer_tage = {s.person_id: s.wochentage for s in Springer.objects.all()}
    springer, weitere = [], []
    for p in pool:
        if p.pk in belegt:
            continue
        if p.pk in springer_tage:
            # Springer stehen nur an ihren Tagen zur Wahl, auch nicht unter „weitere“
            w = springer_tage[p.pk]
            if not w.strip() or tag in wochentage(w):
                springer.append(p)
        else:
            weitere.append(p)
    return springer, weitere


def ersatz_eintragen(datum, tour, nr, person, von, gast: str = "") -> Ersatz | None:
    """Ersatz für einen Platz an einem Tag: eine Person oder ein Gast mit Namen; ohne beides wird
    er zurückgenommen."""
    Ersatz.objects.filter(datum=datum, tour=tour, platz=nr).delete()
    gast = gast.strip()[:100]
    if person is None and not gast:
        return None
    return Ersatz.objects.create(datum=datum, tour=tour, platz=nr, person=person,
                                 gast="" if person else gast, eingetragen_von=von)  # fmt: skip


def einsaetze(person, von: dt.date, bis: dt.date) -> list[Platz]:
    """Alle Plätze, die die Person zwischen ``von`` und ``bis`` hat (fest oder als Ersatz)."""
    if person is None:
        return []
    return [p for _, zeile in tage(fahrtage(von, bis)) for _, plaetze in zeile for p in plaetze
            if p.wer is not None and p.wer.pk == person.pk]  # fmt: skip


def einsatztage(person: Adresse) -> list[tuple[str, str]]:
    """Regelmäßige Einsätze der Person im Fahrdienst (feste Besetzungen) als lesbare Zeilen:
    (Wochentag, „Tour: Platz“), sortiert nach Wochentag, Tour und Platz."""
    if person is None:
        return []
    bes = Besetzung.objects.filter(person=person).select_related("tour")
    bes = sorted(bes, key=lambda b: (
        WOCHENTAGE.index(b.wochentag) if b.wochentag in WOCHENTAGE else 9,
        b.tour.reihenfolge, b.platz))  # fmt: skip
    return [(b.wochentag, f"Tour {b.tour}: {platz_name(b.platz)}") for b in bes]


def person_von(benutzer) -> Adresse | None:
    """Die Fahrdienst-Person (Adresse) zum angemeldeten Konto."""
    return Adresse.objects.filter(konto=benutzer).first() if benutzer else None


def darf_selbst_melden(benutzer) -> bool:
    return (FahrdienstEinstellungen.laden().selbst_melden
            and person_von(benutzer) is not None
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
    for p in einsaetze(ausfall.person, ausfall.von, ausfall.bis):
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
    telegram.benachrichtigen(e, f"🟨 Fahrdienst: {ausfall.person} fällt aus {zeit}.\n\n"
                                + einsaetze_text + link)  # fmt: skip
    if not an:
        return
    text = (
        f"{ausfall.person} fällt im Fahrdienst aus: {zeit} ({ausfall.get_grund_display()}).\n"
        + (f"Anmerkung: {ausfall.anmerkung}\n" if ausfall.anmerkung else "")
        + f"Eingetragen von: {ausfall.eingetragen_von}\n\n"
        + einsaetze_text
        + link
    )
    from apps.core import benachrichtigung

    # Der Ausfall steht ohnehin im Plan; die Mail kommt so oft, wie jede Person es wählt
    betreff = f"Fahrdienst: Ausfall {ausfall.person} {zeit}"
    benachrichtigung.melden("fahrdienst_ausfall", an, betreff, text, schluessel=ausfall.pk)


def ausfall_melden(person, von, bis, grund, anmerkung, eingetragen_von,
                   adresse: str = "") -> Ausfall:  # fmt: skip
    """Ausfall eintragen und die Fahrdienstleitung benachrichtigen. ``adresse``: Link zum Plan."""
    a = Ausfall.objects.create(person=person, von=von, bis=bis or von, grund=grund,
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
    frei = [p for p in einsaetze(a.person, a.gesund_ab, a.bis) if p.fehlt]
    text = (f"{a.person} ist ab {a.gesund_ab:%d.%m.%Y} wieder da und kann einspringen. Die "
            "eigenen Touren bis " f"{a.bis:%d.%m.%Y} bleiben frei bzw. beim Ersatz"
            + (f" ({len(frei)} noch ohne Ersatz)" if frei else "") + "."
            + (f"\n\nPlan: {adresse}" if adresse else ""))  # fmt: skip
    telegram.benachrichtigen(e, f"🟩 Fahrdienst: {text}")
    an = empfaenger() if mail.eingerichtet() else []
    if an:
        from apps.core import benachrichtigung

        betreff = f"Fahrdienst: {a.person} wieder da"
        benachrichtigung.melden("fahrdienst_gesund", an, betreff, text)


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Alte Ausfälle und Ersatz-Einträge löschen (Datensparsamkeit)."""
    heute = heute or timezone.localdate()
    monate = FahrdienstEinstellungen.laden().aufbewahren_monate
    jahr, monat = divmod(heute.year * 12 + heute.month - 1 - monate, 12)
    grenze = dt.date(jahr, monat + 1, 1)
    weg = Ausfall.objects.filter(bis__lt=grenze).delete()[0]
    return weg + Ersatz.objects.filter(datum__lt=grenze).delete()[0]
