"""Modul Touren: Ausgabestellen der Tafel als Stationen (ADR 0171). Alle Daten sind erfunden."""

import pytest
from django.urls import reverse

from apps.core.models import TafelEinstellungen
from apps.kunden.models import Ausgabestelle
from apps.touren import ausgabestellen
from apps.touren.models import Station

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def modul_an():
    t = TafelEinstellungen.laden()
    t.module = ["touren"]
    t.save()


def stelle(name, **mehr):
    daten = {"strasse": "Musterweg 12a", "plz": "12345", "ort": "Musterstadt",
             "telefon": "01234 5550", "email": "stelle@example.org", **mehr}  # fmt: skip
    return Ausgabestelle.objects.create(name=name, **daten)


def test_strasse_teilen():
    teilen = ausgabestellen.strasse_teilen
    assert teilen("Musterweg 12a") == ("Musterweg", "12a")
    assert teilen("  Lange  Straße   7 ") == ("Lange Straße", "7")
    assert teilen("Am Markt 3-5") == ("Am Markt", "3-5")
    assert teilen("Straße des 17. Juni 4 b") == ("Straße des 17. Juni", "4 b")
    assert teilen("Marktplatz") == ("Marktplatz", "")
    assert teilen("") == ("", "")


def test_ausgabestellen_werden_stationen_und_bleiben_aktuell():
    zentrale = stelle("Zentrale")
    stelle("Ohne Anschrift", strasse="", plz="", ort="")
    stelle("Geschlossen", aktiv=False)
    bericht = ausgabestellen.abgleichen()
    assert bericht == {"neu": 1, "geaendert": 0, "ohne_anschrift": ["Ohne Anschrift"]}
    s = Station.objects.get()
    assert (s.kennung, s.art, s.name) == (f"AS-{zentrale.pk}", "ausgabestelle", "Zentrale")
    assert (s.strasse, s.hausnummer, s.plz, s.ort) == ("Musterweg", "12a", "12345", "Musterstadt")
    assert (s.telefon, s.email, s.aktiv, s.lieferschein) == (
        "01234 5550", "stelle@example.org", True, False,
    )  # fmt: skip
    assert s.ausgabestelle == zentrale and "Musterweg 12a" in s.anschrift
    # nichts geändert: der Abgleich schreibt nichts
    assert ausgabestellen.abgleichen()["geaendert"] == 0
    # was an der Station gepflegt wird, bleibt; was aus der Ausgabestelle kommt, zieht nach
    s.anfahrt, s.lieferschein, s.abholzeit = "Rampe hinten", True, "ab 8 Uhr"
    s.save()
    zentrale.name, zentrale.strasse, zentrale.telefon = "Zentrale Mitte", "Neue Gasse 3", "0999"
    zentrale.save()
    assert ausgabestellen.abgleichen() == {
        "neu": 0, "geaendert": 1, "ohne_anschrift": ["Ohne Anschrift"],
    }  # fmt: skip
    s.refresh_from_db()
    assert (s.name, s.strasse, s.hausnummer, s.telefon) == (
        "Zentrale Mitte",
        "Neue Gasse",
        "3",
        "0999",
    )
    assert (s.anfahrt, s.lieferschein, s.abholzeit) == ("Rampe hinten", True, "ab 8 Uhr")
    assert s.kennung == f"AS-{zentrale.pk}"
    # Ausgabestelle abgeschaltet: die Station bleibt, wird aber nicht mehr angefahren
    zentrale.aktiv = False
    zentrale.save()
    ausgabestellen.abgleichen()
    s.refresh_from_db()
    assert not s.aktiv and Station.objects.count() == 1
    # Anschrift an der Ausgabestelle geleert: die alte bleibt an der Station stehen
    zentrale.aktiv, zentrale.strasse = True, ""
    zentrale.save()
    ausgabestellen.abgleichen()
    s.refresh_from_db()
    assert s.aktiv and s.strasse == "Neue Gasse"


def test_von_hand_angelegte_station_wird_verknuepft_statt_verdoppelt():
    nord = stelle("Ausgabestelle Nord")
    alt = Station.objects.create(
        kennung="S-7", art=Station.Art.AUSGABESTELLE, name="ausgabestelle nord",
        strasse="Alte Straße", plz="11111", ort="Altstadt", anfahrt="Hof",
    )  # fmt: skip
    Station.objects.create(kennung="S-8", art=Station.Art.MARKT, name="Ausgabestelle Nord",
                           strasse="Marktweg", plz="12345", ort="Musterstadt")  # fmt: skip
    assert ausgabestellen.abgleichen()["neu"] == 0
    alt.refresh_from_db()
    assert alt.ausgabestelle == nord and alt.kennung == "S-7" and alt.anfahrt == "Hof"
    assert (alt.name, alt.strasse, alt.ort) == ("Ausgabestelle Nord", "Musterweg", "Musterstadt")
    assert Station.objects.count() == 2


def test_liste_seite_und_schutz(admin_client):
    zentrale = stelle("Zentrale")
    stelle("Ohne Anschrift", strasse="")
    # die Liste gleicht selbst ab und nennt, was noch keine Anschrift hat
    seite = admin_client.get(reverse("touren:stationen")).content.decode()
    assert "Zentrale" in seite and "Ohne Anschrift" in seite and "nicht dabei" in seite
    s = Station.objects.get(ausgabestelle=zentrale)
    seite = admin_client.get(reverse("touren:station", args=[s.pk])).content.decode()
    assert "Ausgabestelle der Tafel" in seite and "Station löschen" not in seite
    assert reverse("kunden:ausgabestelle", args=[zentrale.pk]) in seite
    # Löschen geht hier nicht
    antwort = admin_client.post(reverse("touren:loeschen", args=[s.pk]), follow=True)
    assert "lässt sich" in antwort.content.decode() and Station.objects.filter(pk=s.pk).exists()
    # Bearbeiten: Angaben der Ausgabestelle sind gesperrt, die der Station änderbar
    bearbeiten = reverse("touren:bearbeiten", args=[s.pk])
    form = admin_client.get(bearbeiten).context["form"]
    assert form.fields["name"].disabled and form.fields["strasse"].disabled
    assert not form.fields["anfahrt"].disabled and not form.fields["lieferschein"].disabled
    antwort = admin_client.post(bearbeiten, {
        "name": "Gefälscht", "strasse": "Woanders", "plz": "99999", "ort": "X",
        "art": "markt", "kennung": "X-1", "anfahrt": "Rampe hinten", "lieferschein": "on",
        "abholzeit": "ab 8 Uhr",
    })  # fmt: skip
    assert antwort.status_code == 302, antwort.context["form"].errors
    s.refresh_from_db()
    assert (s.name, s.strasse, s.art, s.kennung) == (
        "Zentrale",
        "Musterweg",
        "ausgabestelle",
        f"AS-{zentrale.pk}",
    )
    assert (s.anfahrt, s.lieferschein, s.abholzeit) == ("Rampe hinten", True, "ab 8 Uhr")
    # eine normale Station lässt sich weiter löschen
    markt = Station.objects.create(kennung="S-1", name="Markt", strasse="Weg", plz="1", ort="O")
    admin_client.post(reverse("touren:loeschen", args=[markt.pk]))
    assert not Station.objects.filter(pk=markt.pk).exists()


def test_startseite_haelt_aktuell(admin_client):
    """Auch ohne die Stationsliste zu öffnen: Der tägliche Lauf (Startseite) gleicht ab."""
    stelle("Zentrale")
    admin_client.get(reverse("core:start"))
    assert Station.objects.filter(art="ausgabestelle", name="Zentrale").exists()
