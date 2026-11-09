"""Ausgabestelle schließen: Enddatum + Auto-Archiv und geplante Verlegung der Kunden (ADR 0118).
Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.urls import reverse

from apps.kunden import verlegung
from apps.kunden.models import (
    Ausgabestelle,
    GeplanterWechsel,
    Haushalt,
    HaushaltEreignis,
    Kundengruppe,
    Person,
    fristen_anwenden,
)

pytestmark = pytest.mark.django_db
HEUTE = dt.date(2026, 12, 1)
GUELTIG = dt.date(2027, 6, 30)


@pytest.fixture
def aufbau():
    alt = Ausgabestelle.objects.create(name="Alt-Stelle")
    neu = Ausgabestelle.objects.create(name="Neu-Stelle")
    g_alt = Kundengruppe.objects.create(name="Alt Mo", ausgabestelle=alt, wochentage="Mo")
    g_neu = Kundengruppe.objects.create(name="Neu Di", ausgabestelle=neu, wochentage="Di")
    h = Haushalt.objects.create(
        kundennummer="7001", kundengruppe=g_alt, ausweis_gueltig_bis=GUELTIG
    )
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster")
    return alt, neu, g_alt, g_neu, h


def test_verlegung_zum_stichtag(aufbau):
    alt, neu, g_alt, g_neu, h = aufbau
    verlegung.planen(h, g_neu, HEUTE, "chefin")
    # Vor dem Stichtag passiert nichts
    assert verlegung.anwenden(HEUTE - dt.timedelta(days=1)) == 0
    h.refresh_from_db()
    assert h.kundengruppe_id == g_alt.pk
    # Am Stichtag wird verlegt, der Plan ist erledigt, die Historie hält es fest
    assert verlegung.anwenden(HEUTE) == 1
    h.refresh_from_db()
    assert h.kundengruppe_id == g_neu.pk
    assert GeplanterWechsel.objects.get(haushalt=h).erledigt_am == HEUTE
    assert HaushaltEreignis.objects.filter(
        kundennummer="7001", text__startswith="Verlegung"
    ).exists()
    # Zweiter Lauf verlegt nicht erneut
    assert verlegung.anwenden(HEUTE) == 0


def test_planen_ersetzt_und_entfernt(aufbau):
    alt, neu, g_alt, g_neu, h = aufbau
    verlegung.planen(h, g_neu, HEUTE, "chefin")
    verlegung.planen(h, g_neu, HEUTE + dt.timedelta(days=7), "chefin")  # ersetzt den ersten
    assert GeplanterWechsel.objects.filter(haushalt=h, erledigt_am__isnull=True).count() == 1
    assert verlegung.offener(h).ab == HEUTE + dt.timedelta(days=7)
    verlegung.entfernen(h)
    assert verlegung.offener(h) is None


def test_inaktive_zielgruppe_bleibt_offen(aufbau):
    alt, neu, g_alt, g_neu, h = aufbau
    verlegung.planen(h, g_neu, HEUTE, "chefin")
    Kundengruppe.objects.filter(pk=g_neu.pk).update(aktiv=False)
    assert verlegung.anwenden(HEUTE) == 0  # Zielgruppe inaktiv: nicht ausgeführt
    h.refresh_from_db()
    assert h.kundengruppe_id == g_alt.pk
    assert GeplanterWechsel.objects.get(haushalt=h).erledigt_am is None


def test_stelle_wird_archiviert(aufbau):
    alt, neu, g_alt, g_neu, h = aufbau
    alt.schliesst_am = HEUTE - dt.timedelta(days=1)  # letzter Tag war gestern
    alt.save()
    # Am letzten Tag selbst noch offen
    assert verlegung.stellen_schliessen(alt.schliesst_am) == 0
    assert Ausgabestelle.objects.get(pk=alt.pk).aktiv
    # Ab dem Tag danach ins Archiv, Gruppen inaktiv
    assert verlegung.stellen_schliessen(HEUTE) == 1
    alt.refresh_from_db()
    assert not alt.aktiv and not Kundengruppe.objects.get(pk=g_alt.pk).aktiv
    # Die andere Stelle bleibt unberührt
    assert Ausgabestelle.objects.get(pk=neu.pk).aktiv


def test_fristen_anwenden_ruft_beides(aufbau):
    alt, neu, g_alt, g_neu, h = aufbau
    verlegung.planen(h, g_neu, dt.date.today() - dt.timedelta(days=1), "chefin")
    alt.schliesst_am = dt.date.today() - dt.timedelta(days=2)
    alt.save()
    fristen_anwenden()  # Startseite ruft das täglich
    h.refresh_from_db()
    assert h.kundengruppe_id == g_neu.pk
    assert not Ausgabestelle.objects.get(pk=alt.pk).aktiv


def test_geplanter_zuzug_reserviert_platz(aufbau):
    """Ein geplanter Zuzug belegt den Platz in der Zielgruppe sofort – er wird bis zum Stichtag
    nicht erneut vergeben (sonst drohte ab dem Stichtag eine Überbuchung)."""
    from apps.antraege import aufnahme
    from apps.kunden import gruppen

    alt, neu, g_alt, g_neu, h = aufbau
    Kundengruppe.objects.filter(pk=g_neu.pk).update(maximum=1)

    def frei(pk):
        return next(x["frei"] for x in gruppen.mit_plaetzen() if x["gruppe"].pk == pk)

    assert frei(g_neu.pk) == 1  # ohne Plan: ein Platz frei
    verlegung.planen(h, g_neu, HEUTE, "chefin")
    assert frei(g_neu.pk) == 0  # Plan reserviert den Platz
    # Der Aufnahme-Assistent bietet die (reserviert-)volle Gruppe nicht mehr an
    assert g_neu.pk not in {x["gruppe"].pk for x in aufnahme.freie_gruppen()}
    # Nach Ausführung zählt der Haushalt regulär, die Reservierung entfällt – kein Doppeltzählen
    verlegung.anwenden(HEUTE)
    assert frei(g_neu.pk) == 0


def test_reservierung_erst_in_der_vorlaufzeit(aufbau):
    """Ein weit im Voraus geplanter Umzug blockiert den Platz noch nicht – erst innerhalb der
    eingestellten Vorlaufzeit vor dem Stichtag (``verlegung_vorlauf_wochen``)."""
    from apps.kunden import gruppen
    from apps.kunden.models import KundenEinstellungen

    alt, neu, g_alt, g_neu, h = aufbau
    Kundengruppe.objects.filter(pk=g_neu.pk).update(maximum=1)
    e = KundenEinstellungen.laden()
    e.verlegung_vorlauf_wochen = 6
    e.save()

    def frei(pk):
        return next(x["frei"] for x in gruppen.mit_plaetzen() if x["gruppe"].pk == pk)

    # Stichtag 10 Wochen in der Zukunft: außerhalb der 6-Wochen-Vorlaufzeit → kein Block
    verlegung.planen(h, g_neu, HEUTE + dt.timedelta(weeks=10), "chefin")
    assert frei(g_neu.pk) == 1
    # Stichtag 2 Wochen in der Zukunft: innerhalb der Vorlaufzeit → Platz reserviert
    verlegung.planen(h, g_neu, HEUTE + dt.timedelta(weeks=2), "chefin")
    assert frei(g_neu.pk) == 0


def test_verlegen_seite(admin_client, aufbau):
    alt, neu, g_alt, g_neu, h = aufbau
    url = reverse("kunden:ausgabestelle_verlegen", args=[alt.pk])
    seite = admin_client.get(url).content.decode()
    assert "7001" in seite and "Muster" in seite and "Neu Di" in seite
    # Verlegung planen
    admin_client.post(url, {"ab": "2026-12-01", f"ziel_{h.pk}": g_neu.pk})
    w = GeplanterWechsel.objects.get(haushalt=h)
    assert w.ziel_gruppe_id == g_neu.pk and w.ab == HEUTE and w.erledigt_am is None
    # Leer gewählt nimmt den Plan zurück
    admin_client.post(url, {"ab": "2026-12-01", f"ziel_{h.pk}": ""})
    assert not GeplanterWechsel.objects.filter(haushalt=h, erledigt_am__isnull=True).exists()


def test_enddatum_im_formular(admin_client, aufbau):
    alt, neu, g_alt, g_neu, h = aufbau
    daten = {"z-TOTAL_FORMS": "0", "z-INITIAL_FORMS": "0", "k-TOTAL_FORMS": "0",
             "k-INITIAL_FORMS": "0", "name": "Alt-Stelle", "aktiv": "on",
             "schliesst_am": "2026-12-31"}  # fmt: skip
    admin_client.post(reverse("kunden:ausgabestelle_bearbeiten", args=[alt.pk]), daten)
    assert Ausgabestelle.objects.get(pk=alt.pk).schliesst_am == dt.date(2026, 12, 31)
