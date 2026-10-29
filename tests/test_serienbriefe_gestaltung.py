"""Gestaltete Serienbrief-Vorlagen (ADR 0088). Alle Daten sind erfunden."""

import datetime as dt
import io
from decimal import Decimal
from importlib import import_module

import pytest
from django.apps import apps
from django.core import mail as postfach
from django.core.files.base import ContentFile
from django.urls import reverse
from PIL import Image
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.platypus import Paragraph, Table

from apps.adressen.models import Adresse, AdressKategorie
from apps.core.models import MailEinstellungen, TafelEinstellungen
from apps.serienbriefe import empfaenger as emp
from apps.serienbriefe import gestaltung
from apps.serienbriefe.models import Versand, Vorlage
from apps.spenden.models import Spende

pytestmark = pytest.mark.django_db
JAHR = dt.date.today().year
GESTALTET = (
    '<h2 style="text-align: center;">Einladung</h2><p>{anrede}</p>'
    '<p>Bitte <b>pünktlich</b> sein, <span style="color: rgb(193, 18, 31);">wichtig</span> und '
    '<span style="font-size: x-large;">groß</span>.</p>'
    "<ul><li>Kaffee</li><li>Kuchen</li></ul><ol><li>Begrüßung</li></ol>"
    '<div class="kasten" style="background-color: #fdf3d8"><p>Kastentext</p></div>'
    '<p style="text-align: right;">Gruß<br>{tafel}</p>'
)


@pytest.fixture
def erika():
    a = Adresse.objects.create(art="person", anrede="Frau", vorname="Erika", nachname="Muster",
                               strasse="Weg 1", plz="12345", ort="Musterstadt",
                               email="erika@example.org", einwilligung_post=dt.date(2026, 1, 1),
                               einwilligung_email=dt.date(2026, 1, 1))  # fmt: skip
    a.kategorien.add(AdressKategorie.objects.get(name="Spender"))
    Spende.objects.create(adresse=a, datum=dt.date(JAHR, 2, 1), betrag=Decimal("150"))
    return a


def _bild(farbe) -> bytes:
    """Einfarbiges Logo (im unkomprimierten PDF ohne Zeichen, die wie Text-Escapes aussehen)."""
    puffer = io.BytesIO()
    Image.new("RGB", (60, 20), farbe).save(puffer, "PNG")
    return puffer.getvalue()


def _absenden(client, vorlage, **mehr):
    daten = {"vorlage": vorlage.pk, "quelle": "spender", "versandart": "brief", "jahr": JAHR,
             "nur_einwilligung": "on"} | mehr  # fmt: skip
    return client.post(reverse("serienbriefe:erstellen"), daten)


def test_alter_text_wird_zu_absaetzen():
    assert gestaltung.als_html("{anrede}\n\nZeile 1\nZeile <2>\n\n\n") == (
        "<p>{anrede}</p><p>Zeile 1<br>Zeile &lt;2&gt;</p>"
    )
    assert gestaltung.als_html("<p>schon HTML</p>") == "<p>schon HTML</p>"


def test_speichern_bereinigt_und_macht_felder_zu_platzhaltern():
    html = gestaltung.speichern(
        '<p onclick="alert(1)">Hallo <span class="platzhalter" contenteditable="false" '
        'data-platzhalter="anrede">Briefanrede</span><script>alert(2)</script></p>'
        '<a href="javascript:alert(3)">x</a>'
    )
    assert "<p>Hallo {anrede}</p>" in html
    assert "onclick" not in html and "script" not in html and "javascript" not in html


def test_einsetzen_maskiert_werte():
    html = gestaltung.einsetzen(
        "<p>{anrede} {unbekannt}</p>", {"anrede": '<img src=x onerror="alert(1)"> & Co'}
    )
    assert html == '<p>&lt;img src=x onerror="alert(1)"&gt; &amp; Co {unbekannt}</p>'


