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
from apps.touren.models import Halt, Station, Tour, Umstand

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
        "name": "Sonderfahrt", "datum": "2026-11-24", "fahrer": anna.pk, "beifahrer": fest.pk,
        "gast": "Gerda Gast", "hinweis": "", "aktiv": "on"})  # fmt: skip
    t = Tour.objects.get(name="Sonderfahrt")
    assert antwort.url == reverse("touren:tour", args=[t.pk])
    assert t.datum == DIENSTAG and t.angelegt_von == "bernd" and t.personen.count() == 2
    wer = ablauf.besetzung(t, DIENSTAG)  # Fahrer, Beifahrer und der Gast ohne Konto
    assert [(b["rolle"], b["name"]) for b in wer] == [
        ("Fahrer", "Anna Probe"), ("Beifahrer", "Vera Probe"), ("Gast", "Gerda Gast")]  # fmt: skip
    assert "Gerda Gast" in buero.get(reverse("touren:touren")).content.decode()
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
    # danach lässt sich die Besetzung über einen deutlichen Knopf weiter ändern
    aendern = reverse("touren:start", args=[t.pk]) + "?aendern=1"
    assert aendern in seite and "Besetzung ändern, Mitfahrer oder Gast" in seite
    maske = client.get(aendern).content.decode()
    assert '<details class="tour-aendern" open>' in maske and "Besetzung ändern" in maske
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
    assert seite.count("✓ Ohne Lieferschein abhaken</summary>") == 3
    assert "data-tour-aktuell" not in seite and "Markt geschlossen</option>" in seite
    ziel = reverse("touren:angefahren", args=[t.pk, erste.pk])
    # ohne Auswahl geht es nicht; „Sonstiges“ braucht eine Anmerkung
    assert "Bitte wählen" in fahrer.post(ziel, follow=True).content.decode()
    sonstiges = Umstand.objects.get(name="Sonstiges")
    seite = fahrer.post(ziel, {"umstand": sonstiges.pk}, follow=True).content.decode()
    assert "kurz dazuschreiben" in seite and not Anfahrt.objects.exists()
    zu = Umstand.objects.get(name="Markt geschlossen")
    antwort = fahrer.post(ziel, {"umstand": zu.pk, "anmerkung": " Inventur,  bis  Montag "})
    assert antwort.status_code == 302 and antwort.url == adresse
    eintrag = Anfahrt.objects.get()
    assert (eintrag.umstand, eintrag.anmerkung) == ("Markt geschlossen", "Inventur, bis Montag")
    seite = fahrer.get(adresse).content.decode()
    assert "<strong>Markt geschlossen</strong>" in seite and "„Inventur, bis Montag“" in seite
    # die Station bleibt stehen, ist aber gekennzeichnet; die nächste offene ist die aktuelle
    assert erste.name in seite and "1 angefahren" in seite and "zurücknehmen" in seite
    assert 'class="karte tour-halt tour-erledigt" id="halt-1"' in seite
    assert 'id="halt-2" data-tour-aktuell' in seite
    assert seite.count("✓ Ohne Lieferschein abhaken</summary>") == 2
    fahrer.post(ziel, {"umstand": zu.pk})  # doppelt schadet nicht
    assert Anfahrt.objects.count() == 1
    fahrer.post(reverse("touren:angefahren", args=[t.pk, erste.pk]), {"zurueck": "1"})
    assert not Anfahrt.objects.exists()
    # wer nicht eingetragen ist, kennzeichnet nichts; eine fremde Station auch nicht
    klaus = person(django_user_model, "Klaus").konto
    with pytest.raises(anfahrten.AnfahrtFehler, match="nicht eingetragen"):
        anfahrten.markieren(t, erste, klaus, zu.pk)
    fremd = station("fremd")
    with pytest.raises(anfahrten.AnfahrtFehler, match="nicht auf der Tour"):
        anfahrten.markieren(t, fremd, fahrer.person.konto, zu.pk)
    fahrer.post(reverse("touren:angefahren", args=[t.pk, fremd.pk]), {"umstand": zu.pk})
    assert not Anfahrt.objects.exists()
    # Frist: nach 90 Tagen weg, wenn kein Umstand dabeisteht
    alt = Anfahrt.objects.create(tour=t, station=zweite, datum=heute - dt.timedelta(days=91))
    assert str(alt).startswith(zweite.name)
    # mit Umstand bleibt der Eintrag für die Statistik, aber ohne den Namen
    Anfahrt.objects.create(tour=t, station=erste, datum=heute - dt.timedelta(days=91),
                           von="Fritz Probe", umstand="Keine Ware")  # fmt: skip
    uralt = Anfahrt.objects.create(tour=t, station=erste, umstand="Keine Ware",
                                   datum=heute - dt.timedelta(days=365 * 11))  # fmt: skip
    assert anfahrten.fristen_anwenden() == 2
    bleibt = Anfahrt.objects.get()
    assert (bleibt.umstand, bleibt.von) == ("Keine Ware", "") and bleibt.pk != uralt.pk


