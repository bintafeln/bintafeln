from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse
from django_otp import user_has_device

from apps.konten import zwei_faktor

FREIE_PFADE = ("/static/", "/media/", "/healthz/", "/app/")


class PasswortAendernMiddleware:
    """Nach einem Startpasswort muss zuerst ein eigenes Passwort gewählt werden."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        benutzer = request.user
        if (
            benutzer.is_authenticated
            and benutzer.passwort_aendern
            and not request.path.startswith(FREIE_PFADE)
            and request.path not in (reverse("konten:passwort_aendern"), reverse("konten:abmelden"))
        ):
            return redirect("konten:passwort_aendern")
        return self.get_response(request)


class ZweiFaktorMiddleware:
    """Setzt die Zwei-Faktor-Anmeldung durch.

    - Wer ein Gerät hat, aber in dieser Sitzung keinen Code eingegeben hat (z. B. weil das
      Gerät in einer anderen Sitzung eingerichtet wurde), wird abgemeldet.
    - Wer eine Rolle mit Zwei-Faktor-Pflicht hat und noch kein Gerät, muss es zuerst einrichten.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        benutzer = request.user
        if (
            benutzer.is_authenticated
            and not benutzer.is_verified()
            and not request.path.startswith(FREIE_PFADE)
        ):
            if user_has_device(benutzer):
                logout(request)
                messages.info(request, "Bitte melden Sie sich erneut mit Ihrem Code an.")
                return redirect("konten:anmelden")
            erlaubt = (
                reverse("konten:zwei_faktor_einrichten"),
                reverse("konten:abmelden"),
                reverse("konten:passwort_aendern"),
            )
            if request.path not in erlaubt and zwei_faktor.ist_pflicht(benutzer):
                return redirect("konten:zwei_faktor_einrichten")
        return self.get_response(request)


class StellenKontoMiddleware:
    """Konten der Ausgabestellen (ADR 0059) werden nach 30 Minuten ohne Eingabe abgemeldet.

    Jede Anfrage zählt als Eingabe; die Seite lädt sich nach Ablauf selbst neu (base.html), damit
    auf dem Tablet keine Kundendaten stehen bleiben.
    """

    SCHLUESSEL = "stellen_konto_aktiv"
    MINUTEN = 30

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import time

        benutzer = request.user
        if benutzer.is_authenticated and getattr(benutzer, "stelle_id", None):
            jetzt = time.time()
            zuletzt = request.session.get(self.SCHLUESSEL)
            if zuletzt and jetzt - zuletzt > self.MINUTEN * 60:
                logout(request)
                messages.info(request, f"Nach {self.MINUTEN} Minuten ohne Eingabe abgemeldet.")
                return redirect("konten:anmelden")
            request.session[self.SCHLUESSEL] = jetzt
        return self.get_response(request)
