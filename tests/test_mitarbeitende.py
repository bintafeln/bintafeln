import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.konten import rollen, verwaltung
from apps.konten.models import Rolle
from tests.conftest import PASSWORT

pytestmark = pytest.mark.django_db

LISTE = reverse("konten:mitarbeitende")
ARCHIV = reverse("konten:mitarbeitende_archiv")
NEU = reverse("konten:mitarbeiter_neu")
PASSWORT_AENDERN = reverse("konten:passwort_aendern")


def url(name, ziel):
    return reverse(f"konten:{name}", args=[ziel.pk])


@pytest.fixture
def als(client, admin, benutzer_mit_rolle, anmelden):
    def anmelden_als(rolle, name=None):
        benutzer = benutzer_mit_rolle(name or rolle.lower(), rolle)
        return anmelden(client, benutzer), benutzer

    return anmelden_als


@pytest.fixture
def buero_freigegeben():
    Rolle.objects.filter(gruppe__name="Büro").update(
        rechte=Rolle.objects.get(gruppe__name="Büro").rechte + ["mitarbeitende.verwalten"]
    )


def neu(client, **daten):
    werte = {"username": "max", "first_name": "Max", "last_name": "Beispiel",
             "beschaeftigung": "ehrenamtlich", "rollen": [rollen.AUSGABE], **daten}  # fmt: skip
    return client.post(NEU, werte)


# --- Rollen und Zugang -------------------------------------------------------------------


def test_neue_rollen_fahrer_und_beifahrer():
    assert {"Fahrer", "Beifahrer"} <= set(Group.objects.values_list("name", flat=True))
    namen = [r.name for r in rollen.alle_rollen()]
    assert namen[-3:] == [rollen.FAHRER, rollen.BEIFAHRER, rollen.PERSONAL]


@pytest.mark.parametrize("rolle", [rollen.BUERO, rollen.AUSGABE, rollen.FAHRER])
def test_ohne_freigabe_kein_zugang(als, rolle):
    client, _ = als(rolle)
    assert client.get(LISTE).status_code == 403
    assert "Ehrenamtliche</a>" not in client.get("/").content.decode()


def test_admin_sieht_liste_und_archiv(admin_client):
    assert "Ehrenamtliche</a>" in admin_client.get("/").content.decode()
    inhalt = admin_client.get(LISTE).content.decode()
    assert "chefin" in inhalt and "Konto anlegen" in inhalt
    assert "Keine gesperrten Konten." in admin_client.get(ARCHIV).content.decode()


def test_liste_suche(admin_client):
    U = get_user_model()
    U.objects.create_user("anna.albrecht", first_name="Anna", last_name="Albrecht",
                          beschaeftigung="ehrenamtlich")  # fmt: skip
    U.objects.create_user("bodo.bauer", first_name="Bodo", last_name="Bauer",
                          beschaeftigung="ehrenamtlich")  # fmt: skip
    ehren = reverse("konten:ehrenamtliche")
    # Suchfeld ist da; ohne Suche beide Konten
    seite = admin_client.get(ehren)
    assert 'name="q"' in seite.content.decode()
    namen = {z["b"].username for z in seite.context["zeilen"]}
    assert {"anna.albrecht", "bodo.bauer"} <= namen
    # Nach Nachname filtern (auch über htmx nur der Ergebnisbereich)
    treffer = admin_client.get(ehren, {"q": "albrecht"}, HTTP_HX_REQUEST="true")
    gefunden = [z["b"].username for z in treffer.context["zeilen"]]
    assert gefunden == ["anna.albrecht"]
    assert "bodo.bauer" not in treffer.content.decode()
    # Nach Benutzername
    nach_login = admin_client.get(ehren, {"q": "bodo.b"}).context["zeilen"]
    assert [z["b"].username for z in nach_login] == ["bodo.bauer"]
    # Kein Treffer
    leer = admin_client.get(ehren, {"q": "gibtsnicht"})
    assert leer.context["zeilen"] == [] and "Keine Treffer" in leer.content.decode()


