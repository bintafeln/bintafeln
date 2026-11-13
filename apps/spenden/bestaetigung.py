"""Zuwendungsbestätigungen (ADR 0045) nach den amtlichen Mustern (BMF-Schreiben zu § 10b EStG),
gezeichnet als Vordruck in ``vordruck.py`` (ADR 0136).

Ausstellen vergibt eine fortlaufende Nummer und verknüpft die Spenden, damit keine Spende zweimal
bestätigt wird. Das PDF entsteht jedes Mal neu aus den gespeicherten Daten; stornierte
Bestätigungen tragen den Vermerk „STORNIERT“.

Mit eingescannter Unterschrift (ADR 0130): Wer ausstellt und eine eigene ``Unterschrift``
hinterlegt hat, unterschreibt damit. Das PDF wird dann einmal erzeugt und als ``Ausfertigung``
gespeichert; ab da wird genau dieses PDF ausgegeben. Es gibt keinen Weg, mit der Unterschrift
einer anderen Person auszustellen.
"""

import io

from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader, PdfWriter

from apps.core import privatdateien
from apps.core.models import TafelEinstellungen
from apps.core.pdf import text
from apps.spenden import vordruck
from apps.spenden.models import (
    Ausfertigung,
    Spende,
    SpendenEinstellungen,
    Unterschrift,
    Zuwendungsbestaetigung,
    naechste_nummer,
    summe,
)
from apps.spenden.vordruck import Vordruck


class BestaetigungsFehler(ValueError):
    pass


def _bereit(e: SpendenEinstellungen) -> None:
    fehlt = e.fehlende_angaben()
    if fehlt:
        raise BestaetigungsFehler(
            "Für Zuwendungsbestätigungen fehlen noch Angaben unter „Einstellungen → Spenden“: "
            + ", ".join(fehlt)
            + "."
        )


def offene_geldspenden(adresse, jahr: int):
    """Geldspenden (und abziehbare Mitgliedsbeiträge) eines Jahres ohne gültige Bestätigung."""
    spenden = Spende.objects.filter(
        adresse=adresse, art=Spende.Art.GELD, datum__year=jahr, betrag__gt=0
    ).exclude(bestaetigung__isnull=False, bestaetigung__storniert_am__isnull=True)
    if not SpendenEinstellungen.laden().mitgliedsbeitraege_abziehbar:
        spenden = spenden.exclude(mitgliedsbeitrag=True)
    # Spenden mit Beleg aus einem anderen Programm (ADR 0128): Was dort schon versendet ist,
    # bestätigt bintafeln nie noch einmal. Ein einzelner, dort noch nicht versendeter Beleg ist
    # selbst die Bestätigung (er liegt dem Dankesbrief bei). Erst bei mehreren offenen Spenden im
    # Jahr stellt bintafeln eine Sammelbestätigung aus – dann liegen die Einzelbelege nicht bei.
    spenden = spenden.exclude(fremdbeleg=Spende.Fremdbeleg.VERSENDET)
    if spenden.count() == 1 and spenden.filter(fremdbeleg=Spende.Fremdbeleg.OFFEN).exists():
        return spenden.none()
    return spenden


def jahresliste(jahr: int) -> list[tuple]:
    """[(Adresse, Summe, Anzahl)] aller Spender mit noch nicht bestätigten Geldspenden."""
    from apps.adressen.models import Adresse

    ergebnis = []
    for a in Adresse.objects.filter(spenden__art=Spende.Art.GELD,
                                    spenden__datum__year=jahr).distinct():  # fmt: skip
        offen = offene_geldspenden(a, jahr)
        if offen.exists():
            ergebnis.append((a, summe(offen), offen.count()))
    return ergebnis


def eigene_unterschrift(benutzer) -> Unterschrift | None:
    """Die Unterschrift dieses Kontos, wenn Bild und Name hinterlegt sind. Der einzige Weg zu
    einer Unterschrift führt über das angemeldete Konto – nie über eine Auswahl."""
    if benutzer is None or not getattr(benutzer, "is_authenticated", False):
        return None
    u = Unterschrift.objects.filter(benutzer=benutzer).first()
    return u if u and u.bild and u.name_funktion else None


