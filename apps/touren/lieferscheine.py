"""Lieferscheine an den Stationen (ADR 0149): ausfüllen, unterschreiben, als PDF festhalten und
der Station per E-Mail schicken."""

import base64
import binascii
import datetime as dt
import io
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from reportlab.lib.units import mm

from apps.core import mail, privatdateien
from apps.core.models import TafelEinstellungen
from apps.core.pdf import Pdf
from apps.touren.models import Lieferschein, Position, Station, TourenEinstellungen, Warengruppe

MAX_UNTERSCHRIFT = 400_000  # Bytes der PNG-Datei aus dem Unterschriftsfeld
MAX_MENGE = Decimal("9999.9")


class LieferscheinFehler(ValueError):
    pass


def an() -> bool:
    return TourenEinstellungen.laden().lieferscheine


def moeglich(station: Station) -> bool:
    """Wird an dieser Station ein Lieferschein ausgefüllt?"""
    return station.lieferschein and an()


def warengruppen() -> list[Warengruppe]:
    return list(Warengruppe.objects.filter(aktiv=True))


def unterschrift_lesen(wert: str) -> bytes:
    """Das Bild aus dem Unterschriftsfeld (``data:image/png;base64,…``) als saubere PNG-Datei.
    Leer oder ohne einen Strich ist es keine Unterschrift."""
    kopf, _, daten = (wert or "").partition(",")
    if not kopf.startswith("data:image/png;base64") or not daten:
        raise LieferscheinFehler("Bitte im Feld unterschreiben.")
    try:
        roh = base64.b64decode(daten, validate=True)
    except (binascii.Error, ValueError):
        raise LieferscheinFehler("Die Unterschrift konnte nicht gelesen werden.") from None
    if len(roh) > MAX_UNTERSCHRIFT:
        raise LieferscheinFehler("Die Unterschrift ist zu groß. Bitte neu unterschreiben.")
    try:
        bild = Image.open(io.BytesIO(roh))
        bild.load()
    except (UnidentifiedImageError, OSError, ValueError):
        raise LieferscheinFehler("Die Unterschrift konnte nicht gelesen werden.") from None
    if bild.format != "PNG" or bild.width > 2000 or bild.height > 1000:
        raise LieferscheinFehler("Die Unterschrift konnte nicht gelesen werden.")
    bild = bild.convert("RGBA")
    if bild.getchannel("A").getextrema()[1] == 0:
        raise LieferscheinFehler("Bitte im Feld unterschreiben.")
    # auf Weiß legen und neu speichern: keine Metadaten, im PDF gut lesbar
    weiss = Image.new("RGB", bild.size, "white")
    weiss.paste(bild, mask=bild.getchannel("A"))
    if weiss.convert("L").getextrema()[0] > 200:
        raise LieferscheinFehler("Bitte im Feld unterschreiben.")
    puffer = io.BytesIO()
    weiss.save(puffer, "PNG", optimize=True)
    return puffer.getvalue()


def positionen_lesen(daten) -> list[tuple[str, Decimal, str]]:
    """Mengen aus dem Formular: Felder ``menge_<pk>`` und ``einheit_<pk>`` je Warengruppe.
    Leere Zeilen fallen weg."""
    zeilen = []
    for gruppe in warengruppen():
        text = (daten.get(f"menge_{gruppe.pk}") or "").strip().replace(",", ".")
        if not text:
            continue
        try:
            menge = Decimal(text).quantize(Decimal("0.1"))
        except InvalidOperation:
            raise LieferscheinFehler(f"{gruppe.name}: „{text}“ ist keine Zahl.") from None
        if not menge.is_finite() or menge < 0 or menge > MAX_MENGE:
            raise LieferscheinFehler(f"{gruppe.name}: Die Menge passt nicht.")
        if menge == 0:
            continue
        einheit = daten.get(f"einheit_{gruppe.pk}") or Position.Einheit.KISTEN
        if einheit not in Position.Einheit.values:
            raise LieferscheinFehler(f"{gruppe.name}: unbekannte Einheit.")
        zeilen.append((gruppe.name, menge, einheit))
    if not zeilen:
        raise LieferscheinFehler("Bitte mindestens bei einer Warengruppe eine Menge eintragen.")
    return zeilen


def _name(benutzer) -> str:
    return benutzer.get_full_name() or benutzer.get_username()


