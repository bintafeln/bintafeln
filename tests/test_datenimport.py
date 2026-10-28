"""Import-Assistent (ADR 0078): Lesen, Zuordnen, Abgleich mit Konflikten, Übernehmen."""

import datetime as dt
import io
from decimal import Decimal

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook

from apps.core.models import PapierkorbEintrag
from apps.datenimport import abgleich, lesen, zuordnung
from apps.datenimport.models import ImportSitzung, ImportVorlage
from apps.datenimport.ziele import ZIELE
from apps.konten import rollen
from apps.konten.models import Stammdaten
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe, Person

pytestmark = pytest.mark.django_db

START = reverse("datenimport:start")


def csv_datei(name, *zeilen, kodierung="utf-8"):
    return SimpleUploadedFile(name, ("\n".join(zeilen) + "\n").encode(kodierung), "text/csv")


def excel_datei(name, blaetter: dict[str, list[list]]):
    mappe = Workbook()
    mappe.remove(mappe.active)
    for titel, zeilen in blaetter.items():
        blatt = mappe.create_sheet(titel)
        for z in zeilen:
            blatt.append(z)
    puffer = io.BytesIO()
    mappe.save(puffer)
    return SimpleUploadedFile(name, puffer.getvalue())


@pytest.fixture
def sicherung(settings, tmp_path):
    zeitpunkt = timezone.now() - dt.timedelta(hours=1)
    pfad = tmp_path / "status.txt"
    pfad.write_text(
        f"ergebnis=ok\nletzte_erfolgreiche={zeitpunkt.strftime('%Y-%m-%dT%H:%M:%S%z')}\n"
    )
    settings.SICHERUNG_STATUSDATEI = pfad


def hochladen(client, ziel, *dateien):
    antwort = client.post(START, {"ziel": ziel, "dateien": list(dateien)})
    assert antwort.status_code == 302, antwort.content.decode()[:2000]
    return ImportSitzung.objects.get()


def weiter(client, sitzung, **felder):
    """Zuordnung wie vorgeschlagen absenden (Felder überschreiben einzelne Wahlen)."""
    daten = {"aktion": "weiter"}
    for ti, t in enumerate(sitzung.tabellen):
        daten[f"a-{ti}"] = t["art"]
        daten[f"k-{ti}"] = t["kopf"] + 1
        for ci, w in enumerate(t["zuordnung"]):
            daten[f"z-{ti}-{ci}"] = w
    daten.update(felder)
    return client.post(reverse("datenimport:zuordnen", args=[sitzung.pk]), daten)


# --- Lesen ------------------------------------------------------------------------------


def test_csv_mit_komma_windows_und_titelzeilen():
    roh = "Kundenliste Stand 1.10.\n\nNr,Name,Ort\n1,Müller,Essen\n2,Probe,Bochum\n"
    t = lesen.lesen("liste.csv", roh.encode("cp1252"))[0]
    assert t.zeilen[2] == ["Nr", "Name", "Ort"] and t.zeilen[3][1] == "Müller"
    assert "Windows-1252" in t.hinweise[0]
    assert lesen.kopfzeile_finden(t.zeilen) == 2


def test_excel_blaetter_datum_und_zahlen():
    datei = excel_datei(
        "export.xlsx",
        {
            "Haushalte": [["Kd-Nr", "Geboren", "Betrag"], [123.0, dt.datetime(1980, 5, 1), 1.5]],
            "Leer": [],
        },
    )
    tabellen = lesen.lesen("export.xlsx", datei.read())
    assert [t.name for t in tabellen] == ["export.xlsx › Haushalte"]
    assert tabellen[0].zeilen[1] == ["123", "1980-05-01", "1.5"]


def test_alte_formate_verstaendlich_abgelehnt():
    with pytest.raises(lesen.LeseFehler, match="xlsx"):
        lesen.lesen("alt.xls", b"irgendwas")
    with pytest.raises(lesen.LeseFehler, match="keine Daten"):
        lesen.lesen("leer.csv", b"\n\n")


# --- Zuordnen ---------------------------------------------------------------------------


