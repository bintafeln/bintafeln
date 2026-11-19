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

    assert konto.abgleiche_stand() == {"kunden": 1, "korrekturen": 5}
    assert Buchung.objects.count() == 5  # der Stand ändert nichts

    erg = konto.abgleiche_nachrechnen("Büro")
    assert erg["kunden"] == 1
    kundin.refresh_from_db()
    assert kundin.kontostand == Decimal("1.50")  # bleibt
    assert _bar_je_tag(kundin) == {dt.date(2026, 11, 3): Decimal("6.00")}
    assert not Buchung.objects.filter(art=Buchung.Art.KORREKTUR).exists()
    # ein zweites Mal: nichts mehr zu tun
    assert konto.abgleiche_nachrechnen("Büro") == {"kunden": 0, "buchungen": 0, "offen": 0}


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
    assert "Frühere Abgleiche in die Kasse übernehmen" in inhalt
    assert "Nachrechnen läuft" not in inhalt
    assert admin_client.post(url, {"aktion": "nachrechnen"}).status_code == 302
    assert _bar_je_tag(kundin) == {dt.date(2026, 11, 3): Decimal("6.00")}
    assert 'id="nachrechnen"' not in admin_client.get(url).content.decode()


def test_haushaltsseite_zeigt_bar_gezahlt(admin_client, kundin):
    from apps.uebernahme import besuche_konto

    for tag, beitrag, stand in TAGE:
        besuche_konto.uebernehmen(besuche_konto.lesen(_liste(tag, beitrag, stand)), "Büro")
    inhalt = admin_client.get(reverse("kunden:haushalt", args=["04711"])).content.decode()
    assert "Bar gezahlt" in inhalt and "6,00 €" in inhalt


def _zweite_kundin():
    h = Haushalt.objects.create(kundennummer="04712", kontostand=Decimal("0"))
    Person.objects.create(haushalt=h, vorname="Hanna", nachname="Beispiel",
                          geburtsdatum=dt.date(1965, 3, 2), ist_hauptperson=True)  # fmt: skip
    return h


def test_nachrechnen_in_portionen(admin_client, kundin, monkeypatch):
    """Viele Kunden: Ein Aufruf hört nach der Zeit auf, die Seite ruft von selbst weiter auf –
    und öffnet sofort, ohne vorher alles durchzurechnen."""
    from apps.core.models import TafelEinstellungen
    from apps.uebernahme import views

    t = TafelEinstellungen.laden()
    t.module = sorted(set(t.module or []) | {"uebernahme"})
    t.save()
    zweite = _zweite_kundin()
    for h in (kundin, zweite):
        for tag, beitrag, stand in TAGE:
            _alter_abgleich(h, tag, beitrag, stand)
    # Zeit sofort um: je Aufruf genau ein Kunde
    erg = konto.abgleiche_nachrechnen("Büro", sekunden=0.000001)
    assert erg["kunden"] == 1 and erg["offen"] == 1
    assert konto.abgleiche_stand()["kunden"] == 1

    # Seite öffnen rechnet nichts um
    url = reverse("uebernahme:besuche_konto")
    monkeypatch.setattr(konto, "_abgleich_umrechnen", lambda *a, **k: pytest.fail("rechnet"))
    assert "Frühere Abgleiche" in admin_client.get(url).content.decode()
    monkeypatch.undo()

    # Weiterlaufen über htmx: solange etwas offen ist, zurück auf die Seite mit „läuft“
    for h in (kundin,):
        _alter_abgleich(h, dt.date(2026, 11, 24), "1,50", "0,00")
    monkeypatch.setattr(views, "NACHRECHNEN_S", 0.000001)
    antwort = admin_client.post(url, {"aktion": "nachrechnen"}, HTTP_HX_REQUEST="true")
    assert antwort.status_code == 204 and "laeuft=1#" in antwort["HX-Redirect"]
    laeuft = admin_client.get(url + "?laeuft=1").content.decode()
    assert 'hx-trigger="load delay:300ms"' in laeuft and "Nachrechnen läuft" in laeuft
    antwort = admin_client.post(url, {"aktion": "nachrechnen"}, HTTP_HX_REQUEST="true")
    assert antwort["HX-Redirect"] == url
    assert konto.abgleiche_stand() == {"kunden": 0, "korrekturen": 0}
    for h in (kundin, zweite):
        h.refresh_from_db()
        assert _bar_je_tag(h)[dt.date(2026, 11, 3)] == Decimal("6.00")
    assert kundin.kontostand == Decimal("0.00") and zweite.kontostand == Decimal("1.50")


