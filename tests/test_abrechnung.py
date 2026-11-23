"""Modul Abrechnung je Ausgabestelle (ADR 0060). Alle Daten sind erfunden."""

import datetime as dt
import io
import zipfile
from decimal import Decimal as D

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.abrechnung import ablauf
from apps.abrechnung.models import AbrechnungEinstellungen, Monatsabrechnung, Posten
from apps.ausgabe.models import Buchung
from apps.core import privatdateien
from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle

pytestmark = pytest.mark.django_db
MONAT = dt.date(2026, 9, 1)
FOTO = b"\xff\xd8\xff\xe0 erfundenes Foto"


@pytest.fixture(autouse=True)
def modul_an():
    t = TafelEinstellungen.laden()
    t.module = ["abrechnung"]
    t.save()


@pytest.fixture
def stellen():
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    for stelle, bar in ((mitte, "2.00"), (nord, "9.00")):
        Buchung.objects.create(art=Buchung.Art.ABHOLUNG, soll=D("2"), haben=D(bar) - D(bar) + D(2),
                               bar=D(bar), datum=MONAT + dt.timedelta(days=3),
                               ausgabestelle=stelle)  # fmt: skip
    Buchung.objects.create(art=Buchung.Art.EINZAHLUNG, haben=D("5"), bar=D("5"),
                           datum=MONAT + dt.timedelta(days=4), ausgabestelle=mitte)  # fmt: skip
    Buchung.objects.create(
        art=Buchung.Art.EINZAHLUNG,
        haben=D("7"),
        bar=D("7"),
        datum=dt.date(2026, 10, 1),
        ausgabestelle=mitte,
    )  # anderer Monat
    return mitte, nord


@pytest.fixture
def mitte_client(admin, stellen, benutzer_mit_rolle, anmelden):
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([stellen[0]])
    return anmelden(Client(), b)


@pytest.fixture
def nord_client(admin, stellen, benutzer_mit_rolle, anmelden):
    b = benutzer_mit_rolle("nora", rollen.AUSGABE)
    b.ausgabestellen.set([stellen[1]])
    return anmelden(Client(), b)


def seite(stelle, monat=MONAT):
    return reverse("abrechnung:monat", args=[stelle.pk, f"{monat:%Y-%m}"])


def posten(client, stelle, **mehr):
    daten = {"datum": "2026-09-10", "betrag": "12,50", "art": "Reinigung",
             "empfaenger": "Drogerie", **mehr}  # fmt: skip
    return client.post(seite(stelle), daten)


def test_rechte_und_vorgaben():
    from apps.konten.models import Rolle

    assert "abrechnung.fuehren" in Rolle.objects.get(gruppe__name=rollen.AUSGABE).rechte
    assert "abrechnung.pruefen" in Rolle.objects.get(gruppe__name=rollen.BUERO).rechte
    assert "abrechnung.pruefen" not in Rolle.objects.get(gruppe__name=rollen.AUSGABE).rechte


def test_monate():
    assert ablauf.monatsende(dt.date(2028, 2, 1)) == dt.date(2028, 2, 29)
    assert ablauf.verschieben(dt.date(2026, 1, 1), -1) == dt.date(2025, 12, 1)
    assert ablauf.verschieben(dt.date(2026, 12, 1), 1) == dt.date(2027, 1, 1)
    assert ablauf.monat_lesen("quatsch", dt.date(2026, 5, 17)) == dt.date(2026, 5, 1)
    assert ablauf.monatsname(MONAT) == "September 2026"


