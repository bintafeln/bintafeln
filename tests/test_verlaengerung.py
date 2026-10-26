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
    NotizVorlage,
    Person,
    Sperre,
    Zusatzfeld,
)

pytestmark = pytest.mark.django_db

HEUTE = dt.date(2026, 10, 26)
VERLAENGERN = reverse("kunden:verlaengern")
GEPRUEFT = "Bescheide geprüft, kann verlängert werden"


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
    NotizVorlage.objects.create(text=GEPRUEFT, melden="verlaengern")
    for h in (ok, nein, unklar):
        Nachricht.objects.create(kundennummer=h.kundennummer, anliegen="verlaengern", von="anton")
        Notiz.objects.create(kundennummer=h.kundennummer, text=GEPRUEFT, verfasst_von="anton")
    Notiz.objects.create(kundennummer="202", text="Bringt nächste Woche den Bescheid")
    Nachricht.objects.create(kundennummer="201", anliegen="verlaengern", von="berta")
    Nachricht.objects.create(kundennummer="202", anliegen="sonstiges", text="Neue Telefonnummer")
    return ok, nein, unklar


def test_sammelseite_verlaengert_und_schreibt_notiz(gemeldet, admin_client):
    ok, nein, unklar = gemeldet
    start = admin_client.get("/").content.decode()
    assert "4 × Bescheid geprüft – Ausweis verlängern" in start and "1 × Sonstiges" in start
    seite = admin_client.get(VERLAENGERN).content.decode()
    assert "1 verlängerbar · 1 selbst prüfen · 1 nicht verlängerbar" in seite
    assert (
        "Verlängern nur, wenn jede Person im Haushalt erfüllt eine Bedingung: ab 60 Jahren "
        "oder Schwerbehindert." in seite
    )
    assert 'name="verlaengern" value="201" checked' in seite
    assert 'name="verlaengern" value="203">' in seite  # unklar: nicht vorbelegt
    assert 'name="ablehnen" value="202" checked> Notiz an die Ausgabestelle' in seite
    assert "30.11.2027" in seite  # neu bis
    assert 'name="an_stelle"' in seite  # Startseite der Ausgabestelle nur auf Wunsch
    antwort = admin_client.post(VERLAENGERN, {"monate": "12", "verlaengern": ["201", "202"],
                                              "ablehnen": ["202"]})  # fmt: skip
    assert antwort.status_code == 302
    for h in gemeldet:
        h.refresh_from_db()
    assert ok.ausweis_gueltig_bis == dt.date(2027, 11, 30)
    assert nein.ausweis_gueltig_bis == dt.date(2026, 11, 30)  # nicht verlängert, obwohl gewählt
    assert nein.status == Haushalt.Status.AKTIV  # kein Statuswechsel
    # Gemeldete Notiz gestrichen, neue Notiz an die Ausgabestelle mit Grund
    assert not Notiz.objects.filter(kundennummer__in=["201", "202"], text=GEPRUEFT).exists()
    assert Notiz.objects.filter(kundennummer="203", text=GEPRUEFT).exists()  # nicht gewählt
    texte = list(Notiz.objects.filter(kundennummer="202").values_list("text", flat=True))
    assert "Bringt nächste Woche den Bescheid" in texte
    neu = next(t for t in texte if t.startswith("Ausweis kann nicht"))
    # Ohne Haken nicht auf der Startseite der Ausgabestelle; Verlängerte bekommen keine Notiz
    assert not Notiz.objects.filter(an_stelle=True).exists()
    assert not Notiz.objects.filter(kundennummer="201").exclude(text=GEPRUEFT).exists()
    assert neu == (
        "Ausweis kann nicht verlängert werden. Regel: jede Person im Haushalt erfüllt eine "
        "Bedingung (ab 60 Jahren oder Schwerbehindert). Folgende Bedingung(en) werden nicht "
        "erfüllt: Vera Probe1 (35 Jahre). Der Kunde muss ein Pausenjahr einlegen; der Ausweis "
        "gilt noch bis 30.11.2026. Danach ist eine Neuanmeldung über den Antrag möglich."
    )
    assert unklar.ausweis_gueltig_bis == dt.date(2026, 11, 30)  # nicht gewählt
    offen = Nachricht.objects.filter(erledigt_am__isnull=True)
    assert set(offen.values_list("kundennummer", "anliegen")) == {
        ("203", "verlaengern"), ("202", "sonstiges")}  # fmt: skip
    assert HaushaltEreignis.objects.filter(
        kundennummer="201", text="Ausweis verlängert (Sammel-Verlängerung)").exists()  # fmt: skip
    assert HaushaltEreignis.objects.filter(
        kundennummer="202", text="Nicht verlängert (Sammel-Verlängerung)").exists()  # fmt: skip
    assert ok.geaendert_von == "chefin"


