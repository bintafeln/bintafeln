"""Öffentliches Antragsformular, ohne Anmeldung, in 29 Sprachen (ADR 0024)."""

import datetime as dt
import hashlib
import logging

from django.conf import settings
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from apps.antraege import sprachen
from apps.antraege.forms import MAX_ANHAENGE, AntragForm
from apps.antraege.models import AntragEinstellungen, AntragText, AntragVersuch
from apps.core import html, mail
from apps.core.models import TafelEinstellungen

logger = logging.getLogger(__name__)

MAX_JE_STUNDE = 5


def besucher_ip(request) -> str:
    """Adresse der Besucher. Hinter Caddy steht sie als erster Eintrag in X-Forwarded-For."""
    weitergeleitet = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return weitergeleitet.split(",")[0].strip() or request.META.get("REMOTE_ADDR", "")


def _schluessel(request) -> str:
    """Nur eine Prüfsumme der Adresse wird gespeichert, nie die Adresse selbst."""
    roh = f"{settings.SECRET_KEY}|{besucher_ip(request)}".encode()
    return hashlib.sha256(roh).hexdigest()


def zu_viele(request) -> bool:
    grenze = timezone.now() - dt.timedelta(hours=1)
    AntragVersuch.objects.create(schluessel=_schluessel(request))
    anzahl = AntragVersuch.objects.filter(schluessel=_schluessel(request), zeitpunkt__gte=grenze)
    return anzahl.count() > MAX_JE_STUNDE


def _kontext(code):
    s = sprachen.sprache(code)
    texte = sprachen.texte(s.code)
    tafel = TafelEinstellungen.laden()
    e = AntragEinstellungen.laden()
    eigene = AntragText.objects.filter(sprache=s.code).first() or AntragText(sprache=s.code)
    tafel_name = tafel.name or "Tafel"
    return {
        "s": s,
        "t": texte,
        "sprachen": sprachen.SPRACHEN,
        "eigene": eigene,
        "e": e,
        "tafel": tafel,
        "tafel_name": tafel_name,
        "eigenes_css": html.css_bereinigen(e.eigenes_css),
        "kopf": eigener_bereich(eigene, "kopf", tafel=tafel_name),
        "fuss": eigener_bereich(eigene, "fuss", tafel=tafel_name),
    }


def _ueberschrift(kontext) -> str:
    return kontext["eigene"].ueberschrift or kontext["t"]["titel"]


def start(request):
    """Ohne Sprache in der Adresse: die des Browsers, sonst Deutsch."""
    wahl = request.GET.get("sprache") or sprachen.aus_browser(
        request.META.get("HTTP_ACCEPT_LANGUAGE", "")
    )
    return redirect("antrag:formular", sprache=sprachen.sprache(wahl).code)


def formular(request, sprache):
    if sprache not in sprachen.NACH_CODE:
        return redirect("antrag:start")
    kontext = _kontext(sprache)
    e, t = kontext["e"], kontext["t"]
    kontext["ueberschrift"] = _ueberschrift(kontext)
    kontext["einleitung"] = html.anzeigen(
        kontext["eigene"].einleitung, t["einleitung"], tafel=kontext["tafel_name"]
    )
    kontext["anhaenge_hinweis"] = anhaenge_hinweis(kontext["eigene"])
    if not e.aktiv:
        return render(request, "antraege/geschlossen.html", kontext)
    form = AntragForm(request.POST or None, request.FILES or None, texte=t, einstellungen=e)
    if request.method == "POST":
        if form.ist_bot:  # so tun, als sei alles gut
            request.session["antrag_nummer"] = ""
            return redirect("antrag:danke", sprache=sprache)
        if zu_viele(request):
            kontext["fehler"] = t["fehler_zu_viele"]
        elif form.is_valid():
            antrag = form.speichern(sprache)
            request.session["antrag_nummer"] = antrag.nummer
            request.session["antrag_mail"] = _bestaetigen(request, antrag, kontext)
            _benachrichtigen(request, antrag, e)
            return redirect("antrag:danke", sprache=sprache)
        else:
            kontext["fehler"] = t["fehler_formular"]
    return render(request, "antraege/formular.html",
                  {**kontext, "form": form, "max_anhaenge": MAX_ANHAENGE})  # fmt: skip


