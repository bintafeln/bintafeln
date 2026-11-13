"""Modul Spendenbelege aus dem Vereinsportal (ADR 0126–0128). Alle Daten sind erfunden."""

import datetime as dt
import io
import zipfile
from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from apps.adressen.models import Adresse
from apps.core import privatdateien
from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.spenden import bestaetigung as bst
from apps.spenden import dank as danken
from apps.spenden.models import Spende, SpendenBeleg, SpendenEinstellungen
from apps.vereinsportal import einlesen, namen
from apps.vereinsportal.models import Abruf, Kontakt, PortalEinstellungen, Zugang

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


def test_beleg_lesen_auch_wenn_der_eingetragene_absender_nicht_passt():
    """Ein anders geschriebener Vereinsname darf das Einlesen nicht verhindern: Die erste Zeile
    mit „|“ ist der Absender, darunter steht der Spender."""
    angaben = einlesen.beleg_lesen(beleg_pdf(), "Anderer Verein")
    assert angaben.name == "Erika Beispiel" and angaben.plz_ort == "54321 Beispieldorf"


@pytest.mark.parametrize("pdf", [
    beleg_pdf(spender="Nur Name"), beleg_pdf(spender="Name | Straße |"),
    beleg_pdf(datum="ohne"), b"kein PDF", b"",
])  # fmt: skip
def test_beleg_lesen_unvollstaendig(pdf):
    assert einlesen.beleg_lesen(pdf, ABSENDER) is None


VEREIN = f"{ABSENDER} | Hauptstraße 1 | 12345 Musterstadt"


@pytest.mark.parametrize("zeilen", [
    [VEREIN, ERIKA],  # wie bisher: direkt darunter
    [VEREIN, "Persönlich / Vertraulich", ERIKA],  # eine Zeile dazwischen
    [ERIKA, VEREIN, "Bestätigung über Geldzuwendungen"],  # Spender steht davor
    [VEREIN.replace("e.V.", "e. V.").replace(" | ", "  |  "), ERIKA],  # andere Leerzeichen
    [VEREIN.upper(), ERIKA],
])  # fmt: skip
def test_spenderzeile_findet_den_spender_in_jeder_anordnung(zeilen):
    assert einlesen.spenderzeile(zeilen, ABSENDER) == [
        "Erika Beispiel", "Feldweg 2", "54321 Beispieldorf"]  # fmt: skip


def test_spenderzeile_nimmt_nie_den_verein_und_nichts_entferntes():
    fuss = "Bank Musterstadt | IBAN DE00 | BIC XXXX"
    # Spender ohne Anschrift: weder die Zeile des Vereins noch die Fußzeile weit unten
    zeilen = [VEREIN, "Nur Name", "a", "b", "c", fuss]
    assert einlesen.spenderzeile(zeilen, ABSENDER) is None
    assert einlesen.spenderzeile([VEREIN, VEREIN], ABSENDER) is None
    assert einlesen.spenderzeile(["ohne Strich", "noch eine"], ABSENDER) is None
    assert einlesen.spenderzeile(["ohne Strich"], "") is None
    # ohne Angabe gilt die erste Zeile mit „|“ als Absenderzeile
    assert einlesen.spenderzeile([VEREIN, ERIKA], "")[0] == "Erika Beispiel"


def test_spenderzeile_wenn_der_eingetragene_vereinsname_nicht_passt():
    """Der Name des Vereins ist anders eingetragen, als er auf dem Beleg steht: Die erste Zeile
    mit „|“ ist trotzdem der Absender, die Zeile darunter der Spender. (So sehen die echten
    Belege aus: Absender mit vier Teilen, darunter der Spender.)"""
    erika = ["Erika Beispiel", "Feldweg 2", "54321 Beispieldorf"]
    verein = VEREIN + " | Deutschland"
    beleg = [verein, ERIKA, "25,00 fünfundzwanzig 14.03.2026", "X", "Finanzamt Musterstadt"]
    assert einlesen.spenderzeile(beleg, "Ganz anderer Name") == erika
    assert einlesen.spenderzeile(beleg, ABSENDER) == erika
    assert einlesen.spendendatum(beleg) == dt.date(2026, 3, 14)
    # Spender ohne Anschrift: nur die Absenderzeile hat „|“ – dann nie den Verein nehmen
    ohne = [verein, "Nur Name", "25,00 fünfundzwanzig 14.03.2026"]
    assert einlesen.spenderzeile(ohne, "Ganz anderer Name") is None
    assert einlesen.spenderzeile(ohne, ABSENDER) is None
    # der Name der Tafel oder der Körperschaft kennzeichnet die Zeile ebenfalls als Absender
    assert einlesen.spenderzeile([ERIKA, verein], "Ganz anderer Name", eigene=(ABSENDER,)) == erika


def test_spenderzeile_anschrift_als_block_unter_dem_absender():
    erika = ["Erika Beispiel", "Feldweg 2", "54321 Beispieldorf"]
    assert einlesen.spenderzeile([VEREIN, *erika, "Betrag"], ABSENDER) == erika
    mit_zusatz = [VEREIN, "Erika Beispiel", "c/o Muster", "Feldweg 2", "54321 Beispieldorf"]
    assert einlesen.spenderzeile(mit_zusatz, ABSENDER) == erika
    # auch wenn der eingetragene Name nicht passt
    assert einlesen.spenderzeile([VEREIN, *erika], "Ganz anderer Name") == erika
    assert einlesen.spenderzeile([VEREIN, "Nur Name", "Text", "Text"], ABSENDER) is None


def test_finanzexport_alle_belege_derselbe_spender_wird_abgelehnt():
    """Nennen alle Belege denselben Spender, wurde die Anschrift des Vereins gelesen: nichts
    einlesen, statt den Verein hundertfach als Spender anzulegen."""
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        for nr in range(1, 6):
            z.writestr(f"Spenden/Spendenbeleg_{nr:06d}.pdf", beleg_pdf())
    puffer.seek(0)
    with pytest.raises(einlesen.EinleseFehler, match="Alle 5 Belege nennen denselben Spender"):
        einlesen.finanzexport_einlesen(puffer, "berta")
    assert not Spende.objects.exists() and not Adresse.objects.exists()


