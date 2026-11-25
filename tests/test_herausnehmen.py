"""„Kunden herausnehmen“: Wer lange unentschuldigt gefehlt hat, wird mit einem Knopf aus der
Kundengruppe genommen und gesperrt (ADR 0177). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import PapierkorbEintrag
from apps.kunden import herausnehmen
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Kundengruppe,
    Notiz,
    Person,
    Sperre,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def lage(admin):
    heute = timezone.localdate()
    stelle = Ausgabestelle.objects.create(name="Zentrale")
    g = Kundengruppe.objects.create(name="Mi 12:00", ausgabestelle=stelle, wochentage="Mi")
    spaeter = heute + dt.timedelta(days=200)

    def kunde(nummer, besuch_vor_tagen=None, **mehr):
        besuch = heute - dt.timedelta(days=besuch_vor_tagen) if besuch_vor_tagen else None
        h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=g, letzter_besuch=besuch,
                                    ausweis_gueltig_bis=spaeter, **mehr)  # fmt: skip
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                              nachname=f"Muster{nummer}")  # fmt: skip
        return h

    return {"heute": heute, "g": g, "spaeter": spaeter, "kunde": kunde}


def test_knopf_nur_wenn_lange_nicht_gekommen(admin_client, lage):
    lange = lage["kunde"]("1", 100)
    neulich = lage["kunde"]("2", 10)
    nie = lage["kunde"]("3")
    gesperrt = lage["kunde"]("4", 100, status="gesperrt")
    assert [herausnehmen.faellig(h) for h in (lange, neulich, nie, gesperrt)] == [
        True, False, True, False]  # fmt: skip
    weg = reverse("kunden:herausnehmen", args=["1"])
    assert f'href="{weg}"' in admin_client.get(reverse("kunden:haushalt", args=["1"])).text
    seite = admin_client.get(reverse("kunden:haushalt", args=["2"])).text
    assert "Kunden herausnehmen" not in seite
    # die Grenze ist einstellbar
    e = KundenEinstellungen.laden()
    e.herausnehmen_nach_tagen = 7
    e.save()
    assert herausnehmen.faellig(neulich)
    # dieselbe Grenze ist die Vorgabe der Liste „Lange nicht gekommen“
    from apps.listen import katalog

    vorgabe = katalog.vorgaben(katalog.NACH_KENNUNG["lange_nicht"], lage["heute"])
    assert vorgabe["besuch_vor"] == (lage["heute"] - dt.timedelta(days=7)).isoformat()


def test_herausnehmen_und_zuruecknehmen(admin_client, admin, lage):
    heute = lage["heute"]
    h = lage["kunde"]("1", 100)
    Notiz.objects.create(kundennummer="1", text="Abwesend (krank) bis Monatsende.")
    weg = reverse("kunden:herausnehmen", args=["1"])
    seite = admin_client.get(weg).text
    assert "Abwesend (krank) bis Monatsende." in seite and "Bitte vorher lesen" in seite
    assert 'value="Lange unentschuldigt gefehlt"' in seite
    antwort = admin_client.post(weg, {"begruendung": "Lange unentschuldigt gefehlt"}, follow=True)
    assert "herausgenommen" in antwort.text
    h.refresh_from_db()
    sperre = Sperre.objects.get(haushalt=h)
    assert h.ausweis_gueltig_bis == heute - dt.timedelta(days=1) and h.kundengruppe is None
    assert (sperre.von, sperre.begruendung) == (heute, "Lange unentschuldigt gefehlt")
    assert sperre.bis == herausnehmen.sperre_bis(heute) and sperre.bis.year == heute.year + 1
    assert sperre.herausnahme and sperre.ausweis_vorher == lage["spaeter"]
    assert HaushaltEreignis.objects.filter(
        kundennummer="1", text__contains="Kunde herausgenommen").exists()  # fmt: skip
    # jetzt steht statt des Knopfs „Herausnahme zurücknehmen“ da; ein zweites Mal geht nicht
    seite = admin_client.get(reverse("kunden:haushalt", args=["1"])).text
    assert "Herausnahme zurücknehmen" in seite and f'href="{weg}"' not in seite
    assert "lässt sich hier nicht herausnehmen" in admin_client.get(weg).text
    with pytest.raises(herausnehmen.HerausnehmenFehler):
        herausnehmen.herausnehmen(Haushalt.objects.get(pk=h.pk), admin)

    antwort = admin_client.post(reverse("kunden:herausnahme_zurueck", args=["1"]), follow=True)
    assert "Herausnahme zurückgenommen" in antwort.text
    h.refresh_from_db()
    assert h.ausweis_gueltig_bis == lage["spaeter"] and not Sperre.objects.exists()
    assert PapierkorbEintrag.objects.filter(art="Sperre", kundennummer="1").exists()
    assert h.kundengruppe is None  # die Gruppe wählt man neu
    with pytest.raises(herausnehmen.HerausnehmenFehler):
        herausnehmen.zuruecknehmen(h, admin)


def test_status_gesperrt_mit_der_statusregel(admin, lage):
    e = KundenEinstellungen.laden()
    e.status_nach_ausweis = True
    e.save()
    h = lage["kunde"]("1", 100)
    herausnehmen.herausnehmen(h, admin)
    h.refresh_from_db()
    assert h.status == "gesperrt"
    herausnehmen.zuruecknehmen(h, admin)
    h.refresh_from_db()
    assert h.status == "aktiv"


def test_sperre_bis_am_monatsende():
    e = KundenEinstellungen.laden()
    e.herausnehmen_sperre_monate = 12
    e.save()
    assert herausnehmen.sperre_bis(dt.date(2028, 2, 29)) == dt.date(2029, 2, 28)
    e.herausnehmen_sperre_monate = 6
    e.save()
    assert herausnehmen.sperre_bis(dt.date(2026, 8, 31)) == dt.date(2027, 2, 28)


def test_nur_mit_dem_recht(lage, benutzer_mit_rolle, anmelden, recht_geben):
    lage["kunde"]("1", 100)
    buero = benutzer_mit_rolle("berta", "Büro")
    client = anmelden(Client(), buero)
    assert client.get(reverse("kunden:herausnehmen", args=["1"])).status_code == 403
    assert client.post(reverse("kunden:herausnahme_zurueck", args=["1"])).status_code == 403
    assert "Kunden herausnehmen" not in client.get(reverse("kunden:haushalt", args=["1"])).text
    recht_geben("Büro", "kunden.herausnehmen")
    client = anmelden(Client(), type(buero).objects.get(pk=buero.pk))
    assert "Kunden herausnehmen" in client.get(reverse("kunden:haushalt", args=["1"])).text
