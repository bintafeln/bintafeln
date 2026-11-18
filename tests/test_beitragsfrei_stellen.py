"""Beitragsfreie Zeiträume nur für einzelne Ausgabestellen. Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal as D

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe import konto
from apps.ausgabe.models import AusgabeEinstellungen, BeitragsfreierZeitraum
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe, Person

pytestmark = pytest.mark.django_db
HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def welt():
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_person = D("1.50")
    e.zusatzbeitraege = False
    e.max_abholungen = 0
    e.save()

    def haushalt(nummer, stelle):
        gruppe = Kundengruppe.objects.create(kuerzel=f"D{nummer}", name=f"Gruppe {nummer}",
                                             wochentage="Mo,Di,Mi,Do,Fr,Sa,So",
                                             ausgabestelle=stelle)  # fmt: skip
        h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe,
                                    ausweis_gueltig_bis=dt.date(2030, 1, 1))  # fmt: skip
        Person.objects.create(haushalt=h, vorname="Erika", nachname="Beispiel",
                              geburtsdatum=dt.date(1970, 5, 1), ist_hauptperson=True)  # fmt: skip
        return h

    return mitte, nord, haushalt("00042", mitte), haushalt("00077", nord)


def _zeitraum(heute, *stellen, name="Sommerfest"):
    z = BeitragsfreierZeitraum.objects.create(bezeichnung=name, von=heute,
                                              bis=heute + dt.timedelta(days=2))  # fmt: skip
    z.ausgabestellen.set(stellen)
    return z


def test_ohne_auswahl_gilt_er_ueberall(welt):
    mitte, nord, in_mitte, in_nord = welt
    heute = dt.date(2026, 7, 1)
    z = _zeitraum(heute)
    assert z.gilt_an(mitte) and z.gilt_an(nord) and z.gilt_an(None) and z.wo() == "alle"
    e = AusgabeEinstellungen.laden()
    assert e.beitrag_fuer(in_mitte, heute, 18) == D("0.00")
    assert e.beitrag_fuer(in_nord, heute, 18) == D("0.00")


def test_nur_an_gewaehlten_ausgabestellen(welt):
    mitte, nord, in_mitte, in_nord = welt
    heute = dt.date(2026, 7, 1)
    z = _zeitraum(heute, mitte)
    assert z.gilt_an(mitte) and not z.gilt_an(nord) and not z.gilt_an(None)
    assert z.wo() == "Mitte"
    assert BeitragsfreierZeitraum.am(heute, mitte) == z
    assert BeitragsfreierZeitraum.am(heute, nord) is None
    e = AusgabeEinstellungen.laden()
    # ohne gewählte Ausgabestelle zählt die der Kundengruppe
    assert e.beitrag_fuer(in_mitte, heute, 18) == D("0.00")
    assert e.beitrag_fuer(in_nord, heute, 18) == D("1.50")
    # die am Einlass gewählte Ausgabestelle geht vor
    assert e.beitrag_fuer(in_nord, heute, 18, stelle=mitte) == D("0.00")
    assert e.beitrag_fuer(in_mitte, heute, 18, stelle=nord) == D("1.50")
    # danach kostet es wieder
    assert e.beitrag_fuer(in_mitte, heute + dt.timedelta(days=3), 18) == D("1.50")


def test_vorauszahlung_laesst_nur_dort_die_tage_aus(welt):
    mitte, nord, in_mitte, in_nord = welt
    heute = dt.date(2026, 7, 27)  # bis 31.07. fünf Tage
    _zeitraum(heute, mitte)  # 27.–29.07. beitragsfrei in Mitte
    e = AusgabeEinstellungen.laden()
    in_nord_vorschlag = konto.vorschlaege(in_nord, heute, e, D("1.50"))[0][0]
    assert len(in_nord_vorschlag.tage) == 5
    vorschlaege, grund = konto.vorschlaege(in_mitte, heute, e, D("1.50"))
    assert vorschlaege == [] and "weniger als" in grund  # nur 30. und 31. bleiben


def test_formular_und_liste(admin_client, welt):
    mitte, nord, *_ = welt
    neu = reverse("kunden:listeneintrag_neu", args=["beitragsfrei"])
    assert "Ausgabestellen" in admin_client.get(neu).content.decode()
    daten = {"bezeichnung": "Sommerfest", "von": "2026-07-01", "bis": "2026-07-03"}
    admin_client.post(neu, {**daten, "ausgabestellen": [nord.pk]})
    z = BeitragsfreierZeitraum.objects.get()
    assert list(z.ausgabestellen.all()) == [nord]
    liste = reverse("kunden:liste", args=["beitragsfrei"])
    assert "Nord" in admin_client.get(liste).content.decode()
    # nichts angehakt = alle (die Vorgabe)
    admin_client.post(reverse("kunden:listeneintrag", args=["beitragsfrei", z.pk]), daten)
    assert not z.ausgabestellen.exists()
    assert ">alle<" in admin_client.get(liste).content.decode()


def test_einlass_zeigt_beitragsfrei_nur_an_der_stelle(admin, welt, benutzer_mit_rolle, anmelden):
    mitte, nord, in_mitte, in_nord = welt
    _zeitraum(timezone.localdate(), mitte)
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.ausgabestellen.set([mitte])
    berta = benutzer_mit_rolle("berta", rollen.AUSGABE)
    berta.ausgabestellen.set([nord])
    url = reverse("ausgabe:empfang")
    in_der_mitte = anmelden(Client(), anton).get(url, {"nummer": "42"}, **HX).content.decode()
    assert "Heute beitragsfrei: Sommerfest" in in_der_mitte
    im_norden = anmelden(Client(), berta).get(url, {"nummer": "77"}, **HX).content.decode()
    assert "Heute beitragsfrei" not in im_norden
