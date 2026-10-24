import datetime as dt

import pytest
from auditlog.models import LogEntry
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from apps.kunden import werte
from apps.kunden.models import (
    Abholer,
    Ausgabestelle,
    Bemerkung,
    Einkommensart,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Sperre,
    Zusatzfeld,
)

STICHTAG = dt.date(2026, 6, 15)


# --- Werte -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [("ja", True), ("JA", True), ("1", True), ("x", True), ("nein", False), ("", False)],
)
def test_ja_nein(text, erwartet):
    assert werte.ja_nein(text) is erwartet


def test_ja_nein_ungueltig():
    with pytest.raises(werte.UngueltigerWert):
        werte.ja_nein("vielleicht")


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("21.10.1966", dt.date(1966, 10, 21)),
        ("1966-10-21", dt.date(1966, 10, 21)),
        (" 01.02.2024 ", dt.date(2024, 2, 1)),
        ("", None),
        (None, None),
    ],
)
def test_datum(text, erwartet):
    assert werte.datum(text) == erwartet


@pytest.mark.parametrize("text", ["31.02.2024", "2024/01/01", "gestern"])
def test_datum_ungueltig(text):
    with pytest.raises(werte.UngueltigerWert):
        werte.datum(text)


# --- Zusatzfelder ------------------------------------------------------------------------


def feld(**werte_):
    standard = {"schluessel": "schwerbehindert", "bezeichnung": "Schwerbehindert"}
    return Zusatzfeld(**{**standard, **werte_})


def test_zusatzfeld_ja_nein():
    f = feld(typ=Zusatzfeld.Typ.JA_NEIN)
    assert f.wert_lesen("Ja") is True
    assert f.wert_lesen("nein") is False
    assert f.wert_lesen("  ") is None
    assert f.import_spalte == "zusatz_schwerbehindert"


def test_zusatzfeld_auswahl_und_text_und_datum():
    auswahl = feld(typ=Zusatzfeld.Typ.AUSWAHL, optionen="nein\nja\n\n ja, Merkzeichen G ")
    assert auswahl.optionen_liste() == ["nein", "ja", "ja, Merkzeichen G"]
    assert auswahl.wert_lesen("JA, merkzeichen g") == "ja, Merkzeichen G"
    with pytest.raises(werte.UngueltigerWert):
        auswahl.wert_lesen("vielleicht")
    assert feld(typ=Zusatzfeld.Typ.TEXT).wert_lesen(" frei ") == "frei"
    assert feld(typ=Zusatzfeld.Typ.DATUM).wert_lesen("01.02.2024") == "2024-02-01"


@pytest.mark.django_db
def test_zusatzfeld_auswahl_braucht_optionen():
    with pytest.raises(ValidationError):
        feld(typ=Zusatzfeld.Typ.AUSWAHL, optionen=" \n").full_clean()


@pytest.mark.django_db
@pytest.mark.parametrize("schluessel", ["Gross", "1abc", "mit-strich", "ä"])
def test_zusatzfeld_schluessel_ungueltig(schluessel):
    with pytest.raises(ValidationError):
        feld(schluessel=schluessel).full_clean()


@pytest.mark.django_db
def test_zusatzfeld_str_und_sortierung():
    Zusatzfeld.objects.create(schluessel="b", bezeichnung="B", reihenfolge=2)
    Zusatzfeld.objects.create(schluessel="a", bezeichnung="A", reihenfolge=1)
    assert [str(f) for f in Zusatzfeld.objects.all()] == ["A", "B"]


# --- Einstellungen -----------------------------------------------------------------------


@pytest.mark.django_db
def test_einstellungen_singleton_und_vorgaben():
    e = KundenEinstellungen.laden()
    assert e.kind_bis_alter == 18
    assert e.bemerkungen_importieren is False
    assert e.besondere_kategorie_fuer_ausgabe is False
    KundenEinstellungen(kind_bis_alter=16).save()
    assert KundenEinstellungen.objects.count() == 1
    assert KundenEinstellungen.laden().kind_bis_alter == 16
    assert str(e) == "Einstellungen Kundenstamm"


# --- Haushalt, Personen ------------------------------------------------------------------


@pytest.fixture
def haushalt(db):
    stelle = Ausgabestelle.objects.create(name="Ausgabestelle Mitte")
    gruppe = Kundengruppe.objects.create(kuerzel="MO1", name="Montag", ausgabestelle=stelle)
    return Haushalt.objects.create(
        kundennummer="00030",
        kundengruppe=gruppe,
        einkommensart=Einkommensart.objects.create(bezeichnung="Bürgergeld"),
    )


