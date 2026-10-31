"""Läuft die Sitzung bei einem htmx-Aufruf ab, schickt bintafeln die ganze Seite zur Anmeldung
(HX-Redirect) statt die Anmeldeseite in einen Seitenbereich einzufügen. Erfundene Daten."""

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db


def test_htmx_bekommt_hx_redirect_statt_anmeldeseite(client, admin):
    antwort = client.get(reverse("kunden:uebersicht"), HTTP_HX_REQUEST="true")
    assert antwort.status_code == 204 and antwort.content == b""
    assert reverse("konten:anmelden") in antwort["HX-Redirect"]


def test_ohne_htmx_normaler_redirect(client, admin):
    antwort = client.get(reverse("kunden:uebersicht"))
    assert antwort.status_code == 302 and reverse("konten:anmelden") in antwort["Location"]
