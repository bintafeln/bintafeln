"""Rollen und Rechte (ADR 0033). Alle Daten sind erfunden."""

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from apps.konten import rechte, rollen, verwaltung
from apps.konten.models import Rolle

pytestmark = pytest.mark.django_db


def rolle(name):
    return Rolle.objects.get(gruppe__name=name)


def test_katalog_eindeutig_und_vorgaben_gueltig():
    codes = [r.code for r in rechte.KATALOG]
    assert len(codes) == len(set(codes))
    for name, liste in rechte.VORGABEN.items():
        assert set(liste) <= rechte.ALLE, name
    assert set(rolle("Büro").rechte) == set(rechte.VORGABEN["Büro"])
    assert set(rolle("Ausgabe").rechte) == set(rechte.VORGABEN["Ausgabe"])


def test_rechte_von(admin, benutzer_mit_rolle):
    assert rollen.rechte_von(admin) == rechte.ALLE
    nur_admin_gruppe = benutzer_mit_rolle("ada", rollen.ADMIN)
    assert rollen.rechte_von(nur_admin_gruppe) == rechte.ALLE
    zwei = benutzer_mit_rolle("zwei", rollen.AUSGABE, rollen.PERSONAL)
    assert "personal.sehen" in rollen.rechte_von(zwei) and "einlass.nutzen" in rollen.rechte_von(
        zwei
    )
    assert not rollen.hat_recht(zwei, "kunden.bearbeiten")
    with pytest.raises(ValueError, match="Unbekannte Rechte"):
        rollen.hat_recht(zwei, "gibt.es.nicht")
    with pytest.raises(ValueError, match="Unbekannte Rechte"):
        rollen.recht_erforderlich("gibt.es.nicht")


def test_gruppe_bekommt_automatisch_eine_rolle():
    g = Group.objects.create(name="Lager")
    assert Rolle.objects.get(gruppe=g).rechte == []


def test_neue_rolle_mit_einzelnen_rechten(client, admin_client, benutzer_mit_rolle, anmelden):
    seite = admin_client.get(reverse("konten:rolle_neu")).content.decode()
    assert "Kundenliste und Suche" in seite and "Einlass und Kasse" in seite
    antwort = admin_client.post(reverse("konten:rolle_neu"), {
        "name": "Telefondienst", "beschreibung": "Auskünfte am Telefon", "reihenfolge": "70",
        "rechte": ["kunden.liste", "kunden.ansehen", "kunden.kontakt"],
    })  # fmt: skip
    assert antwort.status_code == 302
    r = rolle("Telefondienst")
    assert r.rechte == ["kunden.liste", "kunden.ansehen", "kunden.kontakt"]
    assert not r.zwei_faktor_pflicht
    assert "Telefondienst" in admin_client.get(reverse("konten:rollen")).content.decode()

    anmelden(client, benutzer_mit_rolle("tom", "Telefondienst"))  # derselbe Client
    start = client.get("/").content.decode()
    assert "Alle Kunden" in start and "Einlass</a>" not in start
    assert client.get(reverse("kunden:uebersicht")).status_code == 200
    assert client.get(reverse("ausgabe:empfang")).status_code == 403
    assert client.get(reverse("konten:rollen")).status_code == 403


def test_doppelter_name_und_admin_name(admin_client):
    for name in ("Büro", "büro", "admin"):
        antwort = admin_client.post(reverse("konten:rolle_neu"), {"name": name, "reihenfolge": "1"})
        assert antwort.status_code == 200, name
        assert "Rolle" in antwort.content.decode() or "vorbehalten" in antwort.content.decode()


def test_admin_rolle_geschuetzt(admin_client):
    admin_rolle = rolle(rollen.ADMIN)
    seite = admin_client.get(reverse("konten:rolle", args=[admin_rolle.pk])).content.decode()
    assert "immer <strong>alle Rechte</strong>" in seite
    admin_client.post(reverse("konten:rolle", args=[admin_rolle.pk]), {
        "name": "Chef", "beschreibung": "Leitung", "reihenfolge": "0", "zwei_faktor_pflicht": "on",
    })  # fmt: skip
    admin_rolle.refresh_from_db()
    assert admin_rolle.name == rollen.ADMIN and admin_rolle.beschreibung == "Leitung"
    assert (
        admin_client.post(reverse("konten:rolle_loeschen", args=[admin_rolle.pk])).status_code
        == 403
    )


