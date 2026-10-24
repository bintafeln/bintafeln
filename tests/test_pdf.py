import datetime as dt
from decimal import Decimal as D

import pytest
from auditlog.models import LogEntry
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe.models import Buchung
from apps.core.models import TafelEinstellungen
from apps.core.pdf import Pdf, text
from apps.konten import rollen
from apps.konten.models import Dokument, DokumentKategorie, Schulung, Stammdaten
from apps.kunden.models import (
    Abholer,
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Bemerkung,
    Haushalt,
    Kundengruppe,
    Person,
    Sperre,
    Zugriff,
    Zusatzfeld,
)
from apps.personal.models import Abwesenheit, Arbeitsvertrag, Stunden, Urlaubsjahr, Zeitbuchung

pytestmark = pytest.mark.django_db


@pytest.fixture
def haushalt():
    stelle = Ausgabestelle.objects.create(name="Ausgabe Nord")
    gruppe = Kundengruppe.objects.create(
        name="Dienstag", wochentage="Di", uhrzeit=dt.time(10, 30), ausgabestelle=stelle
    )
    h = Haushalt.objects.create(
        kundennummer="T-4711", kundengruppe=gruppe, ausweis_gueltig_bis=dt.date(2027, 3, 31),
        strasse="Erfundene Gasse 1", plz="12345", ort="Musterstadt", kontostand=D("5.00"),
        zusatz={"diaet": "ja"},
    )  # fmt: skip
    Person.objects.create(
        haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
        geburtsdatum=dt.date(1980, 1, 2), zusatz={"allergie": "Nuss"},
    )  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Max", nachname="Beispiel")
    Abholer.objects.create(haushalt=h, vorname="Otto", nachname="Abholer")
    Sperre.objects.create(haushalt=h, von=dt.date(2026, 1, 1), bis=dt.date(2026, 1, 31),
                          begruendung="Testsperre")  # fmt: skip
    Bemerkung.objects.create(haushalt=h, datum=dt.date(2026, 2, 1), text="Testbemerkung")
    Ausnahme.objects.create(haushalt=h, datum=dt.date(2026, 3, 1), begruendung="Testausnahme")
    a = Abholung.objects.create(haushalt=h, datum=dt.date(2026, 10, 20), beitrag=D("2.00"),
                                uhrzeit=dt.time(10, 45), ausgabestelle=stelle)  # fmt: skip
    Abholung.objects.create(haushalt=h, datum=dt.date(2026, 10, 13))
    Buchung.objects.create(haushalt=h, kundennummer=h.kundennummer, datum=a.datum,
                           art=Buchung.Art.ABHOLUNG, zahlweise=Buchung.Zahlweise.BAR,
                           soll=D("2"), haben=D("2"), bar=D("2"), abholung=a,
                           ausgabestelle=stelle, eingetragen_von="kim")  # fmt: skip
    Zusatzfeld.objects.create(schluessel="diaet", bezeichnung="Diaet", gilt_fuer="haushalt")
    Zusatzfeld.objects.create(schluessel="allergie", bezeichnung="Allergie", gilt_fuer="person",
                              typ="text", besondere_kategorie=True)  # fmt: skip
    return h


def test_text_und_leere_angaben(pdf_text, admin):
    assert text("<b>&") == "&lt;b&gt;&amp;" and text(None) == "–" and text("a\nb") == "a<br/>b"
    doc = Pdf("Probe")
    doc.angaben([])
    doc.tabelle(["A"], [])
    doc.element(doc.inhalt[0])
    assert doc.erzeugen().startswith(b"%PDF")


# --- Auskunft Kunde ------------------------------------------------------------------------


def test_auskunft_kunde(admin_client, pdf_text, haushalt):
    e = TafelEinstellungen.laden()
    e.name, e.strasse, e.ort = "Tafel Musterstadt", "Testweg 2", "Musterstadt"
    e.save()
    from apps.kunden.models import Notiz

    Notiz.objects.create(kundennummer="T-4711", text="Testnotiz", verfasst_von="kim")
    seite = admin_client.get(reverse("kunden:haushalt", args=["T-4711"])).content.decode()
    assert "Auskunft nach Art. 15 DSGVO (PDF)" in seite and "Kundenausweis drucken" in seite
    inhalt = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["T-4711"])))
    for wort in ("Tafel Musterstadt", "Erfundene Gasse 1", "Erika", "Otto Abholer", "Testsperre",
                 "Testbemerkung", "Testausnahme", "Ausgabe Nord", "Nuss", "Diaet", "chefin",
                 "Ihre Rechte", "Testnotiz"):  # fmt: skip
        assert wort in inhalt, wort
    z = Zugriff.objects.filter(kundennummer="T-4711").order_by("-zeitpunkt").first()
    assert z.besondere_kategorie and z.benutzername == "chefin"


