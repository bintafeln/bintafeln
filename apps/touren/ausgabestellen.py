"""Ausgabestellen der Tafel als Stationen der Touren (ADR 0171).

Jede Ausgabestelle – auch die Zentrale – kann auf einer Tour angefahren werden: am Anfang, am Ende
oder zwischendrin. Damit niemand sie ein zweites Mal eintippt, legt ``abgleichen()`` zu jeder
aktiven Ausgabestelle mit Anschrift eine Station an und hält sie aktuell.

Aus der Ausgabestelle kommen Name, Anschrift, Telefon und E-Mail (``FELDER``); sie werden an der
Station nicht von Hand geändert. Alles andere – Anfahrt, Abholzeit, Lieferschein, Notiz – gehört
der Station und bleibt beim Abgleich unberührt. Schließt eine Ausgabestelle oder wird sie
abgeschaltet, wird auch die Station abgeschaltet; gelöscht wird nie.
"""

import re

from apps.touren.models import Station

FELDER = ("name", "strasse", "hausnummer", "plz", "ort", "telefon", "email", "aktiv")
_NUMMER = r"\d+\s?[a-zA-Z]?"
_HAUSNUMMER = re.compile(rf"^(?P<strasse>.*?\D)\s+(?P<nr>{_NUMMER}(?:\s?[-/]\s?{_NUMMER})?)$")


def kennung(stelle) -> str:
    return f"AS-{stelle.pk}"


def strasse_teilen(text: str) -> tuple[str, str]:
    """„Musterweg 12a“ → („Musterweg“, „12a“); lässt sich keine Hausnummer erkennen, bleibt alles
    in der Straße."""
    text = " ".join((text or "").split())
    treffer = _HAUSNUMMER.match(text)
    if not treffer:
        return text, ""
    return treffer["strasse"].strip(), treffer["nr"].strip()


def _werte(stelle) -> dict:
    strasse, nummer = strasse_teilen(stelle.strasse)
    return {
        "name": stelle.name[:150], "strasse": strasse[:150], "hausnummer": nummer[:20],
        "plz": stelle.plz, "ort": stelle.ort, "telefon": stelle.telefon, "email": stelle.email,
        "aktiv": stelle.aktiv,
    }  # fmt: skip


def abgleichen() -> dict:
    """Legt fehlende Stationen an und übernimmt geänderte Angaben. Liefert ``neu``, ``geaendert``
    und ``ohne_anschrift`` (Namen aktiver Ausgabestellen, denen Straße, PLZ oder Ort fehlt – die
    lassen sich nicht anfahren und bekommen deshalb keine Station)."""
    from apps.kunden.models import Ausgabestelle

    vorhanden = {s.ausgabestelle_id: s for s in Station.objects.filter(ausgabestelle__isnull=False)}
    bericht = {"neu": 0, "geaendert": 0, "ohne_anschrift": []}
    for stelle in Ausgabestelle.objects.all():
        station = vorhanden.get(stelle.pk)
        vollstaendig = bool(stelle.strasse.strip() and stelle.plz.strip() and stelle.ort.strip())
        if station is None:
            if not stelle.aktiv:
                continue
            if not vollstaendig:
                bericht["ohne_anschrift"].append(stelle.name)
                continue
            # schon von Hand als Station angelegt? Dann diese verknüpfen statt eine zweite anzulegen
            station = Station.objects.filter(
                ausgabestelle__isnull=True, art=Station.Art.AUSGABESTELLE, name__iexact=stelle.name
            ).first()
            if station is None:
                Station.objects.create(
                    kennung=kennung(stelle), art=Station.Art.AUSGABESTELLE, ausgabestelle=stelle,
                    lieferschein=False, **_werte(stelle),
                )  # fmt: skip
                bericht["neu"] += 1
                continue
            station.ausgabestelle = stelle
        werte = _werte(stelle)
        if not vollstaendig:
            # Anschrift an der Ausgabestelle gelöscht: die alte an der Station stehen lassen
            for feld in ("strasse", "hausnummer", "plz", "ort"):
                werte.pop(feld)
        geaendert = [f for f, w in werte.items() if getattr(station, f) != w]
        if geaendert or station.pk and station.ausgabestelle_id not in vorhanden:
            for feld in geaendert:
                setattr(station, feld, werte[feld])
            station.save()
            bericht["geaendert"] += 1
    return bericht


def nach_speichern(sender, instance, raw=False, **kwargs):
    """Ausgabestelle gespeichert: die Station gleich nachziehen (und über sie das Adressbuch,
    ADR 0184), nicht erst beim täglichen Lauf."""
    if not raw:
        abgleichen()
