"""Das „?“ oben rechts führt zur passenden Hilfe-Seite (ADR 0038). Erfundene Daten."""

import pytest
from django.urls import reverse

from apps.core import hilfe

pytestmark = pytest.mark.django_db


def test_kennung_fuer_seite_app_und_fallback():
    assert hilfe.kennung_fuer("ausgabe:nachtragen") == "nachtragen"
    assert hilfe.kennung_fuer("ausgabe:empfang") == "einlass"
    assert hilfe.kennung_fuer("spenden:bestaetigungen") == "zuwendungsbestaetigungen"
    # Unbekannte Adresse derselben App → Standardkapitel der App
    assert hilfe.kennung_fuer("spenden:neu", "spenden") == "spenden"
    # Ganz unbekannt → leer (führt zur Handbuch-Übersicht)
    assert hilfe.kennung_fuer("foo:bar", "foo") == ""


def test_zugeordnete_kennungen_sind_echte_kapitel():
    vorhanden = {k.kennung for k in hilfe.alle_kapitel()}
    zugeordnet = set(hilfe._SEITE.values()) | set(hilfe._APP.values())
    fehlen = zugeordnet - vorhanden
    assert not fehlen, fehlen


def test_fragezeichen_verlinkt_passende_seite(admin_client):
    seite = admin_client.get(reverse("kunden:uebersicht")).content.decode()
    ziel = reverse("core:hilfe") + "#kunden-finden"
    assert 'class="hilfe-knopf"' in seite and f'href="{ziel}"' in seite
