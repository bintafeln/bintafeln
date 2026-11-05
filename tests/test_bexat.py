"""Bexat-Import-Modul (ADR 0094). Alle Daten sind erfunden."""

import datetime as dt
import io

import openpyxl
import pytest
from django.urls import reverse

from apps.bexat import konvertieren
from apps.bexat.models import BexatEinstellungen

pytestmark = pytest.mark.django_db


def _xlsx(blaetter: dict[str, list[list]]) -> bytes:
    """Baut eine Bexat-ähnliche .xlsx aus {Blattname: [Kopfzeile, Datenzeilen …]}."""
    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    for name, zeilen in blaetter.items():
        ws = wb.create_sheet(name)
        for zeile in zeilen:
            ws.append(zeile)
    puffer = io.BytesIO()
    wb.save(puffer)
    return puffer.getvalue()


def _lesen(inhalt: bytes) -> list[dict]:
    import csv

    text = inhalt.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(text), delimiter=";"))


def _beispiel() -> bytes:
    return _xlsx(
        {
            "offices": [["id", "title"], [1, "Innenstadt"]],
            "clientgroups": [
                ["id", "short", "title", "offices", "weekday", "description", "max"],
                [10, "MO", "Montagsgruppe", "[1]", "mo", "Montag 12:00-13:00", 50],
            ],
            "households": [
                [
                    "id",
                    "clientgroup_id",
                    "income_id",
                    "valid",
                    "household_since",
                    "lastvisit",
                    "field6",
                    "deleted_at",
                ],
                [8034, 10, 6, "2026-12-31", "2020-05-01", "2026-10-01", "Ja", None],
                [9999, 10, 6, "2026-12-31", "2019-01-01", "2026-09-01", "nein", "2025-01-01"],
            ],
            "persons": [
                [
                    "id",
                    "title",
                    "firstname",
                    "lastname",
                    "street",
                    "zipcode",
                    "city",
                    "birthday",
                    "nationality_id",
                    "telprivat",
                    "telmobil",
                    "email",
                ],
                [
                    1,
                    "herr",
                    "Max",
                    "Mustermann",
                    "Hauptstr. 1",
                    "45127",
                    "Essen",
                    "1980-03-04",
                    37,
                    "0201 1",
                    "0170 1",
                    "max@example.org",
                ],
                [2, "frau", "Erika", "Mustermann", "", "", "", "2015-06-07", 37, "", "", ""],
                [3, "", "Olaf", "Helfer", "", "", "", "1990-01-01", 37, "", "", ""],
                [
                    50,
                    "herr",
                    "Heinz",
                    "EHRENAMT",
                    "Gasse 2",
                    "45128",
                    "Essen",
                    "1960-02-02",
                    37,
                    "0201 9",
                    "0171 9",
                    "heinz@example.org",
                ],
            ],
            "household_person": [
                ["household_id", "person_id", "type", "deleted_at"],
                [8034, 1, "householder", None],
                [8034, 2, "relative", None],
                [8034, 3, "collector", None],
                [9999, 1, "householder", None],
            ],
            "receptions": [
                ["household_id", "date", "time", "fee", "office_id"],
                [8034, "2026-10-01", "12:12:00", "1.50", 1],
                [9999, "2026-09-01", "12:00:00", "1.50", 1],
            ],
            "locks": [
                ["household_id", "lock_from", "lock_until", "reason"],
                [8034, "2026-06-10", "2026-06-01", "Vertauscht"],
            ],
            "exceptions": [["household_id", "date", "reason"], [8034, "2026-07-01", "Urlaub"]],
            "notes": [
                ["household_id", "created_at", "text"],
                [8034, "2026-05-01", "Eine Anmerkung"],
            ],
            "applications": [
                [
                    "id",
                    "status",
                    "firstname",
                    "lastname",
                    "title",
                    "birthday",
                    "street",
                    "zipcode",
                    "city",
                    "telmobil",
                    "email",
                    "nationality_id",
                    "weekday",
                    "message",
                    "comment",
                    "relatives",
                    "nameRelatives",
                    "created_at",
                ],
                [
                    4243,
                    0,
                    "Neu",
                    "Antrag",
                    "frau",
                    "1992-02-02",
                    "Weg 3",
                    "45130",
                    "Essen",
                    "0176 3",
                    "neu@example.org",
                    37,
                    "di",
                    "Bitte um Hilfe",
                    "intern geprüft",
                    "",
                    "Kind 01.01.2018",
                    dt.datetime(2026, 8, 1, 9, 30),
                ],
                [
                    4244,
                    1,
                    "Erledigt",
                    "Antrag",
                    "herr",
                    "1970-01-01",
                    "",
                    "",
                    "",
                    "",
                    "",
                    37,
                    "",
                    "",
                    "",
                    "",
                    "",
                    "2026-01-01",
                ],
            ],
            "staff": [
                ["id", "person_id", "office_id", "active", "staff_since"],
                [500, 50, 1, 1, "2021-01-01"],
                [501, 2, 1, 0, "2020-01-01"],
            ],
            "staff_offices": [["staff_id", "office_id"], [500, 1]],
        }
    )


