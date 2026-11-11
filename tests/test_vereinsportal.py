"""Modul Spendenbelege aus dem Vereinsportal (ADR 0126). Alle Daten sind erfunden."""

import datetime as dt
import io
import zipfile
from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from apps.core import privatdateien
from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.vereinsportal import auswertung, einlesen
from apps.vereinsportal.models import Beleg, Kontakt, PortalEinstellungen

pytestmark = pytest.mark.django_db
ABSENDER = "Tafel Musterstadt e.V."


@pytest.fixture(autouse=True)
def modul_an(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path
    t = TafelEinstellungen.laden()
    t.module = ["vereinsportal"]
    t.save()


ERIKA = "Erika Beispiel | Feldweg 2 | 54321 Beispieldorf"


def beleg_pdf(spender=ERIKA, datum="14.03.2026", betrag="1.250,00 eintausendzweihundertfünfzig",
              absender=ABSENDER) -> bytes:  # fmt: skip
    puffer = io.BytesIO()
    c = canvas.Canvas(puffer)
    zeilen = ["Bestätigung über Geldzuwendungen", f"{absender} | Hauptstraße 1 | 12345 Musterstadt",
              spender, f"Tag der Zuwendung: {datum}", f"Betrag: {betrag}"]  # fmt: skip
    for i, zeile in enumerate(zeilen):
        c.drawString(60, 780 - 22 * i, zeile)
    c.save()
    return puffer.getvalue()


def uebersicht(zeilen, blatt=einlesen.BLATT, kopf=("Belegnummer", "Versendet am",
                                                    "SQ-erstellt Datum")) -> bytes:  # fmt: skip
    mappe = Workbook()
    ws = mappe.active
    ws.title = blatt
    for _ in range(einlesen.KOPFZEILE - 1):
        ws.append(["Finanzexport"])
    ws.append(list(kopf))
    for z in zeilen:
        ws.append(list(z))
    puffer = io.BytesIO()
    mappe.save(puffer)
    return puffer.getvalue()


def spenderliste(zeilen, kopf=("Nr.", "Vorname", "Nachname", "E-Mail", "immer per Post")) -> bytes:
    mappe = Workbook()
    mappe.active.append(list(kopf))
    for z in zeilen:
        mappe.active.append(list(z))
    puffer = io.BytesIO()
    mappe.save(puffer)
    return puffer.getvalue()


def archiv(dateien: dict) -> io.BytesIO:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        for name, inhalt in dateien.items():
            z.writestr(name, inhalt)
    puffer.seek(0)
    return puffer


OTTO = "Otto Muster | Am Markt 5 | 12345 Musterstadt"


@pytest.fixture
def export():
    return archiv({
        "Export/Spenden/Spendenbeleg_000001.pdf": beleg_pdf(),
        "Export/Spenden/Spendenbeleg_000002.pdf": beleg_pdf(betrag="25,00 fünfundzwanzig"),
        "Export/Spenden/Spendenbeleg_000003.pdf": beleg_pdf(spender=OTTO, betrag="10,00 zehn"),
        "Export/Spenden/Spendenbeleg_000004.pdf": beleg_pdf(spender="Nur Name"),
        "Export/Rechnungen/Rechnung_000009.pdf": beleg_pdf(),
        "Export/Finanzexport.xlsx": uebersicht([(3, dt.date(2026, 4, 1), None), (1, None, None)]),
    })  # fmt: skip


# --- Belege lesen -----------------------------------------------------------------------------


def test_beleg_lesen_spender_jahr_betrag():
    a = einlesen.beleg_lesen(beleg_pdf(), ABSENDER)
    assert (a.name, a.strasse, a.plz_ort) == ("Erika Beispiel", "Feldweg 2", "54321 Beispieldorf")
    assert (a.jahr, a.betrag) == (2026, D("1250.00"))


def test_beleg_lesen_ohne_absender_gilt_die_erste_zeile_mit_strich():
    assert einlesen.beleg_lesen(beleg_pdf()).name == "Erika Beispiel"


def test_beleg_lesen_anderer_absender_findet_nichts():
    assert einlesen.beleg_lesen(beleg_pdf(), "Anderer Verein") is None


@pytest.mark.parametrize("pdf", [
    beleg_pdf(spender="Nur Name"), beleg_pdf(spender="Name | Straße |"),
    beleg_pdf(datum="ohne"), b"kein PDF", b"",
])  # fmt: skip
def test_beleg_lesen_unvollstaendig(pdf):
    assert einlesen.beleg_lesen(pdf, ABSENDER) is None


def test_beleg_lesen_ohne_betrag_null():
    assert einlesen.beleg_lesen(beleg_pdf(betrag="unbekannt")).betrag == D("0")


def test_belegnummer_aus_dateiname():
    assert einlesen.belegnummer("Spendenbeleg_000123.PDF") == "123"
    assert einlesen.belegnummer("Spendenbeleg.pdf") == ""


def test_normal():
    assert einlesen.normal("  Erika   BEISPIEL ") == "erika beispiel"


# --- Finanzexport -----------------------------------------------------------------------------


def test_finanzexport_einlesen(export):
    e = einlesen.finanzexport_einlesen(export, "buero")
    assert (e.neu, e.doppelt, e.ohne_anschrift, e.versendet, e.mit_uebersicht) == (3, 0, 1, 1, True)
    b = Beleg.objects.get(belegnummer="2")
    assert (b.name, b.such_name, b.jahr, b.betrag) == ("Erika Beispiel", "erika beispiel", 2026,
                                                       D("25.00"))  # fmt: skip
    assert b.eingelesen_von == "buero" and not b.im_portal_versendet
    assert Beleg.objects.get(belegnummer="3").im_portal_versendet
    # verschlüsselt abgelegt, lesbar nur über privatdateien
    assert privatdateien.lesen(Beleg.ORDNER, b.datei).startswith(b"%PDF")
    assert b"%PDF" not in privatdateien.pfad(Beleg.ORDNER, b.datei).read_bytes()


def test_finanzexport_zweimal_einlesen_legt_nichts_doppelt_an(export):
    einlesen.finanzexport_einlesen(export, "buero")
    export.seek(0)
    e = einlesen.finanzexport_einlesen(export, "buero")
    assert (e.neu, e.doppelt, Beleg.objects.count()) == (0, 3, 3)


def test_finanzexport_ohne_uebersicht():
    e = einlesen.finanzexport_einlesen(
        archiv({"Spendenbeleg_000001.pdf": beleg_pdf(),
                "anderes.xlsx": uebersicht([], blatt="Konten")}), "buero")  # fmt: skip
    assert (e.neu, e.mit_uebersicht, e.versendet) == (1, False, 0)


def test_finanzexport_kein_zip():
    with pytest.raises(einlesen.EinleseFehler, match="kein ZIP"):
        einlesen.finanzexport_einlesen(io.BytesIO(b"kein Archiv"), "buero")


def test_finanzexport_zu_viele_belege(monkeypatch):
    monkeypatch.setattr(einlesen, "MAX_BELEGE", 1)
    with pytest.raises(einlesen.EinleseFehler, match="Mehr als 1"):
        einlesen.finanzexport_einlesen(
            archiv({"spenden_1.pdf": b"", "spenden_2.pdf": b""}), "buero")  # fmt: skip
    assert not Beleg.objects.exists()


def test_finanzexport_zu_grosses_pdf_wird_ausgelassen(monkeypatch):
    monkeypatch.setattr(einlesen, "MAX_PDF", 10)
    e = einlesen.finanzexport_einlesen(archiv({"Spendenbeleg_000001.pdf": beleg_pdf()}), "buero")
    assert (e.neu, e.ohne_anschrift) == (0, 1)


def test_uebersicht_allein_vermerkt_versendete(export):
    einlesen.finanzexport_einlesen(export, "buero")
    zeilen = [("2", None, "02.05.2026"), (1.0, None, None), (None, "x", None), ("A7", "x", None)]
    e = einlesen.uebersicht_einlesen(uebersicht(zeilen))
    assert e.versendet == 1
    assert Beleg.objects.get(belegnummer="2").im_portal_versendet
    assert not Beleg.objects.get(belegnummer="1").im_portal_versendet


@pytest.mark.parametrize("datei", [
    uebersicht([], blatt="Konten"), uebersicht([], kopf=("Nummer", "Versendet am")),
])  # fmt: skip
def test_uebersicht_ohne_blatt_oder_spalte(datei):
    with pytest.raises(einlesen.EinleseFehler, match="Spenden - Übersicht"):
        einlesen.uebersicht_einlesen(datei)


def test_uebersicht_kaputte_datei():
    with pytest.raises(einlesen.EinleseFehler, match="nicht lesen"):
        einlesen.uebersicht_einlesen(b"keine Excel-Datei")


# --- Spenderliste -----------------------------------------------------------------------------


def test_spenderliste_ersetzt_und_prueft():
    Kontakt.objects.create(such_name="alt", email="alt@example.org")
    anzahl, ohne = einlesen.spenderliste_einlesen(spenderliste([
        (1, "Erika", "Beispiel", "erika@example.org", None),
        (2, "Otto", "Muster", "otto@example.org", "Ja"),
        (3, "Otto", "Muster", "zweite@example.org", None),  # gleicher Name: die erste Zeile gilt
        (4, "Ohne", "Mail", "", None),
        (5, "-", None, "x@example.org", None),
        (6, None, None, None, None),
        (7, "- Firma", "Beispiel GmbH", "firma@example.org", "nein"),
    ]))  # fmt: skip
    assert (anzahl, ohne) == (3, 1)
    assert not Kontakt.objects.filter(such_name="alt").exists()
    otto = Kontakt.objects.get(such_name="otto muster")
    assert (otto.email, otto.immer_post, str(otto)) == ("otto@example.org", True, "Otto Muster")
    assert Kontakt.objects.filter(such_name="firma beispiel gmbh", immer_post=False).exists()


def test_spenderliste_ohne_spalte_immer_per_post():
    zeilen = [("Erika", "Beispiel", "erika@example.org")]
    einlesen.spenderliste_einlesen(spenderliste(zeilen, kopf=("Vorname", "Nachname", "E-Mail")))
    assert not Kontakt.objects.get().immer_post


def test_spenderliste_fehlende_spalten_und_zu_lang(monkeypatch):
    with pytest.raises(einlesen.EinleseFehler, match="Es fehlt: E-Mail"):
        einlesen.spenderliste_einlesen(spenderliste([], kopf=("Vorname", "Nachname")))
    monkeypatch.setattr(einlesen, "MAX_ZEILEN", 1)
    with pytest.raises(einlesen.EinleseFehler, match="Mehr als 1"):
        zeilen = [(1, "A", "B", "a@example.org", None), (2, "C", "D", "c@example.org", None)]
        einlesen.spenderliste_einlesen(spenderliste(zeilen))
    assert not Kontakt.objects.exists()


# --- Auswertung -------------------------------------------------------------------------------


@pytest.fixture
def eingelesen(export):
    einlesen.finanzexport_einlesen(export, "buero")
    einlesen.spenderliste_einlesen(
        spenderliste([(1, "Erika", "Beispiel", "erika@example.org", "")])
    )


def test_gruppen(eingelesen):
    liste = auswertung.spender(2026)
    # Otto hat nur einen, schon versendeten Beleg: er steht nicht mehr in der Liste
    assert [s.name for s in liste] == ["Erika Beispiel"]
    erika = liste[0]
    assert (erika.anzahl, erika.summe, erika.offen, erika.gruppe) == (2, D("1275.00"), 2,
                                                                      "mehrfach_mail")  # fmt: skip
    assert dict((k, n) for k, _, n in auswertung.zahlen(liste))["mehrfach_mail"] == 1
    assert auswertung.spender(2025) == []


def test_gruppen_immer_per_post_und_einfach(eingelesen):
    Kontakt.objects.update(immer_post=True)
    Beleg.objects.filter(belegnummer="3").update(im_portal_versendet=False)
    gruppen = {s.name: s.gruppe for s in auswertung.spender(2026)}
    assert gruppen == {"Erika Beispiel": "mehrfach_post", "Otto Muster": "einfach_post"}


def test_teilweise_versendet_bleibt_in_der_liste(eingelesen):
    Beleg.objects.filter(belegnummer="1").update(im_portal_versendet=True)
    (erika,) = auswertung.spender(2026)
    assert (erika.anzahl, erika.offen) == (2, 1)


def test_csv(eingelesen):
    text = auswertung.csv_text(auswertung.spender(2026))
    assert text.startswith("﻿Name;Straße")
    assert "Erika Beispiel;Feldweg 2;54321 Beispieldorf;erika@example.org;2;1275,00;2" in text


def test_jahre_enthaelt_aktuelles_und_vorhandene(eingelesen):
    Beleg.objects.filter(belegnummer="1").update(jahr=2019)
    assert 2019 in auswertung.jahre() and dt.date.today().year in auswertung.jahre()


def test_fristen(eingelesen):
    PortalEinstellungen.objects.update_or_create(pk=1, defaults={"aufbewahrung_jahre": 2})
    assert auswertung.fristen_anwenden(dt.date(2028, 12, 31)) == 0
    b = Beleg.objects.first()
    assert auswertung.fristen_anwenden(dt.date(2029, 1, 1)) == 3
    assert not Beleg.objects.exists() and not Kontakt.objects.exists()
    assert privatdateien.lesen(Beleg.ORDNER, b.datei) is None


def test_fristen_spenderliste_bleibt_solange_belege_da_sind(eingelesen):
    Beleg.objects.filter(belegnummer="1").update(jahr=2020)
    assert auswertung.fristen_anwenden(dt.date(2026, 6, 1)) == 1
    assert Kontakt.objects.exists()
    from apps.vereinsportal.modul import MODUL

    MODUL.fristen()  # der Hook des Moduls läuft ohne Fehler


# --- Seiten -----------------------------------------------------------------------------------


@pytest.fixture
def buero(admin, benutzer_mit_rolle, anmelden, client):
    return anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))


