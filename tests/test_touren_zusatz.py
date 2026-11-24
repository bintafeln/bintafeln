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
from apps.touren.models import Station, Tour, Umstand, Zusatzstopp
from tests.test_touren_lieferscheine import unterschrift

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def module_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["touren", "fahrdienst"]
    t.save()


def ABGEHOLT():  # noqa: N802
    return Umstand.objects.get(name="Abgeholt").pk


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
    anfahrten.markieren(nord, Station.objects.get(kennung="M-1"), fritz, ABGEHOLT())
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
    anfahrten.markieren(nord, extra, fritz, ABGEHOLT())
    stand = anfahrten.fortschritt(nord, heute)
    assert (stand["gesamt"], stand["erledigt"], stand["zusatz"], stand["prozent"]) == (5, 2, 2, 40)
    assert stand["naechste"].name == "Markt 2"
    # doppelt als Zusatzstopp geht nicht, nicht mehr angefahren auch nicht
    with pytest.raises(zusatz.ZusatzFehler, match="schon als Zusatzstopp"):
        zusatz.einfuegen(nord, heute, fritz, extra)
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
    # auch auf „Touren heute“ steht der Knopf an der eigenen Tour (wie an den anderen Karten)
    assert adresse in client.get(reverse("touren:heute")).content.decode()
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
    anfahrten.markieren(nord, Station.objects.get(kennung="M-1"), lage["fritz"], ABGEHOLT())
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


# --- Besetzung am Tag selbst ändern (Mannschaft, vom Handy) -------------------------------------


def test_mannschaft_aendert_besetzung_der_kurzfristigen_tour(client, anmelden, lage,
                                                            django_user_model):  # fmt: skip
    nord, fritz = lage["nord"], lage["fritz"]
    paula = person(django_user_model, "Paula", "Beifahrer")
    anmelden(client, fritz)
    seite = client.get(reverse("touren:fahren", args=[nord.pk])).content.decode()
    start = reverse("touren:start", args=[nord.pk])
    assert f"{start}?aendern=1" in seite and "Besetzung ändern, Mitfahrer oder Gast" in seite
    maske = client.get(start).content.decode()
    assert "Wer fährt heute mit?" in maske and "Paula Probe" in maske
    ich = Adresse.objects.get(konto=fritz)
    antwort = client.post(start, {"fahrer": ich.pk, "beifahrer": paula.pk, "gast": "Gerd Gast"})
    assert antwort.status_code == 302
    nord.refresh_from_db()
    assert (nord.beifahrer, nord.gast) == (paula, "Gerd Gast")
    assert set(nord.personen.all()) == {ich, paula}
    namen_ = [b["name"] for b in ablauf.besetzung(nord, lage["heute"])]
    assert namen_ == ["Fritz Probe", "Paula Probe", "Gerd Gast"]
    # sich selbst herausnehmen geht nicht
    antwort = client.post(start, {"fahrer": paula.pk})
    assert antwort.status_code == 200 and "nicht selbst aus der Tour" in antwort.content.decode()
    nord.refresh_from_db()
    assert nord.fahrer == ich
    # dieselbe Person auf zwei Plätzen auch nicht
    antwort = client.post(start, {"fahrer": ich.pk, "beifahrer": ich.pk})
    assert antwort.status_code == 200


def test_besetzung_aendern_nur_vor_der_abfahrt(client, anmelden, lage, django_user_model):
    """Hat die Fahrt begonnen, ist der Knopf weg, und die Änderung wird abgelehnt."""
    from apps.touren import fahrten
    from apps.touren.models import Fahrzeug

    nord, fritz = lage["nord"], lage["fritz"]
    paula = person(django_user_model, "Paula", "Beifahrer")
    wagen = Fahrzeug.objects.create(name="Kühlwagen", kennzeichen="MU-ST 1")
    fahrten.beginnen(nord, fritz, "100", wagen.pk)
    anmelden(client, fritz)
    seite = client.get(reverse("touren:fahren", args=[nord.pk])).content.decode()
    assert "Besetzung ändern, Mitfahrer" not in seite
    start = reverse("touren:start", args=[nord.pk])
    ich = Adresse.objects.get(konto=fritz)
    antwort = client.post(start, {"fahrer": ich.pk, "beifahrer": paula.pk}, follow=True)
    assert "Die Fahrt hat schon begonnen" in antwort.content.decode()
    nord.refresh_from_db()
    assert nord.beifahrer is None


