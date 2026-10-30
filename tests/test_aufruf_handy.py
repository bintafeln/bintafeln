"""Wartezeit aufs Handy (ADR 0090): Anmeldung, Handy-Bindung, Anzeige, Aushang, Ausweis-QR."""

import datetime as dt

import pytest
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.antraege import sprachen
from apps.aufruf import ablauf, handy, views_warten
from apps.aufruf.models import AufrufEinstellungen, HandyCode, HandyEinstellungen, HandyZugang
from apps.ausgabe.ampel import WOCHENTAGE
from apps.core.models import TafelEinstellungen
from apps.kunden.models import Abholung, Ausgabestelle, Haushalt, Kundengruppe, Person

pytestmark = pytest.mark.django_db
SEITE = reverse("warten:seite")
GEBURT = dt.date(1970, 5, 17)


def heute():
    return timezone.localdate()


@pytest.fixture
def modul_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    HandyEinstellungen.objects.update_or_create(pk=1, defaults={"modus": "auswahl"})
    cache.clear()


def stelle_mit(name, handy_an=True):
    s = Ausgabestelle.objects.create(name=name)
    e = AufrufEinstellungen.laden(s)
    e.handy = handy_an
    e.save()
    g = Kundengruppe.objects.create(name=f"Gruppe {name}", ausgabestelle=s,
                                    wochentage=WOCHENTAGE[heute().weekday()],
                                    uhrzeit=dt.time(12))  # fmt: skip
    return s, g


def haushalt(g, nummer, geburt=GEBURT, status=Haushalt.Status.AKTIV):
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=g, status=status)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster",
                          geburtsdatum=geburt)  # fmt: skip
    return h


@pytest.fixture
def mitte(modul_an):
    s, g = stelle_mit("Mitte")
    for n in ("101", "102", "103", "104", "105", "106", "107", "108"):
        haushalt(g, n, geburt=dt.date(1980, 1, 1))
    haushalt(g, "109")
    return s


def anmelden(client, nummer="109", geburt="1970-05-17"):
    return client.post(SEITE, {"kundennummer": nummer, "geburtsdatum": geburt})


def test_mitgelieferte_texte_vollstaendig():
    import re

    de = views_warten.texte("de")
    for s in sprachen.SPRACHEN:
        t = views_warten._datei(s.code)
        assert set(t) == set(de), s.code
        for k, v in t.items():
            assert v.strip(), (s.code, k)
            assert set(re.findall(r"\{\w+\}", v)) == set(re.findall(r"\{\w+\}", de[k])), (s.code, k)


def test_anmelden_und_platz_sehen(client, mitte):
    seite = client.get(SEITE).content.decode()
    assert "Kundennummer" in seite and 'type="date"' in seite
    antwort = anmelden(client, geburt="1970-05-18")
    assert "stimmen nicht" in antwort.content.decode() and not HandyZugang.objects.exists()
    antwort = anmelden(client, geburt="17.05.1970")  # auch so getippt
    assert antwort.status_code == 302 and handy.COOKIE in antwort.cookies
    z = HandyZugang.objects.get()
    assert z.kundennummer == "109" and handy.COOKIE not in z.pruefsumme  # nur die Prüfsumme
    assert antwort.cookies[handy.COOKIE]["httponly"]
    seite = client.get(SEITE).content.decode()
    # noch nicht gestartet: Vorschau
    assert "noch nicht begonnen" in seite and "Mitte" in seite and "109" in seite
    assert 'http-equiv="refresh"' in seite and "Erika" not in seite and "Muster" not in seite
    ablauf.starten(mitte, heute())
    seite = client.get(SEITE).content.decode()
    assert "vor Ihnen" in seite or "Bitte jetzt eintreten" in seite


def test_platz_jetzt_aufgerufen_erledigt(client, mitte):
    anmelden(client)
    tag = ablauf.starten(mitte, heute())
    s = tag.stand
    reihe = s["gruppen"][0]["wartend"]
    platz = reihe.index("109")
    z = HandyZugang.objects.get()
    anzahl = AufrufEinstellungen.laden(mitte).anzahl
    stand = handy.stand(z)
    if platz < anzahl:
        assert stand["art"] == "jetzt"
    else:
        assert stand["art"] == "warten" and stand["vor"] == platz  # wie am Kiosk
    # alle durchrufen: dann „aufgerufen“
    for _ in range(4):
        ablauf.weiter(mitte, heute())
    assert handy.stand(z)["art"] in {"aufgerufen", "jetzt"}
    Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer="109"), datum=heute(),
                            uhrzeit=dt.time(12, 30))  # fmt: skip
    assert handy.stand(z)["art"] == "erledigt"
    assert "schon da" in client.get(SEITE).content.decode()