def test_abhaken_ohne_liste_und_statistik(fahrer):
    """Sind alle Umstände ausgeschaltet, wird wie früher ohne Auswahl abgehakt. Die Statistik
    zählt je Station, nie je Person."""
    from apps.touren import anfahrten, statistik
    from apps.touren.models import Anfahrt

    heute = timezone.localdate()
    t = tour_mit(2, name="Sonderfahrt", datum=heute)
    t.personen.add(fahrer.person)
    erste, zweite = [h.station for h in t.halte.all()]
    keine = Umstand.objects.get(name="Keine Ware")
    anfahrten.markieren(t, erste, fahrer.person.konto, keine.pk)
    Anfahrt.objects.create(tour=t, station=erste, umstand="Keine Ware",
                           datum=heute - dt.timedelta(days=1))  # fmt: skip
    Anfahrt.objects.filter(datum__year__lt=heute.year).update(datum=heute)  # Jahreswechsel
    teil = statistik.abschnitt_umstaende(statistik.Daten(heute.year))
    assert teil["kopf"] == ["Station", "Keine Ware", "Gesamt"]
    assert teil["zeilen"] == [[erste.name, 2, 2]]
    Umstand.objects.update(aktiv=False)
    seite = fahrer.get(reverse("touren:fahren", args=[t.pk])).content.decode()
    assert seite.count("✓ Hier waren wir</button>") == 1
    fahrer.post(reverse("touren:angefahren", args=[t.pk, zweite.pk]))
    assert Anfahrt.objects.get(station=zweite).umstand == ""


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
    # an der ersten steht der Lieferschein
    assert seite.count("✓ Ohne Lieferschein abhaken</summary>") == 1


# --- Stationen suchen und kurzfristige Tour in einer Maske ---------------------------------------


def test_stationssuche_ueber_alle_angaben():
    from apps.touren import suche

    a = station(1, name="Supermarkt Nord", kette="Beispielkette", telefon="01234 567890",
                ansprechpartner="Frau Muster")  # fmt: skip
    b = station(2, name="Bäckerei Probe", strasse="Hauptstraße", notiz="Hintereingang")
    station(3, name="Geschlossen", aktiv=False, strasse="Hauptstraße")
    assert suche.stationen("su") == []  # erst ab drei Zeichen
    assert suche.stationen("super") == [a] and suche.stationen("beispielk") == [a]
    assert suche.stationen("567890") == [a] and suche.stationen("01234 567") == [a]
    assert suche.stationen("muster nord") == [a]  # jedes Wort muss vorkommen
    assert suche.stationen("haupt") == [b] and suche.stationen("hintereingang") == [b]
    assert suche.stationen("12345") == [b, a]  # PLZ, nur aktive, nach Name
    t = Tour.objects.create(name="Tour 1")
    ablauf.halt_anhaengen(t, a)
    assert suche.stationen("musterstadt", ohne_tour=t) == [b]
    assert len(suche.stationen("musterstadt", grenze=1)) == 1


