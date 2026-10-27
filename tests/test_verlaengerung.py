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
    assert ("Vera Probe1", "✗ 40 Jahre, nicht schwerbehindert") in nein.personen
    assert ergebnis(haushalt("103", (70, None), (None, None))).ergebnis == "unklar"


def test_einkommensart_ist_zusaetzlich_noetig(regel):
    """Jede Person ab 60 oder schwerbehindert UND der Haushalt hat eine der Einkommensarten."""
    bg = Einkommensart.objects.create(bezeichnung="Bürgergeld")
    wg = Einkommensart.objects.create(bezeichnung="Wohngeld")
    rente = Einkommensart.objects.create(bezeichnung="Rente")
    regel.verlaengern_einkommensarten.set([bg, wg])
    # Einkommensart allein genügt nicht mehr
    assert ergebnis(haushalt("104", (30, None), einkommensart=bg)).ergebnis == "nein"
    gemischt = haushalt("106", (70, None), (40, {"schwerbehindert": True}), einkommensart=wg)
    assert ergebnis(gemischt).ergebnis == "ok"
    p = ergebnis(haushalt("107", (70, None), (65, None), einkommensart=rente))
    assert p.ergebnis == "nein" and "Einkommensart „Rente“ zählt nicht" in p.gruende
    assert p.fehlt == ["Einkommensart des Haushalts: Rente (nötig: Bürgergeld oder Wohngeld)"]
    text = verlaengerung.ablehnung_notiz(p, regel)
    assert ("Die Regel besagt: Jede Person im Haushalt muss eine der Bedingungen erfüllen (ab 60 "
            "Jahren oder Schwerbehindert), und zusätzlich muss der Haushalt eine dieser "
            "Einkommensarten haben: Bürgergeld oder Wohngeld.") in text  # fmt: skip
    assert "– Einkommensart des Haushalts: Rente" in text and "zählt nicht." not in text
    p = ergebnis(haushalt("108", (70, None)))  # Einkommensart nicht erfasst
    assert p.ergebnis == "unklar" and "Einkommensart fehlt – bitte selbst prüfen" in p.gruende
    assert verlaengerung.bedingungen_text(regel) == (
        "ab 60 Jahren oder Schwerbehindert; zusätzlich Einkommensart Bürgergeld oder Wohngeld"
    )
    # Nur Einkommensarten eingestellt: Alter und Merkmale zählen nicht
    regel.verlaengern_ab_alter = None
    regel.save()
    regel.verlaengern_felder.clear()
    assert ergebnis(haushalt("109", (30, None), einkommensart=bg)).ergebnis == "ok"
    p = ergebnis(haushalt("119", (30, None), einkommensart=rente))
    assert verlaengerung.bedingungen_text(regel) == "Einkommensart Bürgergeld oder Wohngeld"
    assert "Die Regel besagt: Der Haushalt muss eine dieser Einkommensarten haben: " in (
        verlaengerung.ablehnung_notiz(p, regel)
    )


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
    regel.verlaengern_fruehestens_tage = 0  # jederzeit: nur ein Hinweis
    regel.save()
    Sperre.objects.all().delete()
    assert "Ausweis noch gültig bis 30.06.2027" in ergebnis(h).hinweise
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
        "Verlängert wird, wenn jede Person im Haushalt mindestens 60 Jahre alt ist oder "
        "„Schwerbehindert“ hat. Eine dieser Bedingungen genügt je Person." in seite
    )
    assert 'name="wahl_201" value="verlaengern" checked' in seite
    assert 'name="wahl_203" value="verlaengern">' in seite  # unklar: nicht vorbelegt
    assert 'name="wahl_203" value="" checked' in seite
    assert 'name="wahl_202" value="verlaengern"' not in seite  # nicht verlängerbar
    assert (
        'name="wahl_202" value="ablehnen" checked>\n              Notiz an die Ausgabestelle'
    ) in seite
    assert "30.11.2027" in seite  # neu bis
    assert 'name="an_stelle"' in seite  # Startseite der Ausgabestelle nur auf Wunsch
    antwort = admin_client.post(VERLAENGERN, {"monate": "12", "wahl_201": "verlaengern",
                                              "wahl_202": "ablehnen", "wahl_203": ""})  # fmt: skip
    assert antwort.status_code == 302
    for h in gemeldet:
        h.refresh_from_db()
    assert ok.ausweis_gueltig_bis == dt.date(2027, 11, 30)
    assert nein.ausweis_gueltig_bis == dt.date(2026, 11, 30)  # nicht verlängert
    assert nein.status == Haushalt.Status.AKTIV  # kein Statuswechsel
    # Gemeldete Notiz gestrichen, neue Notiz an die Ausgabestelle mit Grund
    assert not Notiz.objects.filter(kundennummer__in=["201", "202"], text=GEPRUEFT).exists()
    assert Notiz.objects.filter(kundennummer="203", text=GEPRUEFT).exists()  # nicht gewählt
    texte = list(Notiz.objects.filter(kundennummer="202").values_list("text", flat=True))
    assert "Bringt nächste Woche den Bescheid" in texte
    neu = next(t for t in texte if t.startswith("Ausweis kann **NICHT!**"))
    # Ohne Haken nicht auf der Startseite der Ausgabestelle; Verlängerte bekommen keine Notiz
    assert not Notiz.objects.filter(an_stelle=True).exists()
    assert not Notiz.objects.filter(kundennummer="201").exclude(text=GEPRUEFT).exists()
    assert neu == (
        "Ausweis kann **NICHT!** verlängert werden.\n"
        "Die Regel besagt: Jede Person im Haushalt muss eine der Bedingungen erfüllen "
        "(ab 60 Jahren oder Schwerbehindert).\n"
        "In diesem Haushalt sind folgende Kriterien nicht erfüllt:\n"
        "– Vera Probe1: 35 Jahre, nicht schwerbehindert\n"
        "Der Kunde muss ein Pausenjahr einlegen; der Ausweis gilt noch bis 30.11.2026. "
        "Danach ist eine Neuanmeldung über unsere Homepage möglich."
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
    assert 'name="wahl_202" value="ablehnen" checked>\n              6 Monate pausieren' in seite
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
    assert text == "Ausweis kann **NICHT!** verlängert werden.\nStatus „beendet“."


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
        "Ausweis kann **NICHT!** verlängert werden"
    )