def test_liste_spalten_sortieren_export(admin_client):
    from apps.konten.models import Stammdaten

    U = get_user_model()
    zora = U.objects.create_user("zora.zimmer", first_name="Zora", last_name="Zimmer",
                                 beschaeftigung="ehrenamtlich")  # fmt: skip
    anna = U.objects.create_user("anna.albrecht", first_name="Anna", last_name="Albrecht",
                                 beschaeftigung="ehrenamtlich")  # fmt: skip
    Stammdaten.objects.create(benutzer=zora, ort="Zwickau", telefon="0999", strasse="Weg 9")
    Stammdaten.objects.create(benutzer=anna, ort="Aachen", telefon="0111", strasse="Weg 1")
    ehren = reverse("konten:ehrenamtliche")

    # Getrennte Spalten + Anschrift/Telefon standardmäßig sichtbar
    seite = admin_client.get(ehren)
    inhalt = seite.content.decode()
    assert "Nachname" in inhalt and "Zwickau" in inhalt and "0111" in inhalt
    assert "telefon" in seite.context["sichtbar"]  # Vorgabe: alles sichtbar
    namen = [z["b"].last_name for z in seite.context["zeilen"]]
    assert namen.index("Albrecht") < namen.index("Zimmer")  # Vorgabe nach Nachname sortiert

    # Nach Ort sortieren
    sortiert = admin_client.get(ehren, {"sort": "ort"}).context["zeilen"]
    orte = [z["sd"].ort for z in sortiert if z["sd"].ort]
    assert orte == sorted(orte)

    # Spalten abwählen (nur Vorname und Ort behalten) und zurück zur selben Liste
    antwort = admin_client.post(
        reverse("konten:mitarbeitende_spalten"), {"spalte": ["vorname", "ort"]}, HTTP_REFERER=ehren
    )
    assert antwort.status_code == 302
    sichtbar = admin_client.get(ehren).context["sichtbar"]
    assert "telefon" not in sichtbar and {"vorname", "ort"} <= sichtbar

    # CSV-Export: alle Felder, egal welche Spalten sichtbar sind
    csv = admin_client.get(ehren, {"aktion": "csv"})
    assert csv["Content-Type"].startswith("text/csv")
    text = csv.content.decode("utf-8-sig")
    assert "Nachname;Vorname;Anrede;Straße" in text
    assert "Zimmer;Zora" in text and "0999" in text and "Weg 9" in text

    # PDF-Export (zum Drucken)
    pdf = admin_client.get(ehren, {"aktion": "pdf"})
    assert pdf["Content-Type"] == "application/pdf"


def test_personalnummer_automatisch_und_gemeinsame_reihe(admin_client):
    import datetime as dt

    from apps.adressen.models import Adresse
    from apps.konten.models import Stammdaten
    from apps.mitglieder.models import Mitglied, MitgliederEinstellungen

    # Ein Mitglied mit Nummer 5 existiert; die Reihe steht bei 5
    a = Adresse.objects.create(art=Adresse.Art.PERSON, nachname="Alt")
    Mitglied.objects.create(adresse=a, nummer="5", art="foerder", eintritt=dt.date(2020, 1, 1))
    e = MitgliederEinstellungen.laden()
    e.naechste_nummer = 5
    e.save()

    # Neue Mitarbeitende bekommen automatisch Nummern aus derselben Reihe – nicht die belegte 5
    neu(admin_client, username="neo.neu", first_name="Neo", last_name="Neu")
    neo = get_user_model().objects.get(username="neo.neu")
    assert neo.stammdaten.personalnummer == 6  # 5 ist belegt → 6
    neu(admin_client, username="pia.platz", first_name="Pia", last_name="Platz")
    assert Stammdaten.objects.get(benutzer__username="pia.platz").personalnummer == 7

    # Die Nummer erscheint in der Liste
    inhalt = admin_client.get(reverse("konten:ehrenamtliche")).content.decode()
    assert '<td data-titel="Nummer">6</td>' in inhalt


