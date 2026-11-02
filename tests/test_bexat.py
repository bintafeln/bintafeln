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
                    "Ehrenamt",
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
    assert [m["nachname"] for m in ma] == ["Ehrenamt"]  # nur aktive
    assert ma[0]["ausgabestellen"] == "Innenstadt" and ma[0]["handy"] == "0171 9"


def test_umwandeln_ohne_zuordnung_hinweis():
    # income_id vorhanden, aber keine Zuordnung -> Hinweis, Einkommensart bleibt leer
    umw = konvertieren.umwandeln(_beispiel())
    assert any("Einkommensarten" in h for h in umw.hinweise)
    assert _lesen(umw.kundenstamm["haushalte.csv"])[0]["einkommensart"] == ""


def test_umwandeln_unlesbare_datei():
    with pytest.raises(konvertieren.BexatFehler):
        konvertieren.umwandeln(b"keine excel-datei")


def test_text_entfernt_steuerzeichen():
    # NUL u. a. Steuerzeichen (die PostgreSQL nicht als Text speichern kann) werden entfernt.
    assert konvertieren._text("Helfer\x00") == "Helfer"
    assert konvertieren._text("a\x1fb") == "ab"


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


def test_start_ohne_datei_meldung(admin_client):
    _modul_an()
    antwort = admin_client.post(reverse("bexat:start"), {"ziel": "kunden"})
    assert antwort.status_code == 200
    assert "auswählen" in antwort.content.decode()


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
