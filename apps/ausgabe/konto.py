"""Kundenkonto: Buchen am Einlass, Vorschlag für Vorauszahlungen, Fristen (ADR 0014).

Der Kontostand steht in ``Haushalt.kontostand`` (Anfangsstand aus dem Import) und ändert sich
mit jeder Buchung um ``haben − soll``. Alle Änderungen laufen über die Funktionen hier, in einer
Transaktion mit gesperrter Haushaltszeile.
"""

import calendar
import datetime as dt
import re
from dataclasses import dataclass, field
from decimal import Decimal

from auditlog.context import disable_auditlog
from django.db import transaction
from django.utils import timezone

from apps.ausgabe.ampel import WOCHENTAGE
from apps.ausgabe.models import (
    AusgabeEinstellungen,
    BeitragsfreierZeitraum,
    Buchung,
    Schliesszeit,
)
from apps.core.feiertage import feiertage, ist_feiertag
from apps.core.models import TafelEinstellungen
from apps.kunden.models import Haushalt, abholfrist_beginn

NULL = Decimal("0.00")
MONATE = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]  # fmt: skip


class KontoFehler(ValueError):
    pass


def euro(betrag: Decimal) -> str:
    """1234.5 → '1.234,50 €'"""
    text = f"{betrag:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} €"


@dataclass
class Zahlung:
    """Ergebnis einer gebuchten Abholung für die Anzeige am Einlass."""

    bar: Decimal  # was auf dem Tisch lag
    vom_konto: Decimal  # aus Guthaben verrechnet
    angeschrieben: Decimal
    gutgeschrieben: Decimal  # mehr gezahlt als der Beitrag: als Guthaben gebucht
    kontostand: Decimal


UEBERZAHLUNG = "Überzahlung bei der Abholung"


def _gesperrt(haushalt) -> Haushalt:
    return Haushalt.objects.select_for_update().get(pk=haushalt.pk)


def _buchen(h: Haushalt, **felder) -> Buchung:
    buchung = Buchung.objects.create(haushalt=h, kundennummer=h.kundennummer, **felder)
    h.kontostand = (h.kontostand or NULL) + buchung.wirkung
    h.save(update_fields=["kontostand"])
    return buchung


def bar_vorschlag(beitrag: Decimal, kontostand) -> Decimal:
    """Was bar zu zahlen ist, wenn ein vorhandenes Guthaben zuerst verrechnet wird."""
    return max(beitrag - max(kontostand or NULL, NULL), NULL)


@transaction.atomic
def abholung_buchen(abholung, beitrag, bar, einstellungen, stelle, von) -> Zahlung:
    """Bucht eine Abholung mit genau dem Betrag, der gezahlt wurde.

    Reicht das Bargeld nicht, wird Guthaben verrechnet, danach angeschrieben (wenn erlaubt).
    Mehr als den Beitrag bucht eine eigene Einzahlung als Guthaben, damit die Kasse die
    Beiträge richtig zählt.
    """
    if bar is None or bar < 0:
        raise KontoFehler("Bitte eintragen, wie viel bar gezahlt wurde (auch 0).")
    h = _gesperrt(abholung.haushalt)
    fuer_beitrag = min(bar, beitrag)
    rest = beitrag - fuer_beitrag
    vom_konto = min(rest, max(h.kontostand or NULL, NULL))
    angeschrieben = rest - vom_konto
    if angeschrieben and not einstellungen.anschreiben_erlaubt:
        raise KontoFehler(
            f"Es fehlen {euro(angeschrieben)}. Anschreiben ist in den Einstellungen nicht "
            "erlaubt; bitte den fehlenden Betrag bar annehmen."
        )
    if angeschrieben:
        zahlweise = Buchung.Zahlweise.ANSCHREIBEN
    elif vom_konto:
        zahlweise = Buchung.Zahlweise.GUTHABEN
    else:
        zahlweise = Buchung.Zahlweise.BAR
    gemeinsam = {"datum": abholung.datum, "ausgabestelle": stelle, "eingetragen_von": von}
    if beitrag:
        _buchen(h, art=Buchung.Art.ABHOLUNG, zahlweise=zahlweise, soll=beitrag,
                haben=fuer_beitrag, bar=fuer_beitrag, abholung=abholung, **gemeinsam)  # fmt: skip
    ueber = bar - fuer_beitrag
    if ueber:
        um = f" um {abholung.uhrzeit:%H:%M}" if abholung.uhrzeit else ""
        _buchen(h, art=Buchung.Art.EINZAHLUNG, haben=ueber, bar=ueber,
                bemerkung=f"{UEBERZAHLUNG}{um}", **gemeinsam)  # fmt: skip
    return Zahlung(
        bar=bar,
        vom_konto=vom_konto,
        angeschrieben=angeschrieben,
        gutgeschrieben=ueber,
        kontostand=h.kontostand or NULL,
    )