def test_alter_und_kind(haushalt):
    p = Person(haushalt=haushalt, vorname="Mia", nachname="Mustermann")
    assert p.alter(STICHTAG) is None
    assert not p.ist_kind(18, STICHTAG)
    p.geburtsdatum = dt.date(2008, 6, 16)  # wird am Folgetag 18
    assert p.alter(STICHTAG) == 17
    assert p.ist_kind(18, STICHTAG)
    p.geburtsdatum = dt.date(2008, 6, 15)
    assert p.alter(STICHTAG) == 18
    assert not p.ist_kind(18, STICHTAG)
    assert p.alter() is not None
    assert str(p) == "Mia Mustermann"


def test_groesse_aus_personen(haushalt):
    Person.objects.create(
        haushalt=haushalt,
        ist_hauptperson=True,
        vorname="Erika",
        nachname="Mustermann",
        geburtsdatum=dt.date(1968, 3, 12),
    )
    Person.objects.create(
        haushalt=haushalt, vorname="Mia", nachname="Mustermann", geburtsdatum=dt.date(2015, 8, 18)
    )
    Person.objects.create(haushalt=haushalt, vorname="Paul", nachname="Mustermann")
    assert haushalt.groesse(18, STICHTAG) == (2, 1)
    assert haushalt.hauptperson.vorname == "Erika"


def test_groesse_aus_anzahlen(haushalt):
    Person.objects.create(haushalt=haushalt, ist_hauptperson=True, vorname="E", nachname="M")
    haushalt.anzahl_erwachsene, haushalt.anzahl_kinder = 2, 3
    assert haushalt.groesse(18, STICHTAG) == (2, 3)
    haushalt.anzahl_erwachsene = None
    assert haushalt.groesse(18, STICHTAG) == (0, 3)


def test_groesse_ohne_angaben(haushalt):
    assert haushalt.groesse(18, STICHTAG) == (0, 0)


def test_nur_eine_hauptperson(haushalt):
    Person.objects.create(haushalt=haushalt, ist_hauptperson=True, vorname="A", nachname="B")
    with pytest.raises(IntegrityError), transaction.atomic():
        Person.objects.create(haushalt=haushalt, ist_hauptperson=True, vorname="C", nachname="D")


def test_kuerzel_eindeutig_aber_leer_mehrfach(db):
    Kundengruppe.objects.create(name="Ohne Kürzel 1")
    Kundengruppe.objects.create(name="Ohne Kürzel 2")
    Kundengruppe.objects.create(kuerzel="X1", name="Mit Kürzel")
    with pytest.raises(IntegrityError), transaction.atomic():
        Kundengruppe.objects.create(kuerzel="X1", name="Doppelt")


def test_str_darstellungen(haushalt):
    assert str(haushalt) == "Haushalt 00030"
    assert str(haushalt.kundengruppe) == "MO1 – Montag"
    assert str(Kundengruppe(name="Nur Name")) == "Nur Name"
    assert str(haushalt.kundengruppe.ausgabestelle) == "Ausgabestelle Mitte"
    assert str(haushalt.einkommensart) == "Bürgergeld"
    assert str(Abholer(vorname="Lena", nachname="Beispiel")) == "Lena Beispiel"
    assert str(Sperre(von=dt.date(2026, 3, 1))) == "Sperre ab 01.03.2026"
    assert str(Bemerkung(datum=dt.date(2025, 10, 14))) == "Anmerkung vom 14.10.2025"


def test_sperre_aktiv(haushalt):
    sperre = Sperre(haushalt=haushalt, von=dt.date(2026, 6, 1), bis=dt.date(2026, 6, 30))
    assert sperre.ist_aktiv(STICHTAG)
    assert not sperre.ist_aktiv(dt.date(2026, 7, 1))
    assert not sperre.ist_aktiv(dt.date(2026, 5, 31))
    sperre.bis = None
    assert sperre.ist_aktiv(dt.date(2030, 1, 1))
    assert sperre.ist_aktiv() is True


def test_kundenstamm_wird_protokolliert(haushalt):
    haushalt.status = Haushalt.Status.PAUSIERT
    haushalt.save()
    eintrag = LogEntry.objects.get_for_object(haushalt).latest("timestamp")
    assert "status" in eintrag.changes_dict


@pytest.mark.parametrize(
    ("text", "erwartet"),
    [
        ("1,50 €", "1.50"),
        ("1,5 €", "1.50"),
        ("-3,00", "-3.00"),
        ("1.234,56 EUR", "1234.56"),
        ("1.5", "1.50"),
        ("0", "0.00"),
    ],
)
def test_betrag(text, erwartet):
    from decimal import Decimal

    assert werte.betrag(text) == Decimal(erwartet)


@pytest.mark.parametrize("text", ["", "  ", None, "€"])
def test_betrag_leer(text):
    assert werte.betrag(text) is None


@pytest.mark.parametrize("text", ["zehn", "1,2,3", "NaN", "Infinity"])
def test_betrag_ungueltig(text):
    with pytest.raises(werte.UngueltigerWert):
        werte.betrag(text)
