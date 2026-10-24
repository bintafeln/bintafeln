# Fixtures aus test_empfang werden importiert und als Parameter wiederverwendet.
# ruff: noqa: F811
import datetime as dt
from decimal import Decimal as D

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe import ampel, konto
from apps.ausgabe.models import AusgabeEinstellungen, Buchung
from apps.konten import rollen
from apps.kunden import importieren
from apps.kunden.models import Abholung, Haushalt, KundenEinstellungen, Kundengruppe
from tests.test_empfang import HX, als, ausgabe, eintragen, haushalt, stelle  # noqa: F401

pytestmark = pytest.mark.django_db

GUTHABEN, BAR, ANSCHREIBEN = (
    Buchung.Zahlweise.GUTHABEN,
    Buchung.Zahlweise.BAR,
    Buchung.Zahlweise.ANSCHREIBEN,
)
EMPFANG = reverse("ausgabe:empfang")


@pytest.fixture
def einstellungen():
    return AusgabeEinstellungen.laden()


def abholung(h, datum=None):
    return Abholung.objects.create(haushalt=h, datum=datum or timezone.localdate())


def stand(h):
    h.refresh_from_db()
    return h.kontostand


# --- Buchen ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("anfang", "zahlweise", "bar", "vom_konto", "ende"),
    [
        (D("6.00"), GUTHABEN, D("0.00"), D("3.00"), D("3.00")),
        (D("2.00"), GUTHABEN, D("1.00"), D("2.00"), D("0.00")),
        (D("-1.00"), GUTHABEN, D("3.00"), D("0.00"), D("-1.00")),
        (D("6.00"), BAR, D("3.00"), D("0.00"), D("6.00")),
        (D("1.00"), ANSCHREIBEN, D("0.00"), D("3.00"), D("-2.00")),
    ],
)
def test_abholung_buchen(haushalt, einstellungen, anfang, zahlweise, bar, vom_konto, ende):
    einstellungen.anschreiben_erlaubt = True
    haushalt.kontostand = anfang
    haushalt.save()
    zahlung = konto.abholung_buchen(abholung(haushalt), D("3.00"), zahlweise, einstellungen,
                                    None, "Test")  # fmt: skip
    assert (zahlung.bar, zahlung.vom_konto, zahlung.kontostand) == (bar, vom_konto, ende)
    b = Buchung.objects.get()
    assert (b.soll, b.haben, b.bar, b.zahlweise) == (D("3.00"), bar, bar, zahlweise)
    assert b.kundennummer == "00042" and stand(haushalt) == ende
    assert b.wirkung == -vom_konto and str(b).startswith("Abholung vom ")


def test_anschreiben_nur_wenn_erlaubt(haushalt, einstellungen):
    with pytest.raises(konto.KontoFehler):
        konto.abholung_buchen(abholung(haushalt), D("3"), ANSCHREIBEN, einstellungen, None, "")
    assert not Buchung.objects.exists()


def test_beitrag_null_ohne_buchung(haushalt, einstellungen):
    haushalt.kontostand = None
    haushalt.save()
    zahlung = konto.abholung_buchen(abholung(haushalt), D("0"), GUTHABEN, einstellungen, None, "")
    assert zahlung.kontostand == D("0.00") and not Buchung.objects.exists()
    assert stand(haushalt) is None


def test_einzahlen_korrigieren_zuruecknehmen(haushalt):
    einzahlung = konto.einzahlen(haushalt, D("10.00"), None, "Kasse", "Vorauszahlung")
    assert (einzahlung.haben, einzahlung.bar, stand(haushalt)) == (D("10"), D("10"), D("16.00"))
    plus = konto.korrigieren(haushalt, D("1.50"), " Rundung ", "Büro")
    minus = konto.korrigieren(haushalt, D("-2.00"), "Fehlbuchung", "Büro")
    assert (plus.haben, plus.bar, plus.bemerkung) == (D("1.50"), D("0"), "Rundung")
    assert minus.soll == D("2.00") and stand(haushalt) == D("15.50")
    konto.zuruecknehmen(einzahlung)
    assert stand(haushalt) == D("5.50") and Buchung.objects.count() == 2


@pytest.mark.parametrize(
    ("funktion", "argumente"),
    [
        (konto.einzahlen, (D("0"), None, "")),
        (konto.einzahlen, (None, None, "")),
        (konto.korrigieren, (D("0"), "Grund", "")),
        (konto.korrigieren, (D("1"), "  ", "")),
    ],
)
def test_ungueltige_buchungen(haushalt, funktion, argumente):
    with pytest.raises(konto.KontoFehler):
        funktion(haushalt, *argumente)


