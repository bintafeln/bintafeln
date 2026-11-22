"""Push-Nachrichten aufs Handy (Web Push, ADR 0134, 0158).

Web Push (RFC 8030): Der Browser eines Geräts nennt eine Adresse beim Push-Dienst seines
Herstellers; bintafeln schickt dorthin eine verschlüsselte Nachricht (RFC 8291), unterschrieben mit
dem eigenen Schlüssel der Tafel (VAPID, RFC 8292). Der Push-Dienst sieht nur verschlüsselte Daten.
Gebaut nur mit ``cryptography``, ohne weitere Abhängigkeit.

Zwei Nutzer dieser Technik: „Wartezeit aufs Handy“ für Kunden (``apps/aufruf/push.py``) und
Nachrichten an Mitarbeitende, die das auf „Mein Konto“ für ihr Gerät eingeschaltet haben
(``PushAbo``, ``an_benutzer()``). Module rufen nur ``an_benutzer()`` auf.

In Tests ``push._senden`` und ``push._im_hintergrund`` ersetzen.
"""

import base64
import json
import logging
import os
import struct
import threading
import time
import urllib.error
import urllib.request
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
from django.conf import settings
from django.db import connections, transaction

from apps.core import geheimnis

log = logging.getLogger(__name__)
LEBENSDAUER = 15 * 60  # Sekunden: eine verspätete Nachricht nützt niemandem mehr
# Nur an die Push-Dienste der Browser senden (Chrome/Android, Firefox, Safari/iPhone, Edge) –
# nie an eine beliebige Adresse, die jemand einschickt.
PUSH_DIENSTE = (".googleapis.com", ".mozilla.com", ".push.apple.com", ".notify.windows.com")
GERAETE_JE_KONTO = 5


def _b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ── Schlüssel der Tafel (VAPID) ───────────────────────────────────────────


def _privat() -> ec.EllipticCurvePrivateKey:
    """Eigener Schlüssel der Tafel; beim ersten Bedarf erzeugt und verschlüsselt gespeichert."""
    from apps.core.models import PushEinstellungen

    e = PushEinstellungen.laden()
    pem = geheimnis.entschluesseln(e.schluessel) if e.schluessel else None
    if not pem:
        schluessel = ec.generate_private_key(ec.SECP256R1())
        pem = schluessel.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()  # fmt: skip
        PushEinstellungen.objects.filter(pk=e.pk).update(schluessel=geheimnis.verschluesseln(pem))
        return schluessel
    return serialization.load_pem_private_key(pem.encode(), password=None)


def oeffentlicher_schluessel() -> str:
    """Für den Browser (``applicationServerKey``): öffentlicher Schlüssel, base64url."""
    punkt = (
        _privat()
        .public_key()
        .public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)
    )
    return _b64(punkt)


def _absender() -> str:
    """Kontakt für den Push-Dienst (Pflichtangabe „sub“): Adresse der Installation."""
    if settings.DOMAIN:
        return f"https://{settings.DOMAIN}"
    from apps.core.models import MailEinstellungen

    absender = MailEinstellungen.laden().absenderadresse
    return f"mailto:{absender}" if absender else "mailto:push@localhost"


def vapid_kopf(adresse: str) -> str:
    teile = urlsplit(adresse)
    kopf = _b64(json.dumps({"typ": "JWT", "alg": "ES256"}).encode())
    inhalt = _b64(json.dumps({
        "aud": f"{teile.scheme}://{teile.netloc}", "exp": int(time.time()) + 12 * 3600,
        "sub": _absender(),
    }).encode())  # fmt: skip
    schluessel = _privat()
    r, s = decode_dss_signature(schluessel.sign(f"{kopf}.{inhalt}".encode(),
                                                ec.ECDSA(hashes.SHA256())))  # fmt: skip
    signatur = _b64(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
    return f"vapid t={kopf}.{inhalt}.{signatur}, k={oeffentlicher_schluessel()}"


# ── Verschlüsseln (RFC 8291, aes128gcm) ───────────────────────────────────


def _hkdf(salz: bytes, info: bytes, laenge: int, ikm: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=laenge, salt=salz, info=info).derive(ikm)


def verschluesseln(nachricht: bytes, p256dh: str, auth: str) -> bytes:
    """Nachricht für genau diesen Browser verschlüsseln (nur er hat den passenden Schlüssel)."""
    browser = _unb64(p256dh)
    geheim = _unb64(auth)
    eigen = ec.generate_private_key(ec.SECP256R1())  # für jede Nachricht neu
    eigen_pub = eigen.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    gemeinsam = eigen.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), browser)
    )
    ikm = _hkdf(geheim, b"WebPush: info\x00" + browser + eigen_pub, 32, gemeinsam)
    salz = os.urandom(16)
    cek = _hkdf(salz, b"Content-Encoding: aes128gcm\x00", 16, ikm)
    nonce = _hkdf(salz, b"Content-Encoding: nonce\x00", 12, ikm)
    inhalt = AESGCM(cek).encrypt(nonce, nachricht + b"\x02", None)  # \x02: letzter Block
    return salz + struct.pack("!I", 4096) + bytes([len(eigen_pub)]) + eigen_pub + inhalt