def test_beleg_lesen_versucht_weitere_lesarten(monkeypatch):
    """Gibt die erste Lesart die Anschrift nicht her, hilft die nächste."""
    lesarten = (
        lambda inhalt: "Bestätigung\nTag der Zuwendung: 14.3.2026",  # kein Spender
        lambda inhalt: 1 / 0,  # eine Lesart scheitert ganz
        lambda inhalt: f"{VEREIN}\n{ERIKA}\nTag der Zuwendung: 14.3.2026\n25,00 fünfundzwanzig",
    )
    monkeypatch.setattr(einlesen, "LESARTEN", lesarten)
    angaben = einlesen.beleg_lesen(b"egal", ABSENDER)
    assert angaben.name == "Erika Beispiel" and angaben.datum == dt.date(2026, 3, 14)
    assert angaben.betrag == D("25.00")


def test_beleg_lesen_mit_allen_lesarten_des_echten_pdfs():
    for lesen in einlesen.LESARTEN:
        zeilen = einlesen._zerlegen(lesen(beleg_pdf()))
        assert einlesen.spenderzeile(zeilen, ABSENDER)[0] == "Erika Beispiel"
        assert einlesen.spendendatum(zeilen) == dt.date(2026, 3, 14)


def test_diagnose_nennt_nur_zahlen():
    assert einlesen.diagnose(b"kein PDF") == (
        "Aus dem PDF ließ sich kein Text lesen (z. B. eingescannt oder geschützt).")  # fmt: skip
    text = einlesen.diagnose(beleg_pdf(), "Ganz anderer Verein")
    assert text == (
        "Erster Beleg: 5 Textzeilen, davon 2 mit „|“; Name des Vereins gefunden: nein, in einer "
        "Zeile mit „|“: nein; Datum gefunden: ja. Eingetragen ist „Ganz anderer Verein“. Form der "
        "Zeilen mit „|“ (Buchstaben als x): "
        "„Xxxxx Xxxxxxxxxxx x.X. | Xxxxxxxxxxx 9 | 99999 Xxxxxxxxxxx“; "
        "„Xxxxx Xxxxxxxx | Xxxxxxx 9 | 99999 Xxxxxxxxxxxx“.")  # fmt: skip
    assert (
        "Erika" not in text
        and "Feldweg" not in text
        and "nicht angegeben" in einlesen.diagnose(beleg_pdf())
    )


def test_beleg_lesen_ohne_betrag_null():
    assert einlesen.beleg_lesen(beleg_pdf(betrag="unbekannt")).betrag == D("0")


def test_belegnummer_aus_dateiname():
    assert einlesen.belegnummer("Spendenbeleg_000123.PDF") == "123"
    assert einlesen.belegnummer("Spendenbeleg.pdf") == ""


def test_namen_fuers_adressbuch():
    assert namen.normal("  Erika   BEISPIEL ") == "erika beispiel"
    person = namen.teile("Erika Maria Beispiel")
    assert (person["art"], person["vorname"], person["nachname"]) == (
        "person", "Erika Maria", "Beispiel")  # fmt: skip
    assert namen.teile("Cher")["nachname"] == "Cher" and namen.teile("")["nachname"] == ""
    for firma in ("Bäckerei Probe GmbH", "Förderverein Muster e.V.", "Muster & Söhne",
                  "Beispiel Stiftung", "Sparkasse Musterstadt"):  # fmt: skip
        teile = namen.teile(firma)
        assert (teile["art"], teile["organisation"], teile["nachname"]) == (
            "organisation", firma, ""), firma  # fmt: skip
    assert namen.plz_ort("54321 Beispieldorf") == ("54321", "Beispieldorf")
    assert namen.plz_ort("Beispieldorf") == ("", "Beispieldorf") and namen.plz_ort("") == ("", "")
    assert namen.schluessel(" Erika  Beispiel", "54321 ") == "erika beispiel|54321"


# --- Finanzexport in den Spendenpool -----------------------------------------------------------

OFFEN, V = Spende.Fremdbeleg.OFFEN, Spende.Fremdbeleg.VERSENDET


def test_finanzexport_einlesen(export):
    e = einlesen.finanzexport_einlesen(export, "buero")
    assert (e.neu, e.neue_spender, e.doppelt, e.ohne_anschrift, e.versendet, e.mit_uebersicht) == (
        3, 2, 0, 1, 1, True)  # fmt: skip
    s = Spende.objects.get(belegnummer="2")
    assert (s.art, s.datum, s.betrag, s.fremdbeleg) == (
        "geld", dt.date(2026, 3, 14), D("25.00"), OFFEN)  # fmt: skip
    assert s.eingetragen_von == "buero"
    # der Spender steht im Adressbuch, beide Spenden bei derselben Adresse
    erika = s.adresse
    assert (erika.art, erika.vorname, erika.nachname) == ("person", "Erika", "Beispiel")
    assert (erika.strasse, erika.plz, erika.ort) == ("Feldweg 2", "54321", "Beispieldorf")
    assert erika.spenden.count() == 2 and Adresse.objects.count() == 2
    assert Spende.objects.get(belegnummer="3").fremdbeleg == V
    # das PDF hängt verschlüsselt an der Spende
    b = SpendenBeleg.objects.get(spende=s)
    assert (b.dateiname, b.adresse, b.jahr) == ("Spendenbeleg_000002.pdf", erika, 2026)
    assert privatdateien.lesen(SpendenBeleg.ORDNER, b.datei).startswith(b"%PDF")
    assert b"%PDF" not in privatdateien.pfad(SpendenBeleg.ORDNER, b.datei).read_bytes()
    assert einlesen.bericht(e) == (
        "3 neue Spenden eingelesen, 0 waren schon vorhanden, 2 Spender neu ins Adressbuch "
        "aufgenommen, 1 ohne vollständige Anschrift ausgelassen, 1 als im Vereinsportal versendet "
        "vermerkt."
    )


def test_finanzexport_zweimal_einlesen_legt_nichts_doppelt_an(export):
    einlesen.finanzexport_einlesen(export, "buero")
    export.seek(0)
    e = einlesen.finanzexport_einlesen(export, "buero")
    assert (e.neu, e.neue_spender, e.doppelt) == (0, 0, 3)
    assert (Spende.objects.count(), SpendenBeleg.objects.count(), Adresse.objects.count()) == (
        3, 3, 2)  # fmt: skip


