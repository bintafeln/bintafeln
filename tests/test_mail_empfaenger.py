"""Zentrale Seite „Wer bekommt welche Mail“ (ADR 0125)."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.ausgabe import korrekturen
from apps.core import benachrichtigung, update
from apps.core.models import MailEmpfaenger
from apps.konten import rollen

pytestmark = pytest.mark.django_db

SEITE = reverse("core:mail_empfaenger")


def konto(benutzer_mit_rolle, name, rolle=rollen.ADMIN, email=None):
    b = benutzer_mit_rolle(name, rolle)
    b.email = f"{name}@example.org" if email is None else email
    b.save()
    return b


def test_ohne_auswahl_bekommen_alle_berechtigten_die_mail(admin, benutzer_mit_rolle):
    """Vorgabe wie bisher: alle aktiven Konten mit dem Recht und einer E-Mail-Adresse."""
    konto(benutzer_mit_rolle, "anna")
    konto(benutzer_mit_rolle, "bert")
    konto(benutzer_mit_rolle, "ohne", email="")
    konto(benutzer_mit_rolle, "aus", rollen.AUSGABE)  # darf nicht entscheiden
    erwartet = sorted(
        ["anna@example.org", "bert@example.org", *([admin.email] * bool(admin.email))]
    )
    assert korrekturen.empfaenger() == erwartet
    assert update._empfaenger() == erwartet


def test_auswahl_gilt_je_mail(admin_client, benutzer_mit_rolle):
    anna = konto(benutzer_mit_rolle, "anna")
    bert = konto(benutzer_mit_rolle, "bert")
    antwort = admin_client.post(SEITE, {"korrekturwunsch": [anna.pk]})
    assert antwort.status_code == 302
    assert korrekturen.empfaenger() == ["anna@example.org"]
    # die andere Mail bleibt bei der Vorgabe
    assert "bert@example.org" in update._empfaenger()
    admin_client.post(SEITE, {"korrekturwunsch": [anna.pk], "sicherheitsupdate": [bert.pk]})
    assert update._empfaenger() == ["bert@example.org"]
    # Auswahl wieder leeren: alle Berechtigten
    admin_client.post(SEITE, {})
    assert {"anna@example.org", "bert@example.org"} <= set(korrekturen.empfaenger())
    assert not MailEmpfaenger.objects.get(art="korrekturwunsch").personen.exists()


def test_gesperrte_oder_ohne_recht_bekommen_nichts_mehr(benutzer_mit_rolle, recht_nehmen):
    anna = konto(benutzer_mit_rolle, "anna")
    bert = konto(benutzer_mit_rolle, "bert")
    art = benachrichtigung.arten()["korrekturwunsch"]
    benachrichtigung.wahl_speichern(art, [anna])
    assert korrekturen.empfaenger() == ["anna@example.org"]
    anna.is_active = False
    anna.save()
    # niemand Gültiges mehr ausgewählt: die Mail geht wieder an alle Berechtigten, nicht ins Leere
    assert korrekturen.empfaenger() == ["bert@example.org"]
    assert bert.pk not in benachrichtigung.gewaehlt(art)


def test_seite_zeigt_alle_mails_und_wer_sie_bekommt(admin_client, benutzer_mit_rolle):
    konto(benutzer_mit_rolle, "anna")
    aus = konto(benutzer_mit_rolle, "aus", rollen.AUSGABE)
    aus.first_name, aus.last_name = "Aurel", "Ausgabe"
    aus.save()
    seite = admin_client.get(SEITE).content.decode()
    for text in ("Korrekturwunsch vom Einlass", "Sicherheitsupdate verfügbar",
                 "Neuer Antrag eingegangen", "Zugang und Passwort", "Eingangsbestätigung",
                 "Serienbrief per Mail", "Testmail",
                 "alle, die Korrekturwünsche entscheiden dürfen", "Mein Konto"):  # fmt: skip
        assert text in seite, text
    assert "anna@example.org" in seite
    assert "Aurel Ausgabe" not in seite  # ohne das Recht nicht zur Auswahl
    assert reverse("core:mails") in seite and reverse("antraege:einstellungen") in seite
    # im Menü unter Einstellungen
    assert SEITE in admin_client.get(reverse("core:start")).content.decode()


def test_mails_der_module_nur_wenn_eingeschaltet(admin_client):
    from apps.core.models import TafelEinstellungen

    assert "Fahrdienst: Ausfall" not in admin_client.get(SEITE).content.decode()
    e = TafelEinstellungen.laden()
    e.module = [*e.module, "fahrdienst", "warteliste"]
    e.save()
    seite = admin_client.get(SEITE).content.decode()
    assert "Fahrdienst: Ausfall" in seite and "alle, die den Fahrdienst planen dürfen" in seite
    assert "Warteliste: Einladung" in seite


def test_fahrdienst_auswahl_bleibt_in_den_fahrdienst_einstellungen(
    admin_client, benutzer_mit_rolle
):
    """Die bisherige Auswahl wandert nicht um: Die zentrale Seite bearbeitet dasselbe Feld."""
    from apps.core.models import TafelEinstellungen
    from apps.fahrdienst import plan
    from apps.fahrdienst.models import FahrdienstEinstellungen

    e = TafelEinstellungen.laden()
    e.module = [*e.module, "fahrdienst"]
    e.save()
    pia = konto(benutzer_mit_rolle, "pia", rollen.BUERO)
    konto(benutzer_mit_rolle, "bob", rollen.BUERO)
    FahrdienstEinstellungen.laden().benachrichtigen.set([pia])
    seite = admin_client.get(SEITE)
    assert seite.context["form"]["fahrdienst_ausfall"].value() == [pia.pk]
    admin_client.post(SEITE, {})
    assert not FahrdienstEinstellungen.laden().benachrichtigen.exists()
    assert set(plan.empfaenger()) >= {"pia@example.org", "bob@example.org"}


def test_nur_mit_recht(admin, benutzer_mit_rolle, anmelden):
    client = Client()
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(SEITE).status_code == 403
    assert client.post(SEITE, {}).status_code == 403


def test_niemand_bekommt_die_mail(admin_client, benutzer_mit_rolle):
    """„Niemand“ ist eine eigene Wahl: Dann geht die Mail an keinen, auch nicht an alle."""
    anna = konto(benutzer_mit_rolle, "anna")
    seite = admin_client.get(SEITE).content.decode()
    assert 'name="niemand_korrekturwunsch"' in seite and 'name="niemand_sicherheitsupdate"' in seite
    assert 'name="niemand_antrag_neu"' not in seite  # dort heißt „keine Auswahl“ schon niemand
    admin_client.post(SEITE, {"niemand_korrekturwunsch": "on", "korrekturwunsch": [anna.pk]})
    assert korrekturen.empfaenger() == []
    assert "anna@example.org" in update._empfaenger()  # andere Mail unberührt
    seite = admin_client.get(SEITE)
    assert seite.context["form"]["niemand_korrekturwunsch"].value() is True
    assert "Bekommt sie im Moment: niemand." in seite.content.decode()
    # Haken wieder weg: die Auswahl gilt wieder
    admin_client.post(SEITE, {"korrekturwunsch": [anna.pk]})
    assert korrekturen.empfaenger() == ["anna@example.org"]


def test_niemand_auch_beim_fahrdienst(admin_client, benutzer_mit_rolle):
    from apps.core.models import TafelEinstellungen
    from apps.fahrdienst import plan

    e = TafelEinstellungen.laden()
    e.module = [*e.module, "fahrdienst"]
    e.save()
    konto(benutzer_mit_rolle, "pia", rollen.BUERO)
    assert "pia@example.org" in plan.empfaenger()
    admin_client.post(SEITE, {"niemand_fahrdienst_ausfall": "on"})
    assert plan.empfaenger() == []


def _module_an(*namen):
    from apps.core.models import TafelEinstellungen

    e = TafelEinstellungen.laden()
    e.module = [*e.module, *namen]
    e.save()


def test_alle_benachrichtigungen_haben_eine_wahl(admin_client, benutzer_mit_rolle):
    """Jede Benachrichtigung lässt sich einstellen: Personen wählen oder ganz abstellen."""
    _module_an("fahrdienst", "dienstplan", "tickets")
    konto(benutzer_mit_rolle, "anna")
    for art in benachrichtigung.arten().values():
        assert art.wahl is not None, art.kennung
    seite = admin_client.get(SEITE).content.decode()
    for name in ("fahrdienst_gesund", "dienstplan_ausfall", "dienstplan_gesund", "ticket_neu"):
        assert f'name="{name}"' in seite and f'name="niemand_{name}"' in seite, name
    # Antwort auf ein Ticket: geht an die meldende Person, lässt sich nur abstellen
    assert 'name="niemand_ticket_antwort"' in seite and 'name="ticket_antwort"' not in seite


def test_auswahl_ersetzt_die_vorgabe_im_einzelfall(admin_client, benutzer_mit_rolle):
    """Dienstplan, „wieder gesund“ und Tickets: ohne Auswahl die Vorgabe des Einzelfalls,
    mit Auswahl die gewählten Personen, mit „niemand“ keiner."""
    _module_an("dienstplan")
    pia = konto(benutzer_mit_rolle, "pia", rollen.BUERO)
    vorgabe = ["teamleitung@example.org"]
    assert benachrichtigung.an("dienstplan_ausfall", vorgabe) == vorgabe
    admin_client.post(SEITE, {"dienstplan_ausfall": [pia.pk]})
    assert benachrichtigung.an("dienstplan_ausfall", vorgabe) == ["pia@example.org"]
    assert benachrichtigung.an("dienstplan_gesund", vorgabe) == vorgabe  # eigene Wahl je Mail
    admin_client.post(SEITE, {"dienstplan_ausfall": [pia.pk], "niemand_dienstplan_ausfall": "on"})
    assert benachrichtigung.an("dienstplan_ausfall", vorgabe) == []
    # gesperrt: wieder die Vorgabe statt ins Leere
    admin_client.post(SEITE, {"dienstplan_ausfall": [pia.pk]})
    pia.is_active = False
    pia.save()
    assert benachrichtigung.an("dienstplan_ausfall", vorgabe) == vorgabe
    # ausgeschaltetes Modul oder unbekannte Art: die Vorgabe
    assert benachrichtigung.an("ticket_neu", vorgabe) == vorgabe


def test_ticket_mails_folgen_der_wahl(admin, admin_client, benutzer_mit_rolle,
                                      django_capture_on_commit_callbacks):  # fmt: skip
    from django.core import mail as djmail

    from apps.core.models import MailEinstellungen
    from apps.tickets import ablauf
    from apps.tickets.models import Kategorie

    _module_an("tickets")
    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    theo = konto(benutzer_mit_rolle, "theo", rollen.AUSGABE)
    berta = konto(benutzer_mit_rolle, "berta", rollen.BUERO)  # darf alle Tickets bearbeiten
    technik = Kategorie.objects.create(name="Technik")
    technik.personen.add(theo)

    def neues():
        djmail.outbox.clear()
        with django_capture_on_commit_callbacks(execute=True):
            ablauf.eroeffnen(admin, technik, "Waage defekt", "Zeigt nichts an")
        return sorted(a for mail_ in djmail.outbox for a in mail_.to)

    assert neues() == ["theo@example.org"]  # Vorgabe: Zuständige der Kategorie
    admin_client.post(SEITE, {"ticket_neu": [berta.pk]})
    assert neues() == ["berta@example.org"]
    admin_client.post(SEITE, {"niemand_ticket_neu": "on"})
    assert neues() == []