BEITRAG_AUS_IMPORT = "Beitrag laut Import"  # alte, falsche Bar-Buchungen (entfernt mit 0014)
AUS_KONTOSTAND = "laut Import (Kontostand)"


def _import_buchen(h: Haushalt, datum, uhrzeit=None, stelle=None, von="", **felder) -> Buchung:
    """Wie ``_buchen``, aber als Import (Tag und Zeit der Abholung, gekennzeichnet)."""
    zeitpunkt = timezone.make_aware(dt.datetime.combine(datum, uhrzeit or dt.time(12, 0)))
    felder.setdefault("bemerkung", AUS_KONTOSTAND)
    return _buchen(h, datum=datum, ausgabestelle=stelle, zeitpunkt=zeitpunkt,
                   eingetragen_von=von, importiert=True, **felder)  # fmt: skip


def mit_bar_gezahlt(haushalt, abholungen) -> list:
    """Hängt an jede Abholung ``bar_gezahlt``: was der Kunde an dem Tag bar auf den Tisch gelegt
    hat (Bareinnahmen aller Buchungen des Tages – Beitrag und Einzahlung), ``None`` ohne Buchung.
    Nicht der Beitrag: Wer am Monatsanfang für alle Abholungen zahlt, zahlt danach 0 €."""
    from django.db.models import Sum

    tage = {a.datum for a in abholungen}
    bar = dict(Buchung.objects.filter(kundennummer=haushalt.kundennummer, datum__in=tage)
               .values("datum").annotate(bar=Sum("bar")).values_list("datum", "bar"))  # fmt: skip
    for a in abholungen:
        a.bar_gezahlt = bar.get(a.datum)
    return abholungen


def _kosten(h: Haushalt, abholung) -> Decimal:
    """Was die Abholung kostet – nach den Beitragsregeln der Tafel, nicht nach der Liste des
    bisherigen Programms (dort steht am Zahltag die ganze Vorauszahlung)."""
    from apps.ausgabe.models import AusgabeEinstellungen
    from apps.kunden.models import KundenEinstellungen

    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    stelle = abholung.ausgabestelle  # wo abgeholt wurde; sonst die der Kundengruppe
    einstellungen = AusgabeEinstellungen.laden()
    return einstellungen.beitrag_fuer(h, abholung.datum, kind_bis, stelle=stelle) or NULL