def test_zuruecknehmen_ohne_haushalt():
    b = Buchung.objects.create(kundennummer="", art=Buchung.Art.EINZAHLUNG, haben=D("5"))
    konto.zuruecknehmen(b)
    assert not Buchung.objects.exists()


@pytest.mark.parametrize(
    ("betrag", "text"),
    [(D("3"), "3,00 €"), (D("1234.5"), "1.234,50 €"), (D("-2"), "-2,00 €")],
)
def test_euro(betrag, text):
    assert konto.euro(betrag) == text


def test_ampel_gelb_bei_negativem_kontostand(haushalt, einstellungen):
    haushalt.kontostand = D("-2.00")
    b = ampel.bewerten(haushalt, timezone.localdate(), None, einstellungen)
    assert "Kontostand negativ: −2,00 € (angeschrieben)" in [m.text for m in b.meldungen]


# --- Vorschlag ---------------------------------------------------------------------------

# Freitag, 2. Oktober 2026
FREITAG = dt.date(2026, 10, 2)


@pytest.fixture
def freitagsgruppe(haushalt):
    gruppe = Kundengruppe.objects.create(kuerzel="FR", name="Freitag", wochentage="Fr")
    haushalt.kundengruppe = gruppe
    haushalt.ausweis_gueltig_bis = dt.date(2027, 12, 31)
    haushalt.save()
    return haushalt


def test_vorschlag_rest_und_naechster_monat(freitagsgruppe, einstellungen):
    vorschlaege, hinweis = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1.50"))
    assert hinweis == ""
    rest, november = vorschlaege
    assert rest.titel == "Rest Oktober" and len(rest.tage) == 5 and rest.betrag == D("7.50")
    assert rest.erklaerung[0] == "5 Abholtage × 1,50 € = 7,50 €"
    assert rest.erklaerung[1].startswith("Gezählt: Fr 02.10., Fr 09.10.")
    assert rest.erklaerung[1].endswith("(Kundengruppe „Freitag“: Fr)")
    assert "ab heute, weil heute noch nicht abgeholt wurde" in rest.erklaerung[2]
    assert "Höchstens 1 Abholung je Kalenderwoche ist eingehalten." in rest.erklaerung
    assert november.titel == "Ganzer November" and len(november.tage) == 4


def test_vorschlag_ab_morgen_wenn_heute_abgeholt(freitagsgruppe, einstellungen):
    abholung(freitagsgruppe, FREITAG)
    rest = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[0][0]
    assert len(rest.tage) == 4 and "ab morgen" in rest.erklaerung[2]


def test_vorschlag_beachtet_hoechstzahl_je_woche(freitagsgruppe, einstellungen):
    freitagsgruppe.kundengruppe.wochentage = "Mo,Fr"
    abholung(freitagsgruppe, dt.date(2026, 9, 28))  # Montag dieser Woche
    rest = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[0][0]
    assert rest.tage[0] == dt.date(2026, 10, 5)  # Freitag fällt weg, Woche ist voll
    assert len(rest.tage) == 4
    assert "Höchstens 1 Abholung je Kalenderwoche: 5 Abholtage nicht gezählt." in rest.erklaerung


def test_vorschlag_beachtet_hoechstzahl_je_monat(freitagsgruppe, einstellungen):
    einstellungen.zeitraum = AusgabeEinstellungen.Zeitraum.MONAT
    einstellungen.max_abholungen = 2
    rest, november = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[0]
    assert len(rest.tage) == 2 and len(november.tage) == 2
    assert "Höchstens 2 Abholungen je Kalendermonat: 3 Abholtage nicht gezählt." in (
        rest.erklaerung
    )


def test_vorschlag_vierzehn_tage_ohne_grenze(freitagsgruppe, einstellungen):
    einstellungen.zeitraum = AusgabeEinstellungen.Zeitraum.VIERZEHN_TAGE
    rest = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[0][0]
    assert len(rest.tage) == 5
    assert "Die Höchstzahl (1 je 14 Tage) ist im Vorschlag nicht berücksichtigt." in (
        rest.erklaerung
    )