def test_schaetzung_aus_den_letzten_aufrufen(mitte):
    tag = ablauf.starten(mitte, heute())
    jetzt = timezone.now()
    tag.stand["rueckgaengig"] = [
        {"gruppe": 0, "nummern": ["101", "102", "103"], "zeit": "12:00",
         "zeitpunkt": (jetzt - dt.timedelta(minutes=12)).isoformat()},
        {"gruppe": 0, "nummern": ["104", "105", "106"], "zeit": "12:06",
         "zeitpunkt": (jetzt - dt.timedelta(minutes=6)).isoformat()},
        {"gruppe": 0, "nummern": ["107", "108"], "zeit": "12:12", "zeitpunkt": jetzt.isoformat()},
    ]  # fmt: skip
    assert handy.minuten_je_nummer(tag) == pytest.approx(12 / 5)
    tag.stand["rueckgaengig"] = tag.stand["rueckgaengig"][:1]
    assert handy.minuten_je_nummer(tag) is None


def test_andere_ausgabestelle_und_aus(client, mitte):
    _, g = stelle_mit("Nord", handy_an=False)
    haushalt(g, "501")
    antwort = anmelden(client, "501")
    assert "gibt es diese Anzeige nicht" in antwort.content.decode()
    assert not HandyZugang.objects.exists()
    # Kunde von Mitte sieht nur Mitte – egal, wo der Aushang hängt
    anmelden(client)
    seite = client.get(SEITE).content.decode()
    assert "Mitte" in seite and "Nord" not in seite
    # Ausgabestelle schaltet aus: nichts mehr zu sehen
    AufrufEinstellungen.objects.filter(ausgabestelle=mitte).update(handy=False)
    assert "gibt es diese Anzeige nicht" in client.get(SEITE).content.decode()


def test_gesperrter_haushalt_und_heute_kein_termin(client, mitte):
    g = Kundengruppe.objects.get(ausgabestelle=mitte)
    haushalt(g, "120", status=Haushalt.Status.GESPERRT)
    assert "gibt es diese Anzeige nicht" in anmelden(client, "120").content.decode()
    morgen = Kundengruppe.objects.create(name="Morgen", ausgabestelle=mitte,
                                         wochentage=WOCHENTAGE[(heute().weekday() + 1) % 7],
                                         uhrzeit=dt.time(12))  # fmt: skip
    haushalt(morgen, "130")
    anmelden(client, "130")
    assert "nicht an der Reihe" in client.get(SEITE).content.decode()


def test_handys_je_haushalt_begrenzt(mitte, admin_client):
    for _ in range(2):
        assert anmelden(Client()).status_code == 302
    antwort = anmelden(Client())
    assert "genug Handys" in antwort.content.decode()
    assert HandyZugang.objects.count() == 2
    # Einlass sieht die Handys und setzt zurück
    h = Haushalt.objects.get(kundennummer="109")
    hinweise = ablauf.einlass(h, heute(), mitte)
    assert hinweise[0]["text"] == "Wartezeit aufs Handy: 2 Handys eingerichtet"
    url = hinweise[0]["knopf"]["url"]
    assert url == reverse("aufruf:handys_zuruecksetzen", args=["109"])
    antwort = admin_client.post(url)
    assert antwort.status_code == 302 and not HandyZugang.objects.exists()
    assert anmelden(Client()).status_code == 302


def test_abmelden_und_falsche_versuche_sperren(client, mitte):
    anmelden(client)
    client.post(reverse("warten:abmelden"))
    assert not HandyZugang.objects.exists()
    assert "Kundennummer" in client.get(SEITE).content.decode()
    fremd = Client(REMOTE_ADDR="203.0.113.9")
    for _ in range(handy.FEHLVERSUCHE):
        anmelden(fremd, geburt="1999-01-01")
    antwort = anmelden(fremd)  # jetzt auch mit richtigen Daten gesperrt
    assert "Zu viele Versuche" in antwort.content.decode() and not HandyZugang.objects.exists()
    assert anmelden(client).status_code == 302  # andere Adresse nicht betroffen


def test_sprache_waehlen(client, mitte):
    seite = client.get(SEITE, {"sprache": "ar"})
    assert 'lang="ar" dir="rtl"' in seite.content.decode()
    assert views_warten.SPRACH_COOKIE in seite.cookies
    assert "رقم العميل" in client.get(SEITE).content.decode()  # gemerkt
    seite = client.get(SEITE, HTTP_ACCEPT_LANGUAGE="tr")
    assert 'lang="ar"' in seite.content.decode()  # Cookie geht vor


def test_modul_aus_keine_seite(client, admin):
    assert client.get(SEITE).status_code == 404


