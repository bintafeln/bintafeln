"""Grafiken frei auf der Seite einer Serienbrief-Vorlage (ADR 0166). Alle Daten und Bilder sind
erfunden; die „Unterschrift“ ist ein gezeichneter Strich auf weißem Grund."""

import datetime as dt
import io
import json

import pypdfium2 as pdfium
import pytest
from django.core import mail as postfach
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image, ImageDraw
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from apps.adressen.models import Adresse
from apps.core.models import MailEinstellungen
from apps.serienbriefe import frei, grafiken
from apps.serienbriefe.brief import briefe_pdf
from apps.serienbriefe.models import Vorlage

pytestmark = pytest.mark.django_db


def _unterschrift(name="unterschrift.png", format_="PNG"):
    """Weißes Blatt mit einem dunklen Strich in der Mitte."""
    bild = Image.new("RGB", (600, 300), "white")
    ImageDraw.Draw(bild).line([(200, 150), (400, 160)], fill=(20, 30, 90), width=12)
    puffer = io.BytesIO()
    bild.save(puffer, format_)
    return SimpleUploadedFile(name, puffer.getvalue())


def _pdf_mit_strich():
    puffer = io.BytesIO()
    c = canvas.Canvas(puffer, pagesize=A4)
    c.setLineWidth(6)
    c.line(150, 400, 350, 410)
    c.showPage()
    c.save()
    return SimpleUploadedFile("scan.pdf", puffer.getvalue())


