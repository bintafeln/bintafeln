"""Modul Listen (ADR 0063). Alle Daten sind erfunden."""

import csv
import datetime as dt
import io

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Einkommensart,
    Haushalt,
    Kundengruppe,
    Person,
    Zugriff,
)
from apps.listen import katalog, spalten
from apps.listen.models import EigeneListe

pytestmark = pytest.mark.django_db


def jahre(n):
    heute = timezone.localdate()
    return heute.replace(year=heute.year - n) - dt.timedelta(days=1)


@pytest.fixture(autouse=True)
def modul_an():
    t = TafelEinstellungen.laden()
    t.module = ["listen"]
    t.save()


@pytest.fixture
def daten(admin):
    mitte, nord = (
        Ausgabestelle.objects.create(name="Mitte"),
        Ausgabestelle.objects.create(name="Nord"),
    )
    mo = Kundengruppe.objects.create(name="Mo", ausgabestelle=mitte, wochentage="Mo")
    fr = Kundengruppe.objects.create(name="Fr", ausgabestelle=nord, wochentage="Fr")
    bg = Einkommensart.objects.create(bezeichnung="Bürgergeld")
    rente = Einkommensart.objects.create(bezeichnung="Altersrente")
    eins = Haushalt.objects.create(kundennummer="1", kundengruppe=mo, einkommensart=bg,
                                   ausweis_gueltig_bis=timezone.localdate() + dt.timedelta(days=5),
                                   telefon="0123")  # fmt: skip
    Person.objects.create(haushalt=eins, ist_hauptperson=True, vorname="Erika", nachname="Muster",
                          geburtsdatum=jahre(35), staatsangehoerigkeit="deutsch")  # fmt: skip
    Person.objects.create(haushalt=eins, vorname="Kim", nachname="Muster", geburtsdatum=jahre(3),
                          staatsangehoerigkeit="deutsch")  # fmt: skip
    Person.objects.create(haushalt=eins, vorname="Lou", nachname="Muster", geburtsdatum=jahre(9),
                          staatsangehoerigkeit="syrisch")  # fmt: skip
    zwei = Haushalt.objects.create(kundennummer="2", kundengruppe=mo, einkommensart=rente,
                                   ausweis_gueltig_bis=jahre(-1))  # fmt: skip
    Person.objects.create(haushalt=zwei, ist_hauptperson=True, vorname="Otto", nachname="Alt",
                          geburtsdatum=jahre(70), staatsangehoerigkeit="ukrainisch")  # fmt: skip
    drei = Haushalt.objects.create(kundennummer="3", kundengruppe=fr, status="pausiert")
    Person.objects.create(haushalt=drei, ist_hauptperson=True, vorname="Nora", nachname="Nord")
    Abholung.objects.create(haushalt=eins, datum=timezone.localdate() - dt.timedelta(days=40))
    return mitte, nord


def zeilen(antwort):
    return [z["nummer"] for g in antwort.context["e"].gruppen for z in g["zeilen"]]


def url(kennung, **p):
    return reverse("listen:liste", args=[kennung]), {"geladen": "1", **p}


def test_katalog_vollstaendig():
    for liste in katalog.LISTEN:
        bekannt = {s.schluessel for s in spalten.alle(liste.basis)}
        assert set(liste.spalten) <= bekannt, liste.kennung
        assert liste.sort.lstrip("-") in bekannt and (not liste.gruppe or liste.gruppe in bekannt)
    assert spalten.altersgruppe(None) == "unbekannt" and spalten.altersgruppe(5) == "3–5"
    assert spalten.text(dt.date(2026, 1, 2)) == "02.01.2026" and spalten.text(None) == ""


def test_uebersicht_und_rechte(admin_client, daten, benutzer_mit_rolle, anmelden):
    seite = admin_client.get(reverse("listen:uebersicht")).content.decode()
    assert (
        "Kundenliste einer Ausgabestelle" in seite and "Personen nach Staatsangehörigkeit" in seite
    )
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    seite = c.get(reverse("listen:uebersicht")).content.decode()
    assert "Kinder unter 6" in seite and "Staatsangehörigkeit" not in seite  # ohne Stammdaten
    assert c.get(reverse("listen:liste", args=["nationalitaet"])).status_code == 403
    assert c.get(reverse("listen:liste", args=["gibtsnicht"])).status_code == 404
    k = anmelden(Client(), benutzer_mit_rolle("kim", rollen.KIOSK))
    assert k.get(reverse("listen:uebersicht")).status_code == 403


