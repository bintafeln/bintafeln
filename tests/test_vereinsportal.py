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


def test_spendendatum_steht_bei_tag_der_zuwendung():
    """Das Spendendatum ist der Tag der Zuwendung, nicht irgendein Datum im Beleg (z. B. das
    Ausstellungsdatum davor)."""
    a = einlesen.beleg_lesen(beleg_pdf(), ABSENDER)
    assert (a.datum, a.jahr) == (dt.date(2026, 3, 14), 2026)
    zeilen = ["Musterstadt, 05.01.2027", "Betrag in Ziffern in Buchstaben Tag der Zuwendung",
              "25,00 fünfundzwanzig 28.12.2026", "Bescheid vom 02.02.2024"]  # fmt: skip
    assert einlesen.spendendatum(zeilen) == dt.date(2026, 12, 28)
    assert einlesen.spendendatum(["Tag der Zuwendung: 03.04.2026", "01.01.2020"]) == dt.date(
        2026, 4, 3
    )
    # ohne die Angabe: das erste gültige Datum; ungültige Tage zählen nicht
    assert einlesen.spendendatum(["am 31.02.2026 oder 01.03.2026"]) == dt.date(2026, 3, 1)
    assert einlesen.spendendatum(["kein Datum"]) is None


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
    assert b.datum == dt.date(2026, 3, 14)
    assert Beleg.objects.get(belegnummer="3").im_portal_versendet
    # verschlüsselt abgelegt, lesbar nur über privatdateien
    assert privatdateien.lesen(Beleg.ORDNER, b.datei).startswith(b"%PDF")
    assert b"%PDF" not in privatdateien.pfad(Beleg.ORDNER, b.datei).read_bytes()


def test_finanzexport_zweimal_einlesen_legt_nichts_doppelt_an(export):
    einlesen.finanzexport_einlesen(export, "buero")
    export.seek(0)
    e = einlesen.finanzexport_einlesen(export, "buero")
    assert (e.neu, e.doppelt, Beleg.objects.count()) == (0, 3, 3)


def test_spendendatum_wird_fuer_alte_belege_nachgetragen(export):
    """Belege, die vor dem Spendendatum eingelesen wurden: beim nächsten Einlesen derselben
    Datei und beim Öffnen der Seite aus dem gespeicherten PDF."""
    einlesen.finanzexport_einlesen(export, "buero")
    Beleg.objects.update(datum=None, jahr=2020)
    export.seek(0)
    e = einlesen.finanzexport_einlesen(export, "buero")
    assert (e.neu, e.doppelt) == (0, 3)
    assert set(Beleg.objects.values_list("datum", "jahr")) == {(dt.date(2026, 3, 14), 2026)}
    # … und ohne die Datei: aus dem verschlüsselt gespeicherten Beleg
    Beleg.objects.update(datum=None, jahr=2020)
    kaputt = Beleg.objects.get(belegnummer="3")
    privatdateien.loeschen(Beleg.ORDNER, kaputt.datei)
    assert einlesen.daten_nachtragen() == 2
    assert Beleg.objects.filter(datum=dt.date(2026, 3, 14), jahr=2026).count() == 2
    kaputt.refresh_from_db()
    assert kaputt.datum is None and kaputt.datum_gesucht
    assert einlesen.daten_nachtragen() == 0  # nicht lesbar: kein zweiter Versuch


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
    assert text.splitlines()[0].endswith(";Spendendaten")
    zeile = "Erika Beispiel;Feldweg 2;54321 Beispieldorf;erika@example.org;2;1275,00;2;"
    assert zeile + "14.03.2026, 14.03.2026" in text


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
    # zu jedem Beleg das Spendendatum; fehlt es, steht das da
    assert "Gespendet am" in inhalt and "14.03.2026" in inhalt and "Nr. 1" in inhalt
    Beleg.objects.filter(belegnummer="1").update(datum=None, datum_gesucht=True)
    inhalt = buero.get(reverse("vereinsportal:start"), {"jahr": "2026"}).content.decode()
    assert "Datum fehlt" in inhalt
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


# --- Dankesbriefe und Sammelbescheinigungen (Schritt 2) ---------------------------------------


