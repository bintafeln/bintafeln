"""Zwei-Faktor-Anmeldung: Pflicht je Rolle, Einrichtung, Notfallcodes."""

import re

import segno
from django.conf import settings
from django.db import transaction
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.konten.rollen import rollen_von

ANZAHL_NOTFALLCODES = 10
NAME_APP = "Authenticator-App"
NAME_NOTFALL = "Notfallcodes"


def aussteller(geraet=None) -> str:
    """Name, unter dem der Eintrag in der Authenticator-App erscheint."""
    from apps.core.models import TafelEinstellungen

    return TafelEinstellungen.laden().name or "bintafeln"


def ist_pflicht(benutzer) -> bool:
    if not benutzer.is_authenticated or settings.DEMO:  # Demo: Einrichtung ist gesperrt
        return False
    from apps.konten.models import Rolle

    namen = rollen_von(benutzer)
    return Rolle.objects.filter(gruppe__name__in=namen, zwei_faktor_pflicht=True).exists()


def code_bereinigen(code: str) -> str:
    """Leerzeichen und Bindestriche entfernen; Notfallcodes sind kleingeschrieben gespeichert."""
    return re.sub(r"[\s-]", "", code or "").lower()


def app_geraet(benutzer) -> TOTPDevice | None:
    return TOTPDevice.objects.filter(user=benutzer, confirmed=True).first()


def neues_app_geraet(benutzer) -> TOTPDevice:
    """Liefert das noch unbestätigte Gerät für die Einrichtung (legt es bei Bedarf an)."""
    geraet = TOTPDevice.objects.filter(user=benutzer, confirmed=False).first()
    if geraet is None:
        geraet = TOTPDevice.objects.create(user=benutzer, name=NAME_APP, confirmed=False)
    return geraet


def schluessel_als_text(geraet: TOTPDevice) -> str:
    from base64 import b32encode

    text = b32encode(geraet.bin_key).decode("ascii").rstrip("=")
    return " ".join(text[i : i + 4] for i in range(0, len(text), 4))


def qr_code_svg(geraet: TOTPDevice) -> str:
    return segno.make(geraet.config_url, error="m").svg_inline(
        scale=5, dark="#000000", light="#ffffff", title="QR-Code für die Authenticator-App"
    )


@transaction.atomic
def notfallcodes_erzeugen(benutzer) -> list[str]:
    """Ersetzt alle Notfallcodes des Benutzers durch neue und gibt sie zurück."""
    geraet, _ = StaticDevice.objects.get_or_create(
        user=benutzer, name=NAME_NOTFALL, defaults={"confirmed": True}
    )
    geraet.token_set.all().delete()
    codes = [StaticToken.random_token() for _ in range(ANZAHL_NOTFALLCODES)]
    StaticToken.objects.bulk_create(StaticToken(device=geraet, token=code) for code in codes)
    return codes


def notfallcodes_uebrig(benutzer) -> int:
    return StaticToken.objects.filter(device__user=benutzer).count()


@transaction.atomic
def einrichtung_bestaetigen(geraet: TOTPDevice, code: str) -> bool:
    if not geraet.verify_token(code_bereinigen(code)):
        return False
    geraet.confirmed = True
    geraet.save()
    TOTPDevice.objects.filter(user=geraet.user, confirmed=False).delete()
    return True


@transaction.atomic
def abschalten(benutzer) -> None:
    """Entfernt alle Zwei-Faktor-Geräte (App und Notfallcodes) des Benutzers."""
    for geraet in TOTPDevice.objects.filter(user=benutzer):
        geraet.delete()
    for geraet in StaticDevice.objects.filter(user=benutzer):
        geraet.delete()