def _aus_kontostand(h: Haushalt, danach: Decimal, bis: dt.date, von: str = "") -> int:
    """Bucht die offenen Abholungen eines Kunden bis ``bis`` so, dass das Konto danach auf
    ``danach`` steht (siehe ``zahlungen_aus_kontostand``). Rückgabe: Zahl der Buchungen."""
    from apps.kunden.models import Abholung

    schon = set(Buchung.objects.filter(art=Buchung.Art.ABHOLUNG, kundennummer=h.kundennummer)
                .values_list("datum", flat=True))  # fmt: skip
    offen = [a for a in Abholung.objects.filter(haushalt=h, buchung__isnull=True, datum__lte=bis)
             .order_by("datum", "uhrzeit") if a.datum not in schon]  # fmt: skip
    anzahl = 0
    kosten = []
    for a in offen:
        k = _kosten(h, a)
        if a.beitrag != k:  # die Abholung kostet, was die Regeln sagen
            a.beitrag = k
            a.save(update_fields=["beitrag"])
        kosten.append(k)
    gezahlt = max(sum(kosten, NULL) + danach - (h.kontostand or NULL), NULL)
    for i, (a, beitrag) in enumerate(zip(offen, kosten, strict=True)):
        bar = gezahlt if i == len(offen) - 1 else min(gezahlt, beitrag)
        gezahlt -= bar
        fuer_beitrag = min(bar, beitrag)
        rest = beitrag - fuer_beitrag
        vom_konto = min(rest, max(h.kontostand or NULL, NULL))
        if rest - vom_konto:
            zahlweise = Buchung.Zahlweise.ANSCHREIBEN
        elif vom_konto:
            zahlweise = Buchung.Zahlweise.GUTHABEN
        else:
            zahlweise = Buchung.Zahlweise.BAR
        ort = {"datum": a.datum, "uhrzeit": a.uhrzeit, "stelle": a.ausgabestelle,
               "von": von or a.eingetragen_von}  # fmt: skip
        if beitrag:
            _import_buchen(h, **ort, art=Buchung.Art.ABHOLUNG, zahlweise=zahlweise, soll=beitrag,
                           haben=fuer_beitrag, bar=fuer_beitrag, abholung=a)  # fmt: skip
            anzahl += 1
        if bar - fuer_beitrag:
            _import_buchen(h, **ort, art=Buchung.Art.EINZAHLUNG, haben=bar - fuer_beitrag,
                           bar=bar - fuer_beitrag)  # fmt: skip
            anzahl += 1
    if (h.kontostand or NULL) != danach:  # z. B. eine Korrektur im bisherigen Programm
        diff = danach - (h.kontostand or NULL)
        _import_buchen(h, bis, von=von, art=Buchung.Art.KORREKTUR, soll=max(-diff, NULL),
                       haben=max(diff, NULL), bemerkung=f"Kontostand laut bisherigem Programm "
                       f"(Stand {bis:%d.%m.%Y})")  # fmt: skip
        anzahl += 1
    return anzahl


@transaction.atomic
def zahlungen_aus_kontostand(stand: dict, von: str = "") -> int:
    """Bucht Abholungen aus dem bisherigen Programm nach dem, was wirklich gezahlt wurde.

    Die Tagesliste nennt je Kunde, was er an dem Tag zahlen musste (am Zahltag die ganze
    Vorauszahlung), und den Kontostand danach – nicht, was bar auf dem Tisch lag. Das ergibt sich
    aus dem Konto: gezahlt = Kosten der Abholungen (nach den Beitragsregeln der Tafel) + Kontostand
    danach − Kontostand vorher. Wer im Voraus bezahlt hat, zahlt so 0 € (aus Guthaben), wer für den
    Monat zahlt, den ganzen Betrag (der Rest wird Einzahlung) – genau wie am Einlass
    (``abholung_buchen``). Am Ende steht das Konto auf dem Kontostand der Liste (eine Korrektur
    gleicht Abweichungen aus).

    ``stand`` = {Kundennummer: (Kontostand danach, Datum der Liste)}. Gebucht werden Abholungen
    bis zu diesem Datum ohne Buchung; ein Tag, an dem es schon eine Abholungs-Buchung gibt
    (am Einlass oder aus buchungen.csv), wird nicht doppelt gebucht. Rückgabe: Zahl der Buchungen.
    """
    anzahl = 0
    for h in Haushalt.objects.select_for_update().filter(kundennummer__in=list(stand)):
        danach, bis = stand[h.kundennummer]
        anzahl += _aus_kontostand(h, danach, bis, von)
    return anzahl


ABGLEICH = re.compile(r"^Abgleich .+ \(Stand (\d\d)\.(\d\d)\.(\d{4})\)$")


def abgleiche_finden():
    """Korrekturen aus „Besuche übernehmen“ älterer Versionen, die den Kontostand angeglichen
    haben, ohne die Zahlung in die Kasse zu buchen. {Haushalt-pk: [Buchungs-pk]} – nur eine
    Abfrage, damit die Seite auch bei vielen Kunden sofort öffnet."""
    gefunden: dict[int, list] = {}
    art = Buchung.Art.KORREKTUR
    korrekturen = Buchung.objects.filter(art=art, bemerkung__startswith="Abgleich ")
    zeilen = korrekturen.order_by("pk").values_list("pk", "haushalt_id", "bemerkung")
    for pk, haushalt_id, bemerkung in zeilen:
        if haushalt_id and ABGLEICH.match(bemerkung):
            gefunden.setdefault(haushalt_id, []).append(pk)
    return gefunden


