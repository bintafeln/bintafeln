"""Nachrichten der Ausgabestellen an die Verwaltung zu fremden Kunden (ADR 0062)."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    Kundengruppe,
    Nachricht,
    Person,
    alte_nachrichten_loeschen,
)

pytestmark = pytest.mark.django_db
EMPFANG = reverse("ausgabe:empfang")


@pytest.fixture
def lage(admin, benutzer_mit_rolle, anmelden):
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    g = Kundengruppe.objects.create(name="Nord Mo", ausgabestelle=nord, wochentage="Mo")
    h = Haushalt.objects.create(kundennummer="501", kundengruppe=g)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Geheim")
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    return anmelden(Client(), b), mitte


def test_einlass_und_liste(lage, admin_client):
    c, mitte = lage
    c.post(reverse("ausgabe:ausgabestelle"), {"ausgabestelle": mitte.pk})
    seite = c.get(EMPFANG, {"nummer": "501"}).content.decode()
    assert "gehört nicht zu Ihrer Ausgabestelle" in seite and "Nachricht an die Verwaltung" in seite
    assert "Geheim" not in seite
    url = reverse("kunden:nachricht", args=["501"])
    antwort = c.post(url, {"text": "War heute hier, wohnt jetzt bei uns.", "zurueck": EMPFANG})
    assert antwort.url == EMPFANG
    n = Nachricht.objects.get()
    assert (n.kundennummer, n.stelle, n.von) == ("501", mitte, "anton")
    # leer, fremde Rücksprungadresse, unbekannter Kunde
    c.post(url, {"text": " ", "zurueck": EMPFANG})
    assert c.post(url, {"text": "x", "zurueck": "https://boese.example/"}).url == "/"
    assert c.post(reverse("kunden:nachricht", args=["999"]), {"text": "x"}).status_code == 404
    assert Nachricht.objects.count() == 2
    # Kundenliste: Suche nach der Nummer zeigt den Knopf ebenfalls
    liste = c.get(reverse("kunden:uebersicht"), {"q": "501"}).content.decode()
    assert "Nachricht an die Verwaltung" in liste
    # Die Ausgabestelle darf die Nachrichten nicht lesen
    assert c.get(reverse("kunden:nachrichten")).status_code == 403
    # Verwaltung: Startseite, Menü, Liste, Haushaltsseite, erledigen
    assert "2 × Sonstiges" in admin_client.get("/").content.decode()  # je Anliegen (ADR 0068)
    seite = admin_client.get(reverse("kunden:nachrichten")).content.decode()
    assert "War heute hier" in seite and "anton · Mitte" in seite
    haus = admin_client.get(reverse("kunden:haushalt", args=["501"])).content.decode()
    assert "Nachrichten der Ausgabestellen" in haus
    boese = {"nachricht": n.pk, "weiter": "https://boese.example/"}
    assert admin_client.post(reverse("kunden:nachrichten"), boese).url == "/kunden/nachrichten/"
    n.refresh_from_db()
    assert n.erledigt_am and n.erledigt_von == "chefin"
    admin_client.post(reverse("kunden:nachrichten"), {"nachricht": n.pk})
    n.refresh_from_db()
    assert n.erledigt_am is None


def test_recht_auskunft_und_frist(admin_client, lage, pdf_text):
    from apps.konten.models import Rolle

    assert "kunden.nachrichten" in Rolle.objects.get(gruppe__name=rollen.BUERO).rechte
    Nachricht.objects.create(kundennummer="501", text="Neue Adresse bekannt", von="anton")
    text = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["501"])))
    assert "Nachrichten der Ausgabestellen" in text and "Neue Adresse bekannt" in text
    alt = Nachricht.objects.create(kundennummer="501", text="alt",
                                   erledigt_am=timezone.now() - dt.timedelta(days=91))  # fmt: skip
    assert alte_nachrichten_loeschen() == 1 and not Nachricht.objects.filter(pk=alt.pk).exists()
