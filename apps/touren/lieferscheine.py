"""Lieferscheine an den Stationen (ADR 0149): ausfüllen, unterschreiben, als PDF festhalten und
der Station per E-Mail schicken."""

import base64
import binascii
import datetime as dt
import io
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape
from PIL import Image, UnidentifiedImageError

from apps.core import mail, privatdateien
from apps.core.models import TafelEinstellungen
from apps.touren import vordruck
from apps.touren.models import Lieferschein, Position, Station, TourenEinstellungen, Warengruppe

MAX_UNTERSCHRIFT = 400_000  # Bytes der PNG-Datei aus dem Unterschriftsfeld
MAX_KANTE = 6000  # Pixel; größere Bilder kommen nicht aus dem Unterschriftsfeld
UNTERSCHRIFT_GROESSE = (2000, 1000)  # darauf wird ein größeres Bild verkleinert
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
    if bild.format != "PNG" or bild.width > MAX_KANTE or bild.height > MAX_KANTE:
        raise LieferscheinFehler("Die Unterschrift konnte nicht gelesen werden.")
    bild = bild.convert("RGBA")
    # Große Bildschirme (ein großes Tablet quer) liefern ein breiteres Bild, als der Lieferschein
    # braucht: verkleinern statt ablehnen
    bild.thumbnail(UNTERSCHRIFT_GROESSE)
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
    """Der Lieferschein im Aussehen des bekannten Vordrucks (``vordruck.py``): Jede Warengruppe
    hat ihre Zeile, auch ohne Menge („-“) – so sieht die Station, dass nichts vergessen wurde."""
    mengen = {w: Position(menge=m, einheit=e).menge_text for w, m, e in positionen}
    gruppen = [g.name for g in warengruppen()]
    gruppen += [w for w in mengen if w not in gruppen]  # inzwischen abgeschaltete Gruppe
    return vordruck.zeichnen(
        tafel=TafelEinstellungen.laden(), nummer=ls.nummer, datum=ls.datum,
        station_name=ls.station_name, station_anschrift=ls.station_anschrift,
        zeilen=[(mengen.get(g, ""), g) for g in gruppen], anmerkung=ls.anmerkung,
        unterschrift=unterschrift, unterschrieben_von=ls.unterschrieben_von,
    )  # fmt: skip


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


def datenschutz_adresse(tafel) -> str:
    """Öffentliche Seite mit der Datenschutzerklärung der Tafel, wenn es eine gibt und die
    Installation unter einer Domain läuft; sonst leer."""
    if not settings.DOMAIN or not tafel.datenschutz_text:
        return ""
    return f"https://{settings.DOMAIN}{reverse('antrag:rechtstext', args=['de', 'datenschutz'])}"


def mail_inhalt(ls: Lieferschein, vorlage: str, tafel) -> tuple[str, str]:
    """Text und gestaltete Fassung der Mail an die Station: der Text der Tafel mit eingesetztem
    Namen der Tafel und der Station, darunter der Hinweis, warum die Station die Mail bekommt.
    Die erste Zeile ist in der gestalteten Fassung die Überschrift."""
    name = tafel.name or "Tafel"
    text = (vorlage or "").strip().replace("{tafel}", name).replace("{station}", ls.station_name)
    if "{tafel}" not in (vorlage or "") and tafel.name:  # ältere Texte: Name als Gruß darunter
        text = f"{text}\n{tafel.name}"
    grund = (f"Sie erhalten diese Nachricht, weil Ihre E-Mail-Adresse bei uns ({name}) als "
             f"Empfängeradresse der Lieferscheine für {ls.station_name} eingetragen ist. Bei "
             f"Fragen melden Sie sich bei Ihrer Tafel.")  # fmt: skip
    datenschutz = datenschutz_adresse(tafel)
    schluss = f"{grund} Informationen zum Datenschutz: {datenschutz}" if datenschutz else grund
    absaetze = [a for a in text.split("\n\n") if a.strip()]
    html = "".join(
        f"<{'h2' if nr == 0 else 'p'}>{escape(a.strip()).replace(chr(10), '<br>')}"
        f"</{'h2' if nr == 0 else 'p'}>"
        for nr, a in enumerate(absaetze)
    )
    link = (f' Informationen zum Datenschutz finden Sie <a href="{escape(datenschutz)}">hier</a>.'
            if datenschutz else "")  # fmt: skip
    html += f'<hr><p style="font-size: 85%; color: #555;">{escape(grund)}{link}</p>'
    return f"{text}\n\n{'_' * 40}\n{schluss}", html


def senden(ls: Lieferschein) -> bool:
    """Schickt das PDF an die Station – je nach Einstellung gar nicht oder zum Test nur an die
    Test-Adresse (dann gilt der Lieferschein weiter als nicht verschickt und lässt sich später
    richtig senden). Hält fest, wohin es ging oder warum nicht."""
    einstellungen = TourenEinstellungen.laden()
    Versand = TourenEinstellungen.Versand
    test = einstellungen.versand == Versand.TEST
    an_station = ls.station.lieferschein_an if ls.station else ""
    ziel = einstellungen.test_email if test else an_station
    inhalt = pdf(ls)
    fehler = ""
    if einstellungen.versand == Versand.AUS:
        fehler = "Der Versand per E-Mail ist ausgeschaltet (Einstellungen → Touren)."
    elif not ziel:
        fehler = ("Für den Testbetrieb ist keine Test-Adresse eingetragen." if test
                  else "Bei der Station ist keine E-Mail-Adresse eingetragen.")  # fmt: skip
    elif inhalt is None:
        fehler = "Das PDF fehlt."
    elif not mail.eingerichtet():
        fehler = "Es ist kein Mailserver eingerichtet."
    else:
        tafel = TafelEinstellungen.laden()
        text, html = mail_inhalt(ls, einstellungen.mail_text, tafel)
        betreff = f"Lieferschein Nr. {ls.nummer} vom {ls.datum:%d.%m.%Y} – {tafel.name}"
        if test:
            betreff = f"[Test] {betreff}"
            vorab = (f"Testbetrieb: Diese Mail ginge sonst an {an_station or '(keine Adresse)'} "
                     f"({ls.station_name}).")  # fmt: skip
            text = f"{vorab}\n\n{text}"
            html = f"<p><em>{escape(vorab)}</em></p>{html}"
        try:
            mail.senden(
                betreff.rstrip(" –"),
                text, [ziel], html=html,
                anhaenge=[(dateiname(ls), inhalt, "application/pdf")], art="lieferschein",
            )  # fmt: skip
        except mail.MailFehler as grund:
            fehler = str(grund)
        else:
            if test:
                fehler = f"Testbetrieb: nur an {ziel} geschickt, nicht an die Station."
    ls.mail_fehler = fehler[:300]
    if not fehler:
        ls.gesendet_an, ls.gesendet_am = ziel, timezone.now()
    ls.save(update_fields=["mail_fehler", "gesendet_an", "gesendet_am"])
    return not fehler


def darf_sehen(benutzer, ls: Lieferschein) -> bool:
    """Ohne das Recht, alle Lieferscheine zu sehen: nur der eigene und die der Tour, auf der man
    an dem Tag gefahren ist."""
    from apps.touren import ablauf

    if ls.erstellt_von_id == benutzer.pk:
        return True
    return ls.tour is not None and ablauf.faehrt_mit(ls.tour, ls.datum,
                                                     ablauf.person_von(benutzer))  # fmt: skip


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
