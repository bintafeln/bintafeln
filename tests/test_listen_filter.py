"""Alle Übersichtslisten nutzen dieselbe kompakte Filterzeile wie die Kundenliste
(filter-kompakt mit filter-feld), nicht mehr die alte inline-Variante (class="filter")."""

import pytest
from django.urls import reverse

from apps.core.models import TafelEinstellungen

pytestmark = pytest.mark.django_db


def _ohne_alten_filter(seite: str):
    assert "filter-kompakt" in seite
    assert 'class="filter liste-filter"' not in seite
    assert 'class="filter"' not in seite


def test_antraege_mitglieder_spenden_kompakte_filterzeile(admin_client):
    for name in ("antraege:liste", "mitglieder:liste", "spenden:liste"):
        seite = admin_client.get(reverse(name)).content.decode()
        _ohne_alten_filter(seite)
        assert "filter-feld" in seite


def test_warteliste_kompakte_filterzeile(admin_client):
    t = TafelEinstellungen.laden()
    t.module = ["warteliste"]
    t.save()
    seite = admin_client.get(reverse("warteliste:liste")).content.decode()
    _ohne_alten_filter(seite)
    assert "filter-feld" in seite