def test_umwandeln_kundenstamm():
    umw = konvertieren.umwandeln(_beispiel(), einkommensarten={"6": "Rente"})
    haushalte = _lesen(umw.kundenstamm["haushalte.csv"])
    assert len(haushalte) == 1  # der gelöschte Haushalt 9999 kommt nicht mit
    h = haushalte[0]
    assert h["kundennummer"] == "08034"  # fünfstellig mit führenden Nullen
    assert (h["vorname"], h["nachname"]) == ("Max", "Mustermann")  # Vorstand, nicht Angehörige
    assert h["anrede"] == "Herr" and h["staatsangehoerigkeit"] == "Deutschland"
    assert h["kundengruppe"] == "MO" and h["ausgabestelle"] == "Innenstadt"
    assert h["einkommensart"] == "Rente" and h["zusatz_schwerbehindert"] == "ja"
    assert h["telefon"] == "0201 1"

    personen = _lesen(umw.kundenstamm["personen.csv"])
    assert [p["vorname"] for p in personen] == ["Erika"]
    abholer = _lesen(umw.kundenstamm["abholer.csv"])
    assert abholer[0]["nachname"] == "Helfer"

    abholungen = _lesen(umw.kundenstamm["abholungen.csv"])
    assert len(abholungen) == 1  # nur zum exportierten Haushalt
    assert abholungen[0]["uhrzeit"] == "12:12" and abholungen[0]["beitrag"] == "1,50"

    sperren = _lesen(umw.kundenstamm["sperren.csv"])
    assert (sperren[0]["von"], sperren[0]["bis"]) == ("01.06.2026", "10.06.2026")  # getauscht
    assert _lesen(umw.kundenstamm["ausnahmen.csv"])[0]["datum"] == "01.07.2026"
    assert _lesen(umw.kundenstamm["bemerkungen.csv"])[0]["text"] == "Eine Anmerkung"
    gruppen = _lesen(umw.kundenstamm["kundengruppen.csv"])
    assert gruppen[0]["ausgabestelle"] == "Innenstadt" and gruppen[0]["wochentage"] == "Mo"
    assert umw.zusammenfassung["haushalte"] == 1


def test_umwandeln_antraege_nur_offene():
    umw = konvertieren.umwandeln(_beispiel())
    antraege = _lesen(umw.antraege)
    assert [a["nachname"] for a in antraege] == ["Antrag"]  # nur der offene (status 0)
    a = antraege[0]
    assert a["laufnummer"] == "4243" and a["eingegangen_am"] == "01.08.2026 09:30"
    assert a["nachricht"] == "Bitte um Hilfe" and a["anmerkung"] == "intern geprüft"
    assert a["angehoerige"] == "Kind 01.01.2018" and a["wochentage"] == "Di"


def test_umwandeln_mitarbeitende():
    umw = konvertieren.umwandeln(_beispiel())
    ma = _lesen(umw.mitarbeitende)
    assert [m["nachname"] for m in ma] == ["Ehrenamt"]  # nur aktive; „EHRENAMT“ lesbar gemacht
    assert ma[0]["ausgabestellen"] == "Innenstadt" and ma[0]["handy"] == "0171 9"


def test_umwandeln_ohne_zuordnung_hinweis():
    # income_id vorhanden, aber keine Zuordnung -> Hinweis, Einkommensart bleibt leer
    umw = konvertieren.umwandeln(_beispiel())
    assert any("Einkommensarten" in h for h in umw.hinweise)
    assert _lesen(umw.kundenstamm["haushalte.csv"])[0]["einkommensart"] == ""


def test_umwandeln_unlesbare_datei():
    with pytest.raises(konvertieren.BexatFehler):
        konvertieren.umwandeln(b"keine excel-datei")