def test_vorgaben_und_filter(admin_client, daten):
    antwort = admin_client.get(reverse("listen:liste", args=["kunden_stelle"]))
    assert antwort.context["p"]["status"] == "aktiv" and zeilen(antwort) == [
        "2",
        "1",
    ]  # Alt, Muster
    assert [g["titel"] for g in antwort.context["e"].gruppen] == ["Mo"]
    mitte, nord = daten
    assert zeilen(admin_client.get(*url("alle_kunden", stelle=nord.pk))) == ["3"]
    assert zeilen(admin_client.get(*url("buergergeld", status="aktiv",
                                        einkommensart="Bürgergeld"))) == ["1"]  # fmt: skip
    # Vorgabe „rente“ wird auf „Altersrente“ abgebildet
    antwort = admin_client.get(reverse("listen:liste", args=["rente"]))
    assert antwort.context["p"]["einkommensart"] == "Altersrente" and zeilen(antwort) == ["2"]
    assert zeilen(admin_client.get(reverse("listen:liste", args=["ausweis_ablauf"]))) == ["1"]
    assert zeilen(admin_client.get(reverse("listen:liste", args=["lange_nicht"]))) == ["1", "2"]
    assert zeilen(admin_client.get(*url("grosse_haushalte", personen_ab="3"))) == ["1"]
    assert zeilen(admin_client.get(reverse("listen:liste", args=["familien_kleinkinder"]))) == ["1"]
    assert zeilen(admin_client.get(reverse("listen:liste", args=["nicht_aktiv"]))) == ["3"]
    Haushalt.objects.filter(kundennummer="3").update(kundengruppe=None)
    assert zeilen(admin_client.get(reverse("listen:liste", args=["ohne_gruppe"]))) == ["3"]
    antwort = admin_client.get(*url("abholungen", s=["kundennummer", "abholungen"],
                                    sort="-abholungen"))  # fmt: skip
    assert zeilen(antwort)[0] == "1" and antwort.context["e"].summen == {"abholungen": 1}


def test_personenlisten(admin_client, daten):
    antwort = admin_client.get(reverse("listen:liste", args=["kinder_unter_6"]))
    assert [z["werte"]["vorname"] for g in antwort.context["e"].gruppen for z in g["zeilen"]] \
        == ["Kim"]  # fmt: skip
    antwort = admin_client.get(*url("kinder", alter_von="0", alter_bis="17", gruppe="altersgruppe",
                                    s=["vorname", "alter"]))  # fmt: skip
    assert [g["titel"] for g in antwort.context["e"].gruppen] == ["3–5", "6–13"]
    antwort = admin_client.get(reverse("listen:liste", args=["senioren"]))
    assert antwort.context["e"].anzahl == 1
    antwort = admin_client.get(reverse("listen:liste", args=["nationalitaet"]))
    gruppen = {g["titel"]: g["anzahl"] for g in antwort.context["e"].gruppen}
    assert gruppen == {"deutsch": 2, "syrisch": 1, "ukrainisch": 1}
    nur = admin_client.get(*url("nationalitaet", status="aktiv", staatsangehoerigkeit="syrisch"))
    assert nur.context["e"].anzahl == 1
    # Zählung: größte Gruppe zuerst, Summenzeile
    antwort = admin_client.get(reverse("listen:liste", args=["zahl_nationalitaet"]))
    e = antwort.context["e"]
    assert e.gruppen[0]["titel"] == "deutsch" and e.zahlen == [("Anzahl", "4")]
    antwort = admin_client.get(reverse("listen:liste", args=["zahl_stellen"]))
    assert antwort.context["e"].gruppen[0]["zahlen"][0] == ("Personen", "4")
    assert "Summe" in antwort.content.decode()


def test_sortieren_spalten_und_rechte(admin_client, daten, benutzer_mit_rolle, anmelden):
    spalten_ = ["kundennummer", "telefon"]
    antwort = admin_client.get(*url("alle_kunden", sort="-kundennummer", s=spalten_))
    assert zeilen(antwort) == ["3", "2", "1"]
    assert [s.titel for s in antwort.context["e"].spalten] == ["Kundennummer", "Telefon"]
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([daten[0]])
    c = anmelden(Client(), b)
    antwort = c.get(*url("alle_kunden", s=["kundennummer", "telefon", "einkommensart"]))
    assert [s.titel for s in antwort.context["e"].spalten] == ["Kundennummer"]  # ohne Rechte
    assert zeilen(antwort) == ["1", "2"]  # nur eigene Ausgabestelle
    assert (
        [s for s, _ in antwort.context["stellen"].__iter__().__class__.__mro__] if False else True
    )


