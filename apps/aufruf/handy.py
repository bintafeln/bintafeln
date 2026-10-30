"""Wartezeit aufs Handy (ADR 0090): Kunden sehen unter /warten/, wie viele noch vor ihnen sind.

Einmal anmelden mit Kundennummer und Geburtsdatum der Hauptperson (oder über den QR-Code auf
einem neu gedruckten Ausweis), danach merkt sich das Handy den Haushalt über einen zufälligen
Schlüssel im Cookie. Gezeigt wird nur der eigene Platz an der eigenen Ausgabestelle, keine Namen.
Höchstens ``HandyEinstellungen.geraete`` Handys je Haushalt; der Einlass setzt zurück.
"""

import datetime as dt
import hashlib
import secrets

from django.conf import settings
from django.urls import reverse
from django.utils import timezone

from apps.aufruf import ablauf
from apps.aufruf.models import AufrufEinstellungen, HandyCode, HandyEinstellungen, HandyZugang
from apps.kunden.models import Haushalt

COOKIE = "bintafeln_warten"
COOKIE_TAGE = 400
FEHLVERSUCHE = 8  # je Adresse und Stunde, dann gesperrt
SCHRITTE_FUER_SCHAETZUNG = 10


class Abgelehnt(Exception):
    """Anmeldung nicht möglich; ``args[0]`` ist der Schlüssel des Textes (uebersetzungen)."""


def pruefsumme(schluessel: str) -> str:
    return hashlib.sha256(schluessel.encode()).hexdigest()


def stelle_von(h: Haushalt):
    g = h.kundengruppe
    return g.ausgabestelle if g and g.ausgabestelle_id else None


def _einstellungen(h: Haushalt) -> AufrufEinstellungen | None:
    stelle = stelle_von(h)
    if stelle is None:
        return None
    zentral = HandyEinstellungen.laden()
    if zentral.modus == HandyEinstellungen.Modus.AUS:
        return None
    e = AufrufEinstellungen.laden(stelle)
    if not e.aktiv:
        return None
    return e if zentral.modus == HandyEinstellungen.Modus.ALLE or e.handy else None


def _einrichten(h: Haushalt, geraet: str) -> str:
    e = _einstellungen(h)
    if e is None:
        raise Abgelehnt("nicht_verfuegbar")
    grenze = HandyEinstellungen.laden().geraete
    if HandyZugang.objects.filter(kundennummer=h.kundennummer).count() >= grenze:
        raise Abgelehnt("zu_viele")
    schluessel = secrets.token_urlsafe(32)
    HandyZugang.objects.create(kundennummer=h.kundennummer, pruefsumme=pruefsumme(schluessel),
                               geraet=geraet[:120], zuletzt_am=timezone.now())  # fmt: skip
    return schluessel


def anmelden(nummer: str, geburtsdatum: dt.date | None, geraet: str = "") -> str:
    """Prüft Kundennummer und Geburtsdatum der Hauptperson; liefert den Schlüssel fürs Handy."""
    h = ablauf._haushalt(ablauf.norm(nummer or "")) if nummer else None
    hp = h.hauptperson if h else None
    if not (hp and geburtsdatum and hp.geburtsdatum == geburtsdatum):
        raise Abgelehnt("falsch")
    if h.status != Haushalt.Status.AKTIV:
        raise Abgelehnt("nicht_verfuegbar")
    return _einrichten(h, geraet)


def code_einloesen(code: str, geraet: str = "") -> str:
    """QR-Code vom Ausweis: richtet das Handy ohne Geburtsdatum ein."""
    eintrag = HandyCode.objects.filter(code=code).first() if code else None
    h = Haushalt.objects.filter(kundennummer=eintrag.kundennummer).first() if eintrag else None
    if h is None or h.status != Haushalt.Status.AKTIV:
        raise Abgelehnt("code_ungueltig")
    return _einrichten(h, geraet)


def zugang(schluessel: str) -> HandyZugang | None:
    if not schluessel:
        return None
    z = HandyZugang.objects.filter(pruefsumme=pruefsumme(schluessel)).first()
    if z:
        HandyZugang.objects.filter(pk=z.pk).update(zuletzt_am=timezone.now())
    return z


def abmelden(schluessel: str) -> None:
    HandyZugang.objects.filter(pruefsumme=pruefsumme(schluessel or "")).delete()


def zuruecksetzen(kundennummer: str) -> int:
    """Am Einlass: alle Handys des Haushalts abmelden."""
    return HandyZugang.objects.filter(kundennummer=kundennummer).delete()[0]


def sprache_vorschlag(z: HandyZugang) -> str:
    """Sprache zur Staatsangehörigkeit der Hauptperson (wie bei den Mails), sonst leer."""
    from types import SimpleNamespace

    from apps.antraege import sprachen

    h = Haushalt.objects.filter(kundennummer=z.kundennummer).first()
    hp = h.hauptperson if h else None
    if not hp or not hp.staatsangehoerigkeit:
        return ""
    codes = sprachen.mail_sprachen(SimpleNamespace(staatsangehoerigkeit=hp.staatsangehoerigkeit,
                                                   sprache=""))  # fmt: skip
    return codes[-1] if codes[-1] != "de" else ""