def test_ablehnung_text_eine_person_und_ein_jahr(regel):
    """Regel „mindestens eine Person“; ein Kind mit 1 Jahr heißt „1 Jahr“."""
    regel.verlaengern_regel = KundenEinstellungen.Verlaengern.EINE
    regel.save()
    h = haushalt("901", (35, None), (1, None))
    p = ergebnis(h, regel)
    text = verlaengerung.ablehnung_notiz(p, regel)
    assert "Die Regel besagt: Mindestens eine Person im Haushalt muss eine der Bedingungen" in text
    assert "– Vera Probe0: 35 Jahre, nicht schwerbehindert\n" in text
    assert "– Vera Probe1: 1 Jahr, nicht schwerbehindert\n" in text


def test_zu_frueh_gemeldet_bekommt_notiz(gemeldet, admin_client):
    """Höchstens 60 Tage (einstellbar) vor dem Ablauf wird verlängert."""
    h = Haushalt.objects.get(kundennummer="201")
    h.ausweis_gueltig_bis = dt.date(2027, 3, 31)
    h.save()
    p = ergebnis(h)
    assert p.ergebnis == "nein" and p.zu_frueh == dt.date(2027, 1, 30)
    seite = admin_client.get(VERLAENGERN).content.decode()
    assert "verlängern frühestens ab 30.01.2027" in seite
    assert 'name="wahl_201" value="verlaengern"' not in seite
    assert "Notiz: zu früh" in seite
    admin_client.post(VERLAENGERN, {"wahl_201": "ablehnen"})
    h.refresh_from_db()
    assert h.ausweis_gueltig_bis == dt.date(2027, 3, 31) and h.status == Haushalt.Status.AKTIV
    assert Notiz.objects.filter(kundennummer="201").get().text == (
        "Ausweis wird noch **nicht** verlängert: Er gilt noch bis 31.03.2027. Verlängert wird "
        "frühestens ab 30.01.2027 – bitte dann erneut melden."
    )
    assert not Nachricht.objects.filter(kundennummer="201", erledigt_am__isnull=True).exists()


def test_verwaltung_lehnt_trotz_erfuellter_bedingungen_ab(gemeldet, admin_client):
    antwort = admin_client.post(VERLAENGERN, {"wahl_201": "ablehnen", "wahl_203": "ablehnen"},
                                follow=True)  # fmt: skip
    assert "Ohne Begründung nicht abgelehnt (die Bedingungen sind erfüllt): 201, 203" in (
        antwort.content.decode()
    )
    assert Notiz.objects.filter(kundennummer="201", text=GEPRUEFT).exists()  # nichts geschehen
    admin_client.post(VERLAENGERN, {"wahl_201": "ablehnen", "grund_201": "Umzug nach Bochum",
                                    "an_stelle": "1"})  # fmt: skip
    h = Haushalt.objects.get(kundennummer="201")
    assert h.ausweis_gueltig_bis == dt.date(2026, 11, 30) and h.status == Haushalt.Status.AKTIV
    n = Notiz.objects.get(kundennummer="201", an_stelle=True)
    assert n.text == "Ausweis wird **NICHT!** verlängert.\nBegründung: Umzug nach Bochum"
    text = "Nicht verlängert (Verwaltung): Umzug nach Bochum"
    assert HaushaltEreignis.objects.filter(kundennummer="201", text=text).exists()