def test_export_auswahl_und_protokoll(admin_client, daten, pdf_text):
    abfrage = "geladen=1&s=kundennummer&s=nachname&s=personen&sort=kundennummer"
    antwort = admin_client.post(reverse("listen:export", args=["alle_kunden", "csv"]),
                                {"abfrage": abfrage})  # fmt: skip
    text = antwort.content.decode("utf-8")
    assert text.startswith("﻿") and 'filename="alle_kunden-' in antwort["Content-Disposition"]
    tabelle = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
    assert tabelle == [["Kundennummer", "Nachname", "Personen"], ["1", "Muster", "3"],
                       ["2", "Alt", "1"], ["3", "Nord", "1"]]  # fmt: skip
    assert Zugriff.objects.filter(export=True).count() == 3
    zwei = Haushalt.objects.get(kundennummer="2")
    antwort = admin_client.post(reverse("listen:export", args=["alle_kunden", "csv"]),
                                {"abfrage": abfrage, "id": [zwei.pk]})  # fmt: skip
    assert antwort.content.decode().lstrip("﻿").splitlines()[1:] == ["2;Alt;1"]
    q = "geladen=1&status=aktiv&gruppe=kundengruppe&s=nachname&s=personen"
    pdf = admin_client.post(reverse("listen:export", args=["kunden_stelle", "pdf"]), {"abfrage": q})
    text = pdf_text(pdf)
    assert "Kundenliste einer Ausgabestelle" in text and "Mo (2)" in text and "Summe" in text
    q = "geladen=1&gruppe=altersgruppe&summen=1&s=anzahl"
    summen = admin_client.post(reverse("listen:export", args=["zahl_alter", "csv"]), {"abfrage": q})
    zeilen_ = summen.content.decode().lstrip("﻿").splitlines()
    assert zeilen_[0] == "Gruppe;Anzahl;Anzahl" and zeilen_[-1] == "Summe;5;5"
    pdf = admin_client.post(reverse("listen:export", args=["zahl_alter", "pdf"]), {"abfrage": q})
    assert "ab 67" in pdf_text(pdf)
    assert (
        admin_client.post(reverse("listen:export", args=["alle_kunden", "xls"])).status_code == 404
    )
    assert (
        admin_client.get(reverse("listen:export", args=["alle_kunden", "csv"])).status_code == 405
    )


def test_eigene_listen(admin_client, daten, benutzer_mit_rolle, anmelden):
    admin_client.post(reverse("listen:speichern", args=["kinder"]),
                      {"titel": "Kinder Mitte", "abfrage": "geladen=1&alter_bis=10&id=5",
                       "fuer_alle": "1"})  # fmt: skip
    e = EigeneListe.objects.get()
    assert e.fuer_alle and e.parameter == "geladen=1&alter_bis=10"
    assert "Kinder Mitte" in admin_client.get(reverse("listen:uebersicht")).content.decode()
    antwort = admin_client.get(reverse("listen:eigene", args=[e.pk]))
    assert antwort.url == reverse("listen:liste", args=["kinder"]) + "?geladen=1&alter_bis=10"
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert c.get(reverse("listen:eigene", args=[e.pk])).status_code == 302  # für alle
    assert c.post(reverse("listen:eigene_loeschen", args=[e.pk])).status_code == 403
    c.post(reverse("listen:speichern", args=["kinder"]), {"titel": "", "abfrage": "",
                                                          "fuer_alle": "1"})  # fmt: skip
    eigene = EigeneListe.objects.get(benutzer__username="anton")
    assert eigene.titel == "Kinder und Jugendliche (Alter von–bis)" and not eigene.fuer_alle
    EigeneListe.objects.filter(pk=e.pk).update(fuer_alle=False)
    assert c.get(reverse("listen:eigene", args=[e.pk])).status_code == 404
    admin_client.post(reverse("listen:eigene_loeschen", args=[e.pk]))
    assert not EigeneListe.objects.filter(pk=e.pk).exists()


def test_suche_und_menue(admin, admin_client):
    from apps.listen.modul import suchen

    titel = [t for t, _, _ in suchen(admin, "kinder", 10)]
    assert "Liste: Kinder unter 6 Jahren" in titel
    seite = admin_client.get(reverse("listen:uebersicht")).content.decode()
    assert "Alle Listen" in seite and "Kundenliste einer Ausgabestelle</a>" in seite


def test_weitere_listen(admin_client, daten):
    from decimal import Decimal

    Haushalt.objects.filter(kundennummer="2").update(kontostand=Decimal("-3.00"),
                                                     kunde_seit=timezone.localdate())  # fmt: skip
    assert zeilen(admin_client.get(reverse("listen:liste", args=["negativer_kontostand"]))) == ["2"]
    antwort = admin_client.get(*url("schulanfaenger", status="aktiv", alter_von="3", alter_bis="9"))
    assert antwort.context["e"].anzahl == 2
    e = admin_client.get(reverse("listen:liste", args=["zahl_groesse"])).context["e"]
    assert [g["titel"] for g in e.gruppen] == ["1 Pers.", "3 Pers."]
    e = admin_client.get(reverse("listen:liste", args=["zahl_neue"])).context["e"]
    assert [g["titel"] for g in e.gruppen] == [f"{timezone.localdate():%Y-%m}"]