def test_vorschlag_tolerant():
    art = ZIELE["mitarbeitende"].art("mitarbeitende")
    kopf = [
        "Vorname",
        "Nachname",
        "E-Mail-Adresse",
        "Straße",
        "Hausnr.",
        "PLZ Ort",
        "Geb.-Datum",
        "Mobil",
        "Lieblingsessen",
    ]
    z = zuordnung.vorschlagen(kopf, art)
    assert z == [
        "vorname",
        "nachname",
        "email",
        "strasse",
        "strasse",
        zuordnung.PLZ_ORT,
        "geburtsdatum",
        "handy",
        "",
    ]
    werte = zuordnung.umsetzen(
        [
            "Anna",
            "Muster",
            "a@example.org",
            "Weg",
            "5",
            "12345 Ort",
            "01.02.1990",
            "0170 1",
            "Pizza",
        ],
        z,
    )
    assert werte["strasse"] == "Weg 5" and (werte["plz"], werte["ort"]) == ("12345", "Ort")
    assert "Pizza" not in werte.values()
    # nur „Name“: Vor- und Nachname in einer Spalte
    z = zuordnung.vorschlagen(["Name", "Mail"], art)
    assert z == [zuordnung.NAME_VOLL, "email"]
    assert zuordnung.umsetzen(["Muster, Anna", "x"], z)["vorname"] == "Anna"
    assert zuordnung.name_teilen("Anna Maria Muster") == ("Anna Maria", "Muster")


def test_vorlage_wird_gespeichert_und_vorgeschlagen(admin_client):
    datei = csv_datei("stellen.csv", "Bezeichnung;Kommentar", "Nord;Hof")
    sitzung = hochladen(admin_client, "ausgabestellen", datei)
    assert sitzung.tabellen[0]["zuordnung"] == ["name", ""]
    weiter(admin_client, sitzung, **{"z-0-1": "anmerkung", "vn-0": "Altprogramm"})
    assert ImportVorlage.objects.get().zuordnung == {
        "bezeichnung": "name",
        "kommentar": "anmerkung",
    }
    ImportSitzung.objects.all().delete()
    sitzung = hochladen(
        admin_client, "ausgabestellen", csv_datei("b.csv", "Bezeichnung;Kommentar", "Süd;x")
    )
    assert sitzung.tabellen[0]["zuordnung"] == ["name", "anmerkung"]
    assert sitzung.tabellen[0]["vorlage"] == "Altprogramm"


def test_pflichtfeld_fehlt(admin_client):
    sitzung = hochladen(admin_client, "ausgabestellen", csv_datei("s.csv", "Ort;PLZ", "A;1"))
    antwort = weiter(admin_client, sitzung)
    assert "Pflichtfelder fehlen" in antwort.content.decode()
    assert ImportSitzung.objects.get().plan is None


# --- Abgleich ---------------------------------------------------------------------------


def test_abgleich_konflikte_ergaenzungen_dubletten():
    bestand = [
        abgleich.Bestandseintrag("1", "Anna", {"name": "Anna", "ort": "Essen", "tel": ""}),
        abgleich.Bestandseintrag("2", "Ben", {"name": "Ben", "ort": "Bochum"}),
        abgleich.Bestandseintrag("3", "Carla", {"name": "Carla"}),
    ]
    saetze = [
        {"zeile": 2, "werte": {"name": "Anna", "ort": "Bochum", "tel": "01"}},
        {"zeile": 3, "werte": {"name": "Ben", "ort": ""}},
        {"zeile": 4, "werte": {"name": "Bem", "ort": "Dorf"}},
        {"zeile": 5, "werte": {"name": "Dora", "ort": "Hagen"}},
        {"zeile": 6, "werte": {"name": "dora", "ort": "Herne", "tel": "02"}},
    ]

    def treffer(w):
        n = w["name"]
        if n in ("Anna", "Ben"):
            return abgleich.Treffer(n == "Anna" and "1" or "2", True)
        return abgleich.Treffer("2", False, "ähnlich") if n == "Bem" else None

    plan = abgleich.abgleichen(
        saetze,
        bestand,
        felder=[("ort", "Ort"), ("tel", "Telefon")],
        treffer=treffer,
        name=lambda w: w["name"],
        schluessel=lambda w: w["name"].lower(),
    ).als_dict()
    (anna,) = plan["geaendert"]
    assert [(f["feld"], f["art"]) for f in anna["felder"]] == [
        ("ort", "konflikt"),
        ("tel", "ergaenzung"),
    ]
    assert plan["gleich"] == 1  # Ben: leere Zelle überschreibt nichts
    assert [e["name"] for e in plan["neu"]] == ["Bem", "Dora"]
    assert plan["neu"][0]["dublette"]["id"] == "2"
    assert plan["doppelt"][0]["zeilen"] == [5, 6]
    assert plan["doppelt"][0]["widersprueche"][0]["auch"] == "Herne"
    assert plan["neu"][1]["werte"]["tel"] == "02"  # Lücke aus der zweiten Zeile gefüllt
    assert [e["id"] for e in plan["fehlt"]] == ["3"]

    aktionen = [("behalten", "behalten"), ("loeschen", "löschen")]
    nur_neu = abgleich.entscheiden(plan, abgleich.NUR_NEUE, {}, aktionen)
    assert nur_neu.aendern == {} and nur_neu.fehlt == {} and len(nur_neu.anlegen) == 1
    assert nur_neu.ausgelassen == 1  # Dublette ist erst einmal „nicht anlegen“
    ersetzen = abgleich.entscheiden(plan, abgleich.ERSETZEN, {}, aktionen)
    assert ersetzen.fehlt == {"3": "loeschen"}
    # Auf der Seite gewählt: nur die Ergänzung, Dublette ist dieselbe
    wahl = {"f-0-tel": "1", "n-2": "gleich", "f-2-ort": "1", "w-0": "behalten"}
    e = abgleich.entscheiden(plan, abgleich.AKTUALISIEREN, wahl, aktionen)
    assert e.aendern == {"1": {"tel": "01"}, "2": {"ort": "Dorf"}} and e.fehlt == {}


