"""Arbeitszeit am Aushang-Monitor stempeln (ADR 0123): mit Name und PIN oder über den QR-Code."""

import pytest
from django.contrib.auth import get_user_model
from django.core import signing
from django.test import Client
from django.urls import reverse

from apps.aushang import pin, stempeln
from apps.aushang.models import Aushang, AushangSeite
from apps.core.models import TafelEinstellungen
from apps.personal import arbeitszeit
from apps.personal.models import ArbeitszeitEinstellungen, Zeitbuchung

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def module_an():
    t = TafelEinstellungen.laden()
    t.module = ["aushang", "dienstplan", "fahrdienst"]
    t.save()


@pytest.fixture
def kim(benutzer_mit_rolle, admin):
    """Fest angestellt, mit PIN."""
    b = benutzer_mit_rolle("kim", "Ausgabe")
    b.first_name, b.last_name, b.beschaeftigung = "Kim", "Probe", "fest"
    b.save()
    pin.setzen(b, "482915")
    return b


@pytest.fixture
def dienstplan_monitor():
    a = Aushang.objects.create(name="Monitor Ausgabe")
    AushangSeite.objects.create(aushang=a, art="dienstplan", wert="1")
    return a


def _url(aushang):
    return reverse("aushang:stempeln", args=[aushang.schluessel])


def test_knopf_in_der_vorgabe_nur_am_dienstplan_monitor(dienstplan_monitor, kim):
    """Vorgabe: Stempeln nur an Monitoren mit einem Dienstplan; je Monitor an- und abschaltbar."""
    fahrer = Aushang.objects.create(name="Monitor Fahrerraum")
    AushangSeite.objects.create(aushang=fahrer, art="fahrdienst")
    c = Client()
    zeigen = lambda a: c.get(reverse("aushang:anzeige", args=[a.schluessel])).content.decode()  # noqa: E731
    assert stempeln.an(dienstplan_monitor) and 'id="aushang-stempeln"' in zeigen(dienstplan_monitor)
    assert not stempeln.an(fahrer) and 'id="aushang-stempeln"' not in zeigen(fahrer)
    assert c.get(_url(fahrer)).status_code == 404
    # Von Hand: am Fahrer-Monitor ein, am Dienstplan-Monitor aus
    fahrer.stempeln = "an"
    fahrer.save()
    dienstplan_monitor.stempeln = "aus"
    dienstplan_monitor.save()
    assert 'id="aushang-stempeln"' in zeigen(fahrer)
    assert 'id="aushang-stempeln"' not in zeigen(dienstplan_monitor)
    # Ohne Arbeitszeiterfassung gibt es den Knopf nirgends
    e = ArbeitszeitEinstellungen.laden()
    e.aktiv = False
    e.save()
    assert not stempeln.an(fahrer)
    # … außer eine einzelne Person stempelt trotzdem
    kim.zeiterfassung = "an"
    kim.save()
    assert stempeln.an(fahrer)
    # Beide Wege abgeschaltet: kein Knopf
    fahrer.stempeln_pin = fahrer.stempeln_qr = False
    fahrer.save()
    assert not stempeln.an(fahrer)


def test_stempeln_mit_name_und_pin(dienstplan_monitor, kim, benutzer_mit_rolle):
    """Erst wird die PIN geprüft, dann erscheinen die passenden Knöpfe; gestempelt wird für die
    Person, deren PIN stimmt. Wer nicht stempelt oder keine PIN hat, steht nicht zur Wahl."""
    ohne_pin = benutzer_mit_rolle("ole", "Ausgabe")
    ohne_pin.beschaeftigung = "fest"
    ohne_pin.save()
    ehrenamt = benutzer_mit_rolle("eva", "Ausgabe")  # stempelt nicht
    pin.setzen(ehrenamt, "482915")
    c, url = Client(), _url(dienstplan_monitor)
    fenster = c.get(url).content.decode()
    assert ">Kim Probe<" in fenster and ">ole<" not in fenster and ">eva<" not in fenster
    assert "<svg" in fenster  # QR-Code daneben
    # Falsche PIN: nichts gestempelt
    falsch = c.post(url, {"person": kim.pk, "pin": "000000"}).json()
    assert not falsch["ok"] and "PIN stimmt nicht" in falsch["fehler"]
    # Richtige PIN: Stand und mögliche Aktion
    stand = c.post(url, {"person": kim.pk, "pin": "482915"}).json()
    assert (
        stand["ok"] and stand["name"] == "Kim Probe" and stand["aktionen"] == [["kommen", "Kommen"]]
    )
    assert not Zeitbuchung.objects.exists()
    fertig = c.post(url, {"person": kim.pk, "pin": "482915", "aktion": "kommen"}).json()
    assert fertig["fertig"] and "Kim Probe: Kommen um" in fertig["meldung"]
    assert arbeitszeit.laufend(kim)
    stand = c.post(url, {"person": kim.pk, "pin": "482915"}).json()
    assert [a for a, _ in stand["aktionen"]] == ["pause", "gehen"]
    doppelt = c.post(url, {"person": kim.pk, "pin": "482915", "aktion": "kommen"}).json()
    assert not doppelt["ok"] and "schon eingestempelt" in doppelt["fehler"]
    c.post(url, {"person": kim.pk, "pin": "482915", "aktion": "gehen"})
    assert not arbeitszeit.laufend(kim) and Zeitbuchung.objects.get().ende
    # Mit der PIN einer Person, die nicht stempelt, geht nichts
    nein = c.post(url, {"person": ehrenamt.pk, "pin": "482915", "aktion": "kommen"}).json()
    assert not nein["ok"] and Zeitbuchung.objects.count() == 1
    # Nur QR-Code erlaubt: kein Stempeln mit PIN
    dienstplan_monitor.stempeln_pin = False
    dienstplan_monitor.save()
    assert c.post(url, {"person": kim.pk, "pin": "482915", "aktion": "kommen"}).status_code == 404
    assert "Mit Name und PIN" not in c.get(url).content.decode()