def test_suche_beim_anhaengen(buero):
    a = station(1, name="Supermarkt Nord")
    t = Tour.objects.create(name="Tour 1")
    seite = buero.get(reverse("touren:tour", args=[t.pk])).content.decode()
    assert "Station suchen und anhängen" in seite
    assert f"{reverse('touren:stationen_suche')}?tour={t.pk}" in seite
    adresse = reverse("touren:stationen_suche")
    assert "mindestens 3 Zeichen" in buero.get(adresse, {"q": "su", "tour": t.pk}).content.decode()
    treffer = buero.get(adresse, {"q": "super", "tour": t.pk}).content.decode()
    assert "Supermarkt Nord" in treffer and reverse("touren:halt_neu", args=[t.pk]) in treffer
    assert "Keine Station gefunden" in buero.get(adresse, {"q": "xyzxyz"}).content.decode()
    buero.post(reverse("touren:halt_neu", args=[t.pk]), {"station": a.pk})
    leer = buero.get(adresse, {"q": "super", "tour": t.pk}).content.decode()
    assert "noch nicht auf der Tour" in leer  # steht schon darauf
    wahl = buero.get(adresse, {"q": "super"}).content.decode()  # ohne Tour: zur Auswahl
    assert f'data-station-waehlen="{a.pk}"' in wahl


def test_suche_nur_mit_recht_planen(fahrer):
    assert fahrer.get(reverse("touren:stationen_suche"), {"q": "super"}).status_code == 403


def test_kurzfristige_tour_in_einer_maske(buero, django_user_model, mail_an):
    a, b = station(1, name="Supermarkt Nord"), station(2, name="Bäckerei Probe")
    fritz = person(django_user_model, "Fritz")
    adresse = reverse("touren:tour_neu") + "?kurz"
    seite = buero.get(adresse).content.decode()
    assert "Laden oder Lieferadresse suchen" in seite and "noch nicht in der Liste" in seite
    daten = {"name": "Sonderabholung", "datum": "24.11.2026", "fahrer": fritz.pk,
             "hinweis": "", "aktiv": "on", "stationen": [b.pk, a.pk, b.pk], "senden": "1",
             "neu-name": "Hofladen Beispiel", "neu-art": "sonstiges", "neu-strasse": "Feldweg",
             "neu-hausnummer": "3", "neu-plz": "12345", "neu-ort": "Musterstadt"}  # fmt: skip
    antwort = buero.post(adresse, daten)
    t = Tour.objects.get(name="Sonderabholung")
    assert antwort.status_code == 302 and antwort.url == reverse("touren:tour", args=[t.pk])
    neu = Station.objects.get(name="Hofladen Beispiel")
    assert neu.kennung.startswith("S-") and neu.geaendert_von == "bernd"
    # Reihenfolge wie gewählt, jede Station nur einmal, die neue am Ende
    assert [h.station for h in t.halte.all()] == [b, a, neu]
    assert t.datum == dt.date(2026, 11, 24) and list(t.personen.all()) == [fritz]
    assert len(mail.outbox) == 1 and "Bäckerei Probe" in mail.outbox[0].body  # gleich geschickt


def test_kurzfristige_tour_fehler_behaelt_die_auswahl(buero):
    a = station(1, name="Supermarkt Nord")
    adresse = reverse("touren:tour_neu") + "?kurz"
    # neue Adresse nur halb eingetragen: nichts wird angelegt, die Auswahl bleibt stehen
    daten = {"name": "Sonderabholung", "datum": "24.11.2026", "aktiv": "on",
             "stationen": [a.pk], "neu-name": "Hofladen", "neu-art": "sonstiges"}  # fmt: skip
    antwort = buero.post(adresse, daten)
    seite = antwort.content.decode()
    assert antwort.status_code == 200 and not Tour.objects.exists()
    assert f'name="stationen" value="{a.pk}"' in seite and "Supermarkt Nord" in seite
    assert not Station.objects.filter(name="Hofladen").exists()
    # ohne neue Adresse und ohne Senden
    del daten["neu-name"]
    buero.post(adresse, daten)
    t = Tour.objects.get()
    assert [h.station for h in t.halte.all()] == [a] and not mail.outbox
    # die regelmäßige Tour bleibt beim alten Ablauf
    assert "Laden oder Lieferadresse suchen" not in buero.get(
        reverse("touren:tour_neu")).content.decode()  # fmt: skip


# --- Drei Personen und Gast (ADR 0153), ECO-Plattform --------------------------------------------


