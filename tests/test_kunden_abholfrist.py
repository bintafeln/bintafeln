import datetime as dt

import pytest
from auditlog.models import LogEntry
from django.urls import reverse

from apps.kunden.models import (
    Abholung,
    Ausnahme,
    Haushalt,
    KundenEinstellungen,
    abgelaufene_abholungen_loeschen,
    abholfrist_beginn,
)

pytestmark = pytest.mark.django_db


def test_fristbeginn_vorgabe_drei_jahre():
    assert abholfrist_beginn(dt.date(2026, 10, 23)) == dt.date(2023, 10, 23)


def test_fristbeginn_am_29_februar():
    assert abholfrist_beginn(dt.date(2028, 2, 29)) == dt.date(2025, 2, 28)


def _haushalt_mit_abholdaten():
    h = Haushalt.objects.create(kundennummer="900")
    for datum in (dt.date(2023, 10, 22), dt.date(2023, 10, 23)):
        Abholung.objects.create(haushalt=h, datum=datum)
        Ausnahme.objects.create(haushalt=h, datum=datum)
    return h


def test_abgelaufene_werden_ohne_protokolleintrag_geloescht():
    _haushalt_mit_abholdaten()
    assert abgelaufene_abholungen_loeschen(dt.date(2026, 10, 23)) == 2
    assert list(Abholung.objects.values_list("datum", flat=True)) == [dt.date(2023, 10, 23)]
    assert list(Ausnahme.objects.values_list("datum", flat=True)) == [dt.date(2023, 10, 23)]
    geloescht = LogEntry.objects.filter(action=LogEntry.Action.DELETE)
    assert not geloescht.filter(content_type__model__in=["abholung", "ausnahme"]).exists()


def test_kuerzere_frist_aus_einstellungen():
    _haushalt_mit_abholdaten()
    e = KundenEinstellungen.laden()
    e.abholungen_aufbewahren_jahre = 1
    e.save()
    assert abgelaufene_abholungen_loeschen(dt.date(2026, 10, 23)) == 4


def test_startseite_und_kundenuebersicht_loeschen_abgelaufene(admin_client):
    h = Haushalt.objects.create(kundennummer="901")
    Abholung.objects.create(haushalt=h, datum=dt.date(2000, 1, 1))
    admin_client.get(reverse("core:start"))
    assert not Abholung.objects.exists()
    Abholung.objects.create(haushalt=h, datum=dt.date(2000, 1, 1))
    antwort = admin_client.get(reverse("kunden:uebersicht"))
    assert "0 Abholungen" in antwort.content.decode()


def test_str():
    h = Haushalt.objects.create(kundennummer="902")
    assert str(Abholung(haushalt=h, datum=dt.date(2026, 5, 4))) == "Abholung am 04.05.2026"
    assert str(Ausnahme(haushalt=h, datum=dt.date(2026, 5, 4))) == "Ausnahme am 04.05.2026"