def hochladen(client, feld, name, inhalt):
    return client.post(reverse("vereinsportal:start"), {
        "jahr": "2026", feld: SimpleUploadedFile(name, inhalt)}, follow=True)  # fmt: skip


def test_seite_einlesen_und_liste(buero, export):
    antwort = hochladen(buero, "finanzexport", "export.zip", export.getvalue())
    assert "3 neue Belege eingelesen, 0 waren schon vorhanden" in antwort.content.decode()
    assert "1 ohne vollständige Anschrift ausgelassen" in antwort.content.decode()
    assert "1 als im Vereinsportal versendet vermerkt" in antwort.content.decode()
    antwort = hochladen(buero, "spenderliste", "liste.xlsx",
                        spenderliste([(1, "Erika", "Beispiel", "erika@example.org", ""),
                                      (2, "Ohne", "Mail", "", "")]))  # fmt: skip
    assert "Liste ersetzt: 1 Spender mit E-Mail. 1 Zeilen ohne gültige E-Mail" in (
        antwort.content.decode())  # fmt: skip
    inhalt = buero.get(reverse("vereinsportal:start"), {"jahr": "2026"}).content.decode()
    assert "Erika Beispiel" in inhalt and "erika@example.org" in inhalt
    assert "Otto Muster" not in inhalt
    leer = buero.get(reverse("vereinsportal:start"), {"jahr": "2026", "gruppe": "einfach_post"})
    assert "Keine Spender in dieser Auswahl" in leer.content.decode()
    # unbekannte Angaben fallen auf die Vorgabe zurück
    assert (
        buero.get(reverse("vereinsportal:start"), {"jahr": "x", "gruppe": "x"}).status_code == 200
    )