def _pdf(ls: Lieferschein, positionen, unterschrift: bytes) -> bytes:
    tafel = TafelEinstellungen.laden()
    pdf = Pdf(f"Lieferschein Nr. {ls.nummer}", f"{ls.datum:%d.%m.%Y}")
    pdf.angaben([
        ("Abgeholt bei", ls.station_name),
        ("Anschrift", ls.station_anschrift),
        ("Abgeholt von", tafel.name),
        ("Datum", f"{ls.datum:%d.%m.%Y}"),
    ])  # fmt: skip
    pdf.abstand()
    pdf.tabelle(["Warengruppe", "Menge"], [[w, Position(menge=m, einheit=e).menge_text]
                                          for w, m, e in positionen],
                breiten=[0.7, 0.3], gitter=True)  # fmt: skip
    if ls.anmerkung:
        pdf.abstand()
        pdf.absatz(f"Anmerkung: {ls.anmerkung}")
    pdf.abstand(10 * mm)
    pdf.unterschrift_bild(unterschrift, f"{ls.unterschrieben_von}, für {tafel.name}".rstrip(", "))
    return pdf.erzeugen()


@transaction.atomic
def erstellen(station: Station, benutzer, positionen, unterschrift: bytes, anmerkung: str = "",
              tour=None, datum: dt.date | None = None) -> Lieferschein:  # fmt: skip
    """Legt den Lieferschein mit fortlaufender Nummer und fertigem PDF an (ohne zu senden)."""
    e = TourenEinstellungen.objects.select_for_update().get(pk=TourenEinstellungen.laden().pk)
    ls = Lieferschein(
        nummer=e.naechste_nummer, station=station, station_name=station.name,
        station_anschrift=station.anschrift, tour=tour, tour_name=tour.name if tour else "",
        datum=datum or timezone.localdate(), anmerkung=anmerkung.strip()[:1000],
        erstellt_von=benutzer, unterschrieben_von=_name(benutzer),
    )  # fmt: skip
    ls.datei = privatdateien.ablegen(Lieferschein.ORDNER, _pdf(ls, positionen, unterschrift))
    ls.save()
    Position.objects.bulk_create(
        Position(lieferschein=ls, warengruppe=w, menge=m, einheit=einheit)
        for w, m, einheit in positionen
    )
    e.naechste_nummer += 1
    e.save(update_fields=["naechste_nummer"])
    return ls


def pdf(ls: Lieferschein) -> bytes | None:
    return privatdateien.lesen(Lieferschein.ORDNER, ls.datei) if ls.datei else None


def dateiname(ls: Lieferschein) -> str:
    return f"Lieferschein-{ls.nummer}-{ls.datum:%Y-%m-%d}.pdf"


def senden(ls: Lieferschein) -> bool:
    """Schickt das PDF an die Station. Hält fest, wohin es ging oder warum nicht."""
    ziel = ls.station.lieferschein_an if ls.station else ""
    inhalt = pdf(ls)
    fehler = ""
    if not ziel:
        fehler = "Bei der Station ist keine E-Mail-Adresse eingetragen."
    elif inhalt is None:
        fehler = "Das PDF fehlt."
    elif not mail.eingerichtet():
        fehler = "Es ist kein Mailserver eingerichtet."
    else:
        tafel = TafelEinstellungen.laden()
        text = f"{TourenEinstellungen.laden().mail_text.strip()}\n{tafel.name}".strip()
        try:
            mail.senden(
                f"Lieferschein Nr. {ls.nummer} vom {ls.datum:%d.%m.%Y} – {tafel.name}".rstrip(" –"),
                text, [ziel], anhaenge=[(dateiname(ls), inhalt, "application/pdf")],
                art="lieferschein",
            )  # fmt: skip
        except mail.MailFehler as grund:
            fehler = str(grund)
    ls.mail_fehler = fehler[:300]
    if not fehler:
        ls.gesendet_an, ls.gesendet_am = ziel, timezone.now()
    ls.save(update_fields=["mail_fehler", "gesendet_an", "gesendet_am"])
    return not fehler


def am_tag(tag: dt.date, stationen) -> dict[int, Lieferschein]:
    """Der (neueste) Lieferschein des Tages je Station – für die Ansicht unterwegs."""
    scheine = Lieferschein.objects.filter(datum=tag, station__in=stationen).order_by("nummer")
    return {ls.station_id: ls for ls in scheine}


def fristen_anwenden(heute: dt.date | None = None) -> int:
    """Löscht Lieferscheine nach der eingestellten Aufbewahrungszeit, samt PDF."""
    heute = heute or timezone.localdate()
    jahre = TourenEinstellungen.laden().aufbewahrung_jahre
    try:
        grenze = heute.replace(year=heute.year - jahre)
    except ValueError:  # 29. Februar
        grenze = heute.replace(year=heute.year - jahre, day=28)
    alte = Lieferschein.objects.filter(datum__lt=grenze)
    anzahl = 0
    for ls in alte:
        if ls.datei:
            privatdateien.loeschen(Lieferschein.ORDNER, ls.datei)
        ls.delete()
        anzahl += 1
    return anzahl