# --- Ausgabestellen ---------------------------------------------------------------------


def test_ausgabestellen_ergaenzen_aktualisieren_loeschen(admin_client):
    Ausgabestelle.objects.create(name="Nord", ort="Essen", telefon="")
    Ausgabestelle.objects.create(name="Alt")
    benutzt = Ausgabestelle.objects.create(name="Benutzt")
    Kundengruppe.objects.create(name="G", ausgabestelle=benutzt)
    datei = csv_datei(
        "stellen.csv",
        "Ausgabestelle;Ort;Telefon;E-Mail",
        "Nord;Bochum;0201 1;kaputt",
        "Süd;Hagen;;",
    )
    sitzung = hochladen(admin_client, "ausgabestellen", datei)
    weiter(admin_client, sitzung)
    url = reverse("datenimport:abgleich", args=[sitzung.pk])
    inhalt = admin_client.get(url + "?modus=ersetzen").content.decode()
    assert "Konflikt" in inhalt and "keine gültige E-Mail" in inhalt
    assert "Nicht mehr in der Datei (2)" in inhalt
    sitzung.refresh_from_db()
    fehlt = [e["name"] for e in sitzung.plan["fehlt"]]
    wahl = {f"w-{i}": "loeschen" for i in range(len(fehlt))}
    # Ort (Konflikt) nicht übernehmen, Telefon (Ergänzung) schon
    antwort = admin_client.post(url, {"modus": "ersetzen", "f-0-telefon": "1", **wahl})
    assert antwort.status_code == 302
    nord = Ausgabestelle.objects.get(name="Nord")
    assert (nord.ort, nord.telefon) == ("Essen", "0201 1")
    assert Ausgabestelle.objects.filter(name="Süd", ort="Hagen").exists()
    assert not Ausgabestelle.objects.filter(name="Alt").exists()
    assert PapierkorbEintrag.objects.filter(bezeichnung="Alt").exists()
    benutzt.refresh_from_db()
    assert not benutzt.aktiv  # hängt noch eine Kundengruppe daran: nur inaktiv
    assert not ImportSitzung.objects.exists()