def test_anmerkung_zur_ablehnung(gemeldet, admin_client):
    admin_client.post(VERLAENGERN, {"wahl_202": "ablehnen", "grund_202": "Bitte Rücksprache"})
    text = Notiz.objects.filter(kundennummer="202").first().text
    assert text.startswith("Ausweis kann **NICHT!**")
    assert text.endswith("\nAnmerkung der Verwaltung: Bitte Rücksprache")


def test_nur_anzeigen_mit_begruendung(gemeldet, admin_client):
    KundenEinstellungen.objects.update(verlaengern_ablehnung="anzeigen")
    admin_client.post(VERLAENGERN, {"wahl_202": "ablehnen", "grund_202": "Einkommen zu hoch"})
    assert Notiz.objects.filter(kundennummer="202", text__contains="Einkommen zu hoch").exists()
    assert Haushalt.objects.get(kundennummer="202").status == Haushalt.Status.AKTIV


def test_regel_als_satz(regel, admin_client):
    """Die Regel steht als ganzer Satz da, damit „ab 60“ nicht wie die einzige Bedingung wirkt."""
    from apps.kunden.models import Einkommensart

    satz = verlaengerung.regel_satz
    assert satz(regel) == ("Verlängert wird, wenn jede Person im Haushalt mindestens 60 Jahre alt "
                           "ist oder „Schwerbehindert“ hat. Eine dieser Bedingungen genügt je "
                           "Person.")  # fmt: skip
    regel.verlaengern_felder.clear()  # Schwerbehindert nicht mehr als Bedingung
    regel.verlaengern_regel = KundenEinstellungen.Verlaengern.EINE
    regel.verlaengern_einkommensarten.set(
        [
            Einkommensart.objects.create(bezeichnung="Wohngeld"),
            Einkommensart.objects.create(bezeichnung="Rente"),
        ]
    )
    assert satz(regel) == ("Verlängert wird, wenn mindestens eine Person im Haushalt mindestens 60 "
                           "Jahre alt ist. Zusätzlich muss der Haushalt eine dieser "
                           "Einkommensarten haben: Rente oder Wohngeld.")  # fmt: skip
    regel.verlaengern_ab_alter = None
    assert satz(regel).startswith("Für die Personen ist keine Bedingung eingestellt.")
    regel.verlaengern_regel = KundenEinstellungen.Verlaengern.OHNE
    assert satz(regel) == "Ohne Bedingung: Jeder gemeldete Haushalt kann verlängert werden."
    regel.save()
    seite = admin_client.get(reverse("kunden:einstellungen")).content.decode()
    assert 'id="verlaengern-regel" data-autosave-aktualisieren' in seite
    assert "Ohne Bedingung: Jeder gemeldete Haushalt" in seite


def test_erledigte_bleiben_sichtbar_und_lassen_sich_wieder_oeffnen(gemeldet, admin_client):
    admin_client.post(VERLAENGERN, {"wahl_201": "verlaengern", "wahl_202": "ablehnen"})
    seite = admin_client.get(VERLAENGERN).content.decode()
    assert "Erledigt (2)" in seite
    assert "Verlängert bis 30.11.2027" in seite and "Nicht verlängert" in seite
    n = Nachricht.objects.filter(kundennummer="201").first()
    assert n.ergebnis == "Verlängert bis 30.11.2027" and n.erledigt_von == "chefin"
    # Nochmal prüfen: beide Meldungen zu 201 stehen wieder oben
    antwort = admin_client.post(VERLAENGERN, {"wieder_oeffnen": str(n.pk)}, follow=True)
    assert "Kunde 201 steht wieder oben zum Prüfen." in antwort.content.decode()
    assert Nachricht.objects.filter(kundennummer="201", anliegen="verlaengern",
                                    erledigt_am__isnull=True).count() == 2  # fmt: skip
    seite = admin_client.get(VERLAENGERN).content.decode()
    assert "Erledigt (1)" in seite and 'name="wahl_201"' in seite
    assert admin_client.post(VERLAENGERN, {"wieder_oeffnen": "x"}).status_code == 302
