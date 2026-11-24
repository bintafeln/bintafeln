"""Wechselwunsch eines Kunden: andere Uhrzeit, anderer Tag oder andere Ausgabestelle (ADR 0173).

Am Einlass oder im Büro wird der Wunsch Schritt für Schritt eingegrenzt (``moeglichkeiten()``
bietet nur Kundengruppen mit freiem Platz an) und als ``Wechselwunsch`` samt Notiz festgehalten.
Entschieden wird er von jemandem mit dem Recht ``kunden.wechsel_entscheiden``; der Kunde bekommt
die Antwort per E-Mail. Damit das geht, prüft ``erreichbar()`` vorher, ob am Haushalt E-Mail und
Telefon stehen; fehlendes wird beim Eintragen nachgetragen.
"""

import datetime as dt

from django.db import transaction
from django.utils import timezone

from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.core import mail
from apps.kunden import gruppen, historie, verlegung
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    HaushaltEreignis,
    Kundengruppe,
    Notiz,
    Wechselwunsch,
)

RICHTUNGEN = [("frueher", "früher"), ("spaeter", "später"), ("egal", "egal, nur anders")]
TAGNAMEN = dict(zip(
    WOCHENTAGE,
    ["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag", "Samstag", "Sonntag"],
    strict=True,
))  # fmt: skip


class WechselFehler(ValueError):
    pass


def _name(benutzer) -> str:
    return (benutzer.get_full_name() or benutzer.get_username())[:150]


def gruppe_text(g: Kundengruppe | None) -> str:
    """„Zentrale – Mi 12:30 (Mi, 12:30 Uhr)“: so, dass man es am Einlass vorlesen kann."""
    if g is None:
        return "keine Kundengruppe"
    teile = [", ".join(wochentage(g.wochentage))]
    if g.uhrzeit:
        teile.append(f"{g.uhrzeit:%H:%M} Uhr")
    zusatz = ", ".join(t for t in teile if t)
    stelle = f"{g.ausgabestelle.name} – " if g.ausgabestelle_id else ""
    return f"{stelle}{g.name}" + (f" ({zusatz})" if zusatz else "")


def arten(h: Haushalt) -> list[tuple[str, str]]:
    """Was sich ändern kann. Ohne Kundengruppe (oder ohne Ausgabestelle) gibt es keinen
    „selben Tag“ – dann bleibt nur die Wahl der Ausgabestelle."""
    eigene = h.kundengruppe
    if eigene is None or eigene.ausgabestelle_id is None:
        return [(Wechselwunsch.Art.STELLE.value, "eine Ausgabestelle wählen")]
    return [(a.value, a.label) for a in Wechselwunsch.Art]


def tage_zur_wahl(h: Haushalt) -> list[tuple[str, str]]:
    """Andere Wochentage, an denen die eigene Ausgabestelle ausgibt."""
    eigene = h.kundengruppe
    if eigene is None or eigene.ausgabestelle_id is None:
        return []
    meine = set(wochentage(eigene.wochentage))
    da = set()
    for g in Kundengruppe.objects.filter(
        aktiv=True, intern=False, ausgabestelle=eigene.ausgabestelle_id
    ):
        da |= set(wochentage(g.wochentage))
    return [(t, TAGNAMEN[t]) for t in WOCHENTAGE if t in da and t not in meine]


def stellen_zur_wahl(h: Haushalt) -> list[Ausgabestelle]:
    """Andere aktive Ausgabestellen mit mindestens einer Kundengruppe."""
    eigene = h.kundengruppe.ausgabestelle_id if h.kundengruppe_id else None
    return list(
        Ausgabestelle.objects.filter(aktiv=True, kundengruppe__aktiv=True,
                                     kundengruppe__intern=False)
        .exclude(pk=eigene).distinct().order_by("name")
    )  # fmt: skip