def test_ausgabestelle_fuehrt_eigene_abrechnung(mitte_client, stellen):
    mitte, nord = stellen
    # Mit nur einer Ausgabestelle führt die Übersicht direkt zum Monat
    antwort = mitte_client.get(reverse("abrechnung:uebersicht"), {"monat": "2026-09"})
    assert antwort.url == seite(mitte)
    assert mitte_client.get(seite(nord)).status_code == 403
    inhalt = mitte_client.get(seite(mitte)).content.decode()
    assert "7,00 €" in inhalt or "7.00 €" in inhalt  # 2 € Beitrag bar + 5 € Einzahlung
    foto = SimpleUploadedFile("q.jpg", FOTO, content_type="image/jpeg")
    antwort = posten(mitte_client, mitte, foto=foto)
    assert antwort.status_code == 302
    p = Posten.objects.get()
    assert (
        p.betrag == D("12.50") and p.eingetragen_von == "anton" and p.quittung_typ == "image/jpeg"
    )
    assert privatdateien.lesen(Posten.ORDNER, p.quittung) == FOTO
    assert privatdateien.pfad(Posten.ORDNER, p.quittung).read_bytes() != FOTO  # verschlüsselt
    q = mitte_client.get(reverse("abrechnung:quittung", args=[p.pk]))
    assert q.content == FOTO and q["Content-Type"] == "image/jpeg"
    # ohne Quittung, als PDF-Datei, falsches Format, Datum nach Monatsende
    posten(mitte_client, mitte, betrag="3", art="Müll")
    pdf = SimpleUploadedFile("q.pdf", b"%PDF-1.4 erfunden", content_type="application/pdf")
    posten(mitte_client, mitte, datei=pdf, betrag="1")
    txt = SimpleUploadedFile("q.txt", b"x", content_type="text/plain")
    antwort = posten(mitte_client, mitte, datei=txt)
    assert "Foto (JPG, PNG, WebP) oder ein PDF" in antwort.content.decode()
    antwort = posten(mitte_client, mitte, datum="2026-10-01")
    assert "nach dem Ende des Abrechnungszeitraums" in antwort.content.decode()
    abr = Monatsabrechnung.objects.get(stelle=mitte, monat=MONAT)
    z = ablauf.zahlen(abr)
    assert z["einnahmen_summe"] == D("7.00") and z["ausgaben_summe"] == D("16.50")
    assert z["saldo"] == D("-9.50")
    assert "fehlt" in mitte_client.get(seite(mitte)).content.decode()
    # Löschen geht nur bei offener Abrechnung
    letzter = Posten.objects.get(betrag=D("1"))
    mitte_client.post(reverse("abrechnung:posten_loeschen", args=[letzter.pk]))
    assert not Posten.objects.filter(pk=letzter.pk).exists()
    assert not privatdateien.pfad(Posten.ORDNER, letzter.quittung).exists()


def test_einreichen_pruefen_zurueckgeben(mitte_client, stellen, admin_client):
    mitte, _ = stellen
    posten(mitte_client, mitte)
    abr = Monatsabrechnung.objects.get(stelle=mitte)
    # Prüfen darf die Ausgabestelle nicht
    assert mitte_client.post(reverse("abrechnung:aktion", args=[abr.pk, "bestaetigen"])
                             ).status_code == 403  # fmt: skip
    mitte_client.post(reverse("abrechnung:aktion", args=[abr.pk, "einreichen"]),
                      {"anmerkung": "Alles drin"})  # fmt: skip
    abr.refresh_from_db()
    assert abr.status == "eingereicht" and abr.einnahmen["bar_gesamt"] == "7.00"
    assert abr.anmerkung == "Alles drin" and abr.eingereicht_von == "anton"
    # Spätere Buchungen ändern die eingereichte Abrechnung nicht
    Buchung.objects.create(art=Buchung.Art.EINZAHLUNG, haben=D("50"), bar=D("50"),
                           datum=MONAT, ausgabestelle=mitte)  # fmt: skip
    assert ablauf.zahlen(abr)["einnahmen_summe"] == D("7.00")
    # Keine Änderungen mehr
    posten(mitte_client, mitte, betrag="99")
    assert not Posten.objects.filter(betrag=D("99")).exists()
    p = Posten.objects.get()
    antwort = mitte_client.post(reverse("abrechnung:posten_loeschen", args=[p.pk]), follow=True)
    assert "bereits abgeschickt" in antwort.content.decode()
    # … auch nicht bearbeiten: Die Seite ist gesperrt, und ein direkter Aufruf ändert nichts
    bearbeiten = reverse("abrechnung:posten_bearbeiten", args=[p.pk])
    antwort = mitte_client.post(bearbeiten, {"datum": "20.09.2026", "betrag": "1,00",
                                             "art": "Müll"}, follow=True)  # fmt: skip
    assert "bereits abgeschickt" in antwort.content.decode()
    p.refresh_from_db()
    assert p.betrag == D("12.50")
    assert mitte_client.get(bearbeiten).status_code == 302
    with pytest.raises(ablauf.AbrechnungFehler, match="bereits abgeschickt"):
        ablauf.posten_aendern(p, {"datum": p.datum, "betrag": D("1")}, None, None)
    seite_ = mitte_client.get(seite(mitte)).content.decode()
    assert "bereits abgeschickt" in seite_ and bearbeiten not in seite_
    antwort = mitte_client.post(reverse("abrechnung:aktion", args=[abr.pk, "einreichen"]),
                                follow=True)  # fmt: skip
    assert "schon eingereicht" in antwort.content.decode()
    # Büro: Übersicht, zurückgeben ohne Grund geht nicht, mit Grund schon
    uebersicht = admin_client.get(reverse("abrechnung:uebersicht"), {"monat": "2026-09"})
    assert [z["stelle"].name for z in uebersicht.context["zeilen"]] == ["Mitte", "Nord"]
    url = reverse("abrechnung:aktion", args=[abr.pk, "zurueckgeben"])
    assert "Bitte kurz angeben" in admin_client.post(url, follow=True).content.decode()
    admin_client.post(url, {"grund": "Quittung Reinigung unleserlich"})
    abr.refresh_from_db()
    assert abr.offen and abr.einnahmen == {} and abr.rueckgabe == "Quittung Reinigung unleserlich"
    assert "unleserlich" in mitte_client.get(seite(mitte)).content.decode()
    assert ablauf.zahlen(abr)["einnahmen_summe"] == D("57.00")  # wieder aktuell
    assert "schon offen" in admin_client.post(url, {"grund": "x"}, follow=True).content.decode()
    admin_client.post(reverse("abrechnung:aktion", args=[abr.pk, "bestaetigen"]))
    abr.refresh_from_db()
    assert abr.offen  # nur eingereichte lassen sich bestätigen
    mitte_client.post(reverse("abrechnung:aktion", args=[abr.pk, "einreichen"]))
    admin_client.post(reverse("abrechnung:aktion", args=[abr.pk, "bestaetigen"]))
    abr.refresh_from_db()
    assert abr.status == "bestaetigt" and abr.bestaetigt_von and abr.rueckgabe == ""
    assert admin_client.post(reverse("abrechnung:aktion", args=[abr.pk, "quatsch"])
                             ).status_code == 404  # fmt: skip


