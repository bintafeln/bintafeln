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
FREIGABE = "freigabe"

BETREFF = {
    EINLADUNG: "Ihr Zugang zu {tafel}",
    ZURUECKSETZEN: "Neues Passwort für {tafel}",
    FREIGABE: "Ihr Zugang zu {tafel} ist freigeschaltet",
}

# Wie das vorläufige Passwort beim Freigeben (ADR 0114) in der Mail beschrieben wird – nur das
# Format, nicht der konkrete Wert (die Person kennt ihn selbst).
FREIGABE_PASSWORT = {
    "geburtsdatum": "Ihr Geburtsdatum mit Punkten, zum Beispiel 15.03.1980",
    "adresse": "Ihre Straße und Hausnummer, genau wie bei der Tafel hinterlegt "
    "(zum Beispiel: Musterstraße 12)",
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


def freigabe_senden(request, benutzer, basis: str) -> None:
    """Teilt per Mail mit, dass der Zugang freigeschaltet ist, und wie man sich anmeldet (ADR 0114).
    Das vorläufige Passwort wird nur als Format beschrieben, nicht genannt. Löst mail.MailFehler
    aus, wenn keine Adresse hinterlegt ist."""
    if not benutzer.email:
        raise mail.MailFehler("Für dieses Konto ist keine E-Mail-Adresse hinterlegt.")
    tafel = TafelEinstellungen.laden().name or "bintafeln"
    text = render_to_string(
        "mail/freigabe.txt",
        {
            "benutzer": benutzer,
            "tafel": tafel,
            "anmelden": request.build_absolute_uri(reverse("konten:anmelden")),
            "passwort_hinweis": FREIGABE_PASSWORT.get(basis, FREIGABE_PASSWORT["geburtsdatum"]),
        },
    )
    mail.senden(BETREFF[FREIGABE].format(tafel=tafel), text, [benutzer.email])
