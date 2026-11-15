"""Abholungen bekommen immer eine Ausgabestelle, wenn der Haushalt eine Kundengruppe mit
Ausgabestelle hat. Alle Daten sind erfunden."""

import datetime as dt
import importlib
from decimal import Decimal

import pytest
from django.apps import apps

from apps.kunden.models import Abholung, Ausgabestelle, Haushalt, Kundengruppe

pytestmark = pytest.mark.django_db
TAG = dt.date(2026, 11, 10)


@pytest.fixture
def mitte():
    return Ausgabestelle.objects.create(name="Mitte")


def _haushalt(nummer, stelle=None):
    g = (
        Kundengruppe.objects.create(name=f"Gruppe {nummer}", ausgabestelle=stelle)
        if stelle
        else None
    )
    return Haushalt.objects.create(kundennummer=nummer, kundengruppe=g)


def test_ohne_ausgabestelle_gilt_die_der_kundengruppe(mitte):
    nord = Ausgabestelle.objects.create(name="Nord")
    h = _haushalt("101", mitte)
    assert Abholung.objects.create(haushalt=h, datum=TAG).ausgabestelle == mitte
    # eine angegebene Ausgabestelle bleibt
    assert Abholung.objects.create(haushalt=h, datum=TAG, ausgabestelle=nord).ausgabestelle == nord
    # ohne Kundengruppe bleibt sie leer
    assert Abholung.objects.create(haushalt=_haushalt("102"), datum=TAG).ausgabestelle is None


def test_uebernommene_besuche_bekommen_ausgabestelle(mitte):
    from apps.uebernahme import besuche_konto

    h = _haushalt("01294", mitte)
    h.kontostand = Decimal("0")
    h.save()
    csv = "Kundennummer;Letzter Besuch;Kontostand\n01294;10.11.2026;0,00 €\n".encode()
    besuche_konto.uebernehmen(besuche_konto.lesen(csv), "Büro")
    assert Abholung.objects.get(haushalt=h).ausgabestelle == mitte


def test_migration_fuellt_vorhandene_abholungen(mitte):
    h = _haushalt("104", mitte)
    ohne = _haushalt("105")
    a = Abholung.objects.create(haushalt=h, datum=TAG)
    b = Abholung.objects.create(haushalt=ohne, datum=TAG)
    Abholung.objects.update(ausgabestelle=None)  # Stand vor dem Update
    importlib.import_module("apps.kunden.migrations.0051_abholungen_ausgabestelle").zuordnen(
        apps, None
    )
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.ausgabestelle == mitte and b.ausgabestelle is None
