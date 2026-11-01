"""Modul Dienstplan der Ausgabe (ADR 0077). Alle Namen sind erfunden."""

import datetime as dt
from itertools import count

import pytest
from django.core import mail as django_mail
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core.models import MailEinstellungen, PapierkorbEintrag, TafelEinstellungen
from apps.dienstplan import beispiel, plan
from apps.dienstplan.models import (
    Aufgabe,
    Ausfall,
    Besetzung,
    DienstplanEinstellungen,
    DienstStelle,
    Diensttag,
    Ersatz,
)
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle

_zaehler = count(1)


def _helfer(vorname="", nachname="", konto=None, telefon="", email=""):
    """Eine im Dienstplan einteilbare Person: Konto mit der Rolle Ausgabe (ADR 0097)."""
    if konto is None:
        from django.contrib.auth import get_user_model
        from django.contrib.auth.models import Group

        konto = get_user_model().objects.create(username=f"dp-helfer-{next(_zaehler)}")
        konto.groups.add(Group.objects.get_or_create(name=rollen.AUSGABE)[0])
    return Adresse.objects.create(
        art=Adresse.Art.PERSON,
        vorname=vorname,
        nachname=nachname,
        telefon=telefon,
        email=email,
        konto=konto,
    )


pytestmark = pytest.mark.django_db
FREITAG = dt.date(2026, 11, 13)
PLAN = reverse("dienstplan:plan")


@pytest.fixture(autouse=True)
def modul_an():
    t = TafelEinstellungen.laden()
    t.module = ["dienstplan"]
    t.bundesland = "NW"
    t.save()


@pytest.fixture
def team(benutzer_mit_rolle):
    """Ausgabestelle Mitte mit Ausgabe Mo und Fr; Kasse, 2× Obst, Springer (darf leer)."""
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")  # macht nicht mit
    ds = DienstStelle.objects.create(ausgabestelle=mitte, aktiv=True, tage="Mo, Fr")
    DienstStelle.objects.create(ausgabestelle=nord, aktiv=False, tage="Mo")
    konto = benutzer_mit_rolle("erika", rollen.AUSGABE)
    konto.first_name, konto.last_name, konto.email = "Erika", "Muster", "erika@example.org"
    konto.save()
    h = {"erika": _helfer("Erika", "Muster", konto=konto, email="erika@example.org")}
    for vorname, nachname in (("Paul", "Probe"), ("Lea", "Leitung"), ("Tom", "Teich"),
                              ("Uwe", "Ufer")):  # fmt: skip
        h[vorname.lower()] = _helfer(vorname, nachname, telefon="0123 4567")
    h["lea"].email = "lea@example.org"
    h["lea"].save()
    a = {}
    for i, (name, pflicht) in enumerate([("Kasse", True), ("Obst", True), ("Obst", True),
                                         ("Springer", False)], start=1):  # fmt: skip
        a[i] = Aufgabe.objects.create(
            stelle=ds,
            wochentag="Fr",
            name=name,
            reihenfolge=i,
            von=dt.time(11, 30),
            bis=dt.time(15),
            pflicht=pflicht,
        )
    Besetzung.objects.create(aufgabe=a[1], helfer=h["erika"])
    Besetzung.objects.create(aufgabe=a[2], helfer=h["paul"])
    Diensttag.objects.create(stelle=ds, wochentag="Fr", teamleitung=h["lea"], telefon="0123 999")
    return ds, h, a


def test_einteilbar_ueber_rolle(benutzer_mit_rolle):
    """Einteilbar ist, wer ein Konto mit einer der eingestellten Rollen hat (Vorgabe Ausgabe)."""
    ausgabe_konto = benutzer_mit_rolle("ausi", rollen.AUSGABE)
    a_ausgabe = _helfer("Ausi", "Ausgabe", konto=ausgabe_konto)
    buero_konto = benutzer_mit_rolle("bueri", rollen.BUERO)
    a_buero = _helfer("Buer", "Büro", konto=buero_konto)

    frei = plan.verfuegbar(FREITAG)
    assert a_ausgabe in frei and a_buero not in frei  # Vorgabe: nur Ausgabe
    # Tafel stellt Büro als einteilbare Rolle ein → jetzt ist auch das Büro-Konto dabei
    e = DienstplanEinstellungen.laden()
    e.rollen = [rollen.AUSGABE, rollen.BUERO]
    e.save()
    frei = plan.verfuegbar(FREITAG)
    assert a_ausgabe in frei and a_buero in frei


