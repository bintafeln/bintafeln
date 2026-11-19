from urllib.parse import urlparse

from django.contrib import messages
from django.contrib.auth import logout
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django_otp import user_has_device

from apps.konten import zwei_faktor

FREIE_PFADE = ("/static/", "/media/", "/healthz/", "/app/")


class HtmxAnmeldeMiddleware:
    """Läuft die Sitzung ab (Abmeldung, Zeitüberschreitung oder Neustart beim Update), leitet
    bintafeln auf die Anmeldeseite um – und merkt sich in ``next``, wohin es danach gehen soll.

    - Bei einem htmx-Aufruf würde htmx das HTML der Anmeldeseite in einen Seitenbereich einfügen
      – es entsteht ein doppeltes „Anmelden" über der Seite. Stattdessen schicken wir htmx per
      ``HX-Redirect`` die ganze Seite zur Anmeldung.
    - ``next`` bleibt nur stehen, wenn eine ganze Seite aufgerufen wurde. Kam die Anfrage aus dem
      Hintergrund (htmx, ``fetch``, eingebettetes PDF) oder war sie ein abgeschicktes Formular,
      zeigte ``next`` auf einen Seitenbaustein oder eine Adresse, die nur Eingaben annimmt: Nach
      dem Anmelden stand dort nur ein Bruchstück oder eine Fehlerseite. Dann geht es nach dem
      Anmelden zur Startseite."""

    def __init__(self, get_response):
        self.get_response = get_response

    @staticmethod
    def _ganze_seite(request) -> bool:
        """Hat der Browser eine ganze Seite angefordert (Link, Adresszeile, Neuladen)?"""
        if request.method not in ("GET", "HEAD") or request.headers.get("HX-Request"):
            return False
        # Browser nennen das Ziel der Anfrage; ältere ohne diese Angabe gelten als Seitenaufruf
        return request.headers.get("Sec-Fetch-Dest", "document") == "document"

    def __call__(self, request):
        response = self.get_response(request)
        if response.status_code in (301, 302):
            ziel = urlparse(response.headers.get("Location", ""))
            if ziel.path == reverse("konten:anmelden"):
                if not self._ganze_seite(request) and ziel.query:
                    response["Location"] = ziel._replace(query="").geturl()
                if request.headers.get("HX-Request"):
                    leer = HttpResponse(status=204)
                    leer["HX-Redirect"] = response["Location"]
                    return leer
        return response


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
                request.abmeldung_automatisch = True  # fürs Anmeldeprotokoll
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
                request.abmeldung_automatisch = True  # fürs Anmeldeprotokoll
                logout(request)
                messages.info(request, f"Nach {self.MINUTEN} Minuten ohne Eingabe abgemeldet.")
                return redirect("konten:anmelden")
            request.session[self.SCHLUESSEL] = jetzt
        return self.get_response(request)
