"""Benachrichtigung per Telegram (ADR 0074): ein Bot der Tafel schreibt in die eingestellten Chats.

Der Bot-Schlüssel liegt verschlüsselt in den Einstellungen (``apps.core.geheimnis``). Telegram
bekommt nur, wer ausfällt, wann und welche Touren betroffen sind – nie den Grund (z. B. „krank“).
"""

import json
import logging
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.core import geheimnis

log = logging.getLogger(__name__)
ADRESSE = "https://api.telegram.org/bot{schluessel}/{methode}"
ZEIT = 10


class TelegramFehler(Exception):
    pass


def _aufruf(schluessel: str, methode: str, daten: dict | None = None) -> dict:
    """Ruft die Telegram-Schnittstelle auf (nur diese feste https-Adresse)."""
    anfrage = Request(ADRESSE.format(schluessel=schluessel, methode=methode),  # noqa: S310
                      data=json.dumps(daten or {}).encode(),
                      headers={"Content-Type": "application/json"})  # fmt: skip
    try:
        with urlopen(anfrage, timeout=ZEIT) as antwort:  # noqa: S310
            ergebnis = json.load(antwort)
    except HTTPError as fehler:
        if fehler.code in (401, 404):
            raise TelegramFehler(
                "Telegram kennt diesen Bot-Schlüssel nicht. Bitte prüfen."
            ) from fehler
        raise TelegramFehler(f"Telegram antwortet mit Fehler {fehler.code}.") from fehler
    except (URLError, OSError, ValueError) as fehler:
        raise TelegramFehler("Telegram ist nicht erreichbar.") from fehler
    if not ergebnis.get("ok"):
        raise TelegramFehler(ergebnis.get("description") or "Telegram lehnt die Nachricht ab.")
    return ergebnis.get("result")


def schluessel(e) -> str:
    return geheimnis.entschluesseln(e.telegram_schluessel_verschluesselt) or ""


def chats(e) -> list[str]:
    return [c.strip() for c in e.telegram_chats.replace(";", ",").split(",") if c.strip()]


def eingerichtet(e) -> bool:
    return bool(schluessel(e) and chats(e))


def senden(e, text: str) -> int:
    """Schickt ``text`` an alle eingestellten Chats; Ergebnis: Zahl der erreichten Chats."""
    s, erreicht = schluessel(e), 0
    for chat in chats(e):
        _aufruf(s, "sendMessage", {"chat_id": chat, "text": text,
                                   "disable_web_page_preview": True})  # fmt: skip
        erreicht += 1
    return erreicht


def gefundene_chats(e) -> list[tuple[str, str]]:
    """Chats, die dem Bot zuletzt geschrieben haben (z. B. „/start“): [(Chat-ID, Name)]."""
    gefunden = {}
    for u in _aufruf(schluessel(e), "getUpdates") or []:
        chat = (u.get("message") or u.get("my_chat_member") or {}).get("chat") or {}
        if "id" in chat:
            name = chat.get("title") or " ".join(
                x for x in (chat.get("first_name"), chat.get("last_name")) if x
            )
            gefunden[str(chat["id"])] = name or chat.get("username") or "ohne Namen"
    return list(gefunden.items())


def benachrichtigen(e, text: str) -> None:
    """Für den Ausfall: Fehler nur ins Protokoll, der Ausfall steht trotzdem im Plan."""
    if not eingerichtet(e):
        return
    try:
        senden(e, text)
    except TelegramFehler as fehler:
        log.warning("Fahrdienst: Telegram nicht gesendet: %s", fehler)