def test_plan_wie_auf_papier(team, admin_client, pdf_text):
    ds, h, a = team
    daten, zeilen = plan.monat(ds, "Fr", dt.date(2026, 11, 1), dt.date(2026, 11, 30))
    assert daten == [dt.date(2026, 11, d) for d in (6, 13, 20, 27)]
    assert [z[0].name for z in zeilen] == ["Kasse", "Obst", "Obst", "Springer"]
    assert [p.status for _, ps in zeilen for p in ps[:1]] == [plan.OK, plan.OK, plan.UNBESETZT,
                                                             plan.LEER]  # fmt: skip
    seite = admin_client.get(PLAN, {"stelle": ds.ausgabestelle_id, "tag": "Fr",
                                    "monat": "2026-11"}).content.decode()  # fmt: skip
    assert "Dienstplan Freitag · November 2026" in seite and "Erika Muster" in seite
    auswahl = seite.split('id="dp-stelle"')[1].split("</select>")[0]
    assert "Mitte" in auswahl and "Nord" not in auswahl  # macht nicht mit
    assert "Teamleitung: Lea Leitung" in seite and "4 offene Plätze" in seite
    text = pdf_text(
        admin_client.get(
            reverse("dienstplan:pdf"), {"stelle": ds.ausgabestelle_id, "monat": "2026-11"}
        )
    )
    assert "Freitag" in text and "November" in text and "Paul Probe" in text
    assert "Abmeldungen bitte bei Lea Leitung unter 0123 999" in text
    assert "11.30-15.00" in text


def test_ausfall_ersatz_und_benachrichtigung(team, admin_client, settings,
                                             django_capture_on_commit_callbacks):  # fmt: skip
    ds, h, a = team
    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    with django_capture_on_commit_callbacks(execute=True):
        plan.ausfall_melden(h["paul"], FREITAG, FREITAG + dt.timedelta(days=7), "krank", "",
                            "chefin", "https://tafel.example.org/dienstplan/")  # fmt: skip
    post = django_mail.outbox[-1]
    assert post.to == ["lea@example.org"]  # Teamleitung des Freitags
    assert "Paul Probe fällt in der Ausgabe aus" in post.body and "(krank)" in post.body
    assert "Fr 13.11.2026, Mitte: Obst 11.30-15.00" in post.body
    assert "Fr 20.11.2026" in post.body
    p = plan.platz(FREITAG, a[2])
    assert p.status == plan.OFFEN and p.fehlt
    # Ersatz: wer ausfällt oder schon eingeteilt ist, steht nicht zur Wahl
    frei = plan.verfuegbar(FREITAG)
    assert h["paul"] not in frei and h["erika"] not in frei and h["tom"] in frei
    url = reverse("dienstplan:platz", args=[FREITAG.isoformat(), a[2].pk])
    seite = admin_client.get(url).content.decode()
    assert "Paul Probe" in seite and "Tom Teich" in seite
    antwort = admin_client.post(url, {"helfer": h["paul"].pk}, follow=True)
    assert "kann am 13.11.2026 nicht einspringen" in antwort.content.decode()
    admin_client.post(url, {"helfer": h["tom"].pk})
    assert plan.platz(FREITAG, a[2]).status == plan.ERSETZT
    assert h["tom"] not in plan.verfuegbar(FREITAG)  # jetzt eingeteilt
    admin_client.post(reverse("dienstplan:platz", args=[FREITAG.isoformat(), a[3].pk]),
                      {"gast": "Gisela Gast"})  # fmt: skip
    assert Ersatz.objects.get(aufgabe=a[3]).gast == "Gisela Gast"
    assert admin_client.get(reverse("dienstplan:platz", args=["2026-11-12", a[2].pk])
                            ).status_code == 404  # Donnerstag: keine Ausgabe  # fmt: skip


def test_ohne_teamleitung_alle_die_planen(team, benutzer_mit_rolle):
    ds, h, a = team
    Diensttag.objects.filter(stelle=ds).update(teamleitung=None)
    buero = benutzer_mit_rolle("bea", rollen.BUERO)
    buero.email = "bea@example.org"
    buero.save()
    assert "bea@example.org" in plan.empfaenger(plan.einsaetze(h["paul"], FREITAG, FREITAG))


