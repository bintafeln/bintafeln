import datetime as dt
from decimal import Decimal

import pytest
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
    gruppe = Kundengruppe.objects.create(kuerzel="X", name="Jeden Tag", ausgabestelle=stelle)
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


# --- Scannen ------------------------------------------------------------------------------


@pytest.mark.parametrize("eingabe", ["00042", "42", " 042 "])
def test_scannen_findet_auch_ohne_fuehrende_nullen(ausgabe, haushalt, eingabe):
    antwort = ausgabe.get(EMPFANG, {"nummer": eingabe}, **HX)
    inhalt = antwort.content.decode()
    assert "<h1>" not in inhalt  # nur die Ergebniskarte
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
    assert "<h1>Einlass</h1>" in inhalt and "Abholung möglich" in inhalt


def test_kontostand_abschaltbar(ausgabe, haushalt):
    e = AusgabeEinstellungen.laden()
    e.kontostand_anzeigen = False
    e.save()
    assert "Kontostand" not in ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()


def test_ausgabestelle_waehlen(ausgabe, stelle):
    url = reverse("ausgabe:ausgabestelle")
    ausgabe.post(url, {"ausgabestelle": stelle.pk})
    assert ausgabe.session["ausgabestelle_id"] == stelle.pk
    assert ausgabe.get(EMPFANG).context["stelle"] == stelle
    ausgabe.post(url, {"ausgabestelle": ""})
    assert "ausgabestelle_id" not in ausgabe.session
    assert ausgabe.get(EMPFANG).context["stelle"] is None


# --- Abholung eintragen und zurücknehmen --------------------------------------------------


def test_abholung_eintragen_mit_vorschlag(ausgabe, haushalt, stelle):
    e = AusgabeEinstellungen.laden()
    e.beitrag_je_erwachsenem = Decimal("2.50")
    e.save()
    ausgabe.post(reverse("ausgabe:ausgabestelle"), {"ausgabestelle": stelle.pk})
    vorher = ausgabe.get(EMPFANG, {"nummer": "42"}, **HX).content.decode()
    assert 'value="2,50"' in vorher
    inhalt = eintragen(ausgabe, haushalt, beitrag="").content.decode()
    assert "Abholung eingetragen." in inhalt and "Heute bereits abgeholt" in inhalt
    a = Abholung.objects.get()
    assert (a.beitrag, a.ausgabestelle, a.eingetragen_von) == (Decimal("2.50"), stelle, "ausgabe")
    assert a.erfasst_am is not None and a.datum == timezone.localdate()
    haushalt.refresh_from_db()
    assert haushalt.letzter_besuch == timezone.localdate()


def test_abholung_mit_geaendertem_beitrag(ausgabe, haushalt):
    eintragen(ausgabe, haushalt, beitrag="1,50 €")
    assert Abholung.objects.get().beitrag == Decimal("1.50")
    assert Abholung.objects.get().ausgabestelle is None


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
    assert antwort.status_code == 302 and antwort.url == f"{EMPFANG}?nummer=00042"
    assert "Abholung eingetragen." in ausgabe.get(antwort.url).content.decode()


def test_zuruecknehmen(ausgabe, haushalt):
    frueher = timezone.localdate() - dt.timedelta(days=30)
    Abholung.objects.create(haushalt=haushalt, datum=frueher)
    eintragen(ausgabe, haushalt)
    heute = Abholung.objects.get(erfasst_am__isnull=False)
    inhalt = ausgabe.post(reverse("ausgabe:zuruecknehmen", args=[heute.pk]), **HX).content.decode()
    assert "Abholung zurückgenommen." in inhalt and "Abholung möglich" in inhalt
    haushalt.refresh_from_db()
    assert haushalt.letzter_besuch == frueher
    # Importierte Abholungen lassen sich nicht zurücknehmen.
    alte = Abholung.objects.get()
    assert ausgabe.post(reverse("ausgabe:zuruecknehmen", args=[alte.pk])).status_code == 404


def test_zuruecknehmen_der_einzigen_abholung(ausgabe, haushalt):
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
    assert "Kunde anmelden und Abholung buchen" in inhalt
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
    assert "Ausgabe und Ampel" in admin_client.get(reverse("core:einstellungen")).content.decode()
    antwort = admin_client.post(
        url,
        {
            "max_je_tag": "2",
            "max_abholungen": "2",
            "zeitraum": "monat",
            "vorwarnung_tage": "7",
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
    inhalt = eintragen(ausgabe, haushalt).content.decode()
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
    gestern = timezone.now() - dt.timedelta(days=1)
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