def test_auskunft_kunde_ohne_besondere_kategorie(admin_client, pdf_text, haushalt):
    Person.objects.update(zusatz={})
    pdf_text(admin_client.get(reverse("kunden:auskunft", args=["T-4711"])))
    assert not Zugriff.objects.get().besondere_kategorie


def test_auskunft_und_ausweis_nicht_fuer_ausgabe(client, admin, benutzer_mit_rolle, anmelden,
                                                 haushalt):  # fmt: skip
    anmelden(client, benutzer_mit_rolle("kim", rollen.AUSGABE))
    assert client.get(reverse("kunden:auskunft", args=["T-4711"])).status_code == 403
    assert client.get(reverse("kunden:ausweis", args=["T-4711"])).status_code == 403
    seite = client.get(reverse("kunden:haushalt", args=["T-4711"])).content.decode()
    assert "Kundenausweis" not in seite


# --- Kundenausweis -------------------------------------------------------------------------


def test_kundenausweis(admin_client, pdf_text, haushalt):
    antwort = admin_client.get(reverse("kunden:ausweis", args=["T-4711"]))
    assert 'filename="kundenausweis-T-4711.pdf"' in antwort["Content-Disposition"]
    assert "no-cache" in antwort["Cache-Control"]
    inhalt = pdf_text(antwort)
    for wort in ("T-4711", "Erika Beispiel", "Gruppe Dienstag", "10:30 Uhr", "31.03.2027",
                 "Kundenausweis", "Tafel"):  # fmt: skip
        assert wort in inhalt, wort


def test_kundenausweis_lange_nummer_ohne_gruppe(admin_client, pdf_text):
    Haushalt.objects.create(kundennummer="X" * 20)
    inhalt = pdf_text(admin_client.get(reverse("kunden:ausweis", args=["X" * 20])))
    assert "Gruppe" not in inhalt and "ltig bis" not in inhalt


def test_kundenausweis_mit_logo(admin_client, pdf_text, haushalt, tmp_path):
    import io

    from django.core.files.base import ContentFile
    from PIL import Image

    bild = io.BytesIO()
    Image.new("RGB", (40, 20), "green").save(bild, "PNG")
    e = TafelEinstellungen.laden()
    e.logo.save("logo.png", ContentFile(bild.getvalue()))
    assert "/Subtype /Image" in pdf_text(
        admin_client.get(reverse("kunden:ausweis", args=["T-4711"]))
    )
    e.logo.storage.delete(e.logo.name)  # Datei fehlt: Ausweis ohne Logo
    assert "/Subtype /Image" not in pdf_text(
        admin_client.get(reverse("kunden:ausweis", args=["T-4711"]))
    )


# --- Kassenabschluss -----------------------------------------------------------------------


def test_kassenabschluss_tag(admin_client, pdf_text, haushalt):
    url = reverse("ausgabe:kasse")
    seite = admin_client.get(url, {"datum": "2026-10-20"}).content.decode()
    assert "format=pdf" in seite and "Kassenabschluss drucken" in seite
    inhalt = pdf_text(admin_client.get(url, {"datum": "2026-10-20", "format": "pdf"}))
    for wort in ("Kassenabschluss", "Ausgabe Nord", "Summe", "Buchungen des Tages", "T-4711",
                 "hlt von", "Gepr"):  # fmt: skip
        assert wort in inhalt, wort


@pytest.mark.parametrize(
    ("ansicht", "wert", "titel"),
    [("monat", "2026-10", "Oktober 2026"), ("jahr", "2026", "Jahr 2026")],
)
def test_kassenbericht_monat_jahr(admin_client, pdf_text, haushalt, ansicht, wert, titel):
    stelle = Ausgabestelle.objects.get()
    schluessel = "monat" if ansicht == "monat" else "jahr"
    antwort = admin_client.get(
        reverse("ausgabe:kasse"),
        {"ansicht": ansicht, schluessel: wert, "stelle": stelle.pk, "format": "pdf"},
    )
    inhalt = pdf_text(antwort)
    assert "Kassenbericht" in inhalt and titel in inhalt and "Ausgabe Nord" in inhalt
    assert "Buchungen des Tages" not in inhalt and "T-4711" not in inhalt


def test_kassenabschluss_ausgabe_ohne_einzelbuchungen(client, admin, benutzer_mit_rolle, anmelden,
                                                      pdf_text, haushalt):  # fmt: skip
    anmelden(client, benutzer_mit_rolle("kim", rollen.AUSGABE))
    inhalt = pdf_text(
        client.get(reverse("ausgabe:kasse"), {"datum": "2026-10-19", "format": "pdf"})
    )
    assert "Keine Eintr" in inhalt and "Buchungen des Tages" not in inhalt