def test_ausgabestelle_nimmt_einreichen_zurueck(mitte_client, stellen, admin_client):
    """Versehentlich eingereicht: Die Ausgabestelle öffnet selbst wieder, bis das Büro bestätigt."""
    mitte, nord = stellen
    posten(mitte_client, mitte)
    abr = Monatsabrechnung.objects.get(stelle=mitte)
    zurueck = reverse("abrechnung:aktion", args=[abr.pk, "zuruecknehmen"])
    assert "schon offen" in mitte_client.post(zurueck, follow=True).content.decode()
    assert "Einreichen zurücknehmen" not in mitte_client.get(seite(mitte)).content.decode()
    mitte_client.post(reverse("abrechnung:aktion", args=[abr.pk, "einreichen"]))
    assert "Einreichen zurücknehmen" in mitte_client.get(seite(mitte)).content.decode()
    # Das Büro ohne Zuordnung zur Stelle führt sie nicht, eine fremde Stelle auch nicht
    fremd = Monatsabrechnung.objects.create(stelle=nord, monat=MONAT, status="eingereicht")
    fremd_url = reverse("abrechnung:aktion", args=[fremd.pk, "zuruecknehmen"])
    assert mitte_client.post(fremd_url).status_code == 403
    mitte_client.post(zurueck)
    abr.refresh_from_db()
    assert abr.offen and abr.einnahmen == {} and abr.eingereicht_am is None
    posten(mitte_client, mitte, betrag="3")  # wieder änderbar
    assert Posten.objects.filter(betrag=D("3")).exists()
    # Nach der Bestätigung nur noch über das Büro
    mitte_client.post(reverse("abrechnung:aktion", args=[abr.pk, "einreichen"]))
    admin_client.post(reverse("abrechnung:aktion", args=[abr.pk, "bestaetigen"]))
    antwort = mitte_client.post(zurueck, follow=True).content.decode()
    assert "schon bestätigt" in antwort and "Einreichen zurücknehmen</button>" not in antwort
    abr.refresh_from_db()
    assert abr.status == "bestaetigt"