def test_eigene_tour_drei_personen_und_gast(buero, django_user_model):
    a, b, c = (person(django_user_model, n) for n in ("Anna", "Bodo", "Cleo"))
    t = Tour.objects.create(name="Eigene")
    adresse = reverse("touren:tour", args=[t.pk])
    daten = {"name": "Eigene", "fahrtage": [], "fahrer": a.pk, "beifahrer": b.pk,
             "beifahrer2": c.pk, "gast": "", "hinweis": "", "aktiv": "on"}  # fmt: skip
    assert buero.post(adresse, daten).status_code == 302
    t.refresh_from_db()
    assert (t.fahrer, t.beifahrer, t.beifahrer2) == (a, b, c)
    assert set(t.personen.all()) == {a, b, c}  # alle fahren mit („Ihre Tour“, Mail)
    assert [x["rolle"] for x in ablauf.besetzung(t, MONTAG)] == ["Fahrer", "Beifahrer",
                                                                 "Beifahrer"]  # fmt: skip
    assert ablauf.faehrt_mit(t, MONTAG, c)
    # dieselbe Person auf zwei Plätzen geht nicht
    antwort = buero.post(adresse, {**daten, "beifahrer2": a.pk})
    assert "nur auf einem Platz" in antwort.content.decode()
    # Platz wieder frei: fährt nicht mehr mit
    buero.post(adresse, {**daten, "beifahrer2": ""})
    assert set(Tour.objects.get(pk=t.pk).personen.all()) == {a, b}
    # von Hand nur unter „personen“ eingetragene (ältere Touren) bleiben in der Besetzung
    t.personen.add(c)
    assert [x["name"] for x in ablauf.besetzung(t, MONTAG)][-1] == "Cleo Probe"


def test_tourstart_gast_auf_dem_dritten_platz(client, anmelden, heute_tour):
    from apps.fahrdienst.models import Ersatz

    t, heute, start = heute_tour["tour"], heute_tour["heute"], heute_tour["start"]
    ft = heute_tour["ft"]
    ft.plaetze = 3
    ft.save()
    anmelden(client, heute_tour["fritz"].konto)
    adresse = reverse("touren:start", args=[t.pk])
    seite = client.get(adresse).content.decode()
    assert 'name="gast_2"' in seite and 'name="gast_3"' in seite and 'name="gast_1"' not in seite
    client.post(adresse, {"aendern": "1", "platz_1": "", "platz_2": "", "platz_3": "",
                          "gast_3": "Gerda Gast"})  # fmt: skip
    ersatz = Ersatz.objects.get(datum=heute, tour=ft, platz=3)
    assert ersatz.gast == "Gerda Gast" and ersatz.person is None
    assert [b["name"] for b in ablauf.besetzung(t, heute)] == [
        "Fritz Probe", "Paula Probe", "Gerda Gast"]  # fmt: skip
    assert start.frage(start.plaetze(t, heute)) == (
        "Seid ihr Fritz Probe, Paula Probe und Gerda Gast?")  # fmt: skip
    assert start.gestartet(t, heute).geaendert
    # kein Gast auf dem Fahrerplatz; derselbe Gast noch einmal ändert nichts
    with pytest.raises(start.StartFehler, match="Fahrerplatz"):
        start.aendern(t, heute, heute_tour["fritz"].konto, gaeste={1: "Niemand"})
    assert not start.aendern(t, heute, heute_tour["fritz"].konto, gaeste={3: "Gerda Gast"})
    # ein Gast statt der eigenen Person: niemand nimmt sich selbst heraus
    with pytest.raises(start.StartFehler, match="selbst"):
        start.aendern(t, heute, heute_tour["paula"].konto, gaeste={2: "Jemand"})