def test_helfer_mit_konto_traegt_sich_selbst_aus(team, client, anmelden, admin):
    ds, h, a = team
    anmelden(client, h["erika"].konto)
    seite = client.get(PLAN, {"stelle": ds.ausgabestelle_id, "monat": "2026-11"}).content.decode()
    ausfall = reverse("dienstplan:ausfall")
    assert f'href="{ausfall}?von=2026-11-13" title="Ich kann nicht – austragen"' in seite
    assert "/dienstplan/platz/" not in seite  # ohne Planungsrecht kein Ersatz
    meine = client.get(reverse("dienstplan:meine")).content.decode()
    assert "Mitte · Kasse 11.30-15.00" in meine
    client.post(ausfall, {"von": "2026-11-13", "dauer": "14", "bis": "", "grund": "urlaub"})
    x = Ausfall.objects.get(helfer=h["erika"])
    assert (x.von, x.bis) == (FREITAG, dt.date(2026, 11, 26))
    client.post(reverse("dienstplan:ausfall_loeschen", args=[x.pk]))
    assert not Ausfall.objects.exists()
    assert PapierkorbEintrag.objects.get().art == "Ausfall im Dienstplan"
    DienstplanEinstellungen.objects.update(selbst_melden=False)
    assert client.get(ausfall).status_code == 403


def test_einstellungen_stelle_aufgaben_kopieren(team, admin_client):
    ds, h, a = team
    url = reverse("dienstplan:stelle", args=[ds.ausgabestelle_id])
    seite = admin_client.get(url, {"tag": "Fr"}).content.decode()
    assert "Kasse" in seite and 'name="h_' in seite
    admin_client.post(url, {"aktion": "stelle", "aktiv": "on", "tage": ["Mo", "Mi", "Fr"]})
    ds.refresh_from_db()
    assert ds.tage == "Mo, Mi, Fr"
    admin_client.post(f"{url}?tag=Fr", {"aktion": "aufgabe", "name": "Brot", "von": "11:30",
                                         "bis": "15:00", "pflicht": "on"})  # fmt: skip
    assert ds.aufgaben.filter(wochentag="Fr", name="Brot", reihenfolge=5).exists()
    admin_client.post(f"{url}?tag=Fr", {"aktion": "besetzung", f"h_{a[3].pk}": h["uwe"].pk,
                                         f"h_{a[1].pk}": ""})  # fmt: skip
    assert Besetzung.objects.get(aufgabe=a[3]).helfer == h["uwe"]
    assert not Besetzung.objects.filter(aufgabe=a[1]).exists()
    admin_client.post(f"{url}?tag=Fr", {"aktion": "tag", "teamleitung": h["tom"].pk,
                                         "telefon": ""})  # fmt: skip
    assert Diensttag.objects.get(stelle=ds, wochentag="Fr").teamleitung == h["tom"]
    admin_client.post(f"{url}?tag=Mi", {"aktion": "kopieren", "von": "Fr"})
    assert ds.aufgaben.filter(wochentag="Mi").count() == 5
    assert Besetzung.objects.filter(aufgabe__wochentag="Mi", helfer=h["uwe"]).exists()
    admin_client.post(reverse("dienstplan:aufgabe_loeschen", args=[a[4].pk]))
    assert not Aufgabe.objects.filter(pk=a[4].pk).exists()
    # Helfer werden im Adressbuch gepflegt (ADR 0097): nur aktive Helfer-Personen werden
    # angeboten, andere Adressen nicht.
    _helfer("Nina", "Neu")
    Adresse.objects.create(art=Adresse.Art.PERSON, nachname="Extern")  # kein Helfer
    seite = admin_client.get(reverse("dienstplan:einstellungen")).content.decode()
    assert "Nina Neu" in seite and "Extern" not in seite