def _besuche_xlsx() -> bytes:
    """Tagesreport „kunden die da waren“: Titelzeile, Kopfzeile, dann Datenzeilen (nur Nummern)."""
    return _xlsx(
        {
            "Sheet1": [
                ["Bexat Tafelprogramm - kunden die da waren"],
                ["#", "Kundennummer", "Kundengruppe", "Letzter Besuch", "Uhrzeit",
                 "Tafelausweis gültig", "Kontostand", "Beitrag"],
                [1, "01294", "kleiner Markt Do (DO)", "05.11.2026", "16:09", "30.04.2027",
                 "0,00 €", "3 €"],
                [2, "02015", "kleiner Markt Do (DO)", "05.11.2026", "12:15", "31.03.2027",
                 "0,00 €", "1,5 €"],
                [3, "02268", "Treff24 Do (DO)", "", "14:11", "31.01.2027", "0,00 €", "1,5 €"],
            ]
        }
    )  # fmt: skip


def test_besuche_umwandeln():
    umw = konvertieren.besuche_umwandeln(_besuche_xlsx())
    zeilen = _lesen(umw.abholungen)
    assert umw.anzahl == 2  # die Zeile ohne „Letzter Besuch“ wird übersprungen
    assert any("1 Zeile" in h for h in umw.hinweise)
    assert [z["kundennummer"] for z in zeilen] == ["01294", "02015"]
    assert zeilen[0] == {"kundennummer": "01294", "datum": "05.11.2026",
                         "uhrzeit": "16:09", "beitrag": "3"}  # fmt: skip
    assert zeilen[1]["beitrag"] == "1,5"  # „1,5 €“ → „1,5“


def test_besuche_umwandeln_falsches_blatt():
    # Datei ohne Spalte „Kundennummer“ (z. B. der volle Export) → klare Meldung.
    with pytest.raises(konvertieren.BexatFehler, match="Kundennummer"):
        konvertieren.besuche_umwandeln(_xlsx({"persons": [["id", "firstname"], [1, "A"]]}))


def test_besuche_betrag_report():
    assert konvertieren._betrag_report("3 €") == "3"
    assert konvertieren._betrag_report("1,5 €") == "1,5"
    assert konvertieren._betrag_report("2.50") == "2,50"
    assert konvertieren._betrag_report(None) == ""


def test_text_entfernt_steuerzeichen():
    # NUL u. a. Steuerzeichen (die PostgreSQL nicht als Text speichern kann) werden entfernt.
    assert konvertieren._text("Helfer\x00") == "Helfer"
    assert konvertieren._text("a\x1fb") == "ab"


def test_name_gross_wird_lesbar():
    # Komplett groß geschriebene Namen aus dem Altsystem werden lesbar; bewusste Schreibweisen
    # (Kleinbuchstaben vorhanden) bleiben.
    assert konvertieren._name("BRÜGGE") == "Brügge"
    assert konvertieren._name("BUERS") == "Buers"
    assert konvertieren._name("AYDIN-BICER") == "Aydin-Bicer"
    assert konvertieren._name("McDonald") == "McDonald"  # hat Kleinbuchstaben → bleibt
    assert konvertieren._name("van Berg") == "van Berg"
    assert konvertieren._name("") == ""


def _modul_an():
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.module = ["bexat"]
    t.save()


def test_start_kundenstamm_leitet_zum_abgleich(admin_client):
    from apps.kunden.models import ImportVorbereitung

    _modul_an()
    datei = io.BytesIO(_beispiel())
    datei.name = "export.xlsx"
    antwort = admin_client.post(reverse("bexat:start"), {"ziel": "kunden", "datei": datei})
    assert antwort.status_code == 302 and "/kunden/" in antwort["Location"]
    assert ImportVorbereitung.objects.count() == 1


def test_start_antraege_download(admin_client):
    _modul_an()
    datei = io.BytesIO(_beispiel())
    datei.name = "export.xlsx"
    antwort = admin_client.post(reverse("bexat:start"), {"ziel": "antraege", "datei": datei})
    assert antwort["Content-Type"].startswith("text/csv")
    assert "antraege.csv" in antwort["Content-Disposition"]
    assert "Antrag" in antwort.content.decode("utf-8-sig")


def test_start_besuche_download(admin_client):
    _modul_an()
    datei = io.BytesIO(_besuche_xlsx())
    datei.name = "kunden-die-da-waren.xlsx"
    antwort = admin_client.post(reverse("bexat:start"), {"ziel": "besuche", "datei": datei})
    assert antwort["Content-Type"].startswith("text/csv")
    assert "abholungen.csv" in antwort["Content-Disposition"]
    zeilen = _lesen(antwort.content)
    assert [z["kundennummer"] for z in zeilen] == ["01294", "02015"]
    assert zeilen[0]["datum"] == "05.11.2026" and zeilen[0]["beitrag"] == "3"


