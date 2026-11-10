"""Anmeldeprotokoll (ADR 0117): erfolgreiche Anmeldungen, Fehlversuche und Abmeldungen mit IP und
Browser/System für die IT-Sicherheit. Erfolg und falscher Zwei-Faktor-Code tragen die Ansichten
selbst ein; falsche Passwörter fängt das Signal ``user_login_failed`` ab, Abmeldungen (auch die
automatischen) das Signal ``user_logged_out``. Aufbewahrung je Tafel einstellbar, danach
automatisch gelöscht (``fristen_anwenden``)."""

from datetime import timedelta

from django.contrib.auth.signals import user_logged_out, user_login_failed
from django.dispatch import receiver
from django.utils import timezone

# Abmeldungen stehen als eigener Hinweis im Protokoll (``grund`` beginnt mit „Abmeldung“).
ABMELDUNG = "Abmeldung"
ABMELDUNG_AUTOMATISCH = "Abmeldung (automatisch)"


def _ip(request) -> str | None:
    """Echte Besucher-IP hinter dem Caddy-Proxy: erster Eintrag in X-Forwarded-For."""
    if request is None:
        return None
    weitergeleitet = request.META.get("HTTP_X_FORWARDED_FOR", "")
    return weitergeleitet.split(",")[0].strip() or request.META.get("REMOTE_ADDR") or None


def _browser(request) -> str:
    if request is None:
        return ""
    return (request.META.get("HTTP_USER_AGENT", "") or "")[:300]


def eintragen(request, benutzername, erfolg, *, benutzer=None, grund="") -> None:
    """Eine Anmeldung oder einen Fehlversuch festhalten – außer das Protokoll ist aus."""
    from apps.konten.models import AnmeldeEinstellungen, AnmeldeProtokoll

    if AnmeldeEinstellungen.laden().protokoll_tage == 0:
        return
    AnmeldeProtokoll.objects.create(
        benutzer=benutzer, benutzername=(benutzername or "")[:150], erfolg=erfolg,
        grund=grund, ip=_ip(request), browser=_browser(request),
    )  # fmt: skip


def fristen_anwenden(jetzt=None) -> int:
    """Einträge löschen, die älter als die eingestellte Frist sind; bei „aus“ alle (ADR 0117)."""
    from apps.konten.models import AnmeldeEinstellungen, AnmeldeProtokoll

    tage = AnmeldeEinstellungen.laden().protokoll_tage
    if tage == 0:
        anzahl, _ = AnmeldeProtokoll.objects.all().delete()
        return anzahl
    grenze = (jetzt or timezone.now()) - timedelta(days=tage)
    anzahl, _ = AnmeldeProtokoll.objects.filter(zeitpunkt__lt=grenze).delete()
    return anzahl


@receiver(user_login_failed)
def _fehlversuch(sender, credentials=None, request=None, **kwargs):
    """Falsches Passwort oder unbekannter Benutzername: ``authenticate`` meldet den Fehlversuch."""
    name = (credentials or {}).get("username", "")
    eintragen(request, name, False, grund="Passwort")


@receiver(user_logged_out)
def _abmeldung(sender, request=None, user=None, **kwargs):
    """Jede Abmeldung: der Knopf „Abmelden“ ebenso wie die automatische (z. B. Ausgabestellen-Konto
    nach 30 Minuten ohne Eingabe); dort setzt die Middleware ``abmeldung_automatisch``."""
    if user is None or not getattr(user, "is_authenticated", False):
        return
    automatisch = getattr(request, "abmeldung_automatisch", False)
    eintragen(request, user.get_username(), True, benutzer=user,
              grund=ABMELDUNG_AUTOMATISCH if automatisch else ABMELDUNG)  # fmt: skip