def test_vorhandene_adresse_und_vorhandene_spende_werden_wiederverwendet(export):
    """Der Spender steht schon im Adressbuch, und eine der Spenden kam schon über den CSV-Import:
    keine zweite Adresse, keine zweite Spende – nur der Beleg kommt dazu."""
    erika = Adresse.objects.create(art="person", vorname="Erika", nachname="Beispiel",
                                   plz="54321", email="eigene@example.org")  # fmt: skip
    vorhanden = Spende.objects.create(adresse=erika, datum=dt.date(2026, 3, 14), betrag=D("25"),
                                      belegnummer="2")  # fmt: skip
    e = einlesen.finanzexport_einlesen(export, "buero")
    assert (e.neu, e.neue_spender, e.doppelt) == (2, 1, 1)
    assert Adresse.objects.filter(nachname="Beispiel").count() == 1
    assert erika.spenden.count() == 2
    vorhanden.refresh_from_db()
    assert vorhanden.fremdbeleg == OFFEN and vorhanden.belege.count() == 1


def test_finanzexport_ohne_uebersicht():
    e = einlesen.finanzexport_einlesen(
        archiv({"Spendenbeleg_000001.pdf": beleg_pdf(),
                "anderes.xlsx": uebersicht([], blatt="Konten")}), "buero")  # fmt: skip
    assert (e.neu, e.mit_uebersicht, e.versendet) == (1, False, 0)
    assert "keine Übersicht der versendeten Belege" in einlesen.bericht(e)


def test_beleg_ohne_nummer_im_dateinamen(export):
    daten = {"spenden/beleg.pdf": beleg_pdf()}
    assert einlesen.finanzexport_einlesen(archiv(daten), "buero").neu == 1
    assert einlesen.finanzexport_einlesen(archiv(daten), "buero").doppelt == 1
    assert Spende.objects.get().belegnummer == ""


def test_finanzexport_kein_zip():
    with pytest.raises(einlesen.EinleseFehler, match="kein ZIP"):
        einlesen.finanzexport_einlesen(io.BytesIO(b"kein Archiv"), "buero")


def test_finanzexport_zu_viele_belege(monkeypatch):
    monkeypatch.setattr(einlesen, "MAX_BELEGE", 1)
    with pytest.raises(einlesen.EinleseFehler, match="Mehr als 1"):
        einlesen.finanzexport_einlesen(
            archiv({"spenden_1.pdf": b"", "spenden_2.pdf": b""}), "buero")  # fmt: skip
    assert not Spende.objects.exists()


def test_finanzexport_zu_grosses_pdf_wird_ausgelassen(monkeypatch):
    monkeypatch.setattr(einlesen, "MAX_PDF", 10)
    e = einlesen.finanzexport_einlesen(archiv({"Spendenbeleg_000001.pdf": beleg_pdf()}), "buero")
    assert (e.neu, e.ohne_anschrift) == (0, 1)


def test_uebersicht_allein_vermerkt_versendete(export):
    einlesen.finanzexport_einlesen(export, "buero")
    fremd = Spende.objects.create(adresse=Adresse.objects.first(), datum=dt.date(2026, 1, 5),
                                  betrag=D("5"), belegnummer="77")  # fmt: skip
    zeilen = [("2", None, "02.05.2026"), (1.0, None, None), (None, "x", None), ("A7", "x", None),
              (77, "x", None)]  # fmt: skip
    e = einlesen.uebersicht_einlesen(uebersicht(zeilen))
    assert e.versendet == 1
    assert Spende.objects.get(belegnummer="2").fremdbeleg == V
    assert Spende.objects.get(belegnummer="1").fremdbeleg == OFFEN
    fremd.refresh_from_db()
    assert fremd.fremdbeleg == ""  # eine Spende ohne Beleg aus dem Vereinsportal bleibt unberührt


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

KOPF = ("Vorname", "Nachname", "E-Mail", "Anrede", "immer per Post")


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


def test_spenderliste_fehlende_spalten_und_zu_lang(monkeypatch):
    with pytest.raises(einlesen.EinleseFehler, match="Es fehlt: E-Mail"):
        einlesen.spenderliste_einlesen(spenderliste([], kopf=("Vorname", "Nachname")))
    monkeypatch.setattr(einlesen, "MAX_ZEILEN", 1)
    with pytest.raises(einlesen.EinleseFehler, match="Mehr als 1"):
        zeilen = [(1, "A", "B", "a@example.org", None), (2, "C", "D", "c@example.org", None)]
        einlesen.spenderliste_einlesen(spenderliste(zeilen))
    assert not Kontakt.objects.exists()


def test_spenderliste_kommt_ins_adressbuch(export):
    """E-Mail, Anrede und Versandweg stehen danach bei der Adresse – egal, ob die Liste vor oder
    nach dem Finanzexport eingelesen wird."""
    einlesen.spenderliste_einlesen(spenderliste(
        [("Erika", "Beispiel", "erika@example.org", "Frau", None)], kopf=KOPF))  # fmt: skip
    einlesen.finanzexport_einlesen(export, "buero")
    erika = Adresse.objects.get(nachname="Beispiel")
    assert (erika.email, erika.anrede) == ("erika@example.org", "Frau")
    assert erika.einwilligung_email == dt.date.today()
    otto = Adresse.objects.get(nachname="Muster")
    assert otto.email == "" and otto.einwilligung_email is None
    # später kommt Otto dazu, und Erika will Briefe: ihre E-Mail bleibt, die Einwilligung nicht
    einlesen.spenderliste_einlesen(spenderliste([
        ("Erika", "Beispiel", "erika@example.org", "Frau", "Ja"),
        ("Otto", "Muster", "otto@example.org", "Herr", None),
        ("Niemand", "Ohne Spende", "niemand@example.org", "", None),
    ], kopf=KOPF))  # fmt: skip
    erika.refresh_from_db()
    otto.refresh_from_db()
    assert erika.email == "erika@example.org" and erika.einwilligung_email is None
    assert (otto.email, otto.anrede, otto.einwilligung_email) == (
        "otto@example.org", "Herr", dt.date.today())  # fmt: skip
    assert Adresse.objects.count() == 2  # wer nicht gespendet hat, kommt nicht ins Adressbuch


