"""Sammel-Verlängerung der Ausweise (ADR 0068), alle Daten erfunden."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse

from apps.konten import rollen
from apps.kunden import verlaengerung
from apps.kunden.models import (
    Einkommensart,
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Nachricht,
    Notiz,
    Person,
    Sperre,
    Zusatzfeld,
)

pytestmark = pytest.mark.django_db

HEUTE = dt.date(2026, 10, 26)
VERLAENGERN = reverse("kunden:verlaengern")


def jahre(alter):
    return None if alter is None else HEUTE.replace(year=HEUTE.year - alter)


def haushalt(nummer, *personen, bis=dt.date(2026, 11, 30), **felder):
    h = Haushalt.objects.create(kundennummer=nummer, ausweis_gueltig_bis=bis, **felder)
    for i, (alter, zusatz) in enumerate(personen):
        Person.objects.create(haushalt=h, ist_hauptperson=i == 0, vorname="Vera",
                              nachname=f"Probe{i}", geburtsdatum=jahre(alter),
                              zusatz=zusatz or {})  # fmt: skip
    return h


@pytest.fixture
def regel():
    """Wie bei der Tafel im Beispiel: jede Person ab 60 oder schwerbehindert."""
    sb = Zusatzfeld.objects.create(schluessel="schwerbehindert", bezeichnung="Schwerbehindert",
                                   gilt_fuer=Zusatzfeld.GiltFuer.PERSON,
                                   typ=Zusatzfeld.Typ.JA_NEIN)  # fmt: skip
    e = KundenEinstellungen.laden()
    e.verlaengern_regel = KundenEinstellungen.Verlaengern.ALLE
    e.verlaengern_ab_alter = 60
    e.save()
    e.verlaengern_felder.set([sb])
    return e


def ergebnis(h, e=None):
    e = e or KundenEinstellungen.laden()
    return verlaengerung.pruefen(h, HEUTE, 12, e)


def test_ohne_bedingung_alle_verlaengerbar():
    p = ergebnis(haushalt("100", (30, None)))
    assert p.ergebnis == verlaengerung.OK and p.neu_bis == dt.date(2027, 11, 30)


def test_jede_person_muss_eine_bedingung_erfuellen(regel):
    assert ergebnis(haushalt("101", (70, None), (40, {"schwerbehindert": True}))).ergebnis == "ok"
    nein = ergebnis(haushalt("102", (70, None), (40, None)))
    assert nein.ergebnis == "nein" and "Nicht alle Personen" in nein.gruende[0]
    assert ("Vera Probe1", "✗ 40 Jahre") in nein.personen
    assert ergebnis(haushalt("103", (70, None), (None, None))).ergebnis == "unklar"
    # Einkommensart zählt für alle Personen
    ga = Einkommensart.objects.create(bezeichnung="Grundsicherung im Alter")
    regel.verlaengern_einkommensarten.set([ga])
    assert ergebnis(haushalt("104", (30, None), einkommensart=ga)).ergebnis == "ok"


def test_feld_fuer_den_haushalt_zaehlt_fuer_alle(regel):
    sb = Zusatzfeld.objects.get(schluessel="schwerbehindert")
    sb.gilt_fuer = Zusatzfeld.GiltFuer.HAUSHALT
    sb.save()
    h = haushalt("105", (30, None), (8, None), zusatz={"schwerbehindert": True})
    assert ergebnis(h).ergebnis == "ok"


def test_eine_person_genuegt(regel):
    regel.verlaengern_regel = KundenEinstellungen.Verlaengern.EINE
    regel.save()
    assert ergebnis(haushalt("110", (30, None), (61, None))).ergebnis == "ok"
    assert ergebnis(haushalt("111", (30, None), (None, None))).ergebnis == "unklar"
    assert ergebnis(haushalt("112", (30, None), (31, None))).ergebnis == "nein"


def test_status_sperre_und_hinweise(regel):
    assert ergebnis(haushalt("120", (70, None), status=Haushalt.Status.BEENDET)).ergebnis == "nein"
    h = haushalt("121", (70, None), bis=dt.date(2027, 6, 30))
    Sperre.objects.create(haushalt=h, von=HEUTE - dt.timedelta(days=1))
    p = ergebnis(h)
    assert p.ergebnis == "nein" and "Aktive Sperre" in p.gruende
    assert "Ausweis noch gültig bis 30.06.2027" in p.hinweise
    assert ergebnis(haushalt("122")).gruende == ["Keine Personen erfasst"]


def test_neues_datum():
    e = KundenEinstellungen.laden()
    lauft = haushalt("130", bis=dt.date(2027, 1, 15))
    assert verlaengerung.neues_datum(lauft, HEUTE, 12, e) == dt.date(2028, 1, 31)
    abgelaufen = haushalt("131", bis=dt.date(2025, 3, 1))
    assert verlaengerung.neues_datum(abgelaufen, HEUTE, 12, e) == dt.date(2027, 10, 31)
    e.ausweis_bis_monatsende = False
    assert verlaengerung.neues_datum(lauft, HEUTE, 6, e) == dt.date(2027, 7, 15)


@pytest.fixture
def gemeldet(regel, monkeypatch):
    """Drei Haushalte, gemeldet von einer Ausgabestelle über das Einlass-Fenster."""
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda *a: HEUTE)
    ok = haushalt("201", (72, None), (64, None))
    nein = haushalt("202", (72, None), (35, None))
    unklar = haushalt("203", (None, None))
    for h in (ok, nein, unklar):
        Nachricht.objects.create(kundennummer=h.kundennummer, anliegen="verlaengern", von="anton")
    Nachricht.objects.create(kundennummer="201", anliegen="verlaengern", von="berta")
    Nachricht.objects.create(kundennummer="202", anliegen="sonstiges", text="Neue Telefonnummer")
    return ok, nein, unklar


def test_sammelseite_verlaengert_und_pausiert(gemeldet, admin_client):
    ok, nein, unklar = gemeldet
    start = admin_client.get("/").content.decode()
    assert "4 × Bescheid geprüft – Ausweis verlängern" in start and "1 × Sonstiges" in start
    seite = admin_client.get(VERLAENGERN).content.decode()
    assert "1 verlängerbar · 1 selbst prüfen · 1 nicht verlängerbar" in seite
    assert 'name="verlaengern" value="201" checked' in seite
    assert 'name="verlaengern" value="203">' in seite  # unklar: nicht vorbelegt
    assert 'name="pausieren" value="202" checked' in seite
    assert "30.11.2027" in seite  # neu bis
    antwort = admin_client.post(VERLAENGERN, {"monate": "12", "verlaengern": ["201", "202"],
                                              "pausieren": ["202"]})  # fmt: skip
    assert antwort.status_code == 302
    for h in gemeldet:
        h.refresh_from_db()
    assert ok.ausweis_gueltig_bis == dt.date(2027, 11, 30)
    assert nein.ausweis_gueltig_bis == dt.date(2026, 11, 30)  # nicht verlängert, obwohl gewählt
    assert nein.status == Haushalt.Status.PAUSIERT
    assert "Pausiert bis 26.10.2027" in Notiz.objects.get(kundennummer="202").text
    assert unklar.ausweis_gueltig_bis == dt.date(2026, 11, 30)  # nicht gewählt
    offen = Nachricht.objects.filter(erledigt_am__isnull=True)
    assert set(offen.values_list("kundennummer", "anliegen")) == {
        ("203", "verlaengern"), ("202", "sonstiges")}  # fmt: skip
    assert HaushaltEreignis.objects.filter(
        kundennummer="201", text="Ausweis verlängert (Sammel-Verlängerung)").exists()  # fmt: skip
    assert ok.geaendert_von == "chefin"


def test_ohne_pause_nur_anzeigen(gemeldet, admin_client):
    KundenEinstellungen.objects.update(verlaengern_sonst_pausieren_monate=0)
    seite = admin_client.get(VERLAENGERN).content.decode()
    assert 'name="pausieren"' not in seite
    admin_client.post(VERLAENGERN, {"pausieren": ["202"]})
    assert Haushalt.objects.get(kundennummer="202").status == Haushalt.Status.AKTIV


def test_monate_waehlbar(gemeldet, admin_client):
    seite = admin_client.get(VERLAENGERN, {"monate": "6"}).content.decode()
    assert "31.05.2027" in seite
    assert admin_client.get(VERLAENGERN, {"monate": "999"}).context["monate"] == 12


def test_einlass_meldet_mit_anliegen(admin, benutzer_mit_rolle, anmelden):
    haushalt("301", (70, None))
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    seite = c.get(reverse("ausgabe:empfang"), {"nummer": "301"}).content.decode()
    assert "Bescheid geprüft – Ausweis verlängern" in seite  # Fenster auch beim eigenen Kunden
    url = reverse("kunden:nachricht", args=["301"])
    c.post(url, {"anliegen": "verlaengern", "text": ""})
    c.post(url, {"anliegen": "sonstiges", "text": ""})  # ohne Text abgelehnt
    c.post(url, {"anliegen": "erfunden", "text": "x"})  # unbekannt: Sonstiges
    assert list(Nachricht.objects.order_by("pk").values_list("anliegen", flat=True)) == [
        "verlaengern", "sonstiges"]  # fmt: skip
    assert c.get(VERLAENGERN).status_code == 403


def test_menue_zaehlt_gemeldete_haushalte(gemeldet, admin_client):
    seite = admin_client.get("/").content.decode()
    assert 'title="gemeldete Haushalte">3</span>' in seite


def test_notiz_knopf_meldet_der_verwaltung(admin, benutzer_mit_rolle, anmelden):
    """Der Knopf „Bescheide geprüft …“ am Einlass: Notiz und zugleich Meldung."""
    from apps.kunden.models import NotizVorlage

    NotizVorlage.objects.create(text="Bescheide geprüft, kann verlängert werden",
                                melden="verlaengern")  # fmt: skip
    NotizVorlage.objects.create(text="Bringt Bescheid nächste Woche")
    haushalt("401", (70, None))
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    url = reverse("ausgabe:notiz", args=["401"])
    c.post(url, {"text": "Bescheide geprüft, kann verlängert werden"})
    c.post(url, {"text": "Bescheide geprüft, kann verlängert werden"})  # doppelt: eine Meldung
    c.post(url, {"text": "Bringt Bescheid nächste Woche"})
    assert Notiz.objects.filter(kundennummer="401").count() == 3
    n = Nachricht.objects.get()
    assert (n.kundennummer, n.anliegen, n.von) == ("401", "verlaengern", "anton")
