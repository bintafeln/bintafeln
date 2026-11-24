# ruff: noqa: F811 (Fixtures aus test_touren_zusatz)
"""Modul Touren: Neuer Stopp vom Büro – Push-Nachricht und roter Brief (ADR 0159).
Alle Daten sind erfunden."""

import datetime as dt
import json

import pytest
from django.urls import reverse

from apps.core import push
from apps.touren import heuler, zusatz
from apps.touren.models import Fahrt, Zusatzstopp
from tests.test_aufruf_handy import _browser, _entschluesseln
from tests.test_touren_zusatz import lage, module_an, station  # noqa: F401 (Fixtures)

pytestmark = pytest.mark.django_db
ADRESSE = "https://fcm.googleapis.com/fcm/send/"


@pytest.fixture
def handys(lage, monkeypatch):
    """Fritz und Klaus haben Nachrichten auf dem Handy eingeschaltet; ``gesendet`` sammelt, was an
    wen ginge (entschlüsselt wie im Browser)."""
    privat, p256dh, auth = _browser()
    push.abonnieren(lage["fritz"], ADRESSE + "fritz", p256dh, auth)
    push.abonnieren(lage["klaus"], ADRESSE + "klaus", p256dh, auth)
    gesendet = []

    def _senden(adresse, daten, kopf):
        klar = json.loads(_entschluesseln(daten, privat, p256dh, auth))
        gesendet.append((adresse.rsplit("/", 1)[1], klar))
        return 201

    monkeypatch.setattr(push, "_senden", _senden)
    monkeypatch.setattr(push, "_im_hintergrund", lambda fn: fn())
    return gesendet


def fahrt_anlegen(tour, datum):
    """Die Mannschaft hat „Fahrt beginnen“ getippt (ohne Fahrzeug und Regeln, nur der Eintrag)."""
    from django.utils import timezone

    return Fahrt.objects.create(
        tour=tour, tour_name=tour.name, datum=datum, km_start=1000, begonnen_am=timezone.now()
    )


@pytest.fixture
def unterwegs(lage):
    """Beide Touren von heute sind unterwegs – erst dann gibt es Brief und Push."""
    return [fahrt_anlegen(lage[t], lage["heute"]) for t in ("nord", "sued")]


def test_buero_fuegt_ein_mannschaft_bekommt_nachricht(
    lage,
    handys,
    unterwegs,
    django_capture_on_commit_callbacks,
):
    nord, heute = lage["nord"], lage["heute"]
    with django_capture_on_commit_callbacks(execute=True):
        z = zusatz.einfuegen(nord, heute, lage["buero"], station(20, name="Hofladen"), "2 Paletten")
    assert z.vom_buero and z.gesehen_am is None
    assert [wer for wer, _ in handys] == ["fritz"]  # nur die Mannschaft der Nordtour
    nachricht = handys[0][1]
    assert nachricht["titel"] == "Neuer Stopp: Nordtour"
    assert nachricht["text"] == "Hofladen, Musterweg 20, 12345 Musterstadt\n2 Paletten"
    assert nachricht["link"] == f"{reverse('touren:fahren', args=[nord.pk])}?tag={heute:%Y-%m-%d}"
    assert nachricht["kennung"] == f"stopp-{z.pk}"


def test_eigener_stopp_und_stopp_fuer_morgen_ohne_nachricht(
    lage,
    handys,
    unterwegs,
    django_capture_on_commit_callbacks,
):
    nord, heute = lage["nord"], lage["heute"]
    with django_capture_on_commit_callbacks(execute=True):
        selbst = zusatz.einfuegen(nord, heute, lage["fritz"], station(20))
    assert not selbst.vom_buero and handys == []
    assert heuler.offene(lage["fritz"]) == []
    # das Büro plant für morgen: keine Nachricht heute, der Brief erscheint am Tag selbst
    nord.datum = heute + dt.timedelta(days=1)
    nord.save()
    with django_capture_on_commit_callbacks(execute=True):
        morgen = zusatz.einfuegen(nord, nord.datum, lage["buero"], station(21))
    assert morgen.vom_buero and handys == []
    assert heuler.offene(lage["fritz"]) == []
    # am Tag selbst erst, wenn die Fahrt begonnen hat
    assert heuler.offene(lage["fritz"], nord.datum) == []
    fahrt_anlegen(nord, nord.datum)
    assert heuler.offene(lage["fritz"], nord.datum) == [morgen]


def test_ohne_eingeschaltetes_handy_geht_nichts_schief(
    lage, unterwegs, django_capture_on_commit_callbacks
):
    with django_capture_on_commit_callbacks(execute=True):
        z = zusatz.einfuegen(lage["nord"], lage["heute"], lage["buero"], station(20))
    assert heuler.offene(lage["fritz"]) == [z]