def test_rolle_loeschen(admin_client, benutzer_mit_rolle):
    k = benutzer_mit_rolle("kim", rollen.KIOSK)
    admin_client.post(reverse("konten:rolle_loeschen", args=[rolle(rollen.KIOSK).pk]))
    assert not Group.objects.filter(name=rollen.KIOSK).exists()
    assert not k.groups.exists()


def test_nicht_admin_gibt_nur_eigene_rechte_weiter(client, benutzer_mit_rolle, anmelden, admin,
                                                    recht_geben):  # fmt: skip
    recht_geben(rollen.BUERO, "einstellungen.rollen", "mitarbeitende.verwalten")
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    personal = rolle(rollen.PERSONAL)
    seite = client.get(reverse("konten:rolle", args=[personal.pk])).content.decode()
    assert "recht-fremd" in seite  # Personal-Rechte hat das Büro nicht: grau, unveränderbar
    client.post(reverse("konten:rolle", args=[personal.pk]), {
        "name": rollen.PERSONAL, "reihenfolge": "60", "rechte": ["kunden.liste"],
    })  # fmt: skip
    personal.refresh_from_db()
    assert set(personal.rechte) == {"kunden.liste", "personal.sehen", "einstellungen.arbeitszeit"}
    # Rechte, die man nicht hat, lassen sich auch über das Formular nicht einschmuggeln
    client.post(reverse("konten:rolle", args=[rolle(rollen.KIOSK).pk]), {
        "name": rollen.KIOSK, "reihenfolge": "30", "rechte": ["system.status"],
    })  # fmt: skip
    assert rolle(rollen.KIOSK).rechte == []
    # Rollen mit fremden Rechten weder löschen noch vergeben
    client.post(reverse("konten:rolle_loeschen", args=[personal.pk]))
    assert Rolle.objects.filter(pk=personal.pk).exists()
    berta = Group.objects.get(name=rollen.BUERO).user_set.get()
    assert rollen.PERSONAL not in verwaltung.vergebbare_rollen(berta)
    assert rollen.ADMIN not in verwaltung.vergebbare_rollen(berta)
    assert rollen.KIOSK in verwaltung.vergebbare_rollen(berta)
    admin_rolle = rolle(rollen.ADMIN)
    assert client.get(reverse("konten:rolle", args=[admin_rolle.pk])).status_code == 403


def test_nicht_vergebbare_rolle_bleibt_beim_bearbeiten(benutzer_mit_rolle, recht_geben):
    recht_geben(rollen.BUERO, "mitarbeitende.verwalten")
    berta = benutzer_mit_rolle("berta", rollen.BUERO)
    paula = benutzer_mit_rolle("paula", rollen.PERSONAL, rollen.KIOSK)
    verwaltung.bearbeiten(berta, paula, [rollen.AUSGABE])
    assert set(paula.groups.values_list("name", flat=True)) == {rollen.PERSONAL, rollen.AUSGABE}


def test_pflichten_aus_der_rolle(benutzer_mit_rolle):
    from apps.konten import personal

    g = Group.objects.create(name="Kurier")
    Rolle.objects.filter(gruppe=g).update(braucht_fuehrerschein=True)
    benutzer_mit_rolle("karl", "Kurier")
    texte = [f.was for f in personal.faelligkeiten()]
    assert "Führerschein ansehen" in texte


def test_vorgaben_wiederherstellen():
    Rolle.objects.filter(gruppe__name=rollen.BUERO).update(rechte=[])
    rollen.vorgaben_wiederherstellen()
    assert set(rolle(rollen.BUERO).rechte) == set(rechte.VORGABEN["Büro"])


def test_admin_rolle_fuer_admins_verlinkt(admin_client):
    seite = admin_client.get(reverse("konten:rollen")).content.decode()
    assert f'href="{reverse("konten:rolle", args=[rolle(rollen.ADMIN).pk])}"' in seite