def moeglichkeiten(h: Haushalt, was: str, richtung: str = "", tag: str = "",
                   stelle: int | None = None) -> list[dict]:  # fmt: skip
    """Die Kundengruppen, die zum Wunsch passen und aktuell einen freien Platz haben (geplante
    Zuzüge zählen als belegt, ``aufnahme.freie_gruppen``). Je Eintrag: gruppe, frei, text."""
    from apps.antraege.aufnahme import freie_gruppen

    eigene = h.kundengruppe
    meine_tage = set(wochentage(eigene.wochentage)) if eigene else set()
    passend = []
    for eintrag in freie_gruppen(h):
        g = eintrag["gruppe"]
        if eintrag["eigene"] or g.intern:
            continue
        tage = set(wochentage(g.wochentage))
        if was == Wechselwunsch.Art.UHRZEIT:
            if eigene is None or g.ausgabestelle_id != eigene.ausgabestelle_id:
                continue
            if not tage & meine_tage:
                continue
            beide = g.uhrzeit is not None and eigene.uhrzeit is not None
            if richtung == "frueher" and not (beide and g.uhrzeit < eigene.uhrzeit):
                continue
            if richtung == "spaeter" and not (beide and g.uhrzeit > eigene.uhrzeit):
                continue
        elif was == Wechselwunsch.Art.TAG:
            if eigene is None or g.ausgabestelle_id != eigene.ausgabestelle_id:
                continue
            if tag not in tage:
                continue
        elif was == Wechselwunsch.Art.STELLE:
            if stelle is None or g.ausgabestelle_id != stelle:
                continue
        else:
            continue
        passend.append({"gruppe": g, "frei": eintrag["frei"], "text": gruppe_text(g)})
    passend.sort(key=lambda e: (
        min((WOCHENTAGE.index(t) for t in wochentage(e["gruppe"].wochentage)), default=9),
        e["gruppe"].uhrzeit or dt.time(0), e["gruppe"].name,
    ))  # fmt: skip
    return passend


def erreichbar(h: Haushalt) -> dict:
    """Stehen am Haushalt eine E-Mail-Adresse und eine Telefonnummer? Die Antwort auf den Wunsch
    geht per E-Mail; das Telefon ist für Rückfragen."""
    return {"email": bool(h.email.strip()), "telefon": bool(h.telefon.strip())}


def beschreibung(h: Haushalt, was: str, richtung: str = "", tag: str = "", stelle=None,
                 gruppe: Kundengruppe | None = None) -> str:  # fmt: skip
    if was == Wechselwunsch.Art.UHRZEIT:
        wie = dict(RICHTUNGEN).get(richtung, "")
        text = "andere Uhrzeit am selben Tag" + (f" ({wie})" if wie and richtung != "egal" else "")
    elif was == Wechselwunsch.Art.TAG:
        text = "anderer Tag" + (f": {TAGNAMEN[tag]}" if tag in TAGNAMEN else "")
    else:
        text = "andere Ausgabestelle" + (f": {stelle.name}" if stelle else "")
    if gruppe is not None:
        text += f" → {gruppe_text(gruppe)}"
    else:
        text += " – dazu ist aktuell nichts frei"
    return text[:300]