def unterschreiben(b: Zuwendungsbestaetigung, benutzer) -> Ausfertigung | None:
    """Erzeugt das PDF mit der eigenen Unterschrift von ``benutzer`` und hält es fest. Ohne
    hinterlegte Unterschrift passiert nichts (die Bestätigung hat dann eine Linie für die
    Unterschrift von Hand)."""
    u = eigene_unterschrift(benutzer)
    bild = privatdateien.lesen(Unterschrift.ORDNER, u.bild) if u else None
    if not bild or b.storniert_am:
        return None
    inhalt = _erzeugen([b], unterschrift=(bild, u.name_funktion))
    return Ausfertigung.objects.create(
        bestaetigung=b, unterzeichner=benutzer, name_funktion=u.name_funktion,
        datei=privatdateien.ablegen(Ausfertigung.ORDNER, inhalt),
    )  # fmt: skip


def neu_unterschreiben(b: Zuwendungsbestaetigung, benutzer) -> Ausfertigung:
    """Dieselbe Bestätigung (gleiche Nummer, gleicher Inhalt) mit der eigenen Unterschrift neu
    ausfertigen, z. B. wenn die Person, die sie ausgestellt hat, ausgeschieden ist. Frühere
    Ausfertigungen bleiben unverändert gespeichert; ab jetzt gilt die neue."""
    if b.storniert_am:
        raise BestaetigungsFehler("Eine stornierte Bestätigung lässt sich nicht unterschreiben.")
    if not eigene_unterschrift(benutzer):
        raise BestaetigungsFehler("Bitte zuerst Ihre eigene Unterschrift hinterlegen.")
    ausfertigung = unterschreiben(b, benutzer)
    if ausfertigung is None:
        raise BestaetigungsFehler("Ihre Unterschrift ließ sich nicht lesen; bitte neu hochladen.")
    return ausfertigung


@transaction.atomic
def geld_ausstellen(adresse, jahr: int, von: str, unterzeichner=None) -> Zuwendungsbestaetigung:
    """Eine Spende: Einzelbestätigung; mehrere: Sammelbestätigung für das Jahr."""
    _bereit(SpendenEinstellungen.laden())
    spenden = list(offene_geldspenden(adresse, jahr).select_for_update(of=("self",)))
    if not spenden:
        raise BestaetigungsFehler(f"{adresse.name} hat {jahr} keine unbestätigten Geldspenden.")
    art = Zuwendungsbestaetigung.Art.GELD if len(spenden) == 1 else (
        Zuwendungsbestaetigung.Art.SAMMEL)  # fmt: skip
    b = Zuwendungsbestaetigung.objects.create(
        nummer=naechste_nummer(), art=art, adresse=adresse, ausgestellt_am=timezone.localdate(),
        betrag=sum(s.betrag for s in spenden), ausgestellt_von=von,
    )  # fmt: skip
    Spende.objects.filter(pk__in=[s.pk for s in spenden]).update(bestaetigung=b)
    unterschreiben(b, unterzeichner)
    return b


@transaction.atomic
def sach_ausstellen(spende: Spende, von: str, unterzeichner=None) -> Zuwendungsbestaetigung:
    _bereit(SpendenEinstellungen.laden())
    spende = Spende.objects.select_for_update().get(pk=spende.pk)
    if spende.art != Spende.Art.SACH:
        raise BestaetigungsFehler("Das ist keine Sachspende.")
    if spende.bestaetigt:
        raise BestaetigungsFehler("Für diese Sachspende gibt es schon eine Bestätigung.")
    if not spende.betrag:
        raise BestaetigungsFehler("Ohne Wert der Sachspende ist keine Bestätigung möglich.")
    b = Zuwendungsbestaetigung.objects.create(
        nummer=naechste_nummer(), art=Zuwendungsbestaetigung.Art.SACH, adresse=spende.adresse,
        ausgestellt_am=timezone.localdate(), betrag=spende.betrag, ausgestellt_von=von,
    )  # fmt: skip
    spende.bestaetigung = b
    spende.save(update_fields=["bestaetigung"])
    unterschreiben(b, unterzeichner)
    return b


