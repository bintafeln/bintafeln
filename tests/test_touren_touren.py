"""Modul Touren: Abholtouren mit Stationsfolge, Besetzung, Route, kurzfristige Touren und
Import der Stationsfolgen (ADR 0148). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.contrib.auth.models import Group
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.adressen.models import Adresse
from apps.core.models import MailEinstellungen, TafelEinstellungen
from apps.fahrdienst.models import Besetzung
from apps.fahrdienst.models import Tour as FahrdienstTour
from apps.touren import ablauf, importieren_touren
from apps.touren.models import Halt, Station, Tour

pytestmark = pytest.mark.django_db

MONTAG = dt.date(2026, 11, 23)
DIENSTAG = dt.date(2026, 11, 24)


@pytest.fixture(autouse=True)
def module_an():
    t = TafelEinstellungen.laden()
    t.module = ["touren", "fahrdienst"]
    t.save()


def station(nr, **mehr):
    daten = {"kennung": f"M-{nr}", "art": "markt", "name": f"Markt {nr}", "strasse": "Musterweg",
             "hausnummer": str(nr), "plz": "12345", "ort": "Musterstadt", **mehr}  # fmt: skip
    return Station.objects.create(**daten)


def tour_mit(anzahl, **mehr):
    t = Tour.objects.create(name=mehr.pop("name", "Tour 1"), **mehr)
    for nr in range(1, anzahl + 1):
        ablauf.halt_anhaengen(t, station(f"{t.pk}-{nr}"))
    return t


def person(django_user_model, name, rolle="Fahrer", email=True):
    konto = django_user_model.objects.create_user(
        username=name.lower(), password="x", email=f"{name.lower()}@example.org" if email else ""
    )
    konto.groups.add(Group.objects.get(name=rolle))
    adresse = Adresse.objects.filter(konto=konto).first()
    return adresse or Adresse.objects.create(
        art=Adresse.Art.PERSON, vorname=name, nachname="Probe", konto=konto
    )


# --- Regeln ------------------------------------------------------------------------------------


def test_eigene_tour_faehrt_an_ihren_tagen():
    t = Tour.objects.create(name="Eigene", fahrtage="Mo, Mi")
    assert ablauf.faehrt_am(t, MONTAG) and not ablauf.faehrt_am(t, DIENSTAG)
    t.fahrtage = ""
    assert ablauf.faehrt_am(t, DIENSTAG)  # nichts angehakt = jeden Tag
    t.aktiv = False
    assert not ablauf.faehrt_am(t, MONTAG)


def test_kurzfristige_tour_nur_an_ihrem_tag():
    t = Tour.objects.create(name="Sonderfahrt", datum=DIENSTAG)
    assert ablauf.faehrt_am(t, DIENSTAG) and not ablauf.faehrt_am(t, MONTAG)
    assert [x.name for x in ablauf.touren_am(DIENSTAG)] == ["Sonderfahrt"]


def test_tour_aus_dem_fahrerplan(django_user_model):
    ft = FahrdienstTour.objects.create(name="Tour 3", fahrtage="Mo, Di", plaetze=2)
    fritz = person(django_user_model, "Fritz")
    Besetzung.objects.create(tour=ft, wochentag="Mo", platz=1, person=fritz)
    t = Tour.objects.create(name="Tour 3", fahrdienst_tour=ft)
    assert ablauf.faehrt_am(t, MONTAG) and not ablauf.faehrt_am(t, dt.date(2026, 11, 27))
    # eigene Fahrtage grenzen ein: die Montags-Reihenfolge der Tour gilt nur montags
    montags = Tour.objects.create(name="Montag Tour 3", fahrdienst_tour=ft, fahrtage="Mo")
    assert ablauf.faehrt_am(montags, MONTAG) and not ablauf.faehrt_am(montags, DIENSTAG)
    assert ablauf.faehrt_am(t, DIENSTAG)
    montags.delete()
    wer = ablauf.besetzung(t, MONTAG)
    assert wer[0]["name"] == fritz.name and wer[0]["rolle"] == "Fahrer"
    assert wer[1]["offen"]  # Pflichtplatz 2 ist nicht besetzt
    assert ablauf.meine(fritz.konto, MONTAG) == [t]
    assert ablauf.meine(fritz.konto, DIENSTAG) == []
    # Fahrdienst ausgeschaltet: Die Tour gilt als eigene Tour
    e = TafelEinstellungen.laden()
    e.module = ["touren"]
    e.save()
    assert ablauf.besetzung(t, MONTAG) == []
    assert ablauf.faehrt_am(t, dt.date(2026, 11, 27))


def test_halte_nach_wochentag_und_nur_aktive_stationen():
    t = tour_mit(3)
    a, b, c = t.halte.all()
    b.wochentage = "Di"
    b.save()
    c.station.aktiv = False
    c.station.save()
    assert [h.pk for h in ablauf.halte(t)] == [a.pk, b.pk, c.pk]
    assert [h.pk for h in ablauf.halte(t, MONTAG)] == [a.pk]
    assert [h.pk for h in ablauf.halte(t, DIENSTAG)] == [a.pk, b.pk]


def test_halt_bewegen_und_station_nur_einmal():
    t = tour_mit(3)
    a, b, c = t.halte.all()
    ablauf.halt_bewegen(c, -1)
    assert [h.pk for h in t.halte.all()] == [a.pk, c.pk, b.pk]
    ablauf.halt_bewegen(a, -1)  # schon vorn: bleibt
    assert [h.reihenfolge for h in t.halte.all()] == [1, 2, 3]
    ablauf.halt_anhaengen(t, a.station)
    assert t.halte.count() == 3


def test_routen_teilen_nach_zehn_stationen():
    t = tour_mit(12)
    links = ablauf.routen([h.station for h in ablauf.halte(t)])
    assert [(r["von"], r["bis"]) for r in links] == [(1, 10), (11, 12)]
    assert links[0]["url"].startswith("https://www.google.com/maps/dir/?api=1&destination=")
    assert links[0]["url"].count("%7C") == 8  # neun Zwischenstopps
    assert "origin" not in links[0]["url"]
    assert "waypoints" not in ablauf.routen([t.halte.first().station])[0]["url"]
    assert ablauf.routen([]) == []


def test_alte_kurzfristige_touren_werden_geloescht():
    alt = tour_mit(1, name="Alt", datum=MONTAG - dt.timedelta(days=91))
    Tour.objects.create(name="Neu", datum=MONTAG - dt.timedelta(days=5))
    Tour.objects.create(name="Regel")
    assert ablauf.fristen_anwenden(MONTAG) == 1
    assert not Tour.objects.filter(pk=alt.pk).exists() and Tour.objects.count() == 2
    assert Station.objects.count() == 1  # die Station bleibt


# --- Verschicken -------------------------------------------------------------------------------


@pytest.fixture
def mail_an():
    e = MailEinstellungen.laden()
    e.server, e.absender = "smtp.example.org", "tafel@example.org"
    e.save()


def test_kurzfristige_tour_an_die_fahrer(django_user_model, mail_an):
    t = tour_mit(2, name="Sonderfahrt", datum=DIENSTAG, hinweis="Zuerst zum Lager")
    anna = person(django_user_model, "Anna")
    otto = person(django_user_model, "Otto", email=False)
    t.personen.set([anna, otto])
    mit, ohne = ablauf.senden(t, "https://tafel.example.org/touren/tour/1/")
    assert mit == [anna.name] and ohne == [otto.name]
    assert len(mail.outbox) == 1
    m = mail.outbox[0]
    assert m.to == ["anna@example.org"] and "24.11.2026" in m.subject
    assert "1. Markt" in m.body and "Zuerst zum Lager" in m.body
    assert "https://tafel.example.org/touren/tour/1/" in m.body
    t.refresh_from_db()
    assert t.gesendet_am is not None
    assert ablauf.tour_offen(t.pk) == (timezone.localdate() <= DIENSTAG)


# --- Import der Stationsfolgen -----------------------------------------------------------------

KOPF = "tour;reihenfolge;station;wochentage"


def test_import_ersetzt_die_folge_und_legt_touren_an():
    a, b, c = station(1), station(2), station(3)
    ft = FahrdienstTour.objects.create(name="Tour 3")
    alt = Tour.objects.create(name="Tour 1")
    ablauf.halt_anhaengen(alt, c)
    bleibt = Tour.objects.create(name="Bleibt")
    ablauf.halt_anhaengen(bleibt, c)
    text = "\n".join([KOPF, "Tour 1;2;M-2;", "tour 1;1;M-1;Montag", "Tour 3;1;M-3;",
                      "Tour 3;2;M-9;", "Tour 3;x;M-1;", "Tour 1;3;M-2;"])  # fmt: skip
    bericht = importieren_touren.pruefen(text)
    assert {z for z, _ in bericht.fehler} == {5, 6, 7}
    assert bericht.neue_touren == ["Tour 3"] and bericht.halte == 3
    assert importieren_touren.uebernehmen(bericht, "anton") == (2, 3)
    assert [(h.station, h.wochentage) for h in alt.halte.all()] == [(a, "Mo"), (b, "")]
    neu = Tour.objects.get(name="Tour 3")
    assert neu.fahrdienst_tour == ft and neu.angelegt_von == "anton"
    assert bleibt.halte.count() == 1


def test_import_ohne_spalten():
    with pytest.raises(importieren_touren.ImportFehler, match="station"):
        importieren_touren.pruefen("tour;reihenfolge\nA;1\n")


# --- Seiten ------------------------------------------------------------------------------------


@pytest.fixture
def buero(client, admin, benutzer_mit_rolle, anmelden):
    return anmelden(client, benutzer_mit_rolle("bernd", "Büro"))


@pytest.fixture
def fahrer(client, admin, django_user_model, anmelden):
    fritz = person(django_user_model, "Fritz")
    anmelden(client, fritz.konto)
    client.person = fritz
    return client


def test_fahrer_sieht_seine_tour_und_navigiert(fahrer):
    heute = timezone.localdate()
    t = tour_mit(2, name="Sonderfahrt", datum=heute, hinweis="Zuerst zum Lager")
    t.personen.add(fahrer.person)
    fremd = tour_mit(1, name="Andere", datum=heute)
    start = fahrer.get(reverse("core:start")).content.decode()
    assert "Ihre Tour heute" in start and reverse("touren:fahren", args=[t.pk]) in start
    liste = fahrer.get(reverse("touren:heute")).content.decode()
    assert liste.index("Sonderfahrt") < liste.index("Andere") and "Ihre Tour" in liste
    seite = fahrer.get(reverse("touren:fahren", args=[t.pk])).content.decode()
    erste = t.halte.first().station
    assert "Zuerst zum Lager" in seite and "Navigation starten" in seite
    assert erste.navigation.replace("&", "&amp;") in seite
    assert "Alle Stationen als Route" in seite and "Tour bearbeiten" not in seite
    assert fahrer.get(reverse("touren:fahren", args=[fremd.pk])).status_code == 200
    for name, args in (("touren", []), ("tour_neu", []), ("tour", [t.pk]),
                       ("touren_importieren", [])):  # fmt: skip
        assert fahrer.get(reverse(f"touren:{name}", args=args)).status_code == 403
    assert fahrer.post(reverse("touren:tour_senden", args=[t.pk])).status_code == 403


def test_anderer_tag_ueber_die_adresse(fahrer):
    tour_mit(1, name="Dienstags", fahrtage="Di")
    seite = fahrer.get(reverse("touren:heute"), {"tag": "2026-11-24"}).content.decode()
    assert "Dienstags" in seite
    seite = fahrer.get(reverse("touren:heute"), {"tag": "2026-11-23"}).content.decode()
    assert "Dienstags" not in seite and "keine Tour" in seite


def test_buero_legt_kurzfristige_tour_an_und_schickt_sie(buero, django_user_model, mail_an):
    anna = person(django_user_model, "Anna")
    fest = person(django_user_model, "Vera", rolle="Ausgabe")
    fest.konto.beschaeftigung = "fest"
    fest.konto.save()
    person(django_user_model, "Nils", rolle="Ausgabe")  # weder Fahrdienst noch angestellt
    seite = buero.get(reverse("touren:tour_neu") + "?kurz").content.decode()
    assert "Anna Probe" in seite and "Vera Probe" in seite and "Nils Probe" not in seite
    antwort = buero.post(reverse("touren:tour_neu") + "?kurz", {
        "name": "Sonderfahrt", "datum": "2026-11-24", "personen": [anna.pk, fest.pk],
        "hinweis": "", "aktiv": "on"})  # fmt: skip
    t = Tour.objects.get(name="Sonderfahrt")
    assert antwort.url == reverse("touren:tour", args=[t.pk])
    assert t.datum == DIENSTAG and t.angelegt_von == "bernd" and t.personen.count() == 2
    s1, s2 = station(1), station(2)
    for s in (s1, s2):
        buero.post(reverse("touren:halt_neu", args=[t.pk]), {"station": s.pk})
    h1, h2 = t.halte.all()
    buero.post(reverse("touren:halt_aendern", args=[h2.pk]), {"aktion": "hoch"})
    assert [h.station for h in t.halte.all()] == [s2, s1]
    buero.post(reverse("touren:halt_aendern", args=[h1.pk]),
               {"aktion": "tage", "wochentage": ["Di", "Do"]})  # fmt: skip
    assert Halt.objects.get(pk=h1.pk).wochentage == "Di, Do"
    buero.post(reverse("touren:tour_senden", args=[t.pk]))
    assert sorted(a for m in mail.outbox for a in m.to) == ["anna@example.org", "vera@example.org"]
    assert f"/touren/tour/{t.pk}/" in mail.outbox[0].body
    buero.post(reverse("touren:halt_aendern", args=[h1.pk]), {"aktion": "entfernen"})
    assert t.halte.count() == 1 and Station.objects.count() == 2


def test_regelmaessige_tour_name_nur_einmal(buero):
    Tour.objects.create(name="Tour 1")
    antwort = buero.post(reverse("touren:tour_neu"), {"name": "tour 1", "aktiv": "on"})
    assert "gibt es schon" in antwort.content.decode()
    ft = FahrdienstTour.objects.create(name="Tour 2")
    buero.post(reverse("touren:tour_neu"), {"name": "Tour 2", "fahrdienst_tour": ft.pk,
                                            "aktiv": "on"})  # fmt: skip
    t = Tour.objects.get(name="Tour 2")
    assert t.fahrdienst_tour == ft
    seite = buero.get(reverse("touren:tour", args=[t.pk])).content.decode()
    assert "Besetzung aus dem Fahrerplan" in seite and "An die Fahrer schicken" not in seite


def test_import_seite_in_zwei_schritten(buero):
    station(1)
    datei = SimpleUploadedFile("tourstationen.csv", f"{KOPF}\nTour 9;1;M-1;\n".encode())
    seite = buero.post(reverse("touren:touren_importieren"), {"datei": datei}).content.decode()
    assert "Prüfbericht" in seite and "Tour 9" in seite and not Tour.objects.exists()
    buero.post(reverse("touren:touren_importieren"), {"schritt": "uebernehmen"})
    assert Tour.objects.get(name="Tour 9").halte.count() == 1
    assert (
        reverse("touren:touren_importieren")
        in buero.get(reverse("datenimport:start")).content.decode()
    )


def test_tour_loeschen_in_den_papierkorb(buero):
    from apps.core.models import PapierkorbEintrag

    t = tour_mit(2)
    buero.post(reverse("touren:tour_loeschen", args=[t.pk]))
    assert not Tour.objects.exists() and Station.objects.count() == 2
    assert PapierkorbEintrag.objects.filter(art="Tour").exists()


# --- Tourstart: „Seid ihr Peter und Paul?“ (ADR 0150) -------------------------------------------


@pytest.fixture
def heute_tour(admin, django_user_model):
    """Eine Tour aus dem Fahrerplan, die heute fährt, mit Fritz (Fahrer) und Paula (Beifahrerin);
    Klaus und Berta könnten einspringen."""
    from apps.touren import start

    heute = timezone.localdate()
    ft = FahrdienstTour.objects.create(name="Nordtour", plaetze=2,
                                       fahrtage="Mo, Di, Mi, Do, Fr, Sa, So")  # fmt: skip
    fritz, paula = person(django_user_model, "Fritz"), person(django_user_model, "Paula",
                                                              "Beifahrer")  # fmt: skip
    klaus, berta = person(django_user_model, "Klaus"), person(django_user_model, "Berta",
                                                              "Beifahrer")  # fmt: skip
    tag = ablauf.kuerzel(heute)
    Besetzung.objects.create(tour=ft, wochentag=tag, platz=1, person=fritz)
    Besetzung.objects.create(tour=ft, wochentag=tag, platz=2, person=paula)
    t = Tour.objects.create(name="Nordtour", fahrdienst_tour=ft)
    ablauf.halt_anhaengen(t, station("n1"))
    return {"tour": t, "ft": ft, "heute": heute, "fritz": fritz, "paula": paula, "klaus": klaus,
            "berta": berta, "start": start}  # fmt: skip


def test_tourstart_fragt_und_bestaetigt(client, anmelden, heute_tour):
    t, start = heute_tour["tour"], heute_tour["start"]
    anmelden(client, heute_tour["fritz"].konto)
    antwort = client.get(reverse("touren:fahren", args=[t.pk]))
    assert antwort.status_code == 302 and antwort.url == reverse("touren:start", args=[t.pk])
    seite = client.get(antwort.url).content.decode()
    assert "Seid ihr Fritz Probe und Paula Probe?" in seite and "Nein, ändern" in seite
    assert "Klaus Probe" in seite and "Berta Probe" in seite  # könnten einspringen
    assert client.post(antwort.url).status_code == 302
    eintrag = start.gestartet(t, heute_tour["heute"])
    assert eintrag and not eintrag.geaendert and eintrag.bestaetigt_von
    seite = client.get(reverse("touren:fahren", args=[t.pk])).content.decode()
    assert "Besetzung bestätigt" in seite and "Navigation starten" in seite
    # an einem anderen Tag wird nicht gefragt
    morgen = (heute_tour["heute"] + dt.timedelta(days=1)).isoformat()
    assert client.get(reverse("touren:fahren", args=[t.pk]), {"tag": morgen}).status_code == 200


def test_tourstart_aendern_steht_im_fahrerplan(client, anmelden, heute_tour):
    from apps.fahrdienst import plan
    from apps.fahrdienst.models import Ersatz

    t, heute = heute_tour["tour"], heute_tour["heute"]
    anmelden(client, heute_tour["fritz"].konto)
    adresse = reverse("touren:start", args=[t.pk])
    client.post(adresse, {"aendern": "1", "platz_1": "", "platz_2": heute_tour["berta"].pk})
    ersatz = Ersatz.objects.get(datum=heute, tour=heute_tour["ft"], platz=2)
    assert ersatz.person == heute_tour["berta"] and ersatz.eingetragen_von == "fritz"
    assert plan.platz(heute, heute_tour["ft"], 2).wer == heute_tour["berta"]
    assert [b["name"] for b in ablauf.besetzung(t, heute)] == ["Fritz Probe", "Berta Probe"]
    assert heute_tour["start"].gestartet(t, heute).geaendert
    assert heute_tour["start"].frage(heute_tour["start"].plaetze(t, heute)) == (
        "Seid ihr Fritz Probe und Berta Probe?")  # fmt: skip


def test_tourstart_fremde_tragen_sich_nicht_ein(client, anmelden, heute_tour, recht_geben):
    from apps.fahrdienst.models import Ersatz

    t, heute, start = heute_tour["tour"], heute_tour["heute"], heute_tour["start"]
    klaus = heute_tour["klaus"]
    anmelden(client, klaus.konto)
    # nicht eingetragen: sieht die Tour, wird aber nicht gefragt und kann nichts bestätigen
    seite = client.get(reverse("touren:fahren", args=[t.pk]))
    assert seite.status_code == 200 and "noch nicht bestätigt" in seite.content.decode()
    adresse = reverse("touren:start", args=[t.pk])
    assert client.get(adresse).status_code == 302
    client.post(adresse, {"aendern": "1", "platz_1": klaus.pk})
    assert not Ersatz.objects.exists() and start.gestartet(t, heute) is None
    with pytest.raises(start.StartFehler):
        start.bestaetigen(t, heute, klaus.konto, {1: klaus.pk})
    # wer eingetragen ist, nimmt sich nicht selbst heraus und wählt nur, wer einspringen kann
    fritz = heute_tour["fritz"].konto
    with pytest.raises(start.StartFehler, match="selbst"):
        start.bestaetigen(t, heute, fritz, {1: klaus.pk})
    with pytest.raises(start.StartFehler, match="kann an dem Tag nicht"):
        start.bestaetigen(t, heute, fritz, {1: heute_tour["berta"].pk})  # Beifahrerin, kein Fahrer
    with pytest.raises(start.StartFehler):
        start.bestaetigen(t, heute, fritz, {2: klaus.pk, 1: klaus.pk})
    assert not Ersatz.objects.exists()
    # mit dem Recht „touren.besetzung“ geht es auch ohne eigenen Platz
    recht_geben("Fahrer", "touren.besetzung")
    assert client.get(reverse("touren:fahren", args=[t.pk])).status_code == 302
    client.post(adresse, {"aendern": "1", "platz_1": klaus.pk})
    assert Ersatz.objects.get(platz=1).person == klaus and start.gestartet(t, heute).geaendert


def test_tourstart_nur_fuer_touren_aus_dem_fahrerplan(client, anmelden, heute_tour):
    start, heute = heute_tour["start"], heute_tour["heute"]
    eigene = tour_mit(1, name="Eigene")
    eigene.personen.add(heute_tour["fritz"])
    assert not start.gefragt(eigene, heute) and start.gefragt(heute_tour["tour"], heute)
    anmelden(client, heute_tour["fritz"].konto)
    assert client.get(reverse("touren:fahren", args=[eigene.pk])).status_code == 200
    assert client.get(reverse("touren:start", args=[eigene.pk])).status_code == 302
    assert start.frage([]).startswith("Für diese Tour ist niemand")
    einer = [{"person": heute_tour["fritz"], "gast": ""}, {"person": None, "gast": ""}]
    assert start.frage(einer) == "Bist du Fritz Probe?"


def test_tourstart_frist():
    from apps.touren import start
    from apps.touren.models import Tourstart

    t = Tour.objects.create(name="Alt")
    Tourstart.objects.create(tour=t, datum=dt.date(2026, 1, 1), bestaetigt_von="x")
    Tourstart.objects.create(tour=t, datum=dt.date(2026, 6, 1), bestaetigt_von="x")
    assert start.fristen_anwenden(dt.date(2026, 6, 15)) == 1 and Tourstart.objects.count() == 1


def test_import_verbindet_wochentag_im_namen_mit_dem_fahrerplan():
    """„Montag Nordtour“ ist die Tour „Nordtour“ des Fahrerplans in der Montags-Reihenfolge."""
    station(1)
    ft = FahrdienstTour.objects.create(name="Nordtour")
    schon = Tour.objects.create(name="Dienstag Nordtour")  # früher ohne Verbindung eingelesen
    zeilen = ["Montag Nordtour;1;M-1;Mo", "Dienstag Nordtour;1;M-1;Di", "Nordtour;1;M-1;",
              "Freitag Sonderfahrt;1;M-1;", "Montag;1;M-1;"]  # fmt: skip
    text = "\n".join([KOPF, *zeilen])
    importieren_touren.uebernehmen(importieren_touren.pruefen(text), "anton")
    montag = Tour.objects.get(name="Montag Nordtour")
    assert (montag.fahrdienst_tour, montag.fahrtage) == (ft, "Mo")
    assert ablauf.faehrt_am(montag, MONTAG) and not ablauf.faehrt_am(montag, DIENSTAG)
    schon.refresh_from_db()
    assert (schon.fahrdienst_tour, schon.fahrtage) == (ft, "Di")
    gleich = Tour.objects.get(name="Nordtour")
    assert (gleich.fahrdienst_tour, gleich.fahrtage) == (ft, "")
    assert Tour.objects.get(name="Freitag Sonderfahrt").fahrdienst_tour is None
    assert Tour.objects.get(name="Montag").fahrdienst_tour is None
    assert importieren_touren.wochentag_im_namen("Mo. Nordtour") == ("Mo", "Nordtour")


def test_alle_angaben_fuehrt_zurueck_zur_tour(fahrer):
    """Aus der Tour geöffnet, führt „zurück“ auf der Seite der Station wieder in die Tour."""
    heute = timezone.localdate()
    t = tour_mit(2, name="Sonderfahrt", datum=heute)
    t.personen.add(fahrer.person)
    erste = t.halte.first().station
    seite = fahrer.get(reverse("touren:fahren", args=[t.pk])).content.decode()
    ziel = f"{reverse('touren:station', args=[erste.pk])}?tour={t.pk}&amp;tag={heute:%Y-%m-%d}"
    assert f'class="tour-alle-angaben" href="{ziel}&amp;halt=1"' in seite
    werte = {"tour": t.pk, "tag": f"{heute:%Y-%m-%d}", "halt": "1"}
    station = fahrer.get(reverse("touren:station", args=[erste.pk]), werte).content.decode()
    zurueck = f"{reverse('touren:fahren', args=[t.pk])}?tag={heute:%Y-%m-%d}#halt-1"
    assert f'href="{zurueck}"' in station and "zurück zur Tour „Sonderfahrt“" in station
    assert "← Stationen" not in station
    # ohne Tour, mit unbekannter Tour oder kaputtem Tag: wie bisher bzw. ohne Tag
    einfach = fahrer.get(reverse("touren:station", args=[erste.pk])).content.decode()
    assert "← Stationen" in einfach
    fremd = fahrer.get(reverse("touren:station", args=[erste.pk]), {"tour": "999999"})
    assert "← Stationen" in fremd.content.decode()
    kaputt = {"tour": t.pk, "tag": "morgen", "halt": "x"}
    ohne_tag = fahrer.get(reverse("touren:station", args=[erste.pk]), kaputt).content.decode()
    assert f'href="{reverse("touren:fahren", args=[t.pk])}"' in ohne_tag


# --- „Hier waren wir“ (ADR 0152) ----------------------------------------------------------------


def test_angefahren_markieren_und_zuruecknehmen(fahrer, django_user_model):
    from apps.touren import anfahrten
    from apps.touren.models import Anfahrt

    heute = timezone.localdate()
    t = tour_mit(3, name="Sonderfahrt", datum=heute)
    t.personen.add(fahrer.person)
    erste, zweite, _ = [h.station for h in t.halte.all()]
    adresse = reverse("touren:fahren", args=[t.pk])
    seite = fahrer.get(adresse).content.decode()
    assert seite.count("✓ Hier waren wir</button>") == 3 and "data-tour-aktuell" not in seite
    antwort = fahrer.post(reverse("touren:angefahren", args=[t.pk, erste.pk]))
    assert antwort.status_code == 302 and antwort.url == adresse
    seite = fahrer.get(adresse).content.decode()
    # die Station bleibt stehen, ist aber gekennzeichnet; die nächste offene ist die aktuelle
    assert erste.name in seite and "1 angefahren" in seite and "zurücknehmen" in seite
    assert 'class="karte tour-halt tour-erledigt" id="halt-1"' in seite
    assert 'id="halt-2" data-tour-aktuell' in seite
    assert seite.count("✓ Hier waren wir</button>") == 2
    fahrer.post(reverse("touren:angefahren", args=[t.pk, erste.pk]))  # doppelt schadet nicht
    assert Anfahrt.objects.count() == 1
    fahrer.post(reverse("touren:angefahren", args=[t.pk, erste.pk]), {"zurueck": "1"})
    assert not Anfahrt.objects.exists()
    # wer nicht eingetragen ist, kennzeichnet nichts; eine fremde Station auch nicht
    klaus = person(django_user_model, "Klaus").konto
    with pytest.raises(anfahrten.AnfahrtFehler, match="nicht eingetragen"):
        anfahrten.markieren(t, erste, klaus)
    fremd = station("fremd")
    with pytest.raises(anfahrten.AnfahrtFehler, match="nicht auf der Tour"):
        anfahrten.markieren(t, fremd, fahrer.person.konto)
    fahrer.post(reverse("touren:angefahren", args=[t.pk, fremd.pk]))
    assert not Anfahrt.objects.exists()
    # Frist: nach 90 Tagen weg
    alt = Anfahrt.objects.create(tour=t, station=zweite, datum=heute - dt.timedelta(days=91))
    assert str(alt).startswith(zweite.name)
    assert anfahrten.fristen_anwenden() == 1


def test_lieferschein_gilt_als_angefahren(fahrer):
    from decimal import Decimal

    from apps.touren import lieferscheine
    from tests.test_touren_lieferscheine import unterschrift

    heute = timezone.localdate()
    t = tour_mit(2, name="Sonderfahrt", datum=heute)
    t.personen.add(fahrer.person)
    erste = t.halte.first().station
    zeichnung = lieferscheine.unterschrift_lesen(unterschrift())
    lieferscheine.erstellen(erste, fahrer.person.konto, [("Backwaren", Decimal("1"), "kg")],
                            zeichnung, "", t, heute)  # fmt: skip
    seite = fahrer.get(reverse("touren:fahren", args=[t.pk])).content.decode()
    assert "1 angefahren" in seite and 'id="halt-2" data-tour-aktuell' in seite
    assert seite.count("✓ Hier waren wir</button>") == 1  # an der ersten steht der Lieferschein
