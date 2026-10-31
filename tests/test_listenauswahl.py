"""Auswahlkästchen in Listen: Export nur der angehakten Zeilen. Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core import listenauswahl

pytestmark = pytest.mark.django_db


def test_filtern():
    a = Adresse.objects.create(nachname="Erste")
    Adresse.objects.create(nachname="Zweite")
    anfrage = RequestFactory().get("/", {"id": [str(a.pk), "x"]})
    assert list(listenauswahl.filtern(anfrage, Adresse.objects.all())) == [a]
    assert listenauswahl.filtern(RequestFactory().get("/"), Adresse.objects.all()).count() == 2


def test_adressen_spenden_mitglieder_antraege(admin_client):
    from apps.antraege.models import Antrag
    from apps.mitglieder.models import Mitglied
    from apps.spenden.models import Spende

    a = Adresse.objects.create(nachname="Erste", ort="Musterstadt")
    b = Adresse.objects.create(nachname="Zweite", ort="Musterstadt")
    seite = admin_client.get(reverse("adressen:liste")).content.decode()
    assert '<form id="auswahl" method="get" action=""' in seite
    assert 'name="aktion" value="csv"' in seite and 'name="aktion" value="pdf"' in seite
    assert f'name="id" value="{a.pk}" form="auswahl"' in seite
    text = admin_client.get(
        reverse("adressen:liste"), {"aktion": "csv", "id": a.pk}
    ).content.decode()
    assert "Erste" in text and "Zweite" not in text
    tag = dt.date(2026, 3, 1)
    s1 = Spende.objects.create(adresse=a, datum=tag, betrag=Decimal("10"))
    Spende.objects.create(adresse=b, datum=tag, betrag=Decimal("20"))
    text = admin_client.get(reverse("spenden:liste"), {"jahr": "2026", "aktion": "csv",
                                                       "id": s1.pk}).content.decode()  # fmt: skip
    assert "10,00" in text and "20,00" not in text
    m = Mitglied.objects.create(adresse=a, nummer="M1", eintritt=tag)
    Mitglied.objects.create(adresse=b, nummer="M2", eintritt=tag)
    text = admin_client.get(
        reverse("mitglieder:liste"), {"aktion": "csv", "id": m.pk}
    ).content.decode()
    assert "M1" in text and "M2" not in text
    seite = admin_client.get(reverse("antraege:liste")).content.decode()
    assert 'action="/antraege/export/"' in seite and 'data-alle="id"' in seite
    eins = Antrag.objects.create(nachname="Antragseins", vorname="Erika")
    Antrag.objects.create(nachname="Antragszwei", vorname="Max")
    text = admin_client.get(reverse("antraege:export"), {"id": eins.pk}).content.decode()
    assert "Antragseins" in text and "Antragszwei" not in text
