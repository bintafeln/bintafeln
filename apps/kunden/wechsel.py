"""Wechselwunsch eines Kunden: andere Uhrzeit, anderer Tag oder andere Ausgabestelle (ADR 0173).

Am Einlass oder im Büro wird der Wunsch Schritt für Schritt eingegrenzt (``moeglichkeiten()``
bietet nur Kundengruppen mit freiem Platz an) und als ``Wechselwunsch`` samt Notiz festgehalten.
Entschieden wird er von jemandem mit dem Recht ``kunden.wechsel_entscheiden``; der Kunde bekommt
die Antwort per E-Mail. Damit das geht, prüft ``erreichbar()`` vorher, ob am Haushalt E-Mail und
Telefon stehen; fehlendes wird beim Eintragen nachgetragen.
"""

import datetime as dt
import hashlib
import secrets

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


def _angebot_mail(tafel: str, ziel: str, ab: dt.date, bis: dt.date, zusatz: str,
                  link: str) -> tuple[str, str]:  # fmt: skip
    """Text- und HTML-Fassung der Mail mit dem Angebot."""
    kopf = f"wir können Ihnen einen Platz anbieten: {ziel}, ab dem {ab:%d.%m.%Y}."
    bitte = (f"Bitte bestätigen Sie bis zum {bis:%d.%m.%Y}, dass Sie wechseln möchten. Erst mit "
             "Ihrer Bestätigung gilt der Wechsel; bis dahin bleibt alles, wie es ist.")  # fmt: skip
    gruss = "Mit freundlichen Grüßen" + (f"\nIhre {tafel}" if tafel else "")
    text = "\n\n".join(x for x in (
        "Guten Tag,", kopf, bitte, f"Ja, ich möchte wechseln:\n{link}?antwort=ja",
        f"Nein, ich bleibe:\n{link}?antwort=nein", zusatz, gruss) if x)  # fmt: skip
    knopf = ("display:inline-block;padding:12px 22px;margin:6px 8px 6px 0;border-radius:8px;"
             "font-weight:bold;text-decoration:none;")  # fmt: skip
    adresse = escape(link)
    html = "".join([
        f"<p>Guten Tag,</p><p>{escape(kopf)}</p><p>{escape(bitte)}</p><p>",
        f'<a href="{adresse}?antwort=ja" style="{knopf}background:#1a7f37;color:#ffffff">',
        "Ja, ich möchte wechseln</a>",
        f'<a href="{adresse}?antwort=nein" style="{knopf}background:#eeeeee;color:#222222">',
        "Nein, ich bleibe</a></p>",
        f"<p>{escape(zusatz)}</p>" if zusatz else "",
        "<p>Mit freundlichen Grüßen", f"<br>Ihre {escape(tafel)}" if tafel else "", "</p>",
    ])  # fmt: skip
    return text, html


@transaction.atomic
def anbieten(wunsch: Wechselwunsch, benutzer, gruppe: Kundengruppe, ab: dt.date | None,
             zusatz: str, link_bauen) -> Wechselwunsch:  # fmt: skip
    """Bietet dem Kunden per E-Mail einen Platz in ``gruppe`` an. ``link_bauen(schluessel)``
    liefert die vollständige Adresse der Bestätigungsseite. Der Platz ist reserviert, solange
    das Angebot läuft (``gruppen.reservierte_zugaenge``). Geht die Mail nicht hinaus, bleibt
    alles, wie es war."""
    from apps.core.models import TafelEinstellungen

    if wunsch.status != Wechselwunsch.Status.OFFEN:
        raise WechselFehler("Dieser Wunsch ist schon entschieden.")
    if wunsch.angebot_laeuft:
        raise WechselFehler("Zu diesem Wunsch läuft schon ein Angebot.")
    h = Haushalt.objects.filter(kundennummer=wunsch.kundennummer).first()
    if h is None:
        raise WechselFehler("Diesen Kunden gibt es nicht mehr.")
    if not h.email.strip():
        raise WechselFehler("Bei diesem Kunden steht keine E-Mail-Adresse – ein Angebot per "
                            "E-Mail geht nicht. Bitte anrufen.")  # fmt: skip
    if not gruppe.aktiv:
        raise WechselFehler("Diese Kundengruppe gibt es nicht mehr.")
    heute = timezone.localdate()
    ab = ab or heute
    if ab < heute:
        raise WechselFehler("Der Wechsel kann nicht in der Vergangenheit liegen.")
    schluessel = secrets.token_urlsafe(32)
    von, ziel = _name(benutzer), gruppe_text(gruppe)
    bis = heute + dt.timedelta(days=ANGEBOT_TAGE)
    zusatz = " ".join(zusatz.split())[:500]
    tafel = TafelEinstellungen.laden().name
    text, html = _angebot_mail(tafel, ziel, ab, bis, zusatz, link_bauen(schluessel))
    betreff = "Wir können Ihnen einen Platz anbieten"
    try:
        # vertraulich: Der Link in der Mail ist der Schlüssel, er gehört nicht ins Mail-Archiv
        mail.senden(f"{betreff} – {tafel}" if tafel else betreff, text, [h.email.strip()],
                    html=html, art="kunde", vertraulich=True)  # fmt: skip
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
