"""Modul Touren: Fahrten mit Fahrzeug und Kilometerstand, Fahrtenbuch (ADR 0151).
Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from django.utils import timezone

from apps.adressen.models import Adresse
from apps.core.models import TafelEinstellungen
from apps.touren import ablauf, fahrten
from apps.touren.models import Fahrt, Fahrzeug, Station, Tour

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def module_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["touren", "fahrdienst"]
    t.save()


def person(django_user_model, name, rolle="Fahrer"):
    konto = django_user_model.objects.create_user(username=name.lower(), password="x")
    konto.groups.add(Group.objects.get(name=rolle))
    adresse = Adresse.objects.filter(konto=konto).first()
    return adresse or Adresse.objects.create(
        art=Adresse.Art.PERSON, vorname=name, nachname="Probe", konto=konto
    )


@pytest.fixture
def lage(django_user_model):
    """Eine eigene Tour, die jeden Tag fährt, mit Fritz; Klaus ist nicht eingetragen."""
    tour = Tour.objects.create(name="Südtour")
    station = Station.objects.create(kennung="S-1", art="markt", name="Markt Süd",
                                     strasse="Musterweg", hausnummer="1", plz="12345",
                                     ort="Musterstadt")  # fmt: skip
    ablauf.halt_anhaengen(tour, station)
    fritz, klaus = person(django_user_model, "Fritz"), person(django_user_model, "Klaus")
    tour.personen.add(fritz)
    wagen = Fahrzeug.objects.create(name="Kühlwagen", kennzeichen="MU-ST 1")
    return {"tour": tour, "fritz": fritz.konto, "klaus": klaus.konto, "wagen": wagen}


def test_beginnen_und_beenden(lage):
    tour, fritz, wagen = lage["tour"], lage["fritz"], lage["wagen"]
    fahrt = fahrten.beginnen(tour, fritz, "123.400", wagen.pk)
    assert (fahrt.km_start, fahrt.fahrzeug_name, fahrt.besetzung) == (
        123400, "Kühlwagen (MU-ST 1)", "Fritz Probe")  # fmt: skip
    assert fahrt.km is None and fahrt.dauer is None and fahrten.heute(tour, fahrt.datum) == fahrt
    with pytest.raises(fahrten.FahrtFehler, match="schon begonnen"):
        fahrten.beginnen(tour, fritz, "123400", wagen.pk)
    with pytest.raises(fahrten.FahrtFehler, match="kleiner"):
        fahrten.beenden(fahrt, fritz, "123399")
    with pytest.raises(fahrten.FahrtFehler, match="prüfen"):
        fahrten.beenden(fahrt, fritz, "133400")
    with pytest.raises(fahrten.FahrtFehler, match="ganze Zahl"):
        fahrten.beenden(fahrt, fritz, "viel")
    fahrten.beenden(fahrt, fritz, "123 487")
    assert fahrt.km == 87 and fahrt.beendet_von == fritz and fahrt.dauer is not None
    with pytest.raises(fahrten.FahrtFehler, match="schon beendet"):
        fahrten.beenden(fahrt, fritz, "123500")
    wagen.refresh_from_db()  # der Stand des Fahrzeugs wird mit jeder Fahrt fortgeschrieben
    assert fahrten.letzter_stand(wagen) == 123487 and fahrten.staende() == {wagen.pk: 123487}
    assert fahrten.letzter_stand(None) is None
    # in den Einstellungen geändert (anderweitig gefahren): gilt als neuer Vorschlag
    wagen.kilometerstand = 123900
    wagen.save()
    assert fahrten.staende() == {wagen.pk: 123900}
    assert fahrt.km_vorher is None and fahrt.km_unbekannt is None  # erster Stand: keine Lücke


def test_hoeherer_stand_als_bekannt_steht_als_unbekannt_im_fahrtenbuch(lage, admin_client):
    tour, fritz, wagen = lage["tour"], lage["fritz"], lage["wagen"]
    wagen.kilometerstand = 5000
    wagen.save()
    fahrt = fahrten.beginnen(tour, fritz, "5120", wagen.pk)  # 120 km ohne Eintrag gefahren
    assert (fahrt.km_vorher, fahrt.km_unbekannt) == (5000, 120)
    fahrten.beenden(fahrt, fritz, "5160")
    seite = admin_client.get(reverse("touren:fahrten")).content.decode()
    assert "fahrt-unbekannt" in seite and "120 km" in seite and "120 km unbekannt" in seite
    assert "zusammen <strong>40 km</strong>" in seite  # die Summe zählt nur eingetragene Fahrten
    csv_ = admin_client.get(reverse("touren:fahrten") + "?export=csv").content.decode("utf-8-sig")
    assert ";unbekannt;Kühlwagen (MU-ST 1);unbekannt;5000;5120;120;;" in csv_
    # das Büro berichtigt die Abfahrt auf den bekannten Stand: Die Lücke ist weg
    fahrten.berichtigen(fahrt, fritz, "5000", "5160", wagen.pk)
    assert fahrt.km_unbekannt is None
    assert "fahrt-unbekannt" not in admin_client.get(reverse("touren:fahrten")).content.decode()


def test_gleicher_oder_kleinerer_stand_ohne_luecke(lage):
    tour, fritz, wagen = lage["tour"], lage["fritz"], lage["wagen"]
    wagen.kilometerstand = 5000
    wagen.save()
    fahrt = fahrten.beginnen(tour, fritz, "5000", wagen.pk)
    assert fahrt.km_vorher is None and fahrt.km_unbekannt is None
    fahrt.delete()
    fahrt = fahrten.beginnen(tour, fritz, "4990", wagen.pk)  # Stand am Fahrzeug war zu hoch
    assert fahrt.km_vorher is None and fahrt.km_unbekannt is None


def test_nur_wer_eingetragen_ist_oder_das_recht_hat(lage, recht_geben):
    tour, klaus, wagen = lage["tour"], lage["klaus"], lage["wagen"]
    with pytest.raises(fahrten.FahrtFehler, match="nicht eingetragen"):
        fahrten.beginnen(tour, klaus, "100", wagen.pk)
    fahrt = fahrten.beginnen(tour, lage["fritz"], "100", wagen.pk)
    with pytest.raises(fahrten.FahrtFehler, match="nicht eingetragen"):
        fahrten.beenden(fahrt, klaus, "150")
    recht_geben("Fahrer", "touren.besetzung")
    klaus = type(klaus).objects.get(pk=klaus.pk)
    assert fahrten.beenden(fahrt, klaus, "150").km == 50


def test_fahrzeug_pflicht_wenn_es_welche_gibt_und_tour_muss_fahren(lage):
    tour, fritz, wagen = lage["tour"], lage["fritz"], lage["wagen"]
    with pytest.raises(fahrten.FahrtFehler, match="Fahrzeug"):
        fahrten.beginnen(tour, fritz, "100")
    wagen.aktiv = False
    wagen.save()
    assert fahrten.beginnen(tour, fritz, "100").fahrzeug is None  # ohne Fahrzeugliste nur km
    morgen = Tour.objects.create(name="Morgen", datum=timezone.localdate() + dt.timedelta(days=1))
    morgen.personen.add(Adresse.objects.get(konto=fritz))
    with pytest.raises(fahrten.FahrtFehler, match="fährt heute nicht"):
        fahrten.beginnen(morgen, fritz, "100")


def test_am_handy(client, anmelden, lage):
    tour, wagen = lage["tour"], lage["wagen"]
    anmelden(client, lage["fritz"])
    adresse = reverse("touren:fahren", args=[tour.pk])
    seite = client.get(adresse).content.decode()
    assert "Fahrt beginnen" in seite and "Kühlwagen" in seite and "Tour beenden" not in seite
    # schlanker Kopf: Name, Stand, Balken; die Angaben sind vor der Abfahrt aufgeklappt …
    assert '<span class="tour-zaehler" title="erledigte Stationen">0/1</span>' in seite
    assert '<progress class="tour-balken" value="0" max="1"' in seite
    assert '<details class="tour-angaben" open>' in seite
    client.post(reverse("touren:fahrt_beginnen", args=[tour.pk]),
                {"fahrzeug": wagen.pk, "km_start": "5000"})  # fmt: skip
    fahrt = Fahrt.objects.get()
    seite = client.get(adresse).content.decode()
    assert "Unterwegs" in seite and "Tour beenden" in seite and "Fahrt beginnen" not in seite
    assert '<details class="tour-angaben">' in seite  # … und unterwegs zugeklappt
    # solange eine Station offen ist: nur der Link „Tour vorzeitig beenden“, kein großer Abschnitt
    assert (
        '<details class="tour-vorzeitig" id="fahrt">' in seite and "Noch 1 Station offen" in seite
    )
    assert "<h2>Tour beenden</h2>" not in seite
    from apps.touren import anfahrten
    from apps.touren.models import Umstand

    station = tour.halte.get().station
    anfahrten.markieren(tour, station, lage["fritz"], Umstand.objects.get(name="Abgeholt").pk)
    seite = client.get(adresse).content.decode()
    assert "<h2>Tour beenden</h2>" in seite and "Alle Stationen sind erledigt." in seite
    assert "tour-vorzeitig" not in seite
    anfahrten.zuruecknehmen(tour, station, lage["fritz"])
    antwort = client.post(reverse("touren:fahrt_beenden", args=[fahrt.pk]), {"km_ende": "4000"},
                          follow=True)  # fmt: skip
    assert "kleiner" in antwort.content.decode() and Fahrt.objects.get().km_ende is None
    antwort = client.post(reverse("touren:fahrt_beenden", args=[fahrt.pk]), {"km_ende": "5042"},
                          follow=True)  # fmt: skip
    assert "42 km gefahren" in antwort.content.decode()
    seite = client.get(adresse).content.decode()
    assert "Fahrt beendet" in seite and "42 km" in seite
    # ein neues Fahrzeug bekommt beim nächsten Mal den letzten Stand vorgeschlagen
    Fahrt.objects.update(datum=timezone.localdate() - dt.timedelta(days=1))
    assert 'data-km="5042"' in client.get(adresse).content.decode()
    # nicht eingetragen: kein Formular, und die Adresse nimmt nichts an
    client.logout()
    anmelden(client, lage["klaus"])
    assert "Fahrt beginnen" not in client.get(adresse).content.decode()
    client.post(reverse("touren:fahrt_beginnen", args=[tour.pk]),
                {"fahrzeug": wagen.pk, "km_start": "5100"})  # fmt: skip
    assert Fahrt.objects.count() == 1
    assert client.get(reverse("touren:fahrten")).status_code == 403
    assert client.get(reverse("touren:fahrt", args=[fahrt.pk])).status_code == 403


def test_fahrtenbuch_und_berichtigen(client, anmelden, benutzer_mit_rolle, lage):
    tour, wagen = lage["tour"], lage["wagen"]
    fahrt = fahrten.beginnen(tour, lage["fritz"], "100", wagen.pk)
    fahrten.beenden(fahrt, lage["fritz"], "160")
    gestern = timezone.localdate() - dt.timedelta(days=1)
    offen = Fahrt.objects.create(tour=None, tour_name="Alte Tour", datum=gestern, km_start=40,
                                 begonnen_am=timezone.now() - dt.timedelta(days=1),
                                 begonnen_von_name="x")  # fmt: skip
    anmelden(client, benutzer_mit_rolle("bernd", "Büro"))
    seite = client.get(reverse("touren:fahrten")).content.decode()
    assert "Südtour" in seite and "60 km" in seite and "zusammen <strong>60 km" in seite
    assert "1 Fahrt aus früheren Tagen ohne Kilometerstand" in seite
    nur_offen = client.get(reverse("touren:fahrten"), {"stand": "offen"}).content.decode()
    assert "Alte Tour" in nur_offen and "Südtour" not in nur_offen
    je_wagen = client.get(reverse("touren:fahrten"), {"fahrzeug": wagen.pk}).content.decode()
    assert "Südtour" in je_wagen and "Alte Tour" not in je_wagen
    datei = client.get(reverse("touren:fahrten"), {"export": "csv"}).content.decode()
    assert "km gefahren" in datei and "Südtour;Kühlwagen (MU-ST 1);Fritz Probe;100;160;60" in datei
    adresse = reverse("touren:fahrt", args=[offen.pk])
    assert "Fahrt berichtigen" in client.get(adresse).content.decode()
    antwort = client.post(adresse, {"km_start": "40", "km_ende": "30", "fahrzeug": ""})
    assert "kleiner" in antwort.content.decode()
    client.post(adresse, {"km_start": "40", "km_ende": "95", "fahrzeug": wagen.pk})
    offen.refresh_from_db()
    assert (offen.km, offen.fahrzeug, offen.berichtigt_von) == (55, wagen, "bernd")
    assert offen.beendet_am is not None
    wagen.refresh_from_db()
    assert wagen.kilometerstand == 160  # eine ältere Fahrt berichtigt: der Stand bleibt
    client.post(reverse("touren:fahrt", args=[fahrt.pk]),
                {"km_start": "100", "km_ende": "170", "fahrzeug": wagen.pk})  # fmt: skip
    wagen.refresh_from_db()
    assert wagen.kilometerstand == 170  # die letzte Fahrt bestimmt den Stand


def test_fahrzeug_anlegen_und_aendern(admin_client):
    seite = admin_client.get(reverse("touren:einrichten")).content.decode()
    assert "Fahrzeuge" in seite and reverse("touren:fahrzeug_neu") in seite
    assert "Noch kein Fahrzeug angelegt" in seite
    assert "Neues Fahrzeug" in admin_client.get(reverse("touren:fahrzeug_neu")).content.decode()
    daten = {"name": "Transporter", "kennzeichen": "MU-ST 2", "kilometerstand": "45000",
             "reihenfolge": "1", "aktiv": "on"}  # fmt: skip
    antwort = admin_client.post(reverse("touren:fahrzeug_neu"), daten)
    wagen = Fahrzeug.objects.get()
    assert antwort.url == reverse("touren:fahrzeug", args=[wagen.pk]) + "#papiere"
    assert str(wagen) == "Transporter (MU-ST 2)" and wagen.kilometerstand == 45000
    # ändern auf der Seite des Fahrzeugs; ausgeschaltet bleibt es in der Übersicht stehen
    daten |= {"angaben": "1", "kilometerstand": "45100"}
    del daten["aktiv"]
    seite_url = reverse("touren:fahrzeug", args=[wagen.pk])
    assert admin_client.post(seite_url, daten).status_code == 302
    wagen.refresh_from_db()
    assert wagen.kilometerstand == 45100 and not wagen.aktiv
    seite = admin_client.get(reverse("touren:einrichten")).content.decode()
    assert "Transporter" in seite and "ausgeschaltet" in seite and "45100 km" in seite
    # ein zweites Fahrzeug bekommt die nächste Stelle vorgeschlagen; gleicher Name geht nicht
    assert (
        'name="reihenfolge" value="2"'
        in admin_client.get(reverse("touren:fahrzeug_neu")).content.decode()
    )
    antwort = admin_client.post(reverse("touren:fahrzeug_neu"), {"name": "Transporter",
                                                                "reihenfolge": "2"})  # fmt: skip
    assert antwort.status_code == 200 and Fahrzeug.objects.count() == 1


def test_frist_und_auskunft(lage, pdf_text):
    from apps.konten import auskunft

    fahrt = fahrten.beginnen(lage["tour"], lage["fritz"], "100", lage["wagen"].pk)
    fahrten.beenden(fahrt, lage["fritz"], "130")
    Fahrt.objects.create(tour=None, tour_name="Uralt", datum=dt.date(2010, 1, 1), km_start=1,
                         begonnen_am=timezone.now())  # fmt: skip
    assert fahrten.fristen_anwenden() == 1 and Fahrt.objects.count() == 1
    assert fahrten.fristen_anwenden(dt.date(2028, 2, 29)) == 0
    assert str(fahrt).startswith("Südtour am ")
    from django.http import HttpResponse

    antwort = HttpResponse(auskunft.mitarbeiter_pdf(lage["fritz"]), content_type="application/pdf")
    text = pdf_text(antwort)
    assert "Fahrt begonnen oder beendet" in text and "Südtour" in text and "Kühlwagen" in text


# --- Meldungen zum Fahrzeug (ADR 0155) ----------------------------------------------------------


def test_meldung_beim_beenden_und_zwischendurch(client, anmelden, lage):
    from apps.touren.models import Fahrzeugmeldung

    tour, wagen = lage["tour"], lage["wagen"]
    anmelden(client, lage["fritz"])
    client.post(reverse("touren:fahrt_beginnen", args=[tour.pk]),
                {"fahrzeug": wagen.pk, "km_start": "5000"})  # fmt: skip
    fahrt = Fahrt.objects.get()
    seite = client.get(reverse("touren:fahren", args=[tour.pk])).content.decode()
    assert "Etwas zum Fahrzeug melden" in seite and "Zwischendurch etwas zum Fahrzeug" in seite
    # zwischendurch: getankt
    antwort = client.post(reverse("touren:fahrt_melden", args=[fahrt.pk]),
                          {"meldung_art": "getankt", "meldung": "  vollgetankt,  52 Liter "},
                          follow=True)  # fmt: skip
    assert "bei der Fahrdienstleitung" in antwort.content.decode()
    getankt = Fahrzeugmeldung.objects.get()
    assert (getankt.art, getankt.text, getankt.fahrzeug) == ("getankt", "vollgetankt, 52 Liter",
                                                             wagen)  # fmt: skip
    assert getankt.fahrzeug_name == "Kühlwagen (MU-ST 1)" and getankt.tour_name == "Südtour"
    assert getankt.gemeldet_von == lage["fritz"] and getankt.offen
    # leer oder unbekannte Art
    client.post(reverse("touren:fahrt_melden", args=[fahrt.pk]), {"meldung": "  "})
    assert Fahrzeugmeldung.objects.count() == 1
    # beim Beenden gleich mitgemeldet
    client.post(reverse("touren:fahrt_beenden", args=[fahrt.pk]),
                {"km_ende": "5040", "meldung_art": "mangel",
                 "meldung": "Abblendlicht links defekt"})  # fmt: skip
    mangel = Fahrzeugmeldung.objects.get(art="mangel")
    assert mangel.text == "Abblendlicht links defekt" and Fahrt.objects.get().km == 40
    assert str(mangel).startswith("Beanstandung / Defekt: Abblendlicht")
    # nach dem Beenden geht es am selben Tag weiter; ohne Meldungstext entsteht nichts
    seite = client.get(reverse("touren:fahren", args=[tour.pk])).content.decode()
    assert "Zwischendurch etwas zum Fahrzeug" in seite
    assert Fahrzeugmeldung.objects.count() == 2


def test_meldung_nur_wer_faehrt_und_nur_am_tag(lage):
    from apps.touren import meldungen
    from apps.touren.models import Fahrzeugmeldung

    fahrt = fahrten.beginnen(lage["tour"], lage["fritz"], "100", lage["wagen"].pk)
    with pytest.raises(meldungen.MeldungFehler, match="nicht eingetragen"):
        meldungen.melden(fahrt, lage["klaus"], "mangel", "Reifen")
    with pytest.raises(meldungen.MeldungFehler, match="beschreiben"):
        meldungen.melden(fahrt, lage["fritz"], "mangel", "")
    m = meldungen.melden(fahrt, lage["fritz"], "unsinn", "Sitz klemmt")
    assert m.art == "sonstiges"
    Fahrt.objects.update(datum=timezone.localdate() - dt.timedelta(days=1))
    fahrt.refresh_from_db()
    with pytest.raises(meldungen.MeldungFehler, match="nichts mehr melden"):
        meldungen.melden(fahrt, lage["fritz"], "mangel", "Reifen")
    assert Fahrzeugmeldung.objects.count() == 1


def test_fahrdienstleitung_sieht_meldungen_auf_der_startseite(client, anmelden, lage,
                                                              benutzer_mit_rolle):  # fmt: skip
    from apps.touren import meldungen
    from apps.touren.models import Fahrzeugmeldung

    fahrt = fahrten.beginnen(lage["tour"], lage["fritz"], "100", lage["wagen"].pk)
    meldungen.melden(fahrt, lage["fritz"], "mangel", "Abblendlicht links defekt")
    meldungen.melden(fahrt, lage["fritz"], "getankt", "52 Liter")
    # der Fahrer selbst sieht auf der Startseite seine Tour, aber keine Meldungen
    anmelden(client, lage["fritz"])
    start = client.get(reverse("core:start")).content.decode()
    assert "Ihre Tour heute" in start and "Meldungen zum Fahrzeug" not in start
    assert client.get(reverse("touren:meldungen")).status_code == 403
    mangel = Fahrzeugmeldung.objects.get(art="mangel")
    assert client.post(reverse("touren:meldung_erledigen", args=[mangel.pk])).status_code == 403
    client.logout()
    anmelden(client, benutzer_mit_rolle("bernd", "Büro"))
    start = client.get(reverse("core:start")).content.decode()
    assert "Meldungen zum Fahrzeug" in start and "2 offen" in start
    assert "Abblendlicht links defekt" in start and "Kühlwagen" in start and "· fritz" in start
    # abhaken – mit Notiz; danach steht sie nicht mehr auf der Startseite
    daten = {"notiz": "Birne getauscht", "zurueck": reverse("core:start")}
    antwort = client.post(reverse("touren:meldung_erledigen", args=[mangel.pk]), daten)
    assert antwort.url == reverse("core:start")
    mangel.refresh_from_db()
    assert not mangel.offen and (mangel.erledigt_von, mangel.erledigt_notiz) == (
        "bernd", "Birne getauscht")  # fmt: skip
    start = client.get(reverse("core:start")).content.decode()
    assert "Abblendlicht" not in start and "1 offen" in start
    # die Liste: offen / alle, nach Fahrzeug; wieder öffnen
    offen = client.get(reverse("touren:meldungen")).content.decode()
    assert "52 Liter" in offen and "Abblendlicht" not in offen
    alle = client.get(reverse("touren:meldungen"),
                      {"stand": "alle", "fahrzeug": lage["wagen"].pk}).content.decode()  # fmt: skip
    assert "Abblendlicht" in alle and "Birne getauscht" in alle and "wieder öffnen" in alle
    wirr = client.get(reverse("touren:meldungen"), {"fahrzeug": "x", "stand": "x"})
    assert "Abblendlicht" in wirr.content.decode()  # unbekannte Filter: alle
    antwort = client.post(reverse("touren:meldung_erledigen", args=[mangel.pk]),
                          {"oeffnen": "1", "zurueck": "//fremd.example"})  # fmt: skip
    assert antwort.url == reverse("touren:meldungen")
    assert Fahrzeugmeldung.objects.get(pk=mangel.pk).offen


def test_meldungen_frist_und_auskunft(lage, pdf_text):
    from django.http import HttpResponse

    from apps.konten import auskunft
    from apps.touren import meldungen
    from apps.touren.models import Fahrzeugmeldung

    fahrt = fahrten.beginnen(lage["tour"], lage["fritz"], "100", lage["wagen"].pk)
    alt = meldungen.melden(fahrt, lage["fritz"], "mangel", "Uralte Beule")
    offen = meldungen.melden(fahrt, lage["fritz"], "mangel", "Spiegel wackelt")
    meldungen.erledigen(alt, lage["fritz"])
    Fahrzeugmeldung.objects.filter(pk=alt.pk).update(
        erledigt_am=timezone.now() - dt.timedelta(days=366 * 11)
    )
    assert meldungen.fristen_anwenden() == 1  # nur erledigte, alte; offene bleiben
    assert list(Fahrzeugmeldung.objects.all()) == [offen]
    assert meldungen.fristen_anwenden(dt.date(2028, 2, 29)) == 0
    antwort = HttpResponse(auskunft.mitarbeiter_pdf(lage["fritz"]), content_type="application/pdf")
    text = pdf_text(antwort)
    assert "Zum Fahrzeug gemeldet" in text and "Spiegel wackelt" in text


# --- Fahrzeugart, Erstzulassung und Papiere (ADR 0160) ------------------------------------------

PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


def test_fahrzeugart_und_erstzulassung(admin_client):
    Fahrzeug.objects.create(name="Kühlwagen", typ="Koffer")
    daten = {"name": "Stromer", "typ": "E-Vito", "erstzulassung": "15.03.2021",
             "reihenfolge": "1", "aktiv": "on"}  # fmt: skip
    assert admin_client.post(reverse("touren:fahrzeug_neu"), daten).status_code == 302
    wagen = Fahrzeug.objects.get(name="Stromer")
    assert wagen.typ == "E-Vito" and wagen.erstzulassung == dt.date(2021, 3, 15)
    # schon benutzte Fahrzeugarten werden vorgeschlagen, jede andere lässt sich eintragen
    maske = admin_client.get(reverse("touren:fahrzeug_neu")).content.decode()
    assert '<option value="E-Vito">' in maske and '<option value="Koffer">' in maske
    seite = admin_client.get(reverse("touren:einrichten")).content.decode()
    assert "E-Vito" in seite and "15.03.2021" in seite
    assert reverse("touren:fahrzeug", args=[wagen.pk]) + "#papiere" in seite
    assert ">hinterlegen</a>" in seite  # noch keine Papiere: der Link lädt dazu ein
    daten |= {"name": "Zweiter", "erstzulassung": "kein Datum"}
    assert admin_client.post(reverse("touren:fahrzeug_neu"), daten).status_code == 200


def test_papiere_hinterlegen_ansehen_entfernen(admin_client):
    from django.core.files.uploadedfile import SimpleUploadedFile

    from apps.core import privatdateien
    from apps.core.models import PapierkorbEintrag
    from apps.touren.models import FahrzeugDokument

    wagen = Fahrzeug.objects.create(name="Kühlwagen", kennzeichen="MU-ST 1", typ="Sprinter",
                                    erstzulassung=dt.date(2019, 6, 1))  # fmt: skip
    seite_url = reverse("touren:fahrzeug", args=[wagen.pk])
    seite = admin_client.get(seite_url).content.decode()
    assert "Sprinter" in seite and "01.06.2019" in seite and "Noch nichts hinterlegt" in seite
    assert 'href="#papiere"' in seite  # der Weg zu den Papieren steht gleich oben

    def hochladen(art, name="schein.pdf", typ="application/pdf", **mehr):
        datei = SimpleUploadedFile(name, PDF, content_type=typ)
        return admin_client.post(seite_url, {"art": art, "datei": datei, **mehr})

    assert hochladen("schein").status_code == 302
    assert hochladen("brief").status_code == 302
    assert hochladen("sonstiges", bezeichnung="Versicherung").status_code == 302
    titel = {p.titel for p in FahrzeugDokument.objects.all()}
    assert titel == {"Fahrzeugschein", "Fahrzeugbrief", "Versicherung"}
    schein = FahrzeugDokument.objects.get(art="schein")
    assert schein.hochgeladen_von_name and schein.datei.endswith(".bin")
    # verschlüsselt abgelegt, über die Seite lesbar
    assert PDF not in privatdateien.pfad(FahrzeugDokument.ORDNER, schein.datei).read_bytes()
    antwort = admin_client.get(reverse("touren:fahrzeug_papier", args=[schein.pk]))
    assert antwort.content == PDF and antwort["Content-Type"] == "application/pdf"
    assert antwort["Content-Disposition"] == 'inline; filename="Fahrzeugschein-Kühlwagen.pdf"'
    assert "3 hinterlegt" in admin_client.get(reverse("touren:einrichten")).content.decode()
    # falscher Dateityp wird abgelehnt
    antwort = hochladen("schein", "schein.exe", "application/x-msdownload")
    assert antwort.status_code == 200 and "Foto" in antwort.content.decode()
    assert FahrzeugDokument.objects.count() == 3
    # entfernen: in den Papierkorb
    admin_client.post(reverse("touren:fahrzeug_papier_weg", args=[schein.pk]))
    assert not FahrzeugDokument.objects.filter(pk=schein.pk).exists()
    assert PapierkorbEintrag.objects.filter(art="Papier zum Fahrzeug").exists()


def test_papiere_nur_fuer_die_fahrdienstleitung(client, anmelden, lage, recht_geben):
    from apps.touren.models import FahrzeugDokument

    papier = FahrzeugDokument.objects.create(
        fahrzeug=lage["wagen"], art="brief", datei="fehlt.bin", datei_typ="application/pdf"
    )
    adressen = [reverse("touren:fahrzeug", args=[lage["wagen"].pk]),
                reverse("touren:fahrzeug_papier", args=[papier.pk])]  # fmt: skip
    anmelden(client, lage["fritz"])  # fährt, plant aber nicht
    assert [client.get(a).status_code for a in adressen] == [403, 403]
    assert client.post(reverse("touren:fahrzeug_papier_weg", args=[papier.pk])).status_code == 403
    # mit dem Recht fürs Fahrtenbuch: ansehen ja, hochladen nein; fehlende Datei = nicht gefunden
    recht_geben("Fahrer", "touren.fahrten")
    assert [client.get(a).status_code for a in adressen] == [200, 404]
    assert "Papier hinterlegen" not in client.get(adressen[0]).content.decode()
    assert client.post(adressen[0], {"art": "schein"}).status_code == 403


def test_fahrt_loeschen_stellt_kilometerstand_zurueck(lage, admin_client):
    from apps.core.models import PapierkorbEintrag

    tour, fritz, wagen = lage["tour"], lage["fritz"], lage["wagen"]
    wagen.kilometerstand = 5000
    wagen.save()
    test = fahrten.beginnen(tour, fritz, "5010", wagen.pk)  # Testfahrt mit erfundenem Stand
    fahrten.beenden(test, fritz, "5055")
    seite = admin_client.get(reverse("touren:fahrt", args=[test.pk])).content.decode()
    assert "Fahrt löschen" in seite
    antwort = admin_client.post(reverse("touren:fahrt_loeschen", args=[test.pk]))
    assert antwort.status_code == 302 and not Fahrt.objects.exists()
    assert PapierkorbEintrag.objects.filter(art="Fahrt").exists()
    wagen.refresh_from_db()
    assert wagen.kilometerstand == 5000  # wie vor der Testfahrt


def test_fahrt_loeschen_laesst_spaeteren_stand(lage):
    tour, fritz, wagen = lage["tour"], lage["fritz"], lage["wagen"]
    erste = fahrten.beginnen(tour, fritz, "100", wagen.pk)
    fahrten.beenden(erste, fritz, "150")
    # das Fahrzeug wurde danach anderweitig gefahren, der Stand in „Einrichten“ nachgetragen
    wagen.kilometerstand = 400
    wagen.save()
    fahrten.loeschen(erste, fritz)
    wagen.refresh_from_db()
    assert wagen.kilometerstand == 400  # nicht angetastet
    # ohne bekannten Stand davor: zurück auf den Stand bei der Abfahrt
    zweite = fahrten.beginnen(tour, fritz, "400", wagen.pk)
    fahrten.beenden(zweite, fritz, "430")
    fahrten.loeschen(zweite, fritz)
    wagen.refresh_from_db()
    assert wagen.kilometerstand == 400


def test_fahrt_loeschen_nur_mit_recht(client, anmelden, lage):
    fahrt = fahrten.beginnen(lage["tour"], lage["fritz"], "100", lage["wagen"].pk)
    anmelden(client, lage["fritz"])
    assert client.post(reverse("touren:fahrt_loeschen", args=[fahrt.pk])).status_code == 403
    assert Fahrt.objects.filter(pk=fahrt.pk).exists()


def test_link_zur_besetzung_des_gewaehlten_tages(admin_client, lage):
    morgen = timezone.localdate() + dt.timedelta(days=1)
    seite = admin_client.get(
        reverse("touren:fahren", args=[lage["tour"].pk]) + f"?tag={morgen:%Y-%m-%d}"
    ).content.decode()
    ziel = f"{reverse('touren:tour', args=[lage['tour'].pk])}?tag={morgen:%Y-%m-%d}#besetzung"
    assert ziel in seite and "Besetzung für diesen Tag ändern" in seite


def test_fahrzeug_verkaufen_und_archiv(admin_client, lage):
    tour, fritz, wagen = lage["tour"], lage["fritz"], lage["wagen"]
    fahrt = fahrten.beginnen(tour, fritz, "100", wagen.pk)
    fahrten.beenden(fahrt, fritz, "150")
    seite_url = reverse("touren:fahrzeug", args=[wagen.pk])
    daten = {"angaben": "1", "name": wagen.name, "kennzeichen": wagen.kennzeichen,
             "kilometerstand": "150", "reihenfolge": "0", "aktiv": "on",
             "erstzulassung": "01.06.2019", "verkauft_am": "31.10.2026"}  # fmt: skip
    assert admin_client.post(seite_url, daten).status_code == 302
    wagen.refresh_from_db()
    # verkauft = archiviert: nicht mehr aktiv, auch wenn „Aktiv“ angehakt war
    assert wagen.verkauft_am == dt.date(2026, 10, 31) and not wagen.aktiv
    assert fahrten.fahrzeuge() == []  # steht den Fahrern nicht mehr zur Wahl
    seite = admin_client.get(reverse("touren:einrichten")).content.decode()
    assert "Noch kein Fahrzeug angelegt" in seite  # die Liste zeigt nur, was noch da ist
    assert "Archiv:</strong> 1 verkauftes Fahrzeug" in seite and "31.10.2026" in seite
    assert "Verkauft am 31.10.2026" in admin_client.get(seite_url).content.decode()
    # Fahrtenbuch und Fahrt bleiben, wie sie waren
    assert Fahrt.objects.get().fahrzeug == wagen
    assert "Kühlwagen" in admin_client.get(reverse("touren:fahrten")).content.decode()
    # ein Verkauf vor der Erstzulassung ist ein Tippfehler
    daten["verkauft_am"] = "31.10.2018"
    antwort = admin_client.post(seite_url, daten)
    assert antwort.status_code == 200 and "vor der Erstzulassung" in antwort.content.decode()
    # Datum leeren und „Aktiv“ anhaken holt das Fahrzeug zurück
    daten["verkauft_am"] = ""
    assert admin_client.post(seite_url, daten).status_code == 302
    wagen.refresh_from_db()
    assert wagen.verkauft_am is None and wagen.aktiv and fahrten.fahrzeuge() == [wagen]


def test_verkauftes_fahrzeug_bleibt_ausgeschaltet_beim_fortschreiben(lage):
    wagen = lage["wagen"]
    wagen.verkauft_am, wagen.aktiv = dt.date(2026, 10, 31), True
    wagen.kilometerstand = 500
    wagen.save(update_fields=["verkauft_am", "kilometerstand"])
    wagen.refresh_from_db()
    assert not wagen.aktiv and wagen.kilometerstand == 500