def test_standard_aufgaben_fuer_alle_ausgabetage(admin_client):
    stelle = Ausgabestelle.objects.create(name="Zentrale")
    ds = DienstStelle.objects.create(ausgabestelle=stelle, aktiv=True, tage="Mo, Mi, Fr")
    Aufgabe.objects.create(stelle=ds, wochentag="Mi", name="Kasse", reihenfolge=1)
    url = reverse("dienstplan:stelle", args=[stelle.pk])
    seite = admin_client.get(url, {"tag": "Mo"}).content.decode()
    assert "Standard-Aufgaben anlegen" in seite
    antwort = admin_client.post(f"{url}?tag=Mo", {"aktion": "standard"}, follow=True)
    assert "Standard-Aufgaben angelegt für: Montag, Freitag." in antwort.content.decode()
    fr = list(ds.aufgaben.filter(wochentag="Fr"))
    assert len(fr) == 20 and ds.aufgaben.filter(wochentag="Mi").count() == 1  # Mi bleibt
    assert [(a.name, a.zeit) for a in fr[:3]] == [("Teamleitung", "09.00-15.00"),
                                                  ("Frühdienst", "08.00-15.00"),
                                                  ("Frühdienst", "08.00-15.00")]  # fmt: skip
    assert [a.pflicht for a in fr if a.name == "Springer"] == [False, False, False]
    assert not Besetzung.objects.filter(aufgabe__stelle=ds).exists()
    antwort = admin_client.post(f"{url}?tag=Mo", {"aktion": "standard"}, follow=True)
    assert "nichts angelegt" in antwort.content.decode()
    assert ds.aufgaben.count() == 41
    # Mi hat schon Aufgaben: Knopf zum Ersetzen nur dieses Tages
    seite = admin_client.get(url, {"tag": "Mi"}).content.decode()
    assert "Standard-Aufgaben für Mittwoch anlegen" in seite
    antwort = admin_client.post(f"{url}?tag=Mi", {"aktion": "standard", "ersetzen": "Mi"},
                                follow=True)  # fmt: skip
    assert "Standard-Aufgaben angelegt für: Mittwoch." in antwort.content.decode()
    assert ds.aufgaben.filter(wochentag="Mi").count() == 20 and ds.aufgaben.count() == 60


def test_beispiel_und_fristen(admin_client):
    admin_client.post(reverse("dienstplan:beispiel"), {"aktion": "anlegen"})
    ds = DienstStelle.objects.get(ausgabestelle__name=beispiel.STELLE)
    assert ds.tage == "Mo, Mi, Fr" and ds.aufgaben.filter(wochentag="Fr").count() == 20
    daten, zeilen = plan.monat(ds, "Fr", dt.date(2026, 11, 1), dt.date(2026, 11, 30))
    pflicht = [p for a, ps in zeilen if a.pflicht for p in ps]
    assert pflicht and all(p.status == plan.OK for p in pflicht)  # alle Pflichtplätze besetzt
    namen = [p.wer.pk for a, ps in zeilen for p in ps[:1] if p.wer]
    assert len(namen) == len(set(namen))  # niemand doppelt am selben Tag
    assert Diensttag.objects.get(stelle=ds, wochentag="Fr").teamleitung is not None
    admin_client.post(reverse("dienstplan:beispiel"), {"aktion": "entfernen"})
    assert not Adresse.objects.filter(notiz=beispiel.KENNUNG).exists()
    assert not Ausgabestelle.objects.filter(name=beispiel.STELLE).exists()
    # Fristen: alte Ausfälle weg
    h = _helfer("Alt", "Ausfall")
    Ausfall.objects.create(helfer=h, von=dt.date(2020, 1, 1), bis=dt.date(2020, 1, 2))
    assert plan.fristen_anwenden(dt.date(2026, 11, 1)) == 1


def test_rechte(team, client, anmelden, benutzer_mit_rolle, admin):
    anmelden(client, benutzer_mit_rolle("fahrer", rollen.FAHRER))
    assert client.get(PLAN).status_code == 403
    anmelden(client, benutzer_mit_rolle("ausgabe2", rollen.AUSGABE))
    assert client.get(PLAN).status_code == 200
    assert client.get(reverse("dienstplan:einstellungen")).status_code == 403


def test_handy_ansicht_ein_tag_je_karte(team, admin_client, monkeypatch):
    """Schmale Bildschirme: eine Karte je Ausgabetag, gleichnamige Aufgaben zusammen, vergangene
    Tage unter „Frühere Tage“, der nächste Ausgabetag aufgeklappt."""
    ds, h, a = team
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *args: FREITAG)
    antwort = admin_client.get(
        PLAN, {"stelle": ds.ausgabestelle_id, "tag": "Fr", "monat": "2026-11"}
    )
    frueher, karten = antwort.context["karten_frueher"], antwort.context["karten"]
    assert [k["datum"].day for k in frueher] == [6]
    assert [(k["datum"].day, k["offen"]) for k in karten] == [(13, True), (20, False), (27, False)]
    assert [(g["name"], len(g["plaetze"])) for g in karten[0]["gruppen"]] == [
        ("Kasse", 1), ("Obst", 2), ("Springer", 1)]  # fmt: skip
    assert karten[0]["fehlen"] == 1  # zweites Obst ist unbesetzt
    seite = antwort.content.decode()
    assert "Frühere Tage (1)" in seite and "Freitag, 13.11." in seite
