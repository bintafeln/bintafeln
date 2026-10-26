"""Suche im Seitenkopf (ADR 0040). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.urls import reverse

from apps.antraege.models import Antrag, AntragAnmerkung
from apps.core import suche
from apps.konten import rollen
from apps.kunden.models import (
    Abholer,
    Ausgabestelle,
    Bemerkung,
    Dokumentart,
    Haushalt,
    HaushaltDokument,
    Kundengruppe,
    Notiz,
    Person,
)

pytestmark = pytest.mark.django_db
URL = reverse("core:suche")
HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def daten():
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    mo = Kundengruppe.objects.create(name="Mo", ausgabestelle=mitte)
    h1 = Haushalt.objects.create(
        kundennummer="1001", strasse="Lindenweg 3", plz="12345", ort="Musterstadt",
        telefon="0123 456789", kundengruppe=mo,
    )  # fmt: skip
    h2 = Haushalt.objects.create(
        kundennummer="2002", kundengruppe=Kundengruppe.objects.create(name="Di", ausgabestelle=nord)
    )
    Person.objects.create(haushalt=h1, ist_hauptperson=True, vorname="Erika", nachname="Müller")
    Person.objects.create(haushalt=h2, ist_hauptperson=True, vorname="Müllerin", nachname="Probe")
    Abholer.objects.create(haushalt=h1, vorname="Max", nachname="Abholmüller")
    Notiz.objects.create(kundennummer="1001", text="Bringt den neuen Bescheid mit.")
    Notiz.objects.create(kundennummer="2002", text="Bescheide fehlen noch.")
    Bemerkung.objects.create(haushalt=h1, datum=dt.date(2026, 1, 5), text="Spricht wenig Deutsch")
    HaushaltDokument.objects.create(kundennummer="1001", art=Dokumentart.objects.first(),
                                    titel="Bescheid Jobcenter", datei="x")  # fmt: skip
    a = Antrag.objects.create(vorname="Hans", nachname="Müllerhaus")
    AntragAnmerkung.objects.create(antrag=a, text="Rückruf wegen Deutschkurs", von="berta")
    return mitte, nord


def test_zerlegen():
    assert suche.zerlegen("n  bescheid ") == (suche.KUERZEL[1], "bescheid")
    assert suche.zerlegen("an müller")[0].bereich == "antraege"
    assert suche.zerlegen("mül") == (None, "mül")
    assert suche.zerlegen("x müller") == (None, "x müller")


def test_ohne_kuerzel_namen_in_vor_und_nachname(admin, daten):
    e = suche.suchen(admin, "mül")
    gruppen = {g.bereich: [t.titel for t in g.treffer] for g in e.gruppen}
    assert "Erika Müller · Kunde 1001" in gruppen["kunden"]
    assert "Müllerin Probe · Kunde 2002" in gruppen["kunden"]
    assert "Max Abholmüller · Kunde 1001" in gruppen["kunden"]
    assert gruppen["antraege"] == [f"Antrag {Antrag.objects.get().nummer} · Hans Müllerhaus"]
    assert "notizen" not in gruppen
    assert suche.suchen(admin, "mü").zu_kurz
    assert suche.suchen(admin, "100").gruppen[0].treffer[0].titel == "1001 · Erika Müller"


def test_kuerzel(admin, daten):
    def titel(eingabe):
        return [t.titel for g in suche.suchen(admin, eingabe).gruppen for t in g.treffer]

    assert titel("n bescheid") == ["Kunde 2002: Bescheide fehlen noch.",
                                   "Kunde 1001: Bringt den neuen Bescheid mit."]  # fmt: skip
    assert len(titel("a deutsch")) == 2  # Haushalt und Antrag
    assert titel("s linden") == ["Kunde 1001: Lindenweg 3, 12345 Musterstadt"]
    assert titel("t 456") == ["Kunde 1001: 0123 456789"]
    assert titel("d jobcenter") == ["Kunde 1001: Bescheid Jobcenter"]
    assert titel("m chef") == ["chefin"]
    assert any(t.startswith("Der Einlass Schritt für Schritt") for t in titel("h ampel"))


def test_rechte_und_ausgabestelle(client, benutzer_mit_rolle, anmelden, daten):
    mitte, _ = daten
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    anmelden(client, b)
    e = suche.suchen(b, "mül")
    # keine Anträge, keine Mitarbeitenden; das Handbuch nennt „mül“ als Beispiel
    assert [g.bereich for g in e.gruppen] == ["kunden", "hilfe"]
    titel = [t.titel for t in e.gruppen[0].treffer]
    assert "Erika Müller · Kunde 1001" in titel and not any("2002" in t for t in titel)
    assert e.gruppen[0].treffer[0].url == reverse("kunden:haushalt", args=["1001"])
    notizen = [t.titel for g in suche.suchen(b, "n bescheid").gruppen for t in g.treffer]
    assert notizen == ["Kunde 1001: Bringt den neuen Bescheid mit."]
    assert not suche.suchen(b, "s linden").gruppen  # keine Anschrift ohne Recht
    assert not suche.suchen(b, "m chef").gruppen
    zeichen = [k.zeichen for k in suche.kuerzel_fuer(b)]
    assert "m" not in zeichen and "n" in zeichen and "h" in zeichen


def test_nur_einlass_fuehrt_zum_einlass(client, benutzer_mit_rolle, daten):
    from apps.konten.models import Rolle

    rolle = Rolle.objects.get(gruppe__name=rollen.AUSGABE)
    rolle.rechte = ["einlass.nutzen"]
    rolle.save()
    b = benutzer_mit_rolle("emil", rollen.AUSGABE)
    treffer = suche.suchen(b, "mül").gruppen[0].treffer[0]
    assert treffer.url == f"{reverse('ausgabe:empfang')}?nummer=1001"


def test_oberflaeche(admin_client, client, daten):
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert 'id="kopf-suche"' in seite and 'hx-get="/suche/"' in seite
    kurz = admin_client.get(URL, {"q": "mül"}, **HX).content.decode()
    assert "<html" not in kurz and "Erika Müller · Kunde 1001" in kurz
    assert reverse("kunden:haushalt", args=["1001"]) in kurz and "Alle Treffer anzeigen" in kurz
    assert "mindestens 3 Zeichen" in admin_client.get(URL, {"q": "mü"}, **HX).content.decode()
    assert "n bescheid" in admin_client.get(URL, {"q": "?"}, **HX).content.decode()
    assert admin_client.get(URL, {"q": ""}, **HX).content.decode().strip() == ""
    assert "Nichts gefunden" in admin_client.get(URL, {"q": "xyzxyz"}, **HX).content.decode()
    voll = admin_client.get(URL, {"q": "n bescheid"}).content.decode()
    assert "2 Treffer" in voll and "<h2>Notizen</h2>" in voll
    admin_client.logout()
    assert client.get(URL, {"q": "mül"}).status_code == 302  # nur angemeldet


def test_programm_und_handbuch_ohne_kuerzel(admin_client, admin, daten):
    from apps.core.menue import menue

    antwort = admin_client.get(reverse("core:suche"), {"q": "ausgabestellen"})
    e = antwort.context["e"]
    programm = next(g for g in e.gruppen if g.bereich == "programm")
    assert programm.treffer[0].titel == "Ausgabestellen"
    assert programm.treffer[0].url == reverse("kunden:ausgabestellen")
    assert programm.treffer[0].zusatz == "Menü: Kunden"
    assert e.gruppen[0].bereich == "programm"
    hilfe = next(g for g in e.gruppen if g.bereich == "hilfe")
    assert hilfe.treffer[0].titel.startswith("Ausgabestellen")  # Titel vor Text
    assert hilfe.treffer[0].url.startswith(reverse("core:hilfe") + "#")
    # Untermenü der Einstellungen: Weg mit Gruppe; Treffer im Bereich nach Treffern im Namen
    anfrage = antwort.wsgi_request
    treffer = suche._programm(admin, "kunden", 50, menue=menue(anfrage))
    titel = [t.titel for t in treffer]
    assert titel.index("Kunden einsehen") < titel.index("Ausgabestellen")
    gruppen = next(t for t in treffer if t.titel == "Kundengruppen")
    assert gruppen.zusatz == "Menü: Einstellungen › Kunden"
    assert len({t.url for t in treffer}) == len(treffer)
    assert suche._programm(admin, "xyzxyz", 5, menue=menue(anfrage)) == []


def test_programm_nur_mit_rechten(admin, client, benutzer_mit_rolle, anmelden, daten):
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    e = client.get(reverse("core:suche"), {"q": "p rollen"}).context["e"]
    assert e.gruppen == []  # „Rollen und Rechte“ sieht nur, wer das Recht hat


def test_handbuch_abschnitt_und_suchfeld(admin_client):
    seite = admin_client.get(reverse("core:hilfe")).content.decode()
    assert 'name="nur" value="hilfe"' in seite
    e = admin_client.get(reverse("core:suche"), {"q": "ampel", "nur": "hilfe"}).context["e"]
    assert e.kuerzel.bereich == "hilfe" and [g.bereich for g in e.gruppen] == ["hilfe"]
    assert any(" › " in t.titel for t in e.gruppen[0].treffer)
    e = admin_client.get(reverse("core:suche"), {"q": "k ampel", "nur": "hilfe"}).context["e"]
    assert e.kuerzel.bereich == "kunden"


def test_listen_und_einstellungen_werden_gefunden(admin_client, admin, daten):
    """„zentrale“ findet die Ausgabestelle, ihre Kundengruppen und alles, was so heißt."""
    from decimal import Decimal

    from apps.adressen.models import Adresse, AdressKategorie
    from apps.core.models import TafelEinstellungen
    from apps.konten.models import Rolle
    from apps.kunden.models import Ausgabestelle, Dokumentart, Einkommensart, NotizVorlage
    from apps.mitglieder.models import Mitglied
    from apps.serienbriefe.models import Vorlage
    from apps.spenden.models import Spende
    from apps.warteliste.models import Termin
    from apps.wochenuebersicht.models import Selbstabholer

    zentrale = Ausgabestelle.objects.create(
        name="Zentrale", strasse="Hauptstr. 1", ort="Musterstadt"
    )
    Kundengruppe.objects.create(name="Mi 12:30", kuerzel="Z1", ausgabestelle=zentrale,
                                wochentage="Mi")  # fmt: skip
    Einkommensart.objects.create(bezeichnung="Zentrale Leistung")
    Dokumentart.objects.create(bezeichnung="Zentraler Bescheid")
    NotizVorlage.objects.create(text="Bitte in der Zentrale melden")
    AdressKategorie.objects.create(name="Zentrale Partner")
    Rolle.objects.filter(gruppe__name=rollen.BUERO).update(beschreibung="Büro in der Zentrale")
    Vorlage.objects.create(name="Zentrale Info", betreff="Neues aus der Zentrale", text="x")
    a = Adresse.objects.create(art="person", vorname="Max", nachname="Probe")
    Mitglied.objects.create(adresse=a, nummer="ZENTRALE-1", art="aktiv",
                            eintritt=dt.date(2020, 1, 1))  # fmt: skip
    Spende.objects.create(adresse=a, datum=dt.date(2025, 1, 1), betrag=Decimal("5"),
                          belegnummer="ZENTRALE-7")  # fmt: skip
    Selbstabholer.objects.create(name="Zentrale Frauenhaus", tage="Mi")
    Termin.objects.create(datum=dt.date(2026, 11, 1), von=dt.time(10), ort="Zentrale, Raum 2")

    def titel(q):
        e = admin_client.get(reverse("core:suche"), {"q": q}).context["e"]
        g = next((g for g in e.gruppen if g.bereich == "listen"), None)
        return [t.titel for t in g.treffer] if g else []

    gefunden = titel("l zentrale")
    for erwartet in ("Zentrale", "Z1 – Mi 12:30", "Zentrale Leistung", "Zentraler Bescheid",
                     "Bitte in der Zentrale melden", "Zentrale Partner", rollen.BUERO,
                     "Zentrale Info", "Mitglied ZENTRALE-1 · Max Probe",
                     "Spende ZENTRALE-7 · Max Probe"):  # fmt: skip
        assert erwartet in gefunden, erwartet
    assert "Zentrale Frauenhaus" not in gefunden  # Modul aus
    TafelEinstellungen.objects.update(module=["wochenuebersicht", "warteliste"])
    gefunden = titel("l zentrale")
    assert "Zentrale Frauenhaus" in gefunden and any(t.startswith("Termin") for t in gefunden)
    e = admin_client.get(reverse("core:suche"), {"q": "zentrale"}).context["e"]
    assert "listen" in [g.bereich for g in e.gruppen]
    url = next(t.url for g in e.gruppen for t in g.treffer if t.titel == "Zentrale")
    assert url == reverse("kunden:ausgabestelle", args=[zentrale.pk])


def test_listen_nur_mit_rechten(admin, client, benutzer_mit_rolle, anmelden, daten):
    from apps.core.models import TafelEinstellungen
    from apps.kunden.models import Ausgabestelle
    from apps.warteliste.models import Termin
    from apps.wochenuebersicht.models import Selbstabholer

    Ausgabestelle.objects.create(name="Zentrale")
    Kundengruppe.objects.create(name="Zentrale Mi", wochentage="Mi")
    Selbstabholer.objects.create(name="Zentrale Frauenhaus")
    Termin.objects.create(datum=dt.date(2026, 11, 1), von=dt.time(10), ort="Zentrale")
    TafelEinstellungen.objects.update(module=["wochenuebersicht", "warteliste"])
    b = benutzer_mit_rolle("kim", rollen.KIOSK)
    titel = [t.titel for g in suche.suchen(b, "l zentrale").gruppen for t in g.treffer]
    assert titel == []


def test_enter_mit_kundennummer_geht_direkt_zum_kunden(admin_client, client, benutzer_mit_rolle,
                                                      anmelden, daten):  # fmt: skip
    """„k 10141“ bzw. nur die Nummer und Enter: gleich zum Kunden, führende Nullen egal."""
    haushalt = reverse("kunden:haushalt", args=["1001"])
    assert admin_client.get(URL, {"q": "k 1001"}).url == haushalt
    assert admin_client.get(URL, {"q": "1001"}).url == haushalt
    assert admin_client.get(URL, {"q": "k 01001"}).url == haushalt
    # Live-Liste (HTMX), Teilnummern, andere Kürzel und fremde Ausgabestellen: keine Weiterleitung
    assert admin_client.get(URL, {"q": "k 1001"}, **HX).status_code == 200
    assert admin_client.get(URL, {"q": "k 100"}).status_code == 200
    assert admin_client.get(URL, {"q": "n 1001"}).status_code == 200
    mitte, _ = daten
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    anmelden(client, b)
    assert client.get(URL, {"q": "k 2002"}).status_code == 200  # Nord: nicht seine
    assert client.get(URL, {"q": "k 1001"}).status_code == 302
