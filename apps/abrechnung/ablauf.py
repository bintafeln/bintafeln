"""Regeln der Abrechnung je Ausgabestelle (ADR 0060). Ansichten rufen nur diese Funktionen."""

import datetime as dt
import io
import re
import zipfile
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum
from django.utils import timezone

from apps.abrechnung.models import AbrechnungEinstellungen, Monatsabrechnung, Posten
from apps.ausgabe import kasse
from apps.ausgabe.konto import MONATE, euro
from apps.ausgabe.models import Buchung
from apps.core import privatdateien
from apps.core.pdf import Pdf
from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.models import Ausgabestelle

NULL = Decimal("0.00")
# Kennzahlen der Kasse, die die Abrechnung zeigt; „bar_gesamt“ zählt als Einnahme
EINNAHMEN = [("beitraege_bar", "Beiträge bar"), ("einzahlungen", "Einzahlungen auf Kundenkonten"),
             ("bar_gesamt", "Einnahmen bar gesamt")]  # fmt: skip
NEBENBEI = [
    ("abholungen", "Abholungen mit Beitrag"),
    ("beitraege", "Beiträge gesamt"),
    ("vom_konto", "davon aus Guthaben"),
    ("angeschrieben", "davon angeschrieben"),
]
ENDUNGEN = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp",
            "application/pdf": "pdf"}  # fmt: skip


class AbrechnungFehler(ValueError):
    pass


# --- Zugang ---


def darf_pruefen(benutzer) -> bool:
    return rollen.hat_recht(benutzer, "abrechnung.pruefen")


def darf_fuehren(benutzer, stelle) -> bool:
    if not rollen.hat_recht(benutzer, "abrechnung.fuehren"):
        return False
    eigene = zugang.stellen(benutzer)
    return eigene is None or stelle.pk in {s.pk for s in eigene}


def stellen_fuer(benutzer) -> list:
    """Ausgabestellen, deren Abrechnung das Konto sehen darf."""
    alle = list(Ausgabestelle.objects.order_by("name"))
    if darf_pruefen(benutzer):
        return alle
    return [s for s in alle if darf_fuehren(benutzer, s)]


# --- Monat ---


def monatsanfang(tag: dt.date) -> dt.date:
    return tag.replace(day=1)


