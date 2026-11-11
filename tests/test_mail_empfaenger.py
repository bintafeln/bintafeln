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
V = benachrichtigung.VORGABE


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


def einstellen(client, **wahl):
    """Speichert die Seite wie der Browser: alle Felder mit ihrem Stand, ``wahl`` geändert.
    Werte: Liste aus Konten und/oder ``V`` („wie vorgesehen“); leere Liste = niemand."""
    form = client.get(SEITE).context["form"]
    daten = {name: form[name].value() or [] for name in form.fields}
    for name, werte in wahl.items():
        daten[name] = [w if w == V else str(w.pk) for w in werte]
    antwort = client.post(SEITE, daten)
    assert antwort.status_code == 302
    return antwort


def test_auswahl_gilt_je_mail(admin_client, benutzer_mit_rolle):
    anna = konto(benutzer_mit_rolle, "anna")
    bert = konto(benutzer_mit_rolle, "bert")
    # Ausgangslage: „wie vorgesehen“ ist angehakt
    assert admin_client.get(SEITE).context["form"]["korrekturwunsch"].value() == [V]
    einstellen(admin_client, korrekturwunsch=[anna])
    assert korrekturen.empfaenger() == ["anna@example.org"]
    # die andere Mail bleibt bei der Vorgabe
    assert "bert@example.org" in update._empfaenger()
    einstellen(admin_client, sicherheitsupdate=[bert])
    assert update._empfaenger() == ["bert@example.org"]
    assert korrekturen.empfaenger() == ["anna@example.org"]  # unverändert
    # wieder „wie vorgesehen“: alle Berechtigten
    einstellen(admin_client, korrekturwunsch=[V])
    assert {"anna@example.org", "bert@example.org"} <= set(korrekturen.empfaenger())
    assert not MailEmpfaenger.objects.get(art="korrekturwunsch").personen.exists()


def test_nichts_angehakt_heisst_niemand(admin_client, benutzer_mit_rolle):
    """Wie beim neuen Antrag: Ohne Häkchen bekommt niemand die Mail – kein Extra-Haken nötig."""
    konto(benutzer_mit_rolle, "anna")
    seite = admin_client.get(SEITE).content.decode()
    assert "Niemand bekommt diese Mail" not in seite and 'name="niemand_' not in seite
    einstellen(admin_client, korrekturwunsch=[])
    assert korrekturen.empfaenger() == []
    assert "anna@example.org" in update._empfaenger()  # andere Mail unberührt
    assert admin_client.get(SEITE).context["form"]["korrekturwunsch"].value() == []


def test_vorgesehene_und_weitere_personen(admin_client, benutzer_mit_rolle):
    """„Wie vorgesehen“ und einzelne Personen lassen sich zusammen anhaken."""
    from apps.core.models import TafelEinstellungen

    e = TafelEinstellungen.laden()
    e.module = [*e.module, "dienstplan"]
    e.save()
    pia = konto(benutzer_mit_rolle, "pia", rollen.BUERO)
    einstellen(admin_client, dienstplan_ausfall=[V, pia])
    assert benachrichtigung.an("dienstplan_ausfall", ["leitung@example.org"]) == [
        "leitung@example.org", "pia@example.org",
    ]  # fmt: skip


def test_gesperrte_oder_ohne_recht_bekommen_nichts_mehr(admin_client, benutzer_mit_rolle):
    anna = konto(benutzer_mit_rolle, "anna")
    bert = konto(benutzer_mit_rolle, "bert")
    einstellen(admin_client, korrekturwunsch=[anna])
    assert korrekturen.empfaenger() == ["anna@example.org"]
    anna.is_active = False
    anna.save()
    # niemand Gültiges mehr ausgewählt: die Mail geht wieder an alle Berechtigten, nicht ins Leere
    assert korrekturen.empfaenger() == ["bert@example.org"]
    art = benachrichtigung.arten()["korrekturwunsch"]
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
    # bisher nur Pia ausgewählt: bleibt nur Pia, „wie vorgesehen“ ist nicht angehakt
    assert seite.context["form"]["fahrdienst_ausfall"].value() == [str(pia.pk)]
    assert plan.empfaenger() == ["pia@example.org"]
    einstellen(admin_client, fahrdienst_ausfall=[V])
    assert not FahrdienstEinstellungen.laden().benachrichtigen.exists()
    assert set(plan.empfaenger()) >= {"pia@example.org", "bob@example.org"}
    einstellen(admin_client, fahrdienst_ausfall=[])
    assert plan.empfaenger() == []


def test_nur_mit_recht(admin, benutzer_mit_rolle, anmelden):
    client = Client()
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(SEITE).status_code == 403
    assert client.post(SEITE, {}).status_code == 403


def test_alte_einstellungen_bleiben_beim_update(admin_client, benutzer_mit_rolle):
    """Ohne gespeicherten Stand gilt: niemand ausgewählt = wie vorgesehen, Personen ausgewählt =
    nur diese (so stand es vor dem Eintrag „wie vorgesehen“ in den Fahrdienst-Einstellungen)."""
    from apps.core.models import TafelEinstellungen
    from apps.fahrdienst.models import FahrdienstEinstellungen

    e = TafelEinstellungen.laden()
    e.module = [*e.module, "fahrdienst"]
    e.save()
    art = benachrichtigung.arten()["fahrdienst_ausfall"]
    assert benachrichtigung.vorgabe(art)
    FahrdienstEinstellungen.laden().benachrichtigen.set([konto(benutzer_mit_rolle, "pia")])
    assert not benachrichtigung.vorgabe(art)


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
    form = admin_client.get(SEITE).context["form"]
    for name in ("fahrdienst_gesund", "dienstplan_ausfall", "dienstplan_gesund", "ticket_neu"):
        werte = [w for w, _ in form.fields[name].choices]
        assert werte[0] == V and len(werte) > 1, name
    # Antwort auf ein Ticket: nur „wie vorgesehen“ oder niemand
    assert [w for w, _ in form.fields["ticket_antwort"].choices] == [V]
    # neuer Antrag: nur Personen, ohne Auswahl niemand
    assert V not in [w for w, _ in form.fields["antrag_neu"].choices]


def test_auswahl_ersetzt_die_vorgabe_im_einzelfall(admin_client, benutzer_mit_rolle):
    """Dienstplan, „wieder gesund“ und Tickets: „wie vorgesehen“ nimmt die Empfänger des
    Einzelfalls, eine Auswahl ohne diesen Haken nur die gewählten Personen, nichts = niemand."""
    _module_an("dienstplan")
    pia = konto(benutzer_mit_rolle, "pia", rollen.BUERO)
    vorgabe = ["teamleitung@example.org"]
    assert benachrichtigung.an("dienstplan_ausfall", vorgabe) == vorgabe
    einstellen(admin_client, dienstplan_ausfall=[pia])
    assert benachrichtigung.an("dienstplan_ausfall", vorgabe) == ["pia@example.org"]
    assert benachrichtigung.an("dienstplan_gesund", vorgabe) == vorgabe  # eigene Wahl je Mail
    einstellen(admin_client, dienstplan_ausfall=[])
    assert benachrichtigung.an("dienstplan_ausfall", vorgabe) == []
    # gesperrt: wieder die Vorgabe statt ins Leere
    einstellen(admin_client, dienstplan_ausfall=[pia])
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
    einstellen(admin_client, ticket_neu=[berta])
    assert neues() == ["berta@example.org"]
    einstellen(admin_client, ticket_neu=[])
    assert neues() == []
