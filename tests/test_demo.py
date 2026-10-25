import datetime as dt

import pytest
from django.core.management import CommandError, call_command
from django.urls import reverse

from apps.ausgabe.models import Buchung
from apps.core.models import TafelEinstellungen
from apps.konten import rollen, zwei_faktor
from apps.konten.models import Rolle
from apps.kunden.models import Ausgabestelle, Dokumentart, Haushalt
from apps.personal.models import Zeitbuchung

pytestmark = pytest.mark.django_db

PASSWORT = "Demo-Passwort-erfunden-1"


@pytest.fixture
def demo(settings):
    settings.DEMO, settings.DEMO_PASSWORT = True, PASSWORT
    return settings


def test_nur_im_demo_betrieb(settings, admin):
    with pytest.raises(CommandError, match="Nur im Demo-Betrieb"):
        call_command("demo_zuruecksetzen")
    settings.DEMO = True
    with pytest.raises(CommandError, match="BINTAFELN_DEMO_PASSWORT"):
        call_command("demo_zuruecksetzen")
    assert Haushalt.objects.count() == 0  # nichts gelöscht oder angelegt


@pytest.mark.django_db(transaction=True, serialized_rollback=True)
def test_zuruecksetzen(demo, admin, django_user_model, settings, capsys):
    altdatei = settings.MEDIA_ROOT / "privat" / "alt.bin"
    altdatei.parent.mkdir(parents=True)
    altdatei.write_bytes(b"x")
    (settings.MEDIA_ROOT / "lose.txt").write_bytes(b"x")
    Buchung.objects.create(art=Buchung.Art.EINZAHLUNG, haben=1, bar=1)

    with pytest.raises(CommandError, match=r"Abbruch.*\(chefin\)"):
        call_command("demo_zuruecksetzen")
    assert Buchung.objects.exists() and altdatei.exists()  # nichts gelöscht

    call_command("demo_zuruecksetzen", "--auch-fremde-konten")
    assert "Demo zurückgesetzt" in capsys.readouterr().out
    assert not django_user_model.objects.filter(username="chefin").exists()
    assert not Buchung.objects.exists() and not any(settings.MEDIA_ROOT.iterdir())
    assert Haushalt.objects.filter(kundennummer="1001").exists()
    e = TafelEinstellungen.laden()
    assert e.name == "Demo-Tafel Musterstadt"
    assert not Rolle.objects.filter(zwei_faktor_pflicht=True).exists()
    assert Dokumentart.objects.exists() and Rolle.objects.get(gruppe__name="Büro").rechte
    admin_konto = django_user_model.objects.get(username="demo-admin")
    assert admin_konto.is_superuser and not admin_konto.is_staff
    assert admin_konto.check_password(PASSWORT)
    fest = django_user_model.objects.get(username="demo-fest")
    assert fest.vertraege.exists() and Zeitbuchung.objects.filter(benutzer=fest).exists()

    # Module eingeschaltet und mit Beispielen gefüllt (ohne Wetter)
    from apps.links.models import Link
    from apps.wochenuebersicht.models import Selbstabholer

    assert e.module == ["aufruf", "warteliste", "wochenuebersicht", "links", "abrechnung"]
    assert Link.objects.filter(warnung__gt="").exists() and Selbstabholer.objects.count() == 2
    tablet = django_user_model.objects.get(username="demo-tablet")
    assert tablet.stelle and tablet.check_password(PASSWORT)
    assert list(tablet.ausgabestellen.all()) == [tablet.stelle]
    from apps.konten.views import _demo_zugaenge

    assert (tablet.stelle.name, "Tablet am Einlass (Konto der Ausgabestelle)") in (
        _demo_zugaenge()["demo_konten"])  # fmt: skip
    # Ein von Besuchern angelegtes Konto einer Ausgabestelle blockiert das Zurücksetzen nicht
    django_user_model.objects.create_user(username="ausgabestelle-99", stelle=Ausgabestelle.objects
                                          .exclude(pk=tablet.stelle_id).first())  # fmt: skip

    call_command("demo_zuruecksetzen")  # wiederholbar
    assert django_user_model.objects.filter(username__startswith="demo-").count() == 6


def test_zuruecksetzen_ohne_medienordner(demo, settings):
    from apps.core import demo as demo_modul

    assert not settings.MEDIA_ROOT.exists()
    demo_modul.zuruecksetzen(dt.date(2026, 10, 24))
    assert Haushalt.objects.exists()


def test_fehlerhafte_beispieldaten(demo, tmp_path, monkeypatch):
    from django.core.exceptions import ImproperlyConfigured

    from apps.core import demo as demo_modul

    (tmp_path / "haushalte.csv").write_text("kaputt\n1;2\n")
    monkeypatch.setattr(demo_modul, "BEISPIELE", tmp_path)
    with pytest.raises(ImproperlyConfigured, match="Beispieldaten fehlerhaft"):
        demo_modul.zuruecksetzen()


def test_hinweise_und_sperren(demo, client, admin, anmelden, benutzer_mit_rolle):
    anmeldung = client.get(reverse("konten:anmelden")).content.decode()
    assert "Demoversion" in anmeldung and PASSWORT in anmeldung and "demo-buero" in anmeldung
    b = benutzer_mit_rolle("berta", rollen.BUERO)
    assert not zwei_faktor.ist_pflicht(b)
    anmelden(client, b)
    for url in (reverse("konten:passwort_aendern"), reverse("konten:zwei_faktor_einrichten")):
        antwort = client.get(url, follow=True)
        assert "In der Demoversion nicht möglich" in antwort.content.decode()
    client.logout()
    anmelden(client, admin)
    antwort = client.post(reverse("core:mail_einstellungen"), {"server": "x"}, follow=True)
    assert "In der Demoversion nicht möglich" in antwort.content.decode()


def test_ohne_demo_keine_hinweise(client, admin):
    assert "Demo" not in client.get(reverse("konten:anmelden")).content.decode()
