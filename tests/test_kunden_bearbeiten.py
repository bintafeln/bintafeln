import datetime as dt
from decimal import Decimal as D

import pytest
from auditlog.models import LogEntry
from django.urls import reverse

from apps.ausgabe import konto
from apps.ausgabe.models import AusgabeEinstellungen, Buchung
from apps.konten import rollen
from apps.kunden import importieren
from apps.kunden.forms_bearbeiten import HaushaltForm, PersonForm
from apps.kunden.models import (
    Abholer,
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Bemerkung,
    Einkommensart,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Sperre,
    Zusatzfeld,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def h():
    h = Haushalt.objects.create(kundennummer="2001", zusatz={"alt": "bleibt"})
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Test")
    return h


def url(name, *args):
    return reverse(f"kunden:{name}", args=args)


def test_nur_admin(client, admin, benutzer_mit_rolle, anmelden, h):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(url("bearbeiten", "2001")).status_code == 403
    assert client.get(url("haushalt_neu")).status_code == 403
    assert client.get(url("liste", "kundengruppen")).status_code == 403
    assert "Bearbeiten</a>" not in client.get(url("haushalt", "2001")).content.decode()


def test_haushalt_bearbeiten(admin_client, h):
    Zusatzfeld.objects.create(schluessel="sb", bezeichnung="Schwerbehindert",
                              gilt_fuer="haushalt", besondere_kategorie=True)  # fmt: skip
    Zusatzfeld.objects.create(schluessel="seit", bezeichnung="Seit", gilt_fuer="haushalt",
                              typ="datum")  # fmt: skip
    Zusatzfeld.objects.create(schluessel="art", bezeichnung="Art", gilt_fuer="haushalt",
                              typ="auswahl", optionen="A\nB")  # fmt: skip
    Zusatzfeld.objects.create(schluessel="notiz", bezeichnung="Notiz", gilt_fuer="haushalt",
                              typ="text")  # fmt: skip
    gruppe = Kundengruppe.objects.create(name="Montag")
    seite = admin_client.get(url("haushalt", "2001")).content.decode()
    assert "Bearbeiten</a>" in seite
    seite = admin_client.get(url("bearbeiten", "2001")).content.decode()
    assert (
        "ersetzt der nächste Import alle Änderungen" in seite
        and "Schwerbehindert (Art. 9)" in seite
    )
    admin_client.post(
        url("bearbeiten", "2001"),
        {"kundennummer": "2001", "status": "pausiert", "kundengruppe": gruppe.pk,
         "strasse": "Erfundene Gasse 2", "zusatz_sb": "ja", "zusatz_seit": "2026-01-02",
         "zusatz_art": "B", "zusatz_notiz": ""},
    )  # fmt: skip
    h.refresh_from_db()
    assert (h.status, h.kundengruppe, h.strasse) == ("pausiert", gruppe, "Erfundene Gasse 2")
    assert h.zusatz == {"alt": "bleibt", "sb": True, "seit": "2026-01-02", "art": "B"}
    assert h.geaendert_von == "chefin" and h.geaendert_am
    assert LogEntry.objects.get_for_object(h).filter(action=LogEntry.Action.UPDATE).exists()
    form = HaushaltForm(instance=h)
    assert (form.initial["zusatz_sb"], form.initial["zusatz_seit"]) == ("ja", dt.date(2026, 1, 2))
    h.zusatz["sb"] = False
    assert HaushaltForm(instance=h).initial["zusatz_sb"] == "nein"
    admin_client.post(url("bearbeiten", "2001"), {"kundennummer": "2002", "status": "aktiv"})
    assert Haushalt.objects.get(pk=h.pk).kundennummer == "2002"
    assert "In bintafeln geändert" in admin_client.get(url("haushalt", "2002")).content.decode()


def test_datensparsamkeit_blendet_felder_aus(h):
    e = KundenEinstellungen.laden()
    e.telefon_erfassen = e.email_erfassen = False
    e.staatsangehoerigkeit_erfassen = e.familienstand_erfassen = False
    e.save()
    assert "telefon" not in HaushaltForm(instance=h).fields
    form = PersonForm(instance=h.personen.first())
    assert "familienstand" not in form.fields and "staatsangehoerigkeit" not in form.fields


def test_haushalt_neu_und_loeschen(admin_client, admin):
    assert "Neuer Haushalt" in admin_client.get(url("uebersicht")).content.decode()
    antwort = admin_client.post(url("haushalt_neu"), {"kundennummer": "3001", "status": "aktiv"})
    h = Haushalt.objects.get(kundennummer="3001")
    assert antwort.url == url("bearbeiten", "3001") and h.geaendert_am
    assert "Neuer Haushalt" in admin_client.get(url("haushalt_neu")).content.decode()
    b = konto.einzahlen(h, D("5"), None, "chefin")
    admin_client.post(url("haushalt_loeschen", "3001"))
    assert not Haushalt.objects.exists()
    b.refresh_from_db()
    assert b.haushalt is None and b.kundennummer == "3001"  # Kasse bleibt vollständig


def test_personen(admin_client, h):
    Zusatzfeld.objects.create(schluessel="sb", bezeichnung="Schwerbehindert", gilt_fuer="person")
    seite = admin_client.get(url("teil_neu", "2001", "person")).content.decode()
    assert '<option value="Frau">Frau</option>' in seite and "verwitwet" in seite
    daten = {"vorname": "Max", "nachname": "Test", "ist_hauptperson": "on", "anrede": "Herr",
             "familienstand": "ledig", "zusatz_sb": "nein"}  # fmt: skip
    admin_client.post(url("teil_neu", "2001", "person"), daten)
    max_ = Person.objects.get(vorname="Max")
    assert max_.ist_hauptperson and max_.zusatz == {"sb": False}
    assert not Person.objects.get(vorname="Erika").ist_hauptperson
    alt = Person.objects.get(vorname="Erika")
    alt.familienstand, alt.staatsangehoerigkeit = "unbekannt (alt)", "deutsch"
    alt.save()
    seite = admin_client.get(url("teil", "2001", "person", alt.pk)).content.decode()
    assert "unbekannt (alt)" in seite and "Löschen" in seite
    assert '<option value="deutsch" selected>deutsch</option>' in seite  # Importwert bleibt
    assert '<option value="Türkei" data-land="TR">Türkei</option>' in seite
    daten = {"vorname": "Erika", "nachname": "Test", "ist_hauptperson": "on"}
    admin_client.post(url("teil", "2001", "person", alt.pk), daten)
    assert Person.objects.get(ist_hauptperson=True) == alt
    admin_client.post(url("teil_loeschen", "2001", "person", max_.pk))
    assert not Person.objects.filter(vorname="Max").exists()
    assert admin_client.get(url("teil_neu", "2001", "gibtsnicht")).status_code == 404


def test_abholer_sperren_anmerkungen_ausnahmen(admin_client, h):
    admin_client.post(url("teil_neu", "2001", "abholer"), {"vorname": "Otto", "nachname": "A"})
    assert Abholer.objects.get().vorname == "Otto"
    seite = admin_client.get(url("teil_neu", "2001", "sperre")).content.decode()
    assert '<option value="chefin" selected>chefin</option>' in seite  # vorbelegt
    daten = {"von": "2026-02-01", "bis": "2026-01-01"}
    falsch = admin_client.post(url("teil_neu", "2001", "sperre"), daten).content.decode()
    assert "nicht vor" in falsch
    daten = {"von": "2026-01-01", "begruendung": "Test", "eingetragen_von": "chefin"}
    admin_client.post(url("teil_neu", "2001", "sperre"), daten)
    assert Sperre.objects.get().eingetragen_von == "chefin"
    admin_client.post(url("teil_neu", "2001", "anmerkung"),
                      {"datum": "2026-03-01", "text": "Erfundene Anmerkung",
                       "verfasst_von": "chefin"})  # fmt: skip
    assert Bemerkung.objects.get().verfasst_von == "chefin"
    admin_client.post(url("teil_neu", "2001", "ausnahme"), {"datum": "2026-03-02"})
    a = Ausnahme.objects.get()
    assert a.erfasst_am  # in bintafeln erfasst
    admin_client.post(url("teil", "2001", "ausnahme", a.pk), {"datum": "2026-03-03"})
    a.refresh_from_db()
    assert a.datum == dt.date(2026, 3, 3)
    seite = admin_client.get(url("bearbeiten", "2001")).content.decode()
    for text in ("Otto", "Test", "Erfundene Anmerkung", "03.03.2026"):
        assert text in seite


def test_abholung_loeschen_nimmt_buchung_zurueck(admin_client, h):
    stelle = Ausgabestelle.objects.create(name="Mitte")
    alt = Abholung.objects.create(haushalt=h, datum=dt.date(2026, 10, 1))
    neu = Abholung.objects.create(haushalt=h, datum=dt.date(2026, 10, 8), beitrag=D("2"))
    h.letzter_besuch = neu.datum
    h.save()
    e = AusgabeEinstellungen(anschreiben_erlaubt=True)
    konto.abholung_buchen(neu, D("2"), D("0"), e, stelle, "kim")
    h.refresh_from_db()
    assert h.kontostand == D("-2")
    assert "08.10.2026" in admin_client.get(url("bearbeiten", "2001")).content.decode()
    admin_client.post(url("abholung_loeschen", "2001", neu.pk))
    h.refresh_from_db()
    assert (h.kontostand, h.letzter_besuch) == (D("0"), alt.datum) and not Buchung.objects.exists()
    admin_client.post(url("abholung_loeschen", "2001", alt.pk))
    h.refresh_from_db()
    assert h.letzter_besuch is None


def test_notiz_vorlagen_pflegen(admin_client, h):
    from apps.kunden.models import Notiz, NotizVorlage

    assert url("liste", "notizvorlagen") in admin_client.get(url("einstellungen")).content.decode()
    admin_client.post(url("listeneintrag_neu", "notizvorlagen"),
                      {"text": "Bescheide geprüft", "reihenfolge": 1, "aktiv": "on"})  # fmt: skip
    assert str(NotizVorlage.objects.get()) == "Bescheide geprüft"
    seite = admin_client.get(url("haushalt", "2001")).content.decode()
    assert "Bescheide geprüft</button>" in seite and "Notiz-Vorlagen bearbeiten" in seite
    admin_client.post(url("notiz_neu", "2001"), {"text": "Bescheide geprüft"})
    assert Notiz.objects.get().text == "Bescheide geprüft"


def test_listen_pflegen(admin_client):
    seite = admin_client.get(url("einstellungen")).content.decode()
    assert url("liste", "kundengruppen") in seite
    assert admin_client.get(url("liste", "gibtsnicht")).status_code == 404
    admin_client.post(url("listeneintrag_neu", "ausgabestellen"), {"name": "Nord", "aktiv": "on"})
    stelle = Ausgabestelle.objects.get()
    admin_client.post(url("listeneintrag_neu", "kundengruppen"),
                      {"kuerzel": "DI", "name": "Dienstag", "ausgabestelle": stelle.pk,
                       "wochentage": ["Fr", "Di"], "uhrzeit": "14:00", "aktiv": "on"})  # fmt: skip
    gruppe = Kundengruppe.objects.get()
    assert gruppe.wochentage == "Di, Fr" and gruppe.uhrzeit == dt.time(14, 0)
    seite = admin_client.get(url("listeneintrag", "kundengruppen", gruppe.pk)).content.decode()
    assert "checked" in seite
    liste = admin_client.get(url("liste", "kundengruppen")).content.decode()
    assert "DI – Dienstag" in liste and "überschreibt Kundengruppen" in liste
    antwort = admin_client.post(url("listeneintrag_loeschen", "ausgabestellen", stelle.pk),
                                follow=True)  # fmt: skip
    assert "wird noch verwendet" in antwort.content.decode()
    admin_client.post(url("listeneintrag_loeschen", "kundengruppen", gruppe.pk))
    admin_client.post(url("listeneintrag_loeschen", "ausgabestellen", stelle.pk))
    assert not Ausgabestelle.objects.exists()
    admin_client.post(url("listeneintrag_neu", "einkommensarten"), {"bezeichnung": "Rente"})
    e = Einkommensart.objects.get()
    assert not e.aktiv
    inaktiv = admin_client.get(url("liste", "einkommensarten")).content.decode()
    assert "inaktiv" in inaktiv


def test_import_warnt_vor_handaenderungen(h, admin):
    from apps.kunden.models import Haushalt as HaushaltModell

    HaushaltModell.objects.filter(pk=h.pk).update(geaendert_am=h.importiert_am)
    datei = b"kundennummer;nachname;vorname\n2001;Test;Erika\n"
    ergebnis = importieren.pruefen({"haushalte.csv": datei})
    assert any("von Hand geänderte" in m["text"] for m in ergebnis.warnungen)


def test_notizen_haushaltsseite_import_und_umnummern(
    client, admin, benutzer_mit_rolle, anmelden, h
):
    from apps.kunden.models import Notiz, fristen_anwenden

    anmelden(client, benutzer_mit_rolle("kim", rollen.AUSGABE))
    client.post(url("notiz_neu", "2001"), {"text": "Erfundene Notiz"})
    client.post(url("notiz_neu", "2001"), {"text": ""})
    n = Notiz.objects.get()
    seite = client.get(url("haushalt", "2001")).content.decode()
    assert "Erfundene Notiz" in seite and "löschen</button>" in seite  # eigene, von heute
    Notiz.objects.filter(pk=n.pk).update(benutzer=None)  # wie von jemand anderem
    assert "löschen</button>" not in client.get(url("haushalt", "2001")).content.decode()
    assert client.post(reverse("kunden:notiz_loeschen", args=[n.pk])).status_code == 403
    admin_client = anmelden(client, admin)
    assert "löschen</button>" in admin_client.get(url("haushalt", "2001")).content.decode()
    # Kundennummer ändern: Notizen ziehen mit
    admin_client.post(url("bearbeiten", "2001"), {"kundennummer": "2009", "status": "aktiv"})
    assert Notiz.objects.get().kundennummer == "2009"
    # Import: Notiz bleibt, solange es die Kundennummer gibt
    Notiz.objects.create(kundennummer="weg", text="verwaist")
    datei = b"kundennummer;nachname;vorname\n2009;Test;Erika\n"
    ergebnis = importieren.pruefen({"haushalte.csv": datei})
    importieren.uebernehmen(ergebnis.daten, benutzer=None, dateien=["haushalte.csv"],
                            pruefsumme="x", anzahl_warnungen=0)  # fmt: skip
    assert list(Notiz.objects.values_list("text", flat=True)) == ["Erfundene Notiz"]
    Notiz.objects.create(kundennummer="weg", text="verwaist")
    assert fristen_anwenden() >= 1 and Notiz.objects.count() == 1
    admin_client.post(reverse("kunden:notiz_loeschen", args=[Notiz.objects.get().pk]))
    assert not Notiz.objects.exists()
    Notiz.objects.create(kundennummer="2009", text="x")
    admin_client.post(url("haushalt_loeschen", "2009"))
    assert not Notiz.objects.exists()
