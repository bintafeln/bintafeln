import datetime as dt
import re
from decimal import Decimal
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe.models import AusgabeEinstellungen
from apps.konten import rollen
from apps.kunden import importieren
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Haushalt,
    Kundengruppe,
    Person,
    Zugriff,
)

pytestmark = pytest.mark.django_db

KOPF = '<h1>Kunde 00042 <span class="einlass-name">Erika Muster</span>'  # Name groß daneben
EMPFANG = reverse("ausgabe:empfang")
HX = {"HTTP_HX_REQUEST": "true"}


@pytest.fixture
def als(client, admin, benutzer_mit_rolle, anmelden):
    def anmelden_als(rolle):
        return anmelden(client, benutzer_mit_rolle(rolle.lower(), rolle))

    return anmelden_als


@pytest.fixture
def ausgabe(als):
    return als(rollen.AUSGABE)


@pytest.fixture
def stelle():
    return Ausgabestelle.objects.create(name="Ausgabestelle Mitte")


@pytest.fixture
def haushalt(stelle):
    """Erfundener Haushalt, heute dran, Ausweis gültig."""
    heute = timezone.localdate()
    gruppe = Kundengruppe.objects.create(kuerzel="X", name="Jeden Tag", ausgabestelle=stelle,
                                         wochentage="Mo, Di, Mi, Do, Fr, Sa, So")  # fmt: skip
    h = Haushalt.objects.create(
        kundennummer="00042",
        kundengruppe=gruppe,
        ausweis_gueltig_bis=heute + dt.timedelta(days=100),
        kontostand=Decimal("6.00"),
    )
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster")
    return h


def eintragen(client, h, **daten):
    daten.setdefault("bar", "0")  # Pflichtfeld: was bar auf dem Tisch liegt
    return client.post(reverse("ausgabe:eintragen", args=[h.kundennummer]), daten, **HX)


# --- Rechte und Menü ----------------------------------------------------------------------


def test_kiosk_kein_zugriff(als):
    client = als(rollen.KIOSK)
    assert client.get(EMPFANG).status_code == 403
    assert "Einlass</a>" not in client.get("/").content.decode()


def test_ausgabe_sieht_empfang(ausgabe, stelle):
    assert "Einlass</a>" in ausgabe.get("/").content.decode()
    inhalt = ausgabe.get(EMPFANG).content.decode()
    assert "Kundennummer scannen" in inhalt and "Ausgabestelle Mitte" in inhalt


def test_kamera_scanner_eingebunden(ausgabe, stelle):
    """Kamera-Knopf und mitgelieferter Barcode-Leser, ohne Zugriff auf fremde Server."""
    from django.contrib.staticfiles import finders

    inhalt = ausgabe.get(EMPFANG).content.decode()
    assert 'data-kamera="kamera"' in inhalt and 'id="kamera-dialog"' in inhalt
    for datei in [
        "js/kamera_scanner.js",
        "vendor/barcode-detector/ponyfill.js",
        "vendor/barcode-detector/zxing_reader.wasm",
    ]:
        assert f"/static/{datei}" in inhalt
        assert finders.find(datei)
    skript = Path(finders.find("js/kamera_scanner.js")).read_text(encoding="utf-8")
    assert not re.search(r"https?://", skript)  # keine fremden Adressen


def test_kamera_verweist_im_heimnetz_auf_https(ausgabe, settings):
    """Über http fragt der Browser nicht nach der Kamera; im Heimnetz gibt es https (ADR 0041)."""
    assert "data-kamera-https" not in ausgabe.get(EMPFANG).content.decode()
    settings.HEIMNETZ_ADRESSE = "192.0.2.10"
    inhalt = ausgabe.get(EMPFANG).content.decode()
    assert 'data-kamera-https="https://192.0.2.10/ausgabe/"' in inhalt
    assert "Erneut versuchen" in inhalt
    assert "data-kamera-https" not in ausgabe.get(EMPFANG, secure=True).content.decode()


# --- Scannen ------------------------------------------------------------------------------


