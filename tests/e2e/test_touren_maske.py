"""Tourenplanung: Bei einer Tour aus dem Fahrerplan gibt es keine eigenen Besetzungsfelder."""

import pytest
from django.urls import reverse
from playwright.sync_api import expect

from tests.e2e.test_hilfe_bilder_module import _module, oeffnen

pytestmark = pytest.mark.e2e


def test_plaetze_nur_bei_eigener_tour(angemeldet, admin, muster):
    from apps.core import demo_daten
    from apps.fahrdienst import beispiel
    from apps.touren.models import Tour

    _module("touren", "fahrdienst")
    beispiel.anlegen(seed=1)
    demo_daten.touren()
    tour = Tour.objects.filter(fahrdienst_tour__isnull=False, datum__isnull=True).first()
    seite = oeffnen(angemeldet, admin, reverse("touren:tour", args=[tour.pk]))
    # Besetzung aus dem Fahrerplan steht oben; die eigenen Plätze samt Beschriftung fehlen
    expect(seite.locator("#besetzung")).to_be_visible()
    for feld in ("fahrer", "beifahrer", "beifahrer2", "gast"):
        expect(seite.locator(f"#id_{feld}")).to_be_hidden()
        expect(seite.locator(f"label[for=id_{feld}]")).to_be_hidden()
    expect(seite.locator("#id_name")).to_be_visible()
    # Auf „eigene Tour“ umgestellt: Die Felder erscheinen
    seite.locator("#id_fahrdienst_tour").select_option("")
    for feld in ("fahrer", "beifahrer", "beifahrer2", "gast"):
        expect(seite.locator(f"#id_{feld}")).to_be_visible()
        expect(seite.locator(f"label[for=id_{feld}]")).to_be_visible()