def test_html_wird_zu_gestalteten_bausteinen():
    teile = gestaltung.flowables(gestaltung.einsetzen(GESTALTET, {"anrede": "Hallo", "tafel": "T"}),
                                 400)  # fmt: skip
    absaetze = [t for t in teile if isinstance(t, Paragraph)]
    ueberschrift = absaetze[0]
    assert ueberschrift.style.alignment == TA_CENTER
    assert ueberschrift.style.fontName == "Helvetica-Bold"
    text = absaetze[2].text
    assert "<b>pünktlich</b>" in text and 'color="#c1121f"' in text and 'size="15.8"' in text
    assert [a.bulletText for a in absaetze if a.bulletText] == ["•", "•", "1."]
    kasten = next(t for t in teile if isinstance(t, Table))
    assert "Kastentext" in kasten._cellvalues[0][0][0].text
    assert absaetze[-1].style.alignment == TA_RIGHT and "<br/>" in absaetze[-1].text


def test_unbekanntes_und_kaputtes_wird_text():
    html = ("<p>a<table><tr><td>Zelle</td><td>B</td></tr></table>"
            "<blockquote>Zitat</blockquote><hr><font>alt</font></p>")  # fmt: skip
    teile = gestaltung.flowables(html, 400)
    texte = " ".join(t.text for t in teile if isinstance(t, Paragraph))
    assert "Zelle" in texte and "Zitat" in texte and "alt" in texte
    assert gestaltung.farbe("rgba(0, 0, 0, 0)") is None and gestaltung.farbe("#abc") == "#aabbcc"
    assert gestaltung.farbe("red") == "#ff0000" and gestaltung.farbe("url(x)") is None


def test_pdf_mit_gestaltung_fusszeile_und_logo(admin_client, erika, pdf_text):
    tafel = TafelEinstellungen.laden()
    tafel.name, tafel.telefon = "Tafel Musterstadt", "01234 5678"
    tafel.logo.save("logo.png", ContentFile(_bild((232, 113, 10))), save=True)
    v = Vorlage.objects.create(name="Gestaltet", betreff="Einladung {jahr}", text=GESTALTET,
                               fusszeile="<p>Bank: Musterbank</p>")  # fmt: skip
    text = pdf_text(_absenden(admin_client, v, schritt="pdf"))
    assert f"Einladung {JAHR}" in text and "Sehr geehrte Frau Muster," in text
    assert "Kastentext" in text and "Kuchen" in text and "Bank: Musterbank" in text
    assert "01234 5678" in text  # Briefkopf
    assert Versand.objects.get().anzahl == 1
    v.briefkopf = False
    v.save()
    ohne = pdf_text(_absenden(admin_client, v, schritt="pdf"))
    assert "01234 5678" not in ohne and "Kastentext" in ohne


def test_alte_textvorlage_im_pdf(admin_client, erika, pdf_text):
    v = Vorlage.objects.create(name="Alt", betreff="Hallo", text="{anrede}\n\nErster Absatz.")
    text = pdf_text(_absenden(admin_client, v, schritt="pdf"))
    assert "Sehr geehrte Frau Muster," in text and "Erster Absatz." in text
    vorschau = _absenden(admin_client, v).content.decode()
    assert "<p>Sehr geehrte Frau Muster,</p>" in vorschau


def test_migration_wandelt_text_um_und_zurueck():
    migration = import_module("apps.serienbriefe.migrations.0003_gestaltung")
    Vorlage.objects.all().delete()
    v = Vorlage.objects.create(name="Alt", betreff="x", text="{anrede}\n\nA & B\nC")
    Vorlage.objects.create(name="Neu", betreff="x", text="<p>schon <b>HTML</b></p>")
    migration.in_absaetze(apps, None)
    v.refresh_from_db()
    assert v.text == "<p>{anrede}</p><p>A &amp; B<br>C</p>"
    assert Vorlage.objects.get(name="Neu").text == "<p>schon <b>HTML</b></p>"
    migration.als_text(apps, None)
    v.refresh_from_db()
    assert v.text == "{anrede}\n\nA & B\nC"


def test_mitgelieferte_vorlagen_sind_absaetze():
    v = Vorlage.objects.get(name="Dank für Spenden")
    assert v.text.startswith("<p>{anrede}</p><p>im Jahr {jahr}")