@pytest.fixture
def vorlage():
    from apps.serienbriefe.models import Vorlage

    return Vorlage.objects.create(
        name="Dank", betreff="Danke für Ihre Spende",
        text="{anrede}\n\nvielen Dank, {name}, für {anzahl_spenden} Spende(n) über "
             "{spendensumme}.",
    )  # fmt: skip


@pytest.fixture
def mailserver():
    from apps.core import geheimnis
    from apps.core.models import MailEinstellungen

    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()


@pytest.fixture
def spender_da():
    """Erika: 2 Belege, Otto: 1 Beleg, Anna: 1 Beleg mit E-Mail; nichts im Portal versendet."""
    anna = "Anna Probe | Ring 7 | 12345 Musterstadt"
    einlesen.finanzexport_einlesen(archiv({
        "Spendenbeleg_000001.pdf": beleg_pdf(),
        "Spendenbeleg_000002.pdf": beleg_pdf(betrag="25,00 fünfundzwanzig"),
        "Spendenbeleg_000003.pdf": beleg_pdf(spender=OTTO, betrag="10,00 zehn"),
        "Spendenbeleg_000004.pdf": beleg_pdf(spender=anna, betrag="5,00 fünf"),
    }), "buero")  # fmt: skip
    kopf = ("Vorname", "Nachname", "E-Mail", "Anrede")
    einlesen.spenderliste_einlesen(spenderliste([("Anna", "Probe", "anna@example.org", "Frau")],
                                                kopf=kopf))  # fmt: skip


def sammel_pdf(name="Sammelbescheinigung_Erika_Beispiel.pdf"):
    return SimpleUploadedFile(name, beleg_pdf(betrag="1.275,00 Sammel"), "application/pdf")


def test_zuordnen_ueber_dateiname():
    from apps.vereinsportal import briefe

    namen = ["Erika Beispiel", "Erika Beispiel Stiftung", "Otto Muster"]
    assert briefe.zuordnen("Sammelbescheinigung_Erika-Beispiel_2026.pdf", namen) == "Erika Beispiel"
    assert briefe.zuordnen("SB_erika_beispiel_stiftung.pdf", namen) == "Erika Beispiel Stiftung"
    assert briefe.zuordnen("Sammelbescheinigung_Erika.pdf", namen) == ""
    assert briefe.zuordnen("x.pdf", [""]) == ""
    assert briefe.dateiname("Ä b/c") == "Ä_b_c.pdf" and briefe.dateiname("...") == "Beleg.pdf"


def test_sammelbescheinigung_hochladen_zuordnen_ersetzen(spender_da):
    from apps.vereinsportal import briefe
    from apps.vereinsportal.models import Sammelbescheinigung

    erste = briefe.hochladen(sammel_pdf(), 2026, "buero")
    assert (erste.name, erste.such_name, str(erste)) == (
        "Erika Beispiel", "erika beispiel", "Sammelbescheinigung_Erika_Beispiel.pdf")  # fmt: skip
    offen = briefe.hochladen(sammel_pdf("scan0001.pdf"), 2026, "buero")
    assert offen.such_name == ""
    # von Hand zuordnen ersetzt die bisherige des Spenders samt Datei
    briefe.zuweisen(offen, "Erika Beispiel")
    assert list(Sammelbescheinigung.objects.values_list("dateiname", flat=True)) == ["scan0001.pdf"]
    assert privatdateien.lesen(Sammelbescheinigung.ORDNER, erste.datei) is None
    (erika,) = [s for s in auswertung.spender(2026) if s.mehrfach]
    assert erika.sammel.pk == offen.pk
    with pytest.raises(privatdateien.DateiFehler):
        briefe.hochladen(SimpleUploadedFile("x.txt", b"x", "text/plain"), 2026, "buero")


