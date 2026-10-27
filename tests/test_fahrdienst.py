"""Modul Fahrdienst (ADR 0074). Alle Namen sind erfunden."""

import datetime as dt

import pytest
from django.core import mail as django_mail
from django.urls import reverse

from apps.core.models import MailEinstellungen, PapierkorbEintrag, TafelEinstellungen
from apps.fahrdienst import plan
from apps.fahrdienst.models import (
    Ausfall,
    Besetzung,
    Ersatz,
    FahrdienstEinstellungen,
    Springer,
    Tour,
)
from apps.konten import rollen

pytestmark = pytest.mark.django_db
MITTWOCH = dt.date(2026, 11, 11)
PLAN = reverse("fahrdienst:plan")


@pytest.fixture(autouse=True)
def modul_an():
    t = TafelEinstellungen.laden()
    t.module = ["fahrdienst"]
    t.bundesland = "NW"
    t.save()


def person(benutzer_mit_rolle, name, rolle=rollen.FAHRER, email=""):
    vorname, nachname = name.split()
    b = benutzer_mit_rolle(vorname.lower(), rolle)
    b.first_name, b.last_name, b.email = vorname, nachname, email
    b.save()
    return b


@pytest.fixture
def team(benutzer_mit_rolle):
    p = {n.split()[0].lower(): person(benutzer_mit_rolle, n) for n in (
        "Max Mustermann", "Jan Beispiel", "Kai Nordmann", "Eva Lindner", "Ole Hansen",
        "Tim Weber")}  # fmt: skip
    steele = Tour.objects.create(name="Steele", reihenfolge=2, plaetze=2)
    mitte = Tour.objects.create(name="Mitte", reihenfolge=1, plaetze=2)
    for tag in ("Mo", "Mi"):
        Besetzung.objects.create(tour=mitte, wochentag=tag, platz=1, benutzer=p["max"])
        Besetzung.objects.create(tour=mitte, wochentag=tag, platz=2, benutzer=p["jan"])
        Besetzung.objects.create(tour=steele, wochentag=tag, platz=1, benutzer=p["kai"])
        Besetzung.objects.create(tour=steele, wochentag=tag, platz=2, benutzer=p["eva"])
    Springer.objects.create(benutzer=p["ole"])
    Springer.objects.create(benutzer=p["tim"], wochentage="Fr")
    return p, mitte, steele


def namen(personen):
    return [b.first_name for b in personen]


def test_plan_ausfall_und_ersatz(team):
    p, mitte, steele = team
    tage = plan.tage([MITTWOCH])
    assert [t.name for t, _ in tage[0][1]] == ["Mitte", "Steele"]  # nach Reihenfolge
    _, plaetze = tage[0][1][1]
    assert [(x.wer.first_name, x.status, x.name) for x in plaetze] == [
        ("Kai", plan.OK, "Fahrer"),
        ("Eva", plan.OK, "Beifahrer"),
    ]
    plan.ausfall_melden(p["kai"], MITTWOCH, None, "krank", "", "kai")
    platz = plan.platz(MITTWOCH, steele, 1)
    assert platz.status == plan.OFFEN and platz.ausfall.grund == "krank"
    # Frei: Springer ohne Einschränkung (Tim nur freitags), dann niemand weiter
    springer, weitere = plan.verfuegbar(MITTWOCH)
    assert namen(springer) == ["Ole"] and weitere == []
    assert namen(plan.verfuegbar(dt.date(2026, 11, 13))[0]) == ["Ole", "Tim"]  # Freitag
    plan.ersatz_eintragen(MITTWOCH, steele, 1, p["ole"], "chefin")
    platz = plan.platz(MITTWOCH, steele, 1)
    assert platz.status == plan.ERSETZT and platz.wer == p["ole"] and platz.stamm == p["kai"]
    assert "Ole" not in namen(plan.verfuegbar(MITTWOCH)[0])  # schon eingeteilt
    # Fällt der Ersatz selbst aus, ist der Platz wieder offen
    plan.ausfall_melden(p["ole"], MITTWOCH, MITTWOCH, "sonstiges", "", "ole")
    assert plan.platz(MITTWOCH, steele, 1).status == plan.OFFEN
    plan.ersatz_eintragen(MITTWOCH, steele, 1, None, "chefin")
    assert not Ersatz.objects.exists()
    # Einsätze: fest und als Ersatz
    plan.ersatz_eintragen(MITTWOCH, steele, 2, p["max"], "chefin")
    assert [(x.tour.name, x.name) for x in plan.einsaetze(p["max"], MITTWOCH, MITTWOCH)] == [
        ("Mitte", "Fahrer"),
        ("Steele", "Beifahrer"),
    ]


