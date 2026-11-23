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


def test_nachfrist_ausgeschiedene_bleiben_eine_weile_sichtbar(benutzer_mit_rolle, stellen):
    """Wer aus der Kundengruppe gefallen ist, bleibt der früheren Ausgabestelle die Nachfrist
    (Vorgabe 60 Tage) eingeschränkt sichtbar; danach und an fremder Stelle nicht (ADR 0061)."""
    import datetime as dt

    from django.utils import timezone

    from apps.kunden.models import Gruppenzeit, KundenEinstellungen, Kundengruppe

    mitte, nord = stellen
    heute = timezone.localdate()
    g_mitte = Kundengruppe.objects.get(name="Montag Mitte")
    g_nord = Kundengruppe.objects.get(name="Dienstag Nord")
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])

    def ausgeschieden(nummer, gruppe, vor_tagen):
        h = Haushalt.objects.create(kundennummer=nummer, status=Haushalt.Status.BEENDET)
        Gruppenzeit.objects.create(
            kundennummer=nummer, kundengruppe=gruppe, gruppe_name=gruppe.name,
            von=heute - dt.timedelta(days=300), bis=heute - dt.timedelta(days=vor_tagen),
        )  # fmt: skip
        return h

    weg = ausgeschieden("400", g_mitte, 10)  # vor 10 Tagen an „Mitte"
    alt = ausgeschieden("401", g_mitte, 100)  # vor 100 Tagen an „Mitte"
    fremd = ausgeschieden("402", g_nord, 5)  # vor 5 Tagen, aber an „Nord"

    def in_liste(h):
        return zugang.filtern(Haushalt.objects, b).filter(pk=h.pk).exists()

    # In der Nachfrist an der eigenen Stelle: direkt aufrufbar (kein Sperrgrund) …
    assert zugang.sperrgrund(b, weg) == ""
    # … aber in Listen tauchen Ausgeschiedene nicht auf.
    assert not in_liste(weg) and not in_liste(alt) and not in_liste(fremd)
    # Zu lange her: nicht mehr aufrufbar.
    assert "keiner Kundengruppe zugeordnet" in zugang.sperrgrund(b, alt)
    # Fremde Ausgabestelle: nicht aufrufbar.
    assert zugang.sperrgrund(b, fremd) != ""

    # Nachfrist auf 0: sofort auch nicht mehr aufrufbar wie bisher.
    e = KundenEinstellungen.laden()
    e.nachfrist_sichtbar_tage = 0
    e.save()
    b = type(b).objects.get(pk=b.pk)  # Stellen-Zwischenspeicher zurücksetzen
    assert zugang.sperrgrund(b, weg) != ""


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


def test_einlass_fremd_zeigt_ampelgrund(anton, stellen):
    """Kunde einer anderen Ausgabestelle: der Einlass sieht jetzt, warum die Ampel rot wäre
    (z. B. abgelaufener Ausweis), ohne dass ein Zugriff protokolliert wird."""
    import datetime as dt

    h200 = Haushalt.objects.get(kundennummer="200")
    h200.ausweis_gueltig_bis = dt.date(2000, 1, 1)
    h200.save()
    seite = anton.get(reverse("ausgabe:empfang"), {"nummer": "200"}, **HX).content.decode()
    assert "Dieser Kunde gehört nicht zu Ihrer Ausgabestelle" in seite
    assert "wäre die Ampel rot" in seite and "Ausweis abgelaufen" in seite
    assert "Probe200" not in seite  # weiterhin nicht die ganze Karte
    assert not Zugriff.objects.filter(kundennummer="200").exists()  # weiterhin kein Zugriff


def test_kundenliste_der_gewaehlten_stelle(admin_client, admin, stellen, benutzer_mit_rolle,
                                           anmelden):  # fmt: skip
    """Wer alle Ausgabestellen sieht, bekommt unter „Ausgabestelle → Kundenliste“ nur die Kunden
    der oben im Menü gewählten Ausgabestelle – so wie die Ausgabestelle sie sieht."""
    from apps.ausgabe import stelle as stelle_wahl

    mitte, nord = stellen
    url, ziel = reverse("kunden:stellenliste"), reverse("kunden:uebersicht")

    def nummern(antwort):
        return sorted(h.kundennummer for h in antwort.context["seite"])

    def menue(benutzer):
        from django.test import RequestFactory

        from apps.core.menue import menue as bauen

        anfrage = RequestFactory().get("/")
        anfrage.user = type(benutzer).objects.get(pk=benutzer.pk)
        return [e for b in bauen(anfrage) for e in b.get("eintraege", [])]

    # Menü: beim Admin unter „Ausgabestelle“ zusätzlich die Kundenliste der gewählten Stelle
    eintraege = menue(admin)
    assert [e["titel"] for e in eintraege if e["url"] == url] == ["Kundenliste"]
    assert [e["titel"] for e in eintraege if e["url"] == ziel] == ["Kunden einsehen"]
    # ohne gewählte Ausgabestelle: Hinweis und die ganze Liste
    antwort = admin_client.get(url, follow=True)
    assert "eine Ausgabestelle wählen" in antwort.content.decode()
    assert nummern(admin_client.get(ziel, {"tag": ""})) == ["100", "200", "300"]
    # mit gewählter Ausgabestelle: nur deren Kunden, der Filter steht in der Leiste
    stelle_wahl.waehlen(admin, mitte.pk)
    antwort = admin_client.get(url)
    assert antwort.status_code == 302 and "stelle=gewaehlt" in antwort["Location"]
    antwort = admin_client.get(ziel, {"stelle": "gewaehlt", "tag": ""})
    assert nummern(antwort) == ["100"]
    seite = antwort.content.decode()
    assert '<option value="gewaehlt" selected>nur Mitte</option>' in seite
    assert "Montag Mitte" in seite and "Dienstag Nord" not in seite  # nur deren Kundengruppen
    assert "stelle=gewaehlt" in antwort.context["abfrage"]  # bleibt beim Sortieren und Blättern
    # Die Liste folgt der Auswahl oben im Menü
    stelle_wahl.waehlen(admin, nord.pk)
    assert nummern(admin_client.get(ziel, {"stelle": "gewaehlt", "tag": ""})) == ["200"]
    # Gemerkte Filter gelten weiter, die Kundengruppe (einer anderen Stelle) nicht
    admin.refresh_from_db()
    admin.listen_filter = {"kunden": "status=aktiv&gruppe=99"}
    admin.save()
    ort = admin_client.get(url)["Location"]
    assert "status=aktiv" in ort and "gruppe" not in ort and "stelle=gewaehlt" in ort
    # Konten einer Ausgabestelle: Menü wie bisher, die Angabe ändert an ihrer Liste nichts
    from django.test import Client

    konto = benutzer_mit_rolle("anton", rollen.AUSGABE)
    konto.ausgabestellen.set([mitte])
    anton = anmelden(Client(), konto)
    assert not [e for e in menue(konto) if e["url"] == url]
    assert [e["titel"] for e in menue(konto) if e["url"] == ziel] == ["Kundenliste"]
    assert nummern(anton.get(ziel, {"stelle": "gewaehlt", "tag": ""})) == ["100"]
    assert anton.get(url)["Location"] == ziel
