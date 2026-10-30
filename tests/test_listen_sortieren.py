"""Einheitliche Sortierung der Übersichtslisten (?sort=…) und der Spaltenkopf {% sortkopf %}.

Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.template import Context, Template
from django.test import RequestFactory
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core import listen
from apps.mitglieder.models import Mitglied

pytestmark = pytest.mark.django_db


def _sortkopf(get, titel="Name", schluessel="name", sort="", klasse=""):
    request = RequestFactory().get("/liste/", get)
    vorlage = Template("{% load liste %}{% sortkopf titel schluessel sort klasse %}")
    return vorlage.render(Context({"request": request, "titel": titel, "schluessel": schluessel,
                                   "sort": sort, "klasse": klasse}))  # fmt: skip


def test_sortkopf_pfeil_und_filter_bleiben():
    # Ohne Sortierung: neutraler Kopf; Klick sortiert aufsteigend und behält den Filter „q“.
    html = _sortkopf({"q": "muster"}, sort="")
    assert 'class="sortieren"' in html and "sort=name" in html and "q=muster" in html
    # Aktuell aufsteigend: Pfeil hoch (Klasse „auf“), nächster Klick kehrt um (-name).
    html = _sortkopf({}, sort="name")
    assert "sortieren auf" in html and "sort=-name" in html
    # Aktuell absteigend: Pfeil runter, nächster Klick wieder aufsteigend.
    html = _sortkopf({}, sort="-name")
    assert "sortieren ab" in html and "sort=name" in html


def test_sortkopf_ohne_schluessel_ist_schlicht():
    html = _sortkopf({}, titel="Kategorien", schluessel="")
    assert "Kategorien" in html and "sortieren" not in html


def test_sortieren_queryset_nur_bekannte_schluessel():
    qs = Adresse.objects.all()
    _, sort = listen.sortieren(qs, "boese", {"name": ("nachname",)}, "name")
    assert sort == "name"  # unbekannt → Vorgabe
    _, sort = listen.sortieren(qs, "-name", {"name": ("nachname",)}, "name")
    assert sort == "-name"


def test_sortieren_liste_richtung_und_vorgabe():
    zeilen = [{"n": 3}, {"n": 1}, {"n": 2}]
    schluessel = {"n": lambda z: z["n"]}
    sortiert, sort = listen.sortieren_liste(zeilen, "-n", schluessel, "n")
    assert [z["n"] for z in sortiert] == [3, 2, 1] and sort == "-n"
    sortiert, sort = listen.sortieren_liste(zeilen, "quatsch", schluessel, "n")
    assert [z["n"] for z in sortiert] == [1, 2, 3] and sort == "n"


def test_adressbuch_sortiert_nach_name(admin_client):
    Adresse.objects.create(art="person", vorname="Berta", nachname="Zimmer",
                           strasse="W 1", plz="1", ort="X")  # fmt: skip
    Adresse.objects.create(art="person", vorname="Anna", nachname="Albert",
                           strasse="W 2", plz="2", ort="Y")  # fmt: skip
    liste_url = reverse("adressen:liste")
    auf = admin_client.get(liste_url, {"sort": "name"}).content.decode()
    ab = admin_client.get(liste_url, {"sort": "-name"}).content.decode()
    assert auf.index("Albert") < auf.index("Zimmer")
    assert ab.index("Zimmer") < ab.index("Albert")
    # Der Spaltenkopf trägt den Sortierstil wie in allen Listen.
    assert "sortieren" in auf and "Nach Name sortieren" in auf


def test_mitgliederliste_sortiert_als_python_liste(admin_client):
    za = Adresse.objects.create(art="person", vorname="Berta", nachname="Zimmer",
                                strasse="W 1", plz="1", ort="X")  # fmt: skip
    an = Adresse.objects.create(art="person", vorname="Anna", nachname="Albert",
                                strasse="W 2", plz="2", ort="Y")  # fmt: skip
    Mitglied.objects.create(adresse=za, nummer="1", art="Ordentliches Mitglied",
                            eintritt=dt.date(2025, 1, 1), jahresbeitrag=0)  # fmt: skip
    Mitglied.objects.create(adresse=an, nummer="2", art="Ordentliches Mitglied",
                            eintritt=dt.date(2025, 1, 1), jahresbeitrag=0)  # fmt: skip
    liste_url = reverse("mitglieder:liste")
    nach_name = admin_client.get(liste_url, {"sort": "name"}).content.decode()
    assert nach_name.index("Albert") < nach_name.index("Zimmer")
    nach_nr = admin_client.get(liste_url, {"sort": "-nummer"}).content.decode()
    assert nach_nr.index("Albert") < nach_nr.index("Zimmer")  # Nr. 2 (Anna) vor Nr. 1 (Berta)
