"""Menü links: Einstellungen in Untermenüs (Tafel, Kunden, Ausgabe, Verein, …)."""

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.core.menue import menue
from apps.core.models import TafelEinstellungen
from apps.konten import rollen

pytestmark = pytest.mark.django_db


def einstellungen(benutzer, pfad="/"):
    anfrage = RequestFactory().get(pfad)
    anfrage.user = benutzer
    return next((b for b in menue(anfrage) if b["titel"] == "Einstellungen"), None)


def titel(bereich):
    return {g["titel"]: [e["titel"] for e in g["eintraege"]] for g in bereich["gruppen"]}


def test_admin_sieht_alle_untermenues(admin):
    gruppen = titel(einstellungen(admin))
    assert list(gruppen) == ["Tafel", "Kunden", "Ausgabe", "Verein", "Mitarbeitende",
                             "Systemsteuerung"]  # fmt: skip
    assert "Rollen und Rechte" in gruppen["Mitarbeitende"]
    assert "Kundengruppen" in gruppen["Kunden"] and "Sicherungen" in gruppen["Systemsteuerung"]
    assert "Aufruf, Monitor und Kiosk" not in gruppen["Ausgabe"]  # Modul aus


def test_modul_haengt_sich_ins_passende_untermenue(admin):
    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    assert "Aufruf, Monitor und Kiosk" in titel(einstellungen(admin))["Ausgabe"]


def test_aktive_seite_oeffnet_ihr_untermenue(admin):
    bereich = einstellungen(admin, reverse("core:protokoll"))
    assert bereich["offen"]
    offen = [g["titel"] for g in bereich["gruppen"] if g["offen"]]
    assert offen == ["Systemsteuerung"]


def test_nur_untermenues_mit_rechten(benutzer_mit_rolle, recht_geben):
    recht_geben(rollen.AUSGABE, "einstellungen.ausgabe")
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    assert list(titel(einstellungen(anton))) == ["Ausgabe"]
    assert einstellungen(benutzer_mit_rolle("berta", rollen.KIOSK)) is None


def test_untermenues_auf_der_seite(admin_client):
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert (
        '<details class="menue-gruppe" name="menue-gruppe">' in seite
        and "<summary>Systemsteuerung</summary>" in seite
    )


def test_nur_ein_bereich_offen(admin_client):
    """Gleicher ``name`` an den <details>: Der Browser schließt beim Öffnen die anderen."""
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert seite.count('name="menue-bereich"') > 3 and 'name="menue-gruppe"' in seite
