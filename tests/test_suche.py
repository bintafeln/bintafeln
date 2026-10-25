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
    assert "Der Einlass Schritt für Schritt" in titel("h ampel")


def test_rechte_und_ausgabestelle(client, benutzer_mit_rolle, anmelden, daten):
    mitte, _ = daten
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    anmelden(client, b)
    e = suche.suchen(b, "mül")
    assert [g.bereich for g in e.gruppen] == ["kunden"]  # keine Anträge, keine Mitarbeitenden
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
