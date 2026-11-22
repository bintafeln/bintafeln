"""Push-Nachrichten für „Wartezeit aufs Handy“ (ADR 0134).

Wer auf /warten/ die Benachrichtigung einschaltet, bekommt aufs Handy „Gleich sind Sie dran“, sobald
nur noch ``HandyEinstellungen.push_vorher`` Nummern vor ihm sind, und „Sie sind dran“ beim Aufruf –
auch wenn die Seite nicht offen ist. Die Technik (Web Push, Schlüssel der Tafel, Verschlüsselung)
steht in ``apps/core/push.py``; hier steht nur, wann welches Handy welche Nachricht bekommt.

Ausgelöst nach jedem „Weiter“ im Aufruf (``ablauf.weiter``) im Hintergrund, damit der Aufruf am
Schalter nicht wartet. In Tests ``_senden`` und ``_im_hintergrund`` in ``apps.core.push`` ersetzen.
"""

from apps.core import push as kern
from apps.core.push import erlaubt, oeffentlicher_schluessel  # noqa: F401 (für Ansichten)

BALD, JETZT = "bald", "jetzt"


def senden(z, titel: str, text: str) -> bool:
    """Eine Nachricht an das Handy dieses Zugangs. Meldet der Push-Dienst, dass es die Adresse
    nicht mehr gibt (abgemeldet, Browser gewechselt), wird sie vergessen."""
    status = kern.zustellen(z.push_adresse, z.push_p256dh, z.push_auth,
                            {"titel": titel, "text": text})  # fmt: skip
    if status in (404, 410):
        abbestellen(z)
    return 200 <= status < 300


def abonnieren(z, adresse: str, p256dh: str, auth: str, sprache: str) -> None:
    kern.pruefen(adresse, p256dh, auth)
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

    def in_sprache(t):
        if art == JETZT:
            return t["push_jetzt_titel"], t["push_jetzt"].format(nummer=stand.get("nummer", ""))
        return t["push_bald_titel"], t["push_bald"].format(vor=stand.get("vor", ""))

    titel, text = in_sprache(texte("de"))  # Deutsch immer, dazu die Sprache der Kunden
    if sprache and sprache != "de":
        titel2, text2 = in_sprache(texte(sprache))
        titel = titel if titel2 == titel else f"{titel} · {titel2}"
        text = text if text2 == text else f"{text}\n{text2}"
    return titel, text


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


def anstossen(stelle, datum) -> None:
    """Nach dem Speichern eines Aufrufs: Nachrichten im Hintergrund verschicken."""
    from apps.aufruf.models import HandyZugang

    if not HandyZugang.objects.exclude(push_adresse="").exists():
        return
    kern.nach_speichern(lambda: benachrichtigen(stelle, datum))
