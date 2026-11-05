import datetime as dt
import io
import json
import re
import zipfile

import pytest
from auditlog.models import LogEntry
from django.core import mail as django_mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.antraege import sprachen
from apps.antraege.forms import MAX_ANHAENGE, AntragForm
from apps.antraege.models import (
    ANHANG_ORDNER,
    Abfrage,
    Antrag,
    AntragAnhang,
    AntragAnmerkung,
    AntragEinstellungen,
    AntragPerson,
    AntragText,
    AntragVersuch,
    fristen_anwenden,
    in_papierkorb,
)
from apps.antraege.views_oeffentlich import besucher_ip
from apps.core import geheimnis, papierkorb, privatdateien
from apps.core.models import MailEinstellungen, PapierkorbEintrag, TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle

pytestmark = pytest.mark.django_db

FORMULAR = reverse("antrag:formular", args=["de"])


@pytest.fixture
def offen(admin):
    e = AntragEinstellungen.laden()
    e.aktiv = True
    e.save()
    return e


@pytest.fixture
def mailserver(db):
    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()
    return m


def daten(**mehr):
    return {
        "art": "neu", "vorname": "Erika", "nachname": "Beispiel", "geburtsdatum": "1980-02-03",
        "strasse": "Erfundene Gasse 1", "plz": "12345", "ort": "Musterstadt",
        "einwilligung": "on", "datenschutz_bestaetigt": "on", "einverstaendnis_bestaetigt": "on",
        **mehr,
    }  # fmt: skip


def pdf(name="bescheid.pdf", groesse=10):
    return SimpleUploadedFile(name, b"%PDF" + b"x" * groesse, content_type="application/pdf")


# --- Sprachen ------------------------------------------------------------------------------


def test_alle_sprachen_vollstaendig():
    grundlage = sprachen._datei("de")
    assert len(sprachen.SPRACHEN) == 29
    for s in sprachen.SPRACHEN:
        texte = json.loads((sprachen.ORDNER / f"{s.code}.json").read_text(encoding="utf-8"))
        assert set(texte) == set(grundlage), s.code
        for schluessel, text in texte.items():
            platzhalter = set(re.findall(r"\{(\w+)\}", text))
            assert platzhalter == set(re.findall(r"\{(\w+)\}", grundlage[schluessel])), (
                s.code,
                schluessel,
            )
            assert text.strip(), (s.code, schluessel)


def test_sprache_aus_browser():
    assert sprachen.aus_browser("ar-SY,ar;q=0.9,de;q=0.8") == "ar"
    assert sprachen.aus_browser("fa-AF") == "prs"
    assert sprachen.aus_browser("ku") == "kmr"
    assert sprachen.aus_browser("ja, xx") == "de"
    assert sprachen.aus_browser("") == "de"
    assert sprachen.sprache("unbekannt").code == "de"
    assert sprachen.texte("xx") == sprachen.texte("de")


# --- Öffentliches Formular -----------------------------------------------------------------


def test_start_leitet_auf_sprache(client, admin):
    antwort = client.get(reverse("antrag:start"), HTTP_ACCEPT_LANGUAGE="uk,de")
    assert antwort.url == reverse("antrag:formular", args=["uk"])
    assert client.get(reverse("antrag:start"), {"sprache": "tr"}).url.endswith("/tr/")
    assert client.get("/antrag/xx/").url == reverse("antrag:start")


def test_geschlossen(client, admin):
    seite = client.get(FORMULAR).content.decode()
    assert "keine Anträge über diese Seite" in seite


def test_formular_in_arabisch_von_rechts(client, offen):
    seite = client.get(reverse("antrag:formular", args=["ar"])).content.decode()
    assert 'lang="ar" dir="rtl"' in seite and sprachen.texte("ar")["absenden"] in seite
    assert 'lang="de" dir="ltr"' in client.get(FORMULAR).content.decode()


def test_antrag_absenden(client, offen, mailserver, benutzer_mit_rolle):
    b = benutzer_mit_rolle("berta", rollen.BUERO)
    b.email = "berta@example.org"
    b.save()
    offen.benachrichtigen.add(b)
    offen.angehoerige = offen.wochentage = offen.ausgabestelle = offen.anhaenge = Abfrage.OPTIONAL
    offen.save()
    Ausgabestelle.objects.create(name="Ausgabe Nord")
    antwort = client.post(
        reverse("antrag:formular", args=["en"]),
        daten(email="erika@example.org", p1_vorname="Max", p1_geburtsdatum="2015-05-05",
              wochentage=["Mo", "Do"], ausgabestelle="Ausgabe Nord",
              anhaenge=[pdf(), pdf("zwei.pdf")]),
        HTTP_X_FORWARDED_FOR="203.0.113.7, 172.18.0.4",
    )  # fmt: skip
    assert antwort.url == reverse("antrag:danke", args=["en"])
    a = Antrag.objects.get()
    assert (a.sprache, a.art, a.wochentage, a.ausgabestelle) == ("en", "neu", "Mo, Do",
                                                                  "Ausgabe Nord")  # fmt: skip
    assert a.personen.get().geburtsdatum == dt.date(2015, 5, 5)
    anhang = a.anhaenge.first()
    assert b"%PDF" not in privatdateien.pfad(ANHANG_ORDNER, anhang.datei).read_bytes()
    bestaetigung, hinweis = django_mail.outbox
    assert bestaetigung.to == ["erika@example.org"]
    assert "application has been received" in bestaetigung.body
    assert "number" not in bestaetigung.body  # Antragsnummer nie in der Mail
    assert hinweis.to == ["berta@example.org"] and "Erika" not in hinweis.body
    danke = client.get(antwort.url).content.decode()
    assert "erika@example.org" in danke and "number" not in danke  # Nummer auch nicht auf der Seite
    assert client.get(antwort.url).url == reverse("antrag:formular", args=["en"])  # nur einmal


def test_bestaetigung_deutsch_und_sprache_der_staatsangehoerigkeit(client, offen, mailserver):
    offen.staatsangehoerigkeit = Abfrage.OPTIONAL
    offen.save()
    client.post(reverse("antrag:formular", args=["en"]),
                daten(email="erika@example.org", staatsangehoerigkeit="Türkei"))  # fmt: skip
    m = django_mail.outbox[-1]
    tr, de = sprachen.texte("tr"), sprachen.texte("de")
    assert de["danke_eingang"] in m.body and tr["danke_eingang"] in m.body
    assert m.body.index(de["danke_eingang"]) < m.body.index(tr["danke_eingang"])
    assert "has been received" not in m.body  # Formularsprache nicht, wenn das Land passt
    gestaltet = m.alternatives[0][0]
    assert 'lang="de"' in gestaltet and 'lang="tr"' in gestaltet and "<hr>" in gestaltet
    assert " / " in m.subject

    client.post(reverse("antrag:formular", args=["ar"]),
                daten(email="erika@example.org", staatsangehoerigkeit="Deutschland"))  # fmt: skip
    m = django_mail.outbox[-1]
    assert de["danke_eingang"] in m.body and sprachen.texte("ar")["danke_eingang"] not in m.body
    client.post(reverse("antrag:formular", args=["ar"]), daten(email="erika@example.org"))
    gestaltet = django_mail.outbox[-1].alternatives[0][0]
    assert 'lang="ar" dir="rtl"' in gestaltet  # ohne Angabe: Sprache des Formulars


def test_antrag_ohne_mail_und_mit_mailfehler(client, offen, mailserver, monkeypatch):
    from apps.core import mail

    client.post(FORMULAR, daten())
    assert not django_mail.outbox  # keine Adresse, keine Benachrichtigten

    def kaputt(*args, **kwargs):
        raise mail.MailFehler("nicht erreichbar")

    monkeypatch.setattr(mail, "senden", kaputt)
    offen.benachrichtigen.add(offen.benachrichtigen.model.objects.get(username="chefin"))
    chefin = offen.benachrichtigen.get()
    chefin.email = "chefin@example.org"
    chefin.save()
    antwort = client.post(FORMULAR, daten(email="erika@example.org"), follow=True)
    assert "Ihr Antrag ist eingegangen" in antwort.content.decode()
    assert "Bestätigung haben wir" not in antwort.content.decode()


def test_verlaengerung_und_pflichtfelder(client, offen):
    offen.modus = AntragEinstellungen.Modus.VERLAENGERUNG
    offen.kundennummer = offen.telefon = Abfrage.PFLICHT
    offen.anrede = offen.email = Abfrage.AUS
    offen.save()
    seite = client.post(FORMULAR, daten()).content.decode()
    assert "Bitte prüfen Sie die markierten Angaben" in seite and "Bitte ausfüllen" in seite
    assert 'name="anrede"' not in seite
    client.post(FORMULAR, daten(kundennummer="1001", telefon="0000 000000"))
    a = Antrag.objects.get()
    assert (a.art, a.kundennummer) == ("verlaengerung", "1001")


def test_nur_neuanmeldung_ohne_kundennummer(client, offen):
    offen.modus = AntragEinstellungen.Modus.NEU
    offen.save()
    seite = client.get(FORMULAR).content.decode()
    assert 'name="kundennummer"' not in seite and 'name="art"' not in seite
    client.post(FORMULAR, daten())
    assert Antrag.objects.get().art == "neu"


def test_fehler_in_der_gewaehlten_sprache(client, offen):
    offen.anhaenge = offen.angehoerige = Abfrage.OPTIONAL
    offen.save()
    t = sprachen.texte("tr")
    url = reverse("antrag:formular", args=["tr"])
    seite = client.post(url, daten(einwilligung="", geburtsdatum="kein Datum",
                                   p2_geburtsdatum="2015-05-05")).content.decode()  # fmt: skip
    for schluessel in ("fehler_einwilligung", "fehler_datum", "fehler_pflicht"):
        assert t[schluessel] in seite, schluessel
    # Datei-Fehler je eigener Sitzung prüfen, damit behaltene Nachweise sich nicht aufsummieren
    from django.test import Client as _Client

    zu_viele = [pdf(f"{n}.pdf") for n in range(MAX_ANHAENGE + 1)]
    assert t["fehler_datei_anzahl"].format(anzahl=MAX_ANHAENGE) in _Client().post(
        url, daten(anhaenge=zu_viele)).content.decode()  # fmt: skip
    text = SimpleUploadedFile("a.txt", b"x", content_type="text/plain")
    assert t["fehler_datei_typ"] in _Client().post(url, daten(anhaenge=[text])).content.decode()
    gross = pdf(groesse=11 * 1024 * 1024)
    assert "MB" in _Client().post(url, daten(anhaenge=[gross])).content.decode()
    assert not Antrag.objects.exists()


