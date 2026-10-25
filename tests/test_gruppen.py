"""Ohne gültigen Ausweis keine Kundengruppe, Zeiten in Kundengruppen (ADR 0061). Erfundene Daten."""

import datetime as dt

import pytest
from django.urls import reverse

from apps.kunden import gruppen
from apps.kunden.models import (
    Gruppenzeit,
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Kundengruppe,
    Person,
)

pytestmark = pytest.mark.django_db
HEUTE = dt.date(2026, 10, 25)


@pytest.fixture
def mo():
    return Kundengruppe.objects.create(name="Montag")


def haushalt(nummer, gruppe, bis=dt.date(2027, 1, 1), status=Haushalt.Status.AKTIV):
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe, status=status,
                                ausweis_gueltig_bis=bis)  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster")
    return h


def test_grund():
    h = Haushalt(status=Haushalt.Status.AKTIV, ausweis_gueltig_bis=HEUTE)
    assert gruppen.grund(h, HEUTE) == ""  # gilt noch heute
    h.ausweis_gueltig_bis = None
    assert gruppen.grund(h, HEUTE) == ""  # ohne Datum: unbekannt, bleibt
    h.ausweis_gueltig_bis = HEUTE - dt.timedelta(days=1)
    assert gruppen.grund(h, HEUTE) == "Ausweis abgelaufen am 24.10.2026"
    for status in ("pausiert", "gesperrt", "beendet"):
        h.status = status
        assert gruppen.grund(h, HEUTE) == f"Status {status}"


def test_taeglich_und_zeiten(mo):
    di = Kundengruppe.objects.create(name="Dienstag")
    gut = haushalt("1", mo)
    alt = haushalt("2", mo, bis=HEUTE - dt.timedelta(days=3))
    haushalt("3", mo, status=Haushalt.Status.PAUSIERT)
    gruppen.zeiten_abgleichen(heute=HEUTE - dt.timedelta(days=10))
    assert Gruppenzeit.objects.filter(bis__isnull=True).count() == 3
    assert gruppen.regel_anwenden(HEUTE) == 2
    assert list(Haushalt.objects.filter(kundengruppe=mo).values_list("kundennummer", flat=True)) \
        == ["1"]  # fmt: skip
    z = Gruppenzeit.objects.get(kundennummer="2")
    assert (z.von, z.bis, z.grund) == (HEUTE - dt.timedelta(days=10), HEUTE,
                                       "Ausweis abgelaufen am 22.10.2026")  # fmt: skip
    e = HaushaltEreignis.objects.get(kundennummer="3")
    assert e.quelle == "automatik" and e.text == "Kundengruppe: Montag → – (Status pausiert)"
    assert gruppen.regel_anwenden(HEUTE) == 0  # nichts mehr zu tun
    # Wechsel und Verschwinden
    Haushalt.objects.filter(pk=gut.pk).update(kundengruppe=di)
    alt.delete()
    gruppen.zeiten_abgleichen(heute=HEUTE)
    namen = [(z.gruppe_name, z.bis, z.grund) for z in gruppen.zeiten("1")]
    assert namen == [("Dienstag", None, ""), ("Montag", HEUTE, "Wechsel nach Dienstag")]
    assert Gruppenzeit.objects.get(kundennummer="2").grund == "Ausweis abgelaufen am 22.10.2026"


def test_abschaltbar(mo):
    e = KundenEinstellungen.laden()
    e.gruppe_behalten = True
    e.save()
    h = haushalt("1", mo, status=Haushalt.Status.GESPERRT)
    assert gruppen.regel_anwenden(HEUTE) == 0 and gruppen.pruefen(h, HEUTE) == ""
    assert Haushalt.objects.get(pk=h.pk).kundengruppe == mo
    assert Gruppenzeit.objects.get(kundennummer="1").bis is None


def test_sofort_beim_bearbeiten(admin_client, mo):
    h = haushalt("1", mo)
    gruppen.zeiten_abgleichen()
    antwort = admin_client.post(reverse("kunden:bearbeiten", args=["1"]),
                                {"kundennummer": "1", "status": "pausiert",
                                 "kundengruppe": mo.pk}, follow=True)  # fmt: skip
    assert "Kundengruppe entfernt (Status pausiert)" in antwort.content.decode()
    h.refresh_from_db()
    assert h.kundengruppe is None
    assert HaushaltEreignis.objects.filter(text="Kundengruppe: Montag → –").exists()
    seite = admin_client.get(reverse("kunden:haushalt", args=["1"])).content.decode()
    assert "Kundengruppen" in seite and "Status pausiert" in seite
    # neue Kundennummer nimmt die Zeiten mit
    admin_client.post(reverse("kunden:bearbeiten", args=["1"]),
                      {"kundennummer": "9", "status": "aktiv", "kundengruppe": mo.pk})  # fmt: skip
    assert [z.gruppe_name for z in gruppen.zeiten("9")] == ["Montag", "Montag"]
    assert not Gruppenzeit.objects.filter(kundennummer="1").exists()


def test_auskunft_und_fristen(admin_client, mo, pdf_text):
    haushalt("1", mo)
    gruppen.zeiten_abgleichen()
    text = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["1"])))
    assert "Zeiten in Kundengruppen" in text and "Montag" in text
    Gruppenzeit.objects.create(kundennummer="1", gruppe_name="Alt", bis=dt.date(2000, 1, 1))
    from apps.kunden.models import alte_historie_loeschen

    alte_historie_loeschen()
    assert not Gruppenzeit.objects.filter(gruppe_name="Alt").exists()


def test_migration_legt_offene_zeiten_an(mo):
    from importlib import import_module

    from django.apps import apps

    haushalt("1", mo)
    Gruppenzeit.objects.all().delete()
    import_module("apps.kunden.migrations.0020_gruppenzeiten").anfangen(apps, None)
    z = Gruppenzeit.objects.get()
    assert (z.kundennummer, z.gruppe_name, z.von, z.bis) == ("1", "Montag", None, None)


def test_import_ohne_doppelte_historie():
    from tests.test_kunden_import import csv, pruefen, uebernehmen

    dateien = {
        "haushalte_csv": csv("kundennummer;nachname;vorname;status;kundengruppe",
                             "1;Muster;Erika;aktiv;MO1", "2;Muster;Max;pausiert;MO1"),
        "kundengruppen_csv": csv("kuerzel;name;ausgabestelle", "MO1;Montag;Mitte"),
    }  # fmt: skip
    uebernehmen(pruefen(**dateien))
    assert dict(Haushalt.objects.values_list("kundennummer", "kundengruppe__name")) == {
        "1": "Montag", "2": None}  # fmt: skip
    uebernehmen(pruefen(**dateien))  # zweiter Import: keine neuen Einträge für Nr. 2
    texte = list(HaushaltEreignis.objects.filter(kundennummer="2").values_list("text", "quelle"))
    assert texte == [("Neu im Kundenstamm", "import")]
    assert Gruppenzeit.objects.filter(kundennummer="1", bis__isnull=True).count() == 1
