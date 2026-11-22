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
    client.post(reverse("touren:fahrt_beginnen", args=[tour.pk]),
                {"fahrzeug": wagen.pk, "km_start": "5000"})  # fmt: skip
    fahrt = Fahrt.objects.get()
    seite = client.get(adresse).content.decode()
    assert "Unterwegs" in seite and "Tour beenden" in seite and "Fahrt beginnen" not in seite
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


def test_einstellungen_fahrzeuge(admin_client):
    seite = admin_client.get(reverse("touren:einrichten")).content.decode()
    assert "Fahrzeuge" in seite
    daten = {"fahrzeuge": "1", "fz-TOTAL_FORMS": 2, "fz-INITIAL_FORMS": 0,
             "fz-MIN_NUM_FORMS": 0, "fz-MAX_NUM_FORMS": 1000,
             "fz-0-name": "Transporter", "fz-0-kennzeichen": "MU-ST 2", "fz-0-reihenfolge": "1",
             "fz-0-kilometerstand": "45000",
             "fz-0-aktiv": "on", "fz-1-name": "", "fz-1-kennzeichen": "",
             "fz-1-reihenfolge": "0", "fz-1-aktiv": "on"}  # fmt: skip
    assert admin_client.post(reverse("touren:einrichten"), daten).status_code == 302
    wagen = Fahrzeug.objects.get()
    assert str(wagen) == "Transporter (MU-ST 2)" and wagen.kilometerstand == 45000


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