def abgleiche_stand() -> dict:
    """Wie viele Kunden und alte Abgleich-Korrekturen es noch gibt (schnell, ändert nichts)."""
    gefunden = abgleiche_finden()
    return {"kunden": len(gefunden), "korrekturen": sum(map(len, gefunden.values()))}


@transaction.atomic
def _abgleich_umrechnen(pk: int, ids: set, von: str) -> int:
    """Ein Kunde: Abgleich-Korrekturen durch Kassenbuchungen ersetzen (siehe
    ``abgleiche_nachrechnen``). Rückgabe: Zahl der neuen Buchungen."""
    h = Haushalt.objects.select_for_update().get(pk=pk)
    # in der Reihenfolge des Anlegens: Kontostand nach jeder Buchung
    alle = list(Buchung.objects.filter(haushalt=h).order_by("pk"))
    korrekturen = [b for b in alle if b.pk in ids]
    stand = (h.kontostand or NULL) - sum((b.wirkung for b in alle), NULL)
    ziele: dict[dt.date, Decimal] = {}
    for i, b in enumerate(alle):
        stand += b.wirkung
        if b.pk in ids:  # je Tag der Liste zählt die letzte Angleichung
            t, m, j = ABGLEICH.match(b.bemerkung).groups()
            spaeter = sum((x.wirkung for x in alle[i + 1 :] if x.pk not in ids), NULL)
            # was danach noch gebucht wurde (z. B. am Einlass), bleibt und zählt mit
            ziele[dt.date(int(j), int(m), int(t))] = stand + spaeter
    vorher = h.kontostand or NULL
    Buchung.objects.filter(pk__in=ids).delete()
    h.kontostand = vorher - sum((b.wirkung for b in korrekturen), NULL)
    h.save(update_fields=["kontostand"])
    buchungen = 0
    for tag in sorted(ziele):
        buchungen += _aus_kontostand(h, ziele[tag], tag, von)
    if (h.kontostand or NULL) != vorher:  # Sicherheitsnetz: Kontostand bleibt, wie er war
        diff = vorher - (h.kontostand or NULL)
        _buchen(h, art=Buchung.Art.KORREKTUR, soll=max(-diff, NULL), haben=max(diff, NULL),
                bemerkung="Ausgleich beim Nachrechnen", eingetragen_von=von)  # fmt: skip
    return buchungen


def abgleiche_nachrechnen(von: str = "", sekunden: float | None = None) -> dict:
    """Wandelt die alten Abgleich-Korrekturen in Kassenbuchungen um: je Stand (Tag der Liste)
    den Kontostand von damals bestimmen, die Korrekturen entfernen und die Abholungen bis zu dem
    Tag nach ``_aus_kontostand`` buchen – in der Reihenfolge der Tage. Der Kontostand ist danach
    derselbe wie vorher.

    Je Kunde eine eigene Transaktion. Mit ``sekunden`` hört der Lauf nach dieser Zeit auf (die
    Seite ruft ihn dann erneut auf), damit bei vielen Kunden keine Anfrage zu lange dauert und
    kein Konto lange gesperrt ist. Rückgabe: Zahl der Kunden, neuen Buchungen und noch offenen
    Kunden."""
    import time

    ende = time.monotonic() + sekunden if sekunden else None
    gefunden = abgleiche_finden()
    kunden = buchungen = 0
    for pk, ids in gefunden.items():
        if ende and kunden and time.monotonic() >= ende:
            break
        buchungen += _abgleich_umrechnen(pk, set(ids), von)
        kunden += 1
    return {"kunden": kunden, "buchungen": buchungen, "offen": len(gefunden) - kunden}


GESCHAETZT = "geschätzt (alte Abholung ohne Kassendaten)"


