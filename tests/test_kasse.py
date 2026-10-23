import datetime as dt
from decimal import Decimal as D

import pytest
from django.urls import reverse

from apps.ausgabe import kasse
from apps.ausgabe.models import Buchung
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle, Haushalt

pytestmark = pytest.mark.django_db

KASSE = reverse("ausgabe:kasse")
TAG = dt.date(2026, 10, 23)  # Freitag


@pytest.fixture
def als(client, admin, benutzer_mit_rolle, anmelden):
    def anmelden_als(rolle):
        return anmelden(client, benutzer_mit_rolle(rolle.lower(), rolle))

    return anmelden_als


@pytest.fixture
def buchungen():
    """Erfundene Buchungen an zwei Ausgabestellen und mehreren Tagen."""
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    h = Haushalt.objects.create(kundennummer="00042")

    def b(datum, art, stelle=mitte, zahlweise="", soll="0", haben="0", bar="0", haushalt=h):
        return Buchung.objects.create(
            haushalt=haushalt, kundennummer="00042" if haushalt else "", datum=datum, art=art,
            zahlweise=zahlweise, soll=D(soll), haben=D(haben), bar=D(bar), ausgabestelle=stelle,
        )  # fmt: skip

    A, E, K = Buchung.Art.ABHOLUNG, Buchung.Art.EINZAHLUNG, Buchung.Art.KORREKTUR
    b(TAG, A, zahlweise="bar", soll="3", haben="3", bar="3")
    b(TAG, A, zahlweise="guthaben", soll="3", haben="1", bar="1")
    b(TAG, A, nord, zahlweise="anschreiben", soll="2")
    b(TAG, E, nord, haben="20", bar="20")
    b(TAG, K, None, haben="1.50")
    b(TAG, K, None, soll="0.50", haushalt=None)
    b(dt.date(2026, 10, 2), A, zahlweise="bar", soll="3", haben="3", bar="3")
    b(dt.date(2026, 3, 6), E, haben="10", bar="10")
    b(dt.date(2025, 12, 31), E, haben="99", bar="99")
    return mitte, nord


# --- Auswertung -------------------------------------------------------------------------


def test_summe_eines_tages(buchungen):
    s = kasse.summe(Buchung.objects.filter(datum=TAG))
    assert s == {
        "abholungen": 3,
        "beitraege": D("8.00"),
        "beitraege_bar": D("4.00"),
        "vom_konto": D("2.00"),
        "angeschrieben": D("2.00"),
        "einzahlungen": D("20.00"),
        "bar_gesamt": D("24.00"),
        "korrekturen": D("1.00"),
    }


def test_leerer_zeitraum_ergibt_nullen():
    s = kasse.summe(Buchung.objects.none())
    assert s["abholungen"] == 0 and s["bar_gesamt"] == D("0.00") and s["korrekturen"] == D("0.00")


def test_gruppierungen(buchungen):
    tag = kasse.nach_ausgabestelle(Buchung.objects.filter(datum=TAG))
    assert [(z["gruppe"], z["bar_gesamt"]) for z in tag] == [
        ("Mitte", D("4.00")),
        ("Nord", D("20.00")),
        (None, D("0.00")),
    ]
    monat = kasse.nach_tag(Buchung.objects.filter(datum__year=2026, datum__month=10))
    assert [(z["gruppe"], z["abholungen"]) for z in monat] == [
        (dt.date(2026, 10, 2), 1),
        (TAG, 3),
    ]
    jahr = kasse.nach_monat(Buchung.objects.filter(datum__year=2026))
    assert [(z["gruppe"].month, z["bar_gesamt"]) for z in jahr] == [
        (3, D("10.00")),
        (10, D("27.00")),
    ]


# --- Ansicht -----------------------------------------------------------------------------


def test_kiosk_kein_zugriff(als):
    assert als(rollen.KIOSK).get(KASSE).status_code == 403


def test_ausgabe_sieht_summen_aber_keine_einzelbuchungen(als, buchungen):
    client = als(rollen.AUSGABE)
    assert "Kasse</a>" in client.get("/").content.decode()
    inhalt = client.get(KASSE, {"datum": "2026-10-23"}).content.decode()
    assert "Fr 23.10.2026" in inhalt and "Bar eingenommen: 24,00 €" in inhalt
    assert "ohne Ausgabestelle" in inhalt and "Buchungen des Tages" not in inhalt


def test_buero_sieht_einzelbuchungen(als, buchungen):
    inhalt = als(rollen.BUERO).get(KASSE, {"datum": "2026-10-23"}).content.decode()
    assert "Buchungen des Tages" in inhalt
    assert reverse("kunden:haushalt", args=["00042"]) in inhalt
    assert "(anschreiben)" in inhalt


def test_tag_ohne_buchungen_und_ungueltiges_datum(admin_client):
    inhalt = admin_client.get(KASSE, {"datum": "kaputt"}).content.decode()
    assert "Keine Buchungen in diesem Zeitraum." in inhalt
    assert "<tfoot>" not in inhalt


def test_filter_ausgabestelle_und_blaettern(admin_client, buchungen):
    _, nord = buchungen
    antwort = admin_client.get(KASSE, {"datum": "2026-10-23", "stelle": nord.pk})
    inhalt = antwort.content.decode()
    assert "Bar eingenommen: 20,00 €" in inhalt and "· Nord" in inhalt
    assert f"datum=2026-10-22&amp;stelle={nord.pk}" in inhalt
    assert f"datum=2026-10-24&amp;stelle={nord.pk}" in inhalt
    unbekannt = admin_client.get(KASSE, {"datum": "2026-10-23", "stelle": "999"})
    assert unbekannt.context["stelle"] is None


def test_monatsansicht(admin_client, buchungen):
    inhalt = admin_client.get(KASSE, {"ansicht": "monat", "monat": "2026-10"}).content.decode()
    assert "Oktober 2026" in inhalt and "Bar eingenommen: 27,00 €" in inhalt
    assert "ansicht=tag&amp;datum=2026-10-23" in inhalt and "Fr 23.10." in inhalt
    januar = admin_client.get(KASSE, {"ansicht": "monat", "monat": "2026-01"}).content.decode()
    assert "monat=2025-12" in januar and "monat=2026-02" in januar


def test_jahresansicht(admin_client, buchungen):
    inhalt = admin_client.get(KASSE, {"ansicht": "jahr", "jahr": "2026"}).content.decode()
    assert "Jahr 2026" in inhalt and "Bar eingenommen: 37,00 €" in inhalt
    assert "ansicht=monat&amp;monat=2026-03" in inhalt and ">März<" in inhalt
    assert "jahr=2025" in inhalt and "jahr=2027" in inhalt
    assert (
        "Bar eingenommen: 99,00 €"
        in admin_client.get(KASSE, {"ansicht": "jahr", "jahr": "2025"}).content.decode()
    )


@pytest.mark.parametrize(("eingabe", "jahr"), [("1800", 2000), ("9999", 2100), ("abc", None)])
def test_jahr_wird_begrenzt(admin_client, eingabe, jahr):
    antwort = admin_client.get(KASSE, {"ansicht": "jahr", "jahr": eingabe})
    erwartet = jahr or antwort.context["beginn"].year
    assert antwort.context["titel"] == f"Jahr {erwartet}"


def test_unbekannte_ansicht_zeigt_tag(admin_client):
    assert admin_client.get(KASSE, {"ansicht": "woche"}).context["ansicht"] == "tag"