def test_andere_tafeln_pausieren(gemeldet, admin_client):
    KundenEinstellungen.objects.update(verlaengern_ablehnung="pausieren",
                                       verlaengern_sonst_pausieren_monate=6)  # fmt: skip
    seite = admin_client.get(VERLAENGERN).content.decode()
    assert 'name="ablehnen" value="202" checked> 6 Monate pausieren' in seite
    admin_client.post(VERLAENGERN, {"ablehnen": ["202"]})
    h = Haushalt.objects.get(kundennummer="202")
    assert h.status == Haushalt.Status.PAUSIERT
    assert "Pausiert bis 26.04.2027." in Notiz.objects.filter(kundennummer="202").first().text
    assert not Notiz.objects.filter(kundennummer="202", text=GEPRUEFT).exists()


def test_nur_anzeigen(gemeldet, admin_client):
    KundenEinstellungen.objects.update(verlaengern_ablehnung="anzeigen")
    seite = admin_client.get(VERLAENGERN).content.decode()
    assert 'name="ablehnen"' not in seite
    admin_client.post(VERLAENGERN, {"ablehnen": ["202"]})
    assert Haushalt.objects.get(kundennummer="202").status == Haushalt.Status.AKTIV
    assert Notiz.objects.filter(kundennummer="202", text=GEPRUEFT).exists()
    assert Nachricht.objects.filter(kundennummer="202", erledigt_am__isnull=True).count() == 2


def test_gesperrt_notiz_ohne_pausenjahr(gemeldet, admin_client):
    Haushalt.objects.filter(kundennummer="201").update(status=Haushalt.Status.BEENDET)
    admin_client.post(VERLAENGERN, {"ablehnen": ["201"]})
    text = Notiz.objects.filter(kundennummer="201").first().text
    assert text == "Ausweis kann nicht verlängert werden. Status „beendet“."


def test_monate_waehlbar(gemeldet, admin_client):
    seite = admin_client.get(VERLAENGERN, {"monate": "6"}).content.decode()
    assert "31.05.2027" in seite
    assert admin_client.get(VERLAENGERN, {"monate": "999"}).context["monate"] == 12


def test_einlass_meldet_mit_anliegen(admin, benutzer_mit_rolle, anmelden):
    haushalt("301", (70, None))
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    seite = c.get(reverse("ausgabe:empfang"), {"nummer": "301"}).content.decode()
    assert "Bescheid geprüft – Ausweis verlängern" in seite  # Fenster auch beim eigenen Kunden
    assert "Gehört jetzt zu unserer Ausgabestelle" not in seite  # nicht mehr angeboten
    url = reverse("kunden:nachricht", args=["301"])
    c.post(url, {"anliegen": "verlaengern", "text": ""})
    c.post(url, {"anliegen": "sonstiges", "text": ""})  # ohne Text abgelehnt
    c.post(url, {"anliegen": "erfunden", "text": "x"})  # unbekannt: Sonstiges
    c.post(url, {"anliegen": "zugehoerig", "text": "y"})  # nicht mehr angeboten: Sonstiges
    assert list(Nachricht.objects.order_by("pk").values_list("anliegen", flat=True)) == [
        "verlaengern", "sonstiges", "sonstiges"]  # fmt: skip
    # Alte Nachrichten behalten ihren Namen
    alt = Nachricht.objects.create(kundennummer="301", anliegen="zugehoerig", text="früher")
    assert alt.get_anliegen_display() == "Gehört jetzt zu unserer Ausgabestelle"
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


def test_ablehnung_auf_wunsch_an_die_ausgabestelle(gemeldet, admin_client):
    admin_client.post(VERLAENGERN, {"ablehnen": ["202"], "an_stelle": "1"})
    assert Notiz.objects.get(kundennummer="202", an_stelle=True).text.startswith(
        "Ausweis kann nicht verlängert werden"
    )
