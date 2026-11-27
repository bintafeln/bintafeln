"""Wechselwunsch eines Kunden: andere Uhrzeit, anderer Tag oder andere Ausgabestelle (ADR 0173).

Am Einlass oder im Büro wird der Wunsch Schritt für Schritt eingegrenzt (``moeglichkeiten()``
bietet nur Kundengruppen mit freiem Platz an) und als ``Wechselwunsch`` samt Notiz festgehalten.
Entschieden wird er von jemandem mit dem Recht ``kunden.wechsel_entscheiden``; der Kunde bekommt
die Antwort per E-Mail. Damit das geht, prüft ``erreichbar()`` vorher, ob am Haushalt E-Mail und
Telefon stehen; fehlendes wird beim Eintragen nachgetragen.
"""

import datetime as dt
import hashlib
import json
import secrets
from functools import cache
from pathlib import Path

from django.db import transaction
from django.utils import timezone
from django.utils.html import escape

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
    return [(a.value, a.label) for a in Wechselwunsch.Art if a != Wechselwunsch.Art.TAFEL]


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
               antwort: str = "", von: str = "") -> Wechselwunsch:  # fmt: skip
    """Verlegt den Kunden in ``gruppe`` – sofort oder, mit späterem ``ab``, als geplanten Wechsel
    zum Stichtag – und schreibt ihm. Ohne ``benutzer`` (der Kunde hat ein Angebot selbst
    bestätigt) steht ``von`` als Name da."""
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
    von = von or _name(benutzer)
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


# --- Platz per E-Mail anbieten, der Kunde bestätigt über einen Link (ADR 0175) -----------------

ANGEBOT_TAGE = 7


def _pruefsumme(schluessel: str) -> str:
    return hashlib.sha256(schluessel.encode()).hexdigest()


TEXTE = Path(__file__).resolve().parent / "wechsel_texte"


@cache
def texte(code: str) -> dict[str, str]:
    """Texte des Angebots in einer Sprache (``wechsel_texte/<code>.json``, Grundlage Deutsch)."""
    deutsch = json.loads((TEXTE / "de.json").read_text(encoding="utf-8"))
    datei = TEXTE / f"{code}.json"
    if code == "de" or not datei.is_file():
        return deutsch
    return {**deutsch, **json.loads(datei.read_text(encoding="utf-8"))}


def zweitsprache(h: Haushalt | None):
    """Sprache zur Staatsangehörigkeit der Hauptperson (wie bei den Mails der Anträge); ``None``,
    wenn das Deutsch ist oder nichts bekannt."""
    from types import SimpleNamespace

    from apps.antraege import sprachen

    hp = h.hauptperson if h else None
    if not hp or not hp.staatsangehoerigkeit:
        return None
    code = sprachen.mail_sprachen(
        SimpleNamespace(staatsangehoerigkeit=hp.staatsangehoerigkeit, sprache="")
    )[-1]
    return None if code == "de" else sprachen.sprache(code)


def _angebot_mail(tafel: str, ziel: str, ab: dt.date, bis: dt.date, zusatz: str,
                  link: str, zweite=None) -> tuple[str, str]:  # fmt: skip
    """Text- und HTML-Fassung der Mail mit dem Angebot: immer Deutsch, darunter – wenn bekannt –
    dasselbe in der Sprache des Kunden (``zweite``). Kundengruppe und Zusatz bleiben, wie sie
    sind."""
    knopf = ("display:inline-block;padding:12px 22px;margin:6px 8px 6px 0;border-radius:8px;"
             "font-weight:bold;text-decoration:none;")  # fmt: skip
    adresse = escape(link)
    teile_text, teile_html = [], []
    for sprache in [None, zweite] if zweite else [None]:
        t = texte(sprache.code if sprache else "de")
        kopf = f"{t['angebot']}: {ziel}. {t['ab'].format(ab=f'{ab:%d.%m.%Y}')}"
        bitte = t["bitte"].format(bis=f"{bis:%d.%m.%Y}")
        gruss = t["gruss_ende"] + (f"\n{tafel}" if tafel else "")
        teile_text.append("\n\n".join(x for x in (
            t["gruss"], kopf, bitte, f"{t['ja']}:\n{link}?antwort=ja",
            f"{t['nein']}:\n{link}?antwort=nein", zusatz if sprache is None else "", gruss,
        ) if x))  # fmt: skip
        richtung = ' dir="rtl"' if sprache and sprache.rtl else ""
        teile_html.append("".join([
            f'<div lang="{sprache.code if sprache else "de"}"{richtung}>',
            f"<p>{escape(t['gruss'])}</p><p>{escape(kopf)}</p><p>{escape(bitte)}</p><p>",
            f'<a href="{adresse}?antwort=ja" style="{knopf}background:#1a7f37;color:#ffffff">',
            f"{escape(t['ja'])}</a>",
            f'<a href="{adresse}?antwort=nein" style="{knopf}background:#eeeeee;color:#222222">',
            f"{escape(t['nein'])}</a></p>",
            f"<p>{escape(zusatz)}</p>" if zusatz and sprache is None else "",
            f"<p>{escape(t['gruss_ende'])}", f"<br>{escape(tafel)}" if tafel else "", "</p></div>",
        ]))  # fmt: skip
    return ("\n\n" + "–" * 20 + "\n\n").join(teile_text), "<hr>".join(teile_html)