def test_nachweise_bleiben_bei_formularfehler(client, offen):
    """Ein Nachweis, der schon hochgeladen war, geht bei einem Fehler an einem anderen Feld nicht
    verloren: Er wird zwischengelegt, wieder angezeigt und beim nächsten Absenden übernommen."""
    from apps.antraege.models import AntragEntwurfNachweis

    offen.anhaenge = Abfrage.OPTIONAL
    offen.save()
    unvollstaendig = daten(anhaenge=[pdf("bescheid.pdf")])
    del unvollstaendig["vorname"]  # ein Pflichtfeld fehlt
    seite = client.post(FORMULAR, unvollstaendig).content.decode()
    assert not Antrag.objects.exists()  # wegen des fehlenden Feldes nicht angelegt
    assert AntragEntwurfNachweis.objects.count() == 1  # der Nachweis bleibt erhalten
    assert "bescheid.pdf" in seite  # und wird wieder angezeigt
    assert "novalidate" not in seite  # Pflichtfelder prüft jetzt schon der Browser
    # Nur das fehlende Feld nachtragen, ohne die Datei erneut zu wählen
    client.post(FORMULAR, daten())
    antrag = Antrag.objects.get()
    assert antrag.anhaenge.count() == 1 and antrag.anhaenge.first().name == "bescheid.pdf"
    assert not AntragEntwurfNachweis.objects.exists()  # Entwürfe sind aufgebraucht


def test_nachweise_pflicht_prueft_die_ansicht(client, offen):
    """Sind Nachweise Pflicht, lässt sich ohne Datei nicht absenden – mit Datei schon (die Prüfung
    macht jetzt die Ansicht, nicht mehr das Formularfeld)."""
    offen.anhaenge = Abfrage.PFLICHT
    offen.save()
    assert client.post(FORMULAR, daten()).status_code == 200  # ohne Nachweis: Formular erneut
    assert not Antrag.objects.exists()
    client.post(FORMULAR, daten(anhaenge=[pdf("bescheid.pdf")]))
    assert Antrag.objects.get().anhaenge.count() == 1


def test_nachweis_einzeln_wegnehmen_und_aufraeumen(client, offen):
    from apps.antraege import nachweise
    from apps.antraege.models import ANHANG_ORDNER, AntragEntwurfNachweis
    from apps.core import privatdateien

    offen.anhaenge = Abfrage.OPTIONAL
    offen.save()
    unvollstaendig = daten(anhaenge=[pdf("a.pdf"), pdf("b.pdf")])
    del unvollstaendig["vorname"]
    client.post(FORMULAR, unvollstaendig)
    assert AntragEntwurfNachweis.objects.count() == 2
    erster = AntragEntwurfNachweis.objects.first()
    pfad = privatdateien.pfad(ANHANG_ORDNER, erster.datei)
    assert pfad.exists()
    client.post(reverse("antrag:nachweis_entfernen", args=["de", erster.pk]))
    assert AntragEntwurfNachweis.objects.count() == 1 and not pfad.exists()
    # Liegen gebliebene Entwürfe räumt die Frist nach einem Tag weg (samt Datei)
    rest = AntragEntwurfNachweis.objects.get()
    rest_pfad = privatdateien.pfad(ANHANG_ORDNER, rest.datei)
    AntragEntwurfNachweis.objects.update(erstellt_am=timezone.now() - dt.timedelta(days=2))
    assert nachweise.aufraeumen() == 1
    assert not AntragEntwurfNachweis.objects.exists() and not rest_pfad.exists()


def test_bot_und_zu_viele(client, offen):
    antwort = client.post(FORMULAR, daten(webseite="http://spam.example"), follow=True)
    assert "Vielen Dank" in antwort.content.decode() and not Antrag.objects.exists()
    for _ in range(5):
        client.post(FORMULAR, daten())
    assert Antrag.objects.count() == 5
    seite = client.post(FORMULAR, daten()).content.decode()
    assert "zu viele Anträge" in seite and Antrag.objects.count() == 5
    assert all(len(v.schluessel) == 64 for v in AntragVersuch.objects.all())
    assert str(AntragVersuch.objects.first()).startswith("Versuch")


def test_sperre_einstellbar(client, offen):
    offen.max_je_stunde = 2
    offen.save()
    for _ in range(2):
        client.post(FORMULAR, daten())
    assert Antrag.objects.count() == 2
    seite = client.post(FORMULAR, daten()).content.decode()
    assert "zu viele Anträge" in seite and Antrag.objects.count() == 2
    # 0 = aus: beliebig viele Anträge, keine Sperre
    offen.max_je_stunde = 0
    offen.save()
    for _ in range(4):
        client.post(FORMULAR, daten())
    assert Antrag.objects.count() == 6


def test_besucher_ip(rf):
    assert besucher_ip(rf.get("/", REMOTE_ADDR="10.0.0.1")) == "10.0.0.1"
    assert besucher_ip(rf.get("/", HTTP_X_FORWARDED_FOR="203.0.113.7, 10.0.0.1")) == "203.0.113.7"


def test_eigene_texte(client, offen):
    assert "<p>Hier können Sie sich" in client.get(FORMULAR).content.decode()
    AntragText.objects.create(sprache="de", einleitung="Willkommen bei der Testtafel.",
                              bestaetigung="Wir rufen an.")  # fmt: skip
    assert "Willkommen bei der Testtafel." in client.get(FORMULAR).content.decode()
    danke = client.post(FORMULAR, daten(), follow=True).content.decode()
    assert "Wir rufen an." in danke
    assert str(AntragText.objects.get()) == "Texte Deutsch"


def test_eigene_html_texte_und_mail(client, offen, mailserver):
    offen.eigenes_css = ".antrag-kopf { text-align: center }</style><script>"
    offen.save()
    AntragText.objects.create(
        sprache="de", ueberschrift="Willkommen", einleitung='<h2>Hallo</h2><script>x()</script>',
        bestaetigung="<p>Ihre Nummer: <b>{nummer}</b> bei {tafel}</p>",
        mail_betreff="Antrag {nummer}",
        mail_text="<p>Liebe(r) {vorname} {nachname},</p><p onclick='x'>Nr. {nummer}</p>",
    )  # fmt: skip
    seite = client.get(FORMULAR).content.decode()
    assert '<h1 class="antrag-titel">Willkommen</h1>' in seite and "<h2>Hallo</h2>" in seite
    assert "x()" not in seite and ".antrag-kopf { text-align: center }/style>" in seite
    assert 'class="reihe reihe-3"' in seite and "--akzent:" in seite
    antwort = client.post(FORMULAR, daten(email="erika@example.org", vorname="<Erika>"),
                          follow=True)  # fmt: skip
    a = Antrag.objects.get()
    assert "Ihre Nummer: <b></b> bei Tafel" in antwort.content.decode()  # Nummer nie sichtbar
    m = django_mail.outbox[0]
    assert m.subject == "Antrag "  # {nummer} bleibt in der Mail leer
    assert f"Nr. {a.nummer}" not in m.body
    assert m.body.startswith("Liebe(r) <Erika> Beispiel,") and "onclick" not in m.body
    gestaltet, typ = m.alternatives[0]
    assert typ == "text/html" and "&lt;Erika&gt; Beispiel" in gestaltet
    assert "onclick" not in gestaltet


def test_mitgelieferte_mail_ist_gestaltet(client, offen, mailserver, settings):
    from apps.core.models import TafelEinstellungen

    tafel = TafelEinstellungen.laden()
    tafel.name, tafel.ort, tafel.logo = "Testtafel", "Musterstadt", "oeffentlich/logo/l.png"
    tafel.save()
    client.post(FORMULAR, daten(email="erika@example.org"))
    m = django_mail.outbox[0]
    assert m.subject == "Ihr Antrag bei Testtafel"
    assert m.body.startswith("Guten Tag,") and m.body.endswith("Testtafel")
    gestaltet = m.alternatives[0][0]
    assert "http://testserver/" in gestaltet and "l.png" in gestaltet
    assert "Musterstadt" in gestaltet and "<p>Wir prüfen Ihren Antrag" in gestaltet
    assert "&lt;p&gt;" not in gestaltet


def test_staatsangehoerigkeit_als_auswahl(client, offen):
    offen.staatsangehoerigkeit = Abfrage.OPTIONAL
    offen.save()
    seite = client.get(reverse("antrag:formular", args=["ar"])).content.decode()
    assert '<option value="Syrien" data-land="SY">Syrien</option>' in seite
    assert '<option value="staatenlos">عديم الجنسية</option>' in seite and "staaten.js" in seite
    falsch = client.post(FORMULAR, daten(staatsangehoerigkeit="Atlantis")).content.decode()
    assert "Bitte prüfen Sie die markierten Angaben" in falsch
    client.post(FORMULAR, daten(staatsangehoerigkeit="Syrien"))
    assert Antrag.objects.get().staatsangehoerigkeit == "Syrien"


def test_staatsangehoerigkeit_je_person(client, offen):
    offen.angehoerige = Abfrage.OPTIONAL
    offen.save()
    assert "p1_staatsangehoerigkeit" not in client.get(FORMULAR).content.decode()  # nicht abgefragt
    offen.staatsangehoerigkeit = Abfrage.OPTIONAL
    offen.save()
    assert 'name="p1_staatsangehoerigkeit"' in client.get(FORMULAR).content.decode()
    client.post(FORMULAR, daten(staatsangehoerigkeit="Deutschland", p1_vorname="Ali",
                                p1_staatsangehoerigkeit="Türkei"))  # fmt: skip
    a = Antrag.objects.get()
    assert a.staatsangehoerigkeit == "Deutschland"
    assert a.personen.get().staatsangehoerigkeit == "Türkei"


