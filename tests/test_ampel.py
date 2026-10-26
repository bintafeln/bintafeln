import datetime as dt
from decimal import Decimal

import pytest

from apps.ausgabe import ampel
from apps.ausgabe.models import AusgabeEinstellungen
from apps.kunden.models import Abholung, Ausgabestelle, Ausnahme, Haushalt, Kundengruppe, Sperre

pytestmark = pytest.mark.django_db

# Mittwoch
HEUTE = dt.date(2026, 10, 21)


@pytest.fixture
def einstellungen():
    return AusgabeEinstellungen.laden()


@pytest.fixture
def mitte():
    return Ausgabestelle.objects.create(name="Ausgabestelle Mitte")


@pytest.fixture
def haushalt(mitte):
    gruppe = Kundengruppe.objects.create(
        kuerzel="MI1", name="Mittwoch", ausgabestelle=mitte, wochentage="Mi"
    )
    return Haushalt.objects.create(
        kundennummer="1001", kundengruppe=gruppe, ausweis_gueltig_bis=dt.date(2027, 6, 30)
    )


def farbe_und_texte(h, einstellungen, stelle=None, heute=HEUTE):
    b = ampel.bewerten(h, heute, stelle, einstellungen)
    return b.farbe, [m.text for m in b.meldungen]


def test_gruen(haushalt, einstellungen, mitte):
    b = ampel.bewerten(haushalt, HEUTE, mitte, einstellungen)
    assert (b.farbe, b.darf_abholen, b.ausnahme_hilft) == ("gruen", True, False)
    assert [m.text for m in b.meldungen] == ["Alles in Ordnung"]


@pytest.mark.parametrize(
    ("status", "farbe"), [("gesperrt", "rot"), ("beendet", "rot"), ("pausiert", "gelb")]
)
def test_status(haushalt, einstellungen, status, farbe):
    haushalt.status = status
    assert farbe_und_texte(haushalt, einstellungen)[0] == farbe


def test_aktive_sperre(haushalt, einstellungen):
    Sperre.objects.create(haushalt=haushalt, von=dt.date(2026, 10, 1), begruendung="Streit")
    Sperre.objects.create(haushalt=haushalt, von=dt.date(2026, 10, 1), bis=dt.date(2026, 10, 31))
    Sperre.objects.create(haushalt=haushalt, von=dt.date(2025, 1, 1), bis=dt.date(2025, 2, 1))
    farbe, texte = farbe_und_texte(haushalt, einstellungen)
    assert farbe == "rot"
    assert texte == ["Gesperrt seit 01.10.2026: Streit", "Gesperrt seit 01.10.2026 bis 31.10.2026"]
    assert not ampel.bewerten(haushalt, HEUTE, None, einstellungen).ausnahme_hilft


@pytest.mark.parametrize(
    ("ausweis", "farbe", "text"),
    [
        (None, "gelb", "Kein Ablaufdatum des Ausweises hinterlegt"),
        (dt.date(2026, 10, 20), "rot", "Ausweis abgelaufen am 20.10.2026"),
        (dt.date(2026, 10, 21), "gelb", "Ausweis läuft am 21.10.2026 ab"),
        (dt.date(2026, 11, 4), "gelb", "Ausweis läuft am 04.11.2026 ab"),
        (dt.date(2026, 11, 5), "gruen", "Alles in Ordnung"),
    ],
)
def test_ausweis(haushalt, einstellungen, ausweis, farbe, text):
    haushalt.ausweis_gueltig_bis = ausweis
    assert farbe_und_texte(haushalt, einstellungen) == (farbe, [text])


def test_heute_schon_abgeholt(haushalt, einstellungen):
    Abholung.objects.create(haushalt=haushalt, datum=HEUTE, uhrzeit=dt.time(9, 5))
    assert farbe_und_texte(haushalt, einstellungen) == ("rot", ["Heute bereits abgeholt um 09:05"])
    Abholung.objects.all().update(uhrzeit=None)
    assert farbe_und_texte(haushalt, einstellungen)[1] == ["Heute bereits abgeholt"]


def test_mehrfach_am_tag(haushalt, einstellungen):
    einstellungen.max_je_tag, einstellungen.max_abholungen = 2, 0  # keine Grenze je Woche
    Abholung.objects.create(haushalt=haushalt, datum=HEUTE, uhrzeit=dt.time(9, 5))
    assert farbe_und_texte(haushalt, einstellungen) == (
        "gelb", ["Heute schon 1-mal abgeholt (mehrfach erlaubt)"])  # fmt: skip
    Abholung.objects.create(haushalt=haushalt, datum=HEUTE, uhrzeit=dt.time(11, 30))
    text = "Heute bereits 2-mal abgeholt, zuletzt um 11:30 (höchstens 2-mal am Tag)"
    assert farbe_und_texte(haushalt, einstellungen) == ("rot", [text])
    Abholung.objects.all().update(uhrzeit=None)
    assert "zuletzt heute" in farbe_und_texte(haushalt, einstellungen)[1][0]
    einstellungen.max_je_tag = 0  # beliebig oft
    assert farbe_und_texte(haushalt, einstellungen)[0] == "gelb"
    einstellungen.max_abholungen = 2  # aber höchstens 2 je Woche
    b = ampel.bewerten(haushalt, HEUTE, None, einstellungen)
    assert b.farbe == "rot" and b.ausnahme_hilft


