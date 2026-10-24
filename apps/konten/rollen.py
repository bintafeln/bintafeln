"""Rollen von bintafeln. Jede Rolle ist eine Django-Gruppe."""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

ADMIN = "Admin"
BUERO = "Büro"
AUSGABE = "Ausgabe"
KIOSK = "Kiosk"
FAHRER = "Fahrer"
BEIFAHRER = "Beifahrer"

ALLE = (ADMIN, BUERO, AUSGABE, KIOSK, FAHRER, BEIFAHRER)


def rollen_von(benutzer) -> set[str]:
    if not benutzer.is_authenticated:
        return set()
    if benutzer.is_superuser:
        return set(ALLE)
    return set(benutzer.groups.filter(name__in=ALLE).values_list("name", flat=True))


def hat_rolle(benutzer, *rollen: str) -> bool:
    return bool(rollen_von(benutzer) & set(rollen))


def darf_mitarbeitende_verwalten(benutzer) -> bool:
    """Admin immer; Büro nur, wenn ein Admin es in den Tafel-Einstellungen freigegeben hat."""
    from apps.core.models import TafelEinstellungen

    if hat_rolle(benutzer, ADMIN):
        return True
    return hat_rolle(benutzer, BUERO) and TafelEinstellungen.laden().buero_verwaltet_mitarbeitende


def rolle_erforderlich(*rollen: str):
    """Decorator: Ansicht nur für angemeldete Benutzer mit einer der Rollen."""

    def dekorator(ansicht):
        @wraps(ansicht)
        @login_required
        def pruefen(request, *args, **kwargs):
            if not hat_rolle(request.user, *rollen):
                raise PermissionDenied
            return ansicht(request, *args, **kwargs)

        return pruefen

    return dekorator
