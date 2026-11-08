"""Anmeldeprotokoll (ADR 0117): erfolgreiche Anmeldungen und Fehlversuche mit IP und Browser/System
für die IT-Sicherheit. Erfolg und falscher Zwei-Faktor-Code tragen die Ansichten selbst ein;
falsche Passwörter fängt das Signal ``user_login_failed`` ab. Aufbewahrung je Tafel einstellbar,
danach automatisch gelöscht (``fristen_anwenden``)."""

from datetime import timedelta

from django.contrib.auth.signals import user_login_failed
from django.dispatch import receiver
from django.utils import timezone


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
