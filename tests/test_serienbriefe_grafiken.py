"""Grafiken in Serienbrief-Vorlagen (ADR 0138). Alle Daten und Bilder sind erfunden."""

import datetime as dt
import io

import pytest
from django.core import mail as postfach
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image
from pypdf import PdfReader
from reportlab.lib.units import mm

from apps.adressen.models import Adresse
from apps.core.models import MailEinstellungen, PapierkorbEintrag
from apps.konten import rollen
from apps.serienbriefe import gestaltung, grafiken
from apps.serienbriefe.models import Grafik, Vorlage

pytestmark = pytest.mark.django_db


def _datei(name="logo.png", modus="RGB", groesse=(300, 100), format_="PNG", exif=None):
    puffer = io.BytesIO()
    bild = Image.new(modus, groesse, (232, 113, 10, 128) if modus == "RGBA" else (232, 113, 10))
    bild.save(puffer, format_, **({"exif": exif} if exif else {}))
    return SimpleUploadedFile(name, puffer.getvalue(), content_type=f"image/{format_.lower()}")


def _seiten_bilder(pdf: bytes) -> int:
    return sum(len(seite.images) for seite in PdfReader(io.BytesIO(pdf)).pages)


def test_speichern_verkleinert_und_entfernt_metadaten():
    exif = Image.Exif()
    exif[0x010F] = "Kamera Muster"  # Hersteller
    g = grafiken.speichern(_datei("foto.jpg", groesse=(4000, 1000), format_="JPEG",
                                  exif=exif.tobytes()), von="berta")  # fmt: skip
    assert (g.breite, g.hoehe) == (2000, 500) and g.name == "foto" and g.hochgeladen_von == "berta"
    with g.bild.open("rb") as f:
        gespeichert = Image.open(f)
        assert gespeichert.format == "JPEG" and not gespeichert.getexif()


def test_speichern_behaelt_transparenz_als_png():
    g = grafiken.speichern(_datei("stempel.png", modus="RGBA"))
    assert g.bild.name.endswith(".png")
    with g.bild.open("rb") as f:
        assert Image.open(f).mode == "RGBA"


def test_speichern_lehnt_anderes_ab(settings):
    with pytest.raises(grafiken.GrafikFehler, match="PNG oder JPG"):
        grafiken.speichern(SimpleUploadedFile("text.png", b"kein Bild"))
    gross = _datei()
    gross.size = (grafiken.MAX_MB + 1) * 1024 * 1024
    with pytest.raises(grafiken.GrafikFehler, match="höchstens"):
        grafiken.speichern(gross)
    assert not Grafik.objects.exists()


def test_hochladen_liste_ausliefern_und_loeschen(admin_client):
    adresse = reverse("serienbriefe:grafiken")
    antwort = admin_client.post(adresse, {"datei": _datei()})
    assert antwort.status_code == 201
    daten = antwort.json()
    assert daten["adresse"] == reverse("serienbriefe:grafik", args=[daten["id"]])
    assert [g["id"] for g in admin_client.get(adresse).json()["grafiken"]] == [daten["id"]]
    bild = admin_client.get(daten["adresse"])
    assert bild.status_code == 200 and b"".join(bild.streaming_content)[:4] == b"\x89PNG"
    fehler = admin_client.post(adresse, {"datei": SimpleUploadedFile("x.png", b"nein")})
    assert fehler.status_code == 400 and "PNG oder JPG" in fehler.json()["fehler"]
    assert admin_client.post(adresse, {}).status_code == 400
    assert admin_client.post(daten["loeschen"]).json() == {"geloescht": daten["id"]}
    assert not Grafik.objects.exists() and PapierkorbEintrag.objects.count() == 1


def test_ohne_recht_keine_grafiken(admin, client, anmelden, benutzer_mit_rolle):
    g = grafiken.speichern(_datei())
    anmelden(client, benutzer_mit_rolle("carl", rollen.AUSGABE))
    assert client.get(reverse("serienbriefe:grafik", args=[g.pk])).status_code == 403
    assert client.post(reverse("serienbriefe:grafiken"), {"datei": _datei()}).status_code == 403
    assert client.post(reverse("serienbriefe:grafik_loeschen", args=[g.pk])).status_code == 403
    assert Grafik.objects.count() == 1


def test_vorlage_speichert_grafik_im_text():
    g = grafiken.speichern(_datei())
    src = grafiken.adresse(g)
    html = f'<p style="text-align: center;"><img src="{src}" alt="Logo" width="50%"></p>'
    gespeichert = gestaltung.speichern(html)
    assert f'src="{grafiken.adresse(g)}"' in gespeichert and 'width="50%"' in gespeichert