def test_planung_zeigt_und_aendert_besetzung_des_tages(buero, heute_tour):
    from apps.fahrdienst.models import Ersatz

    t, heute, ft = heute_tour["tour"], heute_tour["heute"], heute_tour["ft"]
    adresse = reverse("touren:tour", args=[t.pk])
    seite = buero.get(adresse).content.decode()
    assert "Besetzung am" in seite and "Fritz Probe" in seite and "Paula Probe" in seite
    assert "Für diesen Tag ändern" in seite
    antwort = buero.post(reverse("touren:besetzung", args=[t.pk]), {
        "tag": f"{heute:%Y-%m-%d}", "platz_1": "", "platz_2": heute_tour["berta"].pk})  # fmt: skip
    assert antwort.url == f"{adresse}?tag={heute:%Y-%m-%d}"
    assert Ersatz.objects.get(datum=heute, tour=ft, platz=2).person == heute_tour["berta"]
    assert "Berta Probe" in buero.get(antwort.url).content.decode()
    # unverändert abgeschickt und kaputtes Datum: nichts passiert
    buero.post(reverse("touren:besetzung", args=[t.pk]), {"tag": "x"})
    assert Ersatz.objects.count() == 1
    # ein Tag, an dem die Tour nicht fährt
    ft.fahrtage = "Mo"
    ft.save()
    kein_montag = heute if heute.weekday() != 0 else heute + dt.timedelta(days=1)
    seite = buero.get(adresse, {"tag": f"{kein_montag:%Y-%m-%d}"}).content.decode()
    assert "An diesem Tag fährt die Tour nicht" in seite
    daten = {"tag": f"{kein_montag:%Y-%m-%d}", "gast_2": "Jemand"}
    antwort = buero.post(reverse("touren:besetzung", args=[t.pk]), daten, follow=True)
    assert "fährt an dem Tag nicht" in antwort.content.decode()
    # ohne Tag in der Adresse: der nächste Fahrtag (Montag)
    assert "Besetzung am Montag" in buero.get(adresse).content.decode()


def test_besetzung_aendern_nur_mit_recht(client, anmelden, heute_tour):
    anmelden(client, heute_tour["klaus"].konto)  # Fahrer ohne das Recht, Touren zu planen
    adresse = reverse("touren:besetzung", args=[heute_tour["tour"].pk])
    assert client.post(adresse, {}).status_code == 403


def test_eco_plattform_link(buero, admin_client):
    from apps.touren.models import TourenEinstellungen

    assert "ECO-Plattform" not in buero.get(reverse("touren:heute")).content.decode()
    assert buero.get(reverse("touren:eco")).status_code == 404  # ausgeschaltet
    admin_client.post(reverse("touren:einstellungen"), {
        "einstellungen": "1", "lieferscheine": "on", "versand": "aus", "mail_text": "Hallo",
        "aufbewahrung_jahre": "10", "eco_plattform": "on",
        "eco_adresse": "https://eco.tafel.de"})  # fmt: skip
    e = TourenEinstellungen.laden()
    assert e.eco_plattform and e.eco_link == "https://eco.tafel.de"
    # nur im Menü unter „Touren“, nicht mehr als Knopf auf den Seiten
    assert buero.get(reverse("touren:eco")).status_code == 302
    assert buero.get(reverse("touren:eco")).url == "https://eco.tafel.de"
    for name in ("touren:heute", "touren:touren"):
        seite = buero.get(reverse(name)).content.decode()
        assert seite.count("ECO-Plattform") == 1
        eintrag = f'<a href="{reverse("touren:eco")}" target="_blank" rel="noopener" data-extern>'
        assert eintrag + "ECO-Plattform ↗<" in seite  # ein Pfeil, nicht zwei
    # Touren, Stationen und Lieferscheine bleiben nutzbar
    assert buero.get(reverse("touren:stationen")).status_code == 200


# --- Routenvorschau in der Planung, Zentrale als Start und Ziel (ADR 0154) -----------------------


def _einstellen(**werte):
    from apps.touren.models import TourenEinstellungen

    e = TourenEinstellungen.laden()
    for name, wert in werte.items():
        setattr(e, name, wert)
    e.save()
    return e


