import datetime as dt

import pytest
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core.models import TafelEinstellungen
from apps.konten import geburtstage, rollen

pytestmark = pytest.mark.django_db

GEB = reverse("konten:geburtstage")
START = reverse("core:start")


def mitarbeiter(django_user_model, nachname, geb, *, aktiv=True, stelle=False):
    konto = django_user_model.objects.create_user(
        username=nachname.lower(), last_name=nachname, is_active=aktiv
    )
    if stelle:
        from apps.kunden.models import Ausgabestelle

        konto.stelle = Ausgabestelle.objects.create(name=f"Stelle {nachname}")
        konto.save()
    Adresse.objects.create(art=Adresse.Art.PERSON, nachname=nachname, konto=konto, geburtsdatum=geb)
    return konto


def test_naechste_nur_aktive_mitarbeitende(django_user_model):
    heute = dt.date(2026, 3, 10)
    mitarbeiter(django_user_model, "Bald", dt.date(1980, 3, 15))  # in 5 Tagen
    mitarbeiter(django_user_model, "Spaet", dt.date(1990, 4, 20))  # außerhalb 14 Tage
    mitarbeiter(django_user_model, "Gesperrt", dt.date(1970, 3, 12), aktiv=False)
    mitarbeiter(django_user_model, "Tablet", dt.date(1975, 3, 11), stelle=True)
    # Person im Adressbuch ohne Konto zählt nicht als Mitarbeiter
    Adresse.objects.create(
        art=Adresse.Art.PERSON, nachname="Spender", geburtsdatum=dt.date(1960, 3, 13)
    )

    naechste = geburtstage.naechste(14, heute)
    assert [g["name"] for g in naechste] == ["Bald"]
    assert naechste[0]["wird"] == 46 and naechste[0]["in_tagen"] == 5


def test_naechste_heute_und_jahreswechsel(django_user_model):
    heute = dt.date(2026, 12, 28)
    mitarbeiter(django_user_model, "Heute", dt.date(1990, 12, 28))
    mitarbeiter(django_user_model, "Neujahr", dt.date(2000, 1, 2))  # im nächsten Jahr, in 5 Tagen
    naechste = geburtstage.naechste(14, heute)
    namen = [g["name"] for g in naechste]
    assert namen == ["Heute", "Neujahr"]
    assert naechste[0]["ist_heute"] and naechste[1]["in_tagen"] == 5
    assert naechste[1]["wird"] == 27  # Geburtstag 2027


def test_schalttag_wird_in_normaljahr_am_28_februar(django_user_model):
    heute = dt.date(2026, 2, 20)  # 2026 ist kein Schaltjahr
    mitarbeiter(django_user_model, "Schalt", dt.date(2000, 2, 29))
    naechste = geburtstage.naechste(14, heute)
    assert naechste and naechste[0]["naechster"] == dt.date(2026, 2, 28)


def test_kalender_nach_monaten(django_user_model):
    heute = dt.date(2026, 5, 1)
    mitarbeiter(django_user_model, "Maerz", dt.date(1980, 3, 15))
    mitarbeiter(django_user_model, "MaerzFrueh", dt.date(1985, 3, 2))
    kal = geburtstage.kalender(heute)
    maerz = kal[2]
    assert maerz["name"] == "März"
    assert [e["name"] for e in maerz["eintraege"]] == ["MaerzFrueh", "Maerz"]  # nach Tag sortiert


def test_seite_braucht_recht(admin_client, client, anmelden, benutzer_mit_rolle, django_user_model):
    mitarbeiter(django_user_model, "Heute", _heute_geb())
    # Admin (alle Rechte) sieht die Seite samt Name
    inhalt = admin_client.get(GEB).content.decode()
    assert "Geburtstage des Teams" in inhalt and "Heute" in inhalt
    # Rolle ohne das Recht: kein Zugriff
    anmelden(client, benutzer_mit_rolle("aus", rollen.AUSGABE))
    assert client.get(GEB).status_code == 403


def test_startseite_kachel_nur_mit_einstellung(admin_client, django_user_model):
    mitarbeiter(django_user_model, "Heute", _heute_geb())
    # Vorgabe aus → keine Kachel
    assert "Nächste Geburtstage" not in admin_client.get(START).content.decode()
    t = TafelEinstellungen.laden()
    t.geburtstage_startseite = True
    t.save()
    inhalt = admin_client.get(START).content.decode()
    assert "Nächste Geburtstage" in inhalt and "Heute" in inhalt


def _heute_geb() -> dt.date:
    from django.utils import timezone

    heute = timezone.localdate()
    # ein Geburtstag „heute", aber in einem früheren Jahr (29.02. gibt es 1980)
    return dt.date(1980, heute.month, heute.day)
