"""Antragsliste, Antragsnummern und Aufnahme-Assistent (ADR 0028). Nur erfundene Daten."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.antraege import aufnahme
from apps.antraege.models import Antrag, AntragAnmerkung, AntragEinstellungen, AntragPerson
from apps.konten import rollen
from apps.kunden.models import (
    Ausgabestelle,
    Einkommensart,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Person,
)

pytestmark = pytest.mark.django_db
LISTE = reverse("antraege:liste")


def antrag(**mehr) -> Antrag:
    daten = {"vorname": "Erika", "nachname": "Mustermann", "geburtsdatum": dt.date(1968, 3, 12),
             "strasse": "Erfundene Gasse 1", "plz": "12345", "ort": "Musterstadt",
             "email": "erika@example.org", **mehr}  # fmt: skip
    return Antrag.objects.create(**daten)


@pytest.fixture
def bestand():
    stelle = Ausgabestelle.objects.create(name="Mitte")
    voll = Kundengruppe.objects.create(name="Voll", ausgabestelle=stelle, maximum=1)
    frei = Kundengruppe.objects.create(name="Frei", ausgabestelle=stelle, maximum=5)
    h = Haushalt.objects.create(kundennummer="1001", kundengruppe=voll, strasse="Alte Straße 9",
                                plz="12345", ort="Musterstadt")  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                          nachname="Mustermann", geburtsdatum=dt.date(1968, 3, 12))  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Paul", nachname="Mustermann",
                          geburtsdatum=dt.date(1966, 5, 5))  # fmt: skip
    Haushalt.objects.create(kundennummer="00042", kundengruppe=frei)
    Haushalt.objects.create(kundennummer="A-7", kundengruppe=voll, status="beendet")
    Einkommensart.objects.create(bezeichnung="Bürgergeld", aktiv=True)
    return {"h": h, "voll": voll, "frei": frei}


# --- Hilfsfunktionen --------------------------------------------------------------------------


def test_namen_vergleichen():
    assert aufnahme.normal("Müller-Lüdenscheidt, José") == "mueller luedenscheidt jose"
    assert aufnahme.namens_aehnlichkeit("Erika", "Mustermann", "Mustermann", "Erika") == 1
    assert aufnahme.namens_aehnlichkeit("Erika", "Musterman", "Erika", "Mustermann") > 0.9
    assert aufnahme.namens_aehnlichkeit("Max", "Probe", "Erika", "Mustermann") < 0.5


def test_treffer(bestand):
    vertauscht = antrag(vorname="Mustermann", nachname="Erika")
    t = aufnahme.treffer(vertauscht)
    assert t[0]["haushalt"] == bestand["h"] and t[0]["punkte"] == 100
    assert "gleiches Geburtsdatum" in t[0]["gruende"]
    tippfehler = antrag(vorname="Erica", nachname="Musterman", geburtsdatum=dt.date(1968, 12, 3),
                        strasse="", plz="")  # fmt: skip
    t = aufnahme.treffer(tippfehler)
    assert t[0]["haushalt"] == bestand["h"]
    assert "Geburtsdatum mit vertauschtem Tag und Monat" in t[0]["gruende"]
    assert aufnahme.treffer(antrag(vorname="Max", nachname="Probe", geburtsdatum=None)) == []
    mit_nummer = antrag(vorname="Max", nachname="Probe", kundennummer="00042")
    assert aufnahme.treffer(mit_nummer)[0]["punkte"] == 100


def test_gueltigkeit():
    assert aufnahme.monat_plus(dt.date(2026, 10, 24), 12, True) == dt.date(2027, 10, 31)
    assert aufnahme.monat_plus(dt.date(2026, 1, 31), 1, False) == dt.date(2026, 2, 28)
    assert aufnahme.monat_plus(dt.date(2026, 11, 5), 3, True) == dt.date(2027, 2, 28)
    e = KundenEinstellungen(ausweis_gueltig_monate=12, ausweis_bis_monatsende=True)
    auswahl = aufnahme.gueltigkeit_auswahl(dt.date(2026, 10, 24), e)
    assert auswahl[0] == ("2027-10-31", "12 Monate: bis 31.10.2027 (Vorschlag)")
    assert [w for w, _ in auswahl] == ["2027-10-31", "2027-01-31", "2027-04-30", "2028-10-31"]


def test_freie_gruppen_und_kundennummer(bestand):
    namen = [g["gruppe"].name for g in aufnahme.freie_gruppen()]
    assert namen == ["Frei"]  # „Voll“: 1 von 1 belegt (beendete zählen nicht)
    eigene = aufnahme.freie_gruppen(bestand["h"])
    assert {g["gruppe"].name for g in eigene} == {"Frei", "Voll"}
    assert aufnahme.naechste_kundennummer() == "1002"


def test_antragsnummern():
    e = AntragEinstellungen.laden()
    e.erste_nummer = 4201
    e.save()
    a, b = antrag(), antrag(vorname="Max")
    assert (a.nummer, b.nummer) == ("4201", "4202") and str(a) == "Antrag 4201"
    e.erste_nummer = 10
    e.save()
    assert antrag().laufnummer == 4203


# --- Liste und Bearbeiten -------------------------------------------------------------------


def test_liste_sortiert_sucht_und_blaettert(admin_client):
    AntragEinstellungen.objects.update_or_create(pk=1, defaults={"erste_nummer": 4201})
    for i in range(30):
        antrag(vorname=f"Vorname{i:02d}", telefon=f"0000 {i:02d}")
    a = Antrag.objects.get(vorname="Vorname05")
    AntragAnmerkung.objects.create(antrag=a, text="Rückruf erbeten", von="chefin")
    seite = admin_client.get(LISTE).content.decode()
    assert seite.index("Vorname29") < seite.index("Vorname28")  # neueste zuerst
    assert "Vorname04" not in seite and "Seite 1 von 2" in seite
    alle = admin_client.get(LISTE, {"zeilen": "alle", "sort": "vorname"}).content.decode()
    assert alle.index("Vorname00") < alle.index("Vorname01") and "Rückruf erbeten" in alle
    gesucht = admin_client.get(LISTE, {"suche": str(a.laufnummer)}).content.decode()
    assert "Vorname05" in gesucht and "Vorname06" not in gesucht
    assert "Vorname05" in admin_client.get(LISTE, {"suche": "0000 05"}).content.decode()
    assert "aufnahme" in seite and "bearbeiten" in seite
    admin_client.post(reverse("antraege:papierkorb", args=[a.pk]), {"zurueck": "liste"})
    assert Antrag.objects.get(pk=a.pk).papierkorb_am
    korb = admin_client.get(LISTE, {"ansicht": "papierkorb", "sort": "unsinn"}).content.decode()
    assert "Vorname05" in korb and "endgültig löschen" in korb
    csv = admin_client.get(reverse("antraege:export"), {"sort": "-vorname"}).content.decode()
    assert csv.index("Vorname29") < csv.index("Vorname00")


def test_bearbeiten(admin_client):
    a = antrag(staatsangehoerigkeit="deutsch")
    AntragPerson.objects.create(antrag=a, vorname="Mia", nachname="Mustermann")
    url = reverse("antraege:bearbeiten", args=[a.pk])
    seite = admin_client.get(url).content.decode()
    assert '<option value="deutsch" selected>deutsch</option>' in seite
    assert 'name="p-0-staatsangehoerigkeit"' in seite
    daten = {"art": "neu", "vorname": "Erika", "nachname": "Musterfrau", "anrede": "Frau",
             "staatsangehoerigkeit": "Deutschland", "familienstand": "",
             "p-TOTAL_FORMS": "3", "p-INITIAL_FORMS": "1", "p-MIN_NUM_FORMS": "0",
             "p-MAX_NUM_FORMS": "1000",
             "p-0-id": a.personen.get().pk, "p-0-antrag": a.pk, "p-0-vorname": "Mia",
             "p-0-nachname": "Mustermann", "p-0-DELETE": "on",
             "p-1-vorname": "Tom", "p-1-nachname": "Test",
             "p-1-geburtsdatum": "2016-01-02", "p-1-staatsangehoerigkeit": "Irak"}  # fmt: skip
    antwort = admin_client.post(url, daten)
    assert antwort.status_code == 302
    a.refresh_from_db()
    assert a.nachname == "Musterfrau" and a.staatsangehoerigkeit == "Deutschland"
    assert [(p.vorname, p.staatsangehoerigkeit) for p in a.personen.all()] == [("Tom", "Irak")]


# --- Aufnahme -------------------------------------------------------------------------------


def schritt(client, a, name, daten=None):
    url = reverse("antraege:aufnahme_schritt", args=[a.pk, name])
    return client.post(url, daten or {}) if daten is not None else client.get(url)


def test_aufnahme_neuer_kunde(admin_client, bestand):
    a = antrag(vorname="Max", nachname="Probe", geburtsdatum=dt.date(1990, 1, 1), plz="99999")
    AntragPerson.objects.create(antrag=a, vorname="Lina", nachname="Probe",
                                geburtsdatum=dt.date(2015, 6, 1))  # fmt: skip
    assert admin_client.get(reverse("antraege:aufnahme", args=[a.pk])).url.endswith("/kunde/")
    seite = schritt(admin_client, a, "kunde").content.decode()
    assert "Kein ähnlicher Kunde gefunden." in seite
    assert schritt(admin_client, a, "personen").url.endswith("/kunde/")  # erst Schritt 1
    assert "aus der Liste" in schritt(admin_client, a, "kunde", {"haushalt": "x"}).content.decode()
    assert schritt(admin_client, a, "kunde", {"haushalt": "neu"}).url.endswith("/abgleich/")
    assert "Neuer Kunde" in schritt(admin_client, a, "abgleich").content.decode()
    schritt(admin_client, a, "abgleich", {})
    seite = schritt(admin_client, a, "personen").content.decode()
    assert 'value="Lina"' in seite
    assert 'name="p0_staatsangehoerigkeit"' in seite
    schritt(admin_client, a, "personen", {"anzahl": "2", "p0_vorname": "Lina",
            "p0_nachname": "Probe", "p0_geburtsdatum": "2015-06-01", "p1_vorname": "Ben",
            "p1_geburtsdatum": "2018-02-03", "p0_staatsangehoerigkeit": "Ukraine",
            "p1_staatsangehoerigkeit": ""})  # fmt: skip
    art = Einkommensart.objects.get()
    assert "festlegen" in schritt(admin_client, a, "bescheid",
                                  {"einkommensart": art.pk}).content.decode()  # fmt: skip
    alt = (timezone.localdate() - dt.timedelta(days=1)).isoformat()
    daten = {"einkommensart": art.pk, "gueltig_bis": "eigenes", "gueltig_eigenes": alt}
    fehler = schritt(admin_client, a, "bescheid", daten).content.decode()
    assert "Vergangenheit" in fehler
    bis = aufnahme.gueltigkeit_auswahl(timezone.localdate(), KundenEinstellungen.laden())[0][0]
    schritt(admin_client, a, "bescheid", {"einkommensart": art.pk, "gueltig_bis": bis})
    seite = schritt(admin_client, a, "gruppe").content.decode()
    assert "Frei" in seite and ">Voll<" not in seite
    voll = schritt(admin_client, a, "gruppe", {"kundengruppe": bestand["voll"].pk})
    assert "voll" in voll.content.decode()
    schritt(admin_client, a, "gruppe", {"kundengruppe": bestand["frei"].pk})
    seite = schritt(admin_client, a, "pruefen").content.decode()
    assert "Neuer Kunde, Kundennummer 1002" in seite and "Ben" in seite
    antwort = schritt(admin_client, a, "pruefen", {})
    assert antwort.url == reverse("antraege:aufnahme_fertig", args=[a.pk])
    h = Haushalt.objects.get(kundennummer="1002")
    assert h.aufgenommen_am and h.kunde_seit == timezone.localdate()
    assert h.kundengruppe == bestand["frei"] and h.einkommensart == art
    assert h.ausweis_gueltig_bis.isoformat() == bis and h.plz == "99999"
    assert h.hauptperson.vorname == "Max"
    assert sorted(p.vorname for p in h.personen.filter(ist_hauptperson=False)) == ["Ben", "Lina"]
    assert h.personen.get(vorname="Lina").staatsangehoerigkeit == "Ukraine"
    a.refresh_from_db()
    assert a.status == Antrag.Status.ERLEDIGT and a.kundennummer == "1002"
    fertig = admin_client.get(antwort.url).content.decode()
    assert "Kunde 1002 aufgenommen" in fertig and "Ausweis drucken (PDF)" in fertig


def test_aufnahme_bestehender_kunde(admin_client, bestand):
    a = antrag(vorname="Mustermann", nachname="Erika", strasse="Neue Straße 1", telefon="0000 1")
    AntragPerson.objects.create(antrag=a, vorname="Paul", nachname="Mustermann")
    AntragPerson.objects.create(antrag=a, vorname="Mia", nachname="Mustermann")
    admin_client.get(reverse("antraege:aufnahme", args=[a.pk]))
    seite = schritt(admin_client, a, "kunde").content.decode()
    assert "1001" in seite and "gleiches Geburtsdatum" in seite
    schritt(admin_client, a, "kunde", {"haushalt": "1001"})
    seite = schritt(admin_client, a, "abgleich").content.decode()
    assert "Alte Straße 9" in seite and "Neue Straße 1" in seite and "unterschied" in seite
    # Name wie im Kundenstamm (im Antrag vertauscht), Straße und Telefon aus dem Antrag
    schritt(admin_client, a, "abgleich", {"wahl_vorname": "bestand", "wahl_nachname": "bestand",
            "wahl_strasse": "antrag", "wahl_telefon": "antrag"})  # fmt: skip
    seite = schritt(admin_client, a, "personen").content.decode()
    assert seite.count('value="Paul"') == 1 and 'value="Mia"' in seite  # Paul nicht doppelt
    gruppen = schritt(admin_client, a, "gruppe").content.decode()
    assert "(bisherige)" in gruppen  # eigene volle Gruppe bleibt wählbar
    schritt(admin_client, a, "pruefen", {})
    h = Haushalt.objects.get(kundennummer="1001")
    hp = h.hauptperson
    assert (hp.vorname, hp.nachname) == ("Erika", "Mustermann")
    assert h.strasse == "Neue Straße 1" and h.telefon == "0000 1" and not h.aufgenommen_am
    assert h.geaendert_von == "chefin" and Haushalt.objects.count() == 3
    # Personen-Schritt übersprungen: Vorschlag (Paul bleibt, Mia kommt dazu) gilt
    assert sorted(p.vorname for p in h.personen.filter(ist_hauptperson=False)) == ["Mia", "Paul"]


def test_aufnahme_rechte(client, admin, benutzer_mit_rolle, anmelden):
    a = antrag()
    anmelden(client, benutzer_mit_rolle("kim", rollen.AUSGABE))
    assert client.get(reverse("antraege:aufnahme", args=[a.pk])).status_code == 403
    assert schritt(client, a, "kunde").status_code == 403


def test_aufnahme_unbekannter_schritt(admin_client):
    a = antrag()
    assert schritt(admin_client, a, "gibtsnicht").status_code == 404


def test_datum_de_filter():
    from apps.antraege.templatetags.aufnahme_anzeige import datum_de

    assert datum_de("1968-03-12") == "12.03.1968"
    assert datum_de("Musterweg 1") == "Musterweg 1"
    assert datum_de("0123 45678") == "0123 45678"
    assert datum_de("") == ""


def test_aufnahme_uebernimmt_gdb(admin_client, bestand):
    from apps.kunden.models import Zusatzfeld

    a = antrag(vorname="Max", nachname="Probe", gdb=60, merkzeichen="G, B")
    AntragPerson.objects.create(antrag=a, vorname="Lina", nachname="Probe", gdb=30)
    schritt(admin_client, a, "kunde", {"haushalt": "neu"})
    schritt(admin_client, a, "abgleich", {})
    seite = schritt(admin_client, a, "personen").content.decode()
    assert "Gl <small>(gehörlos)</small>" in seite and "VB <small>" not in seite
    assert 'name="p0_gdb"' in seite and '<option value="30" selected>GdB 30</option>' in seite
    schritt(admin_client, a, "personen", {"anzahl": "2", "p0_vorname": "Lina", "p0_gdb": "30",
                                          "p0_merkzeichen": ["Bl", "Gl", "x"],
                                          "p1_vorname": "Ben", "p1_gdb": "unsinn"})  # fmt: skip
    art = Einkommensart.objects.get()
    bis = aufnahme.gueltigkeit_auswahl(timezone.localdate(), KundenEinstellungen.laden())[0][0]
    schritt(admin_client, a, "bescheid", {"einkommensart": art.pk, "gueltig_bis": bis})
    schritt(admin_client, a, "gruppe", {"kundengruppe": bestand["frei"].pk})
    schritt(admin_client, a, "pruefen", {})
    h = Haushalt.objects.get(kundennummer="1002")
    assert h.hauptperson.zusatz == {"gdb": "GdB 60", "schwerbehindert": True,
                                    "merkzeichen": "G (erheblich gehbehindert), "
                                                   "B (Begleitperson berechtigt)"}  # fmt: skip
    # Gl (gehörlos) setzt nicht das Merkmal „Taub“
    assert h.personen.get(vorname="Lina").zusatz == {
        "gdb": "GdB 30", "schwerbehindert": False, "merkzeichen": "Bl (blind), Gl (gehörlos)",
        "blind": True}  # fmt: skip
    assert Zusatzfeld.objects.get(schluessel="merkzeichen").besondere_kategorie
    assert not h.personen.get(vorname="Ben").zusatz  # ohne Angabe bleibt alles, wie es war
    feld = Zusatzfeld.objects.get(schluessel="gdb")
    assert feld.besondere_kategorie and "GdB 100" in feld.optionen_liste()