def test_freistellen_macht_weiss_durchsichtig_und_schneidet_zu():
    g = grafiken.speichern(_unterschrift(), freistellen=True)
    assert g.bild.name.endswith(".png")
    with g.bild.open("rb") as f:
        bild = Image.open(f)
        bild.load()
    assert bild.mode == "RGBA"
    assert bild.width < 300 and bild.height < 60  # nur noch der Strich mit etwas Rand
    assert bild.getpixel((0, 0))[3] == 0  # Ecke durchsichtig
    assert bild.getpixel((bild.width // 2, bild.height // 2))[3] == 255  # Tinte deckend
    ohne = grafiken.speichern(_unterschrift())
    assert (ohne.breite, ohne.hoehe) == (600, 300)  # ohne Häkchen unverändert


def test_jpg_wird_beim_freistellen_png():
    g = grafiken.speichern(_unterschrift("scan.jpg", "JPEG"), freistellen=True)
    assert g.bild.name.endswith(".png")


def test_pdf_als_quelle():
    g = grafiken.speichern(_pdf_mit_strich(), freistellen=True)
    assert g.bild.name.endswith(".png") and g.breite < 1000
    with pytest.raises(grafiken.GrafikFehler, match="PDF"):
        grafiken.speichern(SimpleUploadedFile("kaputt.pdf", b"%PDF-1.4 kein pdf"))


def test_leeres_blatt_wird_abgelehnt():
    puffer = io.BytesIO()
    Image.new("RGB", (200, 100), "white").save(puffer, "PNG")
    with pytest.raises(grafiken.GrafikFehler, match="nichts mehr"):
        grafiken.speichern(SimpleUploadedFile("leer.png", puffer.getvalue()), freistellen=True)


def test_hochladen_mit_freistellen(admin_client):
    antwort = admin_client.post(reverse("serienbriefe:grafiken"),
                                {"datei": _unterschrift(), "freistellen": "1"})  # fmt: skip
    assert antwort.status_code == 201 and antwort.json()["hoehe"] < 60


def test_lesen_prueft_und_begrenzt():
    g = grafiken.speichern(_unterschrift(), freistellen=True)
    roh = [
        {"grafik": g.pk, "x": -5, "y": 900, "breite": 999, "seite": "erste"},
        {"grafik": g.pk + 99, "x": 10, "y": 10, "breite": 40},  # gibt es nicht
        {"grafik": str(g.pk), "x": 10},  # keine Zahl als Kennung
        {"grafik": g.pk, "x": "abc", "y": None, "breite": "nan", "seite": "quatsch"},
        "kein Eintrag",
    ]
    ergebnis = frei.lesen(json.dumps(roh))
    assert ergebnis == [
        {"grafik": g.pk, "x": 0, "y": 292, "breite": 210, "seite": "erste"},
        {"grafik": g.pk, "x": 25, "y": 200, "breite": 40, "seite": "letzte"},
    ]
    assert frei.lesen("kein json") == [] and frei.lesen({"a": 1}) == []
    assert len(frei.lesen([{"grafik": g.pk}] * 50)) == frei.MAX_ANZAHL


def _vorlage(g, **mehr):
    eintrag = {"grafik": g.pk, "x": 30, "y": 230, "breite": 40, "seite": "letzte"} | mehr
    return Vorlage.objects.create(name=f"Vorlage {Vorlage.objects.count()}", betreff="Dank",
                                  text="<p>Text</p>", freie_grafiken=[eintrag])  # fmt: skip


def _bilder_je_seite(pdf):
    doc = pdfium.PdfDocument(pdf)
    try:
        return [sum(1 for o in seite.get_objects() if o.type == pdfium.raw.FPDF_PAGEOBJ_IMAGE)
                for seite in doc]  # fmt: skip
    finally:
        doc.close()


def test_brief_zeichnet_grafik_auf_erste_oder_letzte_seite():
    g = grafiken.speichern(_unterschrift(), freistellen=True)
    lang = "".join(f"<p>Absatz {i} mit etwas Text.</p>" for i in range(80))
    letzte = _vorlage(g)
    letzte.text = lang
    pdf = briefe_pdf([(["Erika Beispiel"], "Dank", lang)], letzte)
    zaehler = _bilder_je_seite(pdf)
    assert len(zaehler) >= 2 and zaehler[-1] == 1 and sum(zaehler) == 1
    erste = _vorlage(g, seite="erste")
    zaehler = _bilder_je_seite(briefe_pdf([(["Erika Beispiel"], "Dank", lang)], erste))
    assert zaehler[0] == 1 and sum(zaehler) == 1
    # Je Brief eines Serienbriefs
    zwei = briefe_pdf([(["A"], "Dank", "<p>kurz</p>"), (["B"], "Dank", "<p>kurz</p>")], letzte)
    assert _bilder_je_seite(zwei) == [1, 1]
    # Gelöschte Grafik: die Stelle bleibt leer, der Brief geht trotzdem
    g.delete()
    assert sum(_bilder_je_seite(briefe_pdf([(["A"], "Dank", "<p>x</p>")], letzte))) == 0


def test_vorschau_bild_ohne_freie_grafiken_pdf_mit(admin_client):
    g = grafiken.speichern(_unterschrift(), freistellen=True)
    daten = {
        "name": "N",
        "betreff": "B",
        "text": "<p>Hallo</p>",
        "freie_grafiken": json.dumps([{"grafik": g.pk, "x": 30, "y": 230, "breite": 40}]),
    }
    pdf = admin_client.post(reverse("serienbriefe:vorlage_vorschau"), daten).content
    assert sum(_bilder_je_seite(pdf)) == 1
    bild = admin_client.post(reverse("serienbriefe:vorlage_bild"), daten)
    assert bild.status_code == 200 and bild["Content-Type"] == "image/png"


def test_vorlage_speichert_freie_grafiken(admin_client):
    g = grafiken.speichern(_unterschrift(), freistellen=True)
    admin_client.post(reverse("serienbriefe:vorlage_neu"), {
        "name": "Dank", "betreff": "Danke", "text": "<p>Danke</p>",
        "freie_grafiken": json.dumps([{"grafik": g.pk, "x": 12.34, "y": 250, "breite": 30,
                                       "seite": "erste"}, {"grafik": 0}]),
    })  # fmt: skip
    v = Vorlage.objects.get(name="Dank")
    assert v.freie_grafiken == [{"grafik": g.pk, "x": 12.3, "y": 250, "breite": 30,
                                 "seite": "erste"}]  # fmt: skip
    seite = admin_client.get(reverse("serienbriefe:vorlage", args=[v.pk])).content.decode()
    assert "data-brief-frei" in seite and "data-brief-frei-ebene" in seite
    assert "Grafiken frei auf der Seite" in seite


def test_mail_zeigt_freie_grafiken_unter_dem_text(admin_client):
    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    Adresse.objects.create(art="person", anrede="Frau", vorname="Erika", nachname="Muster",
                           email="erika@example.org",
                           einwilligung_email=dt.date(2026, 1, 1))  # fmt: skip
    links = grafiken.speichern(_unterschrift("a.png"), freistellen=True)
    rechts = grafiken.speichern(_unterschrift("b.png"), freistellen=True)
    v = _vorlage(rechts, x=120)
    v.freie_grafiken.append({"grafik": links.pk, "x": 30, "y": 232, "breite": 40,
                             "seite": "letzte"})  # fmt: skip
    v.save()
    admin_client.post(reverse("serienbriefe:erstellen"), {
        "vorlage": v.pk, "quelle": "adressen", "versandart": "email",
        "jahr": dt.date.today().year, "nur_einwilligung": "on", "schritt": "senden",
    })  # fmt: skip
    html = postfach.outbox[0].alternatives[0][0]
    a, b = html.index(f"cid:grafik-{links.pk}@"), html.index(f"cid:grafik-{rechts.pk}@")
    assert html.index("Text") < a < b  # unter dem Text, von links nach rechts
    assert 'width="151"' in html  # 40 mm
    assert frei.fuer_mail(Vorlage(name="ohne")) == ""
