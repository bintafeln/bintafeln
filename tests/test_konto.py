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
    ("anfang", "bar", "zahlweise", "vom_konto", "angeschrieben", "ende"),
    [
        (D("6.00"), D("0.00"), GUTHABEN, D("3.00"), D("0"), D("3.00")),  # ganz aus Guthaben
        (D("2.00"), D("1.00"), GUTHABEN, D("2.00"), D("0"), D("0.00")),  # Rest bar
        (D("6.00"), D("3.00"), BAR, D("0.00"), D("0"), D("6.00")),  # alles bar
        (D("1.00"), D("0.00"), ANSCHREIBEN, D("1.00"), D("2.00"), D("-2.00")),
        (D("-1.00"), D("3.00"), BAR, D("0.00"), D("0"), D("-1.00")),
    ],
)
def test_abholung_buchen(haushalt, einstellungen, anfang, bar, zahlweise, vom_konto,
                         angeschrieben, ende):  # fmt: skip
    einstellungen.anschreiben_erlaubt = True
    haushalt.kontostand = anfang
    haushalt.save()
    zahlung = konto.abholung_buchen(abholung(haushalt), D("3.00"), bar, einstellungen,
                                    None, "Test")  # fmt: skip
    assert (zahlung.bar, zahlung.vom_konto, zahlung.angeschrieben, zahlung.kontostand) == (
        bar, vom_konto, angeschrieben, ende)  # fmt: skip
    b = Buchung.objects.get()
    assert (b.soll, b.haben, b.bar, b.zahlweise) == (D("3.00"), bar, bar, zahlweise)
    assert b.kundennummer == "00042" and stand(haushalt) == ende
    assert str(b).startswith("Abholung vom ")


def test_ueberzahlung_wird_guthaben(haushalt, einstellungen):
    haushalt.kontostand = D("0")
    haushalt.save()
    a = abholung(haushalt)
    zahlung = konto.abholung_buchen(a, D("3"), D("10"), einstellungen, None, "Test")
    assert (zahlung.gutgeschrieben, zahlung.kontostand) == (D("7"), D("7"))
    beitrag = Buchung.objects.get(art=Buchung.Art.ABHOLUNG)
    ueber = Buchung.objects.get(art=Buchung.Art.EINZAHLUNG)
    assert (beitrag.bar, ueber.bar) == (D("3"), D("7"))
    assert ueber.bemerkung == "Überzahlung bei der Abholung"
    konto.abholung_zuruecknehmen(a)
    assert stand(haushalt) == D("0") and not Buchung.objects.exists()


def test_bar_vorschlag():
    assert konto.bar_vorschlag(D("3"), D("5")) == D("0")
    assert konto.bar_vorschlag(D("3"), D("1")) == D("2")
    assert konto.bar_vorschlag(D("3"), D("-4")) == D("3")
    assert konto.bar_vorschlag(D("3"), None) == D("3")


def test_anschreiben_nur_wenn_erlaubt(haushalt, einstellungen):
    haushalt.kontostand = D("1")
    haushalt.save()
    with pytest.raises(konto.KontoFehler, match="Es fehlen 2,00 €"):
        konto.abholung_buchen(abholung(haushalt), D("3"), D("0"), einstellungen, None, "")
    with pytest.raises(konto.KontoFehler, match="auch 0"):
        konto.abholung_buchen(abholung(haushalt), D("3"), None, einstellungen, None, "")
    assert not Buchung.objects.exists()


def test_beitrag_null_ohne_buchung(haushalt, einstellungen):
    haushalt.kontostand = None
    haushalt.save()
    zahlung = konto.abholung_buchen(abholung(haushalt), D("0"), D("0"), einstellungen, None, "")
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


def test_vorschlag_nur_fuer_diesen_monat(freitagsgruppe, einstellungen):
    vorschlaege, hinweis = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1.50"))
    assert hinweis == ""
    (rest,) = vorschlaege  # kein Vorschlag für den nächsten Monat
    assert rest.titel == "Rest Oktober" and len(rest.tage) == 5 and rest.betrag == D("7.50")
    assert rest.erklaerung[0] == "5 Abholtage × 1,50 € = 7,50 €"
    assert rest.erklaerung[1].startswith("Gezählt: Fr 02.10., Fr 09.10.")
    assert rest.erklaerung[1].endswith("(Kundengruppe „Freitag“: Fr)")
    assert "ab heute, weil heute noch nicht abgeholt wurde" in rest.erklaerung[2]
    assert "Höchstens 1 Abholung je Kalenderwoche ist eingehalten." in rest.erklaerung


