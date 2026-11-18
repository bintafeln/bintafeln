"""Einkommensart sammelweise ändern (ADR 0146). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse

from apps.konten import rollen
from apps.kunden import views_einkommensart as ve
from apps.kunden.models import (
    Ausgabestelle,
    Einkommensart,
    Haushalt,
    HaushaltEreignis,
    Kundengruppe,
    Person,
)

pytestmark = pytest.mark.django_db
URL = reverse("kunden:einkommensart_umstellen")
HEUTE = dt.date(2026, 11, 18)


def _haushalt(nummer, art, geboren, status=Haushalt.Status.AKTIV, stelle=None):
    gruppe = Kundengruppe.objects.create(name=f"Gruppe {nummer}", ausgabestelle=stelle)
    h = Haushalt.objects.create(kundennummer=nummer, einkommensart=art, status=status,
                                kundengruppe=gruppe)  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Erika", nachname=f"Muster{nummer}",
                          ist_hauptperson=True, geburtsdatum=geboren)  # fmt: skip
    return h


@pytest.fixture
def welt(admin):
    sonstiges = Einkommensart.objects.create(bezeichnung="Sonstiges")
    alter = Einkommensart.objects.create(bezeichnung="Grundsicherung")
    geld = Einkommensart.objects.create(bezeichnung="Bürgergeld")
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    beendet = [s for s in Haushalt.Status.values if s != Haushalt.Status.AKTIV][0]
    return {
        "sonstiges": sonstiges, "alter": alter, "geld": geld, "mitte": mitte,
        # genau 65 heute: zählt als „65 oder älter“
        "genau65": _haushalt("00001", sonstiges, dt.date(1961, 11, 18), stelle=mitte),
        "fast65": _haushalt("00002", sonstiges, dt.date(1961, 11, 19), stelle=mitte),
        "alt_beendet": _haushalt("00003", sonstiges, dt.date(1940, 1, 1), beendet, stelle=nord),
        "jung": _haushalt("00004", sonstiges, dt.date(1990, 5, 5), stelle=nord),
        "ohne_datum": _haushalt("00005", sonstiges, None, stelle=mitte),
        "andere_art": _haushalt("00006", geld, dt.date(1940, 1, 1), stelle=mitte),
    }  # fmt: skip


def _nummern(haushalte):
    return sorted(h.kundennummer for h in haushalte)


def test_grenze_und_auswahl(welt, admin):
    assert ve.grenze(dt.date(2028, 2, 29), 65) == dt.date(1963, 2, 28)
    ab, ohne = ve.betroffene(admin, welt["sonstiges"], "ab", 65, HEUTE)
    assert _nummern(ab) == ["00001", "00003"] and _nummern(ohne) == ["00005"]
    unter, ohne = ve.betroffene(admin, welt["sonstiges"], "unter", 65, HEUTE)
    assert _nummern(unter) == ["00002", "00004"] and _nummern(ohne) == ["00005"]
    alle, ohne = ve.betroffene(admin, welt["sonstiges"], "alle", 65, HEUTE)
    assert len(alle) == 5 and not ohne.exists()


def test_aendern_mit_historie_und_in_portionen(welt, admin):
    ab, _ = ve.betroffene(admin, welt["sonstiges"], "ab", 65, HEUTE)
    assert ve.aendern(ab, welt["alter"], "chefin") == 2
    for name in ("genau65", "alt_beendet"):
        h = Haushalt.objects.get(pk=welt[name].pk)
        assert h.einkommensart == welt["alter"] and h.geaendert_von == "chefin"
        assert HaushaltEreignis.objects.filter(kundennummer=h.kundennummer).exists()
    assert Haushalt.objects.get(pk=welt["ohne_datum"].pk).einkommensart == welt["sonstiges"]
    assert Haushalt.objects.get(pk=welt["fast65"].pk).einkommensart == welt["sonstiges"]
    # Zeit abgelaufen: mindestens einer, der Rest beim nächsten Mal
    unter, _ = ve.betroffene(admin, welt["sonstiges"], "unter", 65, HEUTE)
    assert ve.aendern(unter, welt["geld"], "chefin", sekunden=0.000001) == 1
    assert unter.count() == 1
    assert ve.aendern(unter, welt["geld"], "chefin", sekunden=30) == 1


def test_seite_vorschau_und_aendern(admin_client, welt, monkeypatch):
    monkeypatch.setattr(ve.timezone, "localdate", lambda: HEUTE)
    assert "Einkommensart sammelweise ändern" in admin_client.get(URL).content.decode()
    wahl = {"von": welt["sonstiges"].pk, "alter": "ab", "jahre": 65, "nach": welt["alter"].pk}
    seite = admin_client.get(URL, wahl).content.decode()
    assert "2 Haushalte betroffen" in seite and "Davon 1 aktiv" in seite
    assert "1 Haushalt ohne Geburtsdatum" in seite and "Muster00001" in seite
    assert Haushalt.objects.filter(einkommensart=welt["alter"]).count() == 0  # nur angesehen
    antwort = admin_client.post(URL, wahl, follow=True)
    assert "Einkommensart geändert" in antwort.content.decode()
    assert _nummern(Haushalt.objects.filter(einkommensart=welt["alter"])) == ["00001", "00003"]
    # danach passt keiner mehr; gleiche Art zweimal ist ein Fehler
    assert "Kein Haushalt passt" in admin_client.get(URL, wahl).content.decode()
    gleich = admin_client.get(URL, {**wahl, "nach": welt["sonstiges"].pk}).content.decode()
    assert "zwei verschiedene Einkommensarten" in gleich


def test_in_portionen_mit_htmx(admin_client, welt, monkeypatch):
    monkeypatch.setattr(ve.timezone, "localdate", lambda: HEUTE)
    monkeypatch.setattr(ve, "SEKUNDEN", 0.000001)
    wahl = {"von": welt["sonstiges"].pk, "alter": "unter", "jahre": 65, "nach": welt["geld"].pk}
    antwort = admin_client.post(URL, wahl, headers={"HX-Request": "true"})
    assert antwort.status_code == 204 and "laeuft=1" in antwort["HX-Redirect"]
    seite = admin_client.get(antwort["HX-Redirect"]).content.decode()
    assert "Ändern läuft" in seite and "1 Haushalt noch offen" in seite
    antwort = admin_client.post(URL, wahl)
    assert antwort.url == URL
    assert not Haushalt.objects.filter(
        einkommensart=welt["sonstiges"], personen__geburtsdatum__gt=dt.date(1961, 11, 18)
    ).exists()


def test_recht_menue_und_nur_eigene_kunden(admin, welt, benutzer_mit_rolle, anmelden,
                                           recht_geben):  # fmt: skip
    from django.test import RequestFactory

    from apps.core.menue import menue as menue_bauen

    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.ausgabestellen.set([welt["mitte"]])
    c = anmelden(Client(), anton)
    assert c.get(URL).status_code == 403
    recht_geben(rollen.AUSGABE, "kunden.bearbeiten")
    anton.refresh_from_db()
    ab, _ = ve.betroffene(anton, welt["sonstiges"], "ab", 65, HEUTE)
    assert _nummern(ab) == ["00001"]  # der Kunde der anderen Ausgabestelle bleibt außen vor
    anfrage = RequestFactory().get("/")
    anfrage.user = admin
    assert URL in str(menue_bauen(anfrage))