def test_ausgabestellen_mit_ausstattung_zeiten_und_ansprechpartnern(admin_client):
    from apps.kunden.models import AusgabestelleZeit

    Ausgabestelle.objects.create(name="Nord")
    datei = csv_datei(
        "stellen.csv",
        "Name;Plätze;Helfer;Barrierefrei;WLAN;Ausgabezeit;Telefon für Kunden;Fax;"
        "Ansprechpartner 1: Name;Ansprechpartner 1: Telefon;Ansprechpartner 1: E-Mail;"
        "Ansprechpartner 2: Name",
        "Nord;30 Plätze;7;ja;nein;Di 13:00, Do 14.00 Uhr;0170 1111111;0201 9;Erika Muster;"
        "0201 12345;erika@example.org;Max Beispiel",
        "Süd;abc;;;;Montag;;;;;;",
    )
    sitzung = hochladen(admin_client, "ausgabestellen", datei)
    zuordnen = admin_client.get(reverse("datenimport:zuordnen", args=[sitzung.pk])).content.decode()
    # Beispiele untereinander, je einer aus einer Zeile – nicht „Nord · Süd“ in einer Reihe
    assert '<ul class="import-beispiele"><li>Nord</li><li>Süd</li></ul>' in zuordnen
    weiter(admin_client, sitzung)
    url = reverse("datenimport:abgleich", args=[sitzung.pk])
    inhalt = admin_client.get(url + "?modus=aktualisieren").content.decode()
    assert "keine Zahl" in inhalt and "nicht lesbar" in inhalt
    alle = {f"f-0-{z}": "1" for z in sitzung.tabellen[0]["zuordnung"]}
    assert admin_client.post(url, {"modus": "aktualisieren", **alle}).status_code == 302
    nord = Ausgabestelle.objects.get(name="Nord")
    assert (nord.plaetze, nord.helfer, nord.barrierefrei, nord.wlan) == (30, 7, True, "nein")
    assert (nord.telefon_kunden, nord.fax) == ("0170 1111111", "0201 9")
    assert [str(z) for z in nord.zeiten.all()] == ["Dienstag 13:00 Ausgabe",
                                                    "Donnerstag 14:00 Ausgabe"]  # fmt: skip
    assert [(k.name, k.telefon, k.email) for k in nord.kontakte.all()] == [
        ("Erika Muster", "0201 12345", "erika@example.org"), ("Max Beispiel", "", "")]  # fmt: skip
    sued = Ausgabestelle.objects.get(name="Süd")
    assert sued.plaetze is None and not sued.zeiten.exists()
    # Ein zweiter Import mit denselben Zeiten legt nichts doppelt an
    zweite = csv_datei("s.csv", "Name;Ausgabezeit;Ansprechpartner 1: Telefon",
                       "Nord;Di 13:00;0201 55555")  # fmt: skip
    sitzung = hochladen(admin_client, "ausgabestellen", zweite)
    weiter(admin_client, sitzung)
    url = reverse("datenimport:abgleich", args=[sitzung.pk])
    admin_client.post(url, {"modus": "aktualisieren", "f-0-kontakt1_telefon": "1"})
    assert AusgabestelleZeit.objects.filter(ausgabestelle=nord).count() == 2
    assert nord.kontakte.first().telefon == "0201 55555"
    html = admin_client.get(reverse("kunden:ausgabestelle", args=[nord.pk])).content.decode()
    assert "30 Haushalte je Ausgabe" in html and "Telefon für Kunden" in html
    assert "kein WLAN" in html


def test_kundengruppen_importieren(admin_client):
    mitte = Ausgabestelle.objects.create(name="Mitte")
    Kundengruppe.objects.create(kuerzel="W11", name="Mitte Mo 12:30", maximum=40)
    datei = csv_datei(
        "gruppen.csv",
        "Kürzel;Gruppenname;Wochentage;Maximum;Beschreibung;Ausgabestellen;Farbe",
        "W11;Mitte Mo 12:30;MO;50;Montag 12:30-13:00;Mitte;Rot",
        "W12;Mitte Di 13:00;DI, DO;45;Dienstag 13:00;Mitte;Schwarz",
        "DOD;Dummygruppe;MO, DI, MI, DO, FR, SA, SO;150;Dummy;-;",
    )
    sitzung = hochladen(admin_client, "kundengruppen", datei)
    weiter(admin_client, sitzung)
    url = reverse("datenimport:abgleich", args=[sitzung.pk])
    inhalt = admin_client.get(url + "?modus=aktualisieren").content.decode()
    assert "Farbe" in inhalt and "Uhrzeit" in inhalt
    alle = {f"f-0-{z}": "1" for z in sitzung.tabellen[0]["zuordnung"]}
    antwort = admin_client.post(url, {"modus": "aktualisieren", **alle})
    assert antwort.url == reverse("kunden:liste", args=["kundengruppen"])
    w11 = Kundengruppe.objects.get(kuerzel="W11")
    assert (w11.maximum, w11.wochentage, w11.ausgabestelle, w11.farbe) == (50, "Mo", mitte, "rot")
    assert f"{w11.uhrzeit:%H:%M}" == "12:30"
    w12 = Kundengruppe.objects.get(kuerzel="W12")
    assert (w12.wochentage, w12.farbe, w12.maximum) == ("Di, Do", "", 45)
    dod = Kundengruppe.objects.get(kuerzel="DOD")
    assert dod.ausgabestelle is None and dod.wochentage == "Mo, Di, Mi, Do, Fr, Sa, So"
    assert dod.uhrzeit is None


# --- Mitarbeitende ----------------------------------------------------------------------