@transaction.atomic
def eintragen(h: Haushalt, benutzer, was: str, richtung: str = "", tag: str = "",
              stelle: Ausgabestelle | None = None, gruppe: Kundengruppe | None = None,
              anmerkung: str = "", email: str = "", telefon: str = "",
              ohne_email: bool = False, eingetragen_an=None) -> Wechselwunsch:  # fmt: skip
    """Hält den Wunsch fest. Fehlende E-Mail-Adresse und Telefonnummer werden – wenn angegeben –
    am Haushalt gespeichert. Ohne E-Mail-Adresse geht es nur mit ``ohne_email`` (ausdrücklich:
    der Kunde hat keine); ganz ohne Kontakt gar nicht."""
    if was not in dict(arten(h)):
        raise WechselFehler("Bitte wählen, was sich ändern soll.")
    if gruppe is not None:
        erlaubt = {e["gruppe"].pk for e in moeglichkeiten(
            h, was, richtung, tag, stelle.pk if stelle else None)}  # fmt: skip
        if gruppe.pk not in erlaubt:
            raise WechselFehler(
                "Diese Kundengruppe passt nicht zum Wunsch oder ist nicht mehr frei."
            )
    if Wechselwunsch.objects.filter(
        kundennummer=h.kundennummer, status=Wechselwunsch.Status.OFFEN
    ).exists():
        raise WechselFehler("Zu diesem Kunden ist schon ein Wechselwunsch offen.")
    email, telefon = email.strip(), " ".join(telefon.split())[:50]
    da = erreichbar(h)
    if not da["email"] and not email and not ohne_email:
        raise WechselFehler(
            "Bitte die E-Mail-Adresse des Kunden eintragen – oder anhaken, dass er keine hat."
        )
    if not da["telefon"] and not telefon and not (da["email"] or email):
        raise WechselFehler(
            "Ohne E-Mail-Adresse und ohne Telefonnummer können wir den Kunden nicht erreichen. "
            "Bitte mindestens eines eintragen."
        )
    if (email and not da["email"]) or (telefon and not da["telefon"]):
        vorher = historie.schnappschuss(h)
        if email and not da["email"]:
            h.email = email
        if telefon and not da["telefon"]:
            h.telefon = telefon
        h.geaendert_am, h.geaendert_von = timezone.now(), _name(benutzer)
        h.save(update_fields=["email", "telefon", "geaendert_am", "geaendert_von"])
        historie.festhalten(
            h.kundennummer, vorher, historie.schnappschuss(h),
            quelle=HaushaltEreignis.Quelle.BEARBEITUNG, von=_name(benutzer),
            zusatz="Kontakt beim Wechselwunsch nachgetragen",
        )  # fmt: skip
    text = beschreibung(h, was, richtung, tag, stelle, gruppe)
    wunsch = Wechselwunsch.objects.create(
        kundennummer=h.kundennummer, art=was, bisher=gruppe_text(h.kundengruppe)[:150],
        wunsch=text, wunsch_gruppe=gruppe, anmerkung=" ".join(anmerkung.split())[:300],
        ohne_email=not h.email.strip(), stelle=eingetragen_an, von=_name(benutzer),
    )  # fmt: skip
    Notiz.objects.create(
        kundennummer=h.kundennummer, benutzer=benutzer, verfasst_von=_name(benutzer)[:100],
        text=(f"Will wechseln: {text}" + (f" – {wunsch.anmerkung}" if wunsch.anmerkung else "")
              + ". Die Verwaltung prüft das.")[:1000],
    )  # fmt: skip
    return wunsch


def offene():
    return Wechselwunsch.objects.filter(status=Wechselwunsch.Status.OFFEN)


def ziele(h: Haushalt | None, wunsch: Wechselwunsch) -> list[dict]:
    """Was beim Genehmigen zur Wahl steht: alle Kundengruppen mit freiem Platz, die gewünschte
    immer dabei (auch wenn sie inzwischen voll ist – dann mit Hinweis)."""
    from apps.antraege.aufnahme import freie_gruppen

    liste = [
        {"gruppe": e["gruppe"], "text": gruppe_text(e["gruppe"]), "voll": False}
        for e in freie_gruppen(h) if not e["eigene"]
    ]  # fmt: skip
    g = wunsch.wunsch_gruppe
    if g is not None and g.aktiv and all(e["gruppe"].pk != g.pk for e in liste):
        liste.insert(0, {"gruppe": g, "text": gruppe_text(g), "voll": True})
    return liste


def _mailen(wunsch: Wechselwunsch, h: Haushalt | None, betreff: str, text: str) -> str:
    """Schickt die Antwort an den Kunden; liefert, was daraus wurde (steht am Wunsch)."""
    from apps.core.models import TafelEinstellungen

    if h is None or not h.email.strip():
        return "keine E-Mail-Adresse – bitte anrufen oder am Einlass Bescheid sagen"
    tafel = TafelEinstellungen.laden().name
    try:
        mail.senden(f"{betreff} – {tafel}" if tafel else betreff,
                    text + (f"\n\nIhre {tafel}" if tafel else ""), [h.email.strip()],
                    art="kunde")  # fmt: skip
    except mail.MailFehler as fehler:
        return f"nicht gesendet: {fehler}"[:200]
    return f"gesendet am {timezone.localtime():%d.%m.%Y %H:%M}"


def _umziehen(h: Haushalt, gruppe: Kundengruppe, von: str) -> None:
    """Der Wechsel gilt sofort: neue Kundengruppe, Historie, Notiz für den neuen Ausweis."""
    vorher = historie.schnappschuss(h)
    h.kundengruppe = gruppe
    h.geaendert_am, h.geaendert_von = timezone.now(), von
    h.save(update_fields=["kundengruppe", "geaendert_am", "geaendert_von"])
    gruppen.pruefen(h, timezone.localdate())  # ohne gültigen Ausweis keine Kundengruppe
    historie.festhalten(
        h.kundennummer, vorher, historie.schnappschuss(h),
        quelle=HaushaltEreignis.Quelle.BEARBEITUNG, von=von, zusatz="Wechselwunsch genehmigt",
    )  # fmt: skip
    Notiz.objects.create(kundennummer=h.kundennummer, verfasst_von=von[:100],
                         text=f"Ausweis drucken (Wechsel zu {gruppe.name})"[:1000])  # fmt: skip