def test_vorschlag_endet_mit_dem_ausweis(freitagsgruppe, einstellungen):
    freitagsgruppe.ausweis_gueltig_bis = dt.date(2026, 10, 10)
    vorschlaege, _ = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))
    assert len(vorschlaege) == 1 and len(vorschlaege[0].tage) == 2
    assert "Nur bis zum Ablauf des Ausweises am 10.10.2026." in vorschlaege[0].erklaerung
    freitagsgruppe.ausweis_gueltig_bis = dt.date(2026, 10, 1)
    assert konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1")) == (
        [],
        "Kein Vorschlag: Bis Ende des nächsten Monats ist kein Abholtag mehr möglich.",
    )


def test_vorschlag_jahreswechsel(freitagsgruppe, einstellungen):
    vorschlaege, _ = konto.vorschlaege(freitagsgruppe, dt.date(2026, 12, 18), einstellungen, D("1"))
    assert [v.titel for v in vorschlaege] == ["Rest Dezember", "Ganzer Januar"]


def test_kein_vorschlag(freitagsgruppe, einstellungen):
    assert "kein Beitrag" in konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("0"))[1]
    freitagsgruppe.kundengruppe.wochentage = ""
    assert (
        "keine festen Wochentage"
        in konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[1]
    )
    freitagsgruppe.kundengruppe = None
    assert (
        "keine festen Wochentage"
        in konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[1]
    )


# --- Fristen -----------------------------------------------------------------------------


def test_buchungsfristen(haushalt):
    heute = dt.date(2026, 10, 24)

    def buchung(datum):
        return Buchung.objects.create(
            haushalt=haushalt, kundennummer="00042", art=Buchung.Art.KORREKTUR, datum=datum,
            bemerkung="Grund", eingetragen_von="Büro",
        )  # fmt: skip

    neu, mittel, alt = buchung(heute), buchung(dt.date(2020, 1, 1)), buchung(dt.date(2016, 1, 1))
    assert konto.buchungsfristen_anwenden(heute) == 1
    assert not Buchung.objects.filter(pk=alt.pk).exists()
    mittel.refresh_from_db()
    neu.refresh_from_db()
    assert (mittel.haushalt, mittel.kundennummer, mittel.bemerkung, mittel.eingetragen_von) == (
        None, "", "", "",
    )  # fmt: skip
    assert neu.kundennummer == "00042"
    assert konto.buchungsfristen_anwenden(dt.date(2028, 2, 29)) == 0


# --- Einlass ----------------------------------------------------------------------------


def test_empfang_guthaben_teilweise(ausgabe, haushalt):
    haushalt.kontostand = D("2.00")
    haushalt.save()
    inhalt = eintragen(ausgabe, haushalt, beitrag="3,00", zahlweise=GUTHABEN).content.decode()
    assert "Bar zu zahlen: 1,00 € (2,00 € vom Konto). Kontostand jetzt: 0,00 €." in inhalt
    assert Abholung.objects.get().buchung.bar == D("1.00")


def test_empfang_alles_bar(ausgabe, haushalt):
    inhalt = eintragen(ausgabe, haushalt, beitrag="3", zahlweise=BAR).content.decode()
    assert "Bar zu zahlen: 3,00 €. Kontostand jetzt: 6,00 €." in inhalt


def test_empfang_anschreiben_nicht_erlaubt_traegt_nichts_ein(ausgabe, haushalt):
    inhalt = eintragen(ausgabe, haushalt, beitrag="3", zahlweise=ANSCHREIBEN).content.decode()
    assert "Anschreiben ist in den Einstellungen nicht erlaubt" in inhalt
    assert not Abholung.objects.exists() and not Buchung.objects.exists()


@pytest.mark.parametrize(
    ("daten", "text"),
    [
        ({"beitrag": "-1"}, "Beitrag ist negativ"),
        ({"beitrag": "1", "zahlweise": "gutschein"}, "unbekannte Zahlweise"),
    ],
)
def test_empfang_ungueltige_eingaben(ausgabe, haushalt, daten, text):
    assert text in eintragen(ausgabe, haushalt, **daten).content.decode()
    assert not Abholung.objects.exists()


def test_empfang_zeigt_passende_zahlweisen(ausgabe, haushalt):
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert 'value="guthaben" checked' in inhalt and "anschreiben" not in inhalt
    haushalt.kontostand = D("0")
    haushalt.save()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert '<input type="hidden" name="zahlweise" value="bar">' in inhalt
    e = AusgabeEinstellungen.laden()
    e.anschreiben_erlaubt = True
    e.save()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert 'value="bar" checked' in inhalt and 'value="anschreiben"' in inhalt