def test_eigene_email_im_adressbuch_bleibt(export):
    erika = Adresse.objects.create(art="person", vorname="Erika", nachname="Beispiel",
                                   plz="54321", email="eigene@example.org")  # fmt: skip
    einlesen.finanzexport_einlesen(export, "buero")
    einlesen.spenderliste_einlesen(spenderliste(
        [("Erika", "Beispiel", "andere@example.org", "Frau", None)], kopf=KOPF))  # fmt: skip
    erika.refresh_from_db()
    # die schon eingetragene Adresse gilt; für sie gibt die Liste keine Einwilligung her
    assert erika.email == "eigene@example.org" and erika.einwilligung_email is None
    assert erika.anrede == "Frau"


# --- Keine zweite Bestätigung, Sammelbestätigung für Mehrfachspender ---------------------------


@pytest.fixture
def einstellungen():
    e = SpendenEinstellungen.laden()
    e.zwecke, e.finanzamt, e.steuernummer = "die Mildtätigkeit", "Musterstadt", "123/456/789"
    e.bescheid_vom, e.unterzeichnet_von = dt.date(2025, 5, 2), "Clara Beispiel"
    e.veranlagungszeitraum = "2021 bis 2023"
    e.save()
    return e


@pytest.fixture
def eingelesen(export):
    """Erika: zwei offene Spenden; Otto: eine, im Vereinsportal schon versendet."""
    einlesen.finanzexport_einlesen(export, "buero")
    return Adresse.objects.get(nachname="Beispiel"), Adresse.objects.get(nachname="Muster")


def test_offene_geldspenden_regeln(eingelesen, einstellungen):
    erika, otto = eingelesen
    # mehrere offene Spenden: bintafeln stellt eine Sammelbestätigung aus
    assert bst.offene_geldspenden(erika, 2026).count() == 2
    # im Vereinsportal versendet: nie eine Bestätigung von hier
    assert not bst.offene_geldspenden(otto, 2026).exists()
    with pytest.raises(bst.BestaetigungsFehler):
        bst.geld_ausstellen(otto, 2026, "buero")
    # eine einzelne offene Spende mit Beleg aus dem Vereinsportal: der Beleg ist die Bestätigung
    Spende.objects.filter(belegnummer="3").update(fremdbeleg=OFFEN)
    assert not bst.offene_geldspenden(otto, 2026).exists()
    # … kommt eine zweite dazu (auch eine von Hand erfasste), wird es eine Sammelbestätigung
    Spende.objects.create(adresse=otto, datum=dt.date(2026, 6, 1), betrag=D("20"))
    assert bst.offene_geldspenden(otto, 2026).count() == 2
    assert {a for a, _, _ in bst.jahresliste(2026)} == {erika, otto}


def test_sammelbestaetigung_fuer_mehrfachspender(eingelesen, einstellungen, pdf_text):
    erika, _ = eingelesen
    b = bst.geld_ausstellen(erika, 2026, "buero")
    assert (b.art, b.betrag) == ("sammel", D("1275.00"))
    assert erika.spenden.filter(bestaetigung=b).count() == 2
    assert not bst.offene_geldspenden(erika, 2026).exists()  # nie ein zweites Mal


@pytest.fixture
def vorlage():
    from apps.serienbriefe.models import Vorlage

    return Vorlage.objects.create(
        name="Dank", betreff="Danke für Ihre Spende",
        text="{anrede}\n\nvielen Dank, {name}, für {anzahl_spenden} Spende(n) am "
             "{spendendaten} über {spendensumme}.",
    )  # fmt: skip


def test_dankesbriefe_auswahl_und_anlagen(eingelesen, einstellungen):
    erika, otto = eingelesen
    danke = danken.auswahl(2026)
    # Otto ist im Vereinsportal schon versorgt: kein Brief von hier
    assert [d.adresse for d in danke] == [erika]
    (d,) = danke
    assert danken.fehlende_ausstellen(danke, 2026, "buero") == []
    anlagen = [name for name, _ in danken.anlagen(d, True, True)]
    # Sammelbestätigung aus bintafeln – die Einzelbelege liegen dann nicht bei
    assert len(anlagen) == 1 and anlagen[0].startswith("Zuwendungsbestaetigung-")


def test_dankesbrief_einfachspender_bekommt_den_beleg_aus_dem_vereinsportal(
    eingelesen, einstellungen
):
    _, otto = eingelesen
    Spende.objects.filter(belegnummer="3").update(fremdbeleg=OFFEN)
    (d,) = danken.auswahl(2026, "einfach")
    assert d.adresse == otto
    assert danken.fehlende_ausstellen([d], 2026, "buero") == []  # nichts auszustellen
    assert [name for name, _ in danken.anlagen(d, True, True)] == ["Spendenbeleg_000003.pdf"]
    assert not otto.spenden.filter(bestaetigung__isnull=False).exists()
    danken.vermerken([d], True)
    assert SpendenBeleg.objects.get(dateiname="Spendenbeleg_000003.pdf").beigelegt_am
    assert danken.auswahl(2026, "einfach") == []


def test_dankesbriefe_seite_druck_pdf_im_grossen_stil(
    admin_client, eingelesen, einstellungen, vorlage, pdf_text
):
    """Die Seite „Dankesbriefe“ liefert alles in einem PDF: Brief und dahinter die Bescheinigung –
    Sammelbestätigung aus bintafeln oder Beleg aus dem Vereinsportal."""
    Spende.objects.filter(belegnummer="3").update(fremdbeleg=OFFEN)
    daten = {"vorlage": vorlage.pk, "jahr": 2026, "art": "alle", "nur_offen": "on",
             "mit_bestaetigungen": "on", "mit_belegen": "on"}  # fmt: skip
    url = reverse("spenden:dank")
    seite = admin_client.post(url, daten | {"schritt": "vorschau"}).content.decode()
    assert "2 Spender" in seite and "(2 per Brief)" in seite
    text = pdf_text(admin_client.post(url, daten | {"schritt": "pdf"}))
    assert "2 Spende(n) am 14.03.2026, 14.03.2026" in text and "Sammelbest" in text
    assert text.count("Sammelbest") >= 1 and "Otto Muster" in text
    assert not Spende.objects.filter(bedankt_am__isnull=True).exists()
    # Spendenliste: die Herkunft steht in der Spalte „Bestätigung“
    liste = admin_client.get(reverse("spenden:liste"), {"jahr": 2026}).content.decode()
    # der Beleg ist ein Link auf das PDF; die Einzelspende behält ihn als Bestätigung
    beleg = SpendenBeleg.objects.get(spende__belegnummer="3")
    assert reverse("spenden:beleg", args=[beleg.pk]) in liste and "📄 Beleg 3" in liste
    assert "dieser Beleg ist die Bescheinigung" in liste and "Sammelbestätigung Nr." in liste
    assert "✓ Bescheinigt von bintafeln" in liste
    assert admin_client.get(reverse("spenden:beleg", args=[beleg.pk])).status_code == 200
    Spende.objects.filter(belegnummer="3").update(fremdbeleg=V)
    liste = admin_client.get(reverse("spenden:liste"), {"jahr": 2026}).content.decode()
    assert "✓ Schon verschickt (Vereinsportal)</span>\n" in liste
    # Filter „Bescheinigung“: nur schon verschickte bzw. nur noch offene
    verschickt = admin_client.get(
        reverse("spenden:liste"), {"jahr": 2026, "bescheinigung": "verschickt"}
    )
    offen = admin_client.get(reverse("spenden:liste"), {"jahr": 2026, "bescheinigung": "offen"})
    verschickt, offen = verschickt.content.decode(), offen.content.decode()
    assert "📄 Beleg 3" in verschickt and "Sammelbestätigung aus bintafeln (" not in verschickt
    assert "📄 Beleg 3" not in offen