def _ohne_kasse(bis: dt.date):
    """Alte Abholungen aus dem bisherigen Programm (nicht am Einlass erfasst) bis ``bis``, zu denen
    es keine Buchung gibt – auch keine andere Abholungs-Buchung des Kunden am selben Tag."""
    from django.db.models import Exists, OuterRef

    from apps.kunden.models import Abholung

    gebucht = Buchung.objects.filter(art=Buchung.Art.ABHOLUNG, datum=OuterRef("datum"),
                                     kundennummer=OuterRef("haushalt__kundennummer"))  # fmt: skip
    return Abholung.objects.filter(buchung__isnull=True, erfasst_am__isnull=True,
                                   datum__lte=bis).exclude(Exists(gebucht))  # fmt: skip


def schaetzung_stand(bis: dt.date) -> dict:
    """Was es zu schätzen gäbe und was schon geschätzt ist (schnell, ändert nichts)."""
    from django.db.models import Count, Max, Min, Sum

    offen = _ohne_kasse(bis).aggregate(anzahl=Count("pk"), kunden=Count("haushalt", distinct=True),
                                       von=Min("datum"), bis=Max("datum"))  # fmt: skip
    schon = Buchung.objects.filter(bemerkung=GESCHAETZT, importiert=True).aggregate(
        anzahl=Count("pk"), summe=Sum("bar"))  # fmt: skip
    return {"offen": offen, "geschaetzt": schon["anzahl"], "summe": schon["summe"] or NULL}


def alte_abholungen_schaetzen(bis: dt.date, von: str = "", ab: int = 0,
                              sekunden: float | None = None) -> dict:  # fmt: skip
    """Bucht für alte Abholungen ohne Kassendaten den Beitrag nach den Beitragsregeln als bar
    gezahlt an dem Tag – eine Schätzung, gekennzeichnet mit ``GESCHAETZT``.

    Was an einem alten Tag wirklich bar gezahlt wurde, steht nirgends: Die Listen des bisherigen
    Programms nannten es nicht. Ohne Buchung bleiben Kasse und Abrechnung für diese Zeit leer.
    Die Schätzung nimmt an, dass jede Abholung an ihrem Tag bar bezahlt wurde (Soll = Haben, der
    Kontostand bleibt). Summen über längere Zeit stimmen so ungefähr; Vorauszahlungen stehen am
    Abholtag statt am Zahltag, und Angeschriebenes zählt als bezahlt. Abholungen ohne Beitrag
    (beitragsfreie Zeit) bekommen keine Buchung.

    In Portionen wie ``abgleiche_nachrechnen``: ``ab`` ist der letzte bearbeitete Haushalt; mit
    ``sekunden`` hört der Lauf nach dieser Zeit auf. Rückgabe: Zahl und Summe der Buchungen und
    ``weiter`` (Haushalt, ab dem der nächste Aufruf weitermacht, sonst ``None``)."""
    import time

    from apps.kunden.models import KundenEinstellungen

    ende = time.monotonic() + sekunden if sekunden else None
    einstellungen = AusgabeEinstellungen.laden()
    kind_bis = KundenEinstellungen.laden().kind_bis_alter
    offen = _ohne_kasse(bis)
    haushalte = sorted(set(offen.filter(haushalt_id__gt=ab).values_list("haushalt_id", flat=True)))
    buchungen, summe, weiter = 0, NULL, None
    for nummer, pk in enumerate(haushalte):
        if ende and nummer and time.monotonic() >= ende:
            weiter = haushalte[nummer - 1]
            break
        with transaction.atomic(), disable_auditlog():
            h = Haushalt.objects.select_for_update().get(pk=pk)
            tage = set()
            for a in offen.filter(haushalt=h).select_related("ausgabestelle").order_by(
                    "datum", "uhrzeit"):  # fmt: skip
                if a.datum in tage:  # zwei Abholungen an einem Tag: nur einmal
                    continue
                tage.add(a.datum)
                kosten = einstellungen.beitrag_fuer(h, a.datum, kind_bis, stelle=a.ausgabestelle)
                if not kosten:
                    continue
                _import_buchen(h, a.datum, a.uhrzeit, a.ausgabestelle, von or a.eingetragen_von,
                               art=Buchung.Art.ABHOLUNG, zahlweise=Buchung.Zahlweise.BAR,
                               soll=kosten, haben=kosten, bar=kosten, abholung=a,
                               bemerkung=GESCHAETZT)  # fmt: skip
                buchungen += 1
                summe += kosten
    return {"buchungen": buchungen, "summe": summe, "weiter": weiter}