def test_fremde_aendern_die_besetzung_nicht_das_buero_schon(client, anmelden, lage):
    nord, klaus = lage["nord"], lage["klaus"]
    start = reverse("touren:start", args=[nord.pk])
    anmelden(client, klaus)  # fährt die Südtour
    seite = client.get(reverse("touren:fahren", args=[nord.pk])).content.decode()
    assert "Besetzung ändern, Mitfahrer" not in seite
    ich = Adresse.objects.get(konto=klaus)
    assert client.post(start, {"fahrer": ich.pk}).status_code == 302
    nord.refresh_from_db()
    assert nord.fahrer != ich
    # das Büro (Recht „Besetzung“) darf jede Besetzung eintragen, auch ohne selbst mitzufahren
    anmelden(client, lage["buero"])
    assert client.post(start, {"fahrer": ich.pk}).status_code == 302
    nord.refresh_from_db()
    assert nord.fahrer == ich


def test_besetzung_aendern_nur_am_tag_der_tour(client, anmelden, lage):
    nord, fritz = lage["nord"], lage["fritz"]
    nord.datum = lage["heute"] + dt.timedelta(days=1)
    nord.save()
    anmelden(client, fritz)
    morgen = f"?tag={nord.datum:%Y-%m-%d}"
    seite = client.get(reverse("touren:fahren", args=[nord.pk]) + morgen).content.decode()
    assert "Besetzung ändern, Mitfahrer" not in seite
    antwort = client.post(reverse("touren:start", args=[nord.pk]), {"gast": "Gerd Gast"})
    assert antwort.status_code == 302
    nord.refresh_from_db()
    assert nord.gast == ""


def test_station_mehrfach_auf_der_tour(client, anmelden, lage):
    """Eine Station – z. B. die Zentrale zum Abladen – steht zweimal auf der Tour (ADR 0172):
    Jeder Besuch wird für sich abgehakt, der Fortschritt zählt beide."""
    from apps.touren.models import Anfahrt

    nord, heute, fritz = lage["nord"], lage["heute"], lage["fritz"]
    lager = station(50, name="Zentrale", lieferschein=False)
    for h in nord.halte.all():  # Folge: Markt 1, Zentrale, Markt 2, Markt 3, Zentrale
        h.reihenfolge = {"Markt 1": 1, "Markt 2": 3, "Markt 3": 4}[h.station.name]
        h.save()
    from apps.touren.models import Halt

    Halt.objects.create(tour=nord, station=lager, reihenfolge=2)
    ablauf.halt_anhaengen(nord, lager)
    assert namen(nord, heute) == ["Markt 1", "Zentrale", "Markt 2", "Markt 3", "Zentrale"]
    assert [h.durchgang for h in ablauf.halte(nord, heute)] == [1, 1, 1, 1, 2]
    # der erste Besuch abgehakt: der zweite bleibt offen
    anfahrten.markieren(nord, Station.objects.get(kennung="M-1"), fritz, ABGEHOLT())
    anfahrten.markieren(nord, lager, fritz, ABGEHOLT())
    stand = anfahrten.fortschritt(nord, heute)
    assert (stand["gesamt"], stand["erledigt"], stand["naechste"].name) == (5, 2, "Markt 2")
    assert [h.angefahren for h in anfahrten.stand(nord, heute)] == [True, True, False, False, False]
    # die Seite zeigt beide Besuche und schickt mit, welcher gemeint ist
    anmelden(client, fritz)
    seite = client.get(reverse("touren:fahren", args=[nord.pk])).content.decode()
    assert "1. Anfahrt" in seite and "2. Anfahrt" in seite
    assert 'name="durchgang" value="2"' in seite
    ziel = reverse("touren:angefahren", args=[nord.pk, lager.pk])
    client.post(ziel, {"umstand": ABGEHOLT(), "durchgang": "2"})
    assert sorted(Anfahrt.objects.filter(station=lager).values_list("durchgang", flat=True)) == [
        1, 2,
    ]  # fmt: skip
    assert anfahrten.fortschritt(nord, heute)["erledigt"] == 3
    # zurücknehmen trifft nur diesen Besuch
    client.post(ziel, {"zurueck": "1", "durchgang": "2"})
    assert list(Anfahrt.objects.filter(station=lager).values_list("durchgang", flat=True)) == [1]
    # einen dritten Besuch gibt es nicht
    with pytest.raises(anfahrten.AnfahrtFehler, match="nicht auf der Tour"):
        anfahrten.markieren(nord, lager, fritz, ABGEHOLT(), durchgang=3)
    # ein Zusatzstopp an einer Station, die schon auf der Tour steht, ist ein weiterer Besuch
    zusatz.einfuegen(nord, heute, fritz, Station.objects.get(kennung="M-1"))
    assert namen(nord, heute).count("Markt 1") == 2
