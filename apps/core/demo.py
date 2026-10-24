"""Öffentliche Demo: setzt die Installation auf erfundene Beispieldaten zurück (ADR 0022).

Nur mit BINTAFELN_DEMO=true. Alle Daten der Installation werden dabei gelöscht.
"""

import datetime as dt
import shutil
from decimal import Decimal
from importlib import import_module
from pathlib import Path

from auditlog.context import disable_auditlog
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone

from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.konten.models import DokumentKategorie, Rolle, Stammdaten
from apps.kunden import importieren
from apps.kunden.models import Dokumentart, Zusatzfeld
from apps.personal.models import Arbeitsvertrag, Zeitbuchung

BEISPIELE = Path(settings.BASE_DIR) / "docs" / "beispiele" / "import"

# Benutzername, Vorname, Nachname, Rollen, fest angestellt – alles erfunden.
KONTEN = [
    ("demo-admin", "Ada", "Admin", [rollen.ADMIN], False),
    ("demo-buero", "Berta", "Büro", [rollen.BUERO], False),
    ("demo-ausgabe", "Anton", "Ausgabe", [rollen.AUSGABE], False),
    ("demo-personal", "Paula", "Personal", [rollen.PERSONAL], False),
    ("demo-fest", "Frieda", "Fest", [rollen.AUSGABE, rollen.FAHRER], True),
]


def fremde_konten() -> list[str]:
    """Konten, die nicht von der Demo stammen: Hinweis auf eine echte Installation."""
    konten = get_user_model().objects.exclude(username__startswith="demo-")
    return list(konten.order_by("username").values_list("username", flat=True)[:3])


def zuruecksetzen(heute: dt.date | None = None, erzwingen: bool = False) -> None:
    if not settings.DEMO:
        raise ImproperlyConfigured("Nur im Demo-Betrieb (BINTAFELN_DEMO=true) erlaubt.")
    if not settings.DEMO_PASSWORT:
        raise ImproperlyConfigured("BINTAFELN_DEMO_PASSWORT fehlt in .env.")
    fremde = fremde_konten()
    if fremde and not erzwingen:
        raise ImproperlyConfigured(
            f"Abbruch: Diese Datenbank enthält Konten, die nicht aus der Demo stammen "
            f"({', '.join(fremde)}). Das sieht nach einer echten Installation aus; es wurde "
            "nichts gelöscht. Bitte prüfen, ob der Befehl im richtigen Ordner läuft."
        )
    heute = heute or timezone.localdate()
    call_command("flush", interactive=False, verbosity=0)
    _medien_leeren()
    with transaction.atomic(), disable_auditlog():
        _grundlagen()
        konten = _konten()
        _kunden(konten["demo-admin"], heute)
        _arbeitszeit(konten["demo-fest"], heute)


def _medien_leeren() -> None:
    wurzel = Path(settings.MEDIA_ROOT)
    if wurzel.is_dir():
        for eintrag in wurzel.iterdir():
            if eintrag.is_dir():
                shutil.rmtree(eintrag)
            else:
                eintrag.unlink()


def _grundlagen() -> None:
    """Was sonst die Migrationen anlegen: Rollen und Dokumentkategorien."""
    rollen.vorgaben_wiederherstellen()
    Rolle.objects.update(zwei_faktor_pflicht=False)  # Demo: Einrichtung ist gesperrt
    for name, monate in import_module("apps.kunden.migrations.0013_dokumente").VORGABEN:
        Dokumentart.objects.get_or_create(bezeichnung=name, defaults={"aufbewahren_monate": monate})
    for name, nur_personal in import_module("apps.konten.migrations.0006_dokumente").VORGABEN:
        DokumentKategorie.objects.get_or_create(name=name, defaults={"nur_personal": nur_personal})
    e = TafelEinstellungen.laden()
    e.name = "Demo-Tafel Musterstadt"
    e.strasse, e.plz, e.ort = "Musterweg 1", "12345", "Musterstadt"
    e.bundesland = "NW"
    e.save()


def _konten() -> dict:
    konten = {}
    for name, vorname, nachname, namen, fest in KONTEN:
        b = get_user_model().objects.create_user(
            username=name, password=settings.DEMO_PASSWORT, first_name=vorname,
            last_name=nachname, email=f"{name}@example.org",
        )  # fmt: skip
        b.is_superuser = name == "demo-admin"  # ohne is_staff: kein Zugang zur Django-Verwaltung
        if fest:
            b.beschaeftigung = b.Beschaeftigung.FEST
        b.save()
        b.groups.set(Group.objects.filter(name__in=namen))
        Stammdaten.objects.create(
            benutzer=b, strasse="Beispielstraße 2", plz="12345", ort="Musterstadt",
            eintritt=dt.date(2024, 1, 1), fs_klassen="B" if fest else "",
        )  # fmt: skip
        konten[name] = b
    return konten


def _kunden(admin, heute) -> None:
    Zusatzfeld.objects.create(
        schluessel="schwerbehindert", bezeichnung="Schwerbehindert",
        gilt_fuer=Zusatzfeld.GiltFuer.PERSON, typ=Zusatzfeld.Typ.JA_NEIN,
    )  # fmt: skip
    dateien = {d.name: d.read_bytes() for d in sorted(BEISPIELE.glob("*.csv"))}
    ergebnis = importieren.pruefen(dateien, heute)
    if ergebnis.fehler:
        raise ImproperlyConfigured(f"Beispieldaten fehlerhaft: {ergebnis.fehler}")
    importieren.uebernehmen(
        ergebnis.daten, benutzer=admin, dateien=ergebnis.dateien,
        pruefsumme=ergebnis.pruefsumme, anzahl_warnungen=len(ergebnis.warnungen),
    )  # fmt: skip


def _arbeitszeit(fest, heute) -> None:
    Arbeitsvertrag.objects.create(
        benutzer=fest, beginn=heute.replace(month=1, day=1), taetigkeit="Fahrdienst",
        wochenstunden=Decimal("30"), urlaubstage=Decimal("30"), stundenlohn=Decimal("14.50"),
    )  # fmt: skip
    zeitzone = timezone.get_current_timezone()
    for tage in range(1, 8):
        tag = heute - dt.timedelta(days=tage)
        if tag.weekday() < 5:
            Zeitbuchung.objects.create(
                benutzer=fest,
                beginn=dt.datetime.combine(tag, dt.time(8, 0), zeitzone),
                ende=dt.datetime.combine(tag, dt.time(14, 30), zeitzone),
            )
