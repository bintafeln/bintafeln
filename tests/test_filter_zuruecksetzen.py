"""Überall, wo gefiltert oder gesucht wird, steht der Knopf „Zurücksetzen“."""

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse

from apps.core.models import TafelEinstellungen

# Papierkorb, Auswertungslisten und „Kundengruppe ändern“ zeigen ihren Filter nur mit Daten
SEITEN = [
    "kunden:uebersicht",
    "kunden:zugriffe",
    "statistik:uebersicht",
    "statistik:verband",
    "adressen:liste",
    "spenden:liste",
    "mitglieder:liste",
    "antraege:liste",
    "warteliste:streichungsliste",
    "wochenuebersicht:uebersicht",
    "tickets:liste",
    "core:dateien",
    "core:protokoll",
    "konten:anmeldeprotokoll",
    "konten:mitarbeitende",
    "ausgabe:kasse",
]


@pytest.fixture
def module_an(db):
    t = TafelEinstellungen.laden()
    t.module = ["warteliste", "wochenuebersicht", "tickets", "listen"]
    t.save()


@pytest.mark.parametrize("name", SEITEN)
def test_knopf_auf_jeder_filterseite(admin_client, module_an, name):
    seite = admin_client.get(reverse(name) + "?q=x")
    assert seite.status_code == 200
    inhalt = seite.content.decode()
    assert "filter-zuruecksetzen" in inhalt and ">Zurücksetzen</a>" in inhalt


def test_knopf_behaelt_nur_genannte_angaben():
    request = RequestFactory().get("/liste/", {"q": "mül", "sort": "name", "ansicht": "alle"})
    vorlage = Template('{% load liste %}{% filter_zuruecksetzen "ansicht" "sort" %}')
    html = vorlage.render(Context({"request": request}))
    assert 'href="/liste/?sort=name&amp;ansicht=alle"' in html and "q=" not in html
    ohne = Template("{% load liste %}{% filter_zuruecksetzen %}").render(
        Context({"request": request})
    )
    assert 'href="/liste/"' in ohne