def test_auswahl_bereit_und_werte(spender_da):
    from apps.vereinsportal import briefe

    (erika,) = briefe.auswahl(2026, "mehrfach_post")
    assert not briefe.bereit(erika) and briefe.anlagen(erika) == []
    (otto,) = briefe.auswahl(2026, "einfach_post")
    assert briefe.bereit(otto)
    assert [n for n, _ in briefe.anlagen(otto)] == ["Spendenbeleg_000003.pdf"]
    e = briefe.werte(otto, 2026)
    assert e.anschrift == ["Otto Muster", "Am Markt 5", "12345 Musterstadt"]
    assert e.werte["anrede"] == "Sehr geehrte Damen und Herren," and e.werte["vorname"] == ""
    (anna,) = briefe.auswahl(2026, "einfach_mail")
    e = briefe.werte(anna, 2026)
    assert (e.email, e.werte["anrede"], e.werte["nachname"]) == (
        "anna@example.org", "Sehr geehrte Frau Probe,", "Probe")  # fmt: skip
    assert e.werte["spendensumme"] == "5,00 €"
    assert e.werte["spendendaten"] == "14.03.2026"
    # nicht mehr lesbare Datei: keine Anlage statt Fehler
    privatdateien.loeschen(Beleg.ORDNER, otto.belege[0].datei)
    assert briefe.anlagen(otto) == []


def brief_daten(vorlage, gruppe, schritt):
    return {"vorlage": vorlage.pk, "jahr": 2026, "gruppe": gruppe, "schritt": schritt}


def test_seite_briefe_druck_pdf(buero, spender_da, vorlage, pdf_text):
    from apps.vereinsportal import briefe

    url = reverse("vereinsportal:briefe")
    assert "Vorschau" in buero.get(url).content.decode()
    seite = buero.post(url, brief_daten(vorlage, "mehrfach_post", "vorschau")).content.decode()
    assert "Sammelbescheinigung fehlt" in seite and "als PDF erstellen" not in seite
    assert "1 Mehrfachspender ohne Sammelbescheinigung" in seite
    # ohne Sammelbescheinigung entsteht kein Brief
    seite = buero.post(url, brief_daten(vorlage, "mehrfach_post", "pdf")).content.decode()
    assert "Sammelbescheinigung fehlt" in seite
    briefe.hochladen(sammel_pdf(), 2026, "buero")
    seite = buero.post(url, brief_daten(vorlage, "mehrfach_post", "vorschau")).content.decode()
    assert "1 Brief als PDF erstellen" in seite
    text = pdf_text(buero.post(url, brief_daten(vorlage, "mehrfach_post", "pdf")))
    assert "Erika Beispiel" in text and "2 Spende(n)" in text and "1.275,00" in text
    erika = Beleg.objects.filter(such_name="erika beispiel")
    assert {(b.bedankt_per, b.bedankt_am is not None) for b in erika} == {("brief", True)}
    assert not Beleg.objects.filter(such_name="otto muster", bedankt_am__isnull=False).exists()
    seite = buero.post(url, brief_daten(vorlage, "mehrfach_post", "vorschau")).content.decode()
    assert "kein Dankesbrief mehr aus" in seite


def test_seite_briefe_einfachspender_mit_beleg_und_warnung(buero, spender_da, vorlage):
    from pypdf import PdfReader

    url = reverse("vereinsportal:briefe")
    antwort = buero.post(url, brief_daten(vorlage, "einfach_post", "pdf"))
    assert len(PdfReader(io.BytesIO(antwort.content)).pages) == 2  # Brief + Beleg
    # ein kaputter Beleg gibt eine Warnung, der Brief entsteht trotzdem
    Beleg.objects.filter(such_name="otto muster").update(bedankt_am=None)
    b = Beleg.objects.get(such_name="otto muster")
    b.datei = privatdateien.ablegen(Beleg.ORDNER, b"kein PDF")
    b.save()
    antwort = buero.post(url, brief_daten(vorlage, "einfach_post", "pdf"))
    assert len(PdfReader(io.BytesIO(antwort.content)).pages) == 1
    assert "ist kein lesbares PDF" in buero.get(url).content.decode()


def test_seite_briefe_per_mail(buero, spender_da, vorlage, mailserver, mailoutbox):
    url = reverse("vereinsportal:briefe")
    seite = buero.post(url, brief_daten(vorlage, "einfach_mail", "vorschau")).content.decode()
    assert "1 E-Mail senden" in seite and "anna@example.org" in seite
    # der PDF-Knopf gilt nicht für Gruppen mit E-Mail
    assert buero.post(url, brief_daten(vorlage, "einfach_mail", "pdf"))["Content-Type"] != (
        "application/pdf")  # fmt: skip
    seite = buero.post(url, brief_daten(vorlage, "einfach_mail", "senden"), follow=True)
    assert "1 Dankesbrief per E-Mail gesendet" in seite.content.decode()
    (nachricht,) = mailoutbox
    assert nachricht.to == ["anna@example.org"] and "Sehr geehrte Frau Probe" in nachricht.body
    assert nachricht.attachments[0][0] == "Spendenbeleg_000004.pdf"
    assert Beleg.objects.get(belegnummer="4").bedankt_per == "mail"
    # Senden gilt nicht für Gruppen ohne E-Mail
    buero.post(url, brief_daten(vorlage, "einfach_post", "senden"))
    assert len(mailoutbox) == 1