def test_personalnummer_mitglied_zeigt_mitgliedsnummer(admin_client):
    import datetime as dt

    from apps.adressen.models import Adresse
    from apps.mitglieder.models import Mitglied

    neu(admin_client, username="mia.mit", first_name="Mia", last_name="Mitglied")
    b = get_user_model().objects.get(username="mia.mit")
    # Mia ist zugleich Mitglied → in der Liste zählt ihre Mitgliedsnummer, nicht die Personalnummer
    Mitglied.objects.create(
        adresse=Adresse.objects.get(konto=b), nummer="99", art="aktiv", eintritt=dt.date(2021, 1, 1)
    )
    assert verwaltung.personennummer(b) == "99"


def test_admin_mitarbeiternummer_selbst_setzen(admin_client):
    from apps.konten.forms import StammdatenForm
    from apps.konten.models import Stammdaten
    from apps.mitglieder.models import MitgliederEinstellungen

    neu(admin_client, username="nia.neu", first_name="Nia", last_name="Neu")
    b = get_user_model().objects.get(username="nia.neu")
    url = reverse("konten:stammdaten", args=[b.pk])
    assert "Mitarbeiternummer" in admin_client.get(url).content.decode()  # Admin sieht das Feld
    admin_client.post(url, {"personalnummer": "1234"})
    assert Stammdaten.objects.get(benutzer=b).personalnummer == 1234
    assert MitgliederEinstellungen.laden().naechste_nummer > 1234  # Reihe rückt darüber hinaus

    # Dieselbe Nummer bei einer anderen Person wird abgelehnt.
    neu(admin_client, username="olf.ohne", first_name="Olf", last_name="Ohne")
    c = get_user_model().objects.get(username="olf.ohne")
    c_url = reverse("konten:stammdaten", args=[c.pk])
    antwort = admin_client.post(c_url, {"personalnummer": "1234"})
    assert "schon an eine andere Person" in antwort.content.decode()
    assert Stammdaten.objects.get(benutzer=c).personalnummer != 1234

    # Ohne das Recht (Vorgabe für Nicht-Admins) gibt es das Feld nicht.
    assert "personalnummer" not in StammdatenForm(instance=Stammdaten(benutzer=b)).fields
    with_feld = StammdatenForm(instance=Stammdaten(benutzer=b), nummer_erlaubt=True)
    assert "personalnummer" in with_feld.fields


def test_liste_nach_nummer_sortieren(admin_client):
    from apps.konten.models import Stammdaten

    U = get_user_model()
    for name, pn in [("Zimmer", 2), ("Albrecht", 10), ("Berg", 1)]:
        b = U.objects.create_user(name.lower(), last_name=name, first_name=name,
                                  beschaeftigung="ehrenamtlich")  # fmt: skip
        Stammdaten.objects.create(benutzer=b, personalnummer=pn)
    ehren = reverse("konten:ehrenamtliche")

    # Nur die Nummern (das Admin-Konto hat keine und steht in beiden Richtungen hinten).
    auf = [z["nummer"] for z in admin_client.get(ehren, {"sort": "nummer"}).context["zeilen"]]
    assert auf == ["1", "2", "10", ""]  # numerisch, nicht 1,10,2; ohne Nummer zuletzt
    ab = [z["nummer"] for z in admin_client.get(ehren, {"sort": "-nummer"}).context["zeilen"]]
    assert ab == ["10", "2", "1", ""]  # absteigend; ohne Nummer weiter hinten


# --- Anlegen -----------------------------------------------------------------------------


def test_anlegen_zeigt_startpasswort_einmal(admin_client, client):
    antwort = neu(admin_client, rollen=[rollen.FAHRER, rollen.BEIFAHRER], beschaeftigung="fest")
    assert antwort.status_code == 200 and "no-store" in antwort["Cache-Control"]
    passwort = antwort.context["passwort"]
    assert passwort in antwort.content.decode() and len(passwort) == 14
    max_ = get_user_model().objects.get(username="max")
    assert max_.passwort_aendern and max_.beschaeftigung == "fest"
    assert rollen.rollen_von(max_) == {rollen.FAHRER, rollen.BEIFAHRER}
    assert max_.check_password(passwort)


def test_benutzername_doppelt(admin_client):
    neu(admin_client)
    antwort = neu(admin_client, username="MAX")
    assert "bereits vergeben" in antwort.content.decode()


