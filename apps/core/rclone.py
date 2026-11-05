"""rclone-Hilfen für die Fernsicherung (ADR 0106): einen rclone-Remote-Block aus den geführten
Eingaben bauen und Passwörter rclone-kompatibel „verschleiern" (obscure).

rclone speichert Passwörter nicht im Klartext, sondern mit einem festen, öffentlich bekannten
Schlüssel verschleiert (AES-CTR). Das ist keine echte Verschlüsselung, nur eine Verschleierung –
reversibel und mit demselben festen Schlüssel wie rclone, damit der Dienst backup die Konfig
unverändert benutzen kann. Umgesetzt mit `cryptography` (ohnehin vorhanden), ohne das rclone-
Programm zu brauchen (das hat nur der Dienst backup).
"""

import base64
import os

from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# Fester rclone-obscure-Schlüssel (rclone/fs/config/obscure, öffentlich). AES-256-CTR, IV voran,
# base64 (URL-sicher, ohne Füllzeichen).
_SCHLUESSEL = bytes([
    0x9c, 0x93, 0x5b, 0x48, 0x73, 0x0a, 0x55, 0x4d, 0x6b, 0xfd, 0x7c, 0x63, 0xc8, 0x86, 0xa9, 0x2b,
    0xd3, 0x90, 0x19, 0x8e, 0xb8, 0x12, 0x8a, 0xfb, 0xf4, 0xde, 0x16, 0x2b, 0x8b, 0x95, 0xf6, 0x38,
])  # fmt: skip


def obscure(text: str) -> str:
    """Ein Passwort wie `rclone obscure` verschleiern."""
    iv = os.urandom(16)
    ver = Cipher(algorithms.AES(_SCHLUESSEL), modes.CTR(iv)).encryptor()
    roh = iv + ver.update(text.encode()) + ver.finalize()
    return base64.urlsafe_b64encode(roh).decode().rstrip("=")


def reveal(verschleiert: str) -> str:
    """Umkehrung von ``obscure`` (für Tests und zum Übernehmen bestehender Werte)."""
    roh = base64.urlsafe_b64decode(verschleiert + "=" * (-len(verschleiert) % 4))
    iv, inhalt = roh[:16], roh[16:]
    ent = Cipher(algorithms.AES(_SCHLUESSEL), modes.CTR(iv)).decryptor()
    return (ent.update(inhalt) + ent.finalize()).decode()


def block_parsen(text: str) -> dict:
    """Die Zeilen `schluessel = wert` des ersten Remote-Blocks als Dict (für die Bearbeitung)."""
    werte = {}
    for zeile in text.splitlines():
        if "=" in zeile and not zeile.lstrip().startswith(("[", "#", ";")):
            k, _, v = zeile.partition("=")
            werte[k.strip()] = v.strip()
    return werte


# Welche Felder je Art in den rclone-Block kommen (Reihenfolge und Schlüssel). Passwörter
# (verschleiert) markiert PASS; der Schlüsselpfad bei SFTP wird vom Aufrufer gesetzt.
SCHLUESSELDATEI_PFAD = "/fernsicherung/sftp_key"


def block_bauen(name: str, art: str, d: dict) -> str:
    """Baut den rclone-Block `[name] …` aus den geführten Werten. ``d`` enthält die schon
    aufbereiteten Werte (Passwörter bereits verschleiert, Schlüsseldatei als Pfad)."""
    zeilen = [f"[{name}]"]

    def setze(schluessel, wert):
        if wert not in (None, ""):
            zeilen.append(f"{schluessel} = {wert}")

    if art == "sftp":
        setze("type", "sftp")
        setze("host", d.get("host"))
        setze("port", d.get("port"))
        setze("user", d.get("user"))
        setze("pass", d.get("pass"))
        setze("key_file", d.get("key_file"))
    elif art in ("nextcloud", "webdav"):
        setze("type", "webdav")
        setze("url", d.get("url"))
        setze("vendor", d.get("vendor") or ("nextcloud" if art == "nextcloud" else "other"))
        setze("user", d.get("user"))
        setze("pass", d.get("pass"))
    elif art == "s3":
        setze("type", "s3")
        setze("provider", d.get("provider") or "Other")
        setze("access_key_id", d.get("access_key_id"))
        setze("secret_access_key", d.get("secret_access_key"))
        setze("endpoint", d.get("endpoint"))
        setze("region", d.get("region"))
    elif art == "ftp":
        setze("type", "ftp")
        setze("host", d.get("host"))
        setze("port", d.get("port"))
        setze("user", d.get("user"))
        setze("pass", d.get("pass"))
        if d.get("tls"):
            setze("explicit_tls", "true")
    return "\n".join(zeilen) + "\n"