def test_abrechnung_ueber_mehrere_monate(mitte_client, stellen, admin_client, pdf_text):
    mitte, _ = stellen
    posten(mitte_client, mitte)
    abr = Monatsabrechnung.objects.get(stelle=mitte)
    assert abr.monate == 1 and ablauf.zeitraum_name(abr) == "September 2026"
    assert ablauf.zeitraeume(abr)[1] == (2, "Oktober 2026")
    # Im Oktober hat die Stelle schon eine offene Abrechnung mit einer Ausgabe
    mitte_client.post(seite(mitte, dt.date(2026, 10, 1)),
                      {"datum": "2026-10-05", "betrag": "4", "art": "Müll"})  # fmt: skip
    assert Monatsabrechnung.objects.filter(stelle=mitte).count() == 2
    zeitraum = reverse("abrechnung:aktion", args=[abr.pk, "zeitraum"])
    for falsch in ("0", "7", "x"):
        assert "1 bis 6 Monate" in mitte_client.post(zeitraum, {"monate": falsch}, follow=True
                                                     ).content.decode()  # fmt: skip
    antwort = mitte_client.post(zeitraum, {"monate": "3"}, follow=True).content.decode()
    assert "Zeitraum: September – November 2026." in antwort
    abr = Monatsabrechnung.objects.get(stelle=mitte)  # die vom Oktober ist darin aufgegangen
    assert abr.bis == dt.date(2026, 11, 1) and abr.monate == 3 and abr.posten.count() == 2
    assert ablauf.zahlen(abr)["einnahmen_summe"] == D("14.00")  # September 7 + Oktober 7
    # Jeder Monat des Zeitraums führt zu dieser Abrechnung; Ausgaben bis Ende November
    assert mitte_client.get(seite(mitte, dt.date(2026, 11, 1))).context["abr"] == abr
    assert Monatsabrechnung.objects.filter(stelle=mitte).count() == 1
    mitte_client.post(seite(mitte), {"datum": "2026-11-30", "betrag": "6", "art": "Müll"})
    antwort = mitte_client.post(seite(mitte), {"datum": "2026-12-01", "betrag": "8", "art": "Müll"})
    assert "nach dem Ende des Abrechnungszeitraums" in antwort.content.decode()
    assert abr.posten.count() == 3
    # Kürzen geht nicht vor die letzte Ausgabe
    antwort = mitte_client.post(zeitraum, {"monate": "1"}, follow=True).content.decode()
    assert "Es gibt Ausgaben nach September 2026" in antwort
    # Büro: in jedem Monat des Zeitraums sichtbar, mit Zeitraum; PDF nennt ihn
    for monat in ("2026-09", "2026-10", "2026-11"):
        zeile = admin_client.get(reverse("abrechnung:uebersicht"), {"monat": monat}
                                 ).context["zeilen"][0]  # fmt: skip
        assert zeile["abr"] == abr and zeile["zeitraum"] == "0926–1126"
    assert admin_client.get(reverse("abrechnung:uebersicht"), {"monat": "2026-12"}
                            ).context["zeilen"][0]["abr"].pk is None  # fmt: skip
    assert "September – November 2026" in pdf_text(
        mitte_client.get(reverse("abrechnung:pdf", args=[abr.pk])))  # fmt: skip
    assert mitte_client.get(seite(mitte)).context["vor"] == "2026-12"
    # Eingereicht: Zeitraum fest; ein eingereichter Monat lässt sich nicht dazunehmen
    mitte_client.post(reverse("abrechnung:aktion", args=[abr.pk, "einreichen"]))
    assert "Änderungen erst nach" in mitte_client.post(zeitraum, {"monate": "2"}, follow=True
                                                       ).content.decode()  # fmt: skip
    august = Monatsabrechnung.objects.create(stelle=mitte, monat=dt.date(2026, 8, 1))
    antwort = mitte_client.post(reverse("abrechnung:aktion", args=[august.pk, "zeitraum"]),
                                {"monate": "2"}, follow=True).content.decode()  # fmt: skip
    assert "schon eine eingereichte Abrechnung" in antwort
    august.refresh_from_db()
    assert august.bis is None
    # Über den Jahreswechsel; mehr als sechs Monate auch durch Zusammenlegen nicht
    winter = Monatsabrechnung.objects.create(stelle=mitte, monat=dt.date(2027, 1, 1),
                                             bis=dt.date(2027, 6, 1))  # fmt: skip
    dezember = Monatsabrechnung.objects.create(stelle=mitte, monat=dt.date(2026, 12, 1))
    ablauf.zeitraum_aendern(dezember, 1)
    with pytest.raises(ablauf.AbrechnungFehler, match="1 bis 6 Monate"):
        ablauf.zeitraum_aendern(dezember, 2)
    assert Monatsabrechnung.objects.filter(pk=winter.pk).exists()  # nichts verloren
    winter.bis = dt.date(2027, 2, 1)
    winter.save()
    ablauf.zeitraum_aendern(dezember, 2)
    dezember.refresh_from_db()
    assert ablauf.zeitraum_name(dezember) == "Dezember 2026 – Februar 2027"
    # Aufbewahrung zählt ab dem Jahr des letzten Monats
    AbrechnungEinstellungen.objects.update_or_create(pk=1, defaults={"aufbewahrung_jahre": 1})
    ablauf.fristen_anwenden(dt.date(2028, 3, 1))
    assert list(Monatsabrechnung.objects.values_list("pk", flat=True)) == [dezember.pk]