def test_fahrtage_und_feiertage(team):
    e = FahrdienstEinstellungen.laden()
    tage = plan.fahrtage(dt.date(2026, 12, 21), dt.date(2026, 12, 27), e)
    assert [t.day for t in tage] == [21, 22, 23, 24]  # 25. und 26. Feiertage, Wochenende frei
    e.feiertage_frei = False
    e.fahrtage = "Mo, Sa"
    assert [t.day for t in plan.fahrtage(dt.date(2026, 12, 21), dt.date(2026, 12, 27), e)] == [
        21,
        26,
    ]


def test_mail_an_die_fahrdienstleitung(team, benutzer_mit_rolle, settings,
                                       django_capture_on_commit_callbacks):  # fmt: skip
    p, _, _ = team
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    leitung = person(benutzer_mit_rolle, "Lea Leitung", rollen.BUERO, "lea@example.org")
    person(benutzer_mit_rolle, "Bob Buero", rollen.BUERO, "bob@example.org")
    assert plan.empfaenger() == ["bob@example.org", "lea@example.org"]  # alle, die planen
    e = FahrdienstEinstellungen.laden()
    e.benachrichtigen.set([leitung])
    assert plan.empfaenger() == ["lea@example.org"]  # normalerweise eine Person
    with django_capture_on_commit_callbacks(execute=True):
        plan.ausfall_melden(p["kai"], MITTWOCH, MITTWOCH + dt.timedelta(days=5), "krank",
                            "Rücken", "kai", "https://tafel.example.org/fahrdienst/")  # fmt: skip
    m = django_mail.outbox[-1]
    assert m.to == ["lea@example.org"] and "Kai Nordmann fällt im Fahrdienst aus" in m.body
    assert "Mi 11.11.2026, Tour Steele, Fahrer. Freie Springer: Ole Hansen" in m.body
    assert "Mo 16.11.2026, Tour Steele, Fahrer" in m.body and "Rücken" in m.body
    assert "https://tafel.example.org/fahrdienst/" in m.body


def test_seiten_und_rechte(team, client, admin_client, anmelden, benutzer_mit_rolle):
    p, mitte, steele = team
    Ausfall.objects.create(benutzer=p["kai"], von=MITTWOCH, bis=MITTWOCH, grund="krank")
    seite = admin_client.get(PLAN, {"monat": "2026-11"}).content.decode()
    assert "Fahrerplan November 2026" in seite and "fd-offen" in seite and "Kai Nordmann" in seite
    assert "fällt aus (krank)" in seite  # Grund nur für die Planung
    url = reverse("fahrdienst:platz", args=["2026-11-11", steele.pk, 1])
    assert "Ole Hansen" in admin_client.get(url).content.decode()
    admin_client.post(url, {"benutzer": p["ole"].pk})
    assert Ersatz.objects.get().benutzer == p["ole"]
    falsch = reverse("fahrdienst:platz", args=["kein-datum", 1, 1])
    assert admin_client.get(falsch).status_code == 404
    assert admin_client.get(reverse("fahrdienst:platz", args=["2026-11-11", steele.pk, 3])
                            ).status_code == 404  # fmt: skip

    # Fahrer: sieht den Plan ohne Grund, meldet selbst, sieht eigene Einsätze
    anmelden(client, p["eva"])
    seite = client.get(PLAN, {"monat": "2026-11"}).content.decode()
    assert "krank" not in seite and "fd-platz" in seite
    assert client.get(url).status_code == 403
    antwort = client.post(reverse("fahrdienst:ausfall"), {"von": "2026-11-16", "bis": "",
                                                          "grund": "urlaub"})  # fmt: skip
    assert antwort.status_code == 302
    a = Ausfall.objects.get(benutzer=p["eva"])
    assert a.bis == a.von == dt.date(2026, 11, 16) and a.eingetragen_von == "eva"
    meine = client.get(reverse("fahrdienst:meine")).content.decode()
    assert "Gemeldete Ausfälle" in meine and "16.11.2026" in meine
    client.post(reverse("fahrdienst:ausfall_loeschen", args=[a.pk]))
    assert not Ausfall.objects.filter(benutzer=p["eva"]).exists()
    assert PapierkorbEintrag.objects.get().art == "Ausfall im Fahrdienst"
    # Fremden Ausfall darf sie nicht löschen; ohne Erlaubnis kein Selbstmelden
    kai = Ausfall.objects.get(benutzer=p["kai"])
    assert client.post(reverse("fahrdienst:ausfall_loeschen", args=[kai.pk])).status_code == 403
    FahrdienstEinstellungen.objects.update(selbst_melden=False)
    assert client.get(reverse("fahrdienst:ausfall")).status_code == 403
    assert "Ausfall melden" not in client.get(reverse("fahrdienst:meine")).content.decode()