@pytest.mark.parametrize("eingabe", ["00042", "42", " 042 "])
def test_scannen_findet_auch_ohne_fuehrende_nullen(ausgabe, haushalt, eingabe):
    antwort = ausgabe.get(EMPFANG, {"nummer": eingabe}, **HX)
    inhalt = antwort.content.decode()
    # Mit Kunde nur dessen Angaben, kein Suchfeld darüber (ADR 0039)
    assert KOPF in inhalt and 'name="nummer"' not in inhalt
    assert "Abholung eintragen" in inhalt and "Abbrechen" in inhalt and "<html" not in inhalt
    assert "Abholung möglich" in inhalt and "Erika Muster" in inhalt
    assert "6,00 €" in inhalt
    assert Zugriff.objects.get().kundennummer == "00042"


@pytest.mark.parametrize("eingabe", ["999", "ABC"])
def test_unbekannte_nummer(ausgabe, haushalt, eingabe):
    inhalt = ausgabe.get(EMPFANG, {"nummer": eingabe}, **HX).content.decode()
    assert "nicht gefunden" in inhalt
    assert not Zugriff.objects.exists()


def test_ohne_htmx_ganze_seite(ausgabe, haushalt):
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}).content.decode()
    assert KOPF in inhalt and "Abholung möglich" in inhalt
    assert 'name="nummer"' not in inhalt
    assert "<h1>Einlass</h1>" in ausgabe.get(EMPFANG).content.decode()


def test_kontostand_abschaltbar(ausgabe, haushalt):
    e = AusgabeEinstellungen.laden()
    e.kontostand_anzeigen = False
    e.save()
    assert "Kontostand" not in ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()


def test_ausgabestelle_waehlen(ausgabe, stelle):
    """Auswahl oben im Menü, gespeichert am Benutzer (ADR 0067)."""
    nord = Ausgabestelle.objects.create(name="Nord")
    url = reverse("ausgabe:ausgabestelle")
    assert ausgabe.get(EMPFANG).context["stelle"] is None  # zwei Stellen: erst wählen
    seite = ausgabe.get(EMPFANG).content.decode()
    assert 'id="menue-stelle"' in seite and "Bitte oben im Menü die Ausgabestelle wählen" in seite
    antwort = ausgabe.post(url, {"ausgabestelle": nord.pk, "weiter": "/kunden/"})
    assert antwort.url == "/kunden/"
    assert ausgabe.get(EMPFANG).context["stelle"] == nord
    konto = get_user_model().objects.get(username="ausgabe")
    assert konto.gewaehlte_stelle == nord  # bleibt über die Anmeldung hinaus
    assert ausgabe.post(url, {"ausgabestelle": stelle.pk, "weiter": "https://fremd.example/"}
                        ).url == EMPFANG  # fmt: skip
    ausgabe.post(url, {"ausgabestelle": ""})
    assert ausgabe.get(EMPFANG).context["stelle"] is None


def test_ausgabestelle_nur_aus_den_eigenen(als, admin, stelle, benutzer_mit_rolle, anmelden):
    nord = Ausgabestelle.objects.create(name="Nord")
    konto = benutzer_mit_rolle("mitte", rollen.AUSGABE)
    konto.ausgabestellen.set([stelle])
    c = anmelden(Client(), konto)
    c.post(reverse("ausgabe:ausgabestelle"), {"ausgabestelle": nord.pk})
    assert c.get(EMPFANG).context["stelle"] == stelle  # einzige eigene, ohne Auswahlfeld
    seite = c.get(EMPFANG).content.decode()
    assert 'id="menue-stelle"' not in seite and "<strong>Ausgabestelle Mitte</strong>" in seite


def test_fortschritt_in_der_kopfzeile(ausgabe, haushalt, stelle):
    """3/236: heute an der Stelle abgeholt / planmäßig heute erwartet."""
    seite = ausgabe.get(EMPFANG).content.decode()
    assert '"fortschritt-blase"><span class="fortschritt-zahl">0/1</span>' in seite
    assert "<strong>0 von 1 möglichen Haushalten haben heute schon abgeholt.</strong>" in seite
    inhalt = eintragen(ausgabe, haushalt).content.decode()
    assert 'hx-swap-oob="true"' in inhalt and ">1/1</span>" in inhalt
    # Ausnahmen zählen vorne mit, hinten nur planmäßige Haushalte
    andere = Kundengruppe.objects.create(name="Nie", ausgabestelle=stelle, wochentage="")
    gast = Haushalt.objects.create(kundennummer="00077", kundengruppe=andere)
    Abholung.objects.create(haushalt=gast, datum=timezone.localdate(), ausgabestelle=stelle)
    assert ">2/1</span>" in ausgabe.get(EMPFANG).content.decode()


