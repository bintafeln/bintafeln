"""Freier Platz auf der Festplatte des Servers: Anzeige, Hinweis und Mail (ADR 0169)."""

import pytest
from django.core.management import call_command
from django.urls import reverse

from apps.core import speicherplatz
from apps.core.models import SpeicherWarnung

pytestmark = pytest.mark.django_db
GB = 1024**3
START, SEITE = reverse("core:start"), reverse("core:speicher")


@pytest.fixture
def platte(monkeypatch):
    """Die Festplatte hat 100 GB; ``platte(frei)`` stellt ein, wie viel davon frei ist."""
    wert = {"frei": 60 * GB}
    monkeypatch.setattr(speicherplatz, "_platte", lambda: (100 * GB, wert["frei"]))

    def setzen(gb):
        wert["frei"] = int(gb * GB)

    return setzen


@pytest.fixture
def mails(monkeypatch, admin):
    gesendet = []
    monkeypatch.setattr("apps.core.mail.senden", lambda betreff, text, an, **mehr: gesendet.append(
        (betreff, text, an)))  # fmt: skip
    monkeypatch.setattr("apps.core.mail.eingerichtet", lambda: True)
    admin.email = "chefin@example.org"
    admin.save()
    return gesendet


def test_stand_und_stufen(platte):
    s = speicherplatz.stand()
    assert (s.gesamt, s.frei, s.belegt, s.prozent_frei, s.prozent_belegt, s.stufe) == (
        100 * GB, 60 * GB, 40 * GB, 60, 40, "")  # fmt: skip
    platte(19.9)
    assert speicherplatz.stand().stufe == "knapp"
    platte(9.9)
    assert speicherplatz.stand().stufe == "dringend"
    e = SpeicherWarnung.laden()
    e.warnen_unter, e.dringend_unter = 5, 3
    e.save()
    assert speicherplatz.stand().stufe == ""


def test_nicht_lesbar(monkeypatch, admin_client):
    monkeypatch.setattr(speicherplatz, "_platte", lambda: None)
    assert speicherplatz.stand() is None and speicherplatz.melden(None) is False
    assert "nicht auslesen" in admin_client.get(SEITE).content.decode()
    assert admin_client.get(START).status_code == 200


def test_echte_platte_laesst_sich_lesen():
    s = speicherplatz.stand()
    assert s is not None and 0 < s.frei <= s.gesamt


def test_seite_zeigt_fuellstand_und_grenzen(admin_client, platte):
    seite = admin_client.get(SEITE).content.decode()
    assert "Festplatte des Servers" in seite and "40,0\xa0GB von 100,0\xa0GB belegt" in seite
    assert "60 %" in seite and 'style="width: 40%"' in seite
    antwort = admin_client.post(SEITE, {"aktion": "warnung", "warnung-warnen_unter": 70,
                                        "warnung-dringend_unter": 15})  # fmt: skip
    assert antwort.status_code == 302
    e = SpeicherWarnung.laden()
    assert (e.warnen_unter, e.dringend_unter) == (70, 15)
    assert "wird voll" in admin_client.get(SEITE).content.decode()
    # „dringend“ über der Warngrenze geht nicht
    antwort = admin_client.post(SEITE, {"aktion": "warnung", "warnung-warnen_unter": 10,
                                        "warnung-dringend_unter": 20})  # fmt: skip
    assert antwort.status_code == 200 and "unter der Warngrenze" in antwort.content.decode()
    assert SpeicherWarnung.laden().warnen_unter == 70


def test_hinweis_auf_der_startseite_nur_mit_recht(admin_client, platte, client, anmelden,
                                                  benutzer_mit_rolle):  # fmt: skip
    assert "Festplatte" not in admin_client.get(START).content.decode()
    platte(15)
    seite = admin_client.get(START).content.decode()
    assert "Die Festplatte des Servers wird voll." in seite and "15 %" in seite
    assert SEITE in seite
    platte(4)
    seite = admin_client.get(START).content.decode()
    assert "ist fast voll" in seite and "nichts mehr speichern" in seite
    anmelden(client, benutzer_mit_rolle("anton", "Ausgabe"))
    assert "Festplatte" not in client.get(START).content.decode()


def test_mail_einmal_je_stufe(admin_client, platte, mails):
    admin_client.get(START)
    assert not mails
    platte(15)
    admin_client.get(START)
    admin_client.get(START)
    call_command("benachrichtigungen_senden")
    assert len(mails) == 1
    betreff, text, an = mails[0]
    assert betreff == "bintafeln: Festplatte wird voll" and an == ["chefin@example.org"]
    assert "15,0 GB von 100,0 GB frei (15 %)" in text and "Speicher und Fotos" in text
    platte(5)  # dringend: noch einmal
    call_command("benachrichtigungen_senden")
    call_command("benachrichtigungen_senden")
    assert len(mails) == 2 and mails[1][0] == "bintafeln: Festplatte fast voll"
    platte(15)  # etwas besser, aber noch knapp: keine neue Mail
    admin_client.get(START)
    assert len(mails) == 2
    platte(60)  # wieder genug frei …
    admin_client.get(START)
    platte(15)  # … und später erneut knapp: neue Mail
    admin_client.get(START)
    assert len(mails) == 3 and SpeicherWarnung.laden().gemeldet == "knapp"


def test_ohne_empfaenger_keine_mail(admin_client, platte, monkeypatch):
    gesendet = []
    monkeypatch.setattr("apps.core.mail.senden", lambda *a, **k: gesendet.append(a))
    platte(5)
    assert admin_client.get(START).status_code == 200  # Admin ohne E-Mail: niemand bekommt sie
    assert not gesendet and SpeicherWarnung.laden().gemeldet == "dringend"


def test_steht_bei_den_mail_empfaengern(admin_client):
    seite = admin_client.get(reverse("core:mail_empfaenger")).content.decode()
    assert "Festplatte des Servers wird voll" in seite
