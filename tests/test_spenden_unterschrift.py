"""Eigene eingescannte Unterschrift auf Zuwendungsbestätigungen (ADR 0130). Alle Daten erfunden."""

import datetime as dt
import io
from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from PIL import Image
from pypdf import PdfReader

from apps.adressen.models import Adresse
from apps.core import privatdateien
from apps.konten import rollen
from apps.spenden import bestaetigung as bst
from apps.spenden import unterschrift as unterschriften
from apps.spenden.models import Ausfertigung, Spende, SpendenEinstellungen, Unterschrift

pytestmark = pytest.mark.django_db
JAHR = 2026


@pytest.fixture(autouse=True)
def ablage(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture
def einstellungen():
    e = SpendenEinstellungen.laden()
    e.koerperschaft, e.anschrift = "Tafel Musterstadt e. V.", "Marktweg 1, 12345 Musterstadt"
    e.zwecke = "mildtätiger Zwecke im Sinne des § 53 AO"
    e.finanzamt, e.steuernummer = "Musterstadt", "12/345/67890"
    e.bescheid_vom, e.veranlagungszeitraum = dt.date(2025, 3, 1), "2021 bis 2023"
    e.unterzeichnet_von, e.ort = "Gemeinsamer Text, Vorstand", "Musterstadt"
    e.save()
    return e


@pytest.fixture
def spender():
    return Adresse.objects.create(art="person", anrede="Herr", vorname="Max", nachname="Probe",
                                  strasse="Weg 2", plz="12345", ort="Musterstadt")  # fmt: skip


def bild(format="PNG", groesse=(600, 200), farbe=(20, 20, 120)) -> SimpleUploadedFile:
    puffer = io.BytesIO()
    Image.new("RGB", groesse, farbe).save(puffer, format)
    endung = {"PNG": "png", "JPEG": "jpg", "GIF": "gif"}[format]
    return SimpleUploadedFile(f"unterschrift.{endung}", puffer.getvalue(), f"image/{endung}")


def spende(adresse, tag=1, betrag="50"):
    return Spende.objects.create(adresse=adresse, datum=dt.date(JAHR, 3, tag), betrag=D(betrag))


def bilder_im_pdf(inhalt: bytes) -> int:
    return sum(len(seite.images) for seite in PdfReader(io.BytesIO(inhalt)).pages)


@pytest.fixture
def vera(admin, benutzer_mit_rolle):
    return benutzer_mit_rolle("vera", rollen.BUERO)


@pytest.fixture
def otto(admin, benutzer_mit_rolle):
    return benutzer_mit_rolle("otto", rollen.BUERO)


def text(pdf_text, inhalt: bytes) -> str:
    return pdf_text(HttpResponse(inhalt, "application/pdf"))


def test_bild_wird_geprueft_und_als_png_abgelegt(vera):
    u = unterschriften.speichern(vera, "Vera Vorstand, Vorsitzende", bild("JPEG", (3000, 900)))
    inhalt = unterschriften.bild(vera)
    gespeichert = Image.open(io.BytesIO(inhalt))
    assert gespeichert.format == "PNG" and gespeichert.width == unterschriften.MAX_BREITE
    assert str(u) == "Unterschrift von vera"
    # verschlüsselt auf der Platte: die Datei selbst ist kein PNG
    roh = privatdateien.pfad(Unterschrift.ORDNER, u.bild).read_bytes()
    assert not roh.startswith(b"\x89PNG")
    # neues Bild ersetzt das alte, ohne Bild bleibt es
    alt = u.bild
    u = unterschriften.speichern(vera, "Vera Vorstand, Vorsitzende", bild())
    assert u.bild != alt and not privatdateien.pfad(Unterschrift.ORDNER, alt).exists()
    assert unterschriften.speichern(vera, "Neue Funktion").bild == u.bild
    for falsch in (SimpleUploadedFile("x.png", b"kein Bild", "image/png"), bild("GIF")):
        with pytest.raises(unterschriften.BildFehler, match="Bild der Unterschrift"):
            unterschriften.aufbereiten(falsch)
    gross = SimpleUploadedFile("x.png", b"0" * (unterschriften.MAX_MB * 1024 * 1024 + 1))
    with pytest.raises(unterschriften.BildFehler, match="höchstens"):
        unterschriften.aufbereiten(gross)
    unterschriften.loeschen(vera)
    assert unterschriften.bild(vera) is None and not Unterschrift.objects.exists()


def test_ausstellen_setzt_nur_die_eigene_unterschrift_ein(
    einstellungen, spender, vera, otto, pdf_text
):
    unterschriften.speichern(vera, "Vera Vorstand, Vorsitzende", bild())
    spende(spender)
    # Otto hat keine Unterschrift: leere Linie für die Unterschrift von Hand, nichts gespeichert
    b = bst.geld_ausstellen(spender, JAHR, "otto", otto)
    assert not b.ausfertigungen.exists() and bilder_im_pdf(bst.pdf([b])) == 0
    assert "(Ort, Datum und Unterschrift des Zuwendungsempfängers)" in text(pdf_text, bst.pdf([b]))
    # ohne Angabe, wer unterschreibt (z. B. ältere Aufrufe), ebenfalls keine Unterschrift
    bst.stornieren(b, "otto")
    assert not bst.geld_ausstellen(spender, JAHR, "otto").ausfertigungen.exists()
    # Vera stellt aus: ihr Bild über der Linie (wie im Vordruck ohne Namen darunter); das PDF ist
    # gespeichert, wer unterschrieben hat, steht in der Ausfertigung
    anderer = Adresse.objects.create(art="person", nachname="Beispiel", strasse="Gasse 1",
                                     plz="12345", ort="Musterstadt")  # fmt: skip
    spende(anderer)
    b = bst.geld_ausstellen(anderer, JAHR, "vera", vera)
    a = b.ausfertigungen.get()
    assert a.unterzeichner == vera and a.name_funktion == "Vera Vorstand, Vorsitzende"
    assert str(a) == f"Nr. {b.nummer}, unterzeichnet von Vera Vorstand, Vorsitzende"
    inhalt = bst.pdf([b])
    assert bilder_im_pdf(inhalt) == 1
    assert bst.ausfertigung(b) == privatdateien.lesen(Ausfertigung.ORDNER, a.datei)
    assert bst.eigene_unterschrift(otto) is None and bst.eigene_unterschrift(None) is None


def test_unterschriebenes_pdf_bleibt_wie_es_war(einstellungen, spender, vera):
    """Das PDF wird gespeichert, nicht neu berechnet: Es ändert sich nicht, wenn die
    Einstellungen sich ändern oder die Unterschrift gelöscht wird."""
    unterschriften.speichern(vera, "Vera Vorstand, Vorsitzende", bild())
    spende(spender)
    b = bst.geld_ausstellen(spender, JAHR, "vera", vera)
    vorher = bst.pdf([b])
    einstellungen.steuernummer = "99/999/99999"
    einstellungen.save()
    unterschriften.loeschen(vera)
    assert bst.pdf([b]) == vorher and bilder_im_pdf(bst.pdf([b])) == 1
    # eine stornierte Bestätigung wird neu erzeugt: mit Vermerk, ohne Unterschrift
    bst.stornieren(b, "vera")
    b.refresh_from_db()
    assert bilder_im_pdf(bst.pdf([b])) == 0 and bst.ausfertigung(b) is None
    assert bst.unterschreiben(b, vera) is None


def test_andere_person_fertigt_mit_eigener_unterschrift_neu_aus(
    einstellungen, spender, vera, otto, pdf_text
):
    unterschriften.speichern(vera, "Vera Vorstand, Vorsitzende", bild())
    spende(spender)
    b = bst.geld_ausstellen(spender, JAHR, "vera", vera)
    erste = b.ausfertigungen.get()
    alt = privatdateien.lesen(Ausfertigung.ORDNER, erste.datei)
    # ohne eigene Unterschrift geht es nicht – auch nicht mit der von Vera
    with pytest.raises(bst.BestaetigungsFehler, match="eigene Unterschrift hinterlegen"):
        bst.neu_unterschreiben(b, otto)
    unterschriften.speichern(otto, "Otto Ordner, Kassenwart", bild(farbe=(120, 20, 20)))
    neu = bst.neu_unterschreiben(b, otto)
    assert neu.unterzeichner == otto and b.ausfertigungen.count() == 2
    # ab jetzt gilt Ottos Ausfertigung; Nummer und Inhalt bleiben
    assert bst.ausfertigung(b) == privatdateien.lesen(Ausfertigung.ORDNER, neu.datei) != alt
    assert f"Nr. {b.nummer}" in text(pdf_text, bst.pdf([b]))
    # Veras Ausfertigung ist unverändert noch da
    assert privatdateien.lesen(Ausfertigung.ORDNER, erste.datei) == alt
    bst.stornieren(b, "otto")
    b.refresh_from_db()
    with pytest.raises(bst.BestaetigungsFehler, match="stornierte"):
        bst.neu_unterschreiben(b, otto)


def test_mehrere_bestaetigungen_in_einem_pdf(einstellungen, spender, vera, otto):
    """Unterschriebene (gespeicherte) und von Hand zu unterschreibende Bestätigungen in einem
    PDF, in der Reihenfolge der Liste."""
    unterschriften.speichern(vera, "Vera Vorstand, Vorsitzende", bild())
    spende(spender)
    mit = bst.geld_ausstellen(spender, JAHR, "vera", vera)
    anderer = Adresse.objects.create(art="person", nachname="Beispiel", strasse="Gasse 1",
                                     plz="12345", ort="Musterstadt")  # fmt: skip
    spende(anderer)
    ohne = bst.geld_ausstellen(anderer, JAHR, "otto", otto)
    gesamt = bst.pdf([ohne, mit])
    seiten = PdfReader(io.BytesIO(gesamt)).pages
    assert len(seiten) == 2 and [len(s.images) for s in seiten] == [0, 1]


def test_seiten_nur_die_eigene_unterschrift(
    einstellungen, spender, vera, otto, recht_geben, anmelden, client
):
    recht_geben(rollen.BUERO, "spenden.bestaetigen")
    seite, bild_url = reverse("spenden:unterschrift"), reverse("spenden:unterschrift_bild")
    als_vera = anmelden(client, vera)
    assert "Nur für Ihr Konto" in als_vera.get(seite).content.decode()
    assert als_vera.get(bild_url).status_code == 404
    # ohne Bild geht es beim ersten Mal nicht; ein falsches Bild meldet den Fehler am Feld
    antwort = als_vera.post(seite, {"name_funktion": "Vera Vorstand, Vorsitzende"})
    assert "Bitte ein Bild Ihrer Unterschrift hochladen" in antwort.content.decode()
    kaputt = SimpleUploadedFile("x.png", b"kein Bild", "image/png")
    antwort = als_vera.post(seite, {"name_funktion": "Vera", "bild": kaputt})
    assert "Bitte ein Bild der Unterschrift hochladen" in antwort.content.decode()
    daten = {"name_funktion": "Vera Vorstand, Vorsitzende", "bild": bild()}
    assert als_vera.post(seite, daten).status_code == 302
    assert als_vera.get(bild_url)["Content-Type"] == "image/png"
    inhalt = als_vera.get(seite).content.decode()
    assert "Hinterlegt:" in inhalt and "R 10b.1" in inhalt
    assert (
        als_vera.post(seite, {"name_funktion": "Vera Vorstand, 1. Vorsitzende"}).status_code == 302
    )
    assert Unterschrift.objects.get().name_funktion == "Vera Vorstand, 1. Vorsitzende"
    # Otto sieht Veras Unterschrift nicht: kein Bild, keine Angaben, eigener leerer Stand
    als_otto = anmelden(Client(), otto)
    assert als_otto.get(bild_url).status_code == 404
    inhalt = als_otto.get(seite).content.decode()
    assert "Vera Vorstand" not in inhalt and "Hinterlegt:" not in inhalt
    uebersicht = als_otto.get(reverse("spenden:bestaetigungen")).content.decode()
    assert "Sie haben keine Unterschrift hinterlegt" in uebersicht
    # Vera stellt über die Seite aus; Otto fertigt später mit seiner Unterschrift neu aus
    spende(spender)
    als_vera.post(reverse("spenden:ausstellen") + f"?jahr={JAHR}", {"adresse": spender.pk})
    b = spender.bestaetigungen.get()
    assert b.ausfertigungen.get().unterzeichner == vera
    url = reverse("spenden:neu_unterschreiben", args=[b.nummer])
    uebersicht = als_otto.get(reverse("spenden:bestaetigungen") + f"?jahr={JAHR}").content.decode()
    assert url not in uebersicht  # ohne eigene Unterschrift kein Knopf
    antwort = als_otto.post(url, follow=True)
    assert "eigene Unterschrift hinterlegen" in antwort.content.decode()
    als_otto.post(seite, {"name_funktion": "Otto Ordner, Kassenwart", "bild": bild()})
    uebersicht = als_otto.get(reverse("spenden:bestaetigungen") + f"?jahr={JAHR}").content.decode()
    assert url in uebersicht and "Vera Vorstand, 1. Vorsitzende" in uebersicht
    antwort = als_otto.post(url, follow=True)
    assert "trägt jetzt Ihre Unterschrift" in antwort.content.decode()
    assert b.ausfertigungen.first().unterzeichner == otto
    # löschen entfernt nur die eigene
    assert als_otto.post(seite, {"loeschen": "1"}).status_code == 302
    assert [u.benutzer for u in Unterschrift.objects.all()] == [vera]


def test_seiten_brauchen_das_recht(vera, anmelden, client, recht_nehmen):
    recht_nehmen(rollen.BUERO, "spenden.bestaetigen")
    anmelden(client, vera)
    for name in ("unterschrift", "unterschrift_bild"):
        assert client.get(reverse(f"spenden:{name}")).status_code == 403
    assert client.post(reverse("spenden:neu_unterschreiben", args=[1])).status_code == 403


def test_auskunft_nennt_die_unterschrift_ohne_bild(vera, pdf_text):
    from apps.konten import auskunft

    assert "Unterschrift für" not in text(pdf_text, auskunft.mitarbeiter_pdf(vera))
    unterschriften.speichern(vera, "Vera Vorstand, Vorsitzende", bild())
    vera.refresh_from_db()
    assert "Vera Vorstand, Vorsitzende" in text(pdf_text, auskunft.mitarbeiter_pdf(vera))