def test_seite_briefe_ohne_mailserver_und_mailfehler(buero, spender_da, vorlage, monkeypatch):
    from apps.core import mail

    url = reverse("vereinsportal:briefe")
    seite = buero.post(url, brief_daten(vorlage, "einfach_mail", "vorschau")).content.decode()
    assert "noch kein Mailserver eingerichtet" in seite

    def kaputt(*a, **k):
        raise mail.MailFehler("Server nicht erreichbar")

    monkeypatch.setattr(mail, "senden", kaputt)
    Beleg.objects.filter(such_name="otto muster").update(name="Anna Probe", such_name="anna probe",
                                                         jahr=2025)  # fmt: skip
    seite = buero.post(url, brief_daten(vorlage, "einfach_mail", "senden"), follow=True)
    assert "Nicht gesendet: Anna Probe: Server nicht erreichbar" in seite.content.decode()
    assert not Beleg.objects.filter(bedankt_am__isnull=False).exists()


def test_mailversand_bricht_nach_drei_fehlern_ab(buero, vorlage, monkeypatch):
    from apps.core import mail

    zeilen = []
    for i, name in enumerate(["Anna", "Berta", "Carla", "Dora"], start=1):
        Beleg.objects.create(dateiname=f"b_{i}.pdf", belegnummer=str(i), name=f"{name} Probe",
                             such_name=f"{name.lower()} probe", strasse="Ring 1",
                             plz_ort="12345 Musterstadt", jahr=2026, datei="fehlt.bin")  # fmt: skip
        zeilen.append((name, "Probe", f"{name.lower()}@example.org"))
    einlesen.spenderliste_einlesen(spenderliste(zeilen, kopf=("Vorname", "Nachname", "E-Mail")))
    versuche = []

    def kaputt(*a, **k):
        versuche.append(1)
        raise mail.MailFehler("Server nicht erreichbar")

    monkeypatch.setattr(mail, "senden", kaputt)
    buero.post(reverse("vereinsportal:briefe"), brief_daten(vorlage, "einfach_mail", "senden"))
    assert len(versuche) == 3


def test_seite_sammelbescheinigungen(buero, spender_da):
    from apps.vereinsportal.models import Sammelbescheinigung

    url = reverse("vereinsportal:sammel")
    assert "Noch ohne Sammelbescheinigung:</strong> Erika Beispiel" in (
        buero.get(url, {"jahr": 2026}).content.decode())  # fmt: skip
    antwort = buero.post(url, {"aktion": "hochladen", "jahr": 2026, "dateien": [
        sammel_pdf(), sammel_pdf("scan0001.pdf"),
        SimpleUploadedFile("falsch.txt", b"x", "text/plain")]}, follow=True)  # fmt: skip
    seite = antwort.content.decode()
    assert "1 über den Namen zugeordnet, 1 bitte von Hand zuordnen" in seite
    assert "falsch.txt" in seite and "Noch zuzuordnen" in seite
    assert "Noch ohne Sammelbescheinigung" not in seite
    offen = Sammelbescheinigung.objects.get(such_name="")
    antwort = buero.get(reverse("vereinsportal:sammel_datei", args=[offen.pk]))
    assert antwort.content.startswith(b"%PDF")
    # unbekannter Name ändert nichts, ein Mehrfachspender ersetzt dessen bisherige Datei
    buero.post(url, {"aktion": "zuordnen", "jahr": 2026, "eintrag": offen.pk, "name": "Fremd"})
    assert Sammelbescheinigung.objects.count() == 2
    antwort = buero.post(url, {"aktion": "zuordnen", "jahr": 2026, "eintrag": offen.pk,
                               "name": "Erika Beispiel"}, follow=True)  # fmt: skip
    assert "„scan0001.pdf“ Erika Beispiel zugeordnet" in antwort.content.decode()
    assert Sammelbescheinigung.objects.count() == 1
    antwort = buero.post(url, {"aktion": "loeschen", "jahr": 2026, "eintrag": offen.pk},
                         follow=True)  # fmt: skip
    assert "in den Papierkorb gelegt" in antwort.content.decode()
    assert not Sammelbescheinigung.objects.exists()
    assert buero.post(url, {"aktion": "hochladen", "jahr": 2026}).status_code == 302
    assert buero.post(url, {"aktion": "anderes", "jahr": 2026}).status_code == 302