# --- Auskunft Mitarbeitende ----------------------------------------------------------------


@pytest.fixture
def kim(benutzer_mit_rolle):
    b = benutzer_mit_rolle("kim", rollen.FAHRER)
    b.first_name, b.last_name, b.email = "Kim", "Test", "kim@example.org"
    b.save()
    Stammdaten.objects.create(benutzer=b, strasse="Testallee 3", fs_klassen="B, C1",
                              fs_gueltig_bis=dt.date(2030, 1, 1), fs_kopie_datei="x",
                              fs_kopie_am=timezone.now())  # fmt: skip
    Schulung.objects.create(benutzer=b, thema="Hygieneschulung", datum=dt.date(2026, 5, 1))
    Dokument.objects.create(benutzer=b, kategorie=DokumentKategorie.objects.get(name="Sonstiges"),
                            titel="Testdokument", datei="d", typ="application/pdf")  # fmt: skip
    Arbeitsvertrag.objects.create(benutzer=b, beginn=dt.date(2026, 1, 1), taetigkeit="Fahrdienst",
                                  wochenstunden=D("19.5"), stundenlohn=D("14.25"))  # fmt: skip
    Abwesenheit.objects.create(benutzer=b, art="krank", von=dt.date(2026, 3, 2),
                               bis=dt.date(2026, 3, 3))  # fmt: skip
    Abwesenheit.objects.create(benutzer=b, von=dt.date(2026, 4, 7), bis=dt.date(2026, 4, 8))
    Urlaubsjahr.objects.create(benutzer=b, jahr=2026, anspruch=D("25"))
    Stunden.objects.create(benutzer=b, datum=dt.date(2026, 6, 1), stunden=D("2"),
                           bemerkung="Dienstreise")  # fmt: skip
    Zeitbuchung.objects.create(benutzer=b, beginn=timezone.now(), korrigiert_von="hr")
    return b


def test_auskunft_mitarbeiter(admin_client, pdf_text, kim):
    seite = admin_client.get(reverse("konten:mitarbeiter", args=[kim.pk])).content.decode()
    assert "Auskunft (PDF)" in seite
    inhalt = pdf_text(admin_client.get(reverse("konten:auskunft", args=[kim.pk])))
    for wort in ("Kim Test", "kim@example.org", "Fahrer", "Testallee 3", "B, C1", "01.01.2030",
                 "Kopie des F", "Hygieneschulung", "Testdokument", "Fahrdienst", "19,5",
                 "14,25", "Krankheit", "Urlaub", "25", "Dienstreise", "offen", "hr",
                 "nein"):  # fmt: skip
        assert wort in inhalt, wort
    assert LogEntry.objects.get_for_object(kim).filter(action=LogEntry.Action.ACCESS).exists()


def test_auskunft_mitarbeiter_ohne_stammdaten(admin_client, pdf_text, admin):
    inhalt = pdf_text(admin_client.get(reverse("konten:meine_auskunft")))
    assert "Keine Stammdaten gespeichert" in inhalt and "chefin" in inhalt
    assert "Meine Daten ansehen" in admin_client.get(reverse("konten:mein_konto")).content.decode()


def test_auskunft_mitarbeiter_nur_personal(client, admin, benutzer_mit_rolle, anmelden, pdf_text,
                                           kim):  # fmt: skip
    e = TafelEinstellungen.laden()
    e.buero_verwaltet_mitarbeitende = True
    e.save()
    anmelden(client, benutzer_mit_rolle("buero", rollen.BUERO))
    assert client.get(reverse("konten:auskunft", args=[kim.pk])).status_code == 403
    assert (
        "Auskunft (PDF)"
        not in client.get(reverse("konten:mitarbeiter", args=[kim.pk])).content.decode()
    )
    client.logout()
    anmelden(client, benutzer_mit_rolle("hr", rollen.PERSONAL))
    pdf_text(client.get(reverse("konten:auskunft", args=[kim.pk])))
    seite = client.get(reverse("personal:person", args=[kim.pk])).content.decode()
    assert "Auskunft (PDF)" in seite


def test_auskunft_mitarbeiter_ohne_kopie(admin_client, pdf_text, admin):
    Stammdaten.objects.create(benutzer=admin, ort="Musterstadt")
    inhalt = pdf_text(admin_client.get(reverse("konten:meine_auskunft")))
    assert "Musterstadt" in inhalt and "Kopie des F" not in inhalt
