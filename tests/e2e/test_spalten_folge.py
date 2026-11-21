"""Spalten im Menü „Spalten wählen“ mit den Pfeilen verschieben (static/js/spalten_folge.js)."""

import pytest
from playwright.sync_api import expect

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]


def test_spalten_verschieben(angemeldet, admin, live_server):
    from apps.adressen.models import Adresse

    Adresse.objects.create(art="person", vorname="Rita", nachname="Reihe", ort="Musterstadt")
    seite = angemeldet(admin)
    seite.goto(live_server.url + "/adressen/")
    kopf = seite.locator("table.tabelle thead th")
    expect(kopf.nth(2)).to_contain_text("Nachname")
    seite.locator("details.spalten-wahl summary").click()
    # „Ort“ zweimal nach vorn: vor „Anrede“ und „Straße“ … bis ganz nach vorn
    ort = seite.locator(".spalten-haken label", has_text="Ort")
    for _ in range(6):
        ort.get_by_role("button", name="Ort nach vorn").click()
    expect(seite.locator(".spalten-haken label").first).to_contain_text("Ort")
    assert ort.locator("input[type=checkbox]").is_checked()  # der Pfeil schaltet kein Häkchen um
    seite.get_by_role("button", name="Übernehmen").click()
    expect(kopf.nth(1)).to_contain_text("Ort")
    expect(seite.locator("table.tabelle tbody tr").first.locator("td").nth(1)).to_have_text(
        "Musterstadt"
    )
    # zurücksetzen stellt die übliche Reihenfolge wieder her
    seite.locator("details.spalten-wahl summary").click()
    seite.get_by_role("button", name="Reihenfolge zurücksetzen").click()
    expect(kopf.nth(2)).to_contain_text("Nachname")
