"""Modul Wochenübersicht (ADR 0054): Soll/Ist je Ausgabestelle und Tag, Selbstabholer, PDF."""

import datetime as dt
import io
import re

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Abholung, Ausgabestelle, Haushalt, Kundengruppe, Person
from apps.wochenuebersicht import auswertung
from apps.wochenuebersicht.models import Selbstabholer, StellenReihenfolge

pytestmark = pytest.mark.django_db
STICHTAG = dt.date(2026, 10, 21)  # Mittwoch


def gruppe(name, stelle, tage, maximum=None):
    return Kundengruppe.objects.create(name=name, ausgabestelle=stelle, wochentage=tage,
                                       maximum=maximum)  # fmt: skip


def haushalt(nummer, g, kinder=0, erwachsene=1, status=Haushalt.Status.AKTIV):
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=g, status=status)
    for i in range(erwachsene):
        Person.objects.create(haushalt=h, ist_hauptperson=i == 0, vorname="Erika",
                              nachname=f"Muster{i}", geburtsdatum=dt.date(1980, 1, 1))  # fmt: skip
    for i in range(kinder):
        Person.objects.create(haushalt=h, vorname="Kim", nachname=f"Muster{i}",
                              geburtsdatum=dt.date(2020, 1, 1))  # fmt: skip
    return h


@pytest.fixture
def daten():
    zentrale = Ausgabestelle.objects.create(name="Zentrale")
    nord = Ausgabestelle.objects.create(name="Nord")
    z1 = gruppe("Zentrale Mi 12:30", zentrale, "Mi", 10)
    z2 = gruppe("Zentrale Mi 13:00", zentrale, "Mi", 8)
    n = gruppe("Nord Mo/Do", nord, "Mo, Do")  # ohne Maximum, an zwei Tagen
    frei = gruppe("Sondergruppe", None, "Mi", 5)
    gruppe("Alt", zentrale, "Mi", 99).__class__.objects.filter(name="Alt").update(aktiv=False)
    haushalt("1", z1, kinder=2)
    haushalt("2", z1)
    haushalt("3", z2, erwachsene=2, kinder=1)
    haushalt("4", z2, status=Haushalt.Status.BEENDET)
    haushalt("5", n, kinder=1)
    haushalt("6", frei)
    return zentrale, nord


def test_soll_ist_je_tag(daten):
    d = auswertung.uebersicht(STICHTAG)
    tage = {t.kurz: t for t in d["tage"]}
    assert list(tage) == ["Mo", "Di", "Mi", "Do", "Fr"]  # Sa/So nur, wenn belegt
    mi = tage["Mi"]
    assert [z.name for z in mi.zeilen] == ["Zentrale", "Sondergruppe"]
    zentrale = mi.zeilen[0]
    assert (zentrale.soll, zentrale.haushalte, zentrale.erwachsene, zentrale.kinder) == (
        18,
        3,
        4,
        3,
    )
    assert zentrale.personen == 7 and zentrale.gruppen == ["Zentrale Mi 12:30", "Zentrale Mi 13:00"]
    assert (mi.summe.soll, mi.summe.haushalte, mi.summe.personen) == (23, 4, 8)
    # Nord zählt an beiden Tagen, ohne Maximum bleibt Soll leer
    for kurz in ("Mo", "Do"):
        nord = tage[kurz].zeilen[0]
        assert (nord.name, nord.soll, nord.haushalte, nord.kinder) == ("Nord", None, 1, 1)
    assert tage["Di"].zeilen == [] and tage["Di"].summe.soll is None
    assert d["gesamt"].personen == 8 + 2 + 2
    assert d["alle_personen"] == 12 and d["woche"] is None


def test_selbstabholer_und_samstag(daten):
    Selbstabholer.objects.create(name="Frauenhaus", tage="Mi, Sa", personen=12)
    Selbstabholer.objects.create(name="Alt", tage="Mi", personen=99, aktiv=False)
    d = auswertung.uebersicht(STICHTAG)
    tage = {t.kurz: t for t in d["tage"]}
    assert "Sa" in tage and "So" not in tage
    assert tage["Mi"].selbst_personen == 12 and tage["Mi"].summe.personen == 8
    assert d["selbst_gesamt"] == 24 and d["alle_personen"] == 12 + 24