def test_route_am_handy_endet_an_der_zentrale():
    stationen = [station(n) for n in range(1, 4)]
    ohne = ablauf.routen(stationen)
    assert len(ohne) == 1 and not ohne[0]["zentrale"] and "Zentralweg" not in ohne[0]["url"]
    mit = ablauf.routen(stationen, "Zentralweg 1, 12345 Musterstadt")
    assert len(mit) == 1 and mit[0]["zentrale"] and (mit[0]["von"], mit[0]["bis"]) == (1, 3)
    assert "destination=Zentralweg+1" in mit[0]["url"] and mit[0]["url"].count("Musterweg") == 3
    # zehn Stationen: die Zentrale passt nicht mehr in den Link und bekommt einen eigenen
    viele = ablauf.routen([station(n) for n in range(10, 20)], "Zentralweg 1")
    assert [(r["von"], r["bis"], r["zentrale"]) for r in viele] == [(1, 10, False),
                                                                   (11, 10, True)]  # fmt: skip
    assert ablauf.routen([], "Zentralweg 1") == []


def test_vorschau_von_der_zentrale_und_zurueck():
    stationen = [station(n) for n in range(1, 4)]
    leer = ablauf.vorschau([], "Zentralweg 1", "schluessel")
    assert leer == {"karten": [], "links": [], "zentrale": "Zentralweg 1"}
    ohne_schluessel = ablauf.vorschau(stationen, "Zentralweg 1")
    assert ohne_schluessel["karten"] == [] and len(ohne_schluessel["links"]) == 1
    link = ohne_schluessel["links"][0]
    assert "origin=Zentralweg+1" in link and "destination=Zentralweg+1" in link
    assert link.count("Musterweg") == 3 and link.startswith("https://www.google.com/maps/dir/")
    mit = ablauf.vorschau(stationen, "Zentralweg 1", "abc123")
    (karte,) = mit["karten"]
    assert karte.startswith("https://www.google.com/maps/embed/v1/directions?key=abc123")
    assert "origin=Zentralweg+1" in karte and "waypoints=" in karte and "mode=driving" in karte
    # ohne Zentrale: von der ersten zur letzten Station
    frei = ablauf.vorschau(stationen, "", "abc123")
    assert "origin=Musterweg+1" in frei["karten"][0] and "Zentralweg" not in frei["karten"][0]
    assert ablauf.vorschau(stationen[:1], "", "abc123") == {"karten": [], "links": [],
                                                            "zentrale": ""}  # fmt: skip
    # lange Tour: Karte in Abschnitten zu 20 Zwischenstopps, Links zu neun
    lang = ablauf.vorschau([station(n) for n in range(100, 125)], "Zentralweg 1", "abc123")
    assert len(lang["karten"]) == 2 and len(lang["links"]) == 3
    erster, zweiter = lang["karten"]
    assert erster.count("%7C") == 19 and "origin=Zentralweg+1" in erster
    assert "destination=Zentralweg+1" in zweiter and "origin=Musterweg+120" in zweiter


def test_zentrale_einstellung():
    t = TafelEinstellungen.laden()
    t.strasse, t.plz, t.ort = "Tafelweg 5", "12345", "Musterstadt"
    t.save()
    assert _einstellen().start_ziel == "Tafelweg 5, 12345 Musterstadt"  # Vorgabe: die Tafel
    assert _einstellen(zentrale=" Lagerstraße 2, 12345 Musterstadt ").start_ziel == (
        "Lagerstraße 2, 12345 Musterstadt")  # fmt: skip
    assert _einstellen(zentrale_aus=True).start_ziel == ""


