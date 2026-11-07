"""PDF-Nachweise rendern (ADR 0107): eine kleine Vorschau fürs Anzeigen und die Seiten als Bilder
für die Ausweisprüfung. Lokal mit PDFium (pypdfium2) – kein externer Dienst.

Viele Antragstellende laden ihren Ausweis als **PDF** hoch (oft mit sehr guten Scans). Damit die
MRZ-Prüfung diese Bilder nutzt und die Oberfläche eine Vorschau zeigen kann, wird das PDF hier
lokal in Bilder umgewandelt.
"""

import io
import logging

log = logging.getLogger(__name__)


def _dokument(pdf_bytes: bytes):
    import pypdfium2 as pdfium

    return pdfium.PdfDocument(pdf_bytes)


def seiten_bilder(pdf_bytes: bytes, max_seiten: int = 3, scale: float = 3.0) -> list[bytes]:
    """Die ersten Seiten eines PDFs als PNG-Bilder (für die OCR). ``scale`` ~3 ≈ 216 dpi, damit die
    MRZ auch bei kleineren Scans lesbar bleibt. Fehler werden verschluckt (dann keine Bilder)."""
    bilder: list[bytes] = []
    try:
        pdf = _dokument(pdf_bytes)
    except Exception as fehler:  # noqa: BLE001
        log.warning("PDF konnte nicht geöffnet werden: %s", fehler)
        return bilder
    try:
        for i in range(min(len(pdf), max(1, max_seiten))):
            pil = pdf[i].render(scale=scale).to_pil().convert("RGB")
            puffer = io.BytesIO()
            pil.save(puffer, "PNG")
            bilder.append(puffer.getvalue())
    except Exception as fehler:  # noqa: BLE001
        log.warning("PDF-Seite konnte nicht gerendert werden: %s", fehler)
    finally:
        pdf.close()
    return bilder


def seiten_lazy(pdf_bytes: bytes, max_seiten: int = 8, scale: float = 3.0):
    """Wie ``seiten_bilder``, aber als Generator – rendert Seite für Seite erst beim Durchlaufen.
    So kostet das Suchen eines Ausweises in einem **mehrseitigen** PDF nur bis zu der Seite, auf der
    er gefunden wird (z. B. die eingescannte Ausweiskontrolle in einem mehrseitigen Bescheid)."""
    try:
        pdf = _dokument(pdf_bytes)
    except Exception as fehler:  # noqa: BLE001
        log.warning("PDF konnte nicht geöffnet werden: %s", fehler)
        return
    try:
        for i in range(min(len(pdf), max(1, max_seiten))):
            try:
                pil = pdf[i].render(scale=scale).to_pil().convert("RGB")
            except Exception as fehler:  # noqa: BLE001
                log.warning("PDF-Seite %s konnte nicht gerendert werden: %s", i, fehler)
                continue
            puffer = io.BytesIO()
            pil.save(puffer, "PNG")
            yield puffer.getvalue()
    finally:
        pdf.close()


def vorschau(pdf_bytes: bytes, breite: int = 480) -> bytes | None:
    """Kleine Vorschau der ersten Seite als JPEG (für die Nachweis-Kachel), auf ``breite`` skaliert.
    Liefert None, wenn das PDF nicht gerendert werden kann."""
    try:
        pdf = _dokument(pdf_bytes)
    except Exception as fehler:  # noqa: BLE001
        log.warning("PDF-Vorschau fehlgeschlagen: %s", fehler)
        return None
    try:
        if len(pdf) == 0:
            return None
        pil = pdf[0].render(scale=2.0).to_pil().convert("RGB")
        if pil.width > breite:
            hoehe = round(pil.height * breite / pil.width)
            pil = pil.resize((breite, hoehe))
        puffer = io.BytesIO()
        pil.save(puffer, "JPEG", quality=75)
        return puffer.getvalue()
    except Exception as fehler:  # noqa: BLE001
        log.warning("PDF-Vorschau fehlgeschlagen: %s", fehler)
        return None
    finally:
        pdf.close()