def test_reihenfolge(daten):
    zentrale, nord = daten
    gruppe("Nord Mi", nord, "Mi")
    mi = next(t for t in auswertung.uebersicht(STICHTAG)["tage"] if t.kurz == "Mi")
    assert [z.name for z in mi.zeilen] == ["Nord", "Zentrale", "Sondergruppe"]
    StellenReihenfolge.objects.create(ausgabestelle=zentrale, reihenfolge=1)
    mi = next(t for t in auswertung.uebersicht(STICHTAG)["tage"] if t.kurz == "Mi")
    assert [z.name for z in mi.zeilen] == ["Zentrale", "Nord", "Sondergruppe"]


def test_abholungen_der_woche(daten):
    zentrale, nord = daten
    woche = auswertung.montag(STICHTAG)
    h1, h2 = Haushalt.objects.get(kundennummer="1"), Haushalt.objects.get(kundennummer="2")
    Abholung.objects.create(haushalt=h1, datum=STICHTAG, ausgabestelle=zentrale)
    Abholung.objects.create(haushalt=h2, datum=STICHTAG, ausgabestelle=zentrale)
    Abholung.objects.create(haushalt=h1, datum=STICHTAG - dt.timedelta(days=7),
                            ausgabestelle=zentrale)  # fmt: skip
    Abholung.objects.create(haushalt=h2, datum=STICHTAG)  # ohne Ausgabestelle: zählt nicht
    d = auswertung.uebersicht(STICHTAG, woche)
    mi = next(t for t in d["tage"] if t.kurz == "Mi")
    assert mi.zeilen[0].abgeholt == 2 and mi.zeilen[1].abgeholt is None
    assert mi.summe.abgeholt == 2 and d["gesamt"].abgeholt == 2
    mo = next(t for t in d["tage"] if t.kurz == "Mo")
    assert mo.zeilen[0].abgeholt == 0


@pytest.fixture
def modul_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["wochenuebersicht"]
    t.save()


def test_seiten_und_pdf(modul_an, admin_client, daten, pdf_text):
    seite = admin_client.get(reverse("wochenuebersicht:uebersicht")).content.decode()
    assert "Wochenübersicht der Ausgabestellen" in seite and "Zentrale" in seite
    assert "Abgeholt" not in seite
    seite = admin_client.get(reverse("wochenuebersicht:uebersicht"),
                             {"abholungen": "1", "kw": "2026-W43"}).content.decode()  # fmt: skip
    assert "Abgeholt" in seite and "KW 43" in seite
    seite = admin_client.get(reverse("wochenuebersicht:uebersicht"),
                             {"abholungen": "1", "kw": "kaputt"})  # fmt: skip
    assert seite.status_code == 200
    hoch = pdf_text(admin_client.get(reverse("wochenuebersicht:pdf", args=["hoch"]),
                                     {"abholungen": "1", "kw": "2026-W43"}))  # fmt: skip
    assert "Mittwoch" in hoch and "GESAMT ALLE PERSONEN" in hoch and "Abgeholt" in hoch
    Selbstabholer.objects.create(name="Frauenhaus", tage="Mi", personen=12)
    quer = pdf_text(admin_client.get(reverse("wochenuebersicht:pdf", args=["quer"])))
    assert "Verteilstelle" in quer and "Selbstabholer: Frauenhaus" in quer
    assert "Alle Personen 24" in quer
    hoch = pdf_text(admin_client.get(reverse("wochenuebersicht:pdf", args=["hoch"])))
    assert "Selbstabholer: Frauenhaus" in hoch and "(+12)" in hoch


def test_wochen_dropdown_und_pdf_knoepfe(modul_an, admin_client, daten):
    seite = admin_client.get(reverse("wochenuebersicht:uebersicht")).content.decode()
    # Kalenderwoche als Auswahlmenü der letzten 8 Wochen statt Wochen-Eingabefeld
    assert '<select name="kw">' in seite and 'type="week"' not in seite
    assert seite.count("<option") >= 8
    # PDF als ordentliche Knöpfe statt reiner Links
    assert seite.count('class="knopf knopf-zweitrangig"') >= 3  # Anzeigen + Hoch + Quer