def test_planung_zeigt_routenvorschau(buero, admin_client):
    from apps.touren.models import TourenEinstellungen

    _einstellen(zentrale="Zentralweg 1, 12345 Musterstadt")
    t = tour_mit(3, name="Nordtour")
    adresse = reverse("touren:tour", args=[t.pk])
    seite = buero.get(adresse).content.decode()
    assert "So wird gefahren" in seite and "Start und Ziel: Zentralweg 1" in seite
    assert "Route in Google Maps öffnen" in seite and "origin=Zentralweg" in seite
    assert "Karte zeigen" not in seite and "embed/v1" not in seite  # ohne Schlüssel keine Karte
    # der Admin trägt den Google-Schlüssel ein: verschlüsselt gespeichert, nie im Formular
    daten = {"einstellungen": "1", "lieferscheine": "on", "versand": "aus", "mail_text": "Hallo",
             "aufbewahrung_jahre": "10", "zentrale": "Zentralweg 1, 12345 Musterstadt",
             "eco_adresse": "https://eco.tafel.de", "karten_schluessel": " abc123 "}  # fmt: skip
    assert admin_client.post(reverse("touren:einstellungen"), daten).status_code == 302
    e = TourenEinstellungen.laden()
    assert e.karten_schluessel == "abc123" and "abc123" not in e.karten_schluessel_verschluesselt
    formular = admin_client.get(reverse("touren:einstellungen")).content.decode()
    assert "abc123" not in formular and "Ein Schlüssel ist gespeichert" in formular
    seite = buero.get(adresse).content.decode()
    assert "Karte zeigen" in seite and "embed/v1/directions?key=abc123" in seite
    assert "<iframe" not in seite  # erst nach dem Klick (static/js/tour_karte.js)
    # leer gespeichert: der Schlüssel bleibt; löschen entfernt ihn
    admin_client.post(reverse("touren:einstellungen"), {**daten, "karten_schluessel": ""})
    assert TourenEinstellungen.laden().karten_schluessel == "abc123"
    weg = {**daten, "karten_schluessel": "", "karten_schluessel_loeschen": "on"}
    admin_client.post(reverse("touren:einstellungen"), weg)
    assert TourenEinstellungen.laden().karten_schluessel == ""
    # die Fahrer bekommen keine Karte, aber die Zentrale als letztes Ziel der Route
    fahren = buero.get(reverse("touren:fahren", args=[t.pk])).content.decode()
    assert "So wird gefahren" not in fahren and "destination=Zentralweg" in fahren
    assert "Alle Stationen als Route und zurück zur Zentrale" in fahren


def test_karte_baustein_fuer_die_maske(buero):
    _einstellen(zentrale="Zentralweg 1", karten_schluessel_verschluesselt="")
    a, b = station(1), station(2)
    adresse = reverse("touren:karte")
    leer = buero.get(adresse).content.decode()
    assert "Sobald Stationen gewählt sind" in leer
    seite = buero.get(adresse, {"stationen": [b.pk, a.pk, b.pk, "x"]}).content.decode()
    assert "Route in Google Maps öffnen" in seite
    assert seite.index("Musterweg+2") < seite.index("Musterweg+1")  # Reihenfolge der Auswahl
    maske = buero.get(reverse("touren:tour_neu") + "?kurz").content.decode()
    assert "So wird gefahren" in maske and reverse("touren:karte") in maske
    assert "So wird gefahren" not in buero.get(reverse("touren:tour_neu")).content.decode()


def test_karte_nur_mit_recht_planen(client, anmelden, heute_tour):
    anmelden(client, heute_tour["klaus"].konto)
    assert client.get(reverse("touren:karte")).status_code == 403