def test_aus_src_nur_eigene_grafiken():
    g = grafiken.speichern(_datei())
    assert grafiken.aus_src(grafiken.adresse(g)) == g
    assert grafiken.aus_src(f"https://example.org{grafiken.adresse(g)}") is None
    assert grafiken.aus_src("/serienbriefe/vorlagen/") is None
    assert grafiken.aus_src("/gibt/es/nicht/") is None
    assert grafiken.aus_src(reverse("serienbriefe:grafik", args=[g.pk + 99])) is None
    assert grafiken.anteil("50%") == 0.5 and grafiken.anteil("300") is None


def test_pdf_zeigt_grafik_in_breite_und_ausrichtung():
    g = grafiken.speichern(_datei(groesse=(400, 100)))
    src = grafiken.adresse(g)
    teile = gestaltung.flowables(
        f'<p>Oben</p><p style="text-align: center;"><img src="{src}" width="50%"></p>'
        f'<p><img src="{src}"></p><p><img src="https://example.org/fremd.png"></p>', 160 * mm,
    )  # fmt: skip
    bilder = [t for t in teile if type(t).__name__ == "Image"]
    assert len(bilder) == 2  # fremde Adresse wird nie abgerufen
    assert bilder[0].drawWidth == pytest.approx(80 * mm) and bilder[0].hAlign == "CENTER"
    assert bilder[0].drawHeight == pytest.approx(20 * mm)
    assert bilder[1].drawWidth == pytest.approx(300)  # ohne Größe: 400 px × 0,75 pt
    hoch = grafiken.speichern(_datei(groesse=(100, 1000)))
    [lang] = gestaltung.flowables(f'<p><img src="{grafiken.adresse(hoch)}" width="100%"></p>',
                                  160 * mm)  # fmt: skip
    assert lang.drawHeight == pytest.approx(gestaltung.MAX_BILDHOEHE)


def test_vorschau_pdf_enthaelt_grafik(admin_client):
    g = grafiken.speichern(_datei())
    text = f'<p>Hallo</p><p><img src="{grafiken.adresse(g)}" width="25%"></p>'
    antwort = admin_client.post(reverse("serienbriefe:vorlage_vorschau"),
                                {"name": "N", "betreff": "B", "text": text})  # fmt: skip
    assert _seiten_bilder(antwort.content) >= 1
    ohne = admin_client.post(reverse("serienbriefe:vorlage_vorschau"),
                             {"name": "N", "betreff": "B", "text": "<p>Hallo</p>"})  # fmt: skip
    assert _seiten_bilder(antwort.content) > _seiten_bilder(ohne.content)


def test_mail_bettet_grafik_im_text_ein(admin_client):
    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    Adresse.objects.create(art="person", anrede="Frau", vorname="Erika", nachname="Muster",
                           email="erika@example.org",
                           einwilligung_email=dt.date(2026, 1, 1))  # fmt: skip
    g = grafiken.speichern(_datei())
    text = (f'<p>{{anrede}}</p><p><img src="{grafiken.adresse(g)}" width="50%">'
            '<img src="https://example.org/fremd.png"></p>')  # fmt: skip
    v = Vorlage.objects.create(name="Mit Bild", betreff="Hallo", text=text)
    admin_client.post(reverse("serienbriefe:erstellen"), {
        "vorlage": v.pk, "quelle": "adressen", "versandart": "email",
        "jahr": dt.date.today().year, "nur_einwilligung": "on", "schritt": "senden",
    })  # fmt: skip
    nachricht = postfach.outbox[0]
    html = nachricht.alternatives[0][0]
    assert f'src="cid:grafik-{g.pk}@bintafeln"' in html and "example.org/fremd.png" not in html
    assert not nachricht.attachments  # kein Anhang: das Bild steht im Text
    roh = nachricht.message()
    assert roh.get_content_type() == "multipart/related"
    teile = {t.get_content_type(): t for t in roh.walk()}
    assert "multipart/alternative" in teile
    assert teile["image/png"]["Content-ID"] == f"<grafik-{g.pk}@bintafeln>"
    assert teile["image/png"].get_content_disposition() == "inline"


def test_mail_mit_bild_und_pdf_anhang():
    """Dankesbriefe: eingebettetes Bild im Text und daneben ein PDF als Anhang."""
    from apps.core import mail

    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    mail.senden("Dank", "Text", ["erika@example.org"], html='<img src="cid:b@x">',
                anhaenge=[("beleg.pdf", b"%PDF-1.4", "application/pdf")],
                bilder=[("b@x", b"\x89PNG", "image/png")])  # fmt: skip
    roh = postfach.outbox[0].message()
    assert roh.get_content_type() == "multipart/mixed"
    arten = [t.get_content_type() for t in roh.walk()]
    assert arten.index("multipart/related") < arten.index("image/png")
    assert "application/pdf" in arten
