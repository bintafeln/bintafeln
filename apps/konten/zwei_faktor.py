"""Zwei-Faktor-Anmeldung: Pflicht je Rolle, Einrichtung, Notfallcodes."""

import datetime as dt
import hashlib
import re
import secrets

import segno
from django.conf import settings
from django.core import signing
from django.db import transaction
from django.utils import timezone
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
    if getattr(benutzer, "stelle_id", None):  # Konto einer Ausgabestelle (ADR 0059)
        return False
    from apps.konten.models import Rolle

    namen = rollen_von(benutzer)
    return Rolle.objects.filter(gruppe__name__in=namen, zwei_faktor_pflicht=True).exists()


def erlaubt(benutzer) -> bool:
    """Konten der Ausgabestellen nur, wenn die Tafel es freigeschaltet hat (ADR 0059)."""
    if not getattr(benutzer, "stelle_id", None):
        return True
    from apps.konten.models import AnmeldeEinstellungen

    return AnmeldeEinstellungen.laden().stellen_zwei_faktor


def stellen_abschalten() -> int:
    """Entfernt die Geräte aller Konten der Ausgabestellen (beim Ausschalten der Freigabe)."""
    from django.contrib.auth import get_user_model

    konten = get_user_model().objects.filter(stelle__isnull=False)
    betroffen = [k for k in konten if TOTPDevice.objects.filter(user=k).exists()
                 or StaticDevice.objects.filter(user=k).exists()]  # fmt: skip
    for k in betroffen:
        abschalten(k)
    return len(betroffen)


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
    vertrauen_entziehen(benutzer)  # neue Einrichtung: alle Geräte fragen wieder nach dem Code
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
    vertrauen_entziehen(benutzer)
    for geraet in TOTPDevice.objects.filter(user=benutzer):
        geraet.delete()
    for geraet in StaticDevice.objects.filter(user=benutzer):
        geraet.delete()


# ── Vertraute Geräte: für einige Tage kein Code nötig ───────────────────────

COOKIE = "bintafeln_geraet"
SALZ = "bintafeln.vertrautes_geraet"


def _pruefsumme(merkmal: str) -> str:
    return hashlib.sha256(merkmal.encode()).hexdigest()


def _passwort_stand(benutzer) -> str:
    """Ändert sich mit jedem neuen Passwort (ohne das Passwort preiszugeben)."""
    return hashlib.sha256(f"{SALZ}:{benutzer.password}".encode()).hexdigest()


def vertrauen_tage() -> int:
    from apps.konten.models import AnmeldeEinstellungen

    return 0 if settings.DEMO else AnmeldeEinstellungen.laden().vertrauen_tage


def geraet_vertrauen(request, antwort, benutzer) -> None:
    """Legt das vertraute Gerät an und setzt das Cookie im Browser."""
    from apps.konten.models import VertrautesGeraet

    tage = vertrauen_tage()
    if not tage:
        return
    merkmal = secrets.token_urlsafe(32)
    agent = request.META.get("HTTP_USER_AGENT", "")
    VertrautesGeraet.objects.create(
        benutzer=benutzer, pruefsumme=_pruefsumme(merkmal),
        passwort_stand=_passwort_stand(benutzer), bezeichnung=geraet_name(agent),
        gueltig_bis=timezone.now() + dt.timedelta(days=tage),
    )  # fmt: skip
    antwort.set_cookie(
        COOKIE, signing.dumps({"b": benutzer.pk, "m": merkmal}, salt=SALZ),
        max_age=tage * 86400, httponly=True, secure=request.is_secure(), samesite="Lax",
    )  # fmt: skip


def vertrautes_geraet(request, benutzer):
    """Das vertraute Gerät dieses Browsers für den Benutzer, sonst None."""
    from apps.konten.models import VertrautesGeraet

    wert = request.COOKIES.get(COOKIE)
    if not wert or not vertrauen_tage():
        return None
    try:
        daten = signing.loads(wert, salt=SALZ)
    except signing.BadSignature:
        return None
    if daten.get("b") != benutzer.pk:
        return None
    geraet = VertrautesGeraet.objects.filter(
        benutzer=benutzer, pruefsumme=_pruefsumme(str(daten.get("m"))),
        gueltig_bis__gt=timezone.now(),
    ).first()  # fmt: skip
    if geraet is None or geraet.passwort_stand != _passwort_stand(benutzer):
        return None
    geraet.zuletzt_am = timezone.now()
    geraet.save(update_fields=["zuletzt_am"])
    return geraet


def vertrauen_entziehen(benutzer) -> int:
    from apps.konten.models import VertrautesGeraet

    return VertrautesGeraet.objects.filter(benutzer=benutzer).delete()[0]


def geraet_name(agent: str) -> str:
    """Grobe Bezeichnung aus dem User-Agent, z. B. „Firefox unter Windows“."""
    browser = next((n for k, n in [("Edg/", "Edge"), ("Firefox", "Firefox"),
                                   ("Chrome", "Chrome"), ("Safari", "Safari")] if k in agent),
                   "Browser")  # fmt: skip
    system = next((n for k, n in [("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
                                  ("Windows", "Windows"), ("Mac OS", "macOS"),
                                  ("Linux", "Linux")] if k in agent), "")  # fmt: skip
    return f"{browser} unter {system}" if system else browser


def geraete_aufraeumen() -> None:
    from apps.konten.models import VertrautesGeraet

    VertrautesGeraet.objects.filter(gueltig_bis__lt=timezone.now()).delete()