LEER = {"k-TOTAL_FORMS": "2", "k-INITIAL_FORMS": "0", "k-MIN_NUM_FORMS": "0",
        "k-MAX_NUM_FORMS": "1000"}  # fmt: skip


def test_selbstabholer_pflegen(modul_an, admin_client):
    antwort = admin_client.post(reverse("wochenuebersicht:selbstabholer_neu"), {
        "name": "Frauenhaus", "tage": ["Mo", "Mi"], "personen": 12, "aktiv": "on", "notiz": "",
        "ort": "Musterstadt", "telefon": "0123 456", **LEER,
        "k-0-name": "Erika Muster", "k-0-funktion": "Leitung", "k-0-telefon": "0123 457",
        "k-0-email": "erika@example.org",
        "k-1-name": "Kim Probe", "k-1-funktion": "Fahrer", "k-1-email": "kein-mail",
    })  # fmt: skip
    assert antwort.status_code == 200 and not Selbstabholer.objects.exists()  # E-Mail falsch
    antwort = admin_client.post(reverse("wochenuebersicht:selbstabholer_neu"), {
        "name": "Frauenhaus", "tage": ["Mo", "Mi"], "personen": 12, "aktiv": "on", "notiz": "",
        "ort": "Musterstadt", "telefon": "0123 456", **LEER,
        "k-0-name": "Erika Muster", "k-0-funktion": "Leitung", "k-0-telefon": "0123 457",
        "k-0-email": "erika@example.org", "k-1-name": "Kim Probe", "k-1-funktion": "Fahrer",
    })  # fmt: skip
    s = Selbstabholer.objects.get()
    assert antwort.url == reverse("wochenuebersicht:selbstabholer_bearbeiten", args=[s.pk])
    assert s.tage == "Mo, Mi" and s.tage_liste == ["Mo", "Mi"] and s.ort == "Musterstadt"
    assert [k.name for k in s.kontakte.all()] == ["Erika Muster", "Kim Probe"]
    seite = admin_client.get(antwort.url).content.decode()
    assert re.search(r'value="Mi"[^>]*checked', seite) and 'value="Erika Muster"' in seite
    # Leere Zusatzzeilen werden nicht gespeichert; eine Ansprechperson entfernen
    erika, kim = s.kontakte.all()
    admin_client.post(antwort.url, {
        "name": "Frauenhaus", "tage": ["Mo"], "personen": 12, "aktiv": "on", "notiz": "",
        "k-TOTAL_FORMS": "4", "k-INITIAL_FORMS": "2", "k-MIN_NUM_FORMS": "0",
        "k-MAX_NUM_FORMS": "1000", "k-0-id": erika.pk, "k-0-name": "Erika Muster",
        "k-1-id": kim.pk, "k-1-name": "Kim Probe", "k-1-DELETE": "on",
    })  # fmt: skip
    assert [k.name for k in s.kontakte.all()] == ["Erika Muster"]
    liste = admin_client.get(reverse("wochenuebersicht:selbstabholer")).content.decode()
    assert "Frauenhaus" in liste and "Erika Muster" in liste
    # Gesprächsnotizen mit Datum und Verfasser
    admin_client.post(reverse("wochenuebersicht:selbstabholer_notiz", args=[s.pk]),
                      {"text": "Abholung künftig um 10 Uhr"})  # fmt: skip
    admin_client.post(reverse("wochenuebersicht:selbstabholer_notiz", args=[s.pk]), {"text": " "})
    n = s.notizen.get()
    assert n.text == "Abholung künftig um 10 Uhr" and n.verfasst_von
    assert "Abholung künftig um 10 Uhr" in admin_client.get(antwort.url).content.decode()
    admin_client.post(reverse("wochenuebersicht:selbstabholer_notiz_loeschen", args=[n.pk]))
    assert not s.notizen.exists()
    admin_client.post(reverse("wochenuebersicht:selbstabholer_loeschen", args=[s.pk]))
    assert not Selbstabholer.objects.exists()


