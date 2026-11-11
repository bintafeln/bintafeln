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

VOR_UMBAU = {"dienstplan": "0003_wieder_gesund", "fahrdienst": "0006_wieder_gesund",
             "adressen": "0006_adresse_fahrdienst"}  # fmt: skip


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


def test_mitarbeiter_werden_adressen():
    """adressen.0007: bestehende Mitarbeiter-Konten werden Personen im Adressbuch; die mit einer
    mitmachenden Rolle als Helfer (ADR 0097, Nachzügler-Migration)."""
    try:
        _mitarbeiter_werden_adressen()
    finally:
        _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _mitarbeiter_werden_adressen():
    # Nur das Adressbuch zurück vor 0007 (Dienstplan/Fahrdienst bleiben auf dem neuesten Stand).
    ziele_vor = _leaves_mit({"adressen": "0006_adresse_fahrdienst"})
    _migriere(ziele_vor)
    apps = MigrationExecutor(connection).loader.project_state(ziele_vor).apps
    Benutzer = apps.get_model("konten", "Benutzer")
    Group = apps.get_model("auth", "Group")
    Adresse = apps.get_model("adressen", "Adresse")

    ausgabe = Group.objects.get_or_create(name="Ausgabe")[0]
    helfer = Benutzer.objects.create(username="ria", first_name="Ria", last_name="Ausgabe")
    helfer.groups.add(ausgabe)
    buero = Benutzer.objects.create(username="bo", first_name="Bo", last_name="Büro")
    buero.groups.add(Group.objects.get_or_create(name="Büro")[0])
    assert not Adresse.objects.filter(konto_id=helfer.pk).exists()  # vorher keine Adresse

    _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())  # wendet 0007 an
    neu = MigrationExecutor(connection).loader.project_state().apps
    Adresse = neu.get_model("adressen", "Adresse")
    a_helfer = Adresse.objects.get(konto=helfer.pk)
    assert a_helfer.nachname == "Ausgabe"
    # Auch das Büro-Konto wird eine Person im Adressbuch
    assert Adresse.objects.filter(konto=buero.pk).exists()


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

    assert Adresse.objects.filter(nachname="Muster").exists()
    assert Adresse.objects.filter(konto=konto.pk).exists()
    b = DBesetzung2.objects.get(aufgabe=aufgabe.pk)
    assert b.helfer_id and Adresse.objects.get(pk=b.helfer_id).nachname == "Muster"
    f = FBesetzung2.objects.get(tour=tour.pk)
    assert f.person_id and Adresse.objects.get(pk=f.person_id).konto_id == konto.pk


def test_mail_empfaenger_stand_bleibt():
    """core.0033: Der Haken „Niemand bekommt diese Mail“ wird zum Eintrag „Wie vorgesehen“.
    Niemand bleibt niemand, ausgewählte Personen bleiben die einzigen, sonst wie vorgesehen."""
    try:
        _mail_empfaenger_stand_bleibt()
    finally:
        _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _mail_empfaenger_stand_bleibt():
    ziele_vor = _leaves_mit({"core": "0032_mail_niemand"})
    _migriere(ziele_vor)
    apps = MigrationExecutor(connection).loader.project_state(ziele_vor).apps
    Benutzer = apps.get_model("konten", "Benutzer")
    MailEmpfaenger = apps.get_model("core", "MailEmpfaenger")
    Fahrdienst = apps.get_model("fahrdienst", "FahrdienstEinstellungen")
    anna = Benutzer.objects.create(username="anna", email="anna@example.org")
    MailEmpfaenger.objects.create(art="korrekturwunsch", niemand=True).personen.add(anna)
    MailEmpfaenger.objects.create(art="sicherheitsupdate").personen.add(anna)
    MailEmpfaenger.objects.create(art="dienstplan_ausfall")
    MailEmpfaenger.objects.create(art="fahrdienst_ausfall")  # Auswahl liegt beim Fahrdienst
    Fahrdienst.objects.create(pk=1).benachrichtigen.add(anna)

    _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())

    from apps.core.models import MailEmpfaenger as Neu

    stand = {e.art: (e.vorgabe, e.personen.count()) for e in Neu.objects.all()}
    assert stand == {
        "korrekturwunsch": (False, 0),  # niemand
        "sicherheitsupdate": (False, 1),  # nur Anna
        "dienstplan_ausfall": (True, 0),  # wie vorgesehen
        "fahrdienst_ausfall": (False, 0),  # nur die beim Fahrdienst Gewählten
    }


def test_uebernahme_modul_umbenannt():
    """uebernahme.0001: Bestehende Installationen behalten Zuordnungen, eingeschaltetes Modul
    und Änderungsprotokoll, obwohl Modul und Tabelle jetzt anders heißen."""
    try:
        _uebernahme_modul_umbenannt()
    finally:
        _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _uebernahme_modul_umbenannt():
    from django.contrib.contenttypes.models import ContentType

    from apps.core.models import TafelEinstellungen
    from apps.uebernahme.models import UebernahmeEinstellungen

    alt_app, alt_tabelle = "bex" + "at", "bex" + "at_" + "bex" + "ateinstellungen"
    e = UebernahmeEinstellungen.laden()
    e.einkommensarten = {"6": "Rente"}
    e.save()
    tafel = TafelEinstellungen.laden()
    tafel.module = ["aufruf", "uebernahme"]
    tafel.save()
    # Zurück auf den Stand vor der Umbenennung: alte Tabelle, altes Modul, alter Eintrag
    _migriere([("uebernahme", None)])
    with connection.cursor() as c:
        assert alt_tabelle in connection.introspection.table_names(c)
        c.execute("SELECT count(*) FROM django_migrations WHERE app = %s", [alt_app])
        assert c.fetchone()[0] == 1
    assert TafelEinstellungen.laden().module == ["aufruf", alt_app]
    assert ContentType.objects.filter(app_label=alt_app).exists()

    _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())

    assert UebernahmeEinstellungen.laden().einkommensarten == {"6": "Rente"}
    assert TafelEinstellungen.laden().module == ["aufruf", "uebernahme"]
    with connection.cursor() as c:
        assert alt_tabelle not in connection.introspection.table_names(c)
        c.execute("SELECT count(*) FROM django_migrations WHERE app = %s", [alt_app])
        assert c.fetchone()[0] == 0
    assert not ContentType.objects.filter(app_label=alt_app).exists()
    assert ContentType.objects.filter(app_label="uebernahme").count() == 1