def _alte_abholungen(h):
    """Drei alte Abholungen aus dem bisherigen Programm, ohne jede Buchung."""
    for tag, _, _ in TAGE:
        Abholung.objects.create(haushalt=h, datum=tag, beitrag=Decimal("6.00"))


def test_alte_abholungen_schaetzen(kundin):
    """Ohne Kassendaten bleibt die Kasse leer; die Schätzung bucht den Beitrag nach den Regeln als
    bar gezahlt am Tag der Abholung – gekennzeichnet, ohne den Kontostand zu ändern."""
    from apps.ausgabe import kasse
    from apps.ausgabe.models import BeitragsfreierZeitraum

    kundin.kontostand = Decimal("1.50")
    kundin.save()
    _alte_abholungen(kundin)
    # nicht angefasst: am Einlass erfasst, schon gebucht, nach dem Stichtag, beitragsfreier Tag
    erfasst = dt.datetime(2026, 11, 5, 10, tzinfo=dt.UTC)
    einlass = Abholung.objects.create(haushalt=kundin, datum=erfasst.date(), erfasst_am=erfasst)
    Abholung.objects.create(haushalt=kundin, datum=dt.date(2026, 11, 12))
    Buchung.objects.create(haushalt=kundin, kundennummer="04711", datum=dt.date(2026, 11, 12),
                           art=Buchung.Art.ABHOLUNG, soll=Decimal("1.50"), haben=Decimal("1.50"),
                           bar=Decimal("1.50"))  # fmt: skip
    spaeter = Abholung.objects.create(haushalt=kundin, datum=dt.date(2026, 11, 24))
    Abholung.objects.create(haushalt=kundin, datum=dt.date(2026, 10, 27))
    BeitragsfreierZeitraum.objects.create(bezeichnung="Herbst", von=dt.date(2026, 10, 26),
                                          bis=dt.date(2026, 10, 30))  # fmt: skip
    Abholung.objects.create(haushalt=kundin, datum=TAGE[0][0], uhrzeit=dt.time(11))  # doppelt
    bis = dt.date(2026, 11, 20)
    stand = konto.schaetzung_stand(bis)
    assert stand["offen"]["anzahl"] == 5 and stand["offen"]["kunden"] == 1
    assert stand["geschaetzt"] == 0

    erg = konto.alte_abholungen_schaetzen(bis, "Büro")
    assert erg == {"buchungen": 3, "summe": Decimal("4.50"), "weiter": None}
    kundin.refresh_from_db()
    assert kundin.kontostand == Decimal("1.50")  # unverändert
    neu = Buchung.objects.filter(bemerkung=konto.GESCHAETZT)
    assert {b.datum for b in neu} == {t for t, _, _ in TAGE}
    assert all(b.bar == b.soll == b.haben == Decimal("1.50") and b.importiert for b in neu)
    assert not Buchung.objects.filter(abholung__in=[einlass, spaeter]).exists()
    assert kasse.summe(Buchung.objects.filter(datum=TAGE[1][0]))["bar_gesamt"] == Decimal("1.50")
    # Noch einmal: nichts doppelt
    assert konto.alte_abholungen_schaetzen(bis, "Büro")["buchungen"] == 0
    assert konto.schaetzung_stand(bis)["summe"] == Decimal("4.50")
    # Wieder entfernen: alles wie vorher
    assert konto.schaetzung_entfernen() == 3
    kundin.refresh_from_db()
    assert kundin.kontostand == Decimal("1.50") and Buchung.objects.count() == 1