def test_seite_nur_excel_des_finanzexports(buero, export):
    hochladen(buero, "finanzexport", "export.zip", export.getvalue())
    antwort = hochladen(buero, "finanzexport", "Finanzexport.XLSX", uebersicht([(2, "x", None)]))
    assert "0 neue Belege eingelesen" in antwort.content.decode()
    assert Beleg.objects.get(belegnummer="2").im_portal_versendet


def test_seite_fehler(buero):
    antwort = hochladen(buero, "finanzexport", "export.zip", b"kein Archiv")
    assert "kein ZIP-Archiv" in antwort.content.decode()
    antwort = buero.post(reverse("vereinsportal:start"), {"jahr": "2026"}, follow=True)
    assert "Bitte eine Datei wählen" in antwort.content.decode()
    antwort = hochladen(buero, "finanzexport", "ohne.zip",
                        archiv({"Spendenbeleg_000001.pdf": beleg_pdf()}).getvalue())  # fmt: skip
    assert "keine Übersicht der versendeten Belege" in antwort.content.decode()


def test_beleg_ansehen_und_export(buero, eingelesen):
    b = Beleg.objects.get(belegnummer="1")
    antwort = buero.get(reverse("vereinsportal:beleg", args=[b.pk]))
    assert antwort.status_code == 200 and antwort.content.startswith(b"%PDF")
    privatdateien.loeschen(Beleg.ORDNER, b.datei)
    assert buero.get(reverse("vereinsportal:beleg", args=[b.pk])).status_code == 404
    antwort = buero.get(reverse("vereinsportal:export"), {"jahr": "2026",
                                                           "gruppe": "mehrfach_mail"})  # fmt: skip
    assert antwort["Content-Disposition"] == 'attachment; filename="spender-mehrfach_mail-2026.csv"'
    assert "Erika Beispiel" in antwort.content.decode()
    alle = buero.get(reverse("vereinsportal:export"), {"jahr": "2026", "gruppe": "x"})
    assert 'filename="spender-alle-2026.csv"' in alle["Content-Disposition"]