def test_startpasswort_ohne_verwechselbare_zeichen():
    for _ in range(50):
        teile = verwaltung.startpasswort().split("-")
        assert len(teile) == 3 and all(len(t) == 4 for t in teile)
        assert not set("".join(teile)) & set("0O1lI")


# --- Büro mit Freigabe -------------------------------------------------------------------


def test_buero_mit_freigabe(als, admin, buero_freigegeben):
    client, buero = als(rollen.BUERO)
    assert "Ehrenamtliche</a>" in client.get("/").content.decode()
    formular = client.get(NEU).content.decode()
    assert 'value="Ausgabe"' in formular and 'value="Admin"' not in formular
    assert "rollen" in neu(client, rollen=[rollen.ADMIN]).context["form"].errors
    assert not get_user_model().objects.filter(username="max").exists()
    assert neu(client, rollen=[rollen.AUSGABE]).status_code == 200
    # Admin-Konten bleiben tabu.
    assert client.get(url("mitarbeiter", admin)).status_code == 403
    assert client.post(url("sperren", admin)).status_code == 403
    with pytest.raises(verwaltung.VerwaltungsFehler):
        verwaltung.anlegen(buero, {"username": "x"}, [rollen.ADMIN])
    with pytest.raises(verwaltung.VerwaltungsFehler):
        verwaltung.sperren(buero, admin)


# --- Bearbeiten --------------------------------------------------------------------------


def test_bearbeiten(admin_client, benutzer_mit_rolle):
    ziel = benutzer_mit_rolle("kim", rollen.AUSGABE)
    antwort = admin_client.post(
        url("mitarbeiter", ziel),
        {"username": "kim", "first_name": "Kim", "last_name": "Probe",
         "beschaeftigung": "fest", "rollen": [rollen.BUERO]},
    )  # fmt: skip
    assert antwort.url == LISTE
    ziel.refresh_from_db()
    assert (ziel.get_full_name(), ziel.beschaeftigung) == ("Kim Probe", "fest")
    assert rollen.rollen_von(ziel) == {rollen.BUERO}
    assert "Kim Probe gespeichert" in admin_client.get(LISTE).content.decode()


def test_anlegen_legt_adresse_an(admin):
    from apps.adressen.models import Adresse

    # Jedes Mitarbeiter-Konto wird eine Person im Adressbuch (ADR 0097); die Einteilbarkeit
    # regelt die Rolle, nicht mehr ein eigenes Helfer-Feld.
    ziel, _ = verwaltung.anlegen(
        admin, {"username": "lea", "first_name": "Lea", "last_name": "Helfer"}, [rollen.AUSGABE]
    )
    adr = Adresse.objects.get(konto=ziel)
    assert adr.art == Adresse.Art.PERSON and adr.name == "Lea Helfer"
    buero, _ = verwaltung.anlegen(admin, {"username": "bo"}, [rollen.BUERO])
    assert Adresse.objects.filter(konto=buero).exists()


def test_rolle_macht_ehrenamtlichen_helfer(admin):
    from apps.adressen.models import Adresse

    # Wer ein Konto mit Rolle hat, wird automatisch als „Ehrenamtliche Helfer“ geführt (ADR 0098).
    ziel, _ = verwaltung.anlegen(
        admin, {"username": "lea", "last_name": "Helfer"}, [rollen.AUSGABE]
    )
    adr = Adresse.objects.get(konto=ziel)
    assert verwaltung.HELFER_KATEGORIE in adr.kategorien.values_list("name", flat=True)


def test_helfer_kategorie_bleibt_auch_ohne_rolle(admin):
    from apps.adressen.models import Adresse

    # Additiv und nie automatisch entfernt: fällt später jede Rolle weg, bleibt die Kategorie.
    ziel, _ = verwaltung.anlegen(
        admin, {"username": "lea", "last_name": "Helfer"}, [rollen.AUSGABE]
    )
    verwaltung.bearbeiten(admin, ziel, [])  # alle Rollen entfernt
    adr = Adresse.objects.get(konto=ziel)
    assert verwaltung.HELFER_KATEGORIE in adr.kategorien.values_list("name", flat=True)