@transaction.atomic
def genehmigen(wunsch: Wechselwunsch, benutzer, gruppe: Kundengruppe, ab: dt.date | None = None,
               antwort: str = "") -> Wechselwunsch:  # fmt: skip
    """Verlegt den Kunden in ``gruppe`` – sofort oder, mit späterem ``ab``, als geplanten Wechsel
    zum Stichtag – und schreibt ihm."""
    if wunsch.status != Wechselwunsch.Status.OFFEN:
        raise WechselFehler("Dieser Wunsch ist schon entschieden.")
    h = Haushalt.objects.select_for_update().filter(kundennummer=wunsch.kundennummer).first()
    if h is None:
        raise WechselFehler("Diesen Kunden gibt es nicht mehr.")
    if not gruppe.aktiv:
        raise WechselFehler("Diese Kundengruppe gibt es nicht mehr.")
    heute = timezone.localdate()
    ab = ab or heute
    if ab < heute:
        raise WechselFehler("Der Wechsel kann nicht in der Vergangenheit liegen.")
    von = _name(benutzer)
    if ab > heute:
        verlegung.planen(h, gruppe, ab, von)
    else:
        verlegung.entfernen(h)  # ein älterer Plan wäre jetzt überholt
        _umziehen(h, gruppe, von)
    ziel = gruppe_text(gruppe)
    wann = "ab sofort" if ab <= heute else f"ab dem {ab:%d.%m.%Y}"
    antwort = " ".join(antwort.split())[:500]
    text = (f"Guten Tag,\n\nIhr Wunsch zu wechseln ist genehmigt. {wann.capitalize()} gilt für "
            f"Sie: {ziel}.\nBitte lassen Sie sich beim nächsten Besuch einen neuen Ausweis geben."
            + (f"\n\n{antwort}" if antwort else "") + "\n\nMit freundlichen Grüßen")  # fmt: skip
    wunsch.status, wunsch.neue_gruppe, wunsch.ab = Wechselwunsch.Status.GENEHMIGT, ziel[:150], ab
    wunsch.entschieden_am, wunsch.entschieden_von, wunsch.antwort = timezone.now(), von, antwort
    wunsch.mail_stand = _mailen(wunsch, h, "Ihr Wechselwunsch ist genehmigt", text)
    wunsch.save()
    Notiz.objects.create(
        kundennummer=h.kundennummer, benutzer=benutzer, verfasst_von=von[:100],
        text=f"Wechselwunsch genehmigt: {wann} {ziel}."[:1000],
    )  # fmt: skip
    return wunsch


@transaction.atomic
def ablehnen(wunsch: Wechselwunsch, benutzer, antwort: str = "") -> Wechselwunsch:
    if wunsch.status != Wechselwunsch.Status.OFFEN:
        raise WechselFehler("Dieser Wunsch ist schon entschieden.")
    h = Haushalt.objects.filter(kundennummer=wunsch.kundennummer).first()
    von = _name(benutzer)
    antwort = " ".join(antwort.split())[:500]
    text = ("Guten Tag,\n\nIhren Wunsch zu wechseln können wir im Moment leider nicht "
            "erfüllen. Es bleibt bei Ihrer bisherigen Ausgabezeit."
            + (f"\n\n{antwort}" if antwort else "") + "\n\nMit freundlichen Grüßen")  # fmt: skip
    wunsch.status = Wechselwunsch.Status.ABGELEHNT
    wunsch.entschieden_am, wunsch.entschieden_von, wunsch.antwort = timezone.now(), von, antwort
    wunsch.mail_stand = _mailen(wunsch, h, "Ihr Wechselwunsch", text)
    wunsch.save()
    if h is not None:
        Notiz.objects.create(
            kundennummer=h.kundennummer, benutzer=benutzer, verfasst_von=von[:100],
            text=("Wechselwunsch abgelehnt" + (f": {antwort}" if antwort else "."))[:1000],
        )  # fmt: skip
    return wunsch