def test_sammel_datei_nicht_mehr_lesbar(buero, spender_da):
    from apps.vereinsportal import briefe
    from apps.vereinsportal.models import Sammelbescheinigung

    eintrag = briefe.hochladen(sammel_pdf(), 2026, "buero")
    privatdateien.loeschen(Sammelbescheinigung.ORDNER, eintrag.datei)
    assert buero.get(reverse("vereinsportal:sammel_datei", args=[eintrag.pk])).status_code == 404


def test_fristen_loeschen_auch_sammelbescheinigungen(spender_da):
    from apps.vereinsportal import briefe
    from apps.vereinsportal.models import Sammelbescheinigung

    eintrag = briefe.hochladen(sammel_pdf(), 2026, "buero")
    auswertung.fristen_anwenden(dt.date(2029, 1, 1))
    assert not Sammelbescheinigung.objects.exists()
    assert privatdateien.lesen(Sammelbescheinigung.ORDNER, eintrag.datei) is None


def test_mail_steht_in_der_uebersicht(admin_client):
    seite = admin_client.get(reverse("core:mail_empfaenger")).content.decode()
    assert "Dankesbrief zu Belegen aus dem Vereinsportal" in seite


# --- Automatischer Abruf (Schritt 3, ADR 0127) ------------------------------------------------


class FalscherDienst:
    """Steht für den Dienst „abruf“: merkt sich Aufrufe und liefert vorbereitete Antworten."""

    def __init__(self, dateien=None):
        self.stand = {"stand": "frei", "schritt": "", "fehler": "", "dateien": {}, "nummer": 0}
        self.dateien = dateien or {}
        self.aufrufe = []
        self.fehler = None

    def __call__(self, pfad, daten=None, ziel=None):
        from apps.vereinsportal import abruf

        self.aufrufe.append((pfad, daten))
        if self.fehler:
            raise abruf.AbrufFehler(self.fehler)
        if pfad.startswith("/datei/"):
            ziel.write(self.dateien[pfad.removeprefix("/datei/")])
            return None
        if pfad == "/start":
            self.stand |= {"stand": "laeuft", "schritt": "Starte …"}
        elif pfad == "/code":
            self.stand |= {"stand": "laeuft", "schritt": "2FA-Code übermittelt …"}
        elif pfad == "/fertig":
            self.stand |= {"stand": "frei", "dateien": {}}
        return dict(self.stand)


@pytest.fixture
def dienst(settings, monkeypatch):
    from apps.vereinsportal import abruf

    settings.ABRUF_SCHLUESSEL = "nur-ein-erfundener-test-schluessel"
    falsch = FalscherDienst()
    monkeypatch.setattr(abruf, "_anfrage", falsch)
    return falsch


@pytest.fixture
def zugang():
    from apps.core import geheimnis

    e = PortalEinstellungen.laden()
    e.anmeldung_url = "https://portal.example.org/login"
    e.liste_url = "https://portal.example.org/liste/1"
    e.export_url = "https://portal.example.org/export"
    e.email = "buero@example.org"
    e.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    e.save()
    return e


def test_abruf_starten_schickt_auftrag(dienst, zugang):
    from apps.vereinsportal import abruf

    abruf.starten(dt.date(2026, 2, 1), dt.date(2026, 2, 4), True)
    pfad, daten = dienst.aufrufe[-1]
    assert pfad == "/start" and daten == {
        "anmeldung_url": "https://portal.example.org/login",
        "liste_url": "https://portal.example.org/liste/1",
        "export_url": "https://portal.example.org/export", "email": "buero@example.org",
        "passwort": "erfunden", "von": "01.02.2026", "bis": "04.02.2026", "mit_liste": True,
    }  # fmt: skip
    # ohne Adresse der Liste wird sie nicht geholt
    zugang.liste_url = ""
    zugang.save()
    abruf.starten(dt.date(2026, 2, 1), dt.date(2026, 2, 4), True)
    assert dienst.aufrufe[-1][1]["mit_liste"] is False


