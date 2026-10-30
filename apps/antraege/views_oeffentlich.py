"""Öffentliches Antragsformular, ohne Anmeldung, in 29 Sprachen (ADR 0024)."""

import datetime as dt
import hashlib
import logging

from django.conf import settings
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

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
        "sprach_hinweise": sprachen.hinweise(),
        "land_sprache": sprachen.LAND_SPRACHE,
        "kopf": eigener_bereich(eigene, "kopf", tafel=tafel_name),
        "fuss": eigener_bereich(eigene, "fuss", tafel=tafel_name),
        "rechtslinks": e.rechtslinks(s.code),
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
            request.session["antrag_mail"] = _bestaetigen(request, antrag)
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
    # Die Antragsnummer erscheint bewusst nicht, auch nicht als {nummer} im eigenen Text
    kontext["bestaetigung"] = _bestaetigung(kontext, "")
    kontext["danke_text"] = t["danke_eingang"]
    kontext["mail_text"] = t["mail_gesendet"].format(email=kontext["mail_an"])
    return render(request, "antraege/danke.html", kontext)


def _mail_teil(antrag, kontext) -> tuple[str, str]:
    """Betreff und HTML-Inhalt der Bestätigung in einer Sprache."""
    t, eigene, tafel = kontext["t"], kontext["eigene"], kontext["tafel_name"]
    werte = {"nummer": "", "vorname": antrag.vorname, "nachname": antrag.nachname,
             "tafel": tafel}  # fmt: skip
    betreff = html.einsetzen(eigene.mail_betreff or t["mail_betreff"], tafel=tafel, nummer="")
    if eigene.mail_text.strip():
        return betreff, html.anzeigen(eigene.mail_text, "", **werte)
    return betreff, format_html(
        "<p>{}</p><p><strong>{}</strong></p>{}<p>{}<br>{}</p>",
        t["mail_anrede"],
        t["danke_eingang"],
        _bestaetigung(kontext, ""),
        t["mail_gruss"],
        tafel,
    )


def antwortmail(request, antrag, eigene: AntragText | None = None) -> tuple[str, str, str]:
    """Betreff, Klartext und HTML der Bestätigung: Deutsch und darunter die Sprache zur
    Staatsangehörigkeit (eigene Fassung oder mitgelieferte). Die Antragsnummer steht bewusst
    nicht in der Mail ({nummer} bleibt leer): Antragsteller sollen sie nicht als Platz in einer
    Reihenfolge verstehen. ``eigene``: noch nicht gespeicherte Texte (Vorschau)."""
    teile = []
    for code in sprachen.mail_sprachen(antrag):
        k = _kontext(code)
        if eigene is not None and eigene.sprache == code:
            k["eigene"] = eigene
        betreff, inhalt = _mail_teil(antrag, k)
        teile.append((k["s"], betreff, inhalt))
    betreff = " / ".join(dict.fromkeys(b for _, b, _ in teile))
    abschnitte = ((s.code, "rtl" if s.rtl else "ltr", i) for s, _, i in teile)
    inhalt = format_html_join(
        format_html("<{}>", "hr"), '<div lang="{}" dir="{}">{}</div>', abschnitte
    )
    kontext = _kontext("de")
    logo = kontext["tafel"].logo
    gestaltet = render_to_string(
        "antraege/mail.html",
        {**kontext, "inhalt": inhalt, "betreff": betreff,
         "logo_url": request.build_absolute_uri(logo.url) if logo else ""},
    )  # fmt: skip
    text = "\n\n----------\n\n".join(html.als_text(i) for _, _, i in teile)
    return betreff, text, gestaltet


def _bestaetigen(request, antrag) -> str:
    """Bestätigung (siehe ``antwortmail``); liefert die Adresse, wenn sie verschickt wurde."""
    if not antrag.email or not mail.eingerichtet():
        return ""
    betreff, text, gestaltet = antwortmail(request, antrag)
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
    from apps.core import benachrichtigung

    link = request.build_absolute_uri(reverse("antraege:antrag", args=[antrag.pk]))
    benachrichtigung.melden(
        "antrag_neu", an, f"Neuer Antrag {antrag.nummer}",
        f"Es ist ein neuer Antrag eingegangen ({antrag.get_art_display()}).\n\n{link}",
        schluessel=antrag.pk,
    )  # fmt: skip


def rechtstext(request, sprache, art):
    """Öffentliche Seite mit dem hinterlegten Datenschutz-, Impressum- oder Einverständnistext
    (ADR 0094). 404, wenn die Sprache unbekannt ist oder kein Text hinterlegt wurde."""
    from django.http import Http404

    if sprache not in sprachen.NACH_CODE or art not in AntragEinstellungen.RECHTSTEXTE:
        raise Http404
    kontext = _kontext(sprache)
    roh = getattr(kontext["e"], f"{art}_text", "")
    if not (roh or "").strip():
        raise Http404
    kontext["ueberschrift"] = kontext["t"][art]
    kontext["rechtstext"] = html.bereinigen(roh)
    return render(request, "antraege/rechtstext.html", kontext)