def test_pdf_und_zip(mitte_client, stellen, admin_client, pdf_text):
    mitte, nord = stellen
    posten(mitte_client, mitte, foto=SimpleUploadedFile("q.jpg", FOTO, content_type="image/jpeg"))
    posten(mitte_client, mitte, art="Miete und Gebühren", betrag="100")
    abr = Monatsabrechnung.objects.get(stelle=mitte)
    text = pdf_text(mitte_client.get(reverse("abrechnung:pdf", args=[abr.pk])))
    assert "Mitte" in text and "September 2026" in text and "Drogerie" in text
    assert "Saldo" in text and "fehlt" in text
    # ZIP: alle Ausgabestellen nur fürs Büro, die eigene auch für die Ausgabestelle
    zip_url = reverse("abrechnung:quittungen", args=["2026-09"])
    assert mitte_client.get(zip_url).status_code == 403
    assert mitte_client.get(zip_url, {"stelle": nord.pk}).status_code == 403
    eigen = mitte_client.get(zip_url, {"stelle": mitte.pk})
    assert eigen["Content-Disposition"] == 'attachment; filename="quittungen-Mitte-0926.zip"'
    assert len(zipfile.ZipFile(io.BytesIO(eigen.content)).namelist()) == 1
    monat_seite = mitte_client.get(reverse("abrechnung:monat", args=[mitte.pk, "2026-09"]))
    assert "⬇ Die Quittung (ZIP)" in monat_seite.content.decode()
    p = Posten.objects.exclude(quittung="").get()
    einzeln = mitte_client.get(reverse("abrechnung:quittung", args=[p.pk]), {"herunterladen": "1"})
    assert einzeln["Content-Disposition"].startswith("attachment;") and einzeln.content == FOTO
    antwort = admin_client.get(zip_url)
    assert antwort["Content-Type"] == "application/zip"
    namen = zipfile.ZipFile(io.BytesIO(antwort.content)).namelist()
    assert len(namen) == 1 and namen[0].startswith("0926_Mitte/2026-09-10_Reinigung_12.50_")
    assert namen[0].endswith(".jpg")
    leer = admin_client.get(zip_url, {"stelle": nord.pk})
    assert leer.status_code == 302 and "monat=2026-09" in leer.url
    inhalt = admin_client.get(reverse("abrechnung:uebersicht"), {"monat": "2026-09"}).content
    assert "Alle Quittungen (ZIP)" in inhalt.decode()


def test_mehrere_stellen_ohne_zuordnung(admin, stellen, benutzer_mit_rolle, anmelden):
    c = anmelden(Client(), benutzer_mit_rolle("berta", rollen.AUSGABE))
    seite_ = c.get(reverse("abrechnung:uebersicht")).content.decode()
    assert "Mitte" in seite_ and "Nord" in seite_  # ohne Zuordnung: alle zur Auswahl
    keine = anmelden(Client(), benutzer_mit_rolle("kim", rollen.KIOSK))
    assert keine.get(reverse("abrechnung:uebersicht")).status_code == 403


def test_stellenkonto_ohne_zuordnung_sieht_hinweis(admin, benutzer_mit_rolle, anmelden):
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([Ausgabestelle.objects.create(name="Weg")])
    Ausgabestelle.objects.all().delete()
    c = anmelden(Client(), b)
    assert (
        "keiner Ausgabestelle zugeordnet"
        in c.get(reverse("abrechnung:uebersicht")).content.decode()
    )