def test_roter_brief_bis_jemand_aus_der_mannschaft_bestaetigt(client, anmelden, lage, unterwegs):
    nord, heute = lage["nord"], lage["heute"]
    erster = zusatz.einfuegen(nord, heute, lage["buero"], station(20, name="Hofladen"), "klingeln")
    zusatz.einfuegen(nord, heute, lage["buero"], station(21, name="Lager"))
    stand = reverse("touren:heuler")
    # Klaus fährt die Südtour: kein Brief, und bestätigen kann er den Stopp nicht
    anmelden(client, lage["klaus"])
    assert "heuler-brief" not in client.get(stand).content.decode()
    antwort = client.post(reverse("touren:heuler_gesehen", args=[erster.pk]))
    assert antwort.status_code == 302 and Zusatzstopp.objects.get(pk=erster.pk).gesehen_am is None
    # Fritz: Kopfzeile fragt nach, der älteste offene Stopp steht im Brief
    anmelden(client, lage["fritz"])
    assert stand in client.get(reverse("core:start")).content.decode()
    brief = client.get(stand).content.decode()
    assert "heuler-brief" in brief and "Hofladen" in brief and "klingeln" in brief
    assert "Neuer Stopp für die Tour Nordtour" in brief and "danach noch 1 weiterer" in brief
    antwort = client.post(reverse("touren:heuler_gesehen", args=[erster.pk]))
    assert antwort.url == f"{heuler.adresse(erster)}#zusatz-{erster.pk}"
    erster.refresh_from_db()
    assert erster.gesehen_am is not None and erster.gesehen_von_name == "fritz"
    # der nächste Stopp kommt dran; ein zweites Bestätigen ändert nichts mehr
    brief = client.get(stand).content.decode()
    assert "Lager" in brief and "Hofladen" not in brief and "weitere" not in brief
    wann = erster.gesehen_am
    client.post(reverse("touren:heuler_gesehen", args=[erster.pk]))
    assert Zusatzstopp.objects.get(pk=erster.pk).gesehen_am == wann
    # das Büro sieht an der Tour, was gesehen ist
    anmelden(client, lage["buero"])
    seite = client.get(heuler.adresse(erster)).content.decode()
    assert "gesehen" in seite and "von fritz" in seite
    assert "von der Mannschaft noch nicht gesehen" in seite


def test_kopfzeile_fragt_nur_mit_recht(client, anmelden, benutzer_mit_rolle, lage):
    from apps.konten import rollen

    anmelden(client, benutzer_mit_rolle("erna", rollen.AUSGABE))
    assert reverse("touren:heuler") not in client.get(reverse("core:start")).content.decode()
    assert client.get(reverse("touren:heuler")).status_code == 403


def test_brief_und_push_erst_nach_fahrtbeginn(
    client, anmelden, lage, handys, django_user_model, django_capture_on_commit_callbacks
):
    """Fügt das Büro den Stopp ein, bevor die Mannschaft „Fahrt beginnen“ getippt hat, wartet er
    still: kein Push, kein roter Brief. Mit dem Beginn der Fahrt kommt beides."""
    from apps.touren import fahrten

    nord, heute = lage["nord"], lage["heute"]
    with django_capture_on_commit_callbacks(execute=True):
        stopp = zusatz.einfuegen(nord, heute, lage["buero"], station(40, name="Hofladen"))
    assert stopp.vom_buero and handys == []
    assert heuler.offene(lage["fritz"]) == [] and not heuler.unterwegs(nord, heute)
    anmelden(client, lage["fritz"])
    assert "heuler-brief" not in client.get(reverse("touren:heuler")).content.decode()
    # in der Tour steht der Stopp trotzdem schon
    assert "Hofladen" in client.get(reverse("touren:fahren", args=[nord.pk])).content.decode()
    with django_capture_on_commit_callbacks(execute=True):
        fahrten.beginnen(nord, lage["fritz"], "1000")
    assert [wer for wer, _ in handys] == ["fritz"]
    assert handys[0][1]["titel"] == "Neuer Stopp: Nordtour"
    brief = client.get(reverse("touren:heuler")).content.decode()
    assert "heuler-brief" in brief and "Hofladen" in brief
    # die andere Tour ist nicht unterwegs: Klaus sieht weiter nichts
    assert heuler.offene(lage["klaus"]) == []
    # schon bestätigte Stopps werden beim Beginn nicht nachgeholt
    heuler.gesehen(stopp, lage["fritz"])
    handys.clear()
    with django_capture_on_commit_callbacks(execute=True):
        heuler.nachholen(nord, heute)
    assert handys == []