def test_fortschritt_zaehlt_alle_gruppen_des_tages(ausgabe, haushalt, stelle):
    """Alle Kundengruppen der Stelle mit heutigem Ausgabetag zählen zusammen, auch wenn der Tag
    ausgeschrieben ist („Montag“) oder klein („mo“)."""
    tag = ["Montag", "di", "Mi.", "Do", "Freitag", "sa", "So"][timezone.localdate().weekday()]
    zweite = Kundengruppe.objects.create(name="Zweite", ausgabestelle=stelle, wochentage=tag)
    Haushalt.objects.create(kundennummer="00078", kundengruppe=zweite)
    seite = ausgabe.get(EMPFANG).content.decode()
    assert ">0/2</span>" in seite and "Zweite" in seite


def test_fortschritt_nur_am_ausgabetag(ausgabe, stelle):
    Kundengruppe.objects.create(name="Nie", ausgabestelle=stelle, wochentage="")
    seite = ausgabe.get(EMPFANG).content.decode()
    assert 'id="ausgabe-fortschritt" class="kopf-fortschritt" hidden' in seite


def test_ohne_einlass_keine_auswahl(admin, benutzer_mit_rolle, anmelden, stelle):
    Ausgabestelle.objects.create(name="Nord")
    c = anmelden(Client(), benutzer_mit_rolle("fahrer", rollen.FAHRER))
    seite = c.get(reverse("core:start")).content.decode()
    assert 'id="menue-stelle"' not in seite and "ausgabe-fortschritt" not in seite


# --- Abholung eintragen und zurücknehmen --------------------------------------------------


def test_abholung_eintragen_mit_vorschlag(ausgabe, haushalt, stelle):
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_person = Decimal("2.50")
    e.save()
    ausgabe.post(reverse("ausgabe:ausgabestelle"), {"ausgabestelle": stelle.pk})
    vorher = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert 'value="2,50"' in vorher
    inhalt = eintragen(ausgabe, haushalt, beitrag="").content.decode()
    # Danach zurück zur Suche, mit Meldung und Link zurück zum Kunden
    assert "Kunde 00042: Abholung eingetragen." in inhalt and 'name="nummer"' in inhalt
    assert "Kunde 00042 wieder öffnen" in inhalt and "<h1>Einlass</h1>" in inhalt
    wieder = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert "Heute bereits abgeholt" in wieder and "Abholung eintragen" not in wieder
    assert "Zur Suche" in wieder
    a = Abholung.objects.get()
    assert (a.beitrag, a.ausgabestelle, a.eingetragen_von) == (Decimal("2.50"), stelle, "ausgabe")
    assert a.erfasst_am is not None and a.datum == timezone.localdate()
    haushalt.refresh_from_db()
    assert haushalt.letzter_besuch == timezone.localdate()


def test_abholung_mit_geaendertem_beitrag(ausgabe, haushalt):
    eintragen(ausgabe, haushalt, beitrag="1,50 €")
    assert Abholung.objects.get().beitrag == Decimal("1.50")
    # Gibt es nur eine Ausgabestelle, gilt sie ohne Wahl (ADR 0067)
    assert Abholung.objects.get().ausgabestelle == haushalt.kundengruppe.ausgabestelle


def test_ungueltiger_beitrag(ausgabe, haushalt):
    inhalt = eintragen(ausgabe, haushalt, beitrag="viel").content.decode()
    assert "Beitrag ist kein Betrag" in inhalt and not Abholung.objects.exists()


def test_bei_rot_wird_nichts_eingetragen(ausgabe, haushalt):
    eintragen(ausgabe, haushalt)
    inhalt = eintragen(ausgabe, haushalt).content.decode()
    assert "Ampel steht auf Rot" in inhalt and Abholung.objects.count() == 1