def schaetzung_entfernen() -> int:
    """Nimmt alle geschätzten Buchungen wieder heraus (Soll = Haben: der Kontostand bleibt)."""
    with transaction.atomic(), disable_auditlog():
        anzahl, _ = Buchung.objects.filter(bemerkung=GESCHAETZT, importiert=True).delete()
    return anzahl


@transaction.atomic
def einzahlen(haushalt, betrag, stelle, von, bemerkung="") -> Buchung:
    """Zahlung ohne Abholung. Mit Minus eine Auszahlung: Geld geht bar zurück an den Kunden."""
    if not betrag:
        raise KontoFehler("Bitte einen Betrag ungleich 0 angeben (mit Minus für eine Auszahlung).")
    return _buchen(
        _gesperrt(haushalt),
        art=Buchung.Art.EINZAHLUNG,
        haben=betrag,
        bar=betrag,
        ausgabestelle=stelle,
        bemerkung=bemerkung[:200],
        eingetragen_von=von,
    )


@transaction.atomic
def korrigieren(haushalt, betrag, begruendung, von) -> Buchung:
    """Korrektur ohne Bargeld: positiv schreibt gut, negativ belastet."""
    if not betrag:
        raise KontoFehler("Bitte einen Betrag ungleich 0 angeben.")
    if not begruendung.strip():
        raise KontoFehler("Bitte eine Begründung angeben.")
    return _buchen(
        _gesperrt(haushalt),
        art=Buchung.Art.KORREKTUR,
        soll=-betrag if betrag < 0 else NULL,
        haben=betrag if betrag > 0 else NULL,
        bemerkung=begruendung.strip()[:200],
        eingetragen_von=von,
    )


AENDERBAR = ("soll", "haben", "bar", "ausgabestelle", "bemerkung")


@transaction.atomic
def aendern(buchung: Buchung, **felder) -> Buchung:
    """Ändert eine einzelne Buchung und zieht den Kontostand um den Unterschied nach."""
    fremd = set(felder) - set(AENDERBAR)
    if fremd:
        raise KontoFehler(f"Nicht änderbar: {', '.join(sorted(fremd))}.")
    vorher = buchung.wirkung
    for name, wert in felder.items():
        setattr(buchung, name, wert)
    buchung.save(update_fields=list(felder))
    if buchung.haushalt_id and buchung.wirkung != vorher:
        h = _gesperrt(buchung.haushalt)
        h.kontostand = (h.kontostand or NULL) + buchung.wirkung - vorher
        h.save(update_fields=["kontostand"])
    return buchung


@transaction.atomic
def zuruecknehmen(buchung: Buchung) -> None:
    """Löscht eine Buchung und stellt den Kontostand davor wieder her."""
    if buchung.haushalt_id:
        h = _gesperrt(buchung.haushalt)
        h.kontostand = (h.kontostand or NULL) - buchung.wirkung
        h.save(update_fields=["kontostand"])
    buchung.delete()


@transaction.atomic
def abholung_zuruecknehmen(abholung) -> None:
    """Nimmt die Buchungen einer Abholung zurück (Beitrag und Überzahlung) und löscht sie."""
    if hasattr(abholung, "buchung"):
        zuruecknehmen(abholung.buchung)
    um = f" um {abholung.uhrzeit:%H:%M}" if abholung.uhrzeit else ""
    ueber = Buchung.objects.filter(
        haushalt=abholung.haushalt,
        art=Buchung.Art.EINZAHLUNG,
        datum=abholung.datum,
        bemerkung=f"{UEBERZAHLUNG}{um}",
    ).first()
    if ueber:
        zuruecknehmen(ueber)
    abholung.delete()


# --- Vorschlag für Vorauszahlungen -------------------------------------------------------


@dataclass
class Vorschlag:
    titel: str
    tage: list[dt.date]
    beitrag: Decimal
    erklaerung: list[str] = field(default_factory=list)
    guthaben: Decimal = NULL

    @property
    def betrag(self) -> Decimal:
        return self.beitrag * len(self.tage)

    @property
    def zu_zahlen(self) -> Decimal:
        """Was bar zu zahlen ist: der Betrag abzüglich vorhandenen Guthabens."""
        return max(self.betrag - self.guthaben, NULL)