def test_vorbelegter_nachname_blockiert_absenden_nicht(client, offen):
    """Regression: Nachname und Staatsangehörigkeit werden bei den weiteren Personen per JavaScript
    von der Hauptperson vorbelegt. Zeilen mit NUR diesen vorbelegten Werten (kein Vorname, kein
    Geburtsdatum) dürfen das Absenden nicht blockieren und legen keine Person an."""
    offen.angehoerige = offen.staatsangehoerigkeit = Abfrage.OPTIONAL
    offen.wochentage = offen.ausgabestelle = offen.anhaenge = Abfrage.OPTIONAL
    offen.save()
    felder = daten(
        staatsangehoerigkeit="Deutschland",
        p1_vorname="Max", p1_nachname="Beispiel", p1_staatsangehoerigkeit="Deutschland",
        p2_nachname="Beispiel", p2_staatsangehoerigkeit="Deutschland",   # nur vorbelegt
        p3_nachname="Beispiel", p3_staatsangehoerigkeit="Deutschland",   # nur vorbelegt
    )  # fmt: skip
    antwort = client.post(FORMULAR, felder)
    assert antwort.status_code == 302, antwort.content.decode()[:2000]
    a = Antrag.objects.get()
    assert [p.vorname for p in a.personen.all()] == ["Max"]  # nur die echte Person


def test_weitere_person_mit_geburtsdatum_braucht_vornamen(client, offen):
    """Trägt jemand bei einer weiteren Person ein Geburtsdatum ein, bleibt der Vorname Pflicht –
    das ist der eigentliche Zweck der Prüfung (ein vorbelegter Nachname allein zählt nicht)."""
    offen.angehoerige = Abfrage.OPTIONAL
    offen.wochentage = offen.ausgabestelle = offen.anhaenge = Abfrage.OPTIONAL
    offen.save()
    antwort = client.post(FORMULAR, daten(p2_geburtsdatum="2015-05-05"))
    assert antwort.status_code == 200 and not Antrag.objects.exists()


def test_form_personen_leer_ohne_angehoerige(offen):
    offen.angehoerige = Abfrage.AUS
    form = AntragForm(texte=sprachen.texte("de"), einstellungen=offen)
    assert form.personen_zeilen == []


# --- Bearbeitung ---------------------------------------------------------------------------