# --- Seiten -----------------------------------------------------------------------------------


@pytest.fixture
def berta(admin, benutzer_mit_rolle, recht_geben):
    """Büro-Konto, das auch automatisch abrufen darf (das Recht hat sonst nur der Admin)."""
    recht_geben(rollen.BUERO, "vereinsportal.abruf")
    return benutzer_mit_rolle("berta", rollen.BUERO)


@pytest.fixture
def buero(berta, anmelden, client):
    return anmelden(client, berta)


def hochladen(client, feld, name, inhalt):
    return client.post(reverse("vereinsportal:start"), {
        feld: SimpleUploadedFile(name, inhalt)}, follow=True)  # fmt: skip


def test_seite_einlesen_und_stand(buero, export):
    leer = buero.get(reverse("vereinsportal:start")).content.decode()
    assert "Noch keine Spenden aus dem Vereinsportal eingelesen" in leer
    seite = hochladen(buero, "finanzexport", "export.zip", export.getvalue()).content.decode()
    assert "3 neue Spenden eingelesen, 0 waren schon vorhanden" in seite
    assert "2 Spender neu ins Adressbuch aufgenommen" in seite
    assert "1 als im Vereinsportal versendet vermerkt" in seite
    # Stand im Spendenpool: 3 Spenden von 2 Spendern, 1 versendet, 2 offen
    zeile = seite[seite.index('id="portal-stand"') :]
    zahlen = [z.split("<")[0] for z in zeile.split('<td class="zahl">')[1:5]]
    assert zahlen == ["3", "2", "1", "2"]
    assert reverse("spenden:liste") + "?jahr=2026" in seite and reverse("spenden:dank") in seite
    antwort = hochladen(buero, "spenderliste", "liste.xlsx",
                        spenderliste([(1, "Erika", "Beispiel", "erika@example.org", ""),
                                      (2, "Ohne", "Mail", "", "")]))  # fmt: skip
    assert "Spenderliste ersetzt: 1 Spender mit E-Mail, 1 Zeilen ohne gültige E-Mail" in (
        antwort.content.decode())  # fmt: skip
    assert Adresse.objects.get(nachname="Beispiel").email == "erika@example.org"


def test_seite_nur_excel_des_finanzexports(buero, export):
    hochladen(buero, "finanzexport", "export.zip", export.getvalue())
    antwort = hochladen(buero, "finanzexport", "Finanzexport.XLSX", uebersicht([(2, "x", None)]))
    assert "0 neue Spenden eingelesen" in antwort.content.decode()
    assert Spende.objects.get(belegnummer="2").fremdbeleg == V


def test_seite_fehler(buero):
    antwort = hochladen(buero, "finanzexport", "export.zip", b"kein Archiv")
    assert "kein ZIP-Archiv" in antwort.content.decode()
    antwort = buero.post(reverse("vereinsportal:start"), {}, follow=True)
    assert "Bitte eine Datei wählen" in antwort.content.decode()


def test_einstellungen(buero):
    seite = reverse("vereinsportal:einstellungen")
    assert buero.get(seite).status_code == 200
    assert buero.post(seite, {"absender": ABSENDER}).status_code == 302
    e = PortalEinstellungen.laden()
    assert e.absender == ABSENDER and str(e) == "Einstellungen für das Vereinsportal"


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
def adressen():
    e = PortalEinstellungen.laden()
    e.anmeldung_url = "https://portal.example.org/login"
    e.liste_url = "https://portal.example.org/liste/1"
    e.export_url = "https://portal.example.org/export"
    e.save()
    return e


@pytest.fixture
def zugang(berta, adressen):
    """Bertas persönliche Zugangsdaten (erfunden)."""
    from apps.core import geheimnis

    geheim = geheimnis.verschluesseln("erfunden")
    return Zugang.objects.create(
        benutzer=berta, email="berta@example.org", passwort_verschluesselt=geheim
    )


def test_abruf_starten_schickt_auftrag_mit_eigenen_zugangsdaten(dienst, zugang, berta, adressen):
    from apps.vereinsportal import abruf

    abruf.starten(berta, dt.date(2026, 2, 1), dt.date(2026, 2, 4), True)
    pfad, daten = dienst.aufrufe[-1]
    assert pfad == "/start" and daten == {
        "anmeldung_url": "https://portal.example.org/login",
        "liste_url": "https://portal.example.org/liste/1",
        "export_url": "https://portal.example.org/export", "email": "berta@example.org",
        "passwort": "erfunden", "von": "01.02.2026", "bis": "04.02.2026", "mit_liste": True,
    }  # fmt: skip
    a = Abruf.objects.get()
    assert a.benutzer == berta and a.stand == "laeuft" and a.mit_liste and a.wer
    assert str(a) == "Abruf 01.02.2026–04.02.2026" and str(zugang) == f"Zugang von {berta}"
    # ohne Adresse der Liste wird sie nicht geholt; der liegengebliebene Abruf gilt als abgebrochen
    adressen.liste_url = ""
    adressen.save()
    abruf.starten(berta, dt.date(2026, 2, 1), dt.date(2026, 2, 4), True)
    assert dienst.aufrufe[-1][1]["mit_liste"] is False
    assert [x.stand for x in Abruf.objects.order_by("pk")] == ["abgebrochen", "laeuft"]