def test_ohne_htmx_weiterleitung_mit_meldung(ausgabe, haushalt):
    url = reverse("ausgabe:eintragen", args=["00042"])
    antwort = ausgabe.post(url, {"beitrag": "0", "bar": "0"})
    assert antwort.status_code == 302 and antwort.url == EMPFANG
    inhalt = ausgabe.get(antwort.url).content.decode()
    assert "Kunde 00042: Abholung eingetragen." in inhalt and 'name="nummer"' in inhalt


def test_zuruecknehmen(ausgabe, haushalt, recht_geben):
    recht_geben(rollen.AUSGABE, "einlass.zuruecknehmen")
    frueher = timezone.localdate() - dt.timedelta(days=30)
    Abholung.objects.create(haushalt=haushalt, datum=frueher)
    eintragen(ausgabe, haushalt)
    heute = Abholung.objects.get(erfasst_am__isnull=False)
    inhalt = ausgabe.post(reverse("ausgabe:zuruecknehmen", args=[heute.pk]), **HX).content.decode()
    assert "Abholung zurückgenommen." in inhalt and "Abholung möglich" in inhalt
    haushalt.refresh_from_db()
    assert haushalt.letzter_besuch == frueher
    # Mit dem Recht auch an späteren Tagen
    alte = Abholung.objects.get()
    ausgabe.post(reverse("ausgabe:zuruecknehmen", args=[alte.pk]), **HX)
    assert not Abholung.objects.exists()


def test_zuruecknehmen_der_einzigen_abholung(ausgabe, haushalt, recht_geben):
    recht_geben(rollen.AUSGABE, "einlass.zuruecknehmen")
    eintragen(ausgabe, haushalt)
    ausgabe.post(reverse("ausgabe:zuruecknehmen", args=[Abholung.objects.get().pk]), **HX)
    haushalt.refresh_from_db()
    assert haushalt.letzter_besuch is None


# --- Ausnahme ----------------------------------------------------------------------------


@pytest.fixture
def nicht_dran(haushalt):
    gestern = timezone.localdate() - dt.timedelta(days=1)
    haushalt.kundengruppe.wochentage = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"][gestern.weekday()]
    haushalt.kundengruppe.save()
    return haushalt


def test_buero_erteilt_ausnahme(als, nicht_dran):
    buero = als(rollen.BUERO)
    vorher = buero.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert "Keine Abholung" in vorher and "Ausnahme erteilen" in vorher
    url = reverse("ausgabe:ausnahme", args=["00042"])
    assert "Begründung angeben" in buero.post(url, {"begruendung": " "}, **HX).content.decode()
    inhalt = buero.post(url, {"begruendung": "Termin verlegt"}, **HX).content.decode()
    assert "Ausnahme für heute erteilt: Termin verlegt" in inhalt
    assert "Abholung eintragen" in inhalt
    assert Ausnahme.objects.get().eingetragen_von == "büro"


def test_ausgabe_darf_keine_ausnahme(ausgabe, nicht_dran):
    assert "Ausnahme erteilen" not in ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    url = reverse("ausgabe:ausnahme", args=["00042"])
    assert ausgabe.post(url, {"begruendung": "x"}).status_code == 403


# --- Einstellungen -----------------------------------------------------------------------


def test_einstellungen_nur_admin(ausgabe):
    assert ausgabe.get(reverse("ausgabe:einstellungen")).status_code == 403


def test_einstellungen_speichern(admin_client):
    url = reverse("ausgabe:einstellungen")
    seite = admin_client.get(reverse("core:einstellungen")).content.decode()
    assert "Ausgabe, Ampel und Beiträge" in seite and "Beitragsfreie Zeiträume" in seite
    antwort = admin_client.post(
        url,
        {
            "max_je_tag": "2",
            "max_abholungen": "2",
            "zeitraum": "monat",
            "vorwarnung_tage": "7",
            "zahlt_ab_alter": "16",
            "beitrag_je_person": "2,00",
            "zusatzbeitraege": "on",
            "beitrag_je_abholung": "1,00",
            "beitrag_je_erwachsenem": "0",
            "beitrag_je_kind": "0",
            "buchungen_aufbewahren_jahre": "10",
        },
    )
    assert antwort.status_code == 302
    e = AusgabeEinstellungen.laden()
    assert (e.max_abholungen, e.zeitraum, e.nicht_dran_rot) == (2, "monat", False)
    assert e.max_je_tag == 2
    assert e.beitrag_je_abholung == Decimal("1.00") and not e.kontostand_anzeigen
    assert (e.zahlt_ab_alter, e.beitrag_je_person, e.zusatzbeitraege) == (16, Decimal("2"), True)
    assert admin_client.post(url, {"max_abholungen": "32"}).status_code == 200


