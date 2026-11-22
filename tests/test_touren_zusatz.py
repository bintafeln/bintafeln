"""Modul Touren: Zusatzstopps, Fortschritt, Lieferscheine nur für die eigene Tour (ADR 0156).
Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.adressen.models import Adresse
from apps.core.models import PapierkorbEintrag, TafelEinstellungen
from apps.touren import ablauf, anfahrten, lieferscheine, zusatz
from apps.touren.models import Station, Tour, Zusatzstopp
from tests.test_touren_lieferscheine import unterschrift

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def module_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["touren", "fahrdienst"]
    t.save()


def station(nr, **mehr):
    daten = {"kennung": f"M-{nr}", "art": "markt", "name": f"Markt {nr}", "strasse": "Musterweg",
             "hausnummer": str(nr), "plz": "12345", "ort": "Musterstadt", "lieferschein": True,
             **mehr}  # fmt: skip
    return Station.objects.create(**daten)


def person(django_user_model, name, rolle="Fahrer"):
    konto = django_user_model.objects.create_user(username=name.lower(), password="x")
    konto.groups.add(Group.objects.get(name=rolle))
    adresse = Adresse.objects.filter(konto=konto).first()
    return adresse or Adresse.objects.create(
        art=Adresse.Art.PERSON, vorname=name, nachname="Probe", konto=konto
    )


@pytest.fixture
def lage(django_user_model, benutzer_mit_rolle):
    """Zwei kurzfristige Touren heute: Fritz fährt die Nordtour, Klaus die Südtour."""
    heute = timezone.localdate()
    fritz, klaus = person(django_user_model, "Fritz"), person(django_user_model, "Klaus")
    nord = Tour.objects.create(name="Nordtour", datum=heute, fahrer=fritz)
    nord.personen.add(fritz)
    sued = Tour.objects.create(name="Südtour", datum=heute, fahrer=klaus)
    sued.personen.add(klaus)
    for nr in (1, 2, 3):
        ablauf.halt_anhaengen(nord, station(nr))
    ablauf.halt_anhaengen(sued, station(9))
    return {"heute": heute, "nord": nord, "sued": sued, "fritz": fritz.konto,
            "klaus": klaus.konto, "buero": benutzer_mit_rolle("bernd", "Büro")}  # fmt: skip


def namen(tour, tag):
    return [h.station.name for h in ablauf.halte(tour, tag)]


def test_zusatzstopp_als_naechstes_und_am_ende(lage):
    nord, heute, fritz = lage["nord"], lage["heute"], lage["fritz"]
    extra, spaet = station(20, name="Hofladen"), station(21, name="Lager")
    anfahrten.markieren(nord, Station.objects.get(kennung="M-1"), fritz)
    z = zusatz.einfuegen(nord, heute, fritz, extra, "  3 Paletten   Joghurt ")
    assert (z.hinweis, z.nach, z.angelegt_von) == ("3 Paletten Joghurt", 1, fritz)
    assert str(z).startswith("Hofladen (Zusatzstopp")
    assert namen(nord, heute) == ["Markt 1", "Hofladen", "Markt 2", "Markt 3"]
    zusatz.einfuegen(nord, heute, fritz, spaet, am_ende=True)
    assert namen(nord, heute) == ["Markt 1", "Hofladen", "Markt 2", "Markt 3", "Lager"]
    # die feste Reihenfolge der Tour bleibt; an einem anderen Tag gibt es den Stopp nicht
    assert namen(nord, None) == ["Markt 1", "Markt 2", "Markt 3"]
    assert [h.zusatz is not None for h in ablauf.halte(nord, heute)] == [False, True, False,
                                                                         False, True]  # fmt: skip
    # „Hier waren wir“ und der Fortschritt zählen den Zusatzstopp mit
    anfahrten.markieren(nord, extra, fritz)
    stand = anfahrten.fortschritt(nord, heute)
    assert (stand["gesamt"], stand["erledigt"], stand["zusatz"], stand["prozent"]) == (5, 2, 2, 40)
    assert stand["naechste"].name == "Markt 2"
    # doppelt, schon auf der Tour, nicht mehr angefahren
    with pytest.raises(zusatz.ZusatzFehler, match="schon auf der Tour"):
        zusatz.einfuegen(nord, heute, fritz, extra)
    with pytest.raises(zusatz.ZusatzFehler, match="schon auf der Tour"):
        zusatz.einfuegen(nord, heute, fritz, Station.objects.get(kennung="M-2"))
    with pytest.raises(zusatz.ZusatzFehler, match="nicht mehr angefahren"):
        zusatz.einfuegen(nord, heute, fritz, station(30, aktiv=False))


def test_fahrer_nur_an_der_eigenen_tour_buero_an_jeder(lage):
    nord, sued, heute = lage["nord"], lage["sued"], lage["heute"]
    extra = station(20, name="Hofladen")
    assert zusatz.darf(lage["fritz"], nord, heute) and not zusatz.darf(lage["fritz"], sued, heute)
    with pytest.raises(zusatz.ZusatzFehler, match="keinen Zusatzstopp"):
        zusatz.einfuegen(sued, heute, lage["fritz"], extra)
    assert zusatz.darf(lage["buero"], sued, heute)
    zusatz.einfuegen(sued, heute, lage["buero"], extra, "bitte heute noch")
    assert namen(sued, heute) == ["Hofladen", "Markt 9"]  # noch nichts angefahren: ganz vorn
    # an einem Tag, an dem die Tour nicht fährt, geht nichts – auch nicht fürs Büro
    morgen = heute + dt.timedelta(days=1)
    assert not zusatz.darf(lage["buero"], sued, morgen)
    # Frist
    Zusatzstopp.objects.update(datum=heute - dt.timedelta(days=91))
    assert zusatz.fristen_anwenden() == 1


def test_am_handy_suchen_freie_adresse_entfernen(client, anmelden, lage):
    nord, heute = lage["nord"], lage["heute"]
    station(20, name="Hofladen Beispiel", telefon="01234 55520")
    anmelden(client, lage["fritz"])
    tour_seite = client.get(reverse("touren:fahren", args=[nord.pk])).content.decode()
    adresse = reverse("touren:zusatzstopp", args=[nord.pk])
    assert "Zusatzstopp einfügen" in tour_seite and adresse in tour_seite
    seite = client.get(adresse).content.decode()
    assert "Station suchen" in seite and "steht nicht in der Liste" in seite
    treffer = client.get(adresse, {"q": "hofl"}).content.decode()
    assert "Hofladen Beispiel" in treffer and 'name="station"' in treffer
    # nichts gewählt
    antwort = client.post(adresse, {"q": "hofl", "hinweis": "Kisten"})
    assert "Bitte eine Station wählen" in antwort.content.decode()
    hof = Station.objects.get(name="Hofladen Beispiel")
    antwort = client.post(adresse, {"station": hof.pk, "hinweis": "2 Kisten Äpfel",
                                    "stelle": "naechste"})  # fmt: skip
    assert antwort.status_code == 302 and Zusatzstopp.objects.get().station == hof
    seite = client.get(reverse("touren:fahren", args=[nord.pk])).content.decode()
    assert "Zusatzstopp</span>" in seite and "2 Kisten Äpfel" in seite
    assert "Zusatzstopp entfernen" in seite
    # freie Adresse: halb eingetragen → Fehler; vollständig → neue Station am Ende
    halb = client.post(adresse, {"neu-name": "Privatspende", "neu-art": "sonstiges"})
    assert "vollständig" in halb.content.decode() and Zusatzstopp.objects.count() == 1
    client.post(adresse, {"neu-name": "Privatspende Garten", "neu-art": "sonstiges",
                          "neu-strasse": "Feldweg", "neu-hausnummer": "3", "neu-plz": "12345",
                          "neu-ort": "Musterstadt", "stelle": "ende"})  # fmt: skip
    neu = Station.objects.get(name="Privatspende Garten")
    assert neu.kennung.startswith("S-") and namen(nord, heute)[-1] == "Privatspende Garten"
    # entfernen: in den Papierkorb
    stopp = Zusatzstopp.objects.get(station=hof)
    client.post(reverse("touren:zusatzstopp_weg", args=[stopp.pk]))
    assert not Zusatzstopp.objects.filter(pk=stopp.pk).exists()
    assert PapierkorbEintrag.objects.filter(art="Zusatzstopp").exists()
    assert "Hofladen Beispiel" not in namen(nord, heute)


def test_fremde_tour_kein_zusatzstopp_am_handy(client, anmelden, lage):
    sued, heute = lage["sued"], lage["heute"]
    anmelden(client, lage["fritz"])
    seite = client.get(reverse("touren:fahren", args=[sued.pk])).content.decode()
    assert "Zusatzstopp einfügen" not in seite
    antwort = client.get(reverse("touren:zusatzstopp", args=[sued.pk]), follow=True)
    assert "keinen Zusatzstopp einfügen" in antwort.content.decode()
    hof = station(20)
    client.post(reverse("touren:zusatzstopp", args=[sued.pk]), {"station": hof.pk})
    assert not Zusatzstopp.objects.exists()
    stopp = zusatz.einfuegen(sued, heute, lage["klaus"], hof)
    client.post(reverse("touren:zusatzstopp_weg", args=[stopp.pk]))
    assert Zusatzstopp.objects.filter(pk=stopp.pk).exists()


def test_buero_sieht_fortschritt_und_fuegt_ein(client, anmelden, lage):
    nord, sued, heute = lage["nord"], lage["sued"], lage["heute"]
    anfahrten.markieren(nord, Station.objects.get(kennung="M-1"), lage["fritz"])
    anmelden(client, lage["buero"])
    seite = client.get(reverse("touren:heute")).content.decode()
    assert "1 von 3</strong> angefahren" in seite and "als Nächstes: Markt 2" in seite
    assert "0 von 1</strong> angefahren" in seite
    assert reverse("touren:zusatzstopp", args=[sued.pk]) in seite
    hof = station(20, name="Hofladen")
    client.post(reverse("touren:zusatzstopp", args=[nord.pk]),
                {"station": hof.pk, "hinweis": "eilt"})  # fmt: skip
    assert namen(nord, heute) == ["Markt 1", "Hofladen", "Markt 2", "Markt 3"]
    seite = client.get(reverse("touren:heute")).content.decode()
    assert "1 von 4</strong> angefahren" in seite and "1 Zusatzstopp" in seite


def test_lieferscheine_nur_fuer_die_eigene_tour(client, anmelden, lage):
    nord, heute = lage["nord"], lage["heute"]
    erste = Station.objects.get(kennung="M-1")
    zeichnung = lieferscheine.unterschrift_lesen(unterschrift())
    ls = lieferscheine.erstellen(erste, lage["fritz"], [("Backwaren", Decimal("1"), "kg")],
                                 zeichnung, "", nord, heute)  # fmt: skip
    pdf = reverse("touren:lieferschein_pdf", args=[ls.pk])
    tour = reverse("touren:fahren", args=[nord.pk])
    # Klaus fährt eine andere Tour: Er sieht die Station als angefahren, aber keinen Lieferschein
    anmelden(client, lage["klaus"])
    seite = client.get(tour).content.decode()
    assert "1 angefahren" in seite and "Lieferschein Nr." not in seite
    assert "Lieferschein ausfüllen" not in seite
    assert client.get(pdf).status_code == 403
    assert not lieferscheine.darf_sehen(lage["klaus"], ls)
    client.logout()
    # die eigene Mannschaft und das Büro sehen ihn
    anmelden(client, lage["fritz"])
    assert "Lieferschein Nr. 1" in client.get(tour).content.decode()
    assert client.get(pdf).status_code == 200
    client.logout()
    anmelden(client, lage["buero"])
    assert "Lieferschein Nr. 1" in client.get(tour).content.decode()
    assert client.get(pdf).status_code == 200


def test_beifahrer_der_tour_sieht_den_lieferschein(lage, django_user_model):
    nord, heute = lage["nord"], lage["heute"]
    paula = person(django_user_model, "Paula", "Beifahrer")
    nord.beifahrer = paula
    nord.save()
    nord.personen.add(paula)
    ls = lieferscheine.erstellen(
        Station.objects.get(kennung="M-1"), lage["fritz"], [("Backwaren", Decimal("1"), "kg")],
        lieferscheine.unterschrift_lesen(unterschrift()), "", nord, heute)  # fmt: skip
    assert lieferscheine.darf_sehen(paula.konto, ls)
    ls.tour = None  # Tour gelöscht: nur noch, wer ihn ausgefüllt hat
    assert not lieferscheine.darf_sehen(paula.konto, ls)
    assert lieferscheine.darf_sehen(lage["fritz"], ls)
