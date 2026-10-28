"""Modul Links (ADR 0057): Kacheln auf der Startseite, Rechte, Pflege, Suche."""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.core import suche
from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.links.forms import recht_auswahl
from apps.links.models import Link, LinkGruppe, adresse_pruefen

pytestmark = pytest.mark.django_db


@pytest.fixture
def modul_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["links"]
    t.save()


@pytest.fixture
def links():
    werkzeuge = LinkGruppe.objects.create(titel="Werkzeuge", reihenfolge=2)
    anzeige = LinkGruppe.objects.create(titel="Anzeigen", reihenfolge=1)
    Link.objects.create(titel="Webseite", adresse="https://example.org", symbol="🌐")
    Link.objects.create(titel="Monitor", untertitel="Wartebereich", adresse="/aufruf/",
                        gruppe=anzeige, neuer_tab=False)  # fmt: skip
    Link.objects.create(titel="Server", adresse="https://server.example.org", gruppe=werkzeuge,
                        warnung="Nur für Admins", recht="system.update")  # fmt: skip
    Link.objects.create(titel="Alt", adresse="https://alt.example.org", aktiv=False)


def test_adresse_pruefen():
    for gut in ("https://example.org/x", "http://192.0.2.1:8080/", "/kunden/"):
        adresse_pruefen(gut)
    for schlecht in ("javascript:alert(1)", "//example.org", "ftp://example.org", "example.org"):
        with pytest.raises(ValidationError):
            adresse_pruefen(schlecht)


def test_startseite_nur_mit_modul_und_recht(admin, admin_client, links, anmelden,
                                            benutzer_mit_rolle):  # fmt: skip
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert "link-kachel" not in seite  # Modul aus
    TafelEinstellungen.objects.update(module=["links"])
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert seite.index("Webseite") < seite.index("Anzeigen") < seite.index("Werkzeuge")
    assert "⚠ Nur für Admins" in seite and "link-warnung" in seite and "Alt" not in seite
    assert 'href="https://example.org" target="_blank" rel="noopener noreferrer"' in seite
    assert 'href="/aufruf/">' in seite and "server.example.org ↗" in seite
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    seite = c.get(reverse("core:start")).content.decode()
    assert "Webseite" in seite and "Monitor" in seite and "Server" not in seite
    Link.objects.all().delete()
    assert "link-bereich" not in admin_client.get(reverse("core:start")).content.decode()


def test_pflege(modul_an, admin_client):
    antwort = admin_client.post(reverse("links:gruppe_neu"), {"titel": "Anzeigen",
                                                              "reihenfolge": 1})  # fmt: skip
    assert antwort.status_code == 302
    g = LinkGruppe.objects.get()
    daten = {
        "titel": "Kiosk",
        "adresse": "/aufruf/",
        "symbol": "🖥️",
        "gruppe": g.pk,
        "recht": "kunden.liste",
        "neuer_tab": "on",
        "reihenfolge": 1,
        "aktiv": "on",
    }
    assert admin_client.post(reverse("links:link_neu"), daten).status_code == 302
    link = Link.objects.get()
    assert link.recht == "kunden.liste" and link.gruppe == g
    seite = admin_client.post(
        reverse("links:link", args=[link.pk]), daten | {"adresse": "javascript:alert(1)"}
    ).content.decode()
    assert "http:// oder https://" in seite
    seite = admin_client.get(reverse("links:liste")).content.decode()
    assert "Kiosk" in seite and "Anzeigen" in seite
    assert (
        "Gruppe „Anzeigen“ ändern"
        in admin_client.get(reverse("links:gruppe", args=[g.pk])).content.decode()
    )
    admin_client.post(reverse("links:loeschen", args=["gruppe", g.pk]))
    link.refresh_from_db()
    assert link.gruppe is None
    admin_client.post(reverse("links:loeschen", args=["link", link.pk]))
    assert not Link.objects.exists()
    assert "Noch keine Links" in admin_client.get(reverse("links:liste")).content.decode()


