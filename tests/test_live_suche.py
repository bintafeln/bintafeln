"""Suchfelder suchen schon beim Tippen (ab 2 Zeichen) und tauschen nur die Trefferliste aus."""

import pytest
from django.urls import reverse

from apps.core.models import TafelEinstellungen

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def warteliste_an():
    t = TafelEinstellungen.laden()
    t.module = ["warteliste"]
    t.save()


@pytest.mark.parametrize(
    "seite",
    ["spenden:liste", "mitglieder:liste", "adressen:liste", "antraege:liste", "warteliste:liste",
     "kunden:zugriffe", "core:suche"],
)  # fmt: skip
def test_suchfelder_suchen_beim_tippen(admin_client, seite):
    html = admin_client.get(reverse(seite)).content.decode()
    assert 'id="ergebnis"' in html and 'hx-select="#ergebnis"' in html
    assert 'hx-trigger="input[this.value.trim().length >= ' in html
    assert f'hx-get="{reverse(seite)}"' in html


def test_trefferbereich_kommt_mit_der_ganzen_seite(admin_client):
    from apps.adressen.models import Adresse

    Adresse.objects.create(nachname="Musterfrau", vorname="Erika")
    Adresse.objects.create(nachname="Beispiel", vorname="Max")
    html = admin_client.get(reverse("adressen:liste"), {"q": "Mu"},
                            HTTP_HX_REQUEST="true").content.decode()  # fmt: skip
    ergebnis = html[html.index('id="ergebnis"') :]
    assert "Musterfrau" in ergebnis and "Beispiel" not in ergebnis


def test_suchseite_beim_tippen_ganze_seite_ohne_sprung(admin_client):
    url = reverse("core:suche")
    html = admin_client.get(url, {"q": "Kunden"}, HTTP_HX_REQUEST="true").content.decode()
    assert 'id="ergebnis"' in html  # nicht die kurze Liste des Seitenkopfs
    kurz = admin_client.get(url, {"q": "Kunden"}, HTTP_HX_REQUEST="true",
                            HTTP_HX_TARGET="kopf-suche-liste").content.decode()  # fmt: skip
    assert 'id="ergebnis"' not in kurz and "suche-liste" in kurz


def test_handbuch_zeigt_treffer_unter_dem_feld(admin_client):
    html = admin_client.get(reverse("core:hilfe")).content.decode()
    assert 'hx-target="#handbuch-suche-liste"' in html and 'id="handbuch-suche-liste"' in html
    kurz = admin_client.get(reverse("core:suche"), {"q": "Ampel", "nur": "hilfe"},
                            HTTP_HX_REQUEST="true",
                            HTTP_HX_TARGET="handbuch-suche-liste").content.decode()  # fmt: skip
    assert "suche-liste" in kurz