def test_einstellungen_und_fristen(admin_client, stellen):
    url = reverse("abrechnung:einstellungen")
    assert "Reinigung" in admin_client.get(url).content.decode()
    admin_client.post(url, {"arten_text": "Müll\n\nMüll\nStrom", "aufbewahrung_jahre": "2"})
    e = AbrechnungEinstellungen.laden()
    assert e.arten == ["Müll", "Strom"] and e.aufbewahrung_jahre == 2
    antwort = admin_client.post(url, {"arten_text": "  ", "aufbewahrung_jahre": "2"})
    assert "hat-fehler" in antwort.content.decode()
    assert AbrechnungEinstellungen.laden().arten == ["Müll", "Strom"]
    mitte, _ = stellen
    alt = Monatsabrechnung.objects.create(stelle=mitte, monat=dt.date(2023, 12, 1))
    name = privatdateien.speichern(Posten.ORDNER, SimpleUploadedFile(
        "q.jpg", FOTO, content_type="image/jpeg"))  # fmt: skip
    Posten.objects.create(abrechnung=alt, betrag=1, art="Müll", quittung=name)
    bleibt = Monatsabrechnung.objects.create(stelle=mitte, monat=dt.date(2024, 1, 1))
    assert ablauf.fristen_anwenden(dt.date(2026, 5, 1)) == 1  # 2023 + 2 volle Jahre vorbei
    assert not Monatsabrechnung.objects.filter(pk=alt.pk).exists()
    assert Monatsabrechnung.objects.filter(pk=bleibt.pk).exists()
    assert not privatdateien.pfad(Posten.ORDNER, name).exists()


def test_menue_und_modul_aus(admin_client, stellen):
    from apps.core.menue import menue

    antwort = admin_client.get(reverse("abrechnung:uebersicht"))
    eintraege = [e["titel"] for b in menue(antwort.wsgi_request) if b["titel"] == "Ausgabestelle"
                 for e in b["eintraege"]]  # fmt: skip
    assert eintraege.count("Abrechnung") == 1  # zwei Rechte, ein Eintrag
    t = TafelEinstellungen.laden()
    t.module = []
    t.save()
    assert admin_client.get(reverse("abrechnung:uebersicht")).status_code == 404


def test_monat_als_mmjj():
    """Die Tafel schreibt den Monat als MMJJ; in den Adressen bleibt 2026-11."""
    lesen = ablauf.monat_aus_text
    assert (
        lesen("1126")
        == lesen("11/26")
        == lesen("11.26")
        == lesen(" 2026-11 ")
        == dt.date(2026, 11, 1)
    )
    assert lesen("0127") == dt.date(2027, 1, 1)
    for unsinn in ("", "1326", "0026", "abc", "112", "11266", "1999-11", "2026-13"):
        assert lesen(unsinn) is None, unsinn
    assert ablauf.mmjj(dt.date(2026, 11, 1)) == "1126"
    # Vor- und Folgemonat über den Jahreswechsel
    januar = lesen("0127")
    assert ablauf.mmjj(ablauf.verschieben(januar, -1)) == "1226"
    assert ablauf.mmjj(ablauf.verschieben(lesen("1226"), 1)) == "0127"


def test_uebersicht_zeigt_und_liest_mmjj(admin_client, stellen):
    url = reverse("abrechnung:uebersicht")
    seite_ = admin_client.get(url, {"monat": "0127"}).content.decode()
    assert "Abrechnungen 0127" in seite_ and 'value="0127"' in seite_
    assert "?monat=2026-12" in seite_ and "?monat=2027-02" in seite_  # Vormonat, Folgemonat
    assert 'type="month"' not in seite_
    # Unlesbare Eingabe: Meldung, und es bleibt beim bisherigen Monat
    seite_ = admin_client.get(url, {"monat": "1326", "bisher": "2026-09"}).content.decode()
    assert "ist kein Monat" in seite_ and "Abrechnungen 0926" in seite_
    assert admin_client.get(url, {"monat": "<b>"}).status_code == 200