def test_ausweis_qr_code(client, mitte, settings, pdf_text):
    from apps.kunden import ausweis
    from apps.kunden.models import AusweisVorlage

    h = Haushalt.objects.get(kundennummer="109")
    settings.DOMAIN = ""
    assert handy.ausweis_qr(h) == ""  # ohne öffentliche Adresse kein Code
    settings.DOMAIN = "tafel.example.org"
    adresse = handy.ausweis_qr(h)
    code = HandyCode.objects.get(kundennummer="109").code
    assert adresse == f"https://tafel.example.org/warten/a/{code}/"
    assert handy.ausweis_qr(h) != adresse  # jeder Druck ein neuer Code
    neu = HandyCode.objects.get(kundennummer="109").code
    assert "gilt nicht mehr" in client.get(reverse("warten:code", args=[code])).content.decode()
    antwort = client.get(reverse("warten:code", args=[neu]))
    assert antwort.status_code == 302 and HandyZugang.objects.filter(kundennummer="109").exists()
    # Vorlage ohne QR-Element: kein neuer Code beim Druck
    vorlage = AusweisVorlage.laden()
    ausweis.ausweise_pdf([h])
    assert HandyCode.objects.get(kundennummer="109").code == neu
    vorlage.vorderseite = [*ausweis.standard(), {"typ": "qr_handy", "x": 60, "y": 20, "b": 10,
                                                 "h": 10}]  # fmt: skip
    vorlage.save()
    assert ausweis.elemente_pruefen(vorlage.vorderseite)[-1]["b"] == ausweis.QR_MIN
    assert ausweis.ausweise_pdf([h])[:4] == b"%PDF"
    assert HandyCode.objects.get(kundennummer="109").code != neu


def test_einstellungen_und_aushang(admin_client, mitte, pdf_text):
    seite = admin_client.get(reverse("aufruf:einstellungen")).content.decode()
    assert "Wartezeit aufs Handy: an" in seite and "/warten/" in seite
    assert 'name="modus"' in seite and 'name="geraete"' in seite
    antwort = admin_client.get(reverse("aufruf:aushang"))
    assert antwort["Content-Type"] == "application/pdf"
    assert "Wartezeit auf dem Handy" in pdf_text(antwort) and "/warten/" in pdf_text(antwort)
    # Ausgabestellen direkt hier wählen, nicht mehr je Ausgabestelle unter „ändern“
    assert 'name="stellen"' in seite and 'data-zeigen-bei="modus=auswahl"' in seite
    url = reverse("aufruf:einstellungen_stelle", args=[mitte.pk])
    assert 'name="handy"' not in admin_client.get(url).content.decode()
    nord, _ = stelle_mit("Nord", handy_an=False)
    einstellungen = reverse("aufruf:einstellungen")
    admin_client.post(einstellungen, {"modus": "auswahl", "stellen": [nord.pk], "geraete": 2})
    assert AufrufEinstellungen.laden(nord).handy and not AufrufEinstellungen.laden(mitte).handy
    # bei „alle“ bleibt die Auswahl für später erhalten
    admin_client.post(einstellungen, {"modus": "alle", "geraete": 2})
    assert AufrufEinstellungen.laden(nord).handy


def test_zentral_fuer_alle_oder_aus(client, admin_client, mitte):
    _, g = stelle_mit("Nord", handy_an=False)
    haushalt(g, "501")
    einstellungen = reverse("aufruf:einstellungen")
    # an allen Ausgabestellen: auch Nord, obwohl dort nicht ausgewählt
    admin_client.post(einstellungen, {"modus": "alle", "geraete": 1})
    assert HandyEinstellungen.laden().geraete == 1
    assert anmelden(client, "501").status_code == 302
    assert "genug Handys" in anmelden(Client(), "501").content.decode()  # Grenze 1
    # zentral aus: niemand sieht etwas, auch schon angemeldete Handys nicht
    admin_client.post(einstellungen, {"modus": "aus", "geraete": 2})
    assert "gibt es diese Anzeige nicht" in client.get(SEITE).content.decode()
    assert "Zurzeit an keiner Ausgabestelle" in admin_client.get(einstellungen).content.decode()


def test_sprachvorschlag_nach_staatsangehoerigkeit(client, mitte):
    hp = Haushalt.objects.get(kundennummer="109").hauptperson
    hp.staatsangehoerigkeit = "Türkei"
    hp.save()
    anmelden(client)
    seite = client.get(SEITE).content.decode()
    assert 'data-vorschlag="tr"' in seite and 'id="sprach-hinweise"' in seite
    assert "sprachhinweis.js" in seite
    seite = client.get(SEITE, {"sprache": "de"}).content.decode()
    assert "data-vorschlag" not in seite  # selbst gewählt: kein Vorschlag mehr


def test_auskunft_nennt_handys(client, mitte, admin_client, pdf_text):
    anmelden(client)
    antwort = admin_client.get(reverse("kunden:auskunft", args=["109"]))
    text = pdf_text(antwort)
    assert "Wartezeit aufs Handy" in text and "Gerät" in text
