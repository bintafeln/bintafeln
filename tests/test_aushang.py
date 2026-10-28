"""Modul Aushang-Monitore (ADR 0080). Alle Namen sind erfunden (Beispieldaten der Module)."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.aushang import anzeige
from apps.aushang.models import Aushang, AushangSeite
from apps.core.models import PapierkorbEintrag, TafelEinstellungen
from apps.dienstplan import beispiel as dp_beispiel
from apps.dienstplan.models import Helfer
from apps.fahrdienst import beispiel as fd_beispiel
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle

pytestmark = pytest.mark.django_db
MITTWOCH = dt.date(2026, 11, 11)
LISTE = reverse("aushang:liste")


@pytest.fixture(autouse=True)
def module_an():
    t = TafelEinstellungen.laden()
    t.module = ["aushang", "dienstplan", "fahrdienst"]
    t.bundesland = "NW"
    t.save()


@pytest.fixture
def heute(monkeypatch):
    """Mittwoch, 11.11.2026, 10 Uhr."""
    jetzt = timezone.make_aware(dt.datetime(2026, 11, 11, 10, 0))
    monkeypatch.setattr("django.utils.timezone.localtime", lambda *a: jetzt)
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a: MITTWOCH)
    return MITTWOCH


@pytest.fixture
def plaene():
    dp_beispiel.anlegen(seed=1)
    fd_beispiel.anlegen(seed=1)
    return Ausgabestelle.objects.get(name=dp_beispiel.STELLE)


def test_zeitraum_ab_heute_bis_monatsende():
    assert anzeige.zeitraum(MITTWOCH, 1) == (MITTWOCH, dt.date(2026, 11, 30))
    assert anzeige.zeitraum(MITTWOCH, 2) == (MITTWOCH, dt.date(2026, 12, 31))
    assert anzeige.zeitraum(dt.date(2026, 12, 31), 2) == (
        dt.date(2026, 12, 31),
        dt.date(2027, 1, 31),
    )


def test_einrichten_seiten_reihenfolge_und_link(plaene, admin_client):
    antwort = admin_client.post(LISTE, {"name": "Monitor Fahrerraum"})
    aushang = Aushang.objects.get()
    assert antwort.url == reverse("aushang:bearbeiten", args=[aushang.pk])
    seite = reverse("aushang:bearbeiten", args=[aushang.pk])
    html = admin_client.get(seite).content.decode()
    assert f"dienstplan:{plaene.pk}" in html and 'value="fahrdienst:"' in html
    admin_client.post(seite, {"aktion": "seite", "seite": f"dienstplan:{plaene.pk}", "monate": 1})
    admin_client.post(seite, {"aktion": "seite", "seite": "fahrdienst:", "monate": 2})
    assert [(s.art, s.wert, s.monate) for s in aushang.seiten.all()] == [
        ("dienstplan", str(plaene.pk), 1), ("fahrdienst", "", 2)]  # fmt: skip
    html = admin_client.get(seite).content.decode()
    assert f"Dienstplan einer Ausgabestelle: {dp_beispiel.STELLE}" in html
    fahrer = aushang.seiten.get(art="fahrdienst")
    admin_client.post(seite, {"aktion": "hoch", "seite": fahrer.pk})
    assert [s.art for s in aushang.seiten.all()] == ["fahrdienst", "dienstplan"]
    admin_client.post(seite, {"aktion": "runter", "seite": fahrer.pk})
    assert [s.art for s in aushang.seiten.all()] == ["dienstplan", "fahrdienst"]
    assert admin_client.post(seite, {"aktion": "hoch", "seite": 999999}).status_code == 404

    admin_client.post(seite, {"aktion": "einstellungen", "name": "Monitor Flur", "aktiv": "on",
                              "nebeneinander": 2, "sekunden": 30})  # fmt: skip
    aushang.refresh_from_db()
    assert (aushang.name, aushang.nebeneinander, aushang.sekunden) == ("Monitor Flur", 2, 30)
    assert admin_client.post(seite, {"aktion": "einstellungen", "name": "x", "nebeneinander": 1,
                                     "sekunden": 2}).status_code == 200  # fmt: skip
    alt = aushang.schluessel
    admin_client.post(seite, {"aktion": "schluessel"})
    aushang.refresh_from_db()
    assert aushang.schluessel != alt
    assert Client().get(reverse("aushang:anzeige", args=[alt])).status_code == 404

    admin_client.post(seite, {"aktion": "entfernen", "seite": fahrer.pk})
    assert [s.art for s in aushang.seiten.all()] == ["dienstplan"]
    admin_client.post(reverse("aushang:loeschen", args=[aushang.pk]))
    assert not Aushang.objects.exists() and not AushangSeite.objects.exists()
    assert PapierkorbEintrag.objects.filter(bezeichnung="Monitor Flur").exists()
    assert "Aushang-Monitore" in admin_client.get(reverse("core:start")).content.decode()


def test_monitor_ohne_anmeldung_nur_namen(plaene, heute, admin):
    aushang = Aushang.objects.create(name="Monitor Fahrerraum")
    AushangSeite.objects.create(aushang=aushang, art="dienstplan", wert=str(plaene.pk), monate=1)
    AushangSeite.objects.create(aushang=aushang, art="fahrdienst", monate=2, reihenfolge=1)
    antwort = Client().get(reverse("aushang:anzeige", args=[aushang.schluessel]))
    html = antwort.content.decode()
    assert antwort.status_code == 200
    # Dienstplan: je Ausgabetag (Mo, Mi, Fr) eine Seite, ab heute; Fahrerplan je Monat
    titel = [t for t, _ in anzeige.folien(aushang, heute)]
    tage = ("Montag", "Mittwoch", "Freitag")
    assert titel == [f"Dienstplan {dp_beispiel.STELLE} · {t}" for t in tage] + [
        "Fahrerplan November 2026", "Fahrerplan Dezember 2026"]  # fmt: skip
    assert "11.11." in html and "09.11." not in html  # vergangene Tage fallen weg
    assert "Teamleitung:" in html and "Mittwoch, 11.11.2026" in html and "Stand 10:00 Uhr" in html
    helfer = Helfer.objects.filter(anmerkung=dp_beispiel.KENNUNG).first()
    assert helfer.name in html and helfer.telefon not in html and "0123 45" not in html
    assert 'class="knopf' not in html and "menue" not in html  # ganzseitig, ohne Menü
    assert "aushang.js" in html and 'data-sekunden="20"' in html

    aushang.aktiv = False
    aushang.save()
    url = reverse("aushang:anzeige", args=[aushang.schluessel])
    assert Client().get(url).status_code == 404
    assert Client().get(url, headers={"X-Aushang": "1"}).status_code == 204  # Monitor leert sich


def test_seiten_ausgeschalteter_module_fallen_weg(plaene, heute, admin_client):
    aushang = Aushang.objects.create(name="Monitor")
    AushangSeite.objects.create(aushang=aushang, art="fahrdienst", monate=1)
    t = TafelEinstellungen.laden()
    t.module = ["aushang", "dienstplan"]
    t.save()
    assert anzeige.folien(aushang, heute) == []
    html = Client().get(reverse("aushang:anzeige", args=[aushang.schluessel])).content.decode()
    assert "Zurzeit gibt es hier nichts anzuzeigen." in html
    html = admin_client.get(reverse("aushang:bearbeiten", args=[aushang.pk])).content.decode()
    assert "fahrdienst (Modul ausgeschaltet)" in html
    # Ganz ohne Modul Aushang: auch der Monitor ist weg
    t.module = ["dienstplan"]
    t.save()
    assert Client().get(reverse("aushang:anzeige", args=[aushang.schluessel])).status_code == 404


def test_unbekannte_stelle_zeigt_nichts(plaene, heute):
    aushang = Aushang.objects.create(name="Monitor")
    AushangSeite.objects.create(aushang=aushang, art="dienstplan", wert="999999")
    AushangSeite.objects.create(aushang=aushang, art="dienstplan", wert="x")
    assert anzeige.folien(aushang, heute) == []


def test_seiten_nur_mit_recht_den_plan_zu_planen(plaene, client, anmelden, benutzer_mit_rolle,
                                                 recht_geben, admin):  # fmt: skip
    recht_geben(rollen.FAHRER, "aushang.einrichten", "fahrdienst.planen")
    anmelden(client, benutzer_mit_rolle("max", rollen.FAHRER))
    aushang = Aushang.objects.create(name="Monitor")
    seite = reverse("aushang:bearbeiten", args=[aushang.pk])
    html = client.get(seite).content.decode()
    assert 'value="fahrdienst:"' in html and "dienstplan:" not in html
    antwort = client.post(
        seite, {"aktion": "seite", "seite": f"dienstplan:{plaene.pk}", "monate": 2}
    )
    assert antwort.status_code == 200 and not aushang.seiten.exists()


def test_ohne_moegliche_seiten_ein_hinweis(admin_client):
    t = TafelEinstellungen.laden()
    t.module = ["aushang"]
    t.save()
    aushang = Aushang.objects.create(name="Monitor")
    html = admin_client.get(reverse("aushang:bearbeiten", args=[aushang.pk])).content.decode()
    assert "Sie können keine Seiten hinzufügen" in html
    assert "Monitor" in admin_client.get(LISTE).content.decode()