# --- Import warnt vor dem Verlust erfasster Daten -----------------------------------------


def test_import_warnt_vor_verlust_erfasster_abholungen(ausgabe, haushalt):
    eintragen(ausgabe, haushalt)
    Ausnahme.objects.create(haushalt=haushalt, datum=timezone.localdate())
    ergebnis = importieren.pruefen(
        {"haushalte.csv": b"kundennummer;nachname;vorname\n00042;Muster;Erika\n"}
    )
    texte = [(m["datei"], m["text"]) for m in ergebnis.warnungen]
    assert (
        "abholungen.csv",
        "1 am Einlass in bintafeln erfasste Einträge werden durch den Import ersetzt und gehen "
        "verloren.",
    ) in texte
    assert not any(d == "ausnahmen.csv" and "am Einlass" in t for d, t in texte)


def test_grosse_ampel_zeigt_die_farbe(ausgabe, haushalt):
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert '<span class="lampe lampe-gruen an">' in inhalt and ">OK</p>" in inhalt
    assert '<span class="lampe lampe-rot">' in inhalt
    eintragen(ausgabe, haushalt)
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert '<span class="lampe lampe-rot an">' in inhalt and ">STOPP</p>" in inhalt
    haushalt.ausweis_gueltig_bis = timezone.localdate()
    haushalt.save()
    Abholung.objects.all().delete()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert '<span class="lampe lampe-gelb an">' in inhalt and ">ACHTUNG</p>" in inhalt


def test_einlass_zeigt_angaben_und_notizen(ausgabe, haushalt):
    from apps.kunden.models import Notiz

    hp = haushalt.personen.get()
    hp.geburtsdatum = dt.date(1970, 5, 6)
    hp.save()
    Person.objects.create(haushalt=haushalt, vorname="Kai", nachname="Muster",
                          geburtsdatum=dt.date(2016, 1, 1))  # fmt: skip
    haushalt.abholer.create(vorname="Otto", nachname="Muster", geburtsdatum=dt.date(2001, 2, 3))
    haushalt.strasse = "Erfundene Gasse 9"
    haushalt.save()
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert "Erika Muster, geb. 06.05.1970" in inhalt and "Otto Muster, geb. 03.02.2001" in inhalt
    assert "1 Erwachsene, 1 Kind" in inhalt and "Kai Muster, geb. 01.01.2016" in inhalt
    assert "Ausgabestelle Mitte · Jeden Tag" in inhalt and "Karte gültig bis" in inhalt
    assert "Erfundene Gasse" not in inhalt and "Keine Notizen." in inhalt
    url = reverse("ausgabe:notiz", args=["00042"])
    leer = ausgabe.post(url, {"text": "  "}, **HX).content.decode()
    assert "Bitte einen Text" in leer and not Notiz.objects.exists()
    inhalt = ausgabe.post(url, {"text": "Bringt Nachweis nächste Woche"}, **HX).content.decode()
    assert "Notiz gespeichert." in inhalt and "Bringt Nachweis nächste Woche" in inhalt
    assert '<div class="notiz">' in inhalt  # gespeicherte Notizen farbig hinterlegt
    n = Notiz.objects.get()
    assert n.kundennummer == "00042" and n.verfasst_von == "ausgabe"
    # eigene Notiz vom selben Tag darf die Ausgabe löschen (Versehen), fremde nicht
    assert "löschen</button>" in inhalt
    fremd = Notiz.objects.create(kundennummer="00042", text="Von Berta", verfasst_von="Berta")
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert inhalt.count("löschen</button>") == 1
    url = reverse("ausgabe:notiz_loeschen", args=[fremd.pk])
    assert "nur Büro und Admin" in ausgabe.post(url, **HX).content.decode()
    gestern = timezone.now() - dt.timedelta(days=2)  # zwei Tage: auch über eine Zeitumstellung
    Notiz.objects.filter(pk=n.pk).update(erstellt_am=gestern)
    url = reverse("ausgabe:notiz_loeschen", args=[n.pk])
    assert "nur Büro und Admin" in ausgabe.post(url, **HX).content.decode()
    Notiz.objects.filter(pk=n.pk).update(erstellt_am=timezone.now())
    assert "Notiz gelöscht." in ausgabe.post(url, **HX).content.decode()
    assert list(Notiz.objects.all()) == [fremd]