@pytest.mark.parametrize(
    ("zeitraum", "beginn"),
    [
        (AusgabeEinstellungen.Zeitraum.WOCHE, dt.date(2026, 10, 19)),
        (AusgabeEinstellungen.Zeitraum.VIERZEHN_TAGE, dt.date(2026, 10, 8)),
        (AusgabeEinstellungen.Zeitraum.MONAT, dt.date(2026, 10, 1)),
    ],
)
def test_zeitraum_beginn(zeitraum, beginn):
    assert ampel.zeitraum_beginn(HEUTE, zeitraum) == beginn


def test_hoechstzahl_je_woche(haushalt, einstellungen):
    Abholung.objects.create(haushalt=haushalt, datum=dt.date(2026, 10, 18))  # Sonntag davor
    assert farbe_und_texte(haushalt, einstellungen)[0] == "gruen"
    Abholung.objects.create(haushalt=haushalt, datum=dt.date(2026, 10, 19))  # Montag
    b = ampel.bewerten(haushalt, HEUTE, None, einstellungen)
    assert [m.text for m in b.meldungen] == [
        "Höchstzahl erreicht: 1 Abholung in dieser Kalenderwoche"
    ]
    assert b.ausnahme_hilft
    einstellungen.max_abholungen = 2
    assert farbe_und_texte(haushalt, einstellungen)[0] == "gruen"
    einstellungen.zeitraum = AusgabeEinstellungen.Zeitraum.MONAT
    assert farbe_und_texte(haushalt, einstellungen)[1] == [
        "Höchstzahl erreicht: 2 Abholungen in diesem Monat"
    ]


def test_zukuenftige_abholung_zaehlt_nicht(haushalt, einstellungen):
    Abholung.objects.create(haushalt=haushalt, datum=dt.date(2026, 10, 22))
    assert farbe_und_texte(haushalt, einstellungen)[0] == "gruen"


def test_nicht_dran_rot_oder_gelb(haushalt, einstellungen):
    donnerstag = dt.date(2026, 10, 22)
    assert farbe_und_texte(haushalt, einstellungen, heute=donnerstag) == (
        "rot",
        ["Heute nicht dran (Kundengruppe Mittwoch: Mi)"],
    )
    einstellungen.nicht_dran_rot = False
    assert farbe_und_texte(haushalt, einstellungen, heute=donnerstag)[0] == "gelb"


def test_gruppe_ohne_wochentage_warnt(haushalt, einstellungen):
    haushalt.kundengruppe.wochentage = ""
    farbe, texte = farbe_und_texte(haushalt, einstellungen, heute=dt.date(2026, 10, 25))
    assert farbe == "gelb" and "hat keine Wochentage" in texte[0]
    haushalt.kundengruppe.wochentage = "Mo, Di, Mi, Do, Fr, Sa, So"  # „jeden Tag“
    assert farbe_und_texte(haushalt, einstellungen, heute=dt.date(2026, 10, 25))[0] == "gruen"


def test_keine_kundengruppe(haushalt, einstellungen):
    haushalt.kundengruppe = None
    assert farbe_und_texte(haushalt, einstellungen) == ("rot", ["Keine Kundengruppe zugeordnet"])


def test_andere_ausgabestelle(haushalt, einstellungen):
    nord = Ausgabestelle.objects.create(name="Ausgabestelle Nord")
    assert farbe_und_texte(haushalt, einstellungen, nord) == (
        "gelb",
        ["Kundengruppe gehört zur Ausgabestelle Ausgabestelle Mitte"],
    )
    haushalt.kundengruppe.ausgabestelle = None
    assert farbe_und_texte(haushalt, einstellungen, nord)[0] == "gruen"


def test_ausnahme_hebt_terminregeln_auf(haushalt, einstellungen):
    donnerstag = dt.date(2026, 10, 22)
    Ausnahme.objects.create(haushalt=haushalt, datum=donnerstag, begruendung="Arzttermin")
    Ausnahme.objects.create(haushalt=haushalt, datum=HEUTE)
    farbe, texte = farbe_und_texte(haushalt, einstellungen, heute=donnerstag)
    assert farbe == "gruen"
    assert texte == [
        "Heute nicht dran (Kundengruppe Mittwoch: Mi) – Ausnahme für heute erteilt: Arzttermin"
    ]
    haushalt.kundengruppe = None
    assert farbe_und_texte(haushalt, einstellungen)[1] == [
        "Keine Kundengruppe zugeordnet – Ausnahme für heute erteilt"
    ]