def test_reihenfolge_pflegen(modul_an, admin_client, daten):
    zentrale, nord = daten
    admin_client.post(reverse("wochenuebersicht:reihenfolge"),
                      {f"r_{zentrale.pk}": "5", f"r_{nord.pk}": "x"})  # fmt: skip
    assert StellenReihenfolge.objects.get(ausgabestelle=zentrale).reihenfolge == 5
    assert not StellenReihenfolge.objects.filter(ausgabestelle=nord).exists()
    seite = admin_client.get(reverse("wochenuebersicht:reihenfolge")).content.decode()
    inhalt = seite[seite.index("<main") :]  # oben im Menü stehen die Stellen nach Namen
    assert inhalt.index("Zentrale") < inhalt.index("Nord")


def test_rechte_und_modulschalter(admin, benutzer_mit_rolle, anmelden, daten):
    c = anmelden(Client(), benutzer_mit_rolle("anton", rollen.AUSGABE))
    url = reverse("wochenuebersicht:uebersicht")
    assert c.get(url).status_code == 404  # Modul aus
    TafelEinstellungen.objects.update(module=["wochenuebersicht"])
    assert c.get(url).status_code == 403
    b = anmelden(Client(), benutzer_mit_rolle("berta", rollen.BUERO))
    assert b.get(url).status_code == 200
    assert "Soll und Ist je Tag" in b.get(reverse("core:start")).content.decode()


# --- Vorschau auf eine kommende Woche -----------------------------------------------------------


def test_vorschau_umzug_schliessung_und_schliesszeit(daten):
    """Kommende Woche: geplante Umzüge zählen ab ihrem Stichtag in der neuen Gruppe, eine
    Ausgabestelle mit Enddatum fällt danach weg, eine Schließzeit steht als „geschlossen“ und
    zählt nicht in die Summe."""
    from apps.ausgabe.models import Schliesszeit
    from apps.kunden.models import GeplanterWechsel

    zentrale, nord = daten
    montag = auswertung.montag(STICHTAG) + dt.timedelta(weeks=1)  # Mo 26.10.2026
    mittwoch, donnerstag = montag + dt.timedelta(days=2), montag + dt.timedelta(days=3)
    # ohne Besonderheiten: dieselben Zahlen wie heute, mit Datum je Tag
    d = auswertung.uebersicht(STICHTAG, vorschau=montag)
    tage = {t.kurz: t for t in d["tage"]}
    assert d["vorschau"] == montag and d["woche"] is None and d["hinweise"] == []
    assert tage["Mi"].datum == mittwoch and tage["Mi"].summe.haushalte == 4
    assert tage["Mo"].zeilen[0].name == "Nord" and tage["Mo"].summe.personen == 2
    # Haushalt 5 (Nord, Mo/Do) zieht ab Donnerstag in die Zentrale (Mi 12:30) um
    ziel = Kundengruppe.objects.get(name="Zentrale Mi 12:30")
    h5 = Haushalt.objects.get(kundennummer="5")
    GeplanterWechsel.objects.create(haushalt=h5, ziel_gruppe=ziel, ab=donnerstag)
    d = auswertung.uebersicht(STICHTAG, vorschau=montag)
    tage = {t.kurz: t for t in d["tage"]}
    assert tage["Mo"].summe.haushalte == 1  # Montag noch in Nord
    assert tage["Mi"].summe.haushalte == 4  # Mittwoch noch nicht in der Zentrale
    assert tage["Do"].summe.haushalte == 0  # Donnerstag nicht mehr in Nord
    assert "1 geplanter Umzug" in d["hinweise"][0]
    # eine Woche später ist er mittwochs in der Zentrale
    spaeter = auswertung.uebersicht(STICHTAG, vorschau=montag + dt.timedelta(weeks=1))
    mi = next(t for t in spaeter["tage"] if t.kurz == "Mi")
    assert mi.zeilen[0].haushalte == 4 and mi.summe.haushalte == 5
    # schon ausgeführte Umzüge zählen nicht doppelt
    GeplanterWechsel.objects.update(erledigt_am=STICHTAG)
    assert auswertung.uebersicht(STICHTAG, vorschau=montag)["hinweise"] == []
    # Nord schließt am Montag der Woche: Montag noch da, Donnerstag weg; Hinweis auf Haushalt 5
    nord.schliesst_am = montag
    nord.save()
    d = auswertung.uebersicht(STICHTAG, vorschau=montag)
    tage = {t.kurz: t for t in d["tage"]}
    assert [z.name for z in tage["Mo"].zeilen] == ["Nord"] and tage["Do"].zeilen == []
    assert any("„Nord“ schließt bis dahin: 1 Haushalt" in h for h in d["hinweise"])
    # Schließzeit der Zentrale am Mittwoch: Zeile bleibt als „geschlossen“, Summe ohne sie
    Schliesszeit.objects.create(ausgabestelle=zentrale, bezeichnung="Betriebsferien",
                                von=mittwoch, bis=mittwoch)  # fmt: skip
    d = auswertung.uebersicht(STICHTAG, vorschau=montag)
    mi = next(t for t in d["tage"] if t.kurz == "Mi")
    assert mi.zeilen[0].geschlossen == "Betriebsferien" and mi.zeilen[0].haushalte == 3
    assert mi.summe.haushalte == 1  # nur die Sondergruppe
    # die Übersicht von heute rechnet davon nichts ein
    heute = auswertung.uebersicht(STICHTAG)
    mi = next(t for t in heute["tage"] if t.kurz == "Mi")
    assert mi.zeilen[0].geschlossen == "" and mi.datum is None and heute["hinweise"] == []
    # Ausweis läuft vor der Woche ab: Hinweis, aber mitgezählt
    Haushalt.objects.filter(kundennummer="1").update(
        ausweis_gueltig_bis=montag - dt.timedelta(days=2)
    )
    d = auswertung.uebersicht(STICHTAG, vorschau=montag)
    assert any("läuft der Ausweis vor dieser Woche ab" in h for h in d["hinweise"])


