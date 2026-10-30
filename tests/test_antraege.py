import datetime as dt
import json
import re

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
)
from apps.antraege.views_oeffentlich import besucher_ip
from apps.core import geheimnis, privatdateien
from apps.core.models import MailEinstellungen
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
                                   p2_nachname="Ohne Vorname")).content.decode()  # fmt: skip
    for schluessel in ("fehler_einwilligung", "fehler_datum", "fehler_pflicht"):
        assert t[schluessel] in seite, schluessel
    zu_viele = [pdf(f"{n}.pdf") for n in range(MAX_ANHAENGE + 1)]
    assert t["fehler_datei_anzahl"].format(anzahl=MAX_ANHAENGE) in client.post(
        url, daten(anhaenge=zu_viele)).content.decode()  # fmt: skip
    text = SimpleUploadedFile("a.txt", b"x", content_type="text/plain")
    assert t["fehler_datei_typ"] in client.post(url, daten(anhaenge=[text])).content.decode()
    gross = pdf(groesse=11 * 1024 * 1024)
    assert "MB" in client.post(url, daten(anhaenge=[gross])).content.decode()
    assert not Antrag.objects.exists()


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


def test_liste_und_detail(admin_client, antrag):
    Antrag.objects.create(vorname="Zweite", nachname="Person")
    seite = admin_client.get(reverse("antraege:liste")).content.decode()
    assert antrag.nummer in seite and "Offen (2)" in seite
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


def test_bearbeiten_und_loeschen(admin_client, antrag):
    url = reverse("antraege:antrag", args=[antrag.pk])
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
    admin_client.post(reverse("antraege:papierkorb", args=[antrag.pk]))
    antrag.refresh_from_db()
    assert antrag.papierkorb_am
    assert "Endgültig löschen" in admin_client.get(url).content.decode()
    admin_client.post(reverse("antraege:papierkorb", args=[antrag.pk]))
    antrag.refresh_from_db()
    assert antrag.papierkorb_am is None
    assert admin_client.post(reverse("antraege:loeschen", args=[antrag.pk])).status_code == 404
    admin_client.post(reverse("antraege:papierkorb", args=[antrag.pk]))
    admin_client.post(reverse("antraege:loeschen", args=[antrag.pk]))
    assert not Antrag.objects.exists() and not AntragPerson.objects.exists()
    assert not LogEntry.objects.filter(object_pk=str(antrag.pk),
                                       content_type__model="antrag").exists()  # fmt: skip


def test_nachweis_ansehen(admin_client, antrag):
    name = privatdateien.speichern(ANHANG_ORDNER, pdf(), typen={"application/pdf"})
    d = AntragAnhang.objects.create(antrag=antrag, name="b.pdf", datei=name,
                                    typ="application/pdf", groesse=14)  # fmt: skip
    url = reverse("antraege:anhang", args=[antrag.pk, d.pk])
    assert admin_client.get(url).content.startswith(b"%PDF") and str(d) == "b.pdf"
    privatdateien.pfad(ANHANG_ORDNER, name).unlink()
    assert admin_client.get(url).status_code == 404


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
              "erledigt_nach_tagen": 0, "papierkorb_nach_tagen": 90, "loeschen_nach_tagen": 30,
              "erste_nummer": 4201, "gebiet_pruefen": "aus",
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


def test_fristen(antrag):
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
    fristen_anwenden(jetzt + dt.timedelta(days=11 + 91))
    antrag.refresh_from_db()
    assert antrag.papierkorb_am
    name = privatdateien.speichern(ANHANG_ORDNER, pdf(), typen={"application/pdf"})
    AntragAnhang.objects.create(antrag=antrag, name="b.pdf", datei=name, typ="application/pdf")
    assert fristen_anwenden(jetzt + dt.timedelta(days=11 + 91 + 31)) == 1
    assert not Antrag.objects.exists()
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
    Antrag.objects.create(vorname="Udo", nachname="Probe", papierkorb_am=timezone.now())
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
              "loeschen_nach_tagen": 30, "gebiet_pruefen": "aus", "erste_nummer": 1}  # fmt: skip
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
    # kein Text, nur externer Link → der externe Link erscheint
    e.datenschutz_url = "https://tafel.example.org/datenschutz"
    e.save()
    seite = client.get(FORMULAR).content.decode()
    assert "https://tafel.example.org/datenschutz" in seite
    # interner Text (in den Tafel-Einstellungen) gesetzt → der Link führt auf die interne Seite
    from apps.core.models import TafelEinstellungen

    tafel = TafelEinstellungen.laden()
    tafel.datenschutz_text = (
        "<h2>Datenschutz</h2><p>Nur erfundene Angaben.</p><script>alert(1)</script>"
    )
    tafel.save()
    intern = reverse("antrag:rechtstext", args=["de", "datenschutz"])
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
