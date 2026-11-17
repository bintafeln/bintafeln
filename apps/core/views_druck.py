"""Druckansicht für PDFs (ADR 0141): PDF per E-Mail senden und die Ansicht je Gerät schalten."""

import base64
import binascii

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseBadRequest
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from apps.core import druckansicht, mail


def _zurueck(request, vorgabe="/"):
    ziel = request.POST.get("zurueck", "")
    if url_has_allowed_host_and_scheme(ziel, allowed_hosts={request.get_host()}):
        return ziel
    return vorgabe


def _pdf(request) -> bytes:
    """Das PDF aus der Anfrage: als Datei (PDF-Fenster in der App) oder Base64 (Druckansicht)."""
    if datei := request.FILES.get("datei"):
        return datei.read(MAX_GROESSE + 1)  # zu große erkennt die Prüfung an der Länge
    try:
        return base64.b64decode(request.POST.get("pdf", ""), validate=True)
    except (binascii.Error, ValueError):
        return b""


MAX_GROESSE = 20 * 1024 * 1024


@require_POST
@login_required
def vorschau(request):
    """Für das PDF-Fenster in der App: Seiten als Bilder, Knöpfe und Mail-Auswahl (HTML-Teil)."""
    inhalt = _pdf(request)
    if (not inhalt or len(inhalt) > MAX_GROESSE
            or not druckansicht.pruefen(inhalt, request.POST.get("signatur", ""))):  # fmt: skip
        return HttpResponseBadRequest("Das PDF ist nicht mehr gültig. Bitte noch einmal öffnen.")
    return render(request, "core/_pdf_fenster.html", {
        "seiten": druckansicht.seiten(inhalt) or [],
        "empfaenger": druckansicht.empfaenger(request), "mail_bereit": mail.eingerichtet(),
    })  # fmt: skip


@xframe_options_sameorigin  # das Ergebnis erscheint im kleinen Rahmen der Druckansicht
@require_POST
@login_required
def senden(request):
    """Das PDF der Druckansicht an eine der angebotenen Adressen schicken."""
    inhalt = _pdf(request)
    an = request.POST.get("an", "")
    erlaubt = dict(druckansicht.empfaenger(request))
    name = (request.POST.get("dateiname") or "dokument.pdf")[:100]
    if not name.lower().endswith(".pdf"):
        name += ".pdf"
    if not inhalt or not druckansicht.pruefen(inhalt, request.POST.get("signatur", "")):
        ergebnis, ok = "Das PDF ist nicht mehr gültig. Bitte noch einmal öffnen.", False
    elif an not in erlaubt:
        ergebnis, ok = "Bitte eine der angebotenen Adressen wählen.", False
    else:
        wer = request.user.get_full_name() or request.user.get_username()
        try:
            mail.senden(f"PDF aus bintafeln: {name}",
                        f"Im Anhang das PDF „{name}“, verschickt von {wer}.", [an],
                        anhaenge=[(name, inhalt, "application/pdf")], art="druck")  # fmt: skip
            ergebnis, ok = f"Das PDF wurde an {an} gesendet.", True
        except mail.MailFehler as fehler:
            ergebnis, ok = f"Nicht gesendet: {fehler}", False
    return render(request, "core/druckansicht_gesendet.html",
                  {"ergebnis": ergebnis, "ok": ok})  # fmt: skip


@require_POST
@login_required
def umschalten(request):
    """Druckansicht auf diesem Gerät ein- oder ausschalten (Cookie, gilt nur für diesen Browser)."""
    an = request.POST.get("an") == "1"
    antwort = redirect(_zurueck(request))
    druckansicht.cookie_setzen(request, antwort, an)
    messages.success(request, "PDFs öffnen auf diesem Gerät jetzt " +
                     ("im Fenster über der Seite." if an else "direkt."))  # fmt: skip
    return antwort