def test_vorschau_kind_wird_erwachsen(daten):
    """Gerechnet wird auf den Tag: Ein Kind, das in der Woche die Altersgrenze erreicht, zählt
    ab dem Geburtstag als erwachsen."""
    from apps.kunden.models import KundenEinstellungen

    grenze = KundenEinstellungen.laden().kind_bis_alter
    montag = auswertung.montag(STICHTAG) + dt.timedelta(weeks=1)
    mittwoch = montag + dt.timedelta(days=2)
    kind = Person.objects.filter(haushalt__kundennummer="3", vorname="Kim").get()
    kind.geburtsdatum = mittwoch.replace(year=mittwoch.year - grenze)
    kind.save()
    heute = next(t for t in auswertung.uebersicht(STICHTAG)["tage"] if t.kurz == "Mi")
    dann = next(
        t for t in auswertung.uebersicht(STICHTAG, vorschau=montag)["tage"] if t.kurz == "Mi"
    )
    assert heute.zeilen[0].kinder == dann.zeilen[0].kinder + 1
    assert heute.zeilen[0].personen == dann.zeilen[0].personen


def test_vorschau_seite_auswahl_und_pdf(modul_an, admin_client, daten, pdf_text):
    from django.utils import timezone

    from apps.ausgabe.models import Schliesszeit

    zentrale, _ = daten
    diese = auswertung.montag(timezone.localdate())
    naechste = diese + dt.timedelta(weeks=1)
    ziel = reverse("wochenuebersicht:uebersicht")
    seite = admin_client.get(ziel).content.decode()
    # Auswahl: vier kommende Wochen als Vorschau, die laufende ist vorgewählt
    assert seite.count("– Vorschau</option>") == 4 and "Vorschau auf KW" not in seite
    assert f'<option value="{diese:%G-W%V}" selected>' in seite and "– diese Woche" in seite
    kw = naechste.strftime("%G-W%V")
    Schliesszeit.objects.create(ausgabestelle=zentrale, von=naechste,
                                bis=naechste + dt.timedelta(days=6))  # fmt: skip
    seite = admin_client.get(ziel, {"kw": kw, "abholungen": "1"}).content.decode()
    assert f"Vorschau auf KW {naechste:%V}" in seite and "Abgeholt" not in seite
    assert "wochen-geschlossen" in seite and ">geschlossen<" in seite
    assert f'<option value="{kw}" selected>' in seite and f"{naechste:%d.%m.}" in seite
    assert f"kw={kw}" in seite  # die PDF-Knöpfe nehmen die Woche mit
    hoch = pdf_text(admin_client.get(reverse("wochenuebersicht:pdf", args=["hoch"]), {"kw": kw}))
    assert f"Vorschau KW {naechste:%V}" in hoch and "Zentrale – geschlossen" in hoch
    antwort = admin_client.get(reverse("wochenuebersicht:pdf", args=["quer"]), {"kw": kw})
    assert f"vorschau-kw{naechste:%V}" in antwort["Content-Disposition"]
    assert f"Vorschau KW {naechste:%V}" in pdf_text(antwort)
    # eine vergangene Woche ohne Haken bleibt die Übersicht von heute
    alt = (diese - dt.timedelta(weeks=2)).strftime("%G-W%V")
    assert "Vorschau auf KW" not in admin_client.get(ziel, {"kw": alt}).content.decode()