def test_mitarbeitende_aus_excel(admin_client, admin, django_user_model):
    vorhanden = django_user_model.objects.create_user(
        username="bmuster", first_name="Ben", last_name="Muster", email="ben@example.org"
    )
    gleicher_name = django_user_model.objects.create_user(
        username="cprobe", first_name="Carla", last_name="Probe"
    )
    weg = django_user_model.objects.create_user(username="weg", first_name="Willi")
    datei = excel_datei(
        "team.xlsx",
        {
            "Team": [
                ["Mitarbeiterliste"],
                ["Vorname", "Name", "E-Mail", "Straße", "Nr.", "PLZ", "Ort", "Rolle", "Geburtstag"],
                [
                    "Anna",
                    "Neu",
                    "anna@example.org",
                    "Weg",
                    5,
                    "12345",
                    "Dorf",
                    "Fahrer, Chef",
                    dt.datetime(1990, 2, 1),
                ],
                ["Ben", "Muster", "BEN@example.org", "Gasse 1", None, "45127", "Essen", "", None],
                ["Carla", "Probe", "", "", None, "", "", "", None],
            ]
        },
    )
    sitzung = hochladen(admin_client, "mitarbeitende", datei)
    t = sitzung.tabellen[0]
    assert t["kopf"] == 1  # Titelzeile übersprungen
    assert t["zuordnung"][4] == "" and t["zuordnung"][3] == "strasse"
    weiter(admin_client, sitzung, **{"z-0-4": "strasse"})  # Hausnummer zur Straße
    url = reverse("datenimport:abgleich", args=[sitzung.pk])
    inhalt = admin_client.get(url).content.decode()
    assert "Mögliche Dublette" in inhalt and "gleicher Name" in inhalt
    sitzung.refresh_from_db()
    plan = abgleich.vorgaben(sitzung.plan, abgleich.AKTUALISIEREN, ZIELE["mitarbeitende"].aktionen)
    felder = {f"f-{e['i']}-{f['feld']}": "1" for e in plan["geaendert"] for f in e["felder"]}
    i_weg = next(i for i, e in enumerate(plan["fehlt"]) if e["id"] == str(weg.pk))
    admin_client.post(url, {"modus": "aktualisieren", **felder, f"w-{i_weg}": "sperren"})

    anna = django_user_model.objects.get(email="anna@example.org")
    assert anna.username == "anna.neu" and not anna.has_usable_password()
    assert list(anna.groups.values_list("name", flat=True)) == [rollen.FAHRER]
    sd = Stammdaten.objects.get(benutzer=anna)
    assert (sd.strasse, sd.plz, sd.ort, sd.geburtsdatum) == (
        "Weg 5",
        "12345",
        "Dorf",
        dt.date(1990, 2, 1),
    )
    vorhanden.refresh_from_db()
    assert vorhanden.stammdaten.ort == "Essen"  # über die E-Mail erkannt, ergänzt
    assert django_user_model.objects.filter(first_name="Carla").count() == 1  # Dublette aus
    assert gleicher_name.is_active
    weg.refresh_from_db()
    assert not weg.is_active
    admin.refresh_from_db()
    assert admin.is_active  # das eigene Konto steht nie zur Wahl


def test_ohne_recht_kein_ziel(client, admin, benutzer_mit_rolle, anmelden, recht_geben):
    anmelden(client, benutzer_mit_rolle("aus", rollen.AUSGABE))
    assert client.get(START).status_code == 403
    recht_geben(rollen.AUSGABE, "einstellungen.listen")
    inhalt = client.get(START).content.decode()
    assert "Ausgabestellen" in inhalt and "Mitarbeitende –" not in inhalt
    antwort = client.post(
        START, {"ziel": "mitarbeitende", "dateien": [csv_datei("a.csv", "Vorname;Name", "A;B")]}
    )
    assert antwort.status_code == 403


# --- Kundenstamm ------------------------------------------------------------------------


def _haushalt(nummer, vorname, nachname, **felder):
    h = Haushalt.objects.create(kundennummer=nummer, **felder)
    Person.objects.create(
        haushalt=h,
        ist_hauptperson=True,
        vorname=vorname,
        nachname=nachname,
        geburtsdatum=dt.date(1970, 1, 1),
    )
    return h