def _tage(von: dt.date, bis: dt.date, wochentage: list[str]) -> list[dt.date]:
    anzahl = (bis - von).days + 1
    tage = (von + dt.timedelta(days=i) for i in range(max(anzahl, 0)))
    return [t for t in tage if WOCHENTAGE[t.weekday()] in wochentage]


def _begrenzen(tage, abgeholt, einstellungen) -> tuple[list[dt.date], str]:
    """Kürzt die Tage auf die erlaubte Höchstzahl; liefert dazu einen erklärenden Satz."""
    hoechst = einstellungen.max_abholungen
    zeitraum = einstellungen.zeitraum
    if not hoechst:
        return tage, "Keine Höchstzahl je Zeitraum eingestellt."
    if zeitraum == AusgabeEinstellungen.Zeitraum.VIERZEHN_TAGE:
        return tage, f"Die Höchstzahl ({hoechst} je 14 Tage) ist im Vorschlag nicht berücksichtigt."
    if zeitraum == AusgabeEinstellungen.Zeitraum.MONAT:

        def gruppe(t):
            return (t.year, t.month)

        einheit = "Kalendermonat"
    else:

        def gruppe(t):
            return t.isocalendar()[:2]

        einheit = "Kalenderwoche"
    ergebnis, gezaehlt = [], {}
    for t in abgeholt:
        gezaehlt[gruppe(t)] = gezaehlt.get(gruppe(t), 0) + 1
    for t in tage:
        if gezaehlt.get(gruppe(t), 0) < hoechst:
            ergebnis.append(t)
            gezaehlt[gruppe(t)] = gezaehlt.get(gruppe(t), 0) + 1
    weggelassen = len(tage) - len(ergebnis)
    satz = f"Höchstens {hoechst} Abholung{'en' if hoechst != 1 else ''} je {einheit}"
    if weggelassen:
        satz += f": {weggelassen} Abholtag{'e' if weggelassen != 1 else ''} nicht gezählt."
    else:
        satz += " ist eingehalten."
    return ergebnis, satz


# Vorauszahlung erst ab so vielen möglichen Abholungen bis Monatsende anbieten
VORSCHLAG_AB_TAGEN = 3