def test_einstellungen(buero):
    seite = reverse("vereinsportal:einstellungen")
    assert buero.get(seite).status_code == 200
    antwort = buero.post(seite, {"absender": ABSENDER, "aufbewahrung_jahre": "3"})
    assert antwort.status_code == 302
    e = PortalEinstellungen.laden()
    assert (e.absender, e.aufbewahrung_jahre) == (ABSENDER, 3)
    assert str(e) == "Einstellungen für das Vereinsportal"
    assert buero.post(seite, {"aufbewahrung_jahre": "99"}).status_code == 200  # Fehler am Feld
    assert PortalEinstellungen.laden().aufbewahrung_jahre == 3


def test_nur_mit_recht_und_modul(admin, benutzer_mit_rolle, anmelden, client):
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(reverse("vereinsportal:start")).status_code == 403
    t = TafelEinstellungen.laden()
    t.module = []
    t.save()
    assert client.get(reverse("vereinsportal:start")).status_code in (403, 404)


def test_menue_und_handbuch(buero):
    inhalt = buero.get(reverse("core:start")).content.decode()
    assert reverse("vereinsportal:start") in inhalt
    assert "Welche Dateien gebraucht werden" in buero.get(reverse("core:hilfe")).content.decode()
    assert str(Beleg(dateiname="a.pdf")) == "a.pdf"