def test_vorschlag_ohne_beitragsfreie_tage(freitagsgruppe, einstellungen):
    from apps.ausgabe.models import BeitragsfreierZeitraum

    BeitragsfreierZeitraum.objects.create(bezeichnung="Herbst", von=dt.date(2026, 10, 16),
                                          bis=dt.date(2026, 10, 23))  # fmt: skip
    rest = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1.50"))[0][0]
    assert len(rest.tage) == 3 and rest.betrag == D("4.50")
    assert "Nicht gezählt, weil beitragsfrei: 16.10., 23.10." in rest.erklaerung


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
    einstellungen.max_abholungen = 3
    (rest,) = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[0]
    assert len(rest.tage) == 3
    assert "Höchstens 3 Abholungen je Kalendermonat: 2 Abholtage nicht gezählt." in (
        rest.erklaerung
    )
    # Für ein, zwei Abholungen bis Monatsende gibt es keine Vorauszahlung
    einstellungen.max_abholungen = 2
    assert konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1")) == (
        [], "Kein Vorschlag: Bis Monatsende sind weniger als 3 Abholungen möglich.",
    )  # fmt: skip


def test_vorschlag_ohne_hoechstzahl(freitagsgruppe, einstellungen):
    einstellungen.max_abholungen = 0
    rest = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[0][0]
    assert "Keine Höchstzahl je Zeitraum eingestellt." in rest.erklaerung


def test_vorschlag_vierzehn_tage_ohne_grenze(freitagsgruppe, einstellungen):
    einstellungen.zeitraum = AusgabeEinstellungen.Zeitraum.VIERZEHN_TAGE
    rest = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))[0][0]
    assert len(rest.tage) == 5
    assert "Die Höchstzahl (1 je 14 Tage) ist im Vorschlag nicht berücksichtigt." in (
        rest.erklaerung
    )


def test_vorschlag_endet_mit_dem_ausweis(freitagsgruppe, einstellungen):
    freitagsgruppe.ausweis_gueltig_bis = dt.date(2026, 10, 17)
    vorschlaege, _ = konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1"))
    assert len(vorschlaege) == 1 and len(vorschlaege[0].tage) == 3
    assert "Nur bis zum Ablauf des Ausweises am 17.10.2026." in vorschlaege[0].erklaerung
    freitagsgruppe.ausweis_gueltig_bis = dt.date(2026, 10, 1)
    assert konto.vorschlaege(freitagsgruppe, FREITAG, einstellungen, D("1")) == (
        [],
        "Kein Vorschlag: Bis Monatsende sind weniger als 3 Abholungen möglich.",
    )


def test_vorschlag_jahreswechsel(freitagsgruppe, einstellungen):
    vorschlaege, _ = konto.vorschlaege(freitagsgruppe, dt.date(2026, 12, 4), einstellungen, D("1"))
    assert [v.titel for v in vorschlaege] == ["Rest Dezember"]


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
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_person = D("3")
    e.save()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert 'name="bar" id="bar" value="1,00"' in inhalt  # Rest nach Guthaben vorgeschlagen
    assert "Abholung eintragen" in inhalt and not Abholung.objects.exists()
    inhalt = eintragen(ausgabe, haushalt, beitrag="3,00", bar="1,00").content.decode()
    assert ("Bar erhalten: 1,00 €, 2,00 € aus Guthaben. Kontostand jetzt: 0,00 €.") in inhalt
    assert Abholung.objects.get().buchung.bar == D("1.00")


def test_empfang_guthaben_reicht_null_vorgeschlagen(ausgabe, haushalt):
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert 'name="bar" id="bar" value="0,00"' in inhalt  # Guthaben 6 € reicht
    inhalt = eintragen(ausgabe, haushalt, beitrag="3", bar="0").content.decode()
    assert "Bar erhalten: 0,00 €, 3,00 € aus Guthaben. Kontostand jetzt: 3,00 €." in inhalt


def test_empfang_mehr_bar_wird_guthaben(ausgabe, haushalt):
    inhalt = eintragen(ausgabe, haushalt, beitrag="3", bar="5").content.decode()
    assert "Bar erhalten: 5,00 €, 2,00 € als Guthaben gebucht. Kontostand jetzt: 8,00 €." in inhalt


def test_empfang_anschreiben(ausgabe, haushalt):
    haushalt.kontostand = D("0")
    haushalt.save()
    inhalt = eintragen(ausgabe, haushalt, beitrag="3", bar="1").content.decode()
    assert "Es fehlen 2,00 €" in inhalt
    assert not Abholung.objects.exists() and not Buchung.objects.exists()
    e = AusgabeEinstellungen.laden()
    e.anschreiben_erlaubt = True
    e.save()
    inhalt = eintragen(ausgabe, haushalt, beitrag="3", bar="1").content.decode()
    assert "Bar erhalten: 1,00 €, 2,00 € angeschrieben. Kontostand jetzt: -2,00 €." in inhalt


