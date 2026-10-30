"""Zugriffsschutz aller Seiten (ADR 0033): Ein Test geht jede Adresse des Programms durch.

- Ohne Anmeldung führt jede Seite zur Anmeldung, außer den bewusst öffentlichen.
- Ein angemeldetes Konto ganz ohne Rechte bekommt überall „kein Zugriff“ (403), außer auf den
  Seiten, die jedem angemeldeten Konto gehören (Startseite, eigenes Konto, Handbuch …).

Neue Seiten fallen damit automatisch unter die Prüfung. Wer eine Seite bewusst öffentlich oder
für alle Angemeldeten macht, trägt sie unten ein; dann ist die Entscheidung im Review sichtbar.
Die Adressen werden mit Platzhaltern (Nummer 999999) aufgerufen: Die Rechteprüfung muss vor der
Suche nach dem Datensatz kommen, sonst verrät ein 404, welche Datensätze es gibt.
"""

import re

import pytest
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver
from django.urls.resolvers import RoutePattern

from apps.core import module
from apps.core.models import TafelEinstellungen

# Ohne Anmeldung erreichbar
OEFFENTLICH = {
    "konten:anmelden",
    "konten:passwort_vergessen",
    "konten:passwort_setzen",  # Link aus der Mail, prüft das Token
    "core:einrichtung",  # nur solange es keinen Admin gibt
    "core:healthz",
    "core:app_symbol",  # Symbol im Browser-Tab, auch auf der Anmeldeseite
    "core:manifest",
    "core:verzeichnis_melden",
    # Wartezeit aufs Handy für Kunden (ADR 0090): Kundennummer + Geburtsdatum oder Ausweis-Code
    "warten:seite",
    "warten:abmelden",
    "warten:code",  # Empfang der Verzeichnis-Meldungen, nur beim Herausgeber (ADR 0089)
    "antrag:start",  # Online-Antrag (ADR 0024)
    "antrag:formular",
    "antrag:danke",
    "antrag:rechtstext",  # Datenschutz/Impressum/Einverständnis als interner Text (ADR 0094)
    # Geräte am Aufruf ohne Anmeldung, nur mit dem Schlüssel im Link (ADR 0050)
    "aufruf:anzeige",
    "aufruf:monitor",
    "aufruf:abfrage",
    "aufruf:kiosk",
    "aufruf:anzeige_stand",
    "aufruf:anzeige_abfrage",
    "aufruf:anzeige_layout",
    "aufruf:anzeige_datei",
    # Aushang-Monitor ohne Anmeldung, nur mit dem Schlüssel im Link (ADR 0080)
    "aushang:anzeige",
    "aushang:platz",  # Ändern nur mit persönlicher PIN
}

# Für jedes angemeldete Konto, auch ohne Rechte
ALLE_ANGEMELDETEN = {
    "konten:anmelden_code",
    "konten:abmelden",
    "konten:mein_konto",
    "konten:benachrichtigungen",
    "konten:passwort_aendern",
    "konten:meine_auskunft",
    "konten:zwei_faktor_einrichten",
    "konten:notfallcodes_neu",
    "konten:zwei_faktor_abschalten",
    "konten:geraete_entfernen",
    "konten:geraet_entfernen",
    "core:start",
    "core:hilfe",
    "core:suche",
    "wetter:kopf",
    # Papierkorb: jedes Konto sieht nur Einträge mit seinen Rechten (ADR 0073)
    "core:papierkorb",
    "core:papierkorb_eintrag",
    "core:papierkorb_wiederherstellen",
    "core:papierkorb_loeschen",
    # Eigene PIN fürs Ändern am Aushang-Monitor (ADR 0080)
    "aushang:meine_pin",
    # Tickets: jede Person meldet und sieht ihre eigenen; fremde nur als Zuständige (ADR 0087)
    "tickets:liste",
    "tickets:neu",
    "tickets:ticket",
    "tickets:loeschen",
    "tickets:anhang",
}

PLATZHALTER = {
    "int": "999999",
    "path": "x9",
    "str": "x9",
    "slug": "x9",
    "uuid": "00000000-0000-0000-0000-000000000000",
}


def _muster(resolver=None, praefix="", namensraum=""):
    for eintrag in (resolver or get_resolver()).url_patterns:
        if isinstance(eintrag, URLResolver):
            ns = f"{namensraum}{eintrag.namespace}:" if eintrag.namespace else namensraum
            yield from _muster(eintrag, praefix + str(eintrag.pattern), ns)
        elif isinstance(eintrag, URLPattern):
            name = f"{namensraum}{eintrag.name}" if eintrag.name else None
            yield praefix + str(eintrag.pattern), name, eintrag


def seiten() -> list[tuple[str, str]]:
    """(Name, Adresse mit Platzhaltern) aller Seiten außer der Django-Verwaltung."""
    ergebnis = []
    for route, name, eintrag in _muster():
        if route.startswith("admin/"):
            continue  # eigene Prüfung unten
        assert isinstance(eintrag.pattern, RoutePattern), f"Regex-Adresse {route}: hier ergänzen"
        assert name, f"Adresse {route} hat keinen Namen"
        adresse = "/" + re.sub(
            r"<(?:(\w+):)?(\w+)>", lambda m: PLATZHALTER[m.group(1) or "str"], route
        )
        ergebnis.append((name, adresse))
    return ergebnis


def _abrufen(client, adresse):
    antwort = client.get(adresse)
    if antwort.status_code == 405:  # nur POST erlaubt
        antwort = client.post(adresse)
    return antwort


@pytest.fixture
def alle_module(db):
    t = TafelEinstellungen.laden()
    t.module = [m.kennung for m in module.alle()]
    t.save()


def test_listen_nennen_nur_vorhandene_seiten():
    namen = {name for name, _ in seiten()}
    assert namen >= OEFFENTLICH, OEFFENTLICH - namen
    assert namen >= ALLE_ANGEMELDETEN, ALLE_ANGEMELDETEN - namen
    assert not OEFFENTLICH & ALLE_ANGEMELDETEN


def test_ohne_anmeldung_nur_oeffentliche_seiten(client, admin, alle_module):
    offen = []
    for name, adresse in seiten():
        if name in OEFFENTLICH:
            continue
        antwort = _abrufen(client, adresse)
        if not (antwort.status_code == 302 and "/konten/anmelden/" in antwort["Location"]):
            offen.append(f"{adresse} ({name}): {antwort.status_code}")
    assert not offen, "Ohne Anmeldung erreichbar:\n" + "\n".join(offen)


def test_ohne_rechte_kein_zugriff(admin, alle_module, django_user_model, anmelden):
    gruppe = Group.objects.create(name="Ohne Rechte")
    konto = django_user_model.objects.create_user(username="ohne", password="Sicher-genug-123")
    konto.groups.add(gruppe)
    client = anmelden(Client(), konto)
    offen = []
    for name, adresse in seiten():
        if name in OEFFENTLICH or name in ALLE_ANGEMELDETEN:
            continue
        antwort = _abrufen(client, adresse)
        if antwort.status_code != 403:
            offen.append(f"{adresse} ({name}): {antwort.status_code}")
    assert not offen, "Ohne Rechte nicht mit 403 gesperrt:\n" + "\n".join(offen)


def test_django_verwaltung_nur_fuer_admins(client, admin, alle_module, django_user_model, anmelden):
    assert client.get("/admin/").status_code == 302
    konto = django_user_model.objects.create_user(username="ohne", password="Sicher-genug-123")
    antwort = anmelden(Client(), konto).get("/admin/")
    assert antwort.status_code == 302 and "login" in antwort["Location"]