def test_abruf_starten_prueft(dienst, zugang, berta, adressen, benutzer_mit_rolle):
    from apps.vereinsportal import abruf

    for von, bis, text in [
        (dt.date(2026, 2, 4), dt.date(2026, 2, 1), "vor dem Startdatum"),
        (dt.date(2026, 1, 1), dt.date(2026, 6, 1), "höchstens drei Monate"),
        (dt.date.today(), dt.date.today() + dt.timedelta(days=2), "in der Zukunft"),
    ]:
        with pytest.raises(abruf.AbrufFehler, match=text):
            abruf.starten(berta, von, bis, False)
    # ein anderes Konto hat keine eigenen Zugangsdaten und kann Bertas nicht benutzen
    carl = benutzer_mit_rolle("carl", rollen.BUERO)
    with pytest.raises(abruf.AbrufFehler, match="Ihre persönlichen Zugangsdaten"):
        abruf.starten(carl, dt.date(2026, 2, 1), dt.date(2026, 2, 4), False)
    zugang.passwort_verschluesselt = "nicht lesbar"
    zugang.save()
    with pytest.raises(abruf.AbrufFehler, match="nicht mehr lesbar"):
        abruf.starten(berta, dt.date(2026, 2, 1), dt.date(2026, 2, 4), False)
    zugang.passwort_verschluesselt = ""
    zugang.save()
    assert abruf.zugang(berta) is None
    adressen.export_url = ""
    adressen.save()
    with pytest.raises(abruf.AbrufFehler, match="zuerst die Adressen"):
        abruf.starten(berta, dt.date(2026, 2, 1), dt.date(2026, 2, 4), False)
    assert dienst.aufrufe == [] and not Abruf.objects.exists()


def test_abruf_historie_haelt_ergebnis_fest(dienst, zugang, berta, export):
    from apps.vereinsportal import abruf

    assert abruf.historie()["anzahl"] == 0 and abruf.historie()["letzter"] is None
    abruf.starten(berta, dt.date(2026, 2, 1), dt.date(2026, 2, 4), True)
    dienst.stand |= {"stand": "fertig", "dateien": {"spenderliste": True, "finanzexport": True}}
    dienst.dateien = {
        "finanzexport": export.getvalue(),
        "spenderliste": spenderliste([(1, "Erika", "Beispiel", "erika@example.org", "")]),
    }  # fmt: skip
    abruf.uebernehmen("berta")
    a = Abruf.objects.get()
    assert (a.stand, a.neu, a.doppelt, a.neue_spender, a.versendet, a.kontakte) == (
        "eingelesen", 3, 0, 2, 1, 1)  # fmt: skip
    assert a.beendet_am and not a.meldung
    # Fehler im Dienst und ein abgebrochener Abruf stehen ebenfalls in der Historie
    abruf.starten(berta, dt.date(2026, 3, 1), dt.date(2026, 3, 4), False)
    abruf.abgleichen({"stand": "fehler", "fehler": "Anmeldung abgelehnt."})
    abruf.starten(berta, dt.date(2026, 4, 1), dt.date(2026, 4, 4), False)
    abruf.abbrechen()
    abruf.starten(berta, dt.date(2026, 5, 1), dt.date(2026, 5, 4), False)
    abruf.abgleichen({"stand": "frei"})  # der Dienst wurde neu gestartet
    abruf.starten(berta, dt.date(2026, 6, 1), dt.date(2026, 6, 4), False)
    dienst.stand |= {"stand": "fertig", "dateien": {"finanzexport": True}}
    dienst.dateien = {"finanzexport": b"kein Archiv"}
    abruf.uebernehmen("berta")
    staende = [(x.stand, x.meldung) for x in Abruf.objects.order_by("pk")]
    assert staende == [
        ("eingelesen", ""), ("fehler", "Anmeldung abgelehnt."), ("abgebrochen", ""),
        ("abgebrochen", ""), ("fehler", "Finanzexport: Die Datei ist kein ZIP-Archiv."),
    ]  # fmt: skip
    h = abruf.historie(grenze=2)
    assert (h["anzahl"], h["gelungen"], h["neu"], h["neue_spender"], h["mehr"]) == (5, 1, 3, 2, 3)
    assert h["letzter"] == a and len(h["abrufe"]) == 2
    assert len(abruf.historie(alle=True)["abrufe"]) == 5 and abruf.historie(alle=True)["mehr"] == 0


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
        (True, "3 neue Spenden eingelesen, 0 waren schon vorhanden, 2 Spender neu ins Adressbuch "
               "aufgenommen, 1 ohne vollständige Anschrift ausgelassen, 1 als im Vereinsportal "
               "versendet vermerkt."),
    ]  # fmt: skip
    assert Spende.objects.count() == 3 and Kontakt.objects.count() == 1
    assert dienst.aufrufe[-1] == ("/fertig", {}) and dienst.stand["stand"] == "frei"
    # nur der Finanzexport, ohne Zeilen ohne E-Mail
    dienst.stand |= {"stand": "fertig", "dateien": {"finanzexport": True}}
    assert len(abruf.uebernehmen("buero")) == 1
    dienst.stand |= {"stand": "fertig", "dateien": {"spenderliste": True}}
    dienst.dateien["spenderliste"] = spenderliste([(1, "Erika", "Beispiel", "e@example.org", "")])
    assert abruf.uebernehmen("buero") == [
        (True, "Spenderliste ersetzt: 1 Spender mit E-Mail."),
        (False, "Der Finanzexport wurde nicht geholt."),
    ]
    # eine unlesbare Spenderliste hält den Finanzexport nicht auf; danach ist der Dienst frei
    dienst.stand |= {"stand": "fertig", "dateien": {"spenderliste": True, "finanzexport": True}}
    dienst.dateien["spenderliste"] = b"keine Excel-Datei"
    kaputt, gut = abruf.uebernehmen("buero")
    assert kaputt == (False, "Spenderliste: Die Excel-Datei lässt sich nicht lesen.")
    assert gut[0] and "3 waren schon vorhanden" in gut[1] and dienst.stand["stand"] == "frei"