def test_sperren_setzt_ehemalige(admin):
    from apps.adressen.models import Adresse

    # Beim Sperren kommt „Ehemalige Ehrenamtliche“ dazu; „Ehrenamtliche Helfer“ bleibt (ADR 0098).
    ziel, _ = verwaltung.anlegen(
        admin, {"username": "lea", "last_name": "Helfer"}, [rollen.AUSGABE]
    )
    verwaltung.sperren(admin, ziel)
    namen = set(Adresse.objects.get(konto=ziel).kategorien.values_list("name", flat=True))
    assert verwaltung.EHEMALIGE_KATEGORIE in namen and verwaltung.HELFER_KATEGORIE in namen


def test_entfernen_loescht_konto_und_adresse_und_stellt_wieder_her(admin, admin_client):
    from apps.adressen.models import Adresse
    from apps.core import papierkorb
    from apps.core.models import PapierkorbEintrag
    from apps.konten.models import Stammdaten

    ziel, _ = verwaltung.anlegen(
        admin, {"username": "lea", "first_name": "Lea", "last_name": "Helfer"}, [rollen.AUSGABE]
    )
    # anlegen() legt schon Stammdaten an (ADR 0101); diese gehören zum Konto.
    assert Stammdaten.objects.filter(benutzer=ziel).exists()
    verwaltung.sperren(admin, ziel)
    antwort = admin_client.post(url("entfernen", ziel))
    assert antwort.status_code == 302 and antwort.url == ARCHIV
    # Konto, Stammdaten und Adresse sind weg und liegen als ein Eintrag im Papierkorb.
    assert not get_user_model().objects.filter(pk=ziel.pk).exists()
    assert not Adresse.objects.filter(konto_id=ziel.pk).exists()
    assert not Stammdaten.objects.filter(benutzer_id=ziel.pk).exists()
    eintrag = PapierkorbEintrag.objects.get(art="Mitarbeiter")
    assert eintrag.recht == "mitarbeitende.loeschen"
    # Wiederherstellen legt Konto, Stammdaten und Adresse mit denselben Nummern wieder an.
    papierkorb.wiederherstellen(eintrag)
    assert get_user_model().objects.filter(pk=ziel.pk, username="lea").exists()
    assert Adresse.objects.filter(konto_id=ziel.pk).exists()
    assert Stammdaten.objects.filter(benutzer_id=ziel.pk).exists()


def test_entfernen_nur_gesperrt_und_nicht_selbst(admin):
    # Aktive Konten erst sperren; niemand löscht sich selbst.
    ziel, _ = verwaltung.anlegen(admin, {"username": "lea", "last_name": "H"}, [rollen.AUSGABE])
    with pytest.raises(verwaltung.VerwaltungsFehler, match="gesperrt"):
        verwaltung.entfernen(admin, ziel)
    with pytest.raises(verwaltung.VerwaltungsFehler, match="selbst"):
        verwaltung.entfernen(admin, admin)
    assert get_user_model().objects.filter(pk=ziel.pk).exists()


def test_entfernen_braucht_recht_und_scheitert_an_spende(admin, admin_client, als,
                                                         buero_freigegeben):  # fmt: skip
    from django.utils import timezone

    from apps.adressen.models import Adresse
    from apps.spenden.models import Spende

    ziel, _ = verwaltung.anlegen(admin, {"username": "lea", "last_name": "H"}, [rollen.AUSGABE])
    verwaltung.sperren(admin, ziel)
    # Büro hat „verwalten“, aber nicht „löschen“: 403, nichts gelöscht.
    client, _ = als(rollen.BUERO)
    assert client.post(url("entfernen", ziel)).status_code == 403
    assert get_user_model().objects.filter(pk=ziel.pk).exists()
    # Mit einer Spende an der Adresse lehnt das Löschen ab (ProtectedError); nichts gelöscht.
    adr = Adresse.objects.get(konto=ziel)
    Spende.objects.create(adresse=adr, datum=timezone.localdate())
    antwort = admin_client.post(url("entfernen", ziel), follow=True)
    assert "Spenden" in antwort.content.decode()
    assert get_user_model().objects.filter(pk=ziel.pk).exists()