@transaction.atomic
def stornieren(b: Zuwendungsbestaetigung, von: str) -> None:
    """Nummer bleibt vergeben; die Spenden lassen sich neu bestätigen (sie zeigen bis dahin
    noch auf die stornierte Bestätigung, damit deren PDF vollständig bleibt)."""
    if b.storniert_am:
        return
    b.storniert_am, b.storniert_von = timezone.now(), von
    b.save(update_fields=["storniert_am", "storniert_von"])


# --- PDF ---------------------------------------------------------------------------------------


def _koerperschaft(e, tafel) -> tuple[str, str]:
    return e.koerperschaft or tafel.name, e.anschrift or tafel.anschrift


def _zuwendender(adresse) -> list[str]:
    """Name in der ersten Zeile, die Anschrift in der zweiten (Teile mit „ | “ getrennt)."""
    zeilen = adresse.anschrift_zeilen
    return [zeilen[0], " | ".join(zeilen[1:])] if len(zeilen) > 1 else zeilen


def _seite(v: Vordruck, b: Zuwendungsbestaetigung, e, tafel, unterschrift=None) -> None:
    """Eine Bestätigung im Aufbau der amtlichen Vordrucke; Sammelbestätigung mit Anlage."""
    name, anschrift = _koerperschaft(e, tafel)
    spenden = list(b.spenden.order_by("datum", "pk"))
    sammel, sach = b.art == b.Art.SAMMEL, b.art == b.Art.SACH
    luft = 4 if b.art == b.Art.GELD else 0  # Einzelbestätigung: etwas höhere Kästen
    v.nummer = b.nummer
    v.storniert = (f"STORNIERT am {timezone.localtime(b.storniert_am):%d.%m.%Y} – diese "
                   "Bestätigung ist ungültig") if b.storniert_am else ""  # fmt: skip

    t = v.feldkasten(102.5 if sammel else 64.5,
                     "Aussteller (Bezeichnung und Anschrift der steuerbegünstigten Einrichtung)",
                     [vordruck.zeile(name, anschrift)], mindestens=37 + luft)  # fmt: skip
    if sach:
        titel = "Bestätigung über Sachzuwendungen"
    elif sammel:
        titel = "Sammelbestätigung über Geldzuwendungen/Mitgliedsbeiträge"
    else:
        titel = "Bestätigung über Geldzuwendungen/Mitgliedsbeitrag"
    t = v.absatz(text(titel), t + 9.1 + luft / 2, vordruck.TITEL)
    t = v.absatz("im Sinne des § 10b des Einkommensteuergesetzes an eine der in § 5 Abs. 1 Nr. 9 "
                 "des Körperschaftsteuergesetzes bezeichneten Körperschaften, "
                 "Personenvereinigungen oder Vermögensmassen", t + 1.4)  # fmt: skip
    t = v.feldkasten(t + 9.5 + luft / 2, "Name und Anschrift des Zuwendenden:",
                     _zuwendender(b.adresse), mindestens=37 + luft)  # fmt: skip

    if sammel:
        zeitraum = (f"{vordruck.datum(spenden[0].datum)} - {vordruck.datum(spenden[-1].datum)}"
                    if spenden else "")  # fmt: skip
        felder = [("Gesamtbetrag der Zuwendung in € - in Ziffern -", vordruck.betrag(b.betrag)),
                  ("- in Buchstaben -", vordruck.ziffern(b.betrag)),
                  ("Zeitraum der Sammelbestätigung:", zeitraum)]  # fmt: skip
    else:
        felder = [
            (
                ("Wert" if sach else "Betrag") + " der Zuwendung in € - in Ziffern -",
                vordruck.betrag(b.betrag),
            ),
            ("- in Buchstaben -", vordruck.ziffern(b.betrag)),
            ("Tag der Zuwendung:", vordruck.datum(spenden[0].datum) if spenden else ""),
        ]
    t = v.betragskasten(t + 19 + luft / 4, felder, mindestens=37 + luft)  # fmt: skip

    if sach:
        s = spenden[0] if spenden else None
        bezeichnung = "Genaue Bezeichnung der Sachzuwendung mit Alter, Zustand, Kaufpreis usw."
        t = v.feldkasten(t + 12, bezeichnung, [s.beschreibung if s else ""], mindestens=30)
        t += 10
        for wert, satz in vordruck.HERKUNFT.items():
            v.kreuz(vordruck.TX, t, bool(s) and s.herkunft == wert)
            t = v.absatz(satz, t, x=vordruck.EINRUECKEN) + 5
        v.kreuz(vordruck.TX, t, bool(s) and s.unterlagen)
        t = v.absatz("Geeignete Unterlagen, die zur Wertermittlung gedient haben, z. B. Rechnung, "
                     "Gutachten, liegen vor.", t, x=vordruck.EINRUECKEN) + 16  # fmt: skip
    elif sammel:
        t += 28
    else:
        verzicht = bool(spenden) and spenden[0].verzicht_aufwand
        t += 20.5
        v.absatz("Es handelt sich um den Verzicht auf Erstattung von Aufwendungen", t)
        v.wort("Ja", 369, t)
        v.kreuz(381, t, verzicht)
        v.wort("Nein", 403, t)
        v.kreuz(421, t, not verzicht)
        t += 30

    unten = vordruck.verwendung(v, vordruck.grundlage(v, t, e), e, mitgliedsbeitrag_satz=not sach,
                                luft=luft * 4.5)  # fmt: skip
    if sammel:
        t = v.absatz("Es wird bestätigt, dass über die in der Gesamtsumme enthaltenen Zuwendungen "
                     "keine weiteren Bestätigungen, weder formelle Zuwendungsbestätigungen noch "
                     "Beitragsquittungen oder Ähnliches, ausgestellt wurden und werden.",
                     unten + 19)  # fmt: skip
        t = v.absatz("Ob es sich um den Verzicht auf Erstattung von Aufwendungen handelt, ist der "
                     "Anlage zur Sammelbestätigung zu entnehmen.", t + 10)  # fmt: skip
        linie = t + 44.5
    else:
        linie = unten + 86.5
    vordruck.unterschrift(v, linie, f"{e.ort or tafel.ort}, {vordruck.datum(b.ausgestellt_am)}",
                          unterschrift[0] if unterschrift else None)  # fmt: skip
    vordruck.hinweis(v, linie + 20 + luft / 2, e)
    v.seite_fertig()
    if sammel:
        vordruck.anlage(v, spenden, b.betrag)
        v.seite_fertig()


