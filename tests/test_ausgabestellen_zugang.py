"""Mitarbeitende einer Ausgabestelle sehen nur deren Kunden (ADR 0034). Erfundene Daten."""

import pytest
from django.urls import reverse

from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.models import (
    Ausgabestelle,
    Dokumentart,
    Haushalt,
    HaushaltDokument,
    Kundengruppe,
    Notiz,
    Person,
    Zugriff,
)

pytestmark = pytest.mark.django_db
HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def stellen():
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    g_mitte = Kundengruppe.objects.create(name="Montag Mitte", ausgabestelle=mitte)
    g_nord = Kundengruppe.objects.create(name="Dienstag Nord", ausgabestelle=nord)
    for nummer, gruppe in (("100", g_mitte), ("200", g_nord), ("300", None)):
        h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe)
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                              nachname=f"Probe{nummer}")  # fmt: skip
    return mitte, nord


@pytest.fixture
def anton(client, admin, benutzer_mit_rolle, anmelden, stellen):
    """Ausgabe, zugeordnet zur Ausgabestelle Mitte."""
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([stellen[0]])
    anmelden(client, b)
    return client


def test_sperrgrund(benutzer_mit_rolle, stellen):
    mitte, nord = stellen
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    h100, h200, h300 = (Haushalt.objects.get(kundennummer=n) for n in ("100", "200", "300"))
    assert all(zugang.sperrgrund(b, h) == "" for h in (h100, h200, h300))  # ohne Zuordnung

    b.ausgabestellen.set([mitte])
    b = type(b).objects.get(pk=b.pk)  # neue Instanz, ohne Zwischenspeicher
    assert zugang.sperrgrund(b, h100) == ""
    grund = zugang.sperrgrund(b, h200)
    assert "Kunde 200 gehört zur Ausgabestelle „Nord“ (Kundengruppe „Dienstag Nord“)" in grund
    assert "Sie sind der Ausgabestelle „Mitte“ zugeordnet" in grund and "Büro" in grund
    assert "keiner Kundengruppe zugeordnet" in zugang.sperrgrund(b, h300)

    b.ausgabestellen.set([mitte, nord])
    b = type(b).objects.get(pk=b.pk)
    assert zugang.sperrgrund(b, h200) == ""
    assert "den Ausgabestellen „Mitte“ und „Nord“" in zugang.sperrgrund(b, h300)


def test_einlass(anton):
    seite = anton.get(reverse("ausgabe:empfang"), {"nummer": "200"}, **HX).content.decode()
    assert "Dieser Kunde gehört nicht zu Ihrer Ausgabestelle" in seite
    assert "gehört zur Ausgabestelle „Nord“" in seite and "Probe200" not in seite
    assert not Zugriff.objects.filter(kundennummer="200").exists()
    seite = anton.get(reverse("ausgabe:empfang"), {"nummer": "100"}, **HX).content.decode()
    assert "Probe100" in seite
    antwort = anton.post(reverse("ausgabe:eintragen", args=["200"]), {"bar": "0"})
    assert antwort.status_code == 403 and "Nord" in antwort.content.decode()


def test_kundenliste_und_detail(anton):
    liste = anton.get(reverse("kunden:uebersicht")).content.decode()
    assert "Probe100" in liste and "Probe200" not in liste and "Probe300" not in liste
    assert "Sie sehen nur Kunden der Ausgabestelle" in liste and "„Mitte“" in liste
    antwort = anton.get(reverse("kunden:uebersicht"), {"q": "200"}, follow=True)
    assert antwort.redirect_chain == [] and "gehört zur Ausgabestelle „Nord“" in (
        antwort.content.decode()
    )
    assert anton.get(reverse("kunden:uebersicht"), {"q": "100"}).status_code == 302
    # Ausgabestellen landen beim Aufruf eines Kunden gleich im Einlass, der die Zuordnung prüft
    detail = anton.get(reverse("kunden:haushalt", args=["200"]), follow=True)
    assert detail.redirect_chain == [("/ausgabe/?nummer=200", 302)]
    assert "Dieser Kunde gehört nicht zu Ihrer Ausgabestelle" in detail.content.decode()
    assert anton.get(reverse("kunden:haushalt", args=["100"])).url == "/ausgabe/?nummer=100"


def test_detail_ohne_einlass_nur_eigene(anton, recht_nehmen):
    recht_nehmen(rollen.AUSGABE, "einlass.nutzen")
    detail = anton.get(reverse("kunden:haushalt", args=["200"]))
    assert detail.status_code == 403
    assert "Kein Zugriff" in detail.content.decode() and "„Nord“" in detail.content.decode()
    assert anton.get(reverse("kunden:haushalt", args=["100"])).status_code == 200


def test_daten_an_der_kundennummer(anton, admin):
    n = Notiz.objects.create(kundennummer="200", text="erfunden")
    assert anton.post(reverse("kunden:notiz_loeschen", args=[n.pk])).status_code == 403
    assert Notiz.objects.filter(pk=n.pk).exists()
    weg = Notiz.objects.create(kundennummer="999", text="ohne Haushalt")
    assert anton.post(reverse("kunden:notiz_loeschen", args=[weg.pk])).status_code == 403
    assert zugang.pruefen_nummer(admin, "999") is None  # Admin darf alles


def test_dokument_fremder_ausgabestelle(client, admin, benutzer_mit_rolle, anmelden, stellen,
                                        recht_geben):  # fmt: skip
    recht_geben(rollen.AUSGABE, "kunden.dokumente")
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([stellen[0]])
    anmelden(client, b)
    art = Dokumentart.objects.first()
    d = HaushaltDokument.objects.create(kundennummer="200", art=art, titel="T", datei="x")
    assert client.get(reverse("kunden:dokument", args=[d.pk])).status_code == 403


def test_buero_mit_zuordnung_sieht_alle(client, admin, benutzer_mit_rolle, anmelden, stellen):
    b = benutzer_mit_rolle("berta", rollen.BUERO)
    b.ausgabestellen.set([stellen[0]])
    anmelden(client, b)
    assert client.get(reverse("kunden:haushalt", args=["200"])).status_code == 200


def test_zuordnung_im_mitarbeitendenformular(admin_client, stellen):
    mitte, nord = stellen
    admin_client.post(reverse("konten:mitarbeiter_neu"), {
        "username": "neu", "first_name": "N", "last_name": "Eu", "beschaeftigung": "ehrenamtlich",
        "rollen": [rollen.AUSGABE], "ausgabestellen": [nord.pk],
    })  # fmt: skip
    from django.contrib.auth import get_user_model

    neu = get_user_model().objects.get(username="neu")
    assert list(neu.ausgabestellen.all()) == [nord]
    admin_client.post(reverse("konten:mitarbeiter", args=[neu.pk]), {
        "username": "neu", "first_name": "N", "last_name": "Eu", "beschaeftigung": "ehrenamtlich",
        "rollen": [rollen.AUSGABE], "ausgabestellen": [mitte.pk, nord.pk],
    })  # fmt: skip
    assert set(neu.ausgabestellen.all()) == {mitte, nord}