def vorschlaege(h, heute, einstellungen, beitrag) -> tuple[list[Vorschlag], str]:
    """Vorschlag für den Rest dieses Monats, mit Erklärung (nicht für den nächsten Monat).

    Liefert die Vorschläge und gegebenenfalls einen Hinweis, warum es keine gibt.
    """
    if not beitrag:
        return [], "Kein Vorschlag: In den Einstellungen ist kein Beitrag festgelegt."
    gruppe = h.kundengruppe
    wochentage = [t.strip() for t in (gruppe.wochentage if gruppe else "").split(",") if t]
    if not wochentage:
        return [], (
            "Kein Vorschlag: Die Kundengruppe hat keine festen Wochentage. "
            "Bitte den Betrag selbst eintragen."
        )
    abgeholt = [a.datum for a in h.abholungen.all()]
    land = TafelEinstellungen.laden().bundesland
    heute_abgeholt = heute in abgeholt
    start = heute + dt.timedelta(days=1) if heute_abgeholt else heute
    monatsende = heute.replace(day=calendar.monthrange(heute.year, heute.month)[1])
    ab_text = (
        "ab morgen, weil heute schon abgeholt wurde"
        if heute_abgeholt
        else "ab heute, weil heute noch nicht abgeholt wurde"
    )
    zeitraeume = [
        (f"Rest {MONATE[heute.month - 1]}", start, monatsende, ab_text),
    ]
    ergebnis = []
    for titel, von, bis, zusatz in zeitraeume:
        tage = _tage(von, bis, wochentage)
        frei = [t for t in tage if ist_feiertag(t, land)]
        tage = [t for t in tage if t not in frei]
        zu = Schliesszeit.tage(gruppe.ausgabestelle, von, bis)
        geschlossen = [t for t in tage if t in zu]
        tage = [t for t in tage if t not in zu]
        ohne_beitrag = [t for t in tage if BeitragsfreierZeitraum.am(t, gruppe.ausgabestelle)]
        tage = [t for t in tage if t not in ohne_beitrag]
        if h.ausweis_gueltig_bis and any(t > h.ausweis_gueltig_bis for t in tage):
            tage = [t for t in tage if t <= h.ausweis_gueltig_bis]
            ausweis = f"Nur bis zum Ablauf des Ausweises am {h.ausweis_gueltig_bis:%d.%m.%Y}."
        else:
            ausweis = None
        tage, grenze = _begrenzen(tage, abgeholt, einstellungen)
        if len(tage) < VORSCHLAG_AB_TAGEN:  # für ein, zwei Abholungen lohnt keine Vorauszahlung
            continue
        v = Vorschlag(titel=titel, tage=tage, beitrag=beitrag)
        v.erklaerung = [
            f"{len(tage)} Abholtag{'e' if len(tage) != 1 else ''} × {euro(beitrag)} "
            f"= {euro(v.betrag)}",
            f"Gezählt: {', '.join(f'{WOCHENTAGE[t.weekday()]} {t:%d.%m.}' for t in tage)} "
            f"(Kundengruppe „{gruppe.name}“: {', '.join(wochentage)})",
        ]
        v.erklaerung.append(f"Gezählt {zusatz}.")
        if ausweis:
            v.erklaerung.append(ausweis)
        v.erklaerung.append(grenze)
        v.guthaben = max(h.kontostand or NULL, NULL)
        if v.guthaben:
            v.erklaerung.append(
                f"Abzüglich Guthaben {euro(v.guthaben)}: zu zahlen {euro(v.zu_zahlen)}."
            )
        if ohne_beitrag:
            namen = ", ".join(f"{t:%d.%m.}" for t in ohne_beitrag)
            v.erklaerung.append(f"Nicht gezählt, weil beitragsfrei: {namen}")
        if frei:
            namen = ", ".join(
                f"{WOCHENTAGE[t.weekday()]} {t:%d.%m.} ({feiertage(t.year, land)[t]})" for t in frei
            )
            v.erklaerung.append(f"Nicht gezählt, weil Feiertag: {namen}.")
        if geschlossen:
            namen = ", ".join(f"{WOCHENTAGE[t.weekday()]} {t:%d.%m.}" for t in geschlossen)
            v.erklaerung.append(f"Nicht gezählt, weil die Ausgabestelle geschlossen hat: {namen}")
        if not land:
            v.erklaerung.append(
                "Feiertage sind nicht berücksichtigt (in den Einstellungen der Tafel ist kein "
                "Bundesland gewählt)."
            )
        v.erklaerung.append(
            "Schließzeiten der Ausgabestelle zählen nur, wenn sie unter „Einstellungen → "
            "Ausgabe → Schließzeiten“ eingetragen sind."
        )
        ergebnis.append(v)
    if not ergebnis:
        return [], (f"Kein Vorschlag: Bis Monatsende sind weniger als {VORSCHLAG_AB_TAGEN} "
                    "Abholungen möglich.")  # fmt: skip
    return ergebnis, ""


# --- Fristen -----------------------------------------------------------------------------


def buchungsfristen_anwenden(heute: dt.date | None = None) -> int:
    """Anonymisiert Buchungen nach der Frist für Abholungen, löscht sie nach der Buchungsfrist.

    Liefert die Zahl der gelöschten Buchungen.
    """
    heute = heute or timezone.localdate()
    jahre = AusgabeEinstellungen.laden().buchungen_aufbewahren_jahre
    try:
        grenze = heute.replace(year=heute.year - jahre)
    except ValueError:  # 29. Februar
        grenze = heute.replace(year=heute.year - jahre, day=28)
    with disable_auditlog():  # Fristablauf ist kein fachliches Ereignis je Buchung
        Buchung.objects.filter(datum__lt=abholfrist_beginn(heute)).exclude(
            haushalt=None, kundennummer="", bemerkung="", eingetragen_von=""
        ).update(haushalt=None, kundennummer="", bemerkung="", eingetragen_von="")
        return Buchung.objects.filter(datum__lt=grenze).delete()[0]
