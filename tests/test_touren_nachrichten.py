# ruff: noqa: F811 (Fixtures aus test_touren_zusatz und test_touren_heuler)
"""Modul Touren: Nachricht der Fahrdienstleitung an die Mannschaft (ADR 0168).
Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.touren import heuler, nachrichten, tourtag, zusatz
from apps.touren.models import Kurztext, Tour, Tournachricht
from tests.test_touren_heuler import handys  # noqa: F401 (Fixture)
from tests.test_touren_zusatz import lage, module_an, station  # noqa: F401 (Fixtures)

pytestmark = pytest.mark.django_db


@pytest.fixture
def buero(lage, anmelden):
    return anmelden(Client(), lage["buero"])


def test_kurztexte_sind_vorbelegt_und_pflegbar(buero):
    assert "Bitte im Büro anrufen" in nachrichten.kurztexte()  # Vorgabe aus der Migration
    seite = buero.get(reverse("touren:einrichten")).content.decode()
    assert 'id="kurztexte"' in seite and "Bitte im Büro anrufen" in seite
    anzahl = Kurztext.objects.count()
    daten = {"kurztexte": "1", "kt-TOTAL_FORMS": anzahl + 2, "kt-INITIAL_FORMS": anzahl}
    for nr, k in enumerate(Kurztext.objects.all()):
        daten |= {f"kt-{nr}-id": k.pk, f"kt-{nr}-text": k.text, f"kt-{nr}-reihenfolge": 5}
    daten |= {f"kt-{anzahl}-text": "Glätte – bitte vorsichtig fahren",
              f"kt-{anzahl}-reihenfolge": 1, f"kt-{anzahl}-aktiv": "on"}  # fmt: skip
    # die zweite leere Zeile kommt aus dem Browser so, wie sie angezeigt wird
    daten |= {f"kt-{anzahl + 1}-reihenfolge": 0, f"kt-{anzahl + 1}-aktiv": "on"}
    antwort = buero.post(reverse("touren:einrichten"), daten)
    assert antwort.status_code == 302, antwort.context["kurztexte"].errors
    # die alten sind jetzt aus (kein Häkchen), der neue steht zur Wahl
    assert nachrichten.kurztexte() == ["Glätte – bitte vorsichtig fahren"]


def test_nachricht_an_eine_tour(lage, handys, buero, anmelden, django_capture_on_commit_callbacks):
    nord, heute = lage["nord"], lage["heute"]
    seite = buero.get(reverse("touren:heute")).content.decode()
    assert "Nachricht an die Mannschaft" in seite and "alle, die heute fahren" in seite
    assert 'data-kurztext="Bitte im Büro anrufen"' in seite
    with django_capture_on_commit_callbacks(execute=True):
        antwort = buero.post(
            reverse("touren:nachricht_senden"),
            {"tour": nord.pk, "text": "  Bitte im   Büro anrufen "},
            follow=True,
        )
    n = Tournachricht.objects.get()
    assert (n.tour, n.datum, n.text, n.von_name) == (nord, heute, "Bitte im Büro anrufen", "bernd")
    assert "Nachricht an 1 Tour geschickt" in antwort.content.decode()
    assert '<span class="marke-warnung">noch nicht bestätigt' in antwort.content.decode()
    # Push nur an die Mannschaft dieser Tour
    assert [wer for wer, _ in handys] == ["fritz"]
    assert handys[0][1]["titel"] == "Nachricht: Nordtour"
    assert handys[0][1]["text"] == "Bitte im Büro anrufen"
    assert handys[0][1]["kennung"] == f"nachricht-{n.pk}"
    # Roter Brief bei Fritz, nicht bei Klaus; bestätigen darf nur die Mannschaft
    fritz, klaus = anmelden(Client(), lage["fritz"]), anmelden(Client(), lage["klaus"])
    stand = reverse("touren:heuler")
    brief = fritz.get(stand).content.decode()
    assert "heuler-brief" in brief and "Bitte im Büro anrufen" in brief
    assert f'data-schluessel="n{n.pk}"' in brief and "Gelesen" in brief
    assert "heuler-brief" not in klaus.get(stand).content.decode()
    gelesen = reverse("touren:nachricht_gesehen", args=[n.pk])
    assert klaus.post(gelesen).url == reverse("touren:heute")
    n.refresh_from_db()
    assert n.gesehen_am is None
    assert fritz.get(gelesen).status_code == 405
    assert fritz.post(gelesen).url == nachrichten.adresse(n)
    n.refresh_from_db()
    assert n.gesehen_am and n.gesehen_von_name == "fritz"
    assert "heuler-brief" not in fritz.get(stand).content.decode()
    # Die Fahrdienstleitung sieht, wer bestätigt hat
    seite = buero.get(reverse("touren:heute")).content.decode()
    assert "von fritz" in seite and '<span class="marke-warnung">noch nicht' not in seite
    # Fahrer sehen weder das Formular noch die Liste und dürfen nicht schicken
    eigene = fritz.get(reverse("touren:heute")).content.decode()
    assert "Nachricht an die Mannschaft" not in eigene
    assert fritz.post(reverse("touren:nachricht_senden"),
                      {"tour": nord.pk, "text": "x"}).status_code == 403  # fmt: skip


def test_nachricht_an_alle_und_reihenfolge_mit_neuem_stopp(
    lage, handys, buero, anmelden, django_capture_on_commit_callbacks
):
    nord, sued, heute = lage["nord"], lage["sued"], lage["heute"]
    Tour.objects.create(name="Morgen", datum=heute + dt.timedelta(days=1))  # fährt heute nicht
    leer = Tour.objects.create(name="Ohne Mannschaft", datum=heute)
    with django_capture_on_commit_callbacks(execute=True):
        antwort = buero.post(
            reverse("touren:nachricht_senden"),
            {"tour": "alle", "text": "Lager schließt um 12 Uhr"},
            follow=True,
        )
    assert {n.tour for n in Tournachricht.objects.all()} == {nord, sued, leer}
    assert sorted(wer for wer, _ in handys) == ["fritz", "klaus"]
    seite = antwort.content.decode()
    assert "Nachricht an 3 Touren geschickt" in seite
    assert "niemand mit Konto eingetragen" in seite and "Ohne Mannschaft" in seite
    # Kommt danach ein neuer Stopp vom Büro, zeigt der Brief zuerst das Ältere: die Nachricht
    zusatz.einfuegen(nord, heute, lage["buero"], station(30, name="Hofladen"))
    fritz = anmelden(Client(), lage["fritz"])
    brief = fritz.get(reverse("touren:heuler")).content.decode()
    assert "Lager schließt um 12 Uhr" in brief and "danach noch 1 weiterer" in brief
    n = Tournachricht.objects.get(tour=nord)
    fritz.post(reverse("touren:nachricht_gesehen", args=[n.pk]))
    brief = fritz.get(reverse("touren:heuler")).content.decode()
    assert "Hofladen" in brief and "Lager schließt" not in brief
    assert len(heuler.offene(lage["fritz"])) == 1 and nachrichten.offene(lage["fritz"]) == []


def test_fehler_und_grenzen(lage, buero):
    nord, heute = lage["nord"], lage["heute"]
    for daten in ({"tour": nord.pk, "text": "   "}, {"tour": "999999", "text": "Hallo"},
                  {"tour": "", "text": "Hallo"}):  # fmt: skip
        antwort = buero.post(reverse("touren:nachricht_senden"), daten, follow=True)
        assert "Bitte einen Text" in antwort.content.decode() or (
            "Heute fährt keine" in antwort.content.decode()
        )
    assert not Tournachricht.objects.exists()
    with pytest.raises(nachrichten.NachrichtFehler):
        nachrichten.senden([Tour.objects.create(name="Aus", datum=heute, aktiv=False)], "x",
                           lage["buero"])  # fmt: skip
    [n] = nachrichten.senden([nord], "x" * 400, lage["buero"])
    assert len(n.text) == 300
    # an einem anderen Tag: kein Formular, aber die Liste des Tages
    gestern = buero.get(
        reverse("touren:heute"), {"tag": f"{heute - dt.timedelta(days=1):%Y-%m-%d}"}
    )
    assert 'id="nachricht-text"' not in gestern.content.decode()
    # Tourtag zurücksetzen nimmt die Nachricht mit; alte werden gelöscht
    assert ("Nachricht an die Mannschaft", 1) in tourtag.inhalt(nord, heute)
    alt = Tournachricht.objects.create(tour=nord, datum=heute - dt.timedelta(days=31), text="alt")
    assert nachrichten.fristen_anwenden() == 1
    assert not Tournachricht.objects.filter(pk=alt.pk).exists() and Tournachricht.objects.exists()
    assert timezone.localdate() == heute