def angebot_pruefen(h: Haushalt | None, gruppe: Kundengruppe, ab: dt.date | None,
                    wunsch: Wechselwunsch | None = None) -> dt.date:  # fmt: skip
    """Ob sich ``gruppe`` dem Kunden anbieten lässt; liefert das Datum des Wechsels. Angeboten
    wird nur ein freier Platz – für eine volle Gruppe bleibt das Vormerken (``vormerken()``)."""
    from apps.antraege.aufnahme import freie_gruppen

    if wunsch is not None:
        if wunsch.status != Wechselwunsch.Status.OFFEN:
            raise WechselFehler("Dieser Wunsch ist schon entschieden.")
        if wunsch.angebot_laeuft:
            raise WechselFehler("Zu diesem Wunsch läuft schon ein Angebot.")
    if h is None:
        raise WechselFehler("Diesen Kunden gibt es nicht mehr.")
    if not h.email.strip():
        raise WechselFehler("Bei diesem Kunden steht keine E-Mail-Adresse – ein Angebot per "
                            "E-Mail geht nicht. Bitte anrufen.")  # fmt: skip
    if not gruppe.aktiv:
        raise WechselFehler("Diese Kundengruppe gibt es nicht mehr.")
    if h.kundengruppe_id == gruppe.pk:
        raise WechselFehler("In dieser Kundengruppe ist der Kunde schon.")
    if all(e["gruppe"].pk != gruppe.pk for e in freie_gruppen(h)):
        raise WechselFehler(f"„{gruppe.name}“ ist voll – ein Platz lässt sich dort nicht "
                            "anbieten, nur vormerken.")  # fmt: skip
    heute = timezone.localdate()
    ab = ab or heute
    if ab < heute:
        raise WechselFehler("Der Wechsel kann nicht in der Vergangenheit liegen.")
    return ab


def angebot_vorschau(h: Haushalt, gruppe: Kundengruppe, ab: dt.date, zusatz: str,
                     link: str = "") -> dict:  # fmt: skip
    """Die Mail mit dem Angebot, wie der Kunde sie bekommt – zum Ansehen vor dem Senden (ohne
    ``link`` mit einem Platzhalter statt des echten Schlüssels) und zum Senden selbst."""
    from apps.core.models import TafelEinstellungen

    tafel = TafelEinstellungen.laden().name
    bis = timezone.localdate() + dt.timedelta(days=ANGEBOT_TAGE)
    zusatz = " ".join(zusatz.split())[:500]
    zweite = zweitsprache(h)
    text, html = _angebot_mail(tafel, gruppe_text(gruppe), ab, bis, zusatz,
                               link or "https://…/bestaetigen", zweite)  # fmt: skip
    betreff = "Wir können Ihnen einen Platz anbieten"
    return {"betreff": f"{betreff} – {tafel}" if tafel else betreff, "text": text, "html": html,
            "an": h.email.strip(), "bis": bis, "zusatz": zusatz, "sprache": zweite,
            "ziel": gruppe_text(gruppe)}  # fmt: skip