def test_abruf_starten_prueft(dienst, zugang):
    from apps.vereinsportal import abruf

    for von, bis, text in [
        (dt.date(2026, 2, 4), dt.date(2026, 2, 1), "vor dem Startdatum"),
        (dt.date(2026, 1, 1), dt.date(2026, 6, 1), "höchstens drei Monate"),
        (dt.date.today(), dt.date.today() + dt.timedelta(days=2), "in der Zukunft"),
    ]:
        with pytest.raises(abruf.AbrufFehler, match=text):
            abruf.starten(von, bis, False)
    zugang.passwort_verschluesselt = "nicht lesbar"
    zugang.save()
    with pytest.raises(abruf.AbrufFehler, match="nicht mehr lesbar"):
        abruf.starten(dt.date(2026, 2, 1), dt.date(2026, 2, 4), False)
    zugang.passwort_verschluesselt = ""
    zugang.save()
    with pytest.raises(abruf.AbrufFehler, match="zuerst Adressen und Zugangsdaten"):
        abruf.starten(dt.date(2026, 2, 1), dt.date(2026, 2, 4), False)
    assert dienst.aufrufe == []


def test_abruf_uebernehmen_liest_ein_und_raeumt_auf(dienst, export):
    from apps.vereinsportal import abruf

    assert abruf.uebernehmen("buero") == []  # nichts fertig
    dienst.stand |= {"stand": "fertig", "dateien": {"spenderliste": True, "finanzexport": True}}
    dienst.dateien = {
        "finanzexport": export.getvalue(),
        "spenderliste": spenderliste([(1, "Erika", "Beispiel", "erika@example.org", ""),
                                      (2, "Ohne", "Mail", "", "")]),
    }  # fmt: skip
    meldungen = abruf.uebernehmen("buero")
    assert meldungen == [
        (True, "Spenderliste ersetzt: 1 Spender mit E-Mail, 1 Zeilen ohne gültige E-Mail "
               "ausgelassen."),
        (True, "3 neue Belege eingelesen, 0 waren schon vorhanden, 1 ohne vollständige Anschrift "
               "ausgelassen, 1 als im Vereinsportal versendet vermerkt."),
    ]  # fmt: skip
    assert Beleg.objects.count() == 3 and Kontakt.objects.count() == 1
    assert dienst.aufrufe[-1] == ("/fertig", {}) and dienst.stand["stand"] == "frei"
    # nur der Finanzexport, ohne Zeilen ohne E-Mail
    dienst.stand |= {"stand": "fertig", "dateien": {"finanzexport": True}}
    assert len(abruf.uebernehmen("buero")) == 1
    dienst.stand |= {"stand": "fertig", "dateien": {"spenderliste": True}}
    dienst.dateien["spenderliste"] = spenderliste([(1, "Erika", "Beispiel", "e@example.org", "")])
    assert abruf.uebernehmen("buero") == [(True, "Spenderliste ersetzt: 1 Spender mit E-Mail.")]
    # eine unlesbare Spenderliste hält den Finanzexport nicht auf; danach ist der Dienst frei
    dienst.stand |= {"stand": "fertig", "dateien": {"spenderliste": True, "finanzexport": True}}
    dienst.dateien["spenderliste"] = b"keine Excel-Datei"
    kaputt, gut = abruf.uebernehmen("buero")
    assert kaputt == (False, "Spenderliste: Die Excel-Datei lässt sich nicht lesen.")
    assert gut[0] and "3 waren schon vorhanden" in gut[1] and dienst.stand["stand"] == "frei"


def test_abruf_uebernehmen_nicht_doppelt(dienst):
    from django.core.cache import cache

    from apps.vereinsportal import abruf

    dienst.stand |= {"stand": "fertig", "dateien": {}}
    cache.add(abruf.SPERRE, 1, timeout=60)
    assert abruf.uebernehmen("buero") == [] and dienst.aufrufe == []
    cache.delete(abruf.SPERRE)