def test_falsche_eingaben(team, admin_client):
    p, _, _ = team
    antwort = admin_client.post(
        reverse("fahrdienst:ausfall"),
        {"benutzer": p["jan"].pk, "von": "2026-11-16", "bis": "2026-11-10", "grund": "krank"},
    )
    assert "Das Ende liegt vor dem Anfang" in antwort.content.decode()
    admin_client.post(
        reverse("fahrdienst:ausfall"),
        {"benutzer": p["jan"].pk, "von": "2026-11-16", "bis": "2026-11-20", "grund": "krank"},
    )
    assert Ausfall.objects.get(benutzer=p["jan"]).bis == dt.date(2026, 11, 20)


def test_einstellungen_touren_besetzung_springer(team, admin_client):
    p, mitte, steele = team
    seite = admin_client.get(reverse("fahrdienst:einstellungen")).content.decode()
    assert "Steele" in seite and "Ole Hansen" in seite
    admin_client.post(
        reverse("fahrdienst:einstellungen"),
        {"selbst_melden": "", "fahrtage": ["Mo", "Di"], "aufbewahren_monate": 6},
    )
    e = FahrdienstEinstellungen.laden()
    assert (e.selbst_melden, e.fahrtage, e.aufbewahren_monate) == (False, "Mo, Di", 6)
    antwort = admin_client.post(reverse("fahrdienst:tour_neu"),
                                {"name": "Sondertour", "reihenfolge": 9, "plaetze": 3,
                                 "aktiv": "on"})  # fmt: skip
    neu = Tour.objects.get(name="Sondertour")
    assert antwort.url == reverse("fahrdienst:besetzung", args=[neu.pk])
    url = reverse("fahrdienst:besetzung", args=[neu.pk])
    assert 'name="b_Di_3"' in admin_client.get(url).content.decode()
    admin_client.post(url, {"b_Mo_1": p["tim"].pk, "b_Di_2": p["ole"].pk, "b_Di_3": "999999"})
    assert {(b.wochentag, b.platz, b.benutzer.first_name) for b in neu.besetzungen.all()} == {
        ("Mo", 1, "Tim"),
        ("Di", 2, "Ole"),
    }
    admin_client.post(url, {"b_Mo_1": p["max"].pk, "b_Di_2": ""})  # ändern und leeren
    assert [(b.wochentag, b.benutzer.first_name) for b in neu.besetzungen.all()] == [("Mo", "Max")]
    admin_client.post(reverse("fahrdienst:tour_loeschen", args=[neu.pk]))
    assert not Tour.objects.filter(name="Sondertour").exists()
    assert PapierkorbEintrag.objects.get().art == "Tour"
    # Springer: nur an bestimmten Tagen; dieselbe Person nicht doppelt
    s = Springer.objects.get(benutzer=p["tim"])
    admin_client.post(reverse("fahrdienst:springer", args=[s.pk]),
                      {"benutzer": p["tim"].pk, "wochentage": ["Mi", "Fr"]})  # fmt: skip
    s.refresh_from_db()
    assert s.wochentage == "Mi, Fr"
    form = admin_client.get(reverse("fahrdienst:springer_neu")).content.decode()
    assert "Tim Weber" not in form and "Max Mustermann" in form
    admin_client.post(reverse("fahrdienst:springer_loeschen", args=[s.pk]))
    assert not Springer.objects.filter(benutzer=p["tim"]).exists()