def test_bearbeiten_mit_editor_und_karten(admin_client):
    v = Vorlage.objects.create(name="Alt", betreff="Hallo", text="{anrede}\n\nText")
    seite = admin_client.get(reverse("serienbriefe:vorlage", args=[v.pk])).content.decode()
    assert "&lt;p&gt;{anrede}&lt;/p&gt;" in seite and "data-editor" in seite
    assert 'data-platzhalter-karte="spendensumme"' in seite and "Briefanrede" in seite
    assert "data-platzhalter=" in seite and "Vorschau (PDF)" in seite
    admin_client.post(reverse("serienbriefe:vorlage", args=[v.pk]), {
        "name": "Alt", "betreff": "Hallo", "briefkopf": "on",
        "text": '<p onmouseover="x()"><b>Fett</b> <span data-platzhalter="vorname" '
                'class="platzhalter">Vorname</span></p>',
        "fusszeile": "<p><br></p>",
    })  # fmt: skip
    v.refresh_from_db()
    assert v.text == "<p><b>Fett</b> {vorname}</p>" and v.fusszeile == "" and v.briefkopf
    leer = {"name": "Alt", "betreff": "Hallo", "text": "<p> </p>"}
    antwort = admin_client.post(reverse("serienbriefe:vorlage", args=[v.pk]), leer)
    assert "Bitte einen Text schreiben." in antwort.content.decode()


def test_vorschau_mit_beispiel_empfaenger(admin_client, pdf_text):
    vorher = Vorlage.objects.count()
    antwort = admin_client.post(reverse("serienbriefe:vorlage_vorschau"), {
        "name": "Neu", "betreff": "Dank {jahr}", "text": "<p>{anrede}</p><p>{spendensumme}</p>",
        "fusszeile": "<p>Bank: Musterbank</p>", "briefkopf": "on",
    })  # fmt: skip
    text = pdf_text(antwort)
    assert "Sehr geehrte Frau Beispiel," in text and "150,00" in text and "Musterweg 1" in text
    assert f"Dank {JAHR}" in text and "Bank: Musterbank" in text
    assert Vorlage.objects.count() == vorher and not Versand.objects.exists()
    assert admin_client.get(reverse("serienbriefe:vorlage_vorschau")).status_code == 405


def test_email_als_html_und_klartext(admin_client, erika):
    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    Adresse.objects.filter(pk=erika.pk).update(nachname="<b>Muster</b>")
    v = Vorlage.objects.create(name="Mail", betreff="Hallo", fusszeile="<p>Bank: Musterbank</p>",
                               text="<p>{anrede}</p><ul><li><b>Punkt</b></li></ul>")  # fmt: skip
    _absenden(admin_client, v, versandart="email", quelle="adressen", schritt="senden")
    nachricht = postfach.outbox[0]
    assert "Sehr geehrte Frau <b>Muster</b>," in nachricht.body and "• Punkt" in nachricht.body
    assert "Bank: Musterbank" in nachricht.body and "<li>" not in nachricht.body
    html = nachricht.alternatives[0][0]
    assert "<li><b>Punkt</b></li>" in html and "&lt;b&gt;Muster&lt;/b&gt;" in html
    assert "Bank: Musterbank" in html


def test_karten_ohne_beitraege():
    namen = [k[1] for k in emp.karten()]
    assert "Briefanrede" in namen and "Spendensumme" in namen
    assert all(name in emp.NAMEN for name, _ in emp.PLATZHALTER)


def test_logo_unlesbar_bleibt_weg():
    from apps.serienbriefe import brief

    tafel = TafelEinstellungen.laden()
    tafel.logo.save("kaputt.png", ContentFile(b"kein Bild"), save=True)
    assert brief._logo(tafel) is None
    tafel.logo = ""
    assert brief._logo(tafel) is None
    tafel.logo.save("klein.png", ContentFile(_bild((0, 0, 0))), save=True)
    assert brief._logo(tafel) is not None