def test_knopf_schaetzen_in_portionen(admin_client, kundin, monkeypatch):
    from apps.core.models import TafelEinstellungen
    from apps.uebernahme import views

    t = TafelEinstellungen.laden()
    t.module = sorted(set(t.module or []) | {"uebernahme"})
    t.save()
    zweite = Haushalt.objects.create(kundennummer="04712", kontostand=Decimal("0"))
    Person.objects.create(haushalt=zweite, vorname="Max", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 1, 1), ist_hauptperson=True)  # fmt: skip
    url = reverse("uebernahme:besuche_konto")
    assert 'id="schaetzen"' not in admin_client.get(url).content.decode()
    _alte_abholungen(kundin)
    _alte_abholungen(zweite)
    seite = admin_client.get(url).content.decode()
    assert "Alte Abholungen ohne Kassendaten schätzen" in seite and "<strong>6</strong>" in seite
    # Solange alte Abgleiche offen sind, erst nachrechnen
    abgleich = Buchung.objects.create(haushalt=kundin, kundennummer="04711", haben=Decimal("0"),
                                      art=Buchung.Art.KORREKTUR,
                                      bemerkung="Abgleich Liste (Stand 03.11.2026)")  # fmt: skip
    antwort = admin_client.post(url, {"aktion": "schaetzen", "bis": "2026-11-30"}, follow=True)
    assert "zuerst die früheren Abgleiche nachrechnen" in antwort.content.decode()
    abgleich.delete()
    # Jede Portion schafft einen Kunden; die Seite ruft sich über HX-Redirect weiter auf
    monkeypatch.setattr(views, "NACHRECHNEN_S", 0.000001)
    antwort = admin_client.post(url, {"aktion": "schaetzen", "bis": "2026-11-30"},
                                HTTP_HX_REQUEST="true")  # fmt: skip
    ziel = antwort["HX-Redirect"]
    assert antwort.status_code == 204 and f"schaetzen={kundin.pk}#schaetzen" in ziel
    assert Buchung.objects.filter(bemerkung=konto.GESCHAETZT).count() == 3
    seite = admin_client.get(ziel).content.decode()
    assert "Schätzen läuft" in seite and f'name="ab" value="{kundin.pk}"' in seite
    antwort = admin_client.post(url, {"aktion": "schaetzen", "bis": "2026-11-30",
                                      "ab": str(kundin.pk)}, follow=True)  # fmt: skip
    seite = antwort.content.decode()
    assert "Alte Abholungen sind geschätzt" in seite
    assert "Bisher geschätzt: <strong>6</strong>" in seite and "9,00 €" in seite
    # Haushaltsseite: kein Strich mehr, im Konto steht „geschätzt“
    haushalt = admin_client.get(reverse("kunden:haushalt", args=["04711"])).content.decode()
    assert "geschätzt (alte Abholung ohne Kassendaten)" in haushalt
    antwort = admin_client.post(url, {"aktion": "schaetzung_entfernen"}, follow=True)
    assert "6 geschätzte Buchung(en) entfernt" in antwort.content.decode()
    assert not Buchung.objects.exists()


def test_schaetzen_braucht_recht_kundenkonto_korrigieren(
    admin, kundin, benutzer_mit_rolle, anmelden, recht_geben, client
):
    from apps.core.models import TafelEinstellungen
    from apps.konten import rollen

    t = TafelEinstellungen.laden()
    t.module = sorted(set(t.module or []) | {"uebernahme"})
    t.save()
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    recht_geben(rollen.AUSGABE, "kunden.importieren")
    assert not rollen.hat_recht(b, "konto.korrektur")
    _alte_abholungen(kundin)
    c = anmelden(client, b)
    url = reverse("uebernahme:besuche_konto")
    assert "Zum Schätzen fehlt das Recht" in c.get(url).content.decode()
    for aktion in ("schaetzen", "schaetzung_entfernen"):
        antwort = c.post(url, {"aktion": aktion}, follow=True)
        assert "fehlt das Recht" in antwort.content.decode()
    assert not Buchung.objects.exists()