def test_ausgabe_bearbeiten_solange_nicht_abgeschickt(mitte_client, nord_client, stellen):
    mitte, _ = stellen
    posten(mitte_client, mitte, foto=SimpleUploadedFile("q.jpg", FOTO, content_type="image/jpeg"))
    p = Posten.objects.get()
    alt = p.quittung
    url = reverse("abrechnung:posten_bearbeiten", args=[p.pk])
    seite_ = mitte_client.get(seite(mitte)).content.decode()
    assert url in seite_ and "bearbeiten" in seite_
    maske = mitte_client.get(url).content.decode()
    assert 'value="12,50"' in maske and "Drogerie" in maske
    # Betrag und Art ändern, Quittung bleibt
    antwort = mitte_client.post(url, {"datum": "11.09.2026", "betrag": "14,00", "art": "Müll",
                                      "empfaenger": "Stadt"}, follow=True)  # fmt: skip
    assert "Ausgabe geändert" in antwort.content.decode()
    p.refresh_from_db()
    assert (p.betrag, p.art, p.empfaenger, p.quittung) == (D("14.00"), "Müll", "Stadt", alt)
    assert p.datum == dt.date(2026, 9, 11)
    # neue Quittung ersetzt die alte
    neu = SimpleUploadedFile("q.png", FOTO, content_type="image/png")
    mitte_client.post(url, {"datum": "11.09.2026", "betrag": "14,00", "art": "Müll",
                            "datei": neu})  # fmt: skip
    p.refresh_from_db()
    assert p.quittung != alt and p.quittung_typ == "image/png"
    assert not privatdateien.pfad(Posten.ORDNER, alt).exists()
    # Datum nach dem Zeitraum und fremde Ausgabestelle
    antwort = mitte_client.post(url, {"datum": "01.10.2026", "betrag": "14,00", "art": "Müll"})
    assert "nach dem Ende des Abrechnungszeitraums" in antwort.content.decode()
    assert nord_client.get(url).status_code == 403
    assert nord_client.post(url, {"datum": "11.09.2026", "betrag": "1", "art": "Müll"}
                            ).status_code == 403  # fmt: skip
    # Eine Art, die es in den Einstellungen nicht mehr gibt, bleibt wählbar
    Posten.objects.filter(pk=p.pk).update(art="Altes")
    assert '<option value="Altes" selected>' in mitte_client.get(url).content.decode()


def test_eingereichte_sind_auffindbar(mitte_client, admin_client, admin, stellen):
    """Das Büro findet eingereichte Abrechnungen, ohne den Monat zu kennen: Liste über alle
    Monate, Datum im Status, Zahl am Menüpunkt."""
    mitte, nord = stellen
    url = reverse("abrechnung:uebersicht")
    leer = admin_client.get(url, {"status": "eingereicht"}).content.decode()
    assert "wartet keine eingereichte Abrechnung" in leer
    assert "Entwurf" in admin_client.get(url, {"monat": "0926"}).content.decode()
    posten(mitte_client, mitte)
    abr = Monatsabrechnung.objects.get(stelle=mitte, monat=MONAT)
    mitte_client.post(reverse("abrechnung:aktion", args=[abr.pk, "einreichen"]))
    heute = f"{timezone.localdate():%d.%m.%Y}"
    liste = admin_client.get(url, {"status": "eingereicht"})
    inhalt = liste.content.decode()
    assert [z["abr"] for z in liste.context["zeilen"]] == [abr]
    assert f"eingereicht am {heute}" in inhalt and "Nord" not in inhalt.split("<tbody>")[1]
    assert reverse("abrechnung:monat", args=[mitte.pk, "2026-09"]) in inhalt and ">0926<" in inhalt
    # in der Monatsansicht eines anderen Monats: Knopf mit Zahl, im Menü ebenfalls
    anders = admin_client.get(url, {"monat": "0127"}).content.decode()
    assert "Nur eingereichte (1)" in anders
    eintrag = next(e for b in admin_client.get(url).context["menue"] for e in b["eintraege"]
                   if e["url"] == url)  # fmt: skip
    assert eintrag["zahl"] == 1
    # Die Ausgabestelle selbst sieht keine Zahl am Menüpunkt
    eigene = [e for b in mitte_client.get(seite(mitte)).context["menue"] for e in b["eintraege"]
              if e["url"] == url]  # fmt: skip
    assert len(eigene) == 1 and not eigene[0].get("zahl")
    # bestätigt: nicht mehr in der Liste
    ablauf.bestaetigen(abr, admin)
    assert not admin_client.get(url, {"status": "eingereicht"}).context["zeilen"]
    assert f"bestätigt am {heute}" in admin_client.get(url, {"monat": "0926"}).content.decode()