def test_ausnahme_hebt_sperre_nicht_auf(haushalt, einstellungen):
    Ausnahme.objects.create(haushalt=haushalt, datum=HEUTE)
    haushalt.ausweis_gueltig_bis = dt.date(2026, 1, 1)
    assert farbe_und_texte(haushalt, einstellungen)[0] == "rot"


def test_beitrag_und_einstellungen():
    e = AusgabeEinstellungen.laden()
    assert (e.zahlt_ab_alter, e.beitrag_je_person) == (18, Decimal("1.50"))
    assert e.beitrag(2, 2, 1) == Decimal("3.00")  # 2 zahlende × 1,50
    e.beitrag_je_abholung = Decimal("1.00")
    e.beitrag_je_erwachsenem = Decimal("1.00")
    e.beitrag_je_kind = Decimal("0.50")
    e.save()
    assert e.beitrag(2, 2, 1) == Decimal("3.00")  # Zusatzbeiträge aus (Standard)
    e.zusatzbeitraege = True
    e.save()
    assert AusgabeEinstellungen.laden().beitrag(2, 2, 1) == Decimal("6.50")
    assert str(e) == "Einstellungen Ausgabe"


def test_eigene_meldungstexte(haushalt, einstellungen):
    einstellungen.meldungstexte = {
        "nicht_dran": "Bitte am {tage} kommen ({gruppe})",
        "ausweis_bald": "Ausweis gilt nur noch bis {datum} – bitte ins Büro",
        "ok": "Willkommen!",
        "keine_gruppe": "{unbekannt} {gruppe.__class__} bleibt stehen",
    }
    heute = dt.date(2026, 10, 25)  # Sonntag, Gruppe ist mittwochs dran
    farbe, texte = farbe_und_texte(haushalt, einstellungen, heute=heute)
    assert texte == ["Bitte am Mi kommen (Mittwoch)"]
    haushalt.ausweis_gueltig_bis = dt.date(2026, 10, 28)
    _, texte = farbe_und_texte(haushalt, einstellungen, heute=dt.date(2026, 10, 28))
    assert texte == ["Ausweis gilt nur noch bis 28.10.2026 – bitte ins Büro"]
    haushalt.ausweis_gueltig_bis = dt.date(2027, 6, 30)
    assert farbe_und_texte(haushalt, einstellungen, heute=dt.date(2026, 10, 28))[1] == [
        "Willkommen!"]  # fmt: skip
    haushalt.kundengruppe = None
    assert farbe_und_texte(haushalt, einstellungen)[1] == [
        "{unbekannt} {gruppe.__class__} bleibt stehen"]  # fmt: skip
    # leerer eigener Text = Standard
    einstellungen.meldungstexte = {"ok": "  "}
    haushalt.kundengruppe = Kundengruppe.objects.get()
    assert farbe_und_texte(haushalt, einstellungen, heute=dt.date(2026, 10, 28))[1] == [
        "Alles in Ordnung"]  # fmt: skip


def test_meldungstexte_in_den_einstellungen(admin_client):
    from django.urls import reverse

    from apps.ausgabe.forms import AusgabeEinstellungenForm

    url = reverse("ausgabe:einstellungen")
    seite = admin_client.get(url).content.decode()
    assert "Text der Ampel: Heute nicht dran" in seite and "{gruppe}, {tage}" in seite
    daten = {k: v for k, v in AusgabeEinstellungenForm(
        instance=AusgabeEinstellungen.laden()).initial.items() if v is not None}  # fmt: skip
    daten.update({"text_ok": "Willkommen!", "text_nicht_dran": " ", "zusatzbeitraege": "[]"})
    daten = {k: ("on" if v is True else v) for k, v in daten.items() if v is not False}
    admin_client.post(url, daten)
    assert AusgabeEinstellungen.laden().meldungstexte == {"ok": "Willkommen!"}
    assert 'value="Willkommen!"' in admin_client.get(url).content.decode()


def test_noch_nicht_dran_blinkt_gelb(haushalt, einstellungen):
    b = ampel.bewerten(haushalt, HEUTE, None, einstellungen)
    assert b.farbe == ampel.GRUEN
    # Hinweis ohne „warten“ (z. B. schon aufgerufen) lässt alles grün
    assert ampel.noch_nicht_dran(b, [{"text": "Aufgerufen", "farbe": "gruen"}]).farbe == "gruen"
    b = ampel.noch_nicht_dran(b, [{"text": "Noch nicht aufgerufen", "warten": True}])
    assert b.blinken and b.farbe == ampel.GELB and b.darf_abholen
    assert [m.text for m in b.meldungen] == ["Noch nicht aufgerufen – Eintragen geht trotzdem"]
    # Rot bleibt rot und blinkt nicht
    Sperre.objects.create(haushalt=haushalt, von=HEUTE, begruendung="Test")
    rot = ampel.noch_nicht_dran(ampel.bewerten(haushalt, HEUTE, None, einstellungen),
                                [{"text": "x", "warten": True}])  # fmt: skip
    assert rot.farbe == ampel.ROT and not rot.blinken