def test_fristen_menue_und_auskunft(team, admin_client, pdf_text):
    p, _, steele = team
    alt = dt.date(2025, 1, 10)
    Ausfall.objects.create(benutzer=p["kai"], von=alt, bis=alt, grund="krank")
    Ersatz.objects.create(datum=alt, tour=steele, platz=1, benutzer=p["ole"])
    Ausfall.objects.create(benutzer=p["kai"], von=MITTWOCH, bis=MITTWOCH, grund="urlaub")
    assert plan.fristen_anwenden(dt.date(2026, 11, 1)) == 2
    assert Ausfall.objects.count() == 1 and not Ersatz.objects.exists()
    start = admin_client.get(reverse("core:start")).content.decode()
    assert "Fahrerplan" in start and "Fahrdienst: Touren und Springer" in start
    text = pdf_text(admin_client.get(reverse("konten:auskunft", args=[p["kai"].pk])))
    assert "Fahrdienst" in text and "Steele" in text and "Urlaub" in text


def test_telegram_ohne_grund(team, admin_client, monkeypatch, django_capture_on_commit_callbacks):
    from apps.core import geheimnis
    from apps.fahrdienst import telegram

    p, _, _ = team
    gesendet = []

    def aufruf(schluessel, methode, daten=None):
        if schluessel != "123:ABC":
            raise telegram.TelegramFehler("Telegram kennt diesen Bot-Schlüssel nicht.")
        if methode == "getUpdates":
            chat = {"id": 4711, "first_name": "Lea", "last_name": "Leitung"}
            return [{"message": {"chat": chat}}, {"update_id": 2}]
        gesendet.append(daten)
        return {}

    monkeypatch.setattr(telegram, "_aufruf", aufruf)
    seite = reverse("fahrdienst:einstellungen")
    tg = reverse("fahrdienst:telegram")
    antwort = admin_client.post(tg, {"aktion": "suchen"}, follow=True)
    assert "zuerst den Bot-Schlüssel" in antwort.content.decode()
    admin_client.post(seite, {"fahrtage": ["Mo", "Mi"], "aufbewahren_monate": 12,
                              "telegram_schluessel": " 123:ABC "})  # fmt: skip
    e = FahrdienstEinstellungen.laden()
    assert geheimnis.entschluesseln(e.telegram_schluessel_verschluesselt) == "123:ABC"
    assert "123:ABC" not in admin_client.get(seite).content.decode()  # nie im Klartext zurück
    assert "Ein Schlüssel ist gespeichert" in admin_client.get(seite).content.decode()
    antwort = admin_client.post(tg, {"aktion": "suchen"}, follow=True).content.decode()
    assert "Lea Leitung: 4711" in antwort
    antwort = admin_client.post(tg, {"aktion": "test"}, follow=True).content.decode()
    assert "mindestens eine Chat-ID" in antwort
    admin_client.post(seite, {"fahrtage": ["Mo", "Mi"], "aufbewahren_monate": 12,
                              "telegram_chats": "4711; 815"})  # fmt: skip
    e.refresh_from_db()
    assert telegram.chats(e) == ["4711", "815"] and telegram.schluessel(e) == "123:ABC"
    assert "an 2 Chat(s)" in admin_client.post(tg, {"aktion": "test"}, follow=True).content.decode()
    gesendet.clear()
    with django_capture_on_commit_callbacks(execute=True):
        plan.ausfall_melden(p["kai"], MITTWOCH, None, "krank", "Rücken", "kai")
    assert [d["chat_id"] for d in gesendet] == ["4711", "815"]
    text = gesendet[0]["text"]
    assert "Kai Nordmann fällt aus am 11.11.2026" in text and "Tour Steele" in text
    assert "krank" not in text and "Rücken" not in text  # Gesundheitsangaben nicht zu Telegram
    # Telegram-Fehler: Ausfall bleibt, nur Protokoll
    monkeypatch.setattr(
        telegram,
        "_aufruf",
        lambda *a, **k: (_ for _ in ()).throw(telegram.TelegramFehler("nicht erreichbar")),
    )
    with django_capture_on_commit_callbacks(execute=True):
        plan.ausfall_melden(p["eva"], MITTWOCH, None, "urlaub", "", "eva")
    assert Ausfall.objects.filter(benutzer=p["eva"]).exists()
    assert "nicht erreichbar" in admin_client.post(tg, {"aktion": "test"}, follow=True
                                                   ).content.decode()  # fmt: skip
    admin_client.post(seite, {"fahrtage": ["Mo"], "aufbewahren_monate": 12,
                              "telegram_schluessel_loeschen": "on"})  # fmt: skip
    e.refresh_from_db()
    assert e.telegram_schluessel_verschluesselt == "" and not telegram.eingerichtet(e)