def test_sperren_stellen_konto_ohne_adresse(admin):
    from apps.adressen.models import Adresse
    from apps.kunden.models import Ausgabestelle

    # Ausgabestellen-Konto ist keine Person: Sperren darf nicht an fehlender Adresse scheitern.
    stelle = Ausgabestelle.objects.create(name="Mitte")
    konto, _ = verwaltung.anlegen(admin, {"username": "tablet-mitte", "stelle": stelle}, [])
    verwaltung.sperren(admin, konto)
    assert not Adresse.objects.filter(konto=konto).exists()


def test_mitarbeiter_braucht_mindestens_eine_rolle(admin_client):
    # Ohne Rolle lässt sich kein Mitarbeiter-Konto anlegen (ADR 0097).
    antwort = neu(admin_client, username="ohnerolle", rollen=[])
    assert "rollen" in antwort.context["form"].errors
    assert not get_user_model().objects.filter(username="ohnerolle").exists()


def test_ausgabestellen_konto_bekommt_keine_adresse(admin):
    from apps.adressen.models import Adresse
    from apps.kunden.models import Ausgabestelle

    stelle = Ausgabestelle.objects.create(name="Mitte")
    konto, _ = verwaltung.anlegen(admin, {"username": "tablet-mitte", "stelle": stelle}, [])
    assert not Adresse.objects.filter(konto=konto).exists()  # Stellen-Konto ist keine Person


def test_admin_kann_sich_admin_rolle_nicht_nehmen(als):
    client, zweiter = als(rollen.ADMIN, "zweiter")
    antwort = client.post(
        url("mitarbeiter", zweiter),
        {"username": "zweiter", "beschaeftigung": "ehrenamtlich", "rollen": [rollen.BUERO]},
    )
    assert "nicht selbst nehmen" in antwort.content.decode()
    assert rollen.ADMIN in rollen.rollen_von(zweiter)


def test_superuser_darf_admin_gruppe_ablegen(admin_client, admin):
    admin_client.post(
        url("mitarbeiter", admin),
        {"username": "chefin", "beschaeftigung": "ehrenamtlich", "rollen": [rollen.BUERO]},
    )
    assert not admin.groups.filter(name=rollen.ADMIN).exists() and admin.is_superuser


def test_bearbeiten_mit_unerlaubter_rolle(admin, benutzer_mit_rolle):
    buero = benutzer_mit_rolle("b", rollen.BUERO)
    ziel = benutzer_mit_rolle("z", rollen.AUSGABE)
    with pytest.raises(verwaltung.VerwaltungsFehler):
        verwaltung.bearbeiten(buero, ziel, [rollen.ADMIN])
    with pytest.raises(verwaltung.VerwaltungsFehler):
        verwaltung.bearbeiten(buero, admin, [rollen.BUERO])


# --- Sperren, Archiv, Zurücksetzen -------------------------------------------------------


def test_sperren_ins_archiv_und_zurueck(admin_client, benutzer_mit_rolle, client):
    ziel = benutzer_mit_rolle("kim", rollen.AUSGABE)
    antwort = admin_client.post(url("sperren", ziel))
    assert antwort.url == url("mitarbeiter", ziel)
    ziel.refresh_from_db()
    assert not ziel.is_active and ziel.gesperrt_von == "chefin" and ziel.gesperrt_am
    aktive = [z["b"].username for z in admin_client.get(LISTE).context["zeilen"]]
    assert "kim" not in aktive
    archiv = admin_client.get(ARCHIV).content.decode()
    assert "kim" in archiv and "von chefin" in archiv
    assert "Gesperrt seit" in admin_client.get(url("mitarbeiter", ziel)).content.decode()
    admin_client.post(url("entsperren", ziel))
    ziel.refresh_from_db()
    assert ziel.is_active and ziel.gesperrt_am is None and ziel.gesperrt_von == ""


