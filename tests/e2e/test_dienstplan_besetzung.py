"""Feste Besetzung im Dienstplan: jede Auswahl speichert sofort, ohne Knopf."""

import pytest
from django.urls import reverse

from tests.e2e.test_hilfe_bilder_module import _dienstplan, _module, oeffnen

pytestmark = pytest.mark.e2e


def test_besetzung_speichert_sofort(angemeldet, admin, muster):
    from apps.dienstplan.models import Besetzung

    _module("dienstplan")
    stelle, _freitag, obst = _dienstplan()
    Besetzung.objects.filter(aufgabe=obst).delete()
    url = f"{reverse('dienstplan:stelle', args=[stelle.ausgabestelle_id])}?tag=Fr"
    seite = oeffnen(angemeldet, admin, url, breite=1200)
    feld = seite.locator(f"#h_{obst.pk}")
    assert not seite.get_by_role("button", name="Besetzung speichern").is_visible()
    wahl = feld.locator("option").nth(1).get_attribute("value")
    feld.select_option(wahl)
    seite.wait_for_selector(".autosave-ok")
    assert str(Besetzung.objects.get(aufgabe=obst).helfer_id) == wahl
