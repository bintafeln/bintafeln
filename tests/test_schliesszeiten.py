"""Schließzeiten einer Ausgabestelle (ADR 0144): eintragen, Vorauszahlung, Hinweis am Einlass.
Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal as D

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe import konto
from apps.ausgabe.models import AusgabeEinstellungen, Schliesszeit
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe

pytestmark = pytest.mark.django_db
LISTE = reverse("kunden:liste", args=["schliesszeiten"])
NEU = reverse("kunden:listeneintrag_neu", args=["schliesszeiten"])


@pytest.fixture
def stellen():
    return Ausgabestelle.objects.create(name="Mitte"), Ausgabestelle.objects.create(name="Nord")


def _haushalt(stelle, nummer="1"):
    gruppe = Kundengruppe.objects.create(kuerzel=f"D{nummer}", name=f"Dienstag {nummer}",
                                         wochentage="Di", ausgabestelle=stelle)  # fmt: skip
    return Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe)


def test_tage_am_und_hinweis(stellen):
    mitte, nord = stellen
    z = Schliesszeit.objects.create(ausgabestelle=mitte, bezeichnung="Sommerpause",
                                    von=dt.date(2026, 7, 13), bis=dt.date(2026, 7, 31))  # fmt: skip
    assert Schliesszeit.am(mitte, dt.date(2026, 7, 13)) == z
    assert Schliesszeit.am(mitte, dt.date(2026, 8, 1)) is None
    assert Schliesszeit.am(nord, dt.date(2026, 7, 20)) is None  # gilt nur für diese Stelle
    assert Schliesszeit.am(None, dt.date(2026, 7, 20)) is None
    tage = Schliesszeit.tage(mitte, dt.date(2026, 7, 1), dt.date(2026, 7, 15))
    assert tage == {dt.date(2026, 7, 13), dt.date(2026, 7, 14), dt.date(2026, 7, 15)}
    assert Schliesszeit.tage(nord, dt.date(2026, 7, 1), dt.date(2026, 7, 31)) == set()
    # Hinweis: 14 Tage vorher, während der Schließzeit, danach nicht mehr
    assert Schliesszeit.hinweis(mitte, dt.date(2026, 6, 28)) is None
    assert Schliesszeit.hinweis(mitte, dt.date(2026, 6, 29)) == z
    assert Schliesszeit.hinweis(mitte, dt.date(2026, 7, 31)) == z
    assert Schliesszeit.hinweis(mitte, dt.date(2026, 8, 1)) is None
    assert str(z) == "Mitte: 13.07.2026 bis 31.07.2026 (Sommerpause)"


def test_vorauszahlung_zaehlt_geschlossene_tage_nicht(stellen):
    mitte, nord = stellen
    h = _haushalt(mitte)
    e = AusgabeEinstellungen.laden()
    e.max_abholungen = 0
    heute = dt.date(2026, 7, 1)  # Dienstage im Juli 2026: 7., 14., 21., 28.
    rest = konto.vorschlaege(h, heute, e, D("1.50"))[0][0]
    assert len(rest.tage) == 4 and rest.betrag == D("6.00")

    Schliesszeit.objects.create(ausgabestelle=mitte, von=dt.date(2026, 7, 20),
                                bis=dt.date(2026, 7, 26))  # fmt: skip
    rest = konto.vorschlaege(h, heute, e, D("1.50"))[0][0]
    assert [t.day for t in rest.tage] == [7, 14, 28] and rest.betrag == D("4.50")
    assert "Nicht gezählt, weil die Ausgabestelle geschlossen hat: Di 21.07." in rest.erklaerung

    # Schließzeit einer anderen Ausgabestelle ändert nichts
    anderer = _haushalt(nord, "2")
    assert len(konto.vorschlaege(anderer, heute, e, D("1.50"))[0][0].tage) == 4

    # bleiben zu wenige Tage, gibt es keinen Vorschlag
    Schliesszeit.objects.create(ausgabestelle=mitte, von=dt.date(2026, 7, 1),
                                bis=dt.date(2026, 7, 14))  # fmt: skip
    vorschlaege, grund = konto.vorschlaege(h, heute, e, D("1.50"))
    assert vorschlaege == [] and "weniger als" in grund


def test_eintragen_in_den_einstellungen(admin_client, stellen):
    mitte, _ = stellen
    assert "Schließzeiten" in admin_client.get(LISTE).content.decode()
    falsch = admin_client.post(NEU, {"ausgabestelle": mitte.pk, "von": "2026-12-28",
                                     "bis": "2026-12-20"})  # fmt: skip
    assert "nicht vor" in falsch.content.decode() and not Schliesszeit.objects.exists()
    admin_client.post(NEU, {"ausgabestelle": mitte.pk, "von": "2026-12-21", "bis": "2027-01-03",
                            "bezeichnung": "Weihnachten"})  # fmt: skip
    z = Schliesszeit.objects.get()
    assert (z.ausgabestelle, z.bezeichnung) == (mitte, "Weihnachten")
    liste = admin_client.get(LISTE).content.decode()
    assert "Mitte" in liste and "21.12.2026" in liste and "03.01.2027" in liste


def test_nur_mit_recht(client, admin, benutzer_mit_rolle, anmelden):
    c = anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert c.get(LISTE).status_code == 403 and c.get(NEU).status_code == 403


def test_hinweis_am_einlass_und_auf_der_startseite(admin, stellen, benutzer_mit_rolle, anmelden):
    mitte, nord = stellen
    heute = timezone.localdate()
    Schliesszeit.objects.create(ausgabestelle=mitte, bezeichnung="Sommerpause",
                                von=heute + dt.timedelta(days=5),
                                bis=heute + dt.timedelta(days=20))  # fmt: skip
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.ausgabestellen.set([mitte])
    c = anmelden(Client(), anton)
    for adresse in ("/", reverse("ausgabe:empfang")):
        inhalt = c.get(adresse).content.decode()
        assert "data-schliesszeit" in inhalt and "Mitte schließt" in inhalt
        assert "Sommerpause" in inhalt
    # läuft die Schließzeit, heißt es „hat geschlossen“
    Schliesszeit.objects.update(von=heute - dt.timedelta(days=1))
    assert "Mitte hat geschlossen" in c.get(reverse("ausgabe:empfang")).content.decode()
    # eine andere Ausgabestelle sieht nichts davon
    berta = benutzer_mit_rolle("berta", rollen.AUSGABE)
    berta.ausgabestellen.set([nord])
    andere = anmelden(Client(), berta)
    assert "data-schliesszeit" not in andere.get(reverse("ausgabe:empfang")).content.decode()