def test_abruf_stand_bei_stoerung(dienst):
    from apps.vereinsportal import abruf

    dienst.fehler = "Der Abruf-Dienst ist nicht erreichbar."
    assert abruf.stand() == {"stand": "stoerung", "schritt": "", "dateien": {},
                             "fehler": "Der Abruf-Dienst ist nicht erreichbar."}  # fmt: skip


def test_anfrage_an_den_dienst(settings, monkeypatch):
    """Die echte Übertragung: Schlüssel im Kopf, JSON hin und zurück, Fehler verständlich."""
    import urllib.error

    from apps.vereinsportal import abruf

    settings.ABRUF_SCHLUESSEL, settings.ABRUF_URL = "geheim-und-erfunden", "http://abruf.invalid"
    gesehen = []

    class Antwort(io.BytesIO):
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def oeffnen(anfrage, timeout):
        gesehen.append((anfrage.full_url, anfrage.get_method(), anfrage.headers, anfrage.data))
        return Antwort(b'{"stand": "frei"}')

    monkeypatch.setattr(abruf.urllib.request, "urlopen", oeffnen)
    assert abruf._anfrage("/stand") == {"stand": "frei"}
    assert gesehen[0][:2] == ("http://abruf.invalid/stand", "GET")
    assert gesehen[0][2]["X-abruf-schluessel"] == "geheim-und-erfunden"
    abruf.code_senden(" 123456 ")
    assert gesehen[1][1] == "POST" and gesehen[1][3] == b'{"code": "123456"}'
    abruf.abbrechen()
    ziel = io.BytesIO()
    assert abruf._anfrage("/datei/finanzexport", ziel=ziel) is None
    assert ziel.getvalue() == b'{"stand": "frei"}'

    def http_fehler(inhalt):
        def oeffnen(anfrage, timeout):
            raise urllib.error.HTTPError(anfrage.full_url, 409, "x", {}, io.BytesIO(inhalt))

        return oeffnen

    monkeypatch.setattr(abruf.urllib.request, "urlopen", http_fehler(b'{"fehler": "Belegt."}'))
    with pytest.raises(abruf.AbrufFehler, match="Belegt"):
        abruf._anfrage("/start", {})
    monkeypatch.setattr(abruf.urllib.request, "urlopen", http_fehler(b"kein JSON"))
    with pytest.raises(abruf.AbrufFehler, match=r"meldet einen Fehler \(409\)"):
        abruf._anfrage("/start", {})

    def nicht_da(anfrage, timeout):
        raise OSError("keine Verbindung")

    monkeypatch.setattr(abruf.urllib.request, "urlopen", nicht_da)
    with pytest.raises(abruf.AbrufFehler, match="nicht erreichbar"):
        abruf._anfrage("/stand")


def test_seite_abruf_nicht_eingeschaltet(buero):
    seite = buero.get(reverse("vereinsportal:abruf")).content.decode()
    assert "nicht eingeschaltet" in seite and "COMPOSE_PROFILES=abruf" in seite
    assert "Automatisch aus dem Vereinsportal holen" not in (
        buero.get(reverse("vereinsportal:start")).content.decode())  # fmt: skip


def test_seite_abruf_ablauf(buero, dienst, zugang, export):
    url, stand_url = reverse("vereinsportal:abruf"), reverse("vereinsportal:abruf_stand")
    assert "Automatisch aus dem Vereinsportal holen" in (
        buero.get(reverse("vereinsportal:start")).content.decode())  # fmt: skip
    seite = buero.get(url).content.decode()
    assert "Abruf starten" in seite and "Es läuft kein Abruf" in seite
    # falscher Zeitraum: Fehler am Formular, kein Auftrag
    seite = buero.post(url, {"von": "04.02.2026", "bis": "01.02.2026"}).content.decode()
    assert "vor dem Startdatum" in seite and dienst.aufrufe[-1][0] == "/stand"
    antwort = buero.post(url, {"von": "01.02.2026", "bis": "04.02.2026", "mit_liste": "on"})
    assert antwort.status_code == 302 and dienst.aufrufe[-1][:1] == ("/start",)
    teil = buero.get(stand_url).content.decode()
    assert "Starte …" in teil and 'hx-trigger="every 2s"' in teil and "Abruf abbrechen" in teil
    dienst.stand |= {"stand": "warte_auf_code", "schritt": "Bitte den 2FA-Code eingeben"}
    teil = buero.get(stand_url).content.decode()
    assert 'name="code"' in teil and "every 2s" not in teil
    teil = buero.post(stand_url, {"aktion": "code", "code": "123456"}).content.decode()
    assert dienst.aufrufe[-2] == ("/code", {"code": "123456"}) and "2FA-Code übermittelt" in teil
    dienst.stand |= {"stand": "fertig", "dateien": {"finanzexport": True}}
    dienst.dateien = {"finanzexport": export.getvalue()}
    teil = buero.get(stand_url).content.decode()
    assert 'hx-trigger="load"' in teil and "liest sie ein" in teil
    teil = buero.post(stand_url, {"aktion": "einlesen"}).content.decode()
    assert "3 neue Belege eingelesen" in teil and "Es läuft kein Abruf" in teil
    assert Beleg.objects.count() == 3


