"""Kundenliste: Filter nach Ausgabetag und CSV-Export (ADR 0058). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse

from apps.konten import rollen
from apps.kunden import export
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Zugriff,
    Zusatzfeld,
)

pytestmark = pytest.mark.django_db
LISTE = reverse("kunden:uebersicht")
EXPORT = reverse("kunden:exportieren")
MITTWOCH = dt.date(2026, 10, 21)


@pytest.fixture
def daten():
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    mo = Kundengruppe.objects.create(name="Montag", ausgabestelle=mitte, wochentage="Mo",
                                     uhrzeit=dt.time(12, 30))  # fmt: skip
    mi = Kundengruppe.objects.create(name="Mittwoch", ausgabestelle=mitte, wochentage="Mi, Fr")
    fr = Kundengruppe.objects.create(name="Nord Fr", ausgabestelle=nord, wochentage="Fr")
    for nr, g in (("101", mo), ("201", mi), ("301", fr)):
        h = Haushalt.objects.create(kundennummer=nr, kundengruppe=g, strasse="Weg 1", plz="1",
                                    ort="Musterstadt", telefon="0123",
                                    zusatz={"rad": True})  # fmt: skip
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname=f"M{nr}")
    return mitte, nord


def nummern(antwort):
    return [h.kundennummer for h in antwort.context["seite"].object_list]


def test_standard_tag():
    class B:
        ausgabetage = "Mo, Mi"

    assert export.standard_tag(B, MITTWOCH, ["Mo", "Mi", "Fr"]) == "Mi"  # heute ist eigener Tag
    assert export.standard_tag(B, MITTWOCH + dt.timedelta(days=1), ["Mo", "Mi"]) == "Mo"
    B.ausgabetage = "Sa"  # eigener Tag gibt es an der Stelle nicht: heute, falls Ausgabe
    assert export.standard_tag(B, MITTWOCH, ["Mi"]) == "Mi"
    assert export.standard_tag(B, MITTWOCH, ["Mo"]) == ""
    assert export.verfuegbare_tage(Kundengruppe(wochentage=w) for w in ("Fr, Mo", "Mo")) == [
        "Mo", "Fr"]  # fmt: skip


def test_tagesfilter_der_ausgabestelle(admin, daten, benutzer_mit_rolle, anmelden, monkeypatch):
    mitte, _ = daten
    monkeypatch.setattr(export.dt, "date", dt.date)
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    b.ausgabetage = "Mo"
    b.save()
    c = anmelden(Client(), b)
    antwort = c.get(LISTE)
    assert antwort.context["tage"] == ["Mo", "Mi", "Fr"]  # nur die eigene Ausgabestelle
    assert antwort.context["filter"]["tag"] == "Mo" and nummern(antwort) == ["101"]
    assert nummern(c.get(LISTE, {"tag": "Fr"})) == ["201"]  # Nord bleibt verborgen
    assert nummern(c.get(LISTE, {"tag": ""})) == ["101", "201"]
    assert nummern(c.get(LISTE, {"tag": "xx"})) == ["101", "201"]
    # Mit Suchtext ohne Tag: alle Tage, damit niemand übersehen wird
    assert nummern(c.get(LISTE, {"q": "Erika"})) == ["101", "201"]
    seite = c.get(LISTE).content.decode()
    assert '<option value="Mo" selected>Mo</option>' in seite and "tag=Mo" in seite


def test_export_csv(admin, daten, benutzer_mit_rolle, anmelden):
    mitte, _ = daten
    Zusatzfeld.objects.create(
        schluessel="rad",
        bezeichnung="Fahrrad",
        typ=Zusatzfeld.Typ.JA_NEIN,
        gilt_fuer=Zusatzfeld.GiltFuer.HAUSHALT,
    )
    e = KundenEinstellungen.laden()
    e.export_felder = ["kundennummer", "nachname", "uhrzeit", "telefon", "kontostand",
                       "zusatz:rad", "gibts:nicht"]  # fmt: skip
    e.save()
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    c = anmelden(Client(), b)
    antwort = c.get(EXPORT, {"tag": ""})
    text = antwort.content.decode("utf-8")
    assert antwort["Content-Type"].startswith("text/csv") and text.startswith("﻿")
    assert 'filename="kunden-' in antwort["Content-Disposition"]
    zeilen = text.lstrip("﻿").splitlines()
    assert zeilen[0] == "Kundennummer;Nachname;Uhrzeit;Telefon;Kontostand;Zusatzfeld: Fahrrad"
    # Ausgabe darf keine Kontaktdaten und kein Konto sehen: Spalten bleiben leer
    assert zeilen[1:] == ["101;M101;12:30;;;ja", "201;M201;;;;ja"]
    assert Zugriff.objects.filter(export=True, benutzername="anton").count() == 2
    antwort = c.get(EXPORT, {"tag": "Mo"})
    assert "kunden-mo-" in antwort["Content-Disposition"]
    assert len(antwort.content.decode().splitlines()) == 2


def test_export_vorgabe_und_admin(admin_client, daten):
    zeilen = admin_client.get(EXPORT, {"tag": "Fr"}).content.decode().lstrip("﻿")
    kopf, *rest = zeilen.splitlines()
    assert kopf == "Kundennummer;Vorname;Nachname;Kundengruppe;Ausgabetage;Uhrzeit;Personen"
    assert rest == ["201;Erika;M201;Mittwoch;Mi, Fr;;1", "301;Erika;M301;Nord Fr;Fr;;1"]
    e = KundenEinstellungen.laden()
    e.export_felder = ["telefon", "ausgabestelle", "status", "erwachsene", "kinder", "ausweis",
                       "letzter_besuch", "kontostand", "strasse", "plz", "ort",
                       "email"]  # fmt: skip
    e.save()
    zeilen = admin_client.get(EXPORT, {"tag": "Mo"}).content.decode().lstrip("﻿")
    assert zeilen.splitlines()[1] == "0123;Mitte;aktiv;1;0;;;;Weg 1;1;Musterstadt;"
    liste = admin_client.get(LISTE, {"tag": ""}).content.decode()
    assert "als CSV exportieren" in liste


def test_art9_zusatzfeld_nur_mit_recht(admin, daten, benutzer_mit_rolle, anmelden):
    Zusatzfeld.objects.create(schluessel="rad", bezeichnung="Fahrrad", typ=Zusatzfeld.Typ.JA_NEIN,
                              gilt_fuer=Zusatzfeld.GiltFuer.HAUSHALT,
                              besondere_kategorie=True)  # fmt: skip
    e = KundenEinstellungen.laden()
    e.export_felder = ["kundennummer", "zusatz:rad"]
    e.save()
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    zeilen = c.get(EXPORT, {"tag": "Mo"}).content.decode().lstrip("﻿").splitlines()
    assert zeilen[1] == "101;"


def test_einstellungen_und_mitarbeiter(admin_client, daten, admin):
    Zusatzfeld.objects.create(
        schluessel="rad",
        bezeichnung="Fahrrad",
        typ=Zusatzfeld.Typ.JA_NEIN,
        gilt_fuer=Zusatzfeld.GiltFuer.HAUSHALT,
    )
    seite = admin_client.get(reverse("kunden:einstellungen")).content.decode()
    assert "Spalten des Exports der Kundenliste" in seite and "Zusatzfeld: Fahrrad" in seite
    form = admin_client.get(reverse("kunden:einstellungen")).context["form"]
    daten_ = {k: v for k, v in form.initial.items() if v not in (None, False)}
    daten_["export_felder"] = ["telefon", "kundennummer", "zusatz:rad"]
    admin_client.post(reverse("kunden:einstellungen"), daten_)
    assert KundenEinstellungen.laden().export_felder == ["kundennummer", "telefon", "zusatz:rad"]
    seite = admin_client.get(reverse("konten:mitarbeiter", args=[admin.pk])).content.decode()
    assert "Ausgabetage" in seite


def test_ausgabetage_speichern(admin_client, benutzer_mit_rolle):
    from apps.konten.forms import MitarbeiterForm

    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    form = MitarbeiterForm({"username": "anton", "ausgabetage": ["Fr", "Mo"]}, instance=b,
                           verwalter=b)  # fmt: skip
    form.is_valid()
    assert form.cleaned_data["ausgabetage"] == "Mo, Fr"
    b.ausgabetage = "Mo, Fr"
    assert MitarbeiterForm(instance=b, verwalter=b).initial["ausgabetage"] == ["Mo", "Fr"]
    b.save()


def test_ausgabetage_in_der_auskunft(admin_client, admin, pdf_text):
    admin.ausgabetage = "Mo, Mi"
    admin.save()
    text = pdf_text(admin_client.get(reverse("konten:auskunft", args=[admin.pk])))
    assert "Ausgabetage" in text and "Mo, Mi" in text


def test_export_nur_mit_recht(admin, benutzer_mit_rolle, anmelden):
    c = anmelden(Client(), benutzer_mit_rolle("kim", rollen.KIOSK))
    assert c.get(EXPORT).status_code == 403


def test_sortieren_und_blaettern(admin, daten, benutzer_mit_rolle, anmelden, monkeypatch):
    from apps.kunden import views

    monkeypatch.setattr(views, "LISTE_JE_SEITE", 1)
    Haushalt.objects.filter(kundennummer="301").update(ausweis_gueltig_bis=dt.date(2027, 1, 1))
    Haushalt.objects.create(kundennummer="1001", kundengruppe=Kundengruppe.objects.first())
    b = benutzer_mit_rolle("berta", rollen.BUERO)
    c = anmelden(Client(), b)
    erste = lambda **f: nummern(c.get(LISTE, {"tag": "", **f}))  # noqa: E731
    assert erste() == ["101"]  # Kundennummer als Zahl: 1001 nach 301
    assert erste(sort="-nr") == ["1001"]
    assert erste(sort="name") == ["101"] and erste(sort="-name") == ["301"]
    assert erste(sort="ausweis") == ["301"]  # leere Werte stehen hinten
    assert erste(sort="-ausweis") == ["301"]
    assert erste(sort="quatsch") == ["101"]
    seite = c.get(LISTE, {"tag": "", "sort": "name"}).content.decode()
    assert seite.count("Seite 1 von 4") == 2  # oben und unten
    assert "?sort=name&amp;tag=&amp;seite=2" in seite and 'class="sortieren auf"' in seite
    assert "sort=-name" in seite  # zweiter Klick: absteigend
    zeilen = c.get(EXPORT, {"tag": "", "sort": "-nr"}).content.decode().lstrip("﻿").splitlines()
    assert [z.split(";")[0] for z in zeilen[1:]] == ["1001", "301", "201", "101"]


def test_letzter_besuch_mit_uhrzeit(admin_client, daten):
    from apps.kunden.models import Abholung

    h = Haushalt.objects.get(kundennummer="101")
    assert h.letzter_besuch_text == ""
    h.letzter_besuch = dt.date(2026, 10, 19)
    h.save()
    assert h.letzter_besuch_text == "19.10.2026"
    Abholung.objects.create(haushalt=h, datum=h.letzter_besuch, uhrzeit=dt.time(12, 40))
    Abholung.objects.create(haushalt=h, datum=h.letzter_besuch, uhrzeit=dt.time(13, 5))
    assert Haushalt.objects.get(pk=h.pk).letzter_besuch_text == "19.10.2026 13:05"
    seite = admin_client.get(LISTE, {"tag": ""}).content.decode()
    assert "19.10.2026 13:05" in seite
    detail = admin_client.get(reverse("kunden:haushalt", args=["101"])).content.decode()
    assert "19.10.2026 13:05" in detail
    e = KundenEinstellungen.laden()
    e.export_felder = ["kundennummer", "letzter_besuch"]
    e.save()
    text = admin_client.get(EXPORT, {"tag": "Mo"}).content.decode()
    assert "101;19.10.2026 13:05" in text


def test_blaettern_vorlage(rf):
    from django.core.paginator import Paginator
    from django.template import Context, Template

    vorlage = Template(
        "{% load liste %}{% blaettern seite %}|"
        '{% blaettern seite ziel="#x" zusatz="Anträge" weiter="Älter" %}'
    )
    seite = Paginator(list(range(5)), 2).get_page(2)
    text = vorlage.render(
        Context({"seite": seite, "request": rf.get("/", {"q": "a b", "seite": "2"})})
    )
    assert 'href="?q=a+b&amp;seite=1"' in text and 'href="?q=a+b&amp;seite=3"' in text
    assert 'hx-target="#x"' in text and "· 5 Anträge" in text and "Älter" in text
    leer = Paginator([1], 2).get_page(1)
    assert vorlage.render(Context({"seite": leer, "request": rf.get("/")})).strip() == "|"
    ohne = Paginator(list(range(5)), 2).get_page(1)
    assert 'href="?seite=2"' in vorlage.render(Context({"seite": ohne, "request": rf.get("/")}))
