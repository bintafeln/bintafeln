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


def test_belege_aus_dem_vereinsportal_kommen_in_den_spendenpool(settings, tmp_path):
    """vereinsportal.0006 (ADR 0128): Schon eingelesene Belege werden Spenden mit Adresse und
    angehängtem PDF; die verschlüsselte Datei zieht mit um. Alle Daten sind erfunden."""
    settings.MEDIA_ROOT = tmp_path
    try:
        _belege_in_den_spendenpool()
    finally:
        _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _belege_in_den_spendenpool():
    from decimal import Decimal as D

    from apps.core import privatdateien

    ziele_vor = _leaves_mit({"vereinsportal": "0005_spendendatum"})
    _migriere(ziele_vor)
    alt = MigrationExecutor(connection).loader.project_state(ziele_vor).apps
    Beleg, Kontakt = (
        alt.get_model("vereinsportal", "Beleg"),
        alt.get_model("vereinsportal", "Kontakt"),
    )
    AdresseAlt, SpendeAlt = alt.get_model("adressen", "Adresse"), alt.get_model("spenden", "Spende")
    bekannt = AdresseAlt.objects.create(art="person", vorname="Otto", nachname="Muster",
                                        plz="12345", email="eigene@example.org")  # fmt: skip
    schon_da = SpendeAlt.objects.create(adresse=bekannt, datum=dt.date(2026, 5, 2),
                                        betrag=D("10"), belegnummer="3")  # fmt: skip
    Kontakt.objects.create(such_name="erika beispiel", vorname="Erika", nachname="Beispiel",
                           anrede="Frau", email="erika@example.org")  # fmt: skip
    datei = privatdateien.ablegen("vereinsportal", b"%PDF erfunden")

    def beleg(nummer, name, strasse, ort, **mehr):
        return Beleg.objects.create(
            dateiname=f"Spendenbeleg_{nummer:06d}.pdf", belegnummer=str(nummer), name=name,
            such_name=name.lower(), strasse=strasse, plz_ort=ort, jahr=2026,
            betrag=D("25"), datei=mehr.pop("datei", f"fehlt{nummer}.bin"), **mehr,
        )  # fmt: skip

    beleg(1, "Erika Beispiel", "Feldweg 2", "54321 Beispieldorf", datum=dt.date(2026, 3, 14),
          datei=datei, bedankt_am=dt.date(2026, 6, 1))  # fmt: skip
    beleg(2, "Erika Beispiel", "Feldweg 2", "54321 Beispieldorf", im_portal_versendet=True)
    beleg(3, "Otto Muster", "Am Markt 5", "12345 Musterstadt", datum=dt.date(2026, 5, 2))
    beleg(4, "Bäckerei Probe GmbH", "Hauptstraße 9", "12345 Musterstadt",
          datum=dt.date(2026, 7, 1))  # fmt: skip

    _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())

    from apps.adressen.models import Adresse
    from apps.spenden.models import Spende, SpendenBeleg

    erika = Adresse.objects.get(nachname="Beispiel")
    assert (erika.art, erika.vorname, erika.plz, erika.ort) == ("person", "Erika", "54321",
                                                                "Beispieldorf")  # fmt: skip
    assert (erika.email, erika.anrede) == ("erika@example.org", "Frau")
    assert erika.einwilligung_email is not None
    eins, zwei = erika.spenden.order_by("belegnummer")
    assert (eins.datum, eins.betrag, eins.fremdbeleg, eins.bedankt_am) == (
        dt.date(2026, 3, 14), D("25"), "offen", dt.date(2026, 6, 1))  # fmt: skip
    # ohne lesbares Datum: letzter Tag des Jahres, mit Vermerk
    assert (zwei.datum, zwei.fremdbeleg) == (dt.date(2026, 12, 31), "versendet")
    assert "nicht lesbar" in zwei.zweck
    # die verschlüsselte Datei ist mit umgezogen
    angehaengt = SpendenBeleg.objects.get(spende=eins)
    assert (angehaengt.dateiname, angehaengt.adresse) == ("Spendenbeleg_000001.pdf", erika)
    assert privatdateien.lesen(SpendenBeleg.ORDNER, angehaengt.datei) == b"%PDF erfunden"
    assert not privatdateien.pfad("vereinsportal", datei).exists()
    # vorhandene Adresse und vorhandene Spende werden wiederverwendet
    otto = Adresse.objects.get(nachname="Muster")
    assert otto.pk == bekannt.pk and otto.email == "eigene@example.org"
    assert otto.spenden.count() == 1
    assert Spende.objects.get(pk=schon_da.pk).fremdbeleg == "offen"
    firma = Adresse.objects.get(organisation="Bäckerei Probe GmbH")
    assert firma.art == "organisation" and firma.spenden.get().belegnummer == "4"
    assert SpendenBeleg.objects.count() == 4 and Spende.objects.count() == 4


def test_gemeinsame_zugangsdaten_werden_persoenlich():
    """vereinsportal.0008 (ADR 0129): Die bisher gemeinsamen Zugangsdaten gehen an das eine
    Konto mit derselben E-Mail; gibt es keins, entfallen sie. Alle Daten sind erfunden."""
    try:
        for konten, erwartet in ((["vera@example.org"], 1), (["x@example.org"], 0),
                                 (["vera@example.org", "VERA@example.org"], 0)):  # fmt: skip
            assert _zugang_nach_migration(konten) == erwartet
    finally:
        _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())


def _zugang_nach_migration(mails):
    ziele_vor = _leaves_mit({"vereinsportal": "0007_ohne_eigene_belege"})
    _migriere(ziele_vor)
    alt = MigrationExecutor(connection).loader.project_state(ziele_vor).apps
    Benutzer = alt.get_model("konten", "Benutzer")
    Benutzer.objects.all().delete()
    for nr, mail in enumerate(mails):
        Benutzer.objects.create(username=f"konto{nr}", email=mail)
    Benutzer.objects.create(username="inaktiv", email="vera@example.org", is_active=False)
    alt.get_model("vereinsportal", "PortalEinstellungen").objects.update_or_create(
        pk=1, defaults={"email": "vera@example.org", "passwort_verschluesselt": "verschluesselt"}
    )
    _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())
    neu = MigrationExecutor(connection).loader.project_state().apps
    zugaenge = list(neu.get_model("vereinsportal", "Zugang").objects.all())
    assert all(z.benutzer.username == "konto0" and z.passwort_verschluesselt == "verschluesselt"
               for z in zugaenge)  # fmt: skip
    return len(zugaenge)