def test_kunden_ueber_assistenten_ergaenzen(admin_client, sicherung):
    _haushalt("1", "Anna", "Alt", ort="Essen", telefon="", kontostand=Decimal("1.00"))
    _haushalt("2", "Ben", "Bleibt", geaendert_am=timezone.now(), ort="Hagen")
    _haushalt("3", "Carla", "Fehlt")
    datei = excel_datei(
        "kunden.xlsx",
        {
            "Kunden": [
                ["Kd.-Nr.", "Name", "Vorname", "Wohnort", "Tel.", "Guthaben", "Geb.-Datum"],
                ["1", "Alt", "Anna", "Bochum", "0201 5", 2.5, dt.datetime(1970, 1, 1)],
                ["2", "Bleibt", "Ben", "Dortmund", "", None, None],
                ["9", "Fehlt", "Carla", "", "", None, dt.datetime(1970, 1, 1)],
                ["10", "Neu", "Dora", "Herne", "", None, None],
            ]
        },
    )
    sitzung = hochladen(admin_client, "kunden", datei)
    assert sitzung.tabellen[0]["art"] == "haushalte.csv"
    antwort = weiter(admin_client, sitzung)
    assert antwort.status_code == 302 and "/kunden/import/" in antwort["Location"]
    vorschau = antwort["Location"]
    inhalt = admin_client.get(vorschau).content.decode()
    assert "Kundenstamm ergänzen" in inhalt and "Konflikt" in inhalt
    assert "Mögliche Dublette" in inhalt  # 9 sieht aus wie 3
    assert "in bintafeln geändert am" in inhalt
    assert "Haushalte, die nicht mehr" not in inhalt  # Vollaustausch-Hinweise fehlen hier
    from apps.kunden import import_ergaenzen
    from apps.kunden.models import ImportVorbereitung

    uebernehmen = reverse("kunden:import_uebernehmen", args=[ImportVorbereitung.objects.get().pk])

    plan = abgleich.vorgaben(
        import_ergaenzen.planen(ImportVorbereitung.objects.get().daten),
        abgleich.AKTUALISIEREN,
        import_ergaenzen.AKTIONEN,
    )
    wahl = {
        f"f-{e['i']}-{f['feld']}": "1" for e in plan["geaendert"] for f in e["felder"] if f["an"]
    }
    antwort = admin_client.post(uebernehmen, {"modus": "aktualisieren", **wahl})
    assert antwort.status_code == 302

    eins = Haushalt.objects.get(kundennummer="1")
    assert (eins.ort, eins.telefon, eins.kontostand) == ("Bochum", "0201 5", Decimal("2.50"))
    assert eins.buchungen.filter(bemerkung__contains="Import").exists()
    zwei = Haushalt.objects.get(kundennummer="2")
    assert zwei.ort == "Hagen"  # in bintafeln geändert: Konflikt nicht vorgewählt
    assert Haushalt.objects.filter(kundennummer="3").exists()  # fehlt: bleibt
    assert not Haushalt.objects.filter(kundennummer="9").exists()  # Dublette: nicht angelegt
    assert Haushalt.objects.get(kundennummer="10").hauptperson.vorname == "Dora"
    from apps.kunden.models import ImportLauf

    assert ImportLauf.objects.get().art == "aktualisieren"


def test_kunden_nur_neue_und_loeschen_waehlbar(admin_client, sicherung):
    _haushalt("1", "Anna", "Alt", ort="Essen")
    _haushalt("2", "Ben", "Weg")
    admin_client.post(
        reverse("kunden:import"),
        {
            "dateien": [
                csv_datei(
                    "haushalte.csv",
                    "kundennummer;nachname;vorname;ort",
                    "1;Alt;Anna;Bochum",
                    "5;Neu;Eva;",
                )
            ]
        },
    )
    from apps.kunden.models import ImportVorbereitung

    v = ImportVorbereitung.objects.get()
    inhalt = admin_client.get(reverse("kunden:import_vorschau", args=[v.pk]) + "?modus=neu")
    assert "Nur neue hinzufügen" in inhalt.content.decode()
    admin_client.post(
        reverse("kunden:import_uebernehmen", args=[v.pk]), {"modus": "neu", "w-0": "loeschen"}
    )
    assert Haushalt.objects.get(kundennummer="1").ort == "Essen"  # nur neue: unverändert
    assert Haushalt.objects.filter(kundennummer="5").exists()
    assert not Haushalt.objects.filter(kundennummer="2").exists()
    assert PapierkorbEintrag.objects.filter(kundennummer="2").exists()


def test_vollaustausch_entfallene_behalten(admin_client, sicherung):
    _haushalt("1", "Anna", "Alt")
    _haushalt("2", "Ben", "Bleibt")
    admin_client.post(
        reverse("kunden:import"),
        {"dateien": [csv_datei("haushalte.csv", "kundennummer;nachname;vorname", "1;Alt;Anna")]},
    )
    from apps.kunden.models import ImportVorbereitung

    v = ImportVorbereitung.objects.get()
    inhalt = admin_client.get(
        reverse("kunden:import_vorschau", args=[v.pk]) + "?modus=vollaustausch"
    ).content.decode()
    assert 'name="wahl_2" value="behalten"' in inhalt
    admin_client.post(
        reverse("kunden:import_uebernehmen", args=[v.pk]),
        {"modus": "vollaustausch", "wahl_2": "behalten"},
    )
    assert set(Haushalt.objects.values_list("kundennummer", flat=True)) == {"1", "2"}


# --- Adressbuch und Mitglieder ----------------------------------------------------------