def test_seite_abruf_fehler_abbrechen_verwerfen(buero, dienst, zugang):
    url, stand_url = reverse("vereinsportal:abruf"), reverse("vereinsportal:abruf_stand")
    dienst.stand |= {"stand": "laeuft", "schritt": "Öffne die Anmeldeseite …"}
    buero.post(stand_url, {"aktion": "abbrechen"})
    assert dienst.aufrufe[-2] == ("/abbrechen", {})
    dienst.stand |= {"stand": "fehler", "fehler": "Der Abruf wurde abgebrochen."}
    teil = buero.get(stand_url).content.decode()
    assert "Der Abruf wurde abgebrochen." in teil and "Meldung schließen" in teil
    teil = buero.post(stand_url, {"aktion": "verwerfen"}).content.decode()
    assert "Es läuft kein Abruf" in teil
    # der Dienst lehnt ab: Meldung statt Absturz
    dienst.fehler = "Es läuft schon ein Abruf."
    seite = buero.post(url, {"von": "01.02.2026", "bis": "04.02.2026"}, follow=True)
    assert "Es läuft schon ein Abruf." in seite.content.decode()
    teil = buero.post(stand_url, {"aktion": "code", "code": "1"}).content.decode()
    assert "Es läuft schon ein Abruf." in teil
    # kaputte Datei beim Einlesen
    dienst.fehler = None
    dienst.stand |= {"stand": "fertig", "dateien": {"finanzexport": True}}
    dienst.dateien = {"finanzexport": b"kein Archiv"}
    teil = buero.post(stand_url, {"aktion": "einlesen"}).content.decode()
    assert "Finanzexport: Die Datei ist kein ZIP-Archiv." in teil and "Es läuft kein Abruf" in teil
    assert buero.post(stand_url, {"aktion": "unbekannt"}).status_code == 200


def test_seite_abruf_ohne_zugangsdaten(buero, dienst):
    seite = buero.get(reverse("vereinsportal:abruf")).content.decode()
    assert "zuerst unter" in seite and "Abruf starten" not in seite


def test_einstellungen_zugangsdaten_verschluesselt(buero, dienst):
    from apps.core import geheimnis

    seite = reverse("vereinsportal:einstellungen")
    assert "noch kein Passwort gespeichert" in buero.get(seite).content.decode()
    daten = {"aufbewahrung_jahre": "2", "anmeldung_url": "https://portal.example.org/login",
             "export_url": "https://portal.example.org/export", "email": "buero@example.org",
             "passwort": "erfunden und geheim"}  # fmt: skip
    assert buero.post(seite, daten).status_code == 302
    e = PortalEinstellungen.laden()
    assert "erfunden" not in e.passwort_verschluesselt
    assert geheimnis.entschluesseln(e.passwort_verschluesselt) == "erfunden und geheim"
    assert e.abruf_eingerichtet
    inhalt = buero.get(seite).content.decode()
    assert "Ein Passwort ist gespeichert" in inhalt and "erfunden und geheim" not in inhalt
    # leer lassen behält es, http wird abgelehnt, löschen entfernt es
    buero.post(seite, daten | {"passwort": ""})
    assert PortalEinstellungen.laden().passwort_verschluesselt == e.passwort_verschluesselt
    antwort = buero.post(seite, daten | {"export_url": "http://portal.example.org/export"})
    assert "muss mit https:// beginnen" in antwort.content.decode()
    buero.post(seite, daten | {"passwort": "", "passwort_loeschen": "on"})
    assert not PortalEinstellungen.laden().abruf_eingerichtet
