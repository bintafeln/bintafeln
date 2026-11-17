"""Tageslisten aus dem bisherigen Programm: was bar gezahlt wurde, kommt in die Kasse.

Beispiel (erfunden): Eine Kundin zahlt am Monatsanfang 6,00 € für den Monat (1,50 € je Besuch),
danach lebt sie vom Guthaben. Die Listen nennen den Kontostand danach: 4,50 / 3,00 / 1,50 €.
"""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.ausgabe import konto
from apps.ausgabe.models import AusgabeEinstellungen, Buchung
from apps.kunden.models import Abholung, Haushalt, Person

pytestmark = pytest.mark.django_db

TAGE = [(dt.date(2026, 11, 3), "6,00", "4,50"), (dt.date(2026, 11, 10), "1,50", "3,00"),
        (dt.date(2026, 11, 17), "1,50", "1,50")]  # fmt: skip


@pytest.fixture
def kundin():
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_person = Decimal("1.50")
    e.zusatzbeitraege = False
    e.save()
    h = Haushalt.objects.create(kundennummer="04711", kontostand=Decimal("0"))
    Person.objects.create(haushalt=h, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1970, 5, 1), ist_hauptperson=True)  # fmt: skip
    return h


def _liste(tag, beitrag, stand) -> bytes:
    return (
        "Kundennummer;Letzter Besuch;Uhrzeit;Beitrag;Kontostand\n"
        f"04711;{tag:%d.%m.%Y};10:15;{beitrag} €;{stand} €\n"
    ).encode("utf-8-sig")


def _bar_je_tag(h):
    tage = {}
    for b in Buchung.objects.filter(kundennummer=h.kundennummer):
        tage[b.datum] = tage.get(b.datum, Decimal("0")) + b.bar
    return {t: v for t, v in tage.items() if v}


def test_tageslisten_buchen_was_bar_gezahlt_wurde(kundin):
    from apps.uebernahme import besuche_konto

    for tag, beitrag, stand in TAGE:
        besuche_konto.uebernehmen(besuche_konto.lesen(_liste(tag, beitrag, stand)), "Büro")
    kundin.refresh_from_db()
    assert kundin.kontostand == Decimal("1.50")
    assert _bar_je_tag(kundin) == {dt.date(2026, 11, 3): Decimal("6.00")}
    # Jede Abholung kostet 1,50 € (Beitragsregel), nicht die 6,00 € aus der Liste
    assert {a.beitrag for a in Abholung.objects.filter(haushalt=kundin)} == {Decimal("1.50")}
    zahlweisen = dict(Buchung.objects.filter(art=Buchung.Art.ABHOLUNG)
                      .values_list("datum", "zahlweise"))  # fmt: skip
    assert zahlweisen[dt.date(2026, 11, 10)] == Buchung.Zahlweise.GUTHABEN
    assert not Buchung.objects.filter(art=Buchung.Art.KORREKTUR).exists()
    # Haushaltsseite zeigt „bar gezahlt“ je Abholung
    abholungen = konto.mit_bar_gezahlt(kundin, list(Abholung.objects.filter(haushalt=kundin)))
    assert sorted(a.bar_gezahlt for a in abholungen) == [Decimal("0"), Decimal("0"),
                                                         Decimal("6.00")]  # fmt: skip


def test_abweichung_wird_korrigiert_auch_ohne_offene_abholung(kundin):
    from apps.uebernahme import besuche_konto

    tag, beitrag, stand = TAGE[0]
    besuche_konto.uebernehmen(besuche_konto.lesen(_liste(tag, beitrag, stand)), "Büro")
    # dieselbe Liste noch einmal, aber im bisherigen Programm inzwischen korrigiert
    besuche_konto.uebernehmen(besuche_konto.lesen(_liste(tag, beitrag, "5,00")), "Büro")
    kundin.refresh_from_db()
    assert kundin.kontostand == Decimal("5.00")
    k = Buchung.objects.get(art=Buchung.Art.KORREKTUR)
    assert k.haben == Decimal("0.50") and k.bar == 0  # Korrektur ist kein Bargeld
    assert not konto.ABGLEICH.match(k.bemerkung)  # wird nie „nachgerechnet“