def _erzeugen(bestaetigungen, unterschrift=None) -> bytes:
    e, tafel = SpendenEinstellungen.laden(), TafelEinstellungen.laden()
    v = Vordruck("Zuwendungsbestätigung", e.koerperschaft or tafel.name or "bintafeln")
    for b in bestaetigungen:
        _seite(v, b, e, tafel, unterschrift)
    return v.erzeugen()


def ausfertigung(b: Zuwendungsbestaetigung) -> bytes | None:
    """Das gespeicherte, unterschriebene PDF (die neueste Ausfertigung), wenn es eines gibt.
    Stornierte Bestätigungen werden neu erzeugt – mit Vermerk und ohne Unterschrift."""
    if b.storniert_am:
        return None
    neueste = b.ausfertigungen.first()
    return privatdateien.lesen(Ausfertigung.ORDNER, neueste.datei) if neueste else None


def pdf(bestaetigungen) -> bytes:
    """Alle Bestätigungen in einem PDF: unterschriebene so, wie sie gespeichert sind, die
    übrigen neu aus den Daten."""
    bestaetigungen = list(bestaetigungen)
    fertige = {b.pk: inhalt for b in bestaetigungen if (inhalt := ausfertigung(b))}
    if not fertige:
        return _erzeugen(bestaetigungen)
    gesamt = PdfWriter()
    for b in bestaetigungen:
        gesamt.append(PdfReader(io.BytesIO(fertige.get(b.pk) or _erzeugen([b]))))
    puffer = io.BytesIO()
    gesamt.write(puffer)
    return puffer.getvalue()