def monatsende(monat: dt.date) -> dt.date:
    naechster = (monat.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return naechster - dt.timedelta(days=1)


def verschieben(monat: dt.date, um: int) -> dt.date:
    zahl = monat.year * 12 + monat.month - 1 + um
    return dt.date(zahl // 12, zahl % 12 + 1, 1)


def monat_lesen(text: str, vorgabe: dt.date) -> dt.date:
    try:
        return dt.datetime.strptime(text or "", "%Y-%m").date()
    except ValueError:
        return monatsanfang(vorgabe)


def monatsname(monat: dt.date) -> str:
    return f"{MONATE[monat.month - 1]} {monat.year}"


HOECHSTENS = 6  # so viele Monate darf eine Abrechnung umfassen


def zeitraum_name(abr: Monatsabrechnung) -> str:
    """„September 2026“, „September – November 2026“ oder „November 2025 – Januar 2026“."""
    if abr.ende == abr.monat:
        return monatsname(abr.monat)
    if abr.ende.year == abr.monat.year:
        return f"{MONATE[abr.monat.month - 1]} – {monatsname(abr.ende)}"
    return f"{monatsname(abr.monat)} – {monatsname(abr.ende)}"


def im_monat(monat: dt.date):
    """Abrechnungen, deren Zeitraum den Monat enthält."""
    monat = monatsanfang(monat)
    return Monatsabrechnung.objects.filter(Q(monat=monat) | Q(monat__lt=monat, bis__gte=monat))


def holen(stelle, monat: dt.date) -> Monatsabrechnung:
    """Die Abrechnung der Stelle, in deren Zeitraum der Monat liegt; sonst eine neue für ihn."""
    vorhanden = im_monat(monat).filter(stelle=stelle).first()
    if vorhanden:
        return vorhanden
    abr, _ = Monatsabrechnung.objects.get_or_create(stelle=stelle, monat=monatsanfang(monat))
    return abr


def zeitraeume(abr: Monatsabrechnung) -> list[tuple[int, str]]:
    """Auswahl „bis einschließlich …“: (Anzahl Monate, Name des letzten Monats)."""
    return [(n, monatsname(verschieben(abr.monat, n - 1))) for n in range(1, HOECHSTENS + 1)]


# --- Zahlen ---


def _kasse(abr: Monatsabrechnung) -> dict:
    buchungen = Buchung.objects.filter(ausgabestelle=abr.stelle, datum__gte=abr.monat,
                                       datum__lte=monatsende(abr.ende))  # fmt: skip
    return kasse.summe(buchungen)


def einnahmen(abr: Monatsabrechnung) -> dict:
    """Kennzahlen der Kasse: festgehalten, sobald eingereicht, sonst aktuell gerechnet."""
    if not abr.offen and abr.einnahmen:
        return {k: (Decimal(v) if k != "abholungen" else int(v)) for k, v in abr.einnahmen.items()}
    return _kasse(abr)


def ausgaben_summe(abr: Monatsabrechnung) -> Decimal:
    if not abr.pk:
        return NULL
    return abr.posten.aggregate(s=Sum("betrag"))["s"] or NULL


def zahlen(abr: Monatsabrechnung) -> dict:
    werte = einnahmen(abr)
    ausgaben = ausgaben_summe(abr)
    return {
        "einnahmen": [(name, werte[k]) for k, name in EINNAHMEN],
        "nebenbei": [(name, werte[k], k != "abholungen") for k, name in NEBENBEI],
        "einnahmen_summe": werte["bar_gesamt"],
        "ausgaben_summe": ausgaben,
        "saldo": werte["bar_gesamt"] - ausgaben,
    }


# --- Ablauf ---


def _sperren(abr: Monatsabrechnung) -> Monatsabrechnung:
    return Monatsabrechnung.objects.select_for_update().get(pk=abr.pk)


def posten_anlegen(abr, daten: dict, datei, benutzer) -> Posten:
    """Neue Ausgabe; die Quittung (Foto oder PDF) wird verschlüsselt gespeichert."""
    if not abr.offen:
        raise AbrechnungFehler("Die Abrechnung ist eingereicht; Änderungen erst nach Rückgabe.")
    if daten["datum"] > monatsende(abr.ende):
        raise AbrechnungFehler("Das Datum liegt nach dem Ende des Abrechnungszeitraums.")
    posten = Posten(abrechnung=abr, eingetragen_von=benutzer.get_username(), **daten)
    if datei:
        posten.quittung = privatdateien.speichern(Posten.ORDNER, datei, max_mb=10)
        posten.quittung_typ = datei.content_type
    posten.save()
    return posten


def posten_loeschen(posten: Posten) -> None:
    if not posten.abrechnung.offen:
        raise AbrechnungFehler("Die Abrechnung ist eingereicht; Änderungen erst nach Rückgabe.")
    privatdateien.loeschen(Posten.ORDNER, posten.quittung)
    posten.delete()


def einreichen(abr, benutzer, anmerkung="") -> None:
    with transaction.atomic():
        abr = _sperren(abr)
        if not abr.offen:
            raise AbrechnungFehler("Die Abrechnung ist schon eingereicht.")
        abr.einnahmen = {k: str(v) for k, v in _kasse(abr).items()}
        abr.status = Monatsabrechnung.Status.EINGEREICHT
        abr.eingereicht_am, abr.eingereicht_von = timezone.now(), benutzer.get_username()
        abr.anmerkung, abr.rueckgabe = anmerkung.strip(), ""
        abr.save()


def zuruecknehmen(abr) -> None:
    """Die Ausgabestelle öffnet ihre eingereichte Abrechnung selbst wieder – nur solange das
    Büro sie nicht bestätigt hat."""
    with transaction.atomic():
        abr = _sperren(abr)
        if abr.status == Monatsabrechnung.Status.BESTAETIGT:
            raise AbrechnungFehler("Die Abrechnung ist schon bestätigt; nur das Büro kann sie "
                                   "zurückgeben.")  # fmt: skip
        if abr.offen:
            raise AbrechnungFehler("Die Abrechnung ist schon offen.")
        abr.status, abr.einnahmen = Monatsabrechnung.Status.OFFEN, {}
        abr.eingereicht_am, abr.eingereicht_von = None, ""
        abr.save()


def zeitraum_aendern(abr, monate: int) -> None:
    """Die offene Abrechnung umfasst ab ihrem ersten Monat ``monate`` Monate (1 bis 6). Offene
    Abrechnungen der dazugenommenen Monate gehen mit ihren Ausgaben in dieser auf."""
    if not 1 <= monate <= HOECHSTENS:
        raise AbrechnungFehler(f"Eine Abrechnung umfasst 1 bis {HOECHSTENS} Monate.")
    with transaction.atomic():
        abr = _sperren(abr)
        if not abr.offen:
            raise AbrechnungFehler("Die Abrechnung ist eingereicht; Änderungen erst nach "
                                   "Rückgabe.")  # fmt: skip
        ende = verschieben(abr.monat, monate - 1)
        spaeter = abr.posten.filter(datum__gt=monatsende(ende)).count()
        if spaeter:
            raise AbrechnungFehler(
                f"Es gibt Ausgaben nach {monatsname(ende)}; der Zeitraum lässt sich nicht "
                "davor beenden."
            )
        andere = list(Monatsabrechnung.objects.select_for_update().filter(
            stelle=abr.stelle, monat__gt=abr.monat, monat__lte=ende))  # fmt: skip
        fest = [a for a in andere if not a.offen]
        if fest:
            raise AbrechnungFehler(
                f"Für {zeitraum_name(fest[0])} gibt es schon eine eingereichte Abrechnung."
            )
        for a in andere:  # offene Abrechnungen der dazugenommenen Monate gehen hier auf
            ende = max(ende, a.ende)
            a.posten.update(abrechnung=abr)
            a.delete()
        if (ende.year - abr.monat.year) * 12 + ende.month - abr.monat.month >= HOECHSTENS:
            raise AbrechnungFehler(f"Eine Abrechnung umfasst 1 bis {HOECHSTENS} Monate.")
        abr.bis = ende if ende != abr.monat else None
        abr.save()


def bestaetigen(abr, benutzer) -> None:
    with transaction.atomic():
        abr = _sperren(abr)
        if abr.status != Monatsabrechnung.Status.EINGEREICHT:
            raise AbrechnungFehler("Nur eingereichte Abrechnungen lassen sich bestätigen.")
        abr.status = Monatsabrechnung.Status.BESTAETIGT
        abr.bestaetigt_am, abr.bestaetigt_von = timezone.now(), benutzer.get_username()
        abr.save()


def zurueckgeben(abr, benutzer, grund: str) -> None:
    """Zurück an die Ausgabestelle (auch eine bestätigte); Einnahmen werden neu gerechnet."""
    grund = grund.strip()
    if not grund:
        raise AbrechnungFehler("Bitte kurz angeben, was noch zu ändern ist.")
    with transaction.atomic():
        abr = _sperren(abr)
        if abr.offen:
            raise AbrechnungFehler("Die Abrechnung ist schon offen.")
        abr.status, abr.einnahmen, abr.rueckgabe = Monatsabrechnung.Status.OFFEN, {}, grund[:300]
        abr.bestaetigt_am, abr.bestaetigt_von = None, ""
        abr.save()


# --- Quittungen und PDF ---


def _sicher(text: str) -> str:
    return re.sub(r"[^\w.-]+", "-", text).strip("-")[:40] or "x"


def quittung_dateiname(posten: Posten) -> str:
    endung = ENDUNGEN.get(posten.quittung_typ, "bin")
    return (f"{posten.datum:%Y-%m-%d}_{_sicher(posten.art)}_{posten.betrag}_"
            f"{posten.pk}.{endung}")  # fmt: skip


def quittungen_zip(abrechnungen) -> tuple[bytes, int]:
    """Alle Quittungen der Abrechnungen als ZIP, je Ausgabestelle ein Ordner."""
    puffer, anzahl = io.BytesIO(), 0
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as zip_:
        for abr in abrechnungen:
            for p in abr.posten.exclude(quittung=""):
                inhalt = privatdateien.lesen(Posten.ORDNER, p.quittung)
                if inhalt is None:
                    continue
                ordner = f"{abr.monat:%Y-%m}_{_sicher(abr.stelle.name)}"
                zip_.writestr(f"{ordner}/{quittung_dateiname(p)}", inhalt)
                anzahl += 1
    return puffer.getvalue(), anzahl


def pdf(abr: Monatsabrechnung) -> bytes:
    z = zahlen(abr)
    doc = Pdf("Abrechnung", f"{abr.stelle.name} · {zeitraum_name(abr)}")
    stand = abr.get_status_display()
    if abr.eingereicht_am:
        stand += f", eingereicht {timezone.localtime(abr.eingereicht_am):%d.%m.%Y} von " \
                 f"{abr.eingereicht_von}"  # fmt: skip
    if abr.bestaetigt_am:
        stand += f", bestätigt {timezone.localtime(abr.bestaetigt_am):%d.%m.%Y} von " \
                 f"{abr.bestaetigt_von}"  # fmt: skip
    doc.angaben([("Stand", stand), *([("Anmerkung", abr.anmerkung)] if abr.anmerkung else [])])
    doc.ueberschrift("Einnahmen (aus der Kasse am Einlass)")
    doc.tabelle(["", "Betrag"], [[n, euro(w)] for n, w in z["einnahmen"]], breiten=[0.6, 0.2],
                rechts=[1], summe=True)  # fmt: skip
    doc.absatz(" · ".join(f"{n}: {euro(w) if b else w}" for n, w, b in z["nebenbei"]), klein=True)
    doc.ueberschrift("Ausgaben")
    posten = list(abr.posten.all())
    zeilen = [[f"{p.datum:%d.%m.%Y}", p.art, p.empfaenger, p.anmerkung,
               "ja" if p.quittung else "fehlt", euro(p.betrag)] for p in posten]  # fmt: skip
    if zeilen:
        zeilen.append(["Summe", "", "", "", "", euro(z["ausgaben_summe"])])
    doc.tabelle(["Datum", "Art", "Bezahlt an", "Anmerkung", "Quittung", "Betrag"], zeilen,
                breiten=[0.12, 0.18, 0.2, 0.26, 0.09, 0.15], rechts=[5], summe=True)  # fmt: skip
    doc.ueberschrift("Ergebnis")
    doc.tabelle(["", "Betrag"], [["Einnahmen bar", euro(z["einnahmen_summe"])],
                                 ["Ausgaben", euro(z["ausgaben_summe"])],
                                 ["Saldo", euro(z["saldo"])]],
                breiten=[0.6, 0.2], rechts=[1], summe=True)  # fmt: skip
    doc.abstand()
    doc.unterschriften(["Aufgestellt von", "Geprüft von"])
    return doc.erzeugen()


# --- Fristen ---


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Löscht Abrechnungen samt Quittungen nach Ablauf der Aufbewahrung (volle Kalenderjahre)."""
    heute = heute or timezone.localdate()
    jahre = AbrechnungEinstellungen.laden().aufbewahrung_jahre
    grenze = heute.year - jahre  # bei mehreren Monaten zählt das Jahr des letzten Monats
    alt = Monatsabrechnung.objects.filter(
        Q(bis__isnull=True, monat__year__lt=grenze) | Q(bis__year__lt=grenze))  # fmt: skip
    anzahl = 0
    for abr in alt:
        for p in abr.posten.all():
            privatdateien.loeschen(Posten.ORDNER, p.quittung)
        abr.delete()
        anzahl += 1
    return anzahl