def _alter_abgleich(h, tag, beitrag, stand):
    """So hat „Besuche übernehmen“ bisher gebucht: Abholung ohne Buchung + Korrektur."""
    if not Abholung.objects.filter(haushalt=h, datum=tag).exists():
        Abholung.objects.create(haushalt=h, datum=tag, uhrzeit=dt.time(10, 15),
                                beitrag=Decimal(beitrag.replace(",", ".")),
                                eingetragen_von="Büro", nachgetragen=True)  # fmt: skip
    h.refresh_from_db()
    differenz = Decimal(stand.replace(",", ".")) - h.kontostand
    if differenz:
        konto.korrigieren(h, differenz, f"Abgleich bisheriges Programm (Stand {tag:%d.%m.%Y})",
                          "Büro")  # fmt: skip


def test_fruehere_abgleiche_nachrechnen(kundin):
    for tag, beitrag, stand in TAGE:
        _alter_abgleich(kundin, tag, beitrag, stand)
    _alter_abgleich(kundin, *TAGE[1])  # Liste vom 10.11. nach der vom 17.11. noch einmal
    _alter_abgleich(kundin, *TAGE[2])
    kundin.refresh_from_db()
    assert kundin.kontostand == Decimal("1.50") and _bar_je_tag(kundin) == {}

    vorschau = konto.abgleiche_vorschau()
    assert vorschau["kunden"] == 1 and vorschau["korrekturen"] == 5
    assert vorschau["tage"] == [(dt.date(2026, 11, 3), Decimal("6.00"))]
    assert Buchung.objects.count() == 5  # die Vorschau ändert nichts

    erg = konto.abgleiche_nachrechnen("Büro")
    assert erg["kunden"] == 1
    kundin.refresh_from_db()
    assert kundin.kontostand == Decimal("1.50")  # bleibt
    assert _bar_je_tag(kundin) == {dt.date(2026, 11, 3): Decimal("6.00")}
    assert not Buchung.objects.filter(art=Buchung.Art.KORREKTUR).exists()
    # ein zweites Mal: nichts mehr zu tun
    assert konto.abgleiche_nachrechnen("Büro") == {"kunden": 0, "buchungen": 0}


def test_nachrechnen_laesst_einlass_buchungen_stehen(kundin):
    # 03.11. am Einlass gebucht (6,00 € bar), 10.11. und 17.11. per altem Abgleich
    a = Abholung.objects.create(haushalt=kundin, datum=TAGE[0][0], beitrag=Decimal("1.50"))
    e = AusgabeEinstellungen.laden()
    konto.abholung_buchen(a, Decimal("1.50"), Decimal("6.00"), e, None, "Einlass")
    for tag, beitrag, stand in TAGE[1:]:
        _alter_abgleich(kundin, tag, beitrag, stand)
    kundin.refresh_from_db()
    vorher = kundin.kontostand
    konto.abgleiche_nachrechnen("Büro")
    kundin.refresh_from_db()
    assert kundin.kontostand == vorher == Decimal("1.50")
    assert _bar_je_tag(kundin) == {dt.date(2026, 11, 3): Decimal("6.00")}
    assert Buchung.objects.filter(art=Buchung.Art.ABHOLUNG).count() == 3


def test_knopf_nachrechnen(admin_client, kundin):
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.module = sorted(set(t.module or []) | {"uebernahme"})
    t.save()
    for tag, beitrag, stand in TAGE:
        _alter_abgleich(kundin, tag, beitrag, stand)
    url = reverse("uebernahme:besuche_konto")
    inhalt = admin_client.get(url).content.decode()
    assert "Frühere Abgleiche in die Kasse übernehmen" in inhalt and "6,00 €" in inhalt
    assert admin_client.post(url, {"aktion": "nachrechnen"}).status_code == 302
    assert _bar_je_tag(kundin) == {dt.date(2026, 11, 3): Decimal("6.00")}
    assert "Frühere Abgleiche" not in admin_client.get(url).content.decode()


def test_haushaltsseite_zeigt_bar_gezahlt(admin_client, kundin):
    from apps.uebernahme import besuche_konto

    for tag, beitrag, stand in TAGE:
        besuche_konto.uebernehmen(besuche_konto.lesen(_liste(tag, beitrag, stand)), "Büro")
    inhalt = admin_client.get(reverse("kunden:haushalt", args=["04711"])).content.decode()
    assert "Bar gezahlt" in inhalt and "6,00 €" in inhalt