def test_start_ohne_datei_meldung(admin_client):
    _modul_an()
    antwort = admin_client.post(reverse("bexat:start"), {"ziel": "kunden"})
    assert antwort.status_code == 200
    assert "auswählen" in antwort.content.decode()


def test_aktivieren_legt_an_und_schaltet_ein():
    from apps.kunden import merkmale
    from apps.kunden.models import Zusatzfeld

    # fehlt ganz → wird angelegt und aktiv
    Zusatzfeld.objects.filter(schluessel="schwerbehindert").delete()
    assert merkmale.aktivieren("schwerbehindert") == ["Schwerbehindert"]
    assert Zusatzfeld.objects.get(schluessel="schwerbehindert").aktiv
    # schon aktiv → nichts zu melden
    assert merkmale.aktivieren("schwerbehindert") == []
    # abgeschaltet → wieder einschalten
    Zusatzfeld.objects.filter(schluessel="schwerbehindert").update(aktiv=False)
    assert merkmale.aktivieren("schwerbehindert") == ["Schwerbehindert"]
    assert Zusatzfeld.objects.get(schluessel="schwerbehindert").aktiv


def test_start_aktiviert_merkmal_schwerbehindert(admin_client):
    """Ein abgeschaltetes Merkmal „Schwerbehindert" wird vor dem Import wieder eingeschaltet, damit
    die Spalte zusatz_schwerbehindert nicht stillschweigend übersprungen wird."""
    from apps.kunden.models import Zusatzfeld

    _modul_an()
    Zusatzfeld.objects.filter(schluessel="schwerbehindert").update(aktiv=False)
    datei = io.BytesIO(_beispiel())
    datei.name = "export.xlsx"
    antwort = admin_client.post(reverse("bexat:start"), {"ziel": "kunden", "datei": datei})
    assert antwort.status_code == 302
    assert Zusatzfeld.objects.get(schluessel="schwerbehindert").aktiv


def test_einstellungen_speichern(admin_client):
    _modul_an()
    antwort = admin_client.post(
        reverse("bexat:einstellungen"),
        {"ausgabestellen": "1 = Innenstadt\nunfug", "einkommensarten": "6 = Rente\n7 = Lohn"},
    )
    assert antwort.status_code == 302
    e = BexatEinstellungen.laden()
    assert e.ausgabestellen == {"1": "Innenstadt"}  # „unfug“ ohne „=“ wird verworfen
    assert e.einkommensarten == {"6": "Rente", "7": "Lohn"}


def test_modul_aus_ist_gesperrt(admin_client):
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.module = []
    t.save()
    assert admin_client.get(reverse("bexat:start")).status_code == 404


def test_ohne_recht_kein_zugriff(client, admin, benutzer_mit_rolle, anmelden):
    from apps.konten import rollen

    _modul_an()  # admin sorgt dafür, dass ein Superuser existiert (keine Einrichtungs-Umleitung)
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(reverse("bexat:start")).status_code == 403


# ── Besuche & Konto nachtragen (ADR 0110) ────────────────────────────────────


def _besuche_konto_xlsx(kontostand="12,00 €", knr="01294", datum="05.11.2026") -> bytes:
    return _xlsx(
        {
            "Sheet1": [
                ["Bexat Tafelprogramm - Abholungen heute"],
                ["#", "Kundennummer", "Letzter Besuch", "Uhrzeit", "Kontostand", "Beitrag"],
                [1, knr, datum, "16:09", kontostand, "3 €"],
            ]
        }
    )


def test_besuche_konto_lesen_xlsx_und_csv():
    from decimal import Decimal

    from apps.bexat import besuche_konto

    z = besuche_konto.lesen(_besuche_konto_xlsx())[0]
    assert z.kundennummer == "01294" and str(z.datum) == "2026-11-05"
    assert z.uhrzeit.hour == 16 and z.betrag == Decimal("3") and z.kontostand == Decimal("12")
    csv_bytes = "Kundennummer;Datum;Kontostand;Beitrag\n01294;05.11.2026;12,00 €;3 €\n".encode(
        "utf-8-sig"
    )
    assert besuche_konto.lesen(csv_bytes)[0].kontostand == Decimal("12")


def test_besuche_konto_falsche_datei():
    from apps.bexat import besuche_konto

    with pytest.raises(besuche_konto.BesucheFehler, match="Kundennummer"):
        besuche_konto.lesen(b"Spalte;Wert\n1;2\n")