def minuten_je_nummer(tag) -> float | None:
    """Aus den letzten Aufrufen des Tages: Minuten je aufgerufener Nummer (None ohne Daten)."""
    schritte = [s for s in (tag.stand.get("rueckgaengig") or []) if s.get("zeitpunkt")]
    schritte = schritte[-SCHRITTE_FUER_SCHAETZUNG:]
    if len(schritte) < 2:
        return None
    anfang = dt.datetime.fromisoformat(schritte[0]["zeitpunkt"])
    ende = dt.datetime.fromisoformat(schritte[-1]["zeitpunkt"])
    nummern = sum(len(s["nummern"]) for s in schritte[1:])
    minuten = (ende - anfang).total_seconds() / 60
    return minuten / nummern if nummern and minuten > 0 else None


def stand(z: HandyZugang, heute: dt.date | None = None) -> dict:
    """Was das Handy zeigt: ``art`` ist der Schlüssel des Textes, dazu Nummer, Platz, Minuten."""
    heute = heute or timezone.localdate()
    h = Haushalt.objects.filter(kundennummer=z.kundennummer).select_related(
        "kundengruppe__ausgabestelle").first()  # fmt: skip
    e = _einstellungen(h) if h and h.status == Haushalt.Status.AKTIV else None
    if e is None:
        return {"art": "nicht_verfuegbar"}
    stelle = e.ausgabestelle
    basis = {"nummer": h.kundennummer, "stelle": stelle.name}
    ergebnis = ablauf.abfrage(stelle, heute, h.kundennummer)
    if not ergebnis.get("active") or not ergebnis.get("gefunden"):
        return {**basis, "art": "kein_termin"}
    if ergebnis.get("abgeholt") or ergebnis.get("eingelassen"):
        return {**basis, "art": "erledigt"}
    if ergebnis.get("jetzt_dran"):
        return {**basis, "art": "jetzt"}
    if ergebnis.get("schon_dran"):
        return {**basis, "art": "aufgerufen"}
    vor = ergebnis.get("vor_der_nummer", 0)
    if ergebnis.get("vorschau"):
        return {**basis, "art": "vorschau", "vor": vor}
    tag = ablauf.tag_holen(stelle, heute)
    je = minuten_je_nummer(tag) if tag else None
    minuten = max(5, round(vor * je / 5) * 5) if je and vor else None
    return {**basis, "art": "warten", "vor": vor, "minuten": minuten}


def ausweis_qr(h) -> str:
    """Adresse für den QR-Code auf dem Ausweis; legt dabei einen neuen Code an (der alte gilt
    nicht mehr). Leer, wenn die Ausgabestelle die Handy-Anzeige nicht nutzt oder bintafeln keine
    öffentliche Adresse hat (Entwicklungsmodus)."""
    if not settings.DOMAIN or not getattr(h, "pk", None) or _einstellungen(h) is None:
        return ""
    eintrag, neu = HandyCode.objects.get_or_create(kundennummer=h.kundennummer)
    if not neu:
        eintrag.code = secrets.token_urlsafe(24)
        eintrag.save()
    return f"https://{settings.DOMAIN}{reverse('warten:code', args=[eintrag.code])}"


def qr_zeichnung(adresse: str, seite):
    """QR-Code als ReportLab-Zeichnung mit Kantenlänge ``seite`` (in Punkt)."""
    from reportlab.graphics.barcode.qr import QrCodeWidget
    from reportlab.graphics.shapes import Drawing

    code = QrCodeWidget(adresse, barBorder=0)
    x1, y1, x2, y2 = code.getBounds()
    zeichnung = Drawing(seite, seite, transform=[seite / (x2 - x1), 0, 0, seite / (y2 - y1), 0, 0])
    zeichnung.add(code)
    return zeichnung


def aushang_pdf(adresse: str) -> bytes:
    """Aushang für den Eingang: QR-Code zu /warten/ und kurze Anleitung (einmal drucken)."""
    from reportlab.lib.units import mm

    from apps.core.pdf import Pdf

    pdf = Pdf("Wartezeit auf dem Handy", "Waiting time on your phone")
    pdf.absatz("Mit dem Handy diesen Code scannen, einmal Kundennummer und Geburtsdatum der "
               "Hauptperson eingeben – dann sehen Sie, wie viele noch vor Ihnen sind.")  # fmt: skip
    englisch = ("Scan this code, enter your customer number and the date of birth of the main "
                "person once – then you can see how many people are ahead of you.")  # fmt: skip
    pdf.absatz(englisch, klein=True)
    pdf.abstand(8 * mm)
    pdf.element(qr_zeichnung(adresse, 120 * mm))
    pdf.abstand(6 * mm)
    pdf.absatz(adresse)
    return pdf.erzeugen()