@pytest.fixture
def antrag(db):
    a = Antrag.objects.create(vorname="Erika", nachname="Beispiel", email="e@example.org",
                              kundennummer="1001", geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    AntragPerson.objects.create(antrag=a, vorname="Max", geburtsdatum=dt.date(2015, 5, 5),
                                staatsangehoerigkeit="Polen")  # fmt: skip
    AntragPerson.objects.create(antrag=a, vorname="Mia")
    return a


def test_antragsliste_spalten_waehlbar(admin_client, antrag):
    """Jede Person wählt in der Antragsliste selbst, welche Spalten sie sieht; # bleibt immer."""
    url = reverse("antraege:liste")
    seite = admin_client.get(url).content.decode()
    assert 'data-titel="Telefon"' in seite and 'data-titel="E-Mail"' in seite
    # nur Status behalten → die übrigen (außer #) verschwinden
    admin_client.post(reverse("antraege:spalten"), {"spalte": ["status"]})
    seite = admin_client.get(url).content.decode()
    assert 'data-titel="Telefon"' not in seite and 'data-titel="E-Mail"' not in seite
    assert 'data-titel="#"' in seite and 'data-titel="Status"' in seite


def test_antrag_blaettern(admin_client):
    """Auf der Antragsseite kann man zum vorigen/nächsten Antrag (nach Nummer) blättern."""
    a1 = Antrag.objects.create(vorname="Eins", nachname="A")
    a2 = Antrag.objects.create(vorname="Zwei", nachname="B")
    a3 = Antrag.objects.create(vorname="Drei", nachname="C")
    url = lambda a: reverse("antraege:antrag", args=[a.pk])  # noqa: E731
    mitte = admin_client.get(url(a2)).content.decode()
    assert url(a1) in mitte and url(a3) in mitte  # voriger und nächster verlinkt
    erster = admin_client.get(url(a1)).content.decode()
    assert url(a2) in erster and url(a3) not in erster and "‹ voriger" in erster
    letzter = admin_client.get(url(a3)).content.decode()
    assert url(a2) in letzter and url(a1) not in letzter and "nächster ›" in letzter


def test_liste_und_detail(admin_client, antrag):
    Antrag.objects.create(vorname="Zweite", nachname="Person")
    seite = admin_client.get(reverse("antraege:liste")).content.decode()
    assert antrag.nummer in seite and "(2 offen)" in seite
    assert str(antrag) == f"Antrag {antrag.nummer}" and str(antrag.personen.first()) == "Max"
    gefunden = admin_client.get(reverse("antraege:liste"), {"suche": antrag.nummer})
    assert "Zweite" not in gefunden.content.decode()
    leer = admin_client.get(reverse("antraege:liste"), {"ansicht": "x", "suche": "niemand"})
    assert "Keine Anträge" in leer.content.decode()
    detail = admin_client.get(reverse("antraege:antrag", args=[antrag.pk])).content.decode()
    assert "Platz 1 der offenen Anträge" in detail and "Max" in detail
    assert LogEntry.objects.get_for_object(antrag).filter(action=LogEntry.Action.ACCESS).exists()
    assert "Neue Anträge" not in detail
    start = admin_client.get(reverse("core:start")).content.decode()
    assert "2 neue Anträge" in start


def test_liste_verweist_auf_gemeinsamen_papierkorb(admin_client, antrag):
    """Die Antragsliste verweist auf den einen gemeinsamen Papierkorb (ADR 0073); einen eigenen
    Antrags-Papierkorb-Reiter gibt es nicht mehr."""
    seite = admin_client.get(reverse("antraege:liste")).content.decode()
    assert "gemeinsamen Papierkorb" in seite
    # „ansicht=papierkorb“ ist keine eigene Ansicht mehr, zeigt aber weiter die Liste
    assert admin_client.get(reverse("antraege:liste"), {"ansicht": "papierkorb"}).status_code == 200


def test_bearbeiten_und_loeschen(admin_client, antrag):
    admin_client.post(reverse("antraege:status", args=[antrag.pk]), {"status": "erledigt"})
    antrag.refresh_from_db()
    assert antrag.status == "erledigt" and antrag.abgeschlossen_am and antrag.bearbeitet_von
    admin_client.post(reverse("antraege:status", args=[antrag.pk]), {"status": "in_bearbeitung"})
    admin_client.post(reverse("antraege:status", args=[antrag.pk]), {"status": "gibtsnicht"})
    antrag.refresh_from_db()
    assert antrag.abgeschlossen_am is None
    admin_client.post(reverse("antraege:anmerkung", args=[antrag.pk]), {"text": "Angerufen"})
    admin_client.post(reverse("antraege:anmerkung", args=[antrag.pk]), {"text": " "})
    assert AntragAnmerkung.objects.get().text == "Angerufen"
    assert str(AntragAnmerkung.objects.get()).startswith("Anmerkung vom")
    # Löschen legt den Antrag in den gemeinsamen Papierkorb (ADR 0073), nicht mehr in einen eigenen
    admin_client.post(reverse("antraege:papierkorb", args=[antrag.pk]))
    assert not Antrag.objects.filter(pk=antrag.pk).exists()
    detail_url = reverse("antraege:antrag", args=[antrag.pk])
    assert detail_url not in admin_client.get(reverse("antraege:liste")).content.decode()
    eintrag = PapierkorbEintrag.objects.get(art="Antrag")
    assert antrag.nummer in eintrag.bezeichnung
    # Wiederherstellen holt den Antrag samt Personen mit denselben Nummern zurück
    admin_client.post(reverse("core:papierkorb_wiederherstellen", args=[eintrag.pk]))
    assert Antrag.objects.filter(pk=antrag.pk).exists()
    assert AntragPerson.objects.filter(antrag=antrag.pk).exists()
    assert not PapierkorbEintrag.objects.exists()


def test_nachweis_ansehen(admin_client, antrag):
    name = privatdateien.speichern(ANHANG_ORDNER, pdf(), typen={"application/pdf"})
    d = AntragAnhang.objects.create(antrag=antrag, name="b.pdf", datei=name,
                                    typ="application/pdf", groesse=14)  # fmt: skip
    url = reverse("antraege:anhang", args=[antrag.pk, d.pk])
    assert admin_client.get(url).content.startswith(b"%PDF") and str(d) == "b.pdf"
    privatdateien.pfad(ANHANG_ORDNER, name).unlink()
    assert admin_client.get(url).status_code == 404


def test_nachweis_nachtraeglich_hinzufuegen(admin_client, antrag):
    """Admin/Büro können nachträglich Nachweise hochladen (verschlüsselt abgelegt)."""
    url = reverse("antraege:nachweis_hinzufuegen", args=[antrag.pk])
    antwort = admin_client.post(url, {"dateien": [pdf("a.pdf"), pdf("b.pdf")]}, follow=True)
    assert antrag.anhaenge.count() == 2
    inhalt = antwort.content.decode()
    assert "2 Nachweise hinzugefügt" in inhalt and "a.pdf" in inhalt
    # verschlüsselt: die Rohdatei enthält das Klartext-PDF nicht
    d = antrag.anhaenge.first()
    assert b"%PDF" not in privatdateien.pfad(ANHANG_ORDNER, d.datei).read_bytes()
    # Falscher Typ wird abgewiesen, der Antrag bekommt nichts dazu
    txt = SimpleUploadedFile("x.txt", b"x", content_type="text/plain")
    admin_client.post(url, {"dateien": [txt]})
    assert antrag.anhaenge.count() == 2
    # Höchstens fünf je Antrag
    admin_client.post(url, {"dateien": [pdf("c.pdf"), pdf("d.pdf"), pdf("e.pdf"), pdf("f.pdf")]})
    assert antrag.anhaenge.count() == 5


def test_nachweis_entfernen_in_papierkorb(admin_client, antrag):
    """Einen Nachweis entfernen legt ihn in den Papierkorb (wiederherstellbar), löscht die Datei
    noch nicht."""
    name = privatdateien.speichern(ANHANG_ORDNER, pdf(), typen={"application/pdf"})
    d = AntragAnhang.objects.create(antrag=antrag, name="bescheid.pdf", datei=name,
                                    typ="application/pdf", groesse=14)  # fmt: skip
    # Der „entfernen"-Knopf steht auf der Antragsseite
    detail = admin_client.get(reverse("antraege:antrag", args=[antrag.pk])).content.decode()
    assert reverse("antraege:nachweis_entfernen", args=[antrag.pk, d.pk]) in detail
    antwort = admin_client.post(reverse("antraege:nachweis_entfernen", args=[antrag.pk, d.pk]),
                                follow=True)  # fmt: skip
    assert "in den Papierkorb gelegt" in antwort.content.decode()
    assert not AntragAnhang.objects.filter(pk=d.pk).exists()
    eintrag = PapierkorbEintrag.objects.get(art="Nachweis")
    assert eintrag.kundennummer == "1001" and eintrag.recht == "antraege.bearbeiten"
    assert privatdateien.pfad(ANHANG_ORDNER, name).exists()  # Datei bleibt bis zur Frist
    # Wiederherstellen bringt den Nachweis zurück
    papierkorb.wiederherstellen(eintrag)
    assert AntragAnhang.objects.filter(antrag=antrag, name="bescheid.pdf").exists()


def test_nachweis_knopf_nur_mit_recht(client, admin, benutzer_mit_rolle, anmelden, recht_nehmen,
                                      antrag):  # fmt: skip
    """Wer Anträge nur sehen, aber nicht bearbeiten darf, sieht keinen Hochladen-/Entfernen-Bereich
    und wird beim Versuch mit 403 gesperrt."""
    name = privatdateien.speichern(ANHANG_ORDNER, pdf(), typen={"application/pdf"})
    AntragAnhang.objects.create(antrag=antrag, name="b.pdf", datei=name, typ="application/pdf")
    recht_nehmen(rollen.BUERO, "antraege.bearbeiten")  # Büro behält antraege.sehen
    anmelden(client, benutzer_mit_rolle("nur_sehen", rollen.BUERO))
    detail = client.get(reverse("antraege:antrag", args=[antrag.pk])).content.decode()
    assert "Nachweis hinzufügen" not in detail and "entfernen</button>" not in detail
    hinzu = reverse("antraege:nachweis_hinzufuegen", args=[antrag.pk])
    assert client.post(hinzu).status_code == 403


def _png(groesse=(20, 20)):
    from PIL import Image

    puffer = io.BytesIO()
    Image.new("RGB", groesse, (200, 50, 50)).save(puffer, "PNG")
    return puffer.getvalue()


def _zip(dateien: dict, manifest: str) -> bytes:
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("nachweise.csv", manifest)
        for name, daten in dateien.items():
            z.writestr(name, daten)
    return puffer.getvalue()


def test_nachweis_import_stapel(antrag):
    """ZIP + nachweise.csv: Dateien werden über die Antragsnummer zugeordnet, Probelauf schreibt
    nichts, ein zweiter Lauf legt nichts doppelt an."""
    from apps.antraege import nachweis_import

    nummer = antrag.laufnummer
    manifest = (f"antragsnummer;datei;name\n{nummer};d/a.png;Ausweis\n"
                f"{nummer};d/b.pdf;Bescheid\n999999;d/c.pdf;Weg\n")  # fmt: skip
    daten = _zip({"d/a.png": _png(), "d/b.pdf": b"%PDF-1.4 x", "d/c.pdf": b"%PDF-1.4 x"}, manifest)
    # Probelauf: ordnet 2 zu, 1 Antrag fehlt – aber speichert nichts
    bericht = nachweis_import.pruefen(io.BytesIO(daten))
    assert bericht["zaehler"]["ok"] == 2 and bericht["zaehler"]["antrag_fehlt"] == 1
    assert antrag.anhaenge.count() == 0
    # Übernehmen hängt die zwei passenden an
    bericht = nachweis_import.uebernehmen(io.BytesIO(daten))
    assert bericht["zaehler"]["ok"] == 2
    assert set(antrag.anhaenge.values_list("name", flat=True)) == {"Ausweis", "Bescheid"}
    # Erneut → Dublette, nichts doppelt
    bericht = nachweis_import.uebernehmen(io.BytesIO(daten))
    assert bericht["zaehler"]["dublette"] == 2 and antrag.anhaenge.count() == 2
    # Das Bild liegt verschlüsselt (kein Klartext im Dateiinhalt)
    bild = antrag.anhaenge.get(name="Ausweis")
    assert b"PNG" not in privatdateien.pfad(ANHANG_ORDNER, bild.datei).read_bytes()


def _mrz_ukr():
    from mrz.generator.td3 import TD3CodeGenerator

    # Reisepass, ausgestellt von „D" (Deutschland), Staatsangehörigkeit UKR (Ukraine)
    return str(TD3CodeGenerator("P", "D", "Kovach", "Svitlana", "A1234567", "UKR",
                                "560818", "F", "300101", ""))  # fmt: skip


def test_ausweis_pruefung_mrz_logik(monkeypatch):
    from apps.antraege import ausweis_pruefung as ap

    monkeypatch.setattr(ap, "tesseract_vorhanden", lambda: True)
    # PassportEye findet hier nichts → Rückfall über das ganze Bild (_ocr + mrz-Parser)
    monkeypatch.setattr(ap, "_passporteye", lambda daten: None)
    monkeypatch.setattr(ap, "_ocr", lambda daten: _mrz_ukr())
    b = ap.pruefen(_png(), "Ukraine")
    assert b["erkannt"] and b["dokument"] == "Reisepass"
    assert b["staatsangehoerigkeit"] == "Ukraine" and b["ausstellland"] == "Deutschland"
    assert b["passt"] is True
    assert ap.pruefen(_png(), "Deutschland")["passt"] is False  # Abweichung erkannt
    # Kein Tesseract bzw. keine MRZ → ehrlich „nicht erkannt", kein Raten
    monkeypatch.setattr(ap, "_ocr", lambda daten: "kein ausweis hier")
    assert ap.pruefen(_png())["erkannt"] is False
    monkeypatch.setattr(ap, "tesseract_vorhanden", lambda: False)
    assert ap.pruefen(_png())["erkannt"] is False


def test_ausweis_pruefung_passporteye(monkeypatch):
    """Stufe 1 (PassportEye findet das Band selbst): das Ergebnis wird korrekt übernommen."""
    from apps.antraege import ausweis_pruefung as ap

    monkeypatch.setattr(ap, "tesseract_vorhanden", lambda: True)
    monkeypatch.setattr(ap, "_passporteye", lambda daten: {
        "dokument": "Reisepass", "country": "D", "nationality": "UKR",
        "name": "SVITLANA KOVACH", "gueltig": True})  # fmt: skip
    b = ap.pruefen(_png(), "Ukraine")
    assert b["erkannt"] and b["gueltig"] and b["passt"] is True
    assert b["ausstellland"] == "Deutschland" and b["staatsangehoerigkeit"] == "Ukraine"
    assert b["name"] == "SVITLANA KOVACH"
    # defektes Bild → ehrlicher Fehler, keine Ausnahme
    assert ap.pruefen(b"kein bild")["erkannt"] is False


def test_ausweis_pruefung_view_und_knopf(admin_client, antrag, monkeypatch):
    from apps.antraege import ausweis_pruefung as ap
    from apps.antraege.models import AntragEinstellungen

    e = AntragEinstellungen.laden()
    e.ausweis_pruefen = True
    e.save()
    monkeypatch.setattr(ap, "tesseract_vorhanden", lambda: True)
    monkeypatch.setattr(ap, "_passporteye", lambda daten: None)
    monkeypatch.setattr(ap, "_ocr", lambda daten: _mrz_ukr())
    name = privatdateien.speichern(
        ANHANG_ORDNER, SimpleUploadedFile("ausweis.png", _png(), content_type="image/png"),
        typen={"image/png"})  # fmt: skip
    d = AntragAnhang.objects.create(antrag=antrag, name="ausweis.png", datei=name, typ="image/png")
    url = reverse("antraege:nachweis_pruefen", args=[antrag.pk, d.pk])
    seite = admin_client.post(url).content.decode()
    assert "Ukraine" in seite and "Reisepass" in seite
    # Knopf steht auf der Antragsseite am Foto
    detail = admin_client.get(reverse("antraege:antrag", args=[antrag.pk])).content.decode()
    assert "Ausweis prüfen" in detail
    # Abgeschaltet: kein Knopf, und die Ansicht ist nicht erreichbar
    e.ausweis_pruefen = False
    e.save()
    detail = admin_client.get(reverse("antraege:antrag", args=[antrag.pk])).content.decode()
    assert "Ausweis prüfen" not in detail
    assert admin_client.post(url).status_code == 404


def test_ausweis_abweichung_und_uebernehmen(admin_client, antrag, monkeypatch):
    """Weicht die erkannte Staatsangehörigkeit ab, kommt ein deutlicher Hinweis und eine Auswahl,
    mit der sich die Staatsangehörigkeit im Antrag überschreiben lässt."""
    from apps.antraege import ausweis_pruefung as ap
    from apps.antraege.models import Antrag, AntragEinstellungen

    e = AntragEinstellungen.laden()
    e.ausweis_pruefen = True
    e.save()
    antrag.staatsangehoerigkeit = "Deutschland"  # Ausweis zeigt Ukraine → Abweichung
    antrag.save()
    monkeypatch.setattr(ap, "tesseract_vorhanden", lambda: True)
    monkeypatch.setattr(ap, "_passporteye", lambda daten: None)
    monkeypatch.setattr(ap, "_ocr", lambda daten: _mrz_ukr())
    name = privatdateien.speichern(
        ANHANG_ORDNER, SimpleUploadedFile("ausweis.png", _png(), content_type="image/png"),
        typen={"image/png"})  # fmt: skip
    d = AntragAnhang.objects.create(antrag=antrag, name="ausweis.png", datei=name, typ="image/png")
    seite = admin_client.post(
        reverse("antraege:nachweis_pruefen", args=[antrag.pk, d.pk])
    ).content.decode()
    assert "weicht ab" in seite and "Ukraine" in seite  # deutlicher Hinweis
    assert 'name="staatsangehoerigkeit"' in seite and "Im Antrag übernehmen" in seite  # Auswahl

    # Übernehmen setzt die Staatsangehörigkeit im Antrag
    uurl = reverse("antraege:nachweis_staat_uebernehmen", args=[antrag.pk])
    antwort = admin_client.post(uurl, {"staatsangehoerigkeit": "Ukraine"}).content.decode()
    assert "Ukraine" in antwort
    assert Antrag.objects.get(pk=antrag.pk).staatsangehoerigkeit == "Ukraine"

    # Ungültige Auswahl (nicht in der Länderliste) ändert nichts
    admin_client.post(uurl, {"staatsangehoerigkeit": "Fantasialand"})
    assert Antrag.objects.get(pk=antrag.pk).staatsangehoerigkeit == "Ukraine"


_UKR = {"erkannt": True, "staatsangehoerigkeit": "Ukraine"}  # erfundener MRZ-Bericht für Tests


def _antrag_mit_ausweis(haupt="Deutschland", personen=()):
    from apps.antraege.models import Antrag, AntragAnhang, AntragPerson

    a = Antrag.objects.create(vorname="A", nachname="B", staatsangehoerigkeit=haupt)
    for n in personen:
        AntragPerson.objects.create(antrag=a, vorname="C", staatsangehoerigkeit=n)
    name = privatdateien.speichern(
        ANHANG_ORDNER, SimpleUploadedFile("ausweis.png", _png(), content_type="image/png"),
        typen={"image/png"})  # fmt: skip
    AntragAnhang.objects.create(antrag=a, name="ausweis.png", datei=name, typ="image/png")
    return a


def test_ausweis_scan_abweichung_und_treffer(monkeypatch):
    from apps.antraege import ausweis_pruefung, ausweis_scan

    monkeypatch.setattr(ausweis_pruefung, "pruefen", lambda inhalt, *a, **k: _UKR)
    # Hauptperson Deutschland, Ausweis Ukraine → Abweichung, Bild gemerkt
    antrag = _antrag_mit_ausweis("Deutschland")
    assert ausweis_scan.antrag_pruefen(antrag) is True
    antrag.refresh_from_db()
    assert antrag.ausweis_abweichung and antrag.ausweis_staat == "Ukraine"
    assert antrag.ausweis_anhang_id and antrag.ausweis_geprueft_am


def test_ausweis_scan_keine_abweichung(monkeypatch):
    from apps.antraege import ausweis_pruefung, ausweis_scan

    monkeypatch.setattr(ausweis_pruefung, "pruefen", lambda inhalt, *a, **k: _UKR)
    # Ukraine ist bei einem Angehörigen angegeben → keine Abweichung (ganzer Haushalt)
    antrag = _antrag_mit_ausweis("Deutschland", ["Ukraine"])
    assert ausweis_scan.antrag_pruefen(antrag) is False
    antrag.refresh_from_db()
    assert not antrag.ausweis_abweichung and antrag.ausweis_staat == "Ukraine"
    # Kein Ausweis erkannt → keine Abweichung, kein Staat, kein Hinweis
    monkeypatch.setattr(ausweis_pruefung, "pruefen", lambda inhalt, *a, **k: {"erkannt": False})
    leer = _antrag_mit_ausweis("Deutschland")
    assert ausweis_scan.antrag_pruefen(leer) is False
    leer.refresh_from_db()
    assert leer.ausweis_staat == "" and leer.ausweis_anhang_id is None and leer.ausweis_geprueft_am


def test_ausweis_scan_liste_bulk_banner_und_automatik(admin_client, monkeypatch):
    from apps.antraege import ausweis_pruefung, ausweis_scan
    from apps.antraege.models import AntragEinstellungen

    e = AntragEinstellungen.laden()
    e.ausweis_pruefen = True
    e.save()
    monkeypatch.setattr(ausweis_pruefung, "tesseract_vorhanden", lambda: True)
    monkeypatch.setattr(ausweis_pruefung, "pruefen", lambda inhalt, *a, **k: _UKR)
    monkeypatch.setattr(ausweis_scan, "_im_hintergrund", lambda fn: fn())  # synchron

    # Automatik: neuer Antrag wird beim Eingang geprüft
    antrag = _antrag_mit_ausweis("Deutschland")
    ausweis_scan.neuen_pruefen(antrag.pk)
    antrag.refresh_from_db()
    assert antrag.ausweis_abweichung

    # Sammelprüfung über die Liste
    zweiter = _antrag_mit_ausweis("Deutschland")
    admin_client.post(reverse("antraege:ausweise_pruefen_alle"))
    zweiter.refresh_from_db()
    assert zweiter.ausweis_abweichung

    # Liste zeigt Marker und Knopf
    liste = admin_client.get(reverse("antraege:liste")).content.decode()
    assert "Ausweis ≠" in liste and "Alle Ausweise prüfen" in liste
    # Antragsseite zeigt Banner mit Bild und Übernahme
    detail = admin_client.get(reverse("antraege:antrag", args=[antrag.pk])).content.decode()
    assert "weicht ab" in detail and "Im Antrag übernehmen" in detail
    assert reverse("antraege:anhang", args=[antrag.pk, antrag.ausweis_anhang_id]) in detail
    # Übernehmen räumt den Hinweis weg
    admin_client.post(reverse("antraege:nachweis_staat_uebernehmen", args=[antrag.pk]),
                      {"staatsangehoerigkeit": "Ukraine"})  # fmt: skip
    antrag.refresh_from_db()
    assert antrag.staatsangehoerigkeit == "Ukraine" and not antrag.ausweis_abweichung


_IMPORT_CSV = (
    "nummer;vorname;nachname;geburtsdatum;staatsangehoerigkeit;personen;nachricht;anmerkung\n"
    "500;Anna;Muster;1980-05-01;Deutschland;Kind Muster 2015-03-04 (Ukraine) | Opa Muster;Bitte anrufen;intern\n"  # noqa: E501
    ";Bruno;Beispiel;;Ukraine;;;\n"
    "500;Clara;Doppelt;;;;;\n"
    ";;Ohnevorname;;;;;\n"
)


def _csv_datei(text=_IMPORT_CSV, name="antraege.csv"):
    return SimpleUploadedFile(name, text.encode("utf-8-sig"), content_type="text/csv")


def test_antrag_import_pruefen_und_uebernehmen():
    from apps.antraege import antrag_import
    from apps.antraege.models import Antrag

    bericht = antrag_import.pruefen(_csv_datei())
    z = bericht["zaehler"]
    assert z["ok"] == 2 and z["dublette"] == 1 and z["unvollstaendig"] == 1
    assert not bericht["geschrieben"] and not Antrag.objects.exists()  # Probelauf schreibt nichts

    bericht = antrag_import.uebernehmen(_csv_datei())
    assert bericht["zaehler"]["ok"] == 2
    assert Antrag.objects.count() == 2
    anna = Antrag.objects.get(laufnummer=500)
    assert anna.vorname == "Anna" and anna.staatsangehoerigkeit == "Deutschland"
    assert anna.geburtsdatum == dt.date(1980, 5, 1) and anna.nachricht == "Bitte anrufen"
    assert anna.anmerkungen.count() == 1 and anna.anmerkungen.first().text == "intern"
    # Angehörige aus der Spalte personen
    personen = list(anna.personen.all())
    assert len(personen) == 2
    kind = personen[0]
    assert kind.vorname == "Kind" and kind.nachname == "Muster"
    assert kind.geburtsdatum == dt.date(2015, 3, 4) and kind.staatsangehoerigkeit == "Ukraine"
    # Ohne Nummer wurde automatisch eine vergeben
    bruno = Antrag.objects.get(vorname="Bruno")
    assert bruno.laufnummer and bruno.laufnummer != 500

    # Erneuter Lauf: beide „500“-Zeilen sind jetzt Dubletten (nichts doppelt unter der Nummer 500)
    bericht = antrag_import.uebernehmen(_csv_datei())
    assert bericht["zaehler"]["dublette"] == 2
    assert Antrag.objects.filter(laufnummer=500).count() == 1


def test_antrag_import_view_und_fehler(admin_client):
    from apps.antraege.models import Antrag

    url = reverse("antraege:antraege_importieren")
    # Probelauf (Haken „nur prüfen")
    admin_client.post(url, {"csv": _csv_datei(), "nur_pruefen": "on"})
    assert not Antrag.objects.exists()
    # Übernehmen
    antwort = admin_client.post(url, {"csv": _csv_datei()}, follow=True)
    assert "2 Anträge angelegt" in antwort.content.decode()
    assert Antrag.objects.count() == 2
    # Falsche Kopfzeile → klarer Fehler
    schlecht = admin_client.post(url, {"csv": _csv_datei("foo;bar\n1;2\n")}, follow=True)
    assert "vorname und nachname" in schlecht.content.decode()


def test_nachweis_import_fehler_und_view(admin_client, antrag):
    from apps.antraege import nachweis_import

    # Falscher Dateityp wird abgewiesen, fehlende Liste gibt einen klaren Fehler
    manifest = f"antragsnummer;datei\n{antrag.laufnummer};a.txt\n"
    bericht = nachweis_import.pruefen(io.BytesIO(_zip({"a.txt": b"x"}, manifest)))
    assert bericht["zaehler"]["typ"] == 1
    # ZIP ohne nachweise.csv → klarer Fehler
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("x.pdf", b"%PDF")
    with pytest.raises(nachweis_import.ImportFehler):
        nachweis_import.pruefen(io.BytesIO(puffer.getvalue()))
    # Über die Seite: Probelauf speichert nichts, Übernehmen hängt an
    url = reverse("antraege:nachweise_importieren")
    gut = _zip({"a.pdf": b"%PDF-1.4 x"}, f"antragsnummer;datei\n{antrag.laufnummer};a.pdf\n")
    antwort = admin_client.post(
        url, {"zip": SimpleUploadedFile("n.zip", gut, content_type="application/zip"),
              "nur_pruefen": "on"})  # fmt: skip
    assert antrag.anhaenge.count() == 0 and "Probelauf" in antwort.content.decode()
    admin_client.post(
        url, {"zip": SimpleUploadedFile("n.zip", gut, content_type="application/zip")}
    )
    assert antrag.anhaenge.count() == 1


def test_auskunft_und_export(admin_client, antrag, pdf_text):
    AntragAnmerkung.objects.create(antrag=antrag, text="Testanmerkung", von="chefin")
    AntragAnhang.objects.create(antrag=antrag, name="bescheid.pdf", datei="x", typ="a",
                                groesse=2048)  # fmt: skip
    inhalt = pdf_text(admin_client.get(reverse("antraege:auskunft", args=[antrag.pk])))
    for wort in ("Erika", "Max", "Polen", "Testanmerkung", "bescheid.pdf", "Ihre Rechte"):
        assert wort in inhalt, wort
    csv = admin_client.get(reverse("antraege:export")).content.decode("utf-8-sig")
    kopf, zeile = csv.splitlines()[:2]
    assert kopf.startswith("nummer;eingegangen_am")
    assert antrag.nummer in zeile and "Max 2015-05-05 (Polen) | Mia" in zeile
    assert "1980-02-03" in zeile


def test_nur_admin_und_buero(client, admin, benutzer_mit_rolle, anmelden, antrag):
    anmelden(client, benutzer_mit_rolle("kim", rollen.AUSGABE))
    assert client.get(reverse("antraege:liste")).status_code == 403
    assert "Anträge</a>" not in client.get(reverse("core:start")).content.decode()
    client.logout()
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(reverse("antraege:antrag", args=[antrag.pk])).status_code == 200
    assert client.get(reverse("antraege:einstellungen")).status_code == 403


def test_einstellungen_und_texte(admin_client, benutzer_mit_rolle):
    b = benutzer_mit_rolle("berta", rollen.BUERO)
    b.email = "berta@example.org"
    b.save()
    url = reverse("antraege:einstellungen")
    seite = admin_client.get(url).content.decode()
    assert "berta" in seite and "Arabisch" in seite and str(AntragEinstellungen.laden())
    werte = {f: "optional" for f in AntragEinstellungen.FELDER}
    werte |= {"aktiv": "on", "modus": "beides", "benachrichtigen": [b.pk],
              "erledigt_nach_tagen": 0, "papierkorb_nach_tagen": 90,
              "max_je_stunde": 5, "erste_nummer": 4201, "gebiet_pruefen": "aus",
              "datenschutz_url": "tafel.example.org/ds",
              "erklaerungen_url": "tafel.example.org/ausgabe",
              "voraussetzungen_url": "https://tafel.example.org/wer",
              "einverstaendnis_url": "tafel.example.org/einverstaendnis.pdf"}  # fmt: skip
    admin_client.post(url, werte)
    e = AntragEinstellungen.laden()
    assert e.aktiv and list(e.benachrichtigen.all()) == [b]
    assert e.datenschutz_url == "https://tafel.example.org/ds"
    assert e.erklaerungen_url == "https://tafel.example.org/ausgabe"
    formular = admin_client.get(reverse("antrag:formular", args=["en"])).content.decode()
    assert 'href="https://tafel.example.org/wer"' in formular
    assert 'href="https://tafel.example.org/einverstaendnis.pdf"' in formular
    assert "Declaration of consent" in formular
    assert (
        "Requirements and documents" in formular and "How the food distribution works" in formular
    )
    texte = reverse("antraege:texte", args=["ar"])
    assert 'dir="rtl"' in admin_client.get(texte).content.decode()
    vorschau = admin_client.post(
        texte, {"einleitung": "<h2>مرحبا</h2>", "bestaetigung": "رقم {nummer}", "vorschau": "1",
                "mail_text": "<p>{vorname}</p>"},
    ).content.decode()  # fmt: skip
    assert "Vorschau (noch nicht gespeichert)" in vorschau and "<h2>مرحبا</h2>" in vorschau
    assert "رقم 4201" not in vorschau and "رقم" in vorschau  # Nummer auch in der Vorschau leer
    assert "srcdoc=" in vorschau and "Erika" in vorschau and "lang=&quot;de&quot;" in vorschau
    # Die Mail steht maskiert im srcdoc, sonst bricht das Attribut am ersten Anführungszeichen ab
    assert 'srcdoc="&lt;!doctype html&gt;' in vorschau
    assert "&lt;div lang=&quot;ar&quot; dir=&quot;rtl&quot;" in vorschau  # unter Deutsch
    assert not AntragText.objects.filter(sprache="ar").exists()
    admin_client.post(texte, {"einleitung": "مرحبا", "bestaetigung": ""})
    assert AntragText.objects.get(sprache="ar").einleitung == "مرحبا"
    assert "eigener Text" in admin_client.get(url).content.decode()
    assert admin_client.get(reverse("antraege:texte", args=["xx"])).status_code == 404


def test_fristen(antrag, django_capture_on_commit_callbacks):
    e = AntragEinstellungen.laden()
    jetzt = timezone.now()
    AntragVersuch.objects.create(schluessel="a", zeitpunkt=jetzt - dt.timedelta(days=2))
    assert fristen_anwenden(jetzt) == 0 and not AntragVersuch.objects.exists()
    antrag.refresh_from_db()
    assert antrag.status == "neu"  # „erledigt nach“ ist aus
    e.erledigt_nach_tagen = 10
    e.save()
    fristen_anwenden(jetzt + dt.timedelta(days=11))
    antrag.refresh_from_db()
    assert antrag.status == "erledigt" and antrag.bearbeitet_von == "Frist"
    # Nachweis anhängen, bevor der Antrag nach „Papierkorb nach 90 Tagen“ weggeräumt wird
    name = privatdateien.speichern(ANHANG_ORDNER, pdf(), typen={"application/pdf"})
    AntragAnhang.objects.create(antrag=antrag, name="b.pdf", datei=name, typ="application/pdf")
    # Abgeschlossene Anträge wandern in den gemeinsamen Papierkorb: Antrag weg, Eintrag da
    assert fristen_anwenden(jetzt + dt.timedelta(days=11 + 91)) == 1
    assert not Antrag.objects.exists()
    assert PapierkorbEintrag.objects.filter(art="Antrag").count() == 1
    assert privatdateien.pfad(ANHANG_ORDNER, name).exists()
    # Der gemeinsame Papierkorb löscht ihn nach seiner Frist endgültig, samt Nachweis
    tage = TafelEinstellungen.laden().papierkorb_tage
    with django_capture_on_commit_callbacks(execute=True):
        assert papierkorb.fristen_anwenden(jetzt + dt.timedelta(days=11 + 91 + tage + 1)) == 1
    assert not PapierkorbEintrag.objects.exists()
    assert not privatdateien.pfad(ANHANG_ORDNER, name).exists()


def test_menue_zeigt_zahl_offener_antraege(admin_client, client, benutzer_mit_rolle, anmelden):
    def zahl(c):
        seite = c.get(reverse("core:start")).content.decode()
        return seite.count(
            '<span class="menue-zahl" title="offene Anträge">2</span>'
        ) + seite.count('<span class="menue-zahl" title="2 offene Anträge">2</span>')

    Antrag.objects.create(vorname="Erika", nachname="Probe")
    Antrag.objects.create(vorname="Max", nachname="Probe", status=Antrag.Status.IN_BEARBEITUNG)
    Antrag.objects.create(vorname="Eva", nachname="Probe", status=Antrag.Status.ERLEDIGT)
    weg = Antrag.objects.create(vorname="Udo", nachname="Probe")
    in_papierkorb(weg)  # im gemeinsamen Papierkorb → zählt nicht mehr als offen
    assert zahl(admin_client) == 2  # am Bereich und am Eintrag
    Antrag.objects.update(status=Antrag.Status.ERLEDIGT)
    assert (
        '<span class="menue-zahl" title="offene Anträge">0</span>'
        in admin_client.get(reverse("core:start")).content.decode()
    )  # die Zahl steht immer da, auch bei 0
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert "menue-zahl" not in client.get(reverse("core:start")).content.decode()


def test_hinweis_zu_den_nachweisen(client, offen):
    from apps.antraege.models import AntragText

    assert (
        "antrag-hinweis" not in client.get(reverse("antrag:formular", args=["de"])).content.decode()
    )
    AntragText.objects.create(sprache="de", anhaenge_hinweis="Ausweis <b>und</b> Bescheid")
    for code in ("de", "tr"):  # ohne eigenen Hinweis gilt der deutsche
        html = client.get(reverse("antrag:formular", args=[code])).content.decode()
        assert '<div class="antrag-hinweis">Ausweis <b>und</b> Bescheid</div>' in html
        assert "data-ablage" in html and "ablage.js" in html and "{#" not in html
    AntragText.objects.create(sprache="tr", anhaenge_hinweis="Kimlik")
    assert "<p>Kimlik</p>" in client.get(reverse("antrag:formular", args=["tr"])).content.decode()


def test_zurueck_knopf_fuehrt_zur_herkunft(client, offen):
    from django.test import Client

    url = reverse("antrag:formular", args=["de"])
    # Von außerhalb (z. B. Tafel-Homepage): „Zurück“ zeigt genau dorthin
    seite = client.get(url, HTTP_REFERER="https://tafel-essen.de/hilfe").content.decode()
    assert 'href="https://tafel-essen.de/hilfe"' in seite and "Zurück" in seite
    # Sprachwechsel (Verweis von der Antragsseite selbst) überschreibt die Herkunft nicht
    seite = client.get(reverse("antrag:formular", args=["tr"]),
                       HTTP_REFERER="http://testserver/antrag/de").content.decode()  # fmt: skip
    assert 'href="https://tafel-essen.de/hilfe"' in seite
    # Nach dem Absenden (Danke-Seite) weiterhin der Weg zurück zur Herkunft
    frisch = Client()
    direkt = frisch.get(url).content.decode()
    assert "antrag-zurueck" not in direkt  # Direktaufruf ohne Herkunft: kein Knopf


def test_behinderung_nur_wenn_eingeschaltet(client, offen, admin_client):
    from apps.antraege.auskunft import antrag_pdf
    from apps.antraege.models import Abfrage, Antrag

    assert 'name="gdb"' not in client.get(FORMULAR).content.decode()  # Vorgabe: nicht abfragen
    offen.behinderung = Abfrage.PFLICHT
    offen.save()
    seite = client.get(reverse("antrag:formular", args=["en"])).content.decode()
    assert 'name="gdb"' in seite and 'name="p1_gdb"' in seite and "GdB 50" in seite
    assert "no disability" in seite
    assert "gdb" in client.post(FORMULAR, daten()).context["form"].errors  # Pflicht
    client.post(FORMULAR, daten(gdb="60", p1_vorname="Lina", p1_gdb="0", p2_vorname="Tom"))
    a = Antrag.objects.get()
    assert (a.gdb, a.gdb_text) == (60, "GdB 60")
    assert [(p.vorname, p.gdb) for p in a.personen.all()] == [("Lina", 0), ("Tom", None)]
    seite = admin_client.get(reverse("antraege:antrag", args=[a.pk])).content.decode()
    assert "GdB 60" in seite and "keine Behinderung" in seite
    assert antrag_pdf(a)  # Auskunft enthält die Angaben (Tabelle mit Spalte Behinderung)


# --- KI-Übersetzung (ADR 0082) -------------------------------------------------------------


class _Antwort:
    def __init__(self, text, stop="end_turn"):
        self.stop_reason = stop
        self.content = [type("Block", (), {"type": "text", "text": text})()]


def _ki(monkeypatch, antwort):
    """Ersetzt den Claude-Client; ``antwort(anfrage) -> _Antwort`` oder eine Ausnahme."""
    from apps.antraege import uebersetzen

    anfragen = []

    class Nachrichten:
        def create(self, **anfrage):
            anfragen.append(anfrage)
            ergebnis = antwort(anfrage)
            if isinstance(ergebnis, Exception):
                raise ergebnis
            return ergebnis

    client = type("Client", (), {"beta": type("Beta", (), {"messages": Nachrichten()})()})()
    monkeypatch.setattr(uebersetzen, "_client", lambda: client)
    return anfragen


def test_ki_uebersetzung(admin_client, monkeypatch):
    import httpx2
    from anthropic import AuthenticationError

    from apps.antraege import uebersetzen
    from apps.core import geheimnis

    texte = reverse("antraege:texte", args=["de"])
    assert "Mit KI in alle Sprachen" not in admin_client.get(texte).content.decode()
    assert admin_client.post(reverse("antraege:uebersetzen")).url == texte  # ohne Schlüssel
    e = AntragEinstellungen.laden()
    e.ki_schluessel_verschluesselt = geheimnis.verschluesseln("sk-erfunden")
    e.save()
    assert "Mit KI in alle Sprachen" in admin_client.get(texte).content.decode()
    assert admin_client.post(reverse("antraege:uebersetzen")).url == texte  # noch keine Texte
    AntragText.objects.create(sprache="de", einleitung="<p>Willkommen bei {tafel}</p>",
                              mail_betreff="Antrag {nummer}")  # fmt: skip

    def gut(anfrage):
        assert anfrage["fallbacks"] == "default" and "Sprache" in anfrage["system"]
        assert set(json.loads(anfrage["messages"][0]["content"])) == {"einleitung", "mail_betreff"}
        return _Antwort(
            json.dumps({"einleitung": "<p>{tafel} hoş geldiniz</p>", "mail_betreff": "Başvuru"})
        )  # Platzhalter fehlt

    _ki(monkeypatch, gut)
    seite = admin_client.post(reverse("antraege:uebersetzen")).content.decode()
    erste = uebersetzen.sprachen_ohne_deutsch()[0].code
    assert f'hx-post="{reverse("antraege:uebersetzen_sprache", args=[erste])}"' in seite
    teil = admin_client.post(reverse("antraege:uebersetzen_sprache", args=["tr"])).content.decode()
    assert "✓" in teil and "(1 Text)" in teil and "uebersetzen/uk/" in teil  # nächste Sprache
    tr = AntragText.objects.get(sprache="tr")
    assert tr.einleitung == "<p>{tafel} hoş geldiniz</p>" and tr.mail_betreff == ""
    assert "Fertig" in admin_client.post(
        reverse("antraege:uebersetzen_sprache",
                args=[uebersetzen.sprachen_ohne_deutsch()[-1].code])).content.decode()  # fmt: skip
    deutsch = reverse("antraege:uebersetzen_sprache", args=["de"])
    assert admin_client.post(deutsch).status_code == 404

    anfrage = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    falsch = AuthenticationError("nein", response=httpx2.Response(401, request=anfrage), body=None)
    _ki(monkeypatch, lambda a: falsch)
    teil = admin_client.post(reverse("antraege:uebersetzen_sprache", args=["en"])).content.decode()
    assert "nicht angenommen" in teil
    _ki(monkeypatch, lambda a: _Antwort("kein json"))
    with pytest.raises(uebersetzen.UebersetzungsFehler):
        uebersetzen.sprache_uebersetzen("en")
    _ki(monkeypatch, lambda a: _Antwort("{}", stop="refusal"))
    with pytest.raises(uebersetzen.UebersetzungsFehler):
        uebersetzen.sprache_uebersetzen("en")


def test_ki_schluessel_speichern(admin_client):
    from apps.antraege import uebersetzen

    url = reverse("antraege:einstellungen")
    werte = {f: "optional" for f in AntragEinstellungen.FELDER}
    werte |= {"modus": "beides", "erledigt_nach_tagen": 0, "papierkorb_nach_tagen": 90,
              "max_je_stunde": 5, "gebiet_pruefen": "aus",
              "erste_nummer": 1}  # fmt: skip
    admin_client.post(url, werte | {"ki_schluessel": "sk-erfunden"})
    e = AntragEinstellungen.laden()
    assert "sk-erfunden" not in e.ki_schluessel_verschluesselt and uebersetzen.verfuegbar()
    assert "sk-erfunden" not in admin_client.get(url).content.decode()
    admin_client.post(url, werte)  # leer: bleibt
    assert uebersetzen.verfuegbar()
    admin_client.post(url, werte | {"ki_schluessel_loeschen": "on"})
    assert not uebersetzen.verfuegbar()


def test_erklaerungen_als_pflicht_bestaetigen(client, offen, admin_client):
    from apps.antraege.models import Antrag

    # Vorgabe: alle drei Häkchen, auch ohne eingetragene Links (dann ohne Link darunter)
    seite = client.get(FORMULAR).content.decode()
    for name in ("einwilligung", "datenschutz_bestaetigt", "einverstaendnis_bestaetigt"):
        assert f'name="{name}"' in seite, name
    assert "Ich habe die Einverständniserklärung gelesen" in seite and ".pdf" not in seite
    ohne = {"einwilligung": "", "datenschutz_bestaetigt": "", "einverstaendnis_bestaetigt": ""}
    fehler = client.post(FORMULAR, daten(**ohne)).context["form"].errors
    assert set(fehler) == {"einwilligung", "datenschutz_bestaetigt", "einverstaendnis_bestaetigt"}
    assert "Bitte bestätigen Sie das" in fehler["datenschutz_bestaetigt"][0]
    assert not Antrag.objects.exists()
    offen.einverstaendnis_url = "https://tafel.example.org/einverstaendnis.pdf"
    offen.save()
    seite = client.get(FORMULAR).content.decode()
    assert 'href="https://tafel.example.org/einverstaendnis.pdf"' in seite
    client.post(FORMULAR, daten())
    a = Antrag.objects.get()
    assert a.einwilligung_bestaetigt and a.datenschutz_bestaetigt and a.einverstaendnis_bestaetigt
    seite = admin_client.get(reverse("antraege:antrag", args=[a.pk])).content.decode()
    assert "Speichern der Angaben · Datenschutzerklärung gelesen · Einverständniserklärung" in seite
    # Einzeln abschaltbar
    offen.einwilligung_abfragen = offen.datenschutz_abfragen = False
    offen.save()
    seite = client.get(FORMULAR).content.decode()
    assert 'name="einwilligung"' not in seite and 'name="datenschutz_bestaetigt"' not in seite
    client.post(FORMULAR, daten(**ohne | {"einverstaendnis_bestaetigt": "on"}, vorname="Ole"))
    b = Antrag.objects.get(vorname="Ole")
    assert not b.einwilligung_bestaetigt and not b.datenschutz_bestaetigt
    assert b.einverstaendnis_bestaetigt


def test_merkzeichen_mit_gdb(client, offen):
    from apps.antraege.models import Abfrage, Antrag

    offen.behinderung = Abfrage.OPTIONAL
    offen.save()
    seite = client.get(FORMULAR).content.decode()
    assert 'name="merkzeichen"' in seite and "aG (außergewöhnlich gehbehindert)" in seite
    assert 'name="p1_merkzeichen"' in seite and "data-merkzeichen-fuer" in seite
    englisch = client.get(reverse("antrag:formular", args=["en"])).content.decode()
    assert "Marks on the disability ID card" in englisch and "gehbehindert" not in englisch
    client.post(FORMULAR, daten(gdb="80", merkzeichen=["B", "G"], p1_vorname="Lina",
                                p1_gdb="0", p1_merkzeichen=["H"]))  # fmt: skip
    a = Antrag.objects.get()
    assert a.merkzeichen == "G, B" and a.gdb_text == (
        "GdB 80, Merkzeichen G (erheblich gehbehindert), B (Begleitperson berechtigt)"
    )
    assert a.personen.get().merkzeichen == ""  # ohne GdB keine Merkzeichen


def test_merkzeichen_unbekannt_abgelehnt(client, offen):
    from apps.antraege.models import Abfrage, Antrag

    offen.behinderung = Abfrage.OPTIONAL
    offen.save()
    antwort = client.post(FORMULAR, daten(gdb="80", merkzeichen=["G", "Unsinn"]))
    assert antwort.status_code == 200 and not Antrag.objects.exists()


def test_kopf_ueberschrift_fuss_ein_und_ausblenden(client, offen):
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.name = "Beispieltafel"
    t.save()
    seite = client.get(FORMULAR).content.decode()
    assert '<span class="marke">' in seite and 'class="antrag-titel"' in seite
    assert '<footer class="fuss">' in seite
    assert "antrag-eigener-kopf" not in seite and "antrag-eigener-fuss" not in seite
    offen.kopf_zeigen = offen.ueberschrift_zeigen = offen.fuss_zeigen = False
    offen.save()
    seite = client.get(FORMULAR).content.decode()
    assert '<span class="marke">' not in seite and "ohne-marke" in seite
    assert 'name="sprache"' in seite  # die Sprachwahl bleibt
    assert 'class="antrag-titel"' not in seite and '<footer class="fuss">' not in seite
    offen.aktiv = False
    offen.save()
    assert "<h1>" not in client.get(FORMULAR).content.decode()  # geschlossen, ohne Überschrift


def test_eigener_kopf_und_fuss_je_sprache(client, offen, admin_client):
    texte = reverse("antraege:texte", args=["de"])
    seite = admin_client.get(texte).content.decode()
    assert 'name="kopf"' in seite and 'name="fuss"' in seite
    antwort = admin_client.post(texte, {"kopf": '<p style="text-align: center">Kopf {tafel}</p>',
                                        "fuss": "<p>Öffnungszeiten Mo–Fr<script>x</script></p>",
                                        "vorschau": "1"})  # fmt: skip
    assert "Kopf Tafel</p>" in antwort.content.decode()  # Vorschau
    admin_client.post(texte, {"kopf": '<p style="text-align: center">Kopf {tafel}</p>',
                              "fuss": "<p>Öffnungszeiten Mo–Fr<script>x</script></p>"})  # fmt: skip
    seite = client.get(FORMULAR).content.decode()
    assert '<div class="antrag-bereich antrag-eigener-kopf"><p style="text-align:center">' in seite
    assert "Kopf Tafel" in seite and "Öffnungszeiten Mo–Fr" in seite and "<script>x" not in seite
    assert seite.index("antrag-eigener-kopf") < seite.index("antrag-titel")
    assert seite.index("antrag-eigener-fuss") > seite.index("antrag-formular")
    englisch = reverse("antrag:formular", args=["en"])
    assert "Kopf Tafel" in client.get(englisch).content.decode()  # ohne eigenen: der deutsche
    AntragText.objects.create(sprache="en", kopf="<p>Header {tafel}</p>")
    seite = client.get(englisch).content.decode()
    assert "Header Tafel" in seite and "Kopf Tafel" not in seite and "Öffnungszeiten" in seite


def test_alte_merkzeichen_nicht_mehr_angeboten_aber_erhalten(client, offen, admin_client):
    from apps.antraege.models import Abfrage, Antrag

    offen.behinderung = Abfrage.OPTIONAL
    offen.save()
    seite = client.get(FORMULAR).content.decode()
    assert "RF (Rundfunkbeitrag ermäßigt)" in seite
    assert "Kriegsbeschädigte" not in seite and "versorgungsberechtigt" not in seite
    antwort = client.post(FORMULAR, daten(gdb="80", merkzeichen=["G", "VB"]))
    assert antwort.status_code == 200 and not Antrag.objects.exists()  # nicht mehr wählbar
    # schon gespeichert: bleibt sichtbar und beim Bearbeiten wählbar
    a = Antrag.objects.create(vorname="Erika", nachname="Beispiel", gdb=80, merkzeichen="G, VB")
    assert a.gdb_text.endswith("G (erheblich gehbehindert), VB (versorgungsberechtigt)")
    seite = admin_client.get(reverse("antraege:bearbeiten", args=[a.pk])).content.decode()
    assert "VB (versorgungsberechtigt)" in seite
    assert "Kriegsbeschädigte" not in seite


def test_rechtstext_intern_oder_extern(client, offen):
    """Datenschutz/Impressum/Einverständnis als interner Text oder externer Link (ADR 0094)."""
    e = offen
    from apps.core.models import TafelEinstellungen

    # externer Link hat Vorrang: ist er gesetzt, erscheint er – auch wenn ein interner Text da ist
    e.datenschutz_url = "https://tafel.example.org/datenschutz"
    e.save()
    tafel = TafelEinstellungen.laden()
    tafel.datenschutz_text = (
        "<h2>Datenschutz</h2><p>Nur erfundene Angaben.</p><script>alert(1)</script>"
    )
    tafel.save()
    intern = reverse("antrag:rechtstext", args=["de", "datenschutz"])
    seite = client.get(FORMULAR).content.decode()
    assert "https://tafel.example.org/datenschutz" in seite and intern not in seite
    # kein externer Link → der interne Text greift (Rückfallebene)
    e.datenschutz_url = ""
    e.save()
    seite = client.get(FORMULAR).content.decode()
    assert intern in seite and "tafel.example.org/datenschutz" not in seite
    # die interne Seite zeigt den Text bereinigt (ohne <script>)
    antwort = client.get(intern)
    inhalt = antwort.content.decode()
    assert antwort.status_code == 200
    assert "Nur erfundene Angaben." in inhalt and "<script>alert" not in inhalt
    # Nur der Text: keine Sprachwahl (einsprachig) und keine Fußzeile mit anderen Links
    assert 'name="sprache"' not in inhalt and '<footer class="fuss"' not in inhalt
    # ohne Text 404; unbekannte Art 404
    assert client.get(reverse("antrag:rechtstext", args=["de", "impressum"])).status_code == 404
    assert client.get(reverse("antrag:rechtstext", args=["de", "unbekannt"])).status_code == 404


def test_rechtstext_zurueck_fuehrt_woher_man_kam(client, offen):
    """„Zurück" führt dorthin, woher man kam – nicht immer zum Antrag."""
    from apps.core.models import TafelEinstellungen

    t = TafelEinstellungen.laden()
    t.impressum_text = "<p>Impressum</p>"
    t.save()
    intern = reverse("antrag:rechtstext", args=["de", "impressum"])
    # Ohne Herkunft: gar kein Zurück-Link (der Browser-Zurück genügt)
    ohne = client.get(intern).content.decode()
    assert 'class="abseits"' not in ohne
    # Von der Anmeldeseite gekommen: Zurück führt dorthin zurück
    anmelden = "http://testserver" + reverse("konten:anmelden")
    mit = client.get(intern, HTTP_REFERER=anmelden).content.decode()
    assert f'href="{anmelden}"' in mit
    # Fremde Seite als Herkunft wird nicht übernommen
    fremd = client.get(intern, HTTP_REFERER="https://boese.example.org/x").content.decode()
    assert "boese.example.org" not in fremd


def test_rechtstexte_bearbeiten(admin_client, offen):
    """Rechtstexte liegen in den Tafel-Einstellungen (ADR 0094)."""
    from apps.core.models import TafelEinstellungen

    url = reverse("core:rechtstexte")
    assert 'name="impressum_text"' in admin_client.get(url).content.decode()
    admin_client.post(url, {"datenschutz_text": "", "impressum_text": "<p>Impressum der Tafel</p>",
                            "einverstaendnis_text": ""})  # fmt: skip
    assert TafelEinstellungen.laden().impressum_text == "<p>Impressum der Tafel</p>"
    seite = admin_client.get(url).content.decode()
    assert "Impressum ansehen" in seite  # Ansehen-Link erscheint, da Text gesetzt
    antwort = admin_client.get(reverse("antrag:rechtstext", args=["de", "impressum"]))
    assert "Impressum der Tafel" in antwort.content.decode()


def test_flyer_und_voraussetzungen_pflicht(client, offen):
    """Voraussetzungen und Erklärungen (z. B. MHD-Flyer) als abschaltbare Pflicht-Häkchen."""
    e = offen
    e.voraussetzungen_abfragen = True
    e.erklaerungen_abfragen = True
    e.erklaerungen_url = "https://tafel.example.org/mhd-flyer.pdf"
    e.save()
    # das Formular zeigt die beiden Häkchen (Rahmen „Ich habe gelesen: …“) und den Flyer-Link
    seite = client.get(FORMULAR).content.decode()
    assert 'name="voraussetzungen_bestaetigt"' in seite
    assert 'name="erklaerungen_bestaetigt"' in seite
    assert "Ich habe gelesen:" in seite and "https://tafel.example.org/mhd-flyer.pdf" in seite
    # ohne die Haken wird der Antrag abgelehnt
    antwort = client.post(FORMULAR, daten(), HTTP_X_FORWARDED_FOR="203.0.113.9")
    assert not Antrag.objects.exists()
    assert antwort.context["form"].errors.keys() >= {"voraussetzungen_bestaetigt",
                                                      "erklaerungen_bestaetigt"}  # fmt: skip
    # mit den Haken geht er durch und wird vermerkt
    antwort = client.post(FORMULAR, daten(voraussetzungen_bestaetigt="on",
                                          erklaerungen_bestaetigt="on"),
                          HTTP_X_FORWARDED_FOR="203.0.113.9")  # fmt: skip
    assert antwort.url == reverse("antrag:danke", args=["de"])
    a = Antrag.objects.get()
    assert a.voraussetzungen_bestaetigt and a.erklaerungen_bestaetigt
    # abschaltbar: ohne die Einstellung kein Häkchen
    e.voraussetzungen_abfragen = e.erklaerungen_abfragen = False
    e.save()
    assert 'name="voraussetzungen_bestaetigt"' not in client.get(FORMULAR).content.decode()
