"""Push-Nachrichten für „Wartezeit aufs Handy“ (ADR 0134).

Wer auf /warten/ die Benachrichtigung einschaltet, bekommt aufs Handy „Gleich sind Sie dran“, sobald
nur noch ``HandyEinstellungen.push_vorher`` Nummern vor ihm sind, und „Sie sind dran“ beim Aufruf –
auch wenn die Seite nicht offen ist. Das ist Web Push (RFC 8030): Der Browser des Handys nennt eine
Adresse beim Push-Dienst seines Herstellers; bintafeln schickt dorthin eine verschlüsselte Nachricht
(RFC 8291), unterschrieben mit dem eigenen Schlüssel der Tafel (VAPID, RFC 8292). Der Push-Dienst
sieht nur verschlüsselte Daten. Gebaut nur mit ``cryptography``, ohne weitere Abhängigkeit.

Ausgelöst nach jedem „Weiter“ im Aufruf (``ablauf.weiter``) im Hintergrund, damit der Aufruf am
Schalter nicht wartet. In Tests ``push._senden`` und ``push._im_hintergrund`` ersetzen.
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
BALD, JETZT = "bald", "jetzt"


def _b64(daten: bytes) -> str:
    return base64.urlsafe_b64encode(daten).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


# ── Schlüssel der Tafel (VAPID) ───────────────────────────────────────────


def _privat() -> ec.EllipticCurvePrivateKey:
    """Eigener Schlüssel der Tafel; beim ersten Bedarf erzeugt und verschlüsselt gespeichert."""
    from apps.aufruf.models import HandyEinstellungen

    e = HandyEinstellungen.laden()
    pem = geheimnis.entschluesseln(e.push_schluessel) if e.push_schluessel else None
    if not pem:
        schluessel = ec.generate_private_key(ec.SECP256R1())
        pem = schluessel.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ).decode()  # fmt: skip
        HandyEinstellungen.objects.filter(pk=e.pk).update(
            push_schluessel=geheimnis.verschluesseln(pem)
        )
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


def senden(z, titel: str, text: str) -> bool:
    """Eine Nachricht an das Handy dieses Zugangs. Meldet der Push-Dienst, dass es die Adresse
    nicht mehr gibt (abgemeldet, Browser gewechselt), wird sie vergessen."""
    if not z.push_adresse or not erlaubt(z.push_adresse):
        return False
    daten = verschluesseln(json.dumps({"titel": titel, "text": text}).encode(),
                           z.push_p256dh, z.push_auth)  # fmt: skip
    status = _senden(z.push_adresse, daten, {
        "Authorization": vapid_kopf(z.push_adresse), "Content-Encoding": "aes128gcm",
        "Content-Type": "application/octet-stream", "TTL": str(LEBENSDAUER), "Urgency": "high",
    })  # fmt: skip
    if status in (404, 410):
        abbestellen(z)
    return 200 <= status < 300


def erlaubt(adresse: str) -> bool:
    teile = urlsplit(adresse)
    host = (teile.hostname or "").lower()
    return (
        teile.scheme == "https"
        and not teile.port
        and any(host.endswith(dienst) for dienst in PUSH_DIENSTE)
    )


def abonnieren(z, adresse: str, p256dh: str, auth: str, sprache: str) -> None:
    if not erlaubt(adresse) or not p256dh or not auth:
        raise ValueError("unvollständig oder kein Push-Dienst")
    _unb64(p256dh), _unb64(auth)  # muss base64url sein
    z.push_adresse, z.push_p256dh, z.push_auth = adresse[:2000], p256dh[:200], auth[:100]
    z.push_sprache, z.push_gesendet = sprache[:10], ""
    z.save(update_fields=["push_adresse", "push_p256dh", "push_auth", "push_sprache",
                          "push_gesendet"])  # fmt: skip


def abbestellen(z) -> None:
    z.push_adresse = z.push_p256dh = z.push_auth = z.push_gesendet = ""
    z.save(update_fields=["push_adresse", "push_p256dh", "push_auth", "push_gesendet"])


# ── Wann wer eine Nachricht bekommt ───────────────────────────────────────


def stufe(stand: dict, vorher: int) -> str:
    """„jetzt“ beim Aufruf, „bald“ wenn nur noch höchstens ``vorher`` Nummern aufgerufen werden,
    bevor diese auf dem Monitor steht; sonst leer."""
    if stand.get("art") == "jetzt":
        return JETZT
    davor = stand.get("vor_aufruf", stand.get("vor", 99))
    if stand.get("art") == "warten" and vorher and davor <= vorher:
        return BALD
    return ""


def nachricht(stand: dict, art: str, sprache: str) -> tuple[str, str]:
    from apps.aufruf.views_warten import texte

    t = texte(sprache or "de")
    if art == JETZT:
        return t["push_jetzt_titel"], t["push_jetzt"].format(nummer=stand.get("nummer", ""))
    return t["push_bald_titel"], t["push_bald"].format(vor=stand.get("vor", ""))


def benachrichtigen(stelle, datum) -> int:
    """Allen Handys dieser Ausgabestelle mit Benachrichtigung schicken, was neu ist; je Tag und
    Stufe nur einmal. Ergebnis: Zahl der gesendeten Nachrichten."""
    from apps.aufruf import handy
    from apps.aufruf.models import HandyEinstellungen, HandyZugang

    vorher = HandyEinstellungen.laden().push_vorher
    gesendet = 0
    for z in HandyZugang.objects.exclude(push_adresse=""):
        st = handy.stand(z, datum)
        if st.get("stelle") != stelle.name:
            continue
        art = stufe(st, vorher)
        merke = f"{datum:%Y-%m-%d}:{art}"
        bisher = z.push_gesendet
        # „bald“ nach „jetzt“ (z. B. nach „Zurück“) nicht noch einmal schicken
        if not art or bisher == merke or (art == BALD and bisher == f"{datum:%Y-%m-%d}:{JETZT}"):
            continue
        titel, text = nachricht(st, art, z.push_sprache)
        if senden(z, titel, text):
            HandyZugang.objects.filter(pk=z.pk).update(push_gesendet=merke)
            gesendet += 1
    return gesendet


def _im_hintergrund(fn) -> None:
    def lauf():
        try:
            fn()
        except Exception as fehler:  # noqa: BLE001
            log.warning("Push-Nachrichten fehlgeschlagen: %s", fehler)
        finally:
            connections.close_all()

    threading.Thread(target=lauf, daemon=True).start()


def anstossen(stelle, datum) -> None:
    """Nach dem Speichern eines Aufrufs: Nachrichten im Hintergrund verschicken."""
    from apps.aufruf.models import HandyZugang

    if not HandyZugang.objects.exclude(push_adresse="").exists():
        return
    transaction.on_commit(lambda: _im_hintergrund(lambda: benachrichtigen(stelle, datum)))