def test_recht_auswahl_behaelt_alten_wert():
    auswahl = recht_auswahl()
    assert auswahl[0] == ("", "alle Angemeldeten")
    codes = {c for _, gruppe in auswahl[1:] for c, _ in gruppe}
    assert "system.update" in codes
    assert ("weg.recht", "weg.recht") in recht_auswahl("weg.recht")


def test_suche_findet_links(modul_an, admin, links):
    titel = [t.titel for g in suche.suchen(admin, "l wartebereich").gruppen for t in g.treffer]
    assert titel == ["Monitor"]


def test_rechte_und_modulschalter(admin, benutzer_mit_rolle, anmelden):
    c = anmelden(Client(), benutzer_mit_rolle("berta", rollen.BUERO))
    assert c.get(reverse("links:liste")).status_code == 404
    TafelEinstellungen.objects.update(module=["links"])
    assert c.get(reverse("links:liste")).status_code == 403


def test_bild_statt_symbol(modul_an, admin_client):
    import io

    from django.core.files.uploadedfile import SimpleUploadedFile
    from PIL import Image

    puffer = io.BytesIO()
    Image.new("RGBA", (600, 400), (0, 128, 0, 0)).save(puffer, "PNG")
    bild = SimpleUploadedFile("shop.png", puffer.getvalue(), content_type="image/png")
    daten = {"titel": "Shop", "adresse": "https://example.org", "reihenfolge": 1, "aktiv": "on",
             "bild": bild}  # fmt: skip
    assert admin_client.post(reverse("links:link_neu"), daten).status_code == 302
    link = Link.objects.get()
    with Image.open(link.bild.path) as bild:
        assert bild.size == (128, 85) and bild.mode == "RGBA"  # verkleinert, transparent
    html = admin_client.get(reverse("core:start")).content.decode()
    assert f'<img class="link-bild" src="{link.bild.url}"' in html
    gross = SimpleUploadedFile("gross.png", b"x" * (2 * 1024 * 1024 + 1),
                               content_type="image/png")  # fmt: skip
    antwort = admin_client.post(reverse("links:link", args=[link.pk]), daten | {"bild": gross})
    assert "höchstens 2 MB" in antwort.content.decode()


def test_svg_wird_bereinigt(modul_an, admin_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    boese = (b'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink"'
             b' viewBox="0 0 10 10" onload="alert(1)"><script>alert(2)</script>'
             b'<circle cx="5" cy="5" r="4" fill="url(#v)" onclick="alert(3)"/>'
             b'<use xlink:href="https://boese.example/x.svg#a"/>'
             b'<rect width="2" height="2" style="fill:url(https://boese.example/)"/>'
             b'<foreignObject><p>x</p></foreignObject></svg>')  # fmt: skip
    daten = {
        "titel": "Logo",
        "adresse": "https://example.org",
        "reihenfolge": 1,
        "aktiv": "on",
        "bild": SimpleUploadedFile("logo.svg", boese, content_type="image/svg+xml"),
    }
    assert admin_client.post(reverse("links:link_neu"), daten).status_code == 302
    inhalt = Link.objects.get().bild.read().decode()
    assert 'cx="5"' in inhalt and 'fill="url(#v)"' in inhalt and "viewBox" in inhalt
    for weg in ("alert", "script", "boese.example", "foreignObject", "onload", "onclick"):
        assert weg not in inhalt, weg
    for kaputt, name in ((b"<svg><nicht zu", "a.svg"), (b"<!DOCTYPE x><svg/>", "b.svg"),
                         (b"<html/>", "c.svg"), (b"kein bild", "d.png")):  # fmt: skip
        antwort = admin_client.post(reverse("links:link_neu"), daten | {
            "bild": SimpleUploadedFile(name, kaputt)})  # fmt: skip
        assert antwort.status_code == 200, name
