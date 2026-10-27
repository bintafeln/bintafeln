"""Mitgelieferte Merkmale am Einlass und auf dem Ausweis (ADR 0071). Nur erfundene Daten."""

import datetime as dt
import importlib

import pytest
from django.apps import apps as django_apps
from django.urls import reverse
from django.utils import timezone

from apps.core.auswahl import FESTE_MERKMALE
from apps.konten import rollen
from apps.kunden import ausweis, merkmale
from apps.kunden.forms import ZusatzfeldForm
from apps.kunden.models import (
    Ausgabestelle,
    AusweisVorlage,
    Haushalt,
    Kundengruppe,
    Person,
    Zugriff,
    Zusatzfeld,
)

pytestmark = [pytest.mark.django_db, pytest.mark.merkmale]
FESTE = [s for s, *_ in FESTE_MERKMALE]
EMPFANG = reverse("ausgabe:empfang")


@pytest.fixture
def haushalt():
    stelle = Ausgabestelle.objects.create(name="Ausgabestelle Mitte")
    gruppe = Kundengruppe.objects.create(name="Jeden Tag", ausgabestelle=stelle,
                                         wochentage="Mo, Di, Mi, Do, Fr, Sa, So")  # fmt: skip
    h = Haushalt.objects.create(
        kundennummer="00042",
        kundengruppe=gruppe,
        ausweis_gueltig_bis=timezone.localdate() + dt.timedelta(days=99),
    )
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster",
                          zusatz={"schwerbehindert": True, "vegetarier": True})  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Kim", nachname="Muster",
                          zusatz={"blind": False, "hilfe_einkauf": True})  # fmt: skip
    return h


def test_mitgeliefert_und_nicht_doppelt():
    felder = {z.schluessel: z for z in Zusatzfeld.objects.filter(schluessel__in=FESTE)}
    assert list(felder) == [s for s, *_ in FESTE_MERKMALE]
    sb = felder["schwerbehindert"]
    assert sb.typ == "ja_nein" and sb.einlass and sb.besondere_kategorie and sb.aktiv
    assert sb.ausweis == "rollstuhl" and not felder["vegetarier"].besondere_kategorie
    merkmale.feste_anlegen()  # wiederholbar
    assert Zusatzfeld.objects.filter(schluessel__in=FESTE).count() == len(FESTE_MERKMALE)


def test_migration_uebernimmt_vorhandenes_feld():
    Zusatzfeld.objects.filter(schluessel__in=FESTE).delete()
    Zusatzfeld.objects.create(
        schluessel="schwerbehindert",
        bezeichnung="SB (alt)",
        gilt_fuer="haushalt",
        typ="auswahl",
        optionen="ja\nnein",
    )
    Zusatzfeld.objects.create(schluessel="blind", bezeichnung="Blind", ausweis="kuerzel",
                              kuerzel="B")  # fmt: skip
    migration = importlib.import_module("apps.kunden.migrations.0029_feste_merkmale")
    migration.anlegen(django_apps, None)
    sb = Zusatzfeld.objects.get(schluessel="schwerbehindert")
    assert sb.fest and sb.bezeichnung == "SB (alt)" and not sb.einlass  # keine Ja/Nein-Frage
    blind = Zusatzfeld.objects.get(schluessel="blind")
    assert blind.fest and blind.einlass and blind.ausweis == "kuerzel"  # Einstellung bleibt
    assert Zusatzfeld.objects.filter(schluessel__in=FESTE).count() == len(FESTE_MERKMALE)
    migration.zuruecksetzen(django_apps, None)  # löscht nichts
    assert Zusatzfeld.objects.filter(schluessel__in=FESTE).count() == len(FESTE)
    assert not Zusatzfeld(schluessel="eigenes").fest


def test_einstellungen_feste_art_und_kuerzel():
    sb = Zusatzfeld.objects.get(schluessel="schwerbehindert")
    form = ZusatzfeldForm(instance=sb)
    assert all(form.fields[n].disabled for n in ("schluessel", "gilt_fuer", "typ", "optionen"))
    daten = {"bezeichnung": "Schwerbehindert", "reihenfolge": 1, "aktiv": "",
             "besondere_kategorie": "on", "einlass": "on", "ausweis": "kuerzel"}  # fmt: skip
    form = ZusatzfeldForm(daten, instance=sb)
    assert not form.is_valid() and "kuerzel" in form.errors
    form = ZusatzfeldForm({**daten, "kuerzel": "SB"}, instance=sb)
    assert form.is_valid(), form.errors
    form.save()
    sb.refresh_from_db()
    assert not sb.aktiv and sb.typ == "ja_nein" and sb.kuerzel == "SB"  # Art bleibt fest
    # Einlass und Ausweis nur für Ja/Nein
    neu = ZusatzfeldForm({"schluessel": "notiz", "bezeichnung": "Notiz", "gilt_fuer": "person",
                          "typ": "text", "reihenfolge": 0, "aktiv": "on", "einlass": "on",
                          "ausweis": "rollstuhl"})  # fmt: skip
    assert neu.is_valid(), neu.errors
    feld = neu.save()
    assert not feld.einlass and feld.ausweis == ""