def _alles_uebernehmen(client, sitzung, modus="aktualisieren", **extra):
    """Abgleich absenden, alle vorgeschlagenen Haken gesetzt."""
    sitzung.refresh_from_db()
    ziel = ZIELE[sitzung.ziel]
    plan = abgleich.vorgaben(sitzung.plan, modus, ziel.aktionen)
    wahl = {
        f"f-{e['i']}-{f['feld']}": "1" for e in plan["geaendert"] for f in e["felder"] if f["an"]
    }
    return client.post(
        reverse("datenimport:abgleich", args=[sitzung.pk]), {"modus": modus, **wahl, **extra}
    )


def test_adressbuch_aus_excel(admin_client):
    from apps.adressen.models import Adresse, AdressKategorie
    from apps.mitglieder.models import Mitglied

    markt = Adresse.objects.create(organisation="Markt Nord", email="markt@example.org")
    markt.kategorien.add(AdressKategorie.objects.create(name="Lebensmittel"))
    weg = Adresse.objects.create(art="person", vorname="Willi", nachname="Weg")
    mitglied = Adresse.objects.create(art="person", vorname="Mia", nachname="Mitglied")
    Mitglied.objects.create(adresse=mitglied, nummer="1", art="x", eintritt=dt.date(2020, 1, 1))
    datei = excel_datei(
        "adressen.xlsx",
        {
            "Adressen": [
                ["Firma", "Name", "Vorname", "E-Mail", "Telefon", "Kategorie", "Newsletter"],
                ["Markt Nord", "", "", "MARKT@example.org", "0201 9", "Spender; Presse", "ja"],
                ["", "Neu", "Nina", "", "", "Spender", ""],
            ]
        },
    )
    sitzung = hochladen(admin_client, "adressen", datei)
    assert sitzung.tabellen[0]["zuordnung"][:2] == ["organisation", "nachname"]
    weiter(admin_client, sitzung)
    sitzung.refresh_from_db()
    fehlt = [e["name"] for e in sitzung.plan["fehlt"]]
    assert set(fehlt) == {"Willi Weg", "Mia Mitglied"}
    wahl = {f"w-{i}": "loeschen" for i in range(len(fehlt))}
    _alles_uebernehmen(admin_client, sitzung, "ersetzen", **wahl)
    markt.refresh_from_db()
    assert markt.telefon == "0201 9" and markt.einwilligung_email == timezone.localdate()
    assert sorted(k.name for k in markt.kategorien.all()) == ["Lebensmittel", "Presse", "Spender"]
    assert Adresse.objects.filter(nachname="Neu", art="person").exists()
    assert not Adresse.objects.filter(pk=weg.pk).exists()
    assert Adresse.objects.filter(pk=mitglied.pk).exists()  # Mitgliedschaft hängt daran


def test_mitglieder_mit_vorhandener_adresse(admin_client):
    from apps.adressen.models import Adresse
    from apps.mitglieder.models import Mitglied

    alt = Mitglied.objects.create(
        adresse=Adresse.objects.create(art="person", vorname="Alma", nachname="Alt"),
        nummer="7",
        art="Ordentliches Mitglied",
        eintritt=dt.date(2010, 1, 1),
    )
    raus = Mitglied.objects.create(
        adresse=Adresse.objects.create(art="person", vorname="Rolf", nachname="Raus"),
        nummer="8",
        art="Ordentliches Mitglied",
        eintritt=dt.date(2010, 1, 1),
    )
    spender = Adresse.objects.create(
        art="person", vorname="Sina", nachname="Spender", email="sina@example.org"
    )
    datei = csv_datei(
        "mitglieder.csv",
        "Mitglieds-Nr.;Name;Vorname;E-Mail;Mitglied seit;Beitrag",
        "7;Alt;Alma;alma@example.org;01.01.2010;24",
        ";Spender;Sina;sina@example.org;01.03.2026;12,50",
    )
    sitzung = hochladen(admin_client, "mitglieder", datei)
    assert sitzung.tabellen[0]["zuordnung"] == [
        "nummer",
        "nachname",
        "vorname",
        "email",
        "eintritt",
        "jahresbeitrag",
    ]
    weiter(admin_client, sitzung)
    sitzung.refresh_from_db()
    i = next(i for i, e in enumerate(sitzung.plan["fehlt"]) if e["id"] == str(raus.pk))
    _alles_uebernehmen(admin_client, sitzung, **{f"w-{i}": "austritt"})
    alt.refresh_from_db()
    assert alt.adresse.email == "alma@example.org" and alt.jahresbeitrag == Decimal("24.00")
    neu = Mitglied.objects.get(adresse=spender)  # vorhandene Adresse weiterverwendet
    assert neu.eintritt == dt.date(2026, 3, 1) and neu.jahresbeitrag == Decimal("12.50")
    assert Adresse.objects.filter(nachname="Spender").count() == 1
    raus.refresh_from_db()
    assert raus.austritt == timezone.localdate()


