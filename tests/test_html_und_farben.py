import pytest
from django.urls import reverse

from apps.core import html
from apps.core.farben import STANDARDFARBE, farbtoene
from apps.core.models import TafelEinstellungen


def test_bereinigen_entfernt_gefaehrliches():
    roh = (
        '<h2 style="color: red; position: fixed">Hallo</h2><script>alert(1)</script>'
        '<p onclick="x()">Text</p><a href="javascript:alert(1)">böse</a>'
        '<a href="https://tafel.example.org">gut</a><iframe src="x"></iframe>'
    )
    sauber = html.bereinigen(roh)
    assert "<script" not in sauber and "onclick" not in sauber and "javascript:" not in sauber
    assert "<iframe" not in sauber and "position" not in sauber
    assert '<h2 style="color:red">Hallo</h2>' in sauber.replace("color: red", "color:red")
    assert 'href="https://tafel.example.org"' in sauber and "noopener" in sauber


def test_kopfleiste_mit_menue_bleibt_erhalten():
    roh = ('<nav style="flex-grow: 1; text-align: right; display: flex; justify-content: '
           'space-between"><a style="color: white; margin-left: 20px; font-family: Arial" '
           'href="https://tafel.example.org/">Start</a></nav>')  # fmt: skip
    sauber = html.bereinigen(roh).replace(": ", ":")
    for teil in ("<nav", "flex-grow:1", "justify-content:space-between", "margin-left:20px",
                 "font-family:Arial"):  # fmt: skip
        assert teil in sauber, teil


def test_anzeigen_html_klartext_und_platzhalter():
    assert html.anzeigen("", "Zeile 1\nZeile 2 {tafel}", tafel="A&B") == (
        "<p>Zeile 1<br>Zeile 2 A&amp;B</p>"
    )
    eigen = "<p>Nr. <strong>{nummer}</strong> {unbekannt}</p>"
    assert html.anzeigen(eigen, "x", nummer="<b>1</b>") == (
        "<p>Nr. <strong>&lt;b&gt;1&lt;/b&gt;</strong> {unbekannt}</p>"
    )
    assert html.anzeigen("alter Text\nohne HTML", "x") == "<p>alter Text<br>ohne HTML</p>"


def test_als_text_und_css():
    assert html.als_text("<p>Guten Tag,</p><p>Nr. <b>1</b><br>Ende &amp; gut</p>") == (
        "Guten Tag,\nNr. 1\nEnde & gut"
    )
    assert html.css_bereinigen("a { color: red }</style><script>") == (
        "a { color: red }/style>script>"
    )
    assert html.css_bereinigen(None) == ""


def test_farbtoene():
    orange = farbtoene(STANDARDFARBE)
    assert orange["akzent"] == STANDARDFARBE and orange["auf_akzent"] == "#ffffff"
    assert farbtoene("#ffff00")["auf_akzent"] == "#1f2421"  # Gelb: dunkle Schrift
    assert farbtoene("kaputt") == orange
    assert orange["akzent_nacht"] == "#f2b178"  # heller Ton für Links im Nachtmodus


@pytest.mark.django_db
def test_nachtmodus_je_konto(admin_client, admin):
    """Darstellung hell/dunkel/wie das Gerät unter „Mein Konto“ (ADR 0164); Vorgabe hell."""
    konto = reverse("konten:mein_konto")
    seite = admin_client.get(konto).content.decode()
    assert "data-nacht" not in seite and "data-darstellung" not in seite
    assert "Dunkel (Nachtmodus)" in seite and "Wie das Gerät" in seite
    antwort = admin_client.post(reverse("konten:darstellung"), {"darstellung": "dunkel"})
    assert antwort.status_code == 302 and antwort.url == konto + "#darstellung"
    seite = admin_client.get(konto).content.decode()
    assert '<html lang="de" data-darstellung="dunkel" data-nacht>' in seite
    assert "js/darstellung.js" not in seite and "--akzent-nacht:" in seite
    admin_client.post(reverse("konten:darstellung"), {"darstellung": "geraet"})
    seite = admin_client.get(konto).content.decode()
    assert '<html lang="de" data-darstellung="geraet">' in seite and "js/darstellung.js" in seite
    admin_client.post(reverse("konten:darstellung"), {"darstellung": "bunt"})  # Unsinn: bleibt
    admin.refresh_from_db()
    assert admin.darstellung == "geraet"
    assert admin_client.get(reverse("konten:darstellung")).status_code == 405


@pytest.mark.django_db
def test_farbe_einstellen(admin_client):
    seite = admin_client.get(reverse("core:einstellungen")).content.decode()
    assert 'type="color"' in seite and f"--akzent: {STANDARDFARBE}" in seite
    admin_client.post(reverse("core:einstellungen"), {"name": "Tafel", "farbe": "#1565c0"})
    assert TafelEinstellungen.laden().farbe == "#1565c0"
    assert "--akzent: #1565c0" in admin_client.get(reverse("core:start")).content.decode()
    admin_client.post(reverse("core:einstellungen"), {"name": "Tafel", "farbe": "blau"})
    assert TafelEinstellungen.laden().farbe == "#1565c0"  # ungültig, nicht gespeichert
