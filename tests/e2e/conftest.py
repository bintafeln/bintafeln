"""Browser-Tests mit Playwright (ADR 0066): ein echter Chromium gegen den Testserver.

Laufen nur mit ``pytest -m e2e`` und brauchen ``requirements-e2e.txt`` samt Browser
(``playwright install --with-deps chromium``). Ein schon vorhandener Chromium lässt sich mit
``BINTAFELN_E2E_CHROMIUM=/pfad/zu/chrome`` nutzen.
"""

import os

import pytest
from django.conf import settings
from django.test import Client

try:
    from playwright import sync_api as playwright
except ImportError:  # requirements-e2e.txt nicht installiert: Browser-Tests gar nicht sammeln
    playwright = None
    collect_ignore_glob = ["test_*.py"]

# Playwright läuft mit eigener Ereignisschleife; die Datenbankzugriffe der Tests sind trotzdem
# synchron und finden im Test-Thread statt.
os.environ.setdefault("DJANGO_ALLOW_ASYNC_UNSAFE", "true")


def pytest_collection_modifyitems(items):
    for item in items:
        if "/e2e/" in str(item.fspath):
            item.add_marker(pytest.mark.e2e)
            # Der Testserver sieht nur Daten aus abgeschlossenen Transaktionen; die Daten aus den
            # Migrationen (Rollen, Rechte) kommen nach jedem Test zurück.
            item.add_marker(pytest.mark.django_db(transaction=True, serialized_rollback=True))


@pytest.fixture(scope="session")
def browser():
    with playwright.sync_playwright() as p:
        b = p.chromium.launch(
            executable_path=os.environ.get("BINTAFELN_E2E_CHROMIUM") or None,
            # Kamera-Scanner: Testbild statt echter Kamera, ohne Rückfrage
            args=["--use-fake-device-for-media-stream", "--use-fake-ui-for-media-stream"],
            # Deutsche Datumsfelder (TT.MM.JJJJ) wie bei den Tafeln, z. B. für die Hilfe-Bilder
            env={**os.environ, "LANG": "de_DE.UTF-8", "LANGUAGE": "de"},
        )
        yield b
        b.close()


@pytest.fixture
def seite(browser, live_server):
    """Neue Browser-Seite; JavaScript-Fehler auf der Seite lassen den Test scheitern."""
    kontext = browser.new_context(
        base_url=live_server.url, locale="de-DE", viewport={"width": 1280, "height": 900}
    )
    kontext.set_default_timeout(10_000)
    page = kontext.new_page()
    fehler = []
    page.on("pageerror", lambda e: fehler.append(f"JavaScript: {e}"))

    def konsole(meldung):
        # Ein eigenes Symbol (favicon) hat bintafeln nicht; danach fragt jeder Browser.
        if meldung.type == "error" and "favicon.ico" not in meldung.location.get("url", ""):
            fehler.append(f"Konsole: {meldung.text} ({meldung.location.get('url')})")

    page.on("console", konsole)
    yield page
    kontext.close()
    assert not fehler, "\n".join(fehler)


@pytest.fixture
def angemeldet(seite, live_server, anmelden):
    """Meldet ein Konto im Browser an (wie nach der Zwei-Faktor-Anmeldung)."""

    def ausfuehren(benutzer):
        client = anmelden(Client(), benutzer)
        sitzung = client.cookies[settings.SESSION_COOKIE_NAME].value
        seite.context.add_cookies(
            [{"name": settings.SESSION_COOKIE_NAME, "value": sitzung, "url": live_server.url}]
        )
        return seite

    return ausfuehren


@pytest.fixture
def muster(admin):
    """Eine erfundene Tafel mit zwei Ausgabestellen und einem Haushalt, der heute dran ist
    (für die Bilder im Handbuch, ``hilfe_bilder.py``). Die angemeldete Chefin heißt „Clara
    Beispiel“ und arbeitet an der Ausgabestelle Mitte."""
    import datetime as dt

    from django.utils import timezone

    from apps.core.models import TafelEinstellungen
    from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe, Notiz, Person

    t = TafelEinstellungen.laden()
    t.name = "Tafel Musterstadt"
    t.save()
    mitte = Ausgabestelle.objects.create(name="Ausgabestelle Mitte")
    Ausgabestelle.objects.create(name="Ausgabestelle Nord")
    gruppe = Kundengruppe.objects.create(kuerzel="A", name="Gruppe A", ausgabestelle=mitte,
                                         wochentage="Mo, Di, Mi, Do, Fr, Sa, So")  # fmt: skip
    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="00042", kundengruppe=gruppe,
                                ausweis_gueltig_bis=heute + dt.timedelta(days=150))  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster",
                          geburtsdatum=dt.date(1961, 4, 12))  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Max", nachname="Muster",
                          geburtsdatum=dt.date(2014, 9, 3))  # fmt: skip
    Notiz.objects.create(kundennummer="00042", verfasst_von="Büro",
                         text="Bringt nächste Woche den neuen Bescheid mit.")  # fmt: skip
    admin.first_name, admin.last_name = "Clara", "Beispiel"
    admin.gewaehlte_stelle = mitte
    admin.save()
    return h