# ── Senden ────────────────────────────────────────────────────────────────


def _senden(adresse: str, daten: bytes, kopf: dict) -> int:
    """HTTP-POST an den Push-Dienst; Statuscode (0 bei Netzfehler)."""
    anfrage = urllib.request.Request(adresse, data=daten, method="POST", headers=kopf)  # noqa: S310
    try:
        with urllib.request.urlopen(anfrage, timeout=10) as antwort:  # noqa: S310
            return antwort.status
    except urllib.error.HTTPError as fehler:
        return fehler.code
    except OSError as fehler:
        log.warning("Push-Nachricht nicht zugestellt: %s", fehler)
        return 0


def erlaubt(adresse: str) -> bool:
    teile = urlsplit(adresse)
    host = (teile.hostname or "").lower()
    return (
        teile.scheme == "https"
        and not teile.port
        and any(host.endswith(dienst) for dienst in PUSH_DIENSTE)
    )


def zustellen(adresse: str, p256dh: str, auth: str, nutzlast: dict) -> int:
    """Eine Nachricht an genau einen Browser; Statuscode des Push-Dienstes (0 = nicht gesendet).
    404 und 410 heißen: Diese Adresse gibt es nicht mehr."""
    if not adresse or not erlaubt(adresse):
        return 0
    daten = verschluesseln(json.dumps(nutzlast).encode(), p256dh, auth)
    return _senden(adresse, daten, {
        "Authorization": vapid_kopf(adresse), "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream", "TTL": str(LEBENSDAUER), "Urgency": "high",
    })  # fmt: skip


def pruefen(adresse: str, p256dh: str, auth: str) -> None:
    """Abo eines Browsers prüfen, bevor es gespeichert wird."""
    if not erlaubt(adresse) or not p256dh or not auth:
        raise ValueError("unvollständig oder kein Push-Dienst")
    _unb64(p256dh), _unb64(auth)  # muss base64url sein


def _im_hintergrund(fn) -> None:
    def lauf():
        try:
            fn()
        except Exception as fehler:  # noqa: BLE001
            log.warning("Push-Nachrichten fehlgeschlagen: %s", fehler)
        finally:
            connections.close_all()

    threading.Thread(target=lauf, daemon=True).start()


def nach_speichern(fn) -> None:
    """Nach dem Speichern im Hintergrund ausführen, damit die Seite nicht auf den Push-Dienst
    wartet."""
    transaction.on_commit(lambda: _im_hintergrund(fn))


# ── Nachrichten an Mitarbeitende ──────────────────────────────────────────


def abonnieren(benutzer, adresse: str, p256dh: str, auth: str, geraet: str = ""):
    """Dieses Gerät bekommt ab jetzt die Nachrichten für dieses Konto. Ein Gerät gehört immer nur
    zu einem Konto; je Konto bleiben die neuesten ``GERAETE_JE_KONTO`` Geräte."""
    from apps.core.models import PushAbo

    pruefen(adresse, p256dh, auth)
    PushAbo.objects.filter(adresse=adresse[:2000]).delete()
    abo = PushAbo.objects.create(
        benutzer=benutzer, adresse=adresse[:2000], p256dh=p256dh[:200], auth=auth[:100],
        geraet=geraet[:200],
    )  # fmt: skip
    alte = PushAbo.objects.filter(benutzer=benutzer).order_by("-angelegt_am", "-pk")
    PushAbo.objects.filter(pk__in=[a.pk for a in alte[GERAETE_JE_KONTO:]]).delete()
    return abo


def abbestellen(benutzer, adresse: str = "") -> int:
    """Ein Gerät abmelden; ohne Adresse alle Geräte des Kontos."""
    from apps.core.models import PushAbo

    abos = PushAbo.objects.filter(benutzer=benutzer)
    if adresse:
        abos = abos.filter(adresse=adresse[:2000])
    return abos.delete()[0]


def geraete(benutzer) -> int:
    from apps.core.models import PushAbo

    return PushAbo.objects.filter(benutzer=benutzer).count()


def an_benutzer(benutzer, titel: str, text: str, link: str = "", kennung: str = "") -> int:
    """Nachricht an alle Geräte, auf denen diese Mitarbeitenden die Benachrichtigung eingeschaltet
    haben (einzelnes Konto oder mehrere). ``link`` öffnet sich beim Antippen (nur eigene Adressen),
    gleiche ``kennung`` ersetzt eine ältere Nachricht. Ergebnis: Zahl der zugestellten."""
    from apps.core.models import PushAbo

    konten = benutzer if hasattr(benutzer, "__iter__") else [benutzer]
    ids = [k.pk for k in konten if k is not None and k.is_active]
    eigen = link.startswith("/") and not link.startswith("//")
    nutzlast = {"titel": titel, "text": text, "kennung": kennung, "link": link if eigen else ""}
    gesendet = 0
    for abo in PushAbo.objects.filter(benutzer_id__in=ids):
        status = zustellen(abo.adresse, abo.p256dh, abo.auth, nutzlast)
        if status in (404, 410):  # abgemeldet, Browser gewechselt
            abo.delete()
        gesendet += 200 <= status < 300
    return gesendet
