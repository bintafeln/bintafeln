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


def test_hintergrund_und_formulare_merken_sich_kein_ziel(client, admin):
    """Nach dem Anmelden darf niemand auf einem Seitenbaustein (z. B. der Eule in der Kopfzeile)
    oder auf einer Adresse landen, die nur Eingaben annimmt – dann lieber auf der Startseite."""
    anmelden = reverse("konten:anmelden")
    kopf = reverse("kunden:post_kopf")
    # htmx-Abfrage im Hintergrund, nachdem die Sitzung weg ist
    assert client.get(kopf, HTTP_HX_REQUEST="true")["HX-Redirect"] == anmelden
    # fetch() aus JavaScript und ein eingebettetes PDF
    assert client.get(kopf, HTTP_SEC_FETCH_DEST="empty")["Location"] == anmelden
    assert client.get(kopf, HTTP_SEC_FETCH_DEST="iframe")["Location"] == anmelden
    # abgeschicktes Formular
    assert client.post(reverse("kunden:uebersicht"), {"x": "1"})["Location"] == anmelden
    # Eine ganze Seite merkt sich weiter, wohin es nach dem Anmelden geht
    liste = reverse("kunden:uebersicht")
    for kopfzeilen in ({}, {"HTTP_SEC_FETCH_DEST": "document"}):
        assert client.get(liste, **kopfzeilen)["Location"] == f"{anmelden}?next={liste}"
