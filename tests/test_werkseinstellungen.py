"""Admin setzt ein Konto auf Werkseinstellungen zurück: persönliche Ansichten wie beim
Anlegen, Rollen und Rechte bleiben."""

import pytest
from django.urls import reverse

from apps.datenimport.models import ImportSitzung
from apps.konten import rollen, verwaltung
from apps.kunden.models import Ausgabestelle

pytestmark = pytest.mark.django_db


def test_werkseinstellungen(admin_client, admin, benutzer_mit_rolle):
    nord = Ausgabestelle.objects.create(name="Nord")
    anna = benutzer_mit_rolle("anna", rollen.BUERO)
    anna.ausgabestellen.add(nord)
    anna.ausgabetage = "Mo"
    anna.kundenliste_aus = ["telefon", "ort"]
    anna.antraege_liste_aus = ["telefon", "email"]
    anna.gewaehlte_stelle = nord
    anna.save()
    ImportSitzung.objects.create(benutzer=anna, ziel="kunden")
    seite = admin_client.get(reverse("konten:mitarbeiter", args=[anna.pk])).content.decode()
    assert "Werkseinstellungen" in seite
    antwort = admin_client.post(reverse("konten:werkseinstellungen", args=[anna.pk]), follow=True)
    assert "auf Werkseinstellungen zurückgesetzt" in antwort.content.decode()
    anna.refresh_from_db()
    assert anna.kundenliste_aus == [] and anna.antraege_liste_aus == []
    assert anna.gewaehlte_stelle is None
    assert anna.ansicht_stand == 1
    assert not ImportSitzung.objects.filter(benutzer=anna).exists()
    # Rollen, Zuordnung und Ausgabetage bleiben
    assert list(anna.groups.values_list("name", flat=True)) == [rollen.BUERO]
    assert list(anna.ausgabestellen.all()) == [nord] and anna.ausgabetage == "Mo"


def test_nur_admin_fasst_admin_konten_an(admin, benutzer_mit_rolle):
    buero = benutzer_mit_rolle("berta", rollen.BUERO)
    with pytest.raises(verwaltung.VerwaltungsFehler):
        verwaltung.werkseinstellungen(buero, admin)
