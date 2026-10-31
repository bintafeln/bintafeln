"""Der Helfer→Adressbuch-Umbau (ADR 0097) muss auch mit echten Daten durchlaufen.

Auf einem leeren Test-/CI-Server fällt der Fehler „cannot ALTER TABLE … pending trigger events"
nicht auf, weil die Daten-Migration nichts tut. Dieser Test baut den Stand *vor* dem Umbau nach,
legt echte Helfer samt Besetzung an und migriert dann vorwärts – so wie auf einem echten Server.
"""

import datetime as dt

import pytest
from django.db import connection
from django.db.migrations.executor import MigrationExecutor

pytestmark = pytest.mark.django_db(transaction=True)

VOR_UMBAU = {"dienstplan": "0003_wieder_gesund", "fahrdienst": "0006_wieder_gesund"}


def _migriere(ziele):
    executor = MigrationExecutor(connection)
    executor.migrate(ziele)
    executor.loader.build_graph()


def _leaves_mit(ersetzungen):
    executor = MigrationExecutor(connection)
    ziele = []
    for app, name in executor.loader.graph.leaf_nodes():
        ziele.append((app, ersetzungen.get(app, name)))
    return ziele


def test_umbau_mit_echten_daten():
    try:
        _umbau_mit_echten_daten()
    finally:
        # Schema in jedem Fall wieder auf den neuesten Stand bringen (sonst stören Folgetests).
        _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _umbau_mit_echten_daten():
    # 1) Auf den Stand vor dem Umbau zurück (Dienstplan/Fahrdienst alt, Adressbuch neu).
    ziele_vor = _leaves_mit(VOR_UMBAU)
    _migriere(ziele_vor)

    # Historische Modelle genau zu diesem Stand (sonst passen Felder nicht zur Datenbank).
    apps = MigrationExecutor(connection).loader.project_state(ziele_vor).apps
    Ausgabestelle = apps.get_model("kunden", "Ausgabestelle")
    DienstStelle = apps.get_model("dienstplan", "DienstStelle")
    Aufgabe = apps.get_model("dienstplan", "Aufgabe")
    Helfer = apps.get_model("dienstplan", "Helfer")
    DBesetzung = apps.get_model("dienstplan", "Besetzung")
    Benutzer = apps.get_model("konten", "Benutzer")
    Tour = apps.get_model("fahrdienst", "Tour")
    FBesetzung = apps.get_model("fahrdienst", "Besetzung")
    Group = apps.get_model("auth", "Group")

    # 2) Echte Daten anlegen: ein Helfer ohne Konto + fester Platz; ein Fahrer mit Konto.
    stelle = Ausgabestelle.objects.create(name="Mitte")
    ds = DienstStelle.objects.create(ausgabestelle=stelle, aktiv=True, tage="Fr")
    aufgabe = Aufgabe.objects.create(stelle=ds, wochentag="Fr", name="Kasse", reihenfolge=1,
                                     von=dt.time(9), bis=dt.time(15), pflicht=True)  # fmt: skip
    helfer = Helfer.objects.create(name="Max Muster", telefon="0123 4567")
    DBesetzung.objects.create(aufgabe=aufgabe, helfer=helfer)

    konto = Benutzer.objects.create(username="fahrer1", first_name="Kai", last_name="Fahrer")
    konto.groups.add(Group.objects.get_or_create(name="Fahrer")[0])
    tour = Tour.objects.create(name="Tour Nord", reihenfolge=1, plaetze=2, mindestbesetzung=2)
    FBesetzung.objects.create(tour=tour, wochentag="Fr", platz=1, benutzer=konto)

    # 3) Vorwärts migrieren – das ist der Schritt, der auf echten Daten gescheitert ist.
    _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())

    # 4) Prüfen: Helfer sind jetzt Personen im Adressbuch, die Pläne zeigen darauf.
    neu = MigrationExecutor(connection).loader.project_state().apps
    Adresse = neu.get_model("adressen", "Adresse")
    DBesetzung2 = neu.get_model("dienstplan", "Besetzung")
    FBesetzung2 = neu.get_model("fahrdienst", "Besetzung")

    assert Adresse.objects.filter(helfer=True, nachname="Muster").exists()
    assert Adresse.objects.filter(fahrdienst="fahrer", konto=konto.pk).exists()
    b = DBesetzung2.objects.get(aufgabe=aufgabe.pk)
    assert b.helfer_id and Adresse.objects.get(pk=b.helfer_id).helfer
    f = FBesetzung2.objects.get(tour=tour.pk)
    assert f.person_id and Adresse.objects.get(pk=f.person_id).fahrdienst == "fahrer"