def test_storno_nimmt_buchung_zurueck(ausgabe, haushalt):
    eintragen(ausgabe, haushalt, beitrag="3", zahlweise=GUTHABEN)
    assert stand(haushalt) == D("3.00")
    a = Abholung.objects.get()
    inhalt = ausgabe.post(reverse("ausgabe:zuruecknehmen", args=[a.pk]), **HX).content.decode()
    assert "Kontostand jetzt: 6,00 €" in inhalt
    assert stand(haushalt) == D("6.00") and not Buchung.objects.exists()


def test_empfang_einzahlung_und_vorschlag(ausgabe, haushalt):
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_abholung = D("1.50")
    e.save()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert "Kein Vorschlag: Die Kundengruppe hat keine festen Wochentage" in inhalt
    haushalt.kundengruppe.wochentage = "Mo,Di,Mi,Do,Fr,Sa,So"
    haushalt.kundengruppe.save()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert "Vorschlag Rest " in inhalt and "Vorauszahlung Rest " in inhalt

    url = reverse("ausgabe:einzahlung", args=["00042"])
    assert "Betrag größer als 0" in ausgabe.post(url, {"betrag": "abc"}, **HX).content.decode()
    inhalt = ausgabe.post(url, {"betrag": "10,00"}, **HX).content.decode()
    assert "Einzahlung von 10,00 € gebucht. Bar erhalten: 10,00 €. Kontostand jetzt: 16,00 €." in (
        inhalt
    )
    assert "Einzahlung 10,00 € von" in inhalt
    b = Buchung.objects.get()
    zurueck = ausgabe.post(reverse("ausgabe:einzahlung_zuruecknehmen", args=[b.pk]), **HX)
    assert "Kontostand jetzt: 6,00 €" in zurueck.content.decode()
    gestern = konto.einzahlen(haushalt, D("1"), None, "")
    Buchung.objects.filter(pk=gestern.pk).update(datum=timezone.localdate() - dt.timedelta(1))
    url = reverse("ausgabe:einzahlung_zuruecknehmen", args=[gestern.pk])
    assert ausgabe.post(url).status_code == 404


# --- Haushaltsseite und Korrektur --------------------------------------------------------


def test_kontoverlauf_und_korrektur(als, haushalt):
    buero = als(rollen.BUERO)
    seite = reverse("kunden:haushalt", args=["00042"])
    assert "Noch keine Buchungen in bintafeln" in buero.get(seite).content.decode()
    url = reverse("ausgabe:korrektur", args=["00042"])
    antwort = buero.post(url, {"betrag": "-1,00", "begruendung": "Fehlbuchung"})
    assert antwort.url == seite
    inhalt = buero.get(seite).content.decode()
    assert "Korrektur gebucht." in inhalt and "Fehlbuchung" in inhalt and "5,00 €" in inhalt
    buero.post(url, {"betrag": "x", "begruendung": "y"})
    assert "Kein gültiger Betrag." in buero.get(seite).content.decode()
    buero.post(url, {"betrag": "1", "begruendung": ""})
    assert "Bitte eine Begründung angeben." in buero.get(seite).content.decode()


def test_korrektur_nicht_fuer_ausgabe(ausgabe, haushalt):
    url = reverse("ausgabe:korrektur", args=["00042"])
    assert ausgabe.post(url, {"betrag": "1", "begruendung": "x"}).status_code == 403
    inhalt = ausgabe.get(reverse("kunden:haushalt", args=["00042"])).content.decode()
    assert "Kundenkonto" not in inhalt


# --- Import ------------------------------------------------------------------------------


def test_import_behaelt_buchungen_fuer_die_kasse(haushalt):
    KundenEinstellungen.laden()
    konto.einzahlen(haushalt, D("5"), None, "")
    datei = {"haushalte.csv": b"kundennummer;nachname;vorname;kontostand\n00042;Muster;Erika;1\n"}
    ergebnis = importieren.pruefen(datei)
    assert any("1 Kontobuchungen aus bintafeln" in m["text"] for m in ergebnis.warnungen)
    importieren.uebernehmen(
        ergebnis.daten, benutzer=None, dateien=[], pruefsumme="", anzahl_warnungen=0
    )
    b = Buchung.objects.get()
    assert b.haushalt is None and b.kundennummer == "00042"
    assert Haushalt.objects.get().kontostand == D("1.00")