def test_abruf_ohne_belege_ist_kein_erfolg(dienst, zugang, berta):
    """Kommt aus dem Finanzexport nichts an, steht der Abruf nicht als „eingelesen“ da, sondern
    sagt, was in der Datei war."""
    from apps.vereinsportal import abruf

    def archiv(dateien):
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as z:
            for name, inhalt in dateien.items():
                z.writestr(name, inhalt)
        return puffer.getvalue()

    liste = spenderliste([(1, "Erika", "Beispiel", "erika@example.org", "")])
    # 1) ein Archiv ganz ohne Spendenbelege; die Spenderliste klappt
    abruf.starten(berta, dt.date(2026, 2, 1), dt.date(2026, 2, 4), True)
    dienst.stand |= {"stand": "fertig", "dateien": {"spenderliste": True, "finanzexport": True}}
    ohne_belege = archiv({"Buchungen.csv": b"x", "Anlage/Rechnung.pdf": b"y"})
    dienst.dateien = {"spenderliste": liste, "finanzexport": ohne_belege}
    ok, kaputt = abruf.uebernehmen("berta")
    assert ok[0] and kaputt == (False, (
        "Finanzexport: Die Datei enthält keine Spendenbelege: 2 Dateien, davon 1 PDF, aber "
        "keines mit „Spenden“ im Namen. Wurde der Export im Vereinsportal mit den Belegen "
        "erzeugt, und stimmt der Zeitraum?"))  # fmt: skip
    a = Abruf.objects.get()
    assert a.stand == "fehler" and a.kontakte == 1 and "keine Spendenbelege" in a.meldung
    # 2) Belege sind da, aber keiner lässt sich lesen (Spender ohne Anschrift)
    e = PortalEinstellungen.laden()
    e.absender = "Ganz anderer Verein e.V."
    e.save()
    abruf.starten(berta, dt.date(2026, 3, 1), dt.date(2026, 3, 4), False)
    dienst.stand |= {"stand": "fertig", "dateien": {"finanzexport": True}}
    dienst.dateien = {"finanzexport": archiv({
        "Spenden/Spendenbeleg_000001.pdf": beleg_pdf(spender="Nur Name"),
        "Spenden/Spendenbeleg_000002.pdf": beleg_pdf(spender="Nur Name")})}  # fmt: skip
    ((gelungen, text),) = abruf.uebernehmen("berta")
    assert not gelungen and "Kein Beleg ließ sich lesen (2 in der Datei)" in text
    assert "Erster Beleg: 5 Textzeilen, davon 1 mit „|“; Name des Vereins gefunden: nein" in text
    assert "Form der Zeilen" in text and "Erika" not in text
    assert "Anschrift des Spenders" in text
    assert Abruf.objects.first().stand == "fehler" and not Spende.objects.exists()
    # 3) der Dienst liefert gar keinen Finanzexport
    abruf.starten(berta, dt.date(2026, 4, 1), dt.date(2026, 4, 4), True)
    dienst.stand |= {"stand": "fertig", "dateien": {"spenderliste": True}}
    dienst.dateien = {"spenderliste": liste}
    assert abruf.uebernehmen("berta")[-1] == (False, "Der Finanzexport wurde nicht geholt.")
    assert Abruf.objects.first().stand == "fehler"
    assert abruf.historie()["gelungen"] == 0


def test_abruf_uebernehmen_reicht_hinweise_des_dienstes_weiter(dienst, export):
    """Konnte der Dienst die Spenderliste nicht holen, steht das auf der Seite."""
    from apps.vereinsportal import abruf

    hinweis = "Die Liste „Spender mit E-Mail“ wurde nicht geholt."
    dienst.stand |= {"stand": "fertig", "dateien": {"finanzexport": True}, "hinweise": [hinweis]}
    dienst.dateien = {"finanzexport": export.getvalue()}
    gut, gemeldet = abruf.uebernehmen("buero")
    assert gut[0] and gemeldet == (False, hinweis)


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
    abruf._anfrage("/code", {"code": "123456"})
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
    assert "Abruf starten" not in (
        buero.get(reverse("vereinsportal:start")).content.decode())  # fmt: skip


def test_seite_abruf_ablauf(buero, dienst, zugang, export):
    url, stand_url = reverse("vereinsportal:abruf"), reverse("vereinsportal:abruf_stand")
    assert "Abruf starten" in (
        buero.get(reverse("vereinsportal:start")).content.decode())  # fmt: skip
    seite = buero.get(url).content.decode()
    assert "Abruf starten" in seite and "Es läuft kein Abruf" in seite
    assert "Noch kein Abruf" in seite and "berta@example.org" in seite
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
    assert "3 neue Spenden eingelesen" in teil and "Es läuft kein Abruf" in teil
    assert Spende.objects.count() == 3
    # die Historie zeigt den Abruf mit Zeitraum und Zahlen
    seite = buero.get(url).content.decode()
    assert 'id="abruf-historie"' in seite and "01.02.2026 – 04.02.2026" in seite
    assert "Letzter erfolgreicher Abruf" in seite and "marke-ok" in seite


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


def test_seite_abruf_ohne_zugangsdaten(buero, dienst, adressen):
    seite = buero.get(reverse("vereinsportal:abruf")).content.decode()
    assert "Meine Zugangsdaten eintragen" in seite and "Abruf starten" not in seite
    assert "Ihre eigenen</strong> Zugangsdaten" in seite


def test_seite_abruf_ohne_adressen(buero, dienst):
    seite = buero.get(reverse("vereinsportal:abruf")).content.decode()
    assert "die Adressen des Vereinsportals eintragen" in seite and "Abruf starten" not in seite