def test_gesperrte_person_ist_sofort_abgemeldet(client, admin, benutzer_mit_rolle, anmelden):
    ziel = benutzer_mit_rolle("kim", rollen.AUSGABE)
    anmelden(client, ziel, zwei_faktor=False)
    assert client.get("/").status_code == 200
    verwaltung.sperren(admin, ziel)
    assert client.get("/").status_code == 302
    assert not client.login(username="kim", password=PASSWORT)


def test_sich_selbst_sperren_geht_nicht(admin_client, admin):
    admin_client.post(url("sperren", admin))
    admin.refresh_from_db()
    assert admin.is_active
    assert "nicht selbst sperren" in admin_client.get(url("mitarbeiter", admin)).content.decode()


def test_passwort_zuruecksetzen(admin_client, benutzer_mit_rolle):
    ziel = benutzer_mit_rolle("kim", rollen.AUSGABE)
    antwort = admin_client.post(url("passwort_zuruecksetzen", ziel))
    assert "Passwort zurückgesetzt" in antwort.content.decode()
    ziel.refresh_from_db()
    assert ziel.passwort_aendern and not ziel.check_password(PASSWORT)
    assert ziel.check_password(antwort.context["passwort"])


def test_zwei_faktor_zuruecksetzen(admin_client, benutzer_mit_rolle):
    ziel = benutzer_mit_rolle("kim", rollen.BUERO)
    TOTPDevice.objects.create(user=ziel, name="App", confirmed=True)
    assert "Zwei-Faktor zurücksetzen" in admin_client.get(url("mitarbeiter", ziel)).content.decode()
    admin_client.post(url("zwei_faktor_zuruecksetzen", ziel))
    assert not TOTPDevice.objects.filter(user=ziel).exists()


# --- Passwort ändern ---------------------------------------------------------------------


def test_startpasswort_muss_geaendert_werden(client, admin, benutzer_mit_rolle, anmelden):
    ziel = benutzer_mit_rolle("kim", rollen.AUSGABE)
    ziel.passwort_aendern = True
    ziel.save()
    anmelden(client, ziel, zwei_faktor=False)
    assert client.get("/").url == PASSWORT_AENDERN
    seite = client.get(PASSWORT_AENDERN).content.decode()
    assert "Startpasswort" in seite and "Einlass</a>" not in seite
    falsch = client.post(
        PASSWORT_AENDERN,
        {
            "old_password": "falsch",
            "new_password1": "Neu-sicher-987",
            "new_password2": "Neu-sicher-987",
        },
    )
    assert falsch.status_code == 200
    antwort = client.post(
        PASSWORT_AENDERN,
        {"old_password": PASSWORT, "new_password1": "Neu-sicher-987",
         "new_password2": "Neu-sicher-987"},
    )  # fmt: skip
    assert antwort.url == reverse("core:start")
    ziel.refresh_from_db()
    assert not ziel.passwort_aendern and ziel.check_password("Neu-sicher-987")
    assert client.get("/").status_code == 200  # bleibt angemeldet


def test_erst_passwort_dann_zwei_faktor(client, admin, benutzer_mit_rolle, anmelden):
    ziel = benutzer_mit_rolle("kim", rollen.BUERO)  # Zwei-Faktor ist für Büro Pflicht
    ziel.passwort_aendern = True
    ziel.save()
    anmelden(client, ziel, zwei_faktor=False)
    assert client.get(PASSWORT_AENDERN).status_code == 200
    ziel.passwort_aendern = False
    ziel.save()
    assert client.get("/").url == reverse("konten:zwei_faktor_einrichten")


def test_mein_konto_verlinkt_passwort_aendern(admin_client):
    inhalt = admin_client.get(reverse("konten:mein_konto")).content.decode()
    assert PASSWORT_AENDERN in inhalt
    assert "← Mein Konto" in admin_client.get(PASSWORT_AENDERN).content.decode()


def test_zwei_faktor_pflicht_fuer_neue_rollen():
    pflicht = {r.name for r in rollen.alle_rollen() if r.zwei_faktor_pflicht}
    assert rollen.FAHRER not in pflicht and rollen.BEIFAHRER not in pflicht