def eigener_bereich(eigene: AntragText, feld: str, **werte) -> str:
    """Eigener Text ohne mitgelieferte Fassung (Hinweis zu den Nachweisen, Kopf- und Fußbereich);
    fehlt er in der Sprache, gilt der deutsche (oder keiner)."""
    text = getattr(eigene, feld)
    if not text.strip() and eigene.sprache != "de":
        deutsch = AntragText.objects.filter(sprache="de").first()
        text = getattr(deutsch, feld) if deutsch else ""
    return html.anzeigen(text, "", **werte) if text.strip() else ""


def anhaenge_hinweis(eigene: AntragText) -> str:
    return eigener_bereich(eigene, "anhaenge_hinweis")


def _bestaetigung(kontext, nummer: str) -> str:
    """Text der Seite nach dem Absenden (eigen oder mitgeliefert), Platzhalter eingesetzt."""
    return html.anzeigen(
        kontext["eigene"].bestaetigung,
        kontext["t"]["bestaetigung"],
        nummer=nummer,
        tafel=kontext["tafel_name"],
    )


def danke(request, sprache):
    kontext = _kontext(sprache)
    kontext["nummer"] = request.session.pop("antrag_nummer", None)
    kontext["mail_an"] = request.session.pop("antrag_mail", "")
    if kontext["nummer"] is None:  # direkt aufgerufen
        return redirect("antrag:formular", sprache=kontext["s"].code)
    t = kontext["t"]
    kontext["ueberschrift"] = _ueberschrift(kontext)
    kontext["bestaetigung"] = _bestaetigung(kontext, kontext["nummer"])
    kontext["danke_text"] = t["danke_nummer"].format(nummer=kontext["nummer"])
    kontext["mail_text"] = t["mail_gesendet"].format(email=kontext["mail_an"])
    return render(request, "antraege/danke.html", kontext)


def antwortmail(request, antrag, kontext) -> tuple[str, str, str]:
    """Betreff, Klartext und HTML der Bestätigung (eigene Fassung oder mitgelieferte)."""
    t, eigene, tafel = kontext["t"], kontext["eigene"], kontext["tafel_name"]
    werte = {"nummer": antrag.nummer, "vorname": antrag.vorname, "nachname": antrag.nachname,
             "tafel": tafel}  # fmt: skip
    betreff = html.einsetzen(eigene.mail_betreff or t["mail_betreff"], tafel=tafel,
                             nummer=antrag.nummer)  # fmt: skip
    if eigene.mail_text.strip():
        inhalt = html.anzeigen(eigene.mail_text, "", **werte)
    else:
        inhalt = format_html(
            "<p>{}</p><p><strong>{}</strong></p>{}<p>{}<br>{}</p>",
            t["mail_anrede"],
            t["danke_nummer"].format(nummer=antrag.nummer),
            _bestaetigung(kontext, antrag.nummer),
            t["mail_gruss"],
            tafel,
        )
    logo = kontext["tafel"].logo
    gestaltet = render_to_string(
        "antraege/mail.html",
        {**kontext, "inhalt": inhalt, "betreff": betreff,
         "logo_url": request.build_absolute_uri(logo.url) if logo else ""},
    )  # fmt: skip
    return betreff, html.als_text(inhalt), gestaltet


def _bestaetigen(request, antrag, kontext) -> str:
    """Bestätigung in der Sprache des Antrags; liefert die Adresse, wenn sie verschickt wurde."""
    if not antrag.email or not mail.eingerichtet():
        return ""
    betreff, text, gestaltet = antwortmail(request, antrag, kontext)
    try:
        mail.senden(betreff, text, [antrag.email], html=gestaltet)
    except mail.MailFehler as fehler:
        logger.warning("Bestätigung für Antrag %s nicht gesendet: %s", antrag.nummer, fehler)
        return ""
    return antrag.email


def _benachrichtigen(request, antrag, e) -> None:
    """Mail an ausgewählte Mitarbeitende, ohne persönliche Angaben."""
    an = [b.email for b in e.benachrichtigen.filter(is_active=True) if b.email]
    if not an or not mail.eingerichtet():
        return
    link = request.build_absolute_uri(reverse("antraege:antrag", args=[antrag.pk]))
    try:
        mail.senden(
            f"Neuer Antrag {antrag.nummer}",
            f"Es ist ein neuer Antrag eingegangen ({antrag.get_art_display()}).\n\n{link}",
            an,
        )
    except mail.MailFehler as fehler:
        logger.warning("Benachrichtigung zu Antrag %s nicht gesendet: %s", antrag.nummer, fehler)
