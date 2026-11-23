"""Abrechnung: Monat als MMJJ eintippen (Feld zwischen Vormonat und Folgemonat)."""

import pytest
from django.urls import reverse

from tests.e2e.test_hilfe_bilder_module import _module, oeffnen

pytestmark = pytest.mark.e2e


def test_monat_als_mmjj_eintippen(angemeldet, admin, muster):
    _module("abrechnung")
    seite = oeffnen(angemeldet, admin, reverse("abrechnung:uebersicht") + "?monat=0127")
    feld = seite.locator("#abr-monat")
    assert feld.input_value() == "0127"
    # Alles in der Leiste ist gleich hoch und nichts läuft waagerecht über
    hoehen = {round(e.bounding_box()["height"]) for e in seite.locator(
        ".monatsleiste .knopf, .monatsleiste input[type=text]").all()}  # fmt: skip
    assert len(hoehen) == 1, hoehen
    leiste = seite.locator(".monatsleiste")
    assert leiste.evaluate("e => e.scrollWidth <= e.clientWidth")
    seite.get_by_role("link", name="← Vormonat").click()
    seite.wait_for_url("**monat=2026-12**")
    assert seite.locator("#abr-monat").input_value() == "1226"
    feld = seite.locator("#abr-monat")
    feld.fill("0327")
    feld.press("Tab")
    seite.wait_for_url("**monat=0327**")
    assert "Abrechnungen 0327" in seite.content()
    feld = seite.locator("#abr-monat")
    feld.fill("1399")
    feld.press("Enter")
    seite.wait_for_url("**monat=1399**")
    assert "ist kein Monat" in seite.content() and "Abrechnungen 0327" in seite.content()
