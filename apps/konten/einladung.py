"""Einmalige Links zum Festlegen des eigenen Passworts, per Mail (ADR 0016).

Der Link enthält ein Token von Djangos Passwort-Zurücksetzen. Es gilt PASSWORD_RESET_TIMEOUT
(3 Tage) und wird ungültig, sobald das Passwort gesetzt oder sich angemeldet wurde.
"""

from django.contrib.auth.tokens import default_token_generator
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

from apps.core import mail
from apps.core.models import TafelEinstellungen

EINLADUNG = "einladung"
ZURUECKSETZEN = "zuruecksetzen"

BETREFF = {
    EINLADUNG: "Ihr Zugang zu {tafel}",
    ZURUECKSETZEN: "Neues Passwort für {tafel}",
}


def link(request, benutzer) -> str:
    pfad = reverse(
        "konten:passwort_setzen",
        kwargs={
            "uidb64": urlsafe_base64_encode(force_bytes(benutzer.pk)),
            "token": default_token_generator.make_token(benutzer),
        },
    )
    return request.build_absolute_uri(pfad)


def senden(request, benutzer, art: str) -> None:
    """Sendet den Link an die hinterlegte Adresse. Löst mail.MailFehler aus."""
    if not benutzer.email:
        raise mail.MailFehler("Für dieses Konto ist keine E-Mail-Adresse hinterlegt.")
    tafel = TafelEinstellungen.laden().name or "bintafeln"
    text = render_to_string(
        f"mail/{art}.txt", {"benutzer": benutzer, "link": link(request, benutzer), "tafel": tafel}
    )
    mail.senden(BETREFF[art].format(tafel=tafel), text, [benutzer.email])