# --- Kundenstamm: Kontobuchungen und Nachreichen in Teilen ------------------------------


def test_buchungen_im_vollaustausch():
    from apps.ausgabe import konto
    from apps.ausgabe.models import Buchung
    from apps.kunden import importieren

    heute = timezone.localdate()
    dateien = {
        "haushalte.csv": b"kundennummer;nachname;vorname\n1;A;B\n",
        "buchungen.csv": (
            "kundennummer;datum;betrag;art\n"
            f"1;{heute:%d.%m.%Y};5,00;einzahlung\n"
            f"1;{heute:%d.%m.%Y};-1,50;\n"
            "1;01.01.2000;3;einzahlung\n"
        ).encode(),
    }
    ergebnis = importieren.pruefen(dateien)
    texte = [m["text"] for m in ergebnis.bericht]
    assert any("aus den Buchungen berechnet" in t for t in texte)
    assert any("Aufbewahrungsfrist" in t for t in texte)
    for _ in range(2):  # wiederholter Import ersetzt, verdoppelt nicht
        importieren.uebernehmen(
            importieren.pruefen(dateien).daten,
            benutzer=None,
            dateien=[],
            pruefsumme="",
            anzahl_warnungen=0,
        )
    h = Haushalt.objects.get()
    assert h.kontostand == Decimal("3.50")
    assert sorted(b.art for b in h.buchungen.all()) == ["abholung", "einzahlung"]
    konto.einzahlen(h, Decimal("1"), None, "")  # in bintafeln gebucht: bleibt für die Kasse
    importieren.uebernehmen(
        importieren.pruefen(dateien).daten,
        benutzer=None,
        dateien=[],
        pruefsumme="",
        anzahl_warnungen=0,
    )
    assert Buchung.objects.filter(importiert=False).count() == 1
    assert Buchung.objects.filter(importiert=True).count() == 2


def test_kunden_in_teilen_nachreichen(admin_client, sicherung):
    from apps.ausgabe.models import Buchung
    from apps.kunden.models import Abholung, ImportVorbereitung

    _haushalt("1", "Anna", "Alt")
    heute = timezone.localdate()
    teil2 = [
        csv_datei(
            "abholungen.csv",
            "kundennummer;datum",
            f"1;{heute:%d.%m.%Y}",
            f"1;{heute - dt.timedelta(days=7):%d.%m.%Y}",
        ),
        csv_datei("personen.csv", "kundennummer;nachname;vorname;geburtsdatum", "1;Alt;Kai;"),
        csv_datei("buchungen.csv", "kundennummer;datum;betrag", f"1;{heute:%d.%m.%Y};2"),
    ]
    for durchgang in range(2):  # zweimal: nichts doppelt
        admin_client.post(reverse("kunden:import"), {"dateien": teil2})
        for d in teil2:
            d.seek(0)
        v = ImportVorbereitung.objects.get()
        assert v.daten["nur_ergaenzen"]
        inhalt = admin_client.get(
            reverse("kunden:import_vorschau", args=[v.pk]) + "?modus=vollaustausch"
        ).content.decode()
        assert "Kundenstamm ergänzen" in inhalt and "?modus=vollaustausch" not in inhalt
        admin_client.post(
            reverse("kunden:import_uebernehmen", args=[v.pk]), {"modus": "vollaustausch"}
        )
        assert Haushalt.objects.count() == 1, durchgang
    h = Haushalt.objects.get()
    assert Abholung.objects.filter(haushalt=h).count() == 2
    assert h.personen.count() == 2
    assert Buchung.objects.filter(haushalt=h, importiert=True).count() == 1


def test_leere_haushalte_liste_im_assistenten(admin_client, sicherung):
    """Nur Überschriften: im Assistenten wie beim Importformat ein gültiger Vollaustausch."""
    from apps.kunden.models import ImportVorbereitung

    _haushalt("1", "Anna", "Alt")
    sitzung = hochladen(
        admin_client, "kunden", csv_datei("haushalte.csv", "Kundennummer;Vorname;Nachname")
    )
    antwort = weiter(admin_client, sitzung)
    assert antwort.status_code == 302, antwort.content.decode()[:3000]
    v = ImportVorbereitung.objects.get()
    admin_client.post(reverse("kunden:import_uebernehmen", args=[v.pk]), {"modus": "vollaustausch"})
    assert not Haushalt.objects.exists()
