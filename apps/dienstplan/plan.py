"""Regeln des Dienstplans (ADR 0077): Plan aus fester Besetzung, Ausfall und Ersatz je Tag.

Ein Platz ist eine Aufgabe an einem Datum. Wer ihn hat, ergibt sich aus dem Ersatz dieses Tages,
sonst aus der festen Besetzung; fällt diese Person aus, ist der Platz „offen“.
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
from apps.dienstplan.models import (
    Aufgabe,
    Ausfall,
    Besetzung,
    DienstplanEinstellungen,
    DienstStelle,
    Diensttag,
    Ersatz,
)
from apps.konten import rollen

# LEER: freier Platz einer Aufgabe, die nicht besetzt sein muss (z. B. Springer)
OK, ERSETZT, OFFEN, LEER, UNBESETZT = "ok", "ersetzt", "offen", "leer", "unbesetzt"


def kuerzel(datum: dt.date) -> str:
    return WOCHENTAGE[datum.weekday()]


@dataclass
class Platz:
    datum: dt.date
    aufgabe: Aufgabe
    stamm: Adresse | None = None
    ersatz: Ersatz | None = None
    ausfall: Ausfall | None = None  # der Person, die den Platz an dem Tag hat

    @property
    def wer(self) -> Adresse | None:
        return self.ersatz.helfer if self.ersatz else self.stamm

    @property
    def gast(self) -> str:
        return self.ersatz.gast if self.ersatz and not self.ersatz.helfer_id else ""

    @property
    def status(self) -> str:
        if self.gast:
            return ERSETZT
        if self.wer is None:
            return UNBESETZT if self.aufgabe.pflicht else LEER
        if self.ausfall:
            return OFFEN
        return ERSETZT if self.ersatz else OK

    @property
    def fehlt(self) -> bool:
        return self.status in (OFFEN, UNBESETZT)


def stellen():
    """Ausgabestellen, die beim Dienstplan mitmachen."""
    return (DienstStelle.objects.filter(aktiv=True, ausgabestelle__aktiv=True)
            .select_related("ausgabestelle").order_by("ausgabestelle__name"))  # fmt: skip


def ausgabetage(stelle: DienstStelle, von: dt.date, bis: dt.date, tag: str = "") -> list:
    """Daten zwischen ``von`` und ``bis``, an denen die Stelle Ausgabe hat (ohne Feiertage, wenn
    eingestellt); ``tag`` = nur dieser Wochentag."""
    from apps.core.models import TafelEinstellungen

    e = DienstplanEinstellungen.laden()
    land = TafelEinstellungen.laden().bundesland if e.feiertage_frei else ""
    tage = set(wochentage(stelle.tage))
    alle = [von + dt.timedelta(days=i) for i in range((bis - von).days + 1)]
    return [d for d in alle if kuerzel(d) in tage and (not tag or kuerzel(d) == tag)
            and not (land and ist_feiertag(d, land))]  # fmt: skip


def _ausfall(ausfaelle, helfer_id, datum, ersatz=None) -> Ausfall | None:
    return next((a for a in ausfaelle
                 if a.helfer_id == helfer_id and ausfallregeln.betrifft(a, datum, ersatz)),
                None)  # fmt: skip


def plaetze(daten: list[dt.date], aufgaben=None) -> dict[dt.date, list[Platz]]:
    """Je Datum die Plätze aller Aufgaben dieses Wochentags (bzw. der angegebenen Aufgaben)."""
    if not daten:
        return {}
    if aufgaben is None:
        aufgaben = Aufgabe.objects.filter(stelle__aktiv=True,
                                          wochentag__in={kuerzel(d) for d in daten})  # fmt: skip
        aufgaben = [
            a
            for a in aufgaben.select_related("stelle__ausgabestelle")
            if a.wochentag in wochentage(a.stelle.tage)
        ]  # nur echte Ausgabetage
    aufgaben = list(aufgaben)
    fest = {
        b.aufgabe_id: b.helfer
        for b in Besetzung.objects.filter(aufgabe__in=aufgaben).select_related("helfer__konto")
    }
    von, bis = min(daten), max(daten)
    ersatz = {
        (x.datum, x.aufgabe_id): x
        for x in Ersatz.objects.filter(
            datum__range=(von, bis), aufgabe__in=aufgaben
        ).select_related("helfer__konto")
    }
    ausfaelle = list(Ausfall.objects.filter(von__lte=bis, bis__gte=von))
    ergebnis = {}
    for datum in daten:
        liste = []
        for a in aufgaben:
            if a.wochentag != kuerzel(datum):
                continue
            p = Platz(datum, a, stamm=fest.get(a.pk), ersatz=ersatz.get((datum, a.pk)))
            if p.wer is not None:
                p.ausfall = _ausfall(ausfaelle, p.wer.pk, datum, p.ersatz)
            liste.append(p)
        ergebnis[datum] = liste
    return ergebnis


def monat(stelle: DienstStelle, tag: str, erster: dt.date, letzter: dt.date):
    """Plan wie auf Papier: Zeilen = Aufgaben des Wochentags, Spalten = Daten.
    Ergebnis: (Daten, [(Aufgabe, [Platz je Datum])])."""
    daten = ausgabetage(stelle, erster, letzter, tag)
    aufgaben = list(stelle.aufgaben.filter(wochentag=tag))
    je_tag = plaetze(daten, aufgaben)
    zeilen = [(a, [next(p for p in je_tag[d] if p.aufgabe.pk == a.pk) for d in daten])
              for a in aufgaben]  # fmt: skip
    return daten, zeilen


def platz(datum: dt.date, aufgabe: Aufgabe) -> Platz:
    return plaetze([datum], [aufgabe])[datum][0]


def eingesetzt(datum: dt.date) -> set[int]:
    """Helfer, die an dem Tag schon irgendwo einen Platz haben (nicht: ausgefallen)."""
    return {p.wer.pk for p in plaetze([datum])[datum] if p.wer is not None and not p.ausfall}


def verfuegbar(datum: dt.date) -> list[Adresse]:
    """Wer an dem Tag einspringen kann: aktiver Helfer, nicht ausgefallen, noch nirgends
    eingeteilt (und das Konto, falls vorhanden, nicht gesperrt)."""
    belegt = eingesetzt(datum) | set(
        Ausfall.objects.filter(ausfallregeln.krank_am(datum)).values_list("helfer_id", flat=True)
    )
    helfer = (Adresse.objects.filter(helfer=True, helfer_aktiv=True)
              .exclude(konto__is_active=False).exclude(pk__in=belegt)
              .select_related("konto"))  # fmt: skip
    return sorted(helfer, key=lambda h: h.name.lower())


def einsaetze(helfer: Adresse, von: dt.date, bis: dt.date) -> list[Platz]:
    """Alle Plätze der Person zwischen ``von`` und ``bis`` (fest oder als Ersatz)."""
    daten = [von + dt.timedelta(days=i) for i in range((bis - von).days + 1)]
    erlaubt = {s.pk: s for s in stellen()}
    ergebnis = []
    for datum, liste in plaetze(daten).items():
        for p in liste:
            s = erlaubt.get(p.aufgabe.stelle_id)
            if p.wer is not None and p.wer.pk == helfer.pk and s and datum in ausgabetage(
                    s, datum, datum):  # fmt: skip
                ergebnis.append(p)
    return ergebnis


def einsatztage(helfer: Adresse) -> list[tuple[str, str]]:
    """Regelmäßige Einsätze der Person im Dienstplan (feste Besetzungen) als lesbare Zeilen:
    (Wochentag, „Ausgabestelle: Aufgabe“), sortiert nach Wochentag und Stelle."""
    if helfer is None:
        return []
    bes = Besetzung.objects.filter(helfer=helfer).select_related("aufgabe__stelle__ausgabestelle")
    bes = sorted(bes, key=lambda b: (
        WOCHENTAGE.index(b.aufgabe.wochentag) if b.aufgabe.wochentag in WOCHENTAGE else 9,
        str(b.aufgabe.stelle.ausgabestelle), b.aufgabe.reihenfolge))  # fmt: skip
    return [(b.aufgabe.wochentag, f"{b.aufgabe.stelle.ausgabestelle}: {b.aufgabe}") for b in bes]


def helfer_von(benutzer) -> Adresse | None:
    """Die Helfer-Person (Adresse) zum angemeldeten Konto, falls aktiv."""
    if not benutzer:
        return None
    return Adresse.objects.filter(konto=benutzer, helfer=True, helfer_aktiv=True).first()


def darf_selbst_melden(benutzer) -> bool:
    return (DienstplanEinstellungen.laden().selbst_melden and helfer_von(benutzer) is not None
            and rollen.hat_recht(benutzer, "dienstplan.sehen"))  # fmt: skip


def planende() -> list[str]:
    konten = get_user_model().objects.filter(is_active=True).exclude(email="")
    konten = konten.filter(Q(is_superuser=True) | Q(groups__rolle__isnull=False)).distinct()
    return sorted({k.email for k in konten if rollen.hat_recht(k, "dienstplan.planen")})


def empfaenger(betroffen: list[Platz]) -> list[str]:
    """Die Teamleitungen der betroffenen Ausgabetage; ohne Teamleitung alle, die planen."""
    an, ohne = set(), False
    for p in betroffen:
        tag = Diensttag.objects.filter(stelle_id=p.aufgabe.stelle_id,
                                       wochentag=p.aufgabe.wochentag).first()  # fmt: skip
        if tag and tag.teamleitung and tag.teamleitung.mail:
            an.add(tag.teamleitung.mail)
        else:
            ohne = True
    return sorted(an | (set(planende()) if ohne or not betroffen else set()))


def _benachrichtigen(ausfall: Ausfall, adresse: str) -> None:
    """E-Mail (mit Grund) an die Teamleitung, Telegram (ohne Grund) an die eingestellten Chats."""
    from apps.core import mail, telegram

    e = DienstplanEinstellungen.laden()
    betroffen = einsaetze(ausfall.helfer, ausfall.von, ausfall.bis)
    an = empfaenger(betroffen) if mail.eingerichtet() else []
    if not an and not telegram.eingerichtet(e):
        return
    zeilen = []
    for p in betroffen:
        frei = ", ".join(str(h) for h in verfuegbar(p.datum)[:8]) or "niemand frei"
        zeilen.append(f"- {kuerzel(p.datum)} {p.datum:%d.%m.%Y}, {p.aufgabe.stelle}: "
                      f"{p.aufgabe}. Frei: {frei}")  # fmt: skip
    zeit = (f"am {ausfall.von:%d.%m.%Y}" if ausfall.von == ausfall.bis
            else f"vom {ausfall.von:%d.%m.%Y} bis {ausfall.bis:%d.%m.%Y}")  # fmt: skip
    dienste = ("Betroffene Dienste:\n" + "\n".join(zeilen) if zeilen
               else "Keine Dienste in diesem Zeitraum.")  # fmt: skip
    link = f"\n\nErsatz eintragen: {adresse}" if adresse else ""
    telegram.benachrichtigen(e, f"🟨 Dienstplan: {ausfall.helfer} fällt aus {zeit}.\n\n"
                                + dienste + link)  # fmt: skip
    if not an:
        return
    text = (f"{ausfall.helfer} fällt in der Ausgabe aus: {zeit} ({ausfall.get_grund_display()}).\n"
            + (f"Anmerkung: {ausfall.anmerkung}\n" if ausfall.anmerkung else "")
            + f"Eingetragen von: {ausfall.eingetragen_von}\n\n" + dienste + link)  # fmt: skip
    from apps.core import benachrichtigung

    # Der Ausfall steht ohnehin im Plan; die Mail kommt so oft, wie jede Person es wählt
    betreff = f"Dienstplan: Ausfall {ausfall.helfer} {zeit}"
    benachrichtigung.melden("dienstplan_ausfall", an, betreff, text, schluessel=ausfall.pk)


def ausfall_melden(helfer, von, bis, grund, anmerkung, eingetragen_von, adresse="") -> Ausfall:
    a = Ausfall.objects.create(helfer=helfer, von=von, bis=bis or von, grund=grund,
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

    e = DienstplanEinstellungen.laden()
    frei = [p for p in einsaetze(a.helfer, a.gesund_ab, a.bis) if p.fehlt]
    text = (f"{a.helfer} ist ab {a.gesund_ab:%d.%m.%Y} wieder da und kann einspringen. Die "
            "eigenen Dienste bis " f"{a.bis:%d.%m.%Y} bleiben frei bzw. beim Ersatz"
            + (f" ({len(frei)} noch ohne Ersatz)" if frei else "") + "."
            + (f"\n\nPlan: {adresse}" if adresse else ""))  # fmt: skip
    telegram.benachrichtigen(e, f"🟩 Dienstplan: {text}")
    an = empfaenger(einsaetze(a.helfer, a.gesund_ab, a.bis)) if mail.eingerichtet() else []
    if an:
        from apps.core import benachrichtigung

        betreff = f"Dienstplan: {a.helfer} wieder da"
        benachrichtigung.melden("dienstplan_gesund", an, betreff, text)


def ersatz_eintragen(datum, aufgabe, helfer, von, gast: str = "") -> Ersatz | None:
    """Ersatz für einen Platz an einem Tag; ohne Helfer und Gast wird er zurückgenommen."""
    Ersatz.objects.filter(datum=datum, aufgabe=aufgabe).delete()
    gast = gast.strip()[:100]
    if helfer is None and not gast:
        return None
    return Ersatz.objects.create(datum=datum, aufgabe=aufgabe, helfer=helfer,
                                 gast="" if helfer else gast, eingetragen_von=von)  # fmt: skip


# Aufgabe, Beginn, Ende, Anzahl, muss besetzt sein – wie auf dem Papierplan einer Freitags-Ausgabe
STANDARD_AUFGABEN = [
    ("Teamleitung", "09:00", "15:00", 1, True), ("Frühdienst", "08:00", "15:00", 2, True),
    ("Vorsortierung", "11:00", "15:00", 1, True), ("Kasse", "09:00", "15:00", 1, True),
    ("Brot", "11:30", "15:00", 1, True), ("Mopro", "11:30", "15:00", 1, True),
    ("Wurst / Fleisch", "11:30", "15:00", 1, True), ("Sonderartikel", "11:30", "15:00", 1, True),
    ("Obst", "11:30", "15:00", 4, True), ("Gemüse", "11:30", "15:00", 4, True),
    ("Springer", "11:30", "15:00", 3, False),
]  # fmt: skip


def standard_anlegen(stelle: DienstStelle, ersetzen: str = "") -> dict[str, int]:
    """Die Standard-Aufgaben für jeden Ausgabetag der Stelle, an dem noch keine Aufgaben stehen
    (ohne Besetzung). Mit ``ersetzen`` (ein Wochentag) werden nur an diesem Tag die vorhandenen
    Aufgaben samt Besetzung ersetzt. Liefert je Tag die Zahl der angelegten Aufgaben."""
    ergebnis = {}
    with transaction.atomic():
        for tag in wochentage(stelle.tage):
            if ersetzen:
                if tag != ersetzen:
                    continue
                stelle.aufgaben.filter(wochentag=tag).delete()
            elif stelle.aufgaben.filter(wochentag=tag).exists():
                continue
            nr = 0
            for name, von, bis, anzahl, pflicht in STANDARD_AUFGABEN:
                for _ in range(anzahl):
                    nr += 1
                    Aufgabe.objects.create(stelle=stelle, wochentag=tag, name=name,
                                           von=dt.time.fromisoformat(von),
                                           bis=dt.time.fromisoformat(bis), reihenfolge=nr,
                                           pflicht=pflicht)  # fmt: skip
            ergebnis[tag] = nr
    return ergebnis


def tag_kopieren(stelle: DienstStelle, von_tag: str, nach_tag: str) -> int:
    """Aufgaben (mit fester Besetzung) eines Wochentags auf einen anderen übernehmen; ersetzt
    die Aufgaben des Zieltags."""
    with transaction.atomic():
        stelle.aufgaben.filter(wochentag=nach_tag).delete()
        anzahl = 0
        for a in stelle.aufgaben.filter(wochentag=von_tag).select_related("besetzung"):
            besetzung = getattr(a, "besetzung", None)
            a.pk, a.wochentag = None, nach_tag
            a.save()
            if besetzung:
                Besetzung.objects.create(aufgabe=a, helfer=besetzung.helfer)
            anzahl += 1
    return anzahl


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Alte Ausfälle und Ersatz-Einträge löschen (Datensparsamkeit)."""
    heute = heute or timezone.localdate()
    monate = DienstplanEinstellungen.laden().aufbewahren_monate
    jahr, m = divmod(heute.year * 12 + heute.month - 1 - monate, 12)
    grenze = dt.date(jahr, m + 1, 1)
    weg = Ausfall.objects.filter(bis__lt=grenze).delete()[0]
    return weg + Ersatz.objects.filter(datum__lt=grenze).delete()[0]