@transaction.atomic
def anbieten(wunsch: Wechselwunsch, benutzer, gruppe: Kundengruppe, ab: dt.date | None,
             zusatz: str, link_bauen) -> Wechselwunsch:  # fmt: skip
    """Bietet dem Kunden per E-Mail einen Platz in ``gruppe`` an. ``link_bauen(schluessel)``
    liefert die vollständige Adresse der Bestätigungsseite. Der Platz ist reserviert, solange
    das Angebot läuft (``gruppen.reservierte_zugaenge``). Geht die Mail nicht hinaus, bleibt
    alles, wie es war."""
    h = Haushalt.objects.filter(kundennummer=wunsch.kundennummer).first()
    ab = angebot_pruefen(h, gruppe, ab, wunsch)
    schluessel = secrets.token_urlsafe(32)
    post = angebot_vorschau(h, gruppe, ab, zusatz, link_bauen(schluessel))
    von, ziel, bis, zusatz = _name(benutzer), post["ziel"], post["bis"], post["zusatz"]
    try:
        # vertraulich: Der Link in der Mail ist der Schlüssel, er gehört nicht ins Mail-Archiv
        mail.senden(post["betreff"], post["text"], [post["an"]], html=post["html"], art="kunde",
                    vertraulich=True)  # fmt: skip
    except mail.MailFehler as fehler:
        raise WechselFehler(f"Die E-Mail ging nicht hinaus: {fehler}") from None
    wunsch.angebot_gruppe, wunsch.angebot_text, wunsch.angebot_ab = gruppe, ziel[:150], ab
    wunsch.angebot_am, wunsch.angebot_von, wunsch.angebot_bis = timezone.now(), von, bis
    wunsch.angebot_zusatz, wunsch.angebot_schluessel = zusatz, _pruefsumme(schluessel)
    wunsch.angebot_antwort, wunsch.angebot_antwort_am = "", None
    wunsch.save()
    Notiz.objects.create(
        kundennummer=h.kundennummer, benutzer=benutzer, verfasst_von=von[:100],
        text=(f"Platz angeboten: {ziel}, ab {ab:%d.%m.%Y}. Der Kunde soll bis "
              f"{bis:%d.%m.%Y} per E-Mail bestätigen.")[:1000],
    )  # fmt: skip
    return wunsch


def angebot_finden(schluessel: str) -> Wechselwunsch | None:
    """Der Wunsch zu einem Schlüssel aus dem Link – auch wenn das Angebot schon beantwortet oder
    abgelaufen ist (die Seite sagt das dann)."""
    if not schluessel or len(schluessel) > 100:
        return None
    return (
        Wechselwunsch.objects.filter(angebot_schluessel=_pruefsumme(schluessel))
        .select_related("angebot_gruppe__ausgabestelle")
        .first()
    )


@transaction.atomic
def angebot_beantworten(wunsch: Wechselwunsch, ja: bool) -> Wechselwunsch:
    """Der Kunde hat über den Link geantwortet. „Ja“ führt den Wechsel aus (wie genehmigt, zum
    angebotenen Datum); „Nein“ lässt den Wunsch offen, die Verwaltung sieht die Antwort."""
    wunsch = Wechselwunsch.objects.select_for_update().get(pk=wunsch.pk)
    if not wunsch.angebot_laeuft:
        raise WechselFehler("Dieses Angebot gilt nicht mehr.")
    wunsch.angebot_antwort, wunsch.angebot_antwort_am = ("ja" if ja else "nein"), timezone.now()
    wunsch.save(update_fields=["angebot_antwort", "angebot_antwort_am"])
    if not ja:
        Notiz.objects.create(
            kundennummer=wunsch.kundennummer, verfasst_von="Kunde (per E-Mail)",
            text=f"Angebotenen Platz abgelehnt: {wunsch.angebot_text}."[:1000],
        )  # fmt: skip
        return wunsch
    gruppe = wunsch.angebot_gruppe
    if gruppe is None:
        raise WechselFehler("Die angebotene Kundengruppe gibt es nicht mehr.")
    ab = max(wunsch.angebot_ab or timezone.localdate(), timezone.localdate())
    return genehmigen(wunsch, None, gruppe, ab, wunsch.angebot_zusatz,
                      von=f"{wunsch.angebot_von} (vom Kunden bestätigt)"[:150])  # fmt: skip


ANGEBOT_ZEIGEN_TAGE = 14  # so lange steht ein beantwortetes/abgelaufenes Angebot am Kunden


def angebot_am_kunden(kundennummer: str, heute: dt.date | None = None) -> Wechselwunsch | None:
    """Das jüngste Angebot eines Platzes für die Kundenseite („Angaben“): solange es läuft, und
    noch 14 Tage nach der Antwort bzw. dem Ablauf der Frist."""
    heute = heute or timezone.localdate()
    w = (
        Wechselwunsch.objects.filter(kundennummer=kundennummer, angebot_am__isnull=False)
        .select_related("angebot_gruppe__ausgabestelle")
        .order_by("-angebot_am")
        .first()
    )
    if w is None or w.angebot_laeuft:
        return w
    zuletzt = (timezone.localtime(w.angebot_antwort_am).date() if w.angebot_antwort_am
               else w.angebot_bis)  # fmt: skip
    grenze = heute - dt.timedelta(days=ANGEBOT_ZEIGEN_TAGE)
    return w if zuletzt and zuletzt >= grenze else None