def test_telegram_schnittstelle(monkeypatch):
    import io
    import json
    from urllib.error import HTTPError, URLError

    from apps.fahrdienst import telegram

    antworten = []

    def urlopen(anfrage, timeout):
        antworten.append(anfrage.full_url)
        wert = antworten_queue.pop(0)
        if isinstance(wert, Exception):
            raise wert
        return io.BytesIO(json.dumps(wert).encode())

    antworten_queue = [{"ok": True, "result": [1]}, {"ok": False, "description": "chat not found"},
                       HTTPError("u", 401, "x", {}, None), HTTPError("u", 500, "x", {}, None),
                       URLError("weg")]  # fmt: skip
    monkeypatch.setattr(telegram, "urlopen", urlopen)
    assert telegram._aufruf("1:A", "getUpdates") == [1]
    assert antworten[0] == "https://api.telegram.org/bot1:A/getUpdates"
    for erwartet in ("chat not found", "kennt diesen Bot-Schlüssel nicht", "Fehler 500",
                     "nicht erreichbar"):  # fmt: skip
        with pytest.raises(telegram.TelegramFehler, match=erwartet):
            telegram._aufruf("1:A", "sendMessage", {"chat_id": "1"})


def test_plan_als_pdf(team, admin_client, pdf_text):
    p, _, steele = team
    Ausfall.objects.create(benutzer=p["kai"], von=MITTWOCH, bis=MITTWOCH, grund="krank")
    plan.ersatz_eintragen(MITTWOCH, steele, 2, p["ole"], "chefin")
    antwort = admin_client.get(reverse("fahrdienst:pdf"), {"monat": "2026-11"})
    assert antwort["Content-Disposition"].endswith('fahrerplan-2026-11.pdf"')
    text = pdf_text(antwort)
    assert "Fahrerplan November 2026" in text and "offen" in text and "Ole Hansen" in text
    assert "(für Eva Lindner)" in text and "Springer" in text and "nur Fr" in text
    assert "krank" not in text
    assert "Drucken (PDF)" in admin_client.get(PLAN).content.decode()
    FahrdienstEinstellungen.objects.update(fahrtage="")
    leer = pdf_text(admin_client.get(reverse("fahrdienst:pdf"), {"monat": "2026-11"}))
    assert "keine Fahrtage" in leer


def test_gaeste_und_mindestbesetzung(team, admin_client, pdf_text):
    p, mitte, steele = team
    steele.plaetze, steele.mindestbesetzung = 3, 2
    steele.save()
    platz3 = plan.platz(MITTWOCH, steele, 3)
    assert platz3.status == plan.LEER and not platz3.fehlt  # Gästeplatz, nichts fehlt
    Besetzung.objects.filter(tour=steele, wochentag="Mi", platz=2).delete()
    assert plan.platz(MITTWOCH, steele, 2).status == plan.UNBESETZT
    seite = admin_client.get(PLAN, {"monat": "2026-11"}).content.decode()
    assert "<strong>unbesetzt</strong>" in seite and "+ Gast" in seite
    url = reverse("fahrdienst:platz", args=["2026-11-11", steele.pk, 3])
    assert "Platz für Gäste" in admin_client.get(url).content.decode()
    admin_client.post(url, {"benutzer": "", "gast": "  Gerda Gast  "})
    g = plan.platz(MITTWOCH, steele, 3)
    assert (g.gast, g.status, g.wer) == ("Gerda Gast", plan.ERSETZT, None)
    assert str(Ersatz.objects.get()) == "11.11.2026 Steele Beifahrer: Gerda Gast (Gast)"
    seite = admin_client.get(PLAN, {"monat": "2026-11"}).content.decode()
    assert "Gerda Gast <small>(Gast)</small>" in seite
    text = pdf_text(admin_client.get(reverse("fahrdienst:pdf"), {"monat": "2026-11"}))
    assert "Gerda Gast" in text and "unbesetzt" in text
    admin_client.post(url, {"benutzer": "", "gast": ""})  # zurücknehmen
    assert not Ersatz.objects.exists()
    # Mindestbesetzung nicht größer als die Zahl der Plätze
    antwort = admin_client.post(
        reverse("fahrdienst:tour", args=[steele.pk]),
        {"name": "Steele", "reihenfolge": 2, "plaetze": 2, "mindestbesetzung": 3, "aktiv": "on"},
    )
    assert "Mehr als die Zahl der Plätze" in antwort.content.decode()


