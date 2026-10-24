"""Verwaltung der Mitarbeitenden (ADR 0015).

Schutzregeln, die hier und nicht in den Ansichten stehen, damit sie überall gelten:
- Niemand sperrt sich selbst oder nimmt sich selbst die Admin-Rolle.
- Wer nur über die Büro-Freigabe verwaltet, fasst keine Admin-Konten an und vergibt keine
  Admin-Rolle.

Zusammen sorgt das dafür, dass immer mindestens ein aktiver Admin bleibt: Ein Admin-Konto
ändert nur ein aktiver Admin, und der kann sich selbst weder sperren noch herabstufen.
"""

import secrets

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from apps.konten import rollen

# Ohne leicht verwechselbare Zeichen (0/O, 1/l/I), damit man es gut abschreiben kann.
ZEICHEN = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"


class VerwaltungsFehler(ValueError):
    pass


def startpasswort() -> str:
    """Zufälliges Passwort in drei Vierergruppen, z. B. 'k7Qm-xP3a-9wTe'."""
    return "-".join("".join(secrets.choice(ZEICHEN) for _ in range(4)) for _ in range(3))


def ist_admin(benutzer) -> bool:
    return benutzer.is_superuser or benutzer.groups.filter(name=rollen.ADMIN).exists()


def vergebbare_rollen(verwalter) -> list[str]:
    if rollen.hat_rolle(verwalter, rollen.ADMIN):
        return list(rollen.ALLE)
    return [r for r in rollen.ALLE if r != rollen.ADMIN]


def darf_bearbeiten(verwalter, ziel) -> bool:
    return rollen.hat_rolle(verwalter, rollen.ADMIN) or not ist_admin(ziel)


def _pruefen(verwalter, ziel):
    if not darf_bearbeiten(verwalter, ziel):
        raise VerwaltungsFehler("Admin-Konten kann nur ein Admin bearbeiten.")


def _passwort_neu(ziel) -> str:
    passwort = startpasswort()
    ziel.set_password(passwort)
    ziel.passwort_aendern = True
    return passwort


@transaction.atomic
def anlegen(verwalter, daten: dict, rollen_namen: list[str]) -> tuple[object, str]:
    """Legt ein Konto an und liefert es mit dem Startpasswort (nur einmal anzeigen)."""
    if set(rollen_namen) - set(vergebbare_rollen(verwalter)):
        raise VerwaltungsFehler("Diese Rolle dürfen Sie nicht vergeben.")
    ziel = get_user_model()(**daten)
    passwort = _passwort_neu(ziel)
    ziel.save()
    ziel.groups.set(Group.objects.filter(name__in=rollen_namen))
    return ziel, passwort


@transaction.atomic
def bearbeiten(verwalter, ziel, rollen_namen: list[str]) -> None:
    """Speichert ein bereits per Formular geändertes Konto und setzt seine Rollen."""
    _pruefen(verwalter, ziel)
    if set(rollen_namen) - set(vergebbare_rollen(verwalter)):
        raise VerwaltungsFehler("Diese Rolle dürfen Sie nicht vergeben.")
    # Ein Superuser bleibt auch ohne die Gruppe Admin; nur ohne Superuser-Recht wäre es eine
    # Herabstufung.
    selbst = ziel.pk == verwalter.pk and not ziel.is_superuser
    if selbst and rollen.ADMIN not in rollen_namen and ist_admin(ziel):
        raise VerwaltungsFehler("Sie können sich die Admin-Rolle nicht selbst nehmen.")
    ziel.save()
    ziel.groups.set(Group.objects.filter(name__in=rollen_namen))


def sperren(verwalter, ziel) -> None:
    _pruefen(verwalter, ziel)
    if ziel.pk == verwalter.pk:
        raise VerwaltungsFehler("Sie können sich nicht selbst sperren.")
    ziel.is_active = False
    ziel.gesperrt_am = timezone.now()
    ziel.gesperrt_von = str(verwalter)[:150]
    ziel.save(update_fields=["is_active", "gesperrt_am", "gesperrt_von"])


def entsperren(verwalter, ziel) -> None:
    _pruefen(verwalter, ziel)
    ziel.is_active = True
    ziel.gesperrt_am = None
    ziel.gesperrt_von = ""
    ziel.save(update_fields=["is_active", "gesperrt_am", "gesperrt_von"])


def passwort_zuruecksetzen(verwalter, ziel) -> str:
    _pruefen(verwalter, ziel)
    passwort = _passwort_neu(ziel)
    ziel.save(update_fields=["password", "passwort_aendern"])
    return passwort
