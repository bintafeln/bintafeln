"""Öffentliches Antragsformular, ohne Anmeldung, in 29 Sprachen (ADR 0024)."""

import datetime as dt
import hashlib
import logging

from django.conf import settings
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone

from apps.antraege import sprachen
from apps.antraege.forms import AntragForm
from apps.antraege.models import AntragEinstellungen, AntragText, AntragVersuch
from apps.core import mail
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
    eigene = AntragText.objects.filter(sprache=s.code).first()
    return {
        "s": s,
        "t": texte,
        "sprachen": sprachen.SPRACHEN,
        "einleitung": (eigene and eigene.einleitung) or texte["einleitung"],
        "bestaetigung": (eigene and eigene.bestaetigung) or texte["bestaetigung"],
        "e": AntragEinstellungen.laden(),
        "tafel": TafelEinstellungen.laden(),
    }


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
            request.session["antrag_mail"] = _bestaetigen(antrag, kontext)
            _benachrichtigen(request, antrag, e)
            return redirect("antrag:danke", sprache=sprache)
        else:
            kontext["fehler"] = t["fehler_formular"]
    return render(request, "antraege/formular.html", {**kontext, "form": form})


def danke(request, sprache):
    kontext = _kontext(sprache)
    kontext["nummer"] = request.session.pop("antrag_nummer", None)
    kontext["mail_an"] = request.session.pop("antrag_mail", "")
    if kontext["nummer"] is None:  # direkt aufgerufen
        return redirect("antrag:formular", sprache=kontext["s"].code)
    t = kontext["t"]
    kontext["danke_text"] = t["danke_nummer"].format(nummer=kontext["nummer"])
    kontext["mail_text"] = t["mail_gesendet"].format(email=kontext["mail_an"])
    return render(request, "antraege/danke.html", kontext)


def _bestaetigen(antrag, kontext) -> str:
    """Bestätigung in der Sprache des Antrags; liefert die Adresse, wenn sie verschickt wurde."""
    if not antrag.email or not mail.eingerichtet():
        return ""
    t, tafel = kontext["t"], kontext["tafel"].name or "Tafel"
    text = "\n\n".join(
        [
            t["mail_anrede"],
            t["danke_nummer"].format(nummer=antrag.nummer),
            kontext["bestaetigung"],
            f"{t['mail_gruss']}\n{tafel}",
        ]
    )
    try:
        mail.senden(t["mail_betreff"].format(tafel=tafel), text, [antrag.email])
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