def test_notiz_vorlagen_am_einlass(als, haushalt):
    from apps.kunden.models import Notiz, NotizVorlage

    NotizVorlage.objects.create(text="Bescheide geprüft, kann verlängert werden", reihenfolge=1)
    NotizVorlage.objects.create(text="Alte Vorlage", aktiv=False)
    ausgabe = als(rollen.AUSGABE)
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert "Bescheide geprüft, kann verlängert werden</button>" in inhalt
    assert "Alte Vorlage" not in inhalt and "Notiz-Vorlagen bearbeiten" not in inhalt
    url = reverse("ausgabe:notiz", args=["00042"])
    inhalt = ausgabe.post(url, {"text": "Bescheide geprüft, kann verlängert werden"},
                          **HX).content.decode()  # fmt: skip
    assert "Notiz gespeichert." in inhalt
    assert Notiz.objects.get().text == "Bescheide geprüft, kann verlängert werden"


def test_beitrag_ab_alter_und_beitragsfrei(als, haushalt):
    from apps.ausgabe.models import BeitragsfreierZeitraum

    heute = timezone.localdate()
    hp = haushalt.personen.get()
    hp.geburtsdatum = dt.date(1980, 1, 1)
    hp.save()
    Person.objects.create(haushalt=haushalt, vorname="Teen", nachname="Muster",
                          geburtsdatum=dt.date(heute.year - 17, 1, 1))  # fmt: skip
    Person.objects.create(haushalt=haushalt, vorname="Oma", nachname="Muster")  # ohne Datum
    e = AusgabeEinstellungen.laden()
    assert e.beitrag_fuer(haushalt, heute, 18) == Decimal("3.00")  # 2 zahlen, 17-Jährige nicht
    e.zahlt_ab_alter = 16
    assert e.beitrag_fuer(haushalt, heute, 18) == Decimal("4.50")
    z = BeitragsfreierZeitraum.objects.create(bezeichnung="Weihnachten", von=heute,
                                              bis=heute + dt.timedelta(days=3))  # fmt: skip
    assert e.beitrag_fuer(haushalt, heute, 18) == Decimal("0.00")
    assert z.aktiv and str(z).startswith("Weihnachten: ")
    ausgabe = als(rollen.AUSGABE)
    inhalt = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert (
        "Heute beitragsfrei: Weihnachten" in inhalt
        and 'name="beitrag" id="beitrag" value="0,00"' in inhalt
    )


def test_beitragsfreie_zeitraeume_pflegen(admin_client):
    from apps.ausgabe.models import BeitragsfreierZeitraum

    url = reverse("kunden:listeneintrag_neu", args=["beitragsfrei"])
    falsch = admin_client.post(url, {"bezeichnung": "X", "von": "2026-12-20", "bis": "2026-12-01"})
    assert "nicht vor" in falsch.content.decode()
    admin_client.post(url, {"bezeichnung": "Weihnachten", "von": "2026-12-01", "bis": "2026-12-24"})
    assert BeitragsfreierZeitraum.objects.get().bezeichnung == "Weihnachten"
    liste = admin_client.get(reverse("kunden:liste", args=["beitragsfrei"])).content.decode()
    assert "Weihnachten</a></td>" in liste and "01.12.2026" in liste and "24.12.2026" in liste