def test_einlass_zeigt_nur_ja_und_art9_nur_mit_recht(
    haushalt, admin_client, client, benutzer_mit_rolle, anmelden
):
    seite = admin_client.get(EMPFANG, {"nummer": "00042"}).content.decode()
    assert "<dt>Merkmale</dt>" in seite
    assert "Erika Muster: " in seite and '<span class="merkmal">Schwerbehindert</span>' in seite
    assert '<span class="merkmal">Vegetarier</span>' in seite
    assert "Kim Muster: " in seite and "Braucht Hilfe beim Einkauf" in seite
    assert '<span class="merkmal">Blind</span>' not in seite  # „nein“ wird nicht gezeigt
    assert Zugriff.objects.get(benutzername="chefin").besondere_kategorie

    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    seite = client.get(EMPFANG, {"nummer": "00042"}).content.decode()
    assert "Vegetarier" in seite and "Schwerbehindert" not in seite  # Art. 9 ohne Recht
    assert not Zugriff.objects.get(benutzername="anton").besondere_kategorie

    # Abgeschaltet oder nicht für den Einlass: nichts zu sehen
    Zusatzfeld.objects.filter(schluessel="vegetarier").update(aktiv=False)
    Zusatzfeld.objects.filter(schluessel="hilfe_einkauf").update(einlass=False)
    seite = client.get(EMPFANG, {"nummer": "00042"}).content.decode()
    assert "<dt>Merkmale</dt>" not in seite


def test_haushaltsfeld_und_eine_person(haushalt, admin):
    Zusatzfeld.objects.create(schluessel="lieferung", bezeichnung="Lieferung", gilt_fuer="haushalt",
                              einlass=True)  # fmt: skip
    haushalt.zusatz = {"lieferung": True}
    haushalt.save()
    zeilen, art9 = merkmale.einlass(haushalt, admin)
    assert zeilen[0] == {"name": "", "merkmale": ["Lieferung"]} and art9
    assert zeilen[1]["merkmale"] == ["Schwerbehindert", "Vegetarier"]


def test_ausweis_symbole(haushalt, monkeypatch, pdf_text, admin_client):
    assert merkmale.ausweis(haushalt) == [("rollstuhl", "")]
    Zusatzfeld.objects.filter(schluessel="vegetarier").update(ausweis="kuerzel", kuerzel="V")
    Zusatzfeld.objects.filter(schluessel="hilfe_einkauf").update(ausweis="rollstuhl")
    assert merkmale.ausweis(haushalt) == [("rollstuhl", ""), ("kuerzel", "V")]  # nur einmal ♿
    assert merkmale.ausweis(Haushalt.objects.create(kundennummer="00043")) == []

    gezeichnet = []
    echt = ausweis._rollstuhl
    monkeypatch.setattr(ausweis, "_rollstuhl", lambda *a: gezeichnet.append(a) or echt(*a))
    vorlage = AusweisVorlage.laden()
    vorlage.vorderseite = [*ausweis.STANDARD, {"typ": "merkmale", "x": 60, "y": 30, "b": 20,
                                                "h": 6, "ausrichtung": "rechts"}]  # fmt: skip
    vorlage.save()
    e = next(x for x in vorlage.elemente_vorne() if x["typ"] == "merkmale")
    assert e["typ"] == "merkmale" and e["farbe"] == ausweis.MERKMAL_FARBE
    text = pdf_text(admin_client.get(reverse("kunden:ausweis", args=["00042"])))
    assert len(gezeichnet) == 1 and "(V) Tj" in text


def test_bearbeiten_mit_haekchen(haushalt, admin_client):
    erika = haushalt.personen.get(vorname="Erika")
    url = reverse("kunden:teil", args=[haushalt.kundennummer, "person", erika.pk])
    seite = admin_client.get(url).content.decode()
    assert 'type="checkbox" name="zusatz_schwerbehindert"' in seite
    assert 'name="zusatz_vegetarier" id="id_zusatz_vegetarier" checked' in seite