@pytest.mark.parametrize(
    ("daten", "text"),
    [
        ({"beitrag": "-1", "bar": "0"}, "Beitrag ist negativ"),
        ({"beitrag": "1", "bar": "viel"}, "Bar gezahlt ist kein Betrag"),
        ({"beitrag": "1", "bar": ""}, "auch 0"),
    ],
)
def test_empfang_ungueltige_eingaben(ausgabe, haushalt, daten, text):
    assert text in eintragen(ausgabe, haushalt, **daten).content.decode()
    assert not Abholung.objects.exists()


def test_storno_nimmt_buchung_zurueck(ausgabe, haushalt, recht_geben):
    recht_geben(rollen.AUSGABE, "einlass.zuruecknehmen")
    eintragen(ausgabe, haushalt, beitrag="3", bar="0")
    assert stand(haushalt) == D("3.00")
    a = Abholung.objects.get()
    inhalt = ausgabe.post(reverse("ausgabe:zuruecknehmen", args=[a.pk]), **HX).content.decode()
    assert "Kontostand jetzt: 6,00 €" in inhalt
    assert stand(haushalt) == D("6.00") and not Buchung.objects.exists()


def test_empfang_einzahlung_und_vorschlag(ausgabe, haushalt, recht_geben, monkeypatch):
    # Fester Tag am Monatsanfang: Vorschläge gibt es erst ab drei möglichen Abholungen
    mitte = timezone.now().replace(day=3, hour=10)
    # Die Anmeldung geschah in Echtzeit; die Sitzung läuft nach SESSION_COOKIE_AGE (10 h) ab. Noch
    # vor dem Vorstellen der Uhr ihre Gültigkeit über die vorgestellte Zeit hinaus verlängern –
    # sonst gälte sie als abgelaufen und die Anfrage käme als Weiterleitung zur Anmeldung zurück
    # (leere Antwort), je nach echtem Laufdatum.
    sitzung = ausgabe.session
    sitzung.set_expiry(mitte + dt.timedelta(hours=10))
    sitzung.save()
    monkeypatch.setattr(timezone, "now", lambda: mitte)
    recht_geben(rollen.AUSGABE, "einlass.zuruecknehmen")
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_abholung = D("1.50")
    e.save()
    haushalt.kundengruppe.wochentage = ""
    haushalt.kundengruppe.save()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert "Vorauszahlung" not in inhalt  # ohne feste Wochentage kein Vorschlag
    haushalt.kundengruppe.wochentage = "Mo,Di,Mi,Do,Fr,Sa,So"
    haushalt.kundengruppe.save()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    # Vorauszahlung läuft über das Feld „Gezahlt“: der Knopf trägt den Betrag dort ein
    assert "Vorauszahlung Rest " in inhalt and "document.getElementById('bar')" in inhalt
    assert "Abzüglich Guthaben 6,00 €" in inhalt and 'id="einzahlung"' not in inhalt
    # Ohne mögliche Abholung (hier: heute schon abgeholt) gibt es „Gezahlt ohne Abholung“
    eintragen(ausgabe, haushalt, bar="0")
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert "Gezahlt ohne Abholung" in inhalt and "document.getElementById('einzahlung')" in inhalt
    ausgabe.post(reverse("ausgabe:zuruecknehmen", args=[Abholung.objects.get().pk]), **HX)
    assert stand(haushalt) == D("6.00") and not Buchung.objects.exists()

    url = reverse("ausgabe:einzahlung", args=["00042"])
    assert "Betrag größer als 0" in ausgabe.post(url, {"betrag": "abc"}, **HX).content.decode()
    inhalt = ausgabe.post(url, {"betrag": "10,00"}, **HX).content.decode()
    assert "Einzahlung von 10,00 € gebucht. Bar erhalten: 10,00 €. Kontostand jetzt: 16,00 €." in (
        inhalt
    )
    assert "Zahlung 10,00 € zurücknehmen" in inhalt
    b = Buchung.objects.get()
    zurueck = ausgabe.post(reverse("ausgabe:einzahlung_zuruecknehmen", args=[b.pk]), **HX)
    assert "Kontostand jetzt: 6,00 €" in zurueck.content.decode()
    gestern = konto.einzahlen(haushalt, D("1"), None, "")
    Buchung.objects.filter(pk=gestern.pk).update(datum=timezone.localdate() - dt.timedelta(1))
    url = reverse("ausgabe:einzahlung_zuruecknehmen", args=[gestern.pk])
    assert ausgabe.post(url).status_code == 302  # mit dem Recht auch an späteren Tagen
    assert not Buchung.objects.filter(pk=gestern.pk).exists()


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
