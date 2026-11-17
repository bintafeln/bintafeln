"""Druckansicht für PDFs (ADR 0141): Tablets im Kiosk-Modus zeigen PDFs ohne Knopf zum Drucken
oder Zurückgehen. Auf solchen Geräten erscheint ein PDF deshalb als normale Seite: jede Seite
als Bild, darüber „Drucken“ (Druckdialog des Geräts), „Per E-Mail senden“, „PDF herunterladen“
und „Zurück“.

Die ``DruckansichtMiddleware`` fängt jedes PDF ab, das als Seite geöffnet wird, wenn die
Druckansicht auf dem Gerät gilt (``aktiv()``): Vorgabe für Konten einer Ausgabestelle, sonst je
Gerät unter „Mein Konto“ einschaltbar (Cookie). Gespeichert wird nichts: Die Seite enthält das
PDF selbst; zum Mailen schickt der Browser es mit einer Prüfsumme des Servers zurück, sodass nur
von bintafeln erzeugte PDFs verschickt werden.
"""

import base64
import hashlib
import io
import logging

from django.core import signing
from django.template.response import TemplateResponse

log = logging.getLogger(__name__)

COOKIE = "bintafeln_druckansicht"
COOKIE_JAHRE = 5
HOECHSTENS_SEITEN = 30  # größere PDFs (z. B. Serienbriefe) öffnen wie bisher direkt
SKALA = 2.0  # ≈ 144 dpi: scharf genug zum Drucken, klein genug für die Seite
ROH = "_pdf"  # ?_pdf=roh: das PDF selbst, ohne Druckansicht
SALZ = "bintafeln.druckansicht"


def aktiv(request) -> bool:
    """Gilt die Druckansicht für dieses Gerät? Das Cookie entscheidet; ohne Cookie gilt sie für
    Konten einer Ausgabestelle (die Tablets am Einlass)."""
    wert = request.COOKIES.get(COOKIE)
    if wert in ("1", "0"):
        return wert == "1"
    benutzer = getattr(request, "user", None)
    return bool(getattr(benutzer, "is_authenticated", False) and benutzer.stelle_id)


def cookie_setzen(request, antwort, an: bool) -> None:
    antwort.set_cookie(COOKIE, "1" if an else "0", max_age=COOKIE_JAHRE * 365 * 24 * 3600,
                       samesite="Lax", httponly=True, secure=request.is_secure())  # fmt: skip


def _pruefsumme(inhalt: bytes) -> str:
    return hashlib.sha256(inhalt).hexdigest()


def signieren(inhalt: bytes) -> str:
    return signing.Signer(salt=SALZ).sign(_pruefsumme(inhalt))


def pruefen(inhalt: bytes, signatur: str) -> bool:
    try:
        return signing.Signer(salt=SALZ).unsign(signatur) == _pruefsumme(inhalt)
    except signing.BadSignature:
        return False


def seiten(inhalt: bytes) -> list[dict] | None:
    """Die Seiten als PNG (Base64) mit Ausrichtung; ``None``, wenn das PDF zu groß ist oder sich
    nicht lesen lässt – dann öffnet es wie bisher direkt."""
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(inhalt)
    except Exception as fehler:  # noqa: BLE001
        log.warning("PDF für die Druckansicht nicht lesbar: %s", fehler)
        return None
    try:
        if len(pdf) > HOECHSTENS_SEITEN:
            return None
        ergebnis = []
        for seite in pdf:
            breite, hoehe = seite.get_size()
            puffer = io.BytesIO()
            seite.render(scale=SKALA).to_pil().convert("RGB").save(puffer, "PNG", optimize=True)
            ergebnis.append({"bild": base64.b64encode(puffer.getvalue()).decode(),
                             "quer": breite > hoehe})  # fmt: skip
        return ergebnis
    except Exception as fehler:  # noqa: BLE001
        log.warning("PDF-Seite für die Druckansicht nicht darstellbar: %s", fehler)
        return None
    finally:
        pdf.close()


def empfaenger(request) -> list[tuple[str, str]]:
    """Wohin das PDF gehen darf (Auswahl statt Freitext): die E-Mail der gewählten
    Ausgabestelle, die eigene und die der Tafel."""
    from apps.ausgabe.stelle import aktuelle
    from apps.core.models import TafelEinstellungen

    liste = []
    stelle = aktuelle(request.user)
    if stelle and stelle.email:
        liste.append((stelle.email, f"{stelle.name} ({stelle.email})"))
    if request.user.email and not request.user.stelle_id:
        liste.append((request.user.email, f"meine E-Mail ({request.user.email})"))
    tafel = TafelEinstellungen.laden()
    if tafel.email:
        liste.append((tafel.email, f"{tafel.name or 'Tafel'} ({tafel.email})"))
    gesehen, eindeutig = set(), []
    for adresse, text in liste:
        if adresse.lower() not in gesehen:
            gesehen.add(adresse.lower())
            eindeutig.append((adresse, text))
    return eindeutig


def _dateiname(antwort) -> str:
    kopf = antwort.get("Content-Disposition", "")
    if 'filename="' in kopf:
        return kopf.split('filename="', 1)[1].split('"', 1)[0] or "dokument.pdf"
    return "dokument.pdf"


def anzeigen(request, antwort):
    """Die Druckansicht statt des PDFs, oder die Antwort unverändert."""
    inhalt = b"".join(antwort.streaming_content) if antwort.streaming else antwort.content
    if antwort.streaming:  # gelesen: für den Fall, dass es unverändert weitergeht, neu setzen
        antwort.streaming_content = [inhalt]
    bilder = seiten(inhalt)
    if bilder is None:
        return antwort
    from apps.core import mail

    seite = TemplateResponse(request, "core/druckansicht.html", {
        "seiten": bilder, "dateiname": _dateiname(antwort),
        "pdf": base64.b64encode(inhalt).decode(), "signatur": signieren(inhalt),
        "empfaenger": empfaenger(request), "mail_bereit": mail.eingerichtet(),
        "quer": bool(bilder and bilder[0]["quer"]),
    })  # fmt: skip
    seite["Cache-Control"] = "no-store"
    return seite.render()


class DruckansichtMiddleware:
    """PDFs, die als Seite geöffnet werden, auf Geräten mit Druckansicht als Seite zeigen."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        methode = request.method  # Ansichten wie ``im_fenster`` ändern sie unterwegs
        antwort = self.get_response(request)
        if (
            methode == "GET"
            and antwort.status_code == 200
            and antwort.get("Content-Type", "").startswith("application/pdf")
            and not antwort.get("Content-Disposition", "").startswith("attachment")
            and request.GET.get(ROH) != "roh"
            and request.headers.get("Sec-Fetch-Dest", "document") == "document"
            and getattr(request, "user", None) is not None
            and request.user.is_authenticated
            and aktiv(request)
        ):
            return anzeigen(request, antwort)
        return antwort