def test_eigene_zugangsdaten_verschluesselt_und_nur_fuer_das_eigene_konto(
    buero, berta, dienst, adressen, benutzer_mit_rolle, anmelden, client
):
    from apps.core import geheimnis

    seite = reverse("vereinsportal:zugang")
    assert "Nur für Ihr Konto" in buero.get(seite).content.decode()
    # ohne Passwort geht es beim ersten Mal nicht
    assert "Bitte das Passwort eintragen" in (
        buero.post(seite, {"email": "berta@example.org"}).content.decode())  # fmt: skip
    daten = {"email": "berta@example.org", "passwort": "erfunden und geheim"}
    assert buero.post(seite, daten).status_code == 302
    z = Zugang.objects.get()
    assert z.benutzer == berta and "erfunden" not in z.passwort_verschluesselt
    assert geheimnis.entschluesseln(z.passwort_verschluesselt) == "erfunden und geheim"
    inhalt = buero.get(seite).content.decode()
    assert "erfunden und geheim" not in inhalt and "Ein Passwort ist gespeichert" in inhalt
    assert "berta@example.org" in buero.get(reverse("vereinsportal:abruf")).content.decode()
    # leeres Passwort behält das gespeicherte
    buero.post(seite, {"email": "neu@example.org", "passwort": ""})
    z.refresh_from_db()
    assert z.email == "neu@example.org"
    assert geheimnis.entschluesseln(z.passwort_verschluesselt) == "erfunden und geheim"
    # ein anderes Konto sieht nichts davon und legt seinen eigenen Zugang an
    carl = benutzer_mit_rolle("carl", rollen.BUERO)
    anmelden(client, carl)
    inhalt = client.get(seite).content.decode() + client.get(
        reverse("vereinsportal:abruf")).content.decode()  # fmt: skip
    assert "neu@example.org" not in inhalt and "Meine Zugangsdaten eintragen" in inhalt
    client.post(seite, {"email": "carl@example.org", "passwort": "auch erfunden"})
    assert Zugang.objects.count() == 2 and Zugang.objects.get(benutzer=carl).email == (
        "carl@example.org")  # fmt: skip
    # löschen entfernt nur den eigenen
    assert client.post(seite, {"loeschen": "1"}).status_code == 302
    assert list(Zugang.objects.all()) == [z]
    assert client.post(seite, {"loeschen": "1"}).status_code == 302  # nichts mehr da: kein Fehler
    # die Einstellungen des Moduls kennen keine Zugangsdaten mehr
    inhalt = client.get(reverse("vereinsportal:einstellungen")).content.decode()
    assert 'name="passwort"' not in inhalt and 'name="email"' not in inhalt


def test_code_gibt_nur_ein_wer_gestartet_hat(
    buero, berta, dienst, zugang, benutzer_mit_rolle, anmelden, client
):
    from django.test import Client

    stand_url = reverse("vereinsportal:abruf_stand")
    buero.post(reverse("vereinsportal:abruf"), {"von": "01.02.2026", "bis": "04.02.2026"})
    dienst.stand |= {"stand": "warte_auf_code", "schritt": "Bitte den 2FA-Code eingeben"}
    anderer = anmelden(Client(), benutzer_mit_rolle("carl", rollen.BUERO))
    teil = anderer.get(stand_url).content.decode()
    assert 'name="code"' not in teil and "Den gibt nur" in teil and "every 2s" in teil
    teil = anderer.post(stand_url, {"aktion": "code", "code": "123456"}).content.decode()
    assert "nur ein, wer den Abruf gestartet hat" in teil
    assert not any(pfad == "/code" for pfad, _ in dienst.aufrufe)
    assert 'name="code"' in buero.get(stand_url).content.decode()


def test_abruf_nur_mit_eigenem_recht(admin, benutzer_mit_rolle, anmelden, client, dienst):
    """Wer nur von Hand einlesen darf (Vorgabe Büro), kommt nicht an den automatischen Abruf."""
    anmelden(client, benutzer_mit_rolle("dora", rollen.BUERO))
    assert client.get(reverse("vereinsportal:start")).status_code == 200
    for name in ("abruf", "abruf_stand", "zugang"):
        assert client.get(reverse(f"vereinsportal:{name}")).status_code == 403
    assert reverse("vereinsportal:abruf") not in client.get(reverse("core:start")).content.decode()


def test_spendenliste_zeigt_offene_sammelbestaetigung(eingelesen, einstellungen, admin_client):
    """Mehrere noch nicht bestätigte Spenden eines Spenders im Jahr: Die Liste sagt, dass
    bintafeln dafür eine Sammelbestätigung ausstellt."""
    liste = admin_client.get(reverse("spenden:liste"), {"jahr": 2026}).content.decode()
    assert "kommt in die Sammelbestätigung aus bintafeln (2 Spenden 2026)" in liste
    assert liste.count("📄 Beleg") == 3 and "(wird nicht verschickt)" in liste


def test_eine_seite_fuer_abruf_und_hochladen(
    admin, benutzer_mit_rolle, recht_geben, recht_nehmen, anmelden, client, dienst
):
    """Ein Menüeintrag führt zu beidem; jede Person sieht den Weg, den sie gehen darf."""
    start = reverse("vereinsportal:start")
    anmelden(client, benutzer_mit_rolle("dora", rollen.BUERO))  # nur von Hand
    seite = client.get(start).content.decode()
    assert "Von Hand hochladen" in seite and "Automatisch holen" not in seite
    menue = client.get(reverse("core:start")).content.decode()
    assert menue.count(f'href="{start}"') == 1
    # nur der automatische Abruf: dieselbe Seite, ohne Hochladen
    recht_geben(rollen.BUERO, "vereinsportal.abruf")
    recht_nehmen(rollen.BUERO, "vereinsportal.nutzen")
    seite = client.get(start).content.decode()
    assert "Automatisch holen" in seite and "Von Hand hochladen" not in seite
    assert client.post(start, {}).status_code == 403
    assert f'href="{start}"' in client.get(reverse("core:start")).content.decode()
    # beides
    recht_geben(rollen.BUERO, "vereinsportal.nutzen")
    seite = client.get(start).content.decode()
    assert "Automatisch holen" in seite and "Von Hand hochladen" in seite
    assert client.get(reverse("core:start")).content.decode().count(f'href="{start}"') == 1


def test_auskunft_nennt_zugang_und_abrufe(admin, berta, zugang, dienst, pdf_text):
    from django.http import HttpResponse

    from apps.konten import auskunft
    from apps.vereinsportal import abruf

    def text(konto):
        return pdf_text(HttpResponse(auskunft.mitarbeiter_pdf(konto), "application/pdf"))

    assert "Vereinsportal" not in text(admin)
    abruf.starten(berta, dt.date(2026, 2, 1), dt.date(2026, 2, 4), False)
    inhalt = text(berta)
    assert "Vereinsportal" in inhalt and "berta@example.org" in inhalt and "01.02.2026" in inhalt
    assert "erfunden" not in inhalt