def test_beispiel_plan(admin_client):
    from apps.fahrdienst import beispiel

    assert not beispiel.vorhanden()
    admin_client.post(reverse("fahrdienst:beispiel"), {"aktion": "anlegen"})
    assert beispiel.vorhanden()
    assert list(Tour.objects.values_list("name", "plaetze", "mindestbesetzung")) == [
        (n, 3, 2) for n in beispiel.TOUREN
    ]
    tage = plan.tage(plan.fahrtage(dt.date(2026, 11, 9), dt.date(2026, 11, 13)))
    for _, zeile in tage:
        heute = [p.wer.pk for _, plaetze in zeile for p in plaetze if p.wer]
        assert len(heute) == len(set(heute))  # niemand zweimal am Tag
        assert all(not p.fehlt for _, plaetze in zeile for p in plaetze)
    from django.contrib.auth import get_user_model

    konto = get_user_model().objects.filter(username__startswith=beispiel.PRAEFIX).first()
    assert not konto.has_usable_password()  # erfundene Konten können sich nicht anmelden
    assert Springer.objects.count() == 3
    seite = admin_client.get(reverse("fahrdienst:einstellungen")).content.decode()
    assert "Beispiel neu würfeln" in seite and "Beispiel entfernen" in seite
    beispiel.anlegen(seed=1)  # wiederholbar, ohne doppelte Konten
    assert get_user_model().objects.filter(username__startswith=beispiel.PRAEFIX).count() == 23
    echt = Tour.objects.create(name="Echte Tour")
    admin_client.post(reverse("fahrdienst:beispiel"), {"aktion": "entfernen"})
    assert not beispiel.vorhanden() and list(Tour.objects.all()) == [echt]


def test_monat_oeffnen_und_besetzung_vom_plan_aendern(team, admin_client, anmelden, client):
    """Jeder Monat lässt sich wieder öffnen; die feste Besetzung ist vom Plan aus erreichbar."""
    p, mitte, steele = team
    seite = admin_client.get(PLAN, {"m": "03", "jahr": "2025"}).content.decode()
    assert "Fahrerplan März 2025" in seite
    assert '<option value="03" selected>März</option>' in seite and "<option selected>2025" in seite
    besetzung = reverse("fahrdienst:besetzung", args=[steele.pk])
    assert f'href="{besetzung}?monat=2025-03"' in seite
    zurueck = admin_client.get(besetzung, {"monat": "2025-03"}).content.decode()
    assert f'href="{PLAN}?monat=2025-03">← Fahrerplan' in zurueck
    antwort = admin_client.post(f"{besetzung}?monat=2025-03", {"b_Mo_1": p["max"].pk})
    assert antwort.url == f"{PLAN}?monat=2025-03"
    assert admin_client.post(besetzung, {}).url == reverse("fahrdienst:einstellungen")
    platz = reverse("fahrdienst:platz", args=["2026-11-11", steele.pk, 1])
    assert f'href="{besetzung}?monat=2026-11"' in admin_client.get(platz).content.decode()
    anmelden(client, p["eva"])  # ohne Planungsrecht keine Links zur Besetzung
    assert besetzung not in client.get(PLAN, {"monat": "2026-11"}).content.decode()
