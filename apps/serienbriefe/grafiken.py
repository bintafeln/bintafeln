"""Grafiken in Serienbrief-Vorlagen (ADR 0138).

Hochgeladene Bilder liegen als ``Grafik`` in der Datenbank, die Datei unter MEDIA_ROOT (damit
kommt sie mit in die Datensicherung). Im Vorlagentext steht ein ``<img>`` mit der Adresse
``serienbriefe:grafik`` und der Größe als ``width`` in Prozent der Textbreite (``GROESSEN``).
Beim Drucken (``gestaltung.flowables``) und für Mails (``mail_bilder``) wird diese Adresse wieder
zur Grafik; fremde Adressen bleiben außen vor – der Server ruft nie Bilder aus dem Internet ab.
"""

import io
import re
from urllib.parse import urlparse

from django.core.files.base import ContentFile
from django.urls import Resolver404, resolve, reverse
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_MB = 8
MAX_PIXEL = 2000  # längste Seite nach dem Verkleinern: reicht für A4 in guter Qualität
PDF_DPI = 200  # erste Seite eines hochgeladenen PDFs in dieser Auflösung
GROESSEN = {"klein": "25%", "mittel": "50%", "gross": "100%"}
CID = "grafik-{pk}@bintafeln"


class GrafikFehler(ValueError):
    pass


def _aus_pdf(datei) -> Image.Image:
    """Die erste Seite eines PDFs als Bild (z. B. eine eingescannte Unterschrift)."""
    import pypdfium2 as pdfium

    try:
        pdf = pdfium.PdfDocument(datei.read())
    except pdfium.PdfiumError as fehler:
        raise GrafikFehler("Das PDF lässt sich nicht lesen.") from fehler
    try:
        if not len(pdf):
            raise GrafikFehler("Das PDF hat keine Seite.")
        seite = pdf[0]
        breite, hoehe = seite.get_size()
        skala = min(PDF_DPI / 72, MAX_PIXEL / max(breite, hoehe, 1))
        return seite.render(scale=skala).to_pil().convert("RGB")
    finally:
        pdf.close()


def _zuschneiden(bild: Image.Image) -> Image.Image:
    """Durchsichtigen Rand abschneiden, damit die Grafik nur so groß ist wie die Tinte."""
    rahmen = bild.getchannel("A").point(lambda a: 255 if a > 8 else 0).getbbox()
    if not rahmen:
        raise GrafikFehler("Auf dem Bild ist nach dem Freistellen nichts mehr zu sehen.")
    links, oben, rechts, unten = rahmen
    rand = max(2, round(max(rechts - links, unten - oben) * 0.02))
    return bild.crop((max(links - rand, 0), max(oben - rand, 0),
                      min(rechts + rand, bild.width), min(unten + rand, bild.height)))  # fmt: skip


def speichern(datei, von: str = "", freistellen: bool = False):
    """Prüft und speichert eine hochgeladene Datei (Bild oder PDF, davon die erste Seite) als
    ``Grafik``: dreht nach EXIF, verkleinert auf ``MAX_PIXEL`` und speichert neu (JPEG-Fotos als
    JPEG, alles andere als PNG) – ohne Metadaten wie Aufnahmeort oder Kamera. ``freistellen``
    macht weißes Papier durchsichtig und schneidet den leeren Rand ab (Unterschriften, ADR 0166)."""
    from apps.serienbriefe.models import Grafik

    if datei.size > MAX_MB * 1024 * 1024:
        raise GrafikFehler(f"Die Datei darf höchstens {MAX_MB} MB groß sein.")
    kopf = datei.read(5)
    datei.seek(0)
    if kopf == b"%PDF-":
        bild, foto = _aus_pdf(datei), False
    else:
        try:
            bild = Image.open(datei)
            bild.load()
        except (UnidentifiedImageError, OSError) as fehler:
            raise GrafikFehler(
                "Das ist kein Bild, das bintafeln lesen kann (PNG, JPG oder PDF)."
            ) from fehler
        foto = bild.format == "JPEG"
        bild = ImageOps.exif_transpose(bild)
    if freistellen:
        from apps.spenden.unterschrift import freistellen as weiss_weg

        bild, foto = _zuschneiden(weiss_weg(bild)), False  # PNG, damit es durchsichtig bleibt
    bild.thumbnail((MAX_PIXEL, MAX_PIXEL))
    puffer = io.BytesIO()
    if foto:  # Fotos bleiben JPEG (klein), Grafiken wie Logos PNG (scharfe Kanten, Transparenz)
        bild.convert("RGB").save(puffer, "JPEG", quality=88, optimize=True)
        endung = "jpg"
    else:
        bild.convert(
            "RGBA" if "A" in bild.getbands() or "transparency" in bild.info else "RGB"
        ).save(puffer, "PNG", optimize=True)
        endung = "png"
    name = (datei.name or "Grafik").rsplit("/", 1)[-1].rsplit(".", 1)[0][:140] or "Grafik"
    g = Grafik(name=name, breite=bild.width, hoehe=bild.height, hochgeladen_von=von)
    g.bild.save(f"grafik.{endung}", ContentFile(puffer.getvalue()), save=False)
    g.save()
    return g


def adresse(grafik) -> str:
    return reverse("serienbriefe:grafik", args=[grafik.pk])


def aus_src(src: str):
    """Die ``Grafik`` zu einer Bildadresse im Vorlagentext, sonst ``None`` (fremde Adressen)."""
    from apps.serienbriefe.models import Grafik

    pfad = urlparse(src or "")
    if pfad.scheme or pfad.netloc:
        return None
    try:
        treffer = resolve(pfad.path)
    except Resolver404:
        return None
    if treffer.view_name != "serienbriefe:grafik":
        return None
    return Grafik.objects.filter(pk=treffer.kwargs.get("pk")).first()


def anteil(breite: str | None) -> float | None:
    """``width`` eines Bildes als Anteil der Textbreite (``"50%"`` → 0,5), sonst ``None``."""
    m = re.fullmatch(r"\s*(\d{1,3}(?:\.\d+)?)\s*%\s*", breite or "")
    return min(float(m.group(1)), 100) / 100 if m else None


_IMG_SRC = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]*)(")', re.IGNORECASE)


def fuer_mail(html: str) -> tuple[str, list[tuple[str, bytes, str]]]:
    """Ersetzt die Adressen eigener Grafiken durch ``cid:``-Verweise und liefert die Bilder dazu
    für ``mail.senden(..., bilder=…)``. Fremde Bildadressen fallen weg (kein Nachladen)."""
    bilder: dict[int, tuple[str, bytes, str]] = {}

    def ersetzen(m):
        g = aus_src(m.group(2).replace("&amp;", "&"))
        if g is None:
            return m.group(1) + m.group(3)
        if g.pk not in bilder:
            with g.bild.open("rb") as f:
                inhalt = f.read()
            typ = "image/png" if g.bild.name.lower().endswith(".png") else "image/jpeg"
            bilder[g.pk] = (CID.format(pk=g.pk), inhalt, typ)
        stil = ' style="max-width:100%;height:auto"'
        return m.group(1) + "cid:" + CID.format(pk=g.pk) + m.group(3) + stil

    return _IMG_SRC.sub(ersetzen, html), list(bilder.values())
