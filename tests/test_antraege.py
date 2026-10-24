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
        "einwilligung": "on", **mehr,
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
    assert bestaetigung.to == ["erika@example.org"] and a.nummer in bestaetigung.body
    assert hinweis.to == ["berta@example.org"] and "Erika" not in hinweis.body
    danke = client.get(antwort.url).content.decode()
    assert a.nummer in danke and "erika@example.org" in danke
    assert client.get(antwort.url).url == reverse("antrag:formular", args=["en"])  # nur einmal


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
    assert f"Ihre Nummer: <b>{a.nummer}</b> bei Tafel" in antwort.content.decode()
    m = django_mail.outbox[0]
    assert m.subject == f"Antrag {a.nummer}"
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


def test_form_personen_leer_ohne_angehoerige(offen):
    offen.angehoerige = Abfrage.AUS
    form = AntragForm(texte=sprachen.texte("de"), einstellungen=offen)
    assert form.personen_zeilen == []


# --- Bearbeitung ---------------------------------------------------------------------------


@pytest.fixture
def antrag(db):
    a = Antrag.objects.create(vorname="Erika", nachname="Beispiel", email="e@example.org",
                              kundennummer="1001", geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    AntragPerson.objects.create(antrag=a, vorname="Max", geburtsdatum=dt.date(2015, 5, 5))
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
    for wort in ("Erika", "Max", "Testanmerkung", "bescheid.pdf", "Ihre Rechte"):
        assert wort in inhalt, wort
    csv = admin_client.get(reverse("antraege:export")).content.decode("utf-8-sig")
    kopf, zeile = csv.splitlines()[:2]
    assert kopf.startswith("nummer;eingegangen_am")
    assert antrag.nummer in zeile and "Max  2015-05-05 | Mia" in zeile and "1980-02-03" in zeile


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
              "datenschutz_url": "tafel.example.org/ds"}  # fmt: skip
    admin_client.post(url, werte)
    e = AntragEinstellungen.laden()
    assert e.aktiv and list(e.benachrichtigen.all()) == [b]
    assert e.datenschutz_url == "https://tafel.example.org/ds"
    texte = reverse("antraege:texte", args=["ar"])
    assert 'dir="rtl"' in admin_client.get(texte).content.decode()
    vorschau = admin_client.post(
        texte, {"einleitung": "<h2>مرحبا</h2>", "bestaetigung": "رقم {nummer}", "vorschau": "1",
                "mail_text": "<p>{vorname}</p>"},
    ).content.decode()  # fmt: skip
    assert "Vorschau (noch nicht gespeichert)" in vorschau and "<h2>مرحبا</h2>" in vorschau
    assert "رقم 2026-00001" in vorschau and "srcdoc=" in vorschau and "Erika" in vorschau
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