def test_vorschau_neues_maximum_ab_datum(daten):
    """Ein geplantes neues Maximum einer Kundengruppe zählt in der Vorschau ab seinem Tag als
    Soll – vorher und in der laufenden Woche gilt das bisherige (ADR 0174)."""
    montag = auswertung.montag(STICHTAG) + dt.timedelta(weeks=1)  # Mo 26.10.2026
    z1 = Kundengruppe.objects.get(name="Zentrale Mi 12:30")  # Maximum 10, daneben eine mit 8
    z1.maximum_neu, z1.maximum_ab = 25, montag + dt.timedelta(days=2)  # ab dem Mittwoch
    z1.save()

    def soll_mi(**mehr):
        tage = {t.kurz: t for t in auswertung.uebersicht(STICHTAG, **mehr)["tage"]}
        return tage["Mi"].zeilen[0].soll

    assert soll_mi() == 18  # laufende Woche: noch das alte
    assert soll_mi(vorschau=montag) == 33  # 25 + 8
    z1.maximum_ab = montag + dt.timedelta(days=3)  # erst ab Donnerstag: am Mittwoch noch alt
    z1.save()
    assert soll_mi(vorschau=montag) == 18
    assert soll_mi(vorschau=montag + dt.timedelta(weeks=1)) == 33


@pytest.mark.django_db
def test_querformat_fuellt_das_blatt():
    """Wenige Zeilen: große Schrift und hohe Zeilen; viele Zeilen: nie kleiner als bisher.
    Eine übliche Woche (elf Ausgabestellen, sieben Selbstabholer) bleibt auf einer Seite."""
    from types import SimpleNamespace as N

    from pypdf import PdfReader

    from apps.wochenuebersicht import pdf

    gross, hoch, _ = pdf._masse(5, 0)
    assert gross == pdf.SCHRIFT_MAX and hoch > gross * 1.75
    mittel, _, _ = pdf._masse(19, 0)
    assert pdf.SCHRIFT_MIN < mittel < pdf.SCHRIFT_MAX
    klein, hoehe, _ = pdf._masse(60, 2)
    assert klein == pdf.SCHRIFT_MIN and hoehe >= klein * 1.75

    def woche(stellen, selbst):
        tage = []
        for i, name in enumerate(["Montag", "Dienstag", "Mittwoch", "Donnerstag", "Freitag"]):
            zeilen = [N(name=f"Ausgabe Beispiel {k}", soll=240, haushalte=236, erwachsene=331,
                        kinder=126, personen=457, geschlossen="")
                      for k in range(stellen)]  # fmt: skip
            sa = [N(name=f"Kooperation Beispiel {k}", personen=70) for k in range(selbst)]
            summe = N(name="Summe", soll=362, haushalte=351, erwachsene=484, kinder=172,
                      personen=1756 + i)  # fmt: skip
            tage.append(N(name=name, zeilen=zeilen, selbstabholer=sa, summe=summe,
                          selbst_personen=70 * selbst))  # fmt: skip
        return {"tage": tage, "woche": None, "stichtag": dt.date(2026, 11, 24),
                "gesamt": N(personen=2285), "selbst_gesamt": 740,
                "alle_personen": 3025}  # fmt: skip

    assert len(PdfReader(io.BytesIO(pdf.querformat(woche(11, 7)))).pages) == 1
    assert len(PdfReader(io.BytesIO(pdf.querformat(woche(3, 0)))).pages) == 1
    assert len(PdfReader(io.BytesIO(pdf.querformat(woche(40, 10)))).pages) == 2