def test_touren_planen_nach_fahrtag_geordnet(buero, django_user_model):
    """Die Übersicht ordnet die regelmäßigen Touren nach Fahrtag (Montag zuerst, nicht nach
    Alphabet) und zeigt, wer fest fährt – ohne „aus dem Fahrerplan: … (Di)“ in jeder Zeile."""
    nord = FahrdienstTour.objects.create(name="Nordtour", fahrtage="Mo, Di", plaetze=2)
    fritz, paula = person(django_user_model, "Fritz"), person(django_user_model, "Paula")
    Besetzung.objects.create(tour=nord, wochentag="Mo", platz=1, person=fritz)
    Besetzung.objects.create(tour=nord, wochentag="Mo", platz=2, person=paula)
    Tour.objects.create(name="Dienstag Nordtour", fahrdienst_tour=nord, fahrtage="Di")
    Tour.objects.create(name="Montag Nordtour", fahrdienst_tour=nord, fahrtage="Mo")
    Tour.objects.create(name="Lager", fahrdienst_tour=nord)  # an beiden Tagen des Fahrerplans
    Tour.objects.create(name="Sonderfahrt", fahrtage="Mo", fahrer=paula, gast="Gerda Gast")
    Tour.objects.create(name="Immer")  # eigene Tour, jeden Tag
    antwort = buero.get(reverse("touren:touren"))
    gruppen = antwort.context["gruppen"]
    assert [g["titel"] for g in gruppen] == ["Montag", "Dienstag", "An mehreren Tagen"]
    montag, dienstag, mehrere = (g["zeilen"] for g in gruppen)
    assert [z["tour"].name for z in montag] == ["Montag Nordtour", "Sonderfahrt"]
    assert montag[0]["wer"] == [("Fahrer", fritz.name), ("Beifahrer", paula.name)]
    assert not montag[0]["eigen"] and montag[0]["plan"] == ""  # Name enthält „Nordtour“ schon
    assert montag[1]["eigen"] and montag[1]["wer"] == [("Fahrer", paula.name),
                                                       ("Gast", "Gerda Gast")]  # fmt: skip
    assert dienstag[0]["wer"] == []  # am Dienstag ist im Fahrerplan niemand fest eingetragen
    assert [z["tour"].name for z in mehrere] == ["Immer", "Lager"]
    assert mehrere[1]["wer"] is None and mehrere[1]["plan"] == "Nordtour"
    seite = antwort.content.decode()
    assert "aus dem Fahrerplan:" not in seite and "niemand fest eingetragen" in seite
    assert "je Tag nach dem Fahrerplan" in seite and "Fahrerplan: Nordtour" in seite
    assert seite.index(">Montag<") < seite.index(">Dienstag<") < seite.index("An mehreren Tagen")
    assert seite.count("eigene Tour") == 2
    # Ohne Fahrdienst-Modul: alles eigene Touren, keine Abfrage des Fahrerplans
    e = TafelEinstellungen.laden()
    e.module = ["touren"]
    e.save()
    gruppen = buero.get(reverse("touren:touren")).context["gruppen"]
    assert all(z["eigen"] for g in gruppen for z in g["zeilen"])


def test_touren_planen_zeigt_uebliche_laenge(buero):
    """Länge einer Tour = Schnitt der letzten beendeten Fahrten laut Fahrtenbuch."""
    from apps.touren import fahrten
    from apps.touren.models import Fahrt

    t = Tour.objects.create(name="Nordtour", fahrtage="Mo")
    ohne = Tour.objects.create(name="Neu", fahrtage="Mo")
    jetzt = timezone.now()
    for tag, start, ende in ((1, 1000, 1040), (2, 1040, 1085), (3, 1085, None)):
        Fahrt.objects.create(tour=t, tour_name=t.name, datum=MONTAG + dt.timedelta(days=7 * tag),
                             km_start=start, km_ende=ende, begonnen_am=jetzt)  # fmt: skip
    assert fahrten.uebliche_laenge([t, ohne]) == {t.pk: (42, 2)}  # die laufende Fahrt zählt nicht
    antwort = buero.get(reverse("touren:touren"))
    zeilen = {z["tour"].name: z for g in antwort.context["gruppen"] for z in g["zeilen"]}
    assert zeilen["Nordtour"]["laenge"] == (42, 2) and zeilen["Neu"]["laenge"] is None
    seite = antwort.content.decode()
    assert "ca. 42 km" in seite and "Schnitt aus 2 Fahrten" in seite
    # nur die letzten zehn Fahrten zählen
    for tag in range(4, 16):
        Fahrt.objects.create(tour=t, tour_name=t.name, datum=MONTAG + dt.timedelta(days=7 * tag),
                             km_start=0, km_ende=100, begonnen_am=jetzt)  # fmt: skip
    assert fahrten.uebliche_laenge([t]) == {t.pk: (100, fahrten.LAENGE_AUS)}


def test_maske_blendet_eigene_plaetze_bei_tour_aus_dem_fahrerplan_aus():
    """Bei einer Tour aus dem Fahrerplan steht die Besetzung oben; die leeren Felder für Fahrer,
    Beifahrer und Gast sähen aus, als fehlten die Fahrer – sie erscheinen nur bei eigenen Touren."""
    from apps.touren.forms import TourForm

    mit = TourForm(fahrdienst=True)
    for name in ("fahrer", "beifahrer", "beifahrer2", "gast"):
        assert mit.fields[name].widget.attrs["data-zeigen-bei"] == "fahrdienst_tour="
    ohne = TourForm(fahrdienst=False)  # Fahrdienst-Modul aus: nur eigene Touren, Felder immer da
    assert "data-zeigen-bei" not in ohne.fields["fahrer"].widget.attrs