def test_besuche_konto_euro():
    from decimal import Decimal

    from apps.bexat import besuche_konto

    assert besuche_konto.euro(Decimal("1234.5")) == "1.234,50 €"
    assert besuche_konto.euro(Decimal("-3")) == "-3,00 €"


def test_besuche_konto_plan_und_uebernehmen():
    from decimal import Decimal

    from apps.bexat import besuche_konto
    from apps.kunden.models import Abholung, Haushalt

    h = Haushalt.objects.create(kundennummer="01294", kontostand=Decimal("0"))
    zeilen = besuche_konto.lesen(_besuche_konto_xlsx("12,00 €"))

    plan = besuche_konto.plan(zeilen)
    assert plan["besuche_neu"] == 1 and len(plan["konto"]) == 1
    assert plan["konto"][0]["ziel"] == "12,00 €" and plan["unbekannt"] == []

    erg = besuche_konto.uebernehmen(zeilen, "Büro")
    assert erg["besuche_neu"] == 1 and erg["korrekturen"] == 1
    h.refresh_from_db()
    assert h.kontostand == Decimal("12")  # Kontostand auf den Wert aus der Liste gesetzt
    a = Abholung.objects.get(haushalt=h)
    assert str(a.datum) == "2026-11-05" and a.beitrag == Decimal("3") and a.nachgetragen

    # Zweiter Lauf: Besuch schon da, Kontostand passt → nichts doppelt
    erg = besuche_konto.uebernehmen(zeilen, "Büro")
    assert erg["besuche_neu"] == 0 and erg["korrekturen"] == 0
    assert Abholung.objects.filter(haushalt=h).count() == 1
    h.refresh_from_db()
    assert h.kontostand == Decimal("12")


def test_besuche_konto_unbekannte_nummer():
    from apps.bexat import besuche_konto

    zeilen = besuche_konto.lesen(_besuche_konto_xlsx())  # kein Haushalt angelegt
    plan = besuche_konto.plan(zeilen)
    assert plan["unbekannt"] == ["01294"] and plan["besuche_neu"] == 0
    erg = besuche_konto.uebernehmen(zeilen, "Büro")
    assert erg["besuche_neu"] == 0 and erg["korrekturen"] == 0 and erg["unbekannt"] == ["01294"]


def test_besuche_konto_view_pruefen_und_uebernehmen(admin_client):
    from decimal import Decimal

    from apps.kunden.models import Abholung, Haushalt

    _modul_an()
    Haushalt.objects.create(kundennummer="01294", kontostand=Decimal("0"))
    datei = io.BytesIO(_besuche_konto_xlsx("12,00 €"))
    datei.name = "tag.xlsx"
    antwort = admin_client.post(
        reverse("bexat:besuche_konto"), {"aktion": "pruefen", "datei": datei},
        HTTP_HX_REQUEST="true",
    )  # fmt: skip
    inhalt = antwort.content.decode()
    assert "Probelauf" in inhalt and "12,00 €" in inhalt and "<html" not in inhalt

    datei = io.BytesIO(_besuche_konto_xlsx("12,00 €"))
    datei.name = "tag.xlsx"
    antwort = admin_client.post(
        reverse("bexat:besuche_konto"), {"aktion": "uebernehmen", "datei": datei}
    )
    assert antwort.status_code == 302
    h = Haushalt.objects.get(kundennummer="01294")
    assert h.kontostand == Decimal("12") and Abholung.objects.filter(haushalt=h).count() == 1


def test_besuche_konto_ohne_konto_recht_bucht_nicht(client, admin, benutzer_mit_rolle, anmelden):
    from decimal import Decimal

    from apps.konten import rollen
    from apps.konten.models import Rolle
    from apps.kunden.models import Abholung, Haushalt

    _modul_an()
    # Eine Rolle, die importieren darf, aber ausdrücklich NICHT das Konto korrigieren darf.
    rolle = Rolle.objects.get(gruppe__name=rollen.BUERO)
    rolle.rechte = sorted(
        {r for r in rolle.rechte if r != "konto.korrektur"} | {"kunden.importieren"}
    )
    rolle.save()
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    Haushalt.objects.create(kundennummer="01294", kontostand=Decimal("0"))
    datei = io.BytesIO(_besuche_konto_xlsx("12,00 €"))
    datei.name = "tag.xlsx"
    client.post(reverse("bexat:besuche_konto"), {"aktion": "uebernehmen", "datei": datei})
    h = Haushalt.objects.get(kundennummer="01294")
    assert h.kontostand == Decimal("0")  # nichts gebucht
    assert not Abholung.objects.filter(haushalt=h).exists()