@transaction.atomic
def angebot_zusage_eintragen(wunsch: Wechselwunsch, benutzer) -> Wechselwunsch:
    """Der Kunde hat auf anderem Weg zugesagt (Antwort-Mail, Telefon, am Einlass) statt über den
    Link: Die Verwaltung trägt die Zusage ein. Wirkt wie die Bestätigung über den Link – der
    Kunde zieht zum angebotenen Datum um und bekommt die Bestätigung."""
    wunsch = Wechselwunsch.objects.select_for_update().get(pk=wunsch.pk)
    if not wunsch.angebot_laeuft:
        raise WechselFehler("Dieses Angebot gilt nicht mehr.")
    gruppe = wunsch.angebot_gruppe
    if gruppe is None:
        raise WechselFehler("Die angebotene Kundengruppe gibt es nicht mehr.")
    wunsch.angebot_antwort, wunsch.angebot_antwort_am = "ja", timezone.now()
    wunsch.save(update_fields=["angebot_antwort", "angebot_antwort_am"])
    ab = max(wunsch.angebot_ab or timezone.localdate(), timezone.localdate())
    return genehmigen(wunsch, None, gruppe, ab, wunsch.angebot_zusatz,
                      von=f"{_name(benutzer)} (Zusage des Kunden eingetragen)"[:150])  # fmt: skip


# --- Von der Tafel aus: Platz anbieten oder vormerken, ohne dass der Kunde gefragt hat ---------


def _eigener_wunsch(h: Haushalt, benutzer, text: str, gruppe: Kundengruppe,
                    anmerkung: str = "") -> Wechselwunsch:  # fmt: skip
    if offene().filter(kundennummer=h.kundennummer).exists():
        raise WechselFehler("Zu diesem Kunden ist schon ein Wechselwunsch offen – bitte dort "
                            "entscheiden (Kunden → Wechselwünsche).")  # fmt: skip
    return Wechselwunsch.objects.create(
        kundennummer=h.kundennummer, art=Wechselwunsch.Art.TAFEL,
        bisher=gruppe_text(h.kundengruppe)[:150], wunsch=text[:300], wunsch_gruppe=gruppe,
        anmerkung=" ".join(anmerkung.split())[:300], ohne_email=not h.email.strip(),
        von=_name(benutzer),
    )  # fmt: skip


@transaction.atomic
def von_uns_anbieten(h: Haushalt, benutzer, gruppe: Kundengruppe, ab: dt.date | None,
                     zusatz: str, link_bauen) -> Wechselwunsch:  # fmt: skip
    """Die Tafel bietet von sich aus einen freien Platz an: legt den Vorgang an und schickt die
    Mail. Scheitert etwas, bleibt nichts zurück."""
    angebot_pruefen(h, gruppe, ab)
    wunsch = _eigener_wunsch(h, benutzer, f"Angebot der Tafel: {gruppe_text(gruppe)}", gruppe)
    return anbieten(wunsch, benutzer, gruppe, ab, zusatz, link_bauen)


@transaction.atomic
def vormerken(h: Haushalt, benutzer, gruppe: Kundengruppe, anmerkung: str = "") -> Wechselwunsch:
    """Die Tafel merkt den Kunden für eine (volle) Kundengruppe vor: Der Vorgang steht bei den
    Wechselwünschen und lässt sich anbieten oder genehmigen, sobald dort Platz ist. Der Kunde
    erfährt davon nichts."""
    if not gruppe.aktiv:
        raise WechselFehler("Diese Kundengruppe gibt es nicht mehr.")
    if h.kundengruppe_id == gruppe.pk:
        raise WechselFehler("In dieser Kundengruppe ist der Kunde schon.")
    wunsch = _eigener_wunsch(h, benutzer, f"Von der Tafel vorgemerkt: {gruppe_text(gruppe)}",
                             gruppe, anmerkung)  # fmt: skip
    Notiz.objects.create(
        kundennummer=h.kundennummer, benutzer=benutzer, verfasst_von=_name(benutzer)[:100],
        text=f"Vorgemerkt für {gruppe_text(gruppe)}."[:1000],
    )  # fmt: skip
    return wunsch


def gruppen_zur_wahl(h: Haushalt) -> list[dict]:
    """Alle Kundengruppen außer der eigenen und internen, mit freien Plätzen: Wo Platz ist, lässt
    er sich anbieten, sonst nur vormerken."""
    return [
        {"gruppe": e["gruppe"], "text": gruppe_text(e["gruppe"]), "frei": e["frei"],
         "voll": e["frei"] is not None and e["frei"] <= 0}
        for e in gruppen.mit_plaetzen(h)
        if not e["eigene"] and not e["gruppe"].intern
    ]  # fmt: skip