# --- Anzeige am Einlass (je Tafel einstellbar) ------------------------------------------------


def test_einlass_anzeige_einstellbar(ausgabe, haushalt):
    from apps.kunden.models import Abholer, Sperre

    heute = timezone.localdate()
    haushalt.strasse, haushalt.plz, haushalt.ort = "Erfundene Gasse 3", "12345", "Musterstadt"
    haushalt.save()
    haushalt.kundengruppe.farbe = "blau"
    haushalt.kundengruppe.save()
    Person.objects.create(haushalt=haushalt, vorname="Mia", nachname="Muster",
                          geburtsdatum=dt.date(2015, 8, 18))  # fmt: skip
    Abholer.objects.create(haushalt=haushalt, vorname="Otto", nachname="Nachbar")
    Sperre.objects.create(haushalt=haushalt, von=heute, begruendung="erfundener Grund")

    def seite():
        return ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()

    vorher = seite()
    assert "Erwachsene" in vorher and "18.08.2015" in vorher and "Otto Nachbar" in vorher
    assert 'class="gruppe-band gruppe-blau"' in vorher and "erfundener Grund" in vorher
    assert "Letzte Abholungen" in vorher and "Erfundene Gasse" not in vorher

    e = AusgabeEinstellungen.laden()
    e.einlass_haushaltsgroesse = e.einlass_geburtsdaten = e.einlass_abholer = False
    e.einlass_sperren = e.einlass_abholungen = e.einlass_gruppenfarbe = False
    e.einlass_anschrift = True
    e.save()
    nachher = seite()
    assert "Erwachsene" not in nachher and "18.08.2015" not in nachher
    assert "Otto Nachbar" not in nachher and "gruppe-band" not in nachher
    assert "erfundener Grund" not in nachher and "Gesperrt seit" in nachher
    assert "Letzte Abholungen" not in nachher
    assert "Erfundene Gasse 3, 12345 Musterstadt" in nachher


def test_gruppenfarbe_pflegen(admin_client, stelle):
    admin_client.post(
        reverse("kunden:listeneintrag_neu", args=["kundengruppen"]),
        {"name": "Grün-Gruppe", "ausgabestelle": stelle.pk, "farbe": "gruen", "aktiv": "on"},
    )
    assert Kundengruppe.objects.get(name="Grün-Gruppe").farbe == "gruen"


def test_letzte_kunden(ausgabe, haushalt, stelle, benutzer_mit_rolle, anmelden):
    from django.test import Client

    gruppe = haushalt.kundengruppe
    zweiter = Haushalt.objects.create(kundennummer="00043", kundengruppe=gruppe,
                                      ausweis_gueltig_bis=haushalt.ausweis_gueltig_bis)  # fmt: skip
    Person.objects.create(haushalt=zweiter, ist_hauptperson=True, vorname="Max", nachname="Probe")
    assert "Letzte Kunden" not in ausgabe.get(EMPFANG).content.decode()
    ausgabe.post(reverse("ausgabe:ausgabestelle"), {"ausgabestelle": stelle.pk})
    ausgabe.get(EMPFANG, {"nummer": "42"}, **HX)
    inhalt = eintragen(ausgabe, haushalt).content.decode()  # zurück zur Suche, mit Liste
    assert "Letzte Kunden heute (1)" in inhalt and "abgeholt" in inhalt
    ausgabe.get(EMPFANG, {"nummer": "43"}, **HX)  # nur aufgerufen
    seite = ausgabe.get(EMPFANG).content.decode()
    assert "Letzte Kunden heute (2)" in seite
    assert seite.index("00043</strong> Max Probe") < seite.index("00042</strong> Erika Muster")
    assert "aufgerufen" in seite and '?nummer=00043"' in seite
    # Eine andere Person an derselben Ausgabestelle sieht die Abholung, nicht die Aufrufe
    c = anmelden(Client(), benutzer_mit_rolle("berta", rollen.AUSGABE))
    c.post(reverse("ausgabe:ausgabestelle"), {"ausgabestelle": stelle.pk})
    seite = c.get(EMPFANG).content.decode()
    assert "Letzte Kunden heute (1)" in seite and "00043" not in seite