def test_nur_am_monitor_und_qr_code(dienstplan_monitor, kim, anmelden, monkeypatch):
    """„Stempeln nur am Monitor“: Unter „Meine Arbeitszeit“ fehlen die Knöpfe, bis der QR-Code
    am Monitor gescannt wurde; der Code gilt nur kurz und nur für diesen Monitor."""
    e = ArbeitszeitEinstellungen.laden()
    e.nur_am_monitor = True
    e.save()
    c = anmelden(Client(), kim)
    seite = c.get(reverse("personal:meine_arbeitszeit")).content.decode()
    assert "Stempeln geht nur am Aushang-Monitor" in seite and 'value="kommen"' not in seite
    c.post(reverse("personal:stempeln"), {"aktion": "kommen"})
    assert not Zeitbuchung.objects.exists()  # von zu Hause geht es nicht
    # Der Monitor liefert auf Anfrage einen frischen Code
    svg = Client().get(_url(dienstplan_monitor) + "?qr=1")
    assert svg.status_code == 200 and svg["Content-Type"] == "image/svg+xml"
    # Abgelaufener oder gefälschter Code: keine Freigabe
    assert stempeln.einloesen("unsinn") is None
    alt = signing.dumps({"a": dienstplan_monitor.pk}, salt=stempeln.SALZ)
    monkeypatch.setattr(stempeln, "GILT_SEKUNDEN", -1)
    antwort = c.get(reverse("aushang:stempeln_handy", args=[alt]), follow=True)
    assert "abgelaufen" in antwort.content.decode()
    c.post(reverse("personal:stempeln"), {"aktion": "kommen"})
    assert not Zeitbuchung.objects.exists()
    monkeypatch.setattr(stempeln, "GILT_SEKUNDEN", 90)
    # Gültiger Code: Knöpfe erscheinen, Stempeln geht
    marke = stempeln.marke(dienstplan_monitor)
    antwort = c.get(reverse("aushang:stempeln_handy", args=[marke]), follow=True)
    seite = antwort.content.decode()
    assert "Vor Ort bestätigt" in seite and 'value="kommen"' in seite
    c.post(reverse("personal:stempeln"), {"aktion": "kommen"})
    assert arbeitszeit.laufend(kim)
    # Am Monitor mit PIN geht es weiterhin, auch ohne Handy
    daten = {"person": kim.pk, "pin": "482915", "aktion": "gehen"}
    fertig = Client().post(_url(dienstplan_monitor), daten).json()
    assert fertig["fertig"]
    # Monitor ohne QR-Code: Die Marke wird nicht eingelöst
    dienstplan_monitor.stempeln_qr = False
    dienstplan_monitor.save()
    assert stempeln.einloesen(stempeln.marke(dienstplan_monitor)) is None
    assert Client().get(_url(dienstplan_monitor) + "?qr=1").status_code == 404


def test_qr_code_vor_der_anmeldung(dienstplan_monitor, kim, anmelden, benutzer_mit_rolle):
    """Wer am Handy noch nicht angemeldet ist, kommt zur Anmeldung; die Freigabe bleibt in der
    Sitzung. Wer keine Arbeitszeit erfasst, kann mit dem Code nichts anfangen."""
    e = ArbeitszeitEinstellungen.laden()
    e.nur_am_monitor = True
    e.save()
    c = Client()
    antwort = c.get(reverse("aushang:stempeln_handy", args=[stempeln.marke(dienstplan_monitor)]))
    assert antwort.status_code == 302 and reverse("konten:anmelden") in antwort.url
    assert arbeitszeit.SITZUNG_FREIGABE in c.session
    fremd = anmelden(Client(), benutzer_mit_rolle("eva", "Ausgabe"))
    antwort = fremd.get(
        reverse("aushang:stempeln_handy", args=[stempeln.marke(dienstplan_monitor)]), follow=True
    )
    assert "keine Arbeitszeit erfasst" in antwort.content.decode()


def test_pin_abschnitt_auf_mein_konto_auch_fuers_stempeln(kim, anmelden, recht_nehmen):
    """Die PIN brauchen jetzt auch Angestellte ohne Dienst- oder Fahrerplan."""
    for recht in ("dienstplan.sehen", "fahrdienst.sehen"):
        recht_nehmen("Ausgabe", recht)
    c = anmelden(Client(), get_user_model().objects.get(pk=kim.pk))
    assert "PIN für Aushang-Monitore" in c.get(reverse("konten:mein_konto")).content.decode()
