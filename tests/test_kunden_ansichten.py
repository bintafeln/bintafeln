import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Bemerkung,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Sperre,
    Zugriff,
    Zusatzfeld,
    abgelaufene_zugriffe_loeschen,
    fristen_anwenden,
)

pytestmark = pytest.mark.django_db

LISTE = reverse("kunden:uebersicht")
ZUGRIFFE = reverse("kunden:zugriffe")


def detail(nummer):
    return reverse("kunden:haushalt", args=[nummer])


@pytest.fixture
def als(client, admin, benutzer_mit_rolle, anmelden):
    def anmelden_als(rolle):
        return anmelden(client, benutzer_mit_rolle(rolle.lower(), rolle))

    return anmelden_als


@pytest.fixture
def bestand():
    """Zwei erfundene Haushalte mit allem, was die Detailseite zeigen kann."""
    heute = timezone.localdate()
    stelle = Ausgabestelle.objects.create(name="Ausgabestelle Mitte")
    gruppe = Kundengruppe.objects.create(kuerzel="MO1", name="Montag früh", ausgabestelle=stelle)
    andere = Kundengruppe.objects.create(kuerzel="DI1", name="Dienstag")
    Zusatzfeld.objects.create(
        schluessel="schwerbehindert",
        bezeichnung="Schwerbehindert",
        gilt_fuer=Zusatzfeld.GiltFuer.PERSON,
        typ=Zusatzfeld.Typ.JA_NEIN,
        besondere_kategorie=True,
    )
    Zusatzfeld.objects.create(
        schluessel="hinweis",
        bezeichnung="Hinweis Haushalt",
        gilt_fuer=Zusatzfeld.GiltFuer.HAUSHALT,
        typ=Zusatzfeld.Typ.TEXT,
    )
    h = Haushalt.objects.create(
        kundennummer="1001",
        kundengruppe=gruppe,
        ausweis_gueltig_bis=heute - dt.timedelta(days=1),
        strasse="Musterweg 1",
        plz="12345",
        ort="Musterstadt",
        telefon="0000 111111",
        kontostand=Decimal("1.50"),
        zusatz={"hinweis": "bringt eigene Taschen"},
    )
    Person.objects.create(
        haushalt=h,
        ist_hauptperson=True,
        vorname="Erika",
        nachname="Mustermann",
        geburtsdatum=dt.date(1968, 3, 12),
        zusatz={"schwerbehindert": True},
    )
    Person.objects.create(
        haushalt=h, vorname="Kim", nachname="Mustermann", geburtsdatum=dt.date(2015, 1, 1)
    )
    h.abholer.create(vorname="Max", nachname="Beispiel", eigene_kundennummer="1002")
    Sperre.objects.create(haushalt=h, von=heute - dt.timedelta(days=3), begruendung="aktiv")
    Sperre.objects.create(
        haushalt=h, von=dt.date(2020, 1, 1), bis=dt.date(2020, 2, 1), begruendung="Alte Sperre"
    )
    Ausnahme.objects.create(haushalt=h, datum=heute, begruendung="Arzttermin")
    Bemerkung.objects.create(haushalt=h, datum=heute, text="Interne Notiz")
    for tage in range(8):
        Abholung.objects.create(
            haushalt=h,
            datum=heute - dt.timedelta(days=7 * tage),
            uhrzeit=dt.time(12, 30),
            beitrag=Decimal("2.00"),
            ausgabestelle=stelle,
            eingetragen_von="Ausgabe Musterstadt",
        )
    zweiter = Haushalt.objects.create(kundennummer="1002", kundengruppe=andere, status="pausiert")
    Person.objects.create(
        haushalt=zweiter, ist_hauptperson=True, vorname="Max", nachname="Beispiel"
    )
    return h


# --- Rechte und Menü ----------------------------------------------------------------------


def test_kiosk_hat_keinen_zugriff(als, bestand):
    client = als(rollen.KIOSK)
    assert client.get(LISTE).status_code == 403
    assert client.get(detail("1001")).status_code == 403
    assert "Kunden einsehen</a>" not in client.get("/").content.decode()


def test_ausgabe_sieht_liste_aber_nicht_import(als, bestand):
    client = als(rollen.AUSGABE)
    assert "Kunden einsehen</a>" in client.get("/").content.decode()
    inhalt = client.get(LISTE).content.decode()
    assert ">Mustermann</a>" in inhalt and ">Erika</a>" in inhalt
    assert "Neuen Stand importieren" not in inhalt


@pytest.mark.parametrize("rolle", [rollen.BUERO, rollen.AUSGABE])
def test_zugriffsprotokoll_nur_admin(als, rolle):
    assert als(rolle).get(ZUGRIFFE).status_code == 403


# --- Liste und Suche ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("parameter", "erwartet"),
    [
        ({}, {"1001", "1002"}),
        ({"q": "erika muster"}, {"1001"}),
        ({"q": "100"}, {"1001", "1002"}),
        ({"q": "Kim"}, {"1001"}),
        ({"q": "niemand"}, set()),
        ({"status": "pausiert"}, {"1002"}),
        ({"status": "unbekannt"}, {"1001", "1002"}),
        ({"gruppe": "x"}, {"1001", "1002"}),
    ],
)
def test_suche_und_filter(admin_client, bestand, parameter, erwartet):
    antwort = admin_client.get(LISTE, parameter)
    assert antwort.status_code == 200
    gefunden = {h.kundennummer for h in antwort.context["seite"]}
    assert gefunden == erwartet


def test_filter_kundengruppe(admin_client, bestand, gruppe_behalten):
    antwort = admin_client.get(LISTE, {"gruppe": bestand.kundengruppe.pk})
    assert [h.kundennummer for h in antwort.context["seite"]] == ["1001"]


def test_genaue_kundennummer_oeffnet_haushalt(admin_client, bestand):
    antwort = admin_client.get(LISTE, {"q": "1001"})
    assert antwort.status_code == 302 and antwort.url == detail("1001")


def test_htmx_liefert_nur_die_liste(admin_client, bestand):
    antwort = admin_client.get(
        LISTE, {"q": "1001"}, HTTP_HX_REQUEST="true", HTTP_HX_TARGET="kunden-liste"
    )
    assert antwort.status_code == 200
    inhalt = antwort.content.decode()
    assert "<h1>" not in inhalt and ">Mustermann</a>" in inhalt


def test_liste_blaettert(admin_client):
    Haushalt.objects.bulk_create(Haushalt(kundennummer=f"{n:04d}") for n in range(55))
    inhalt = admin_client.get(LISTE).content.decode()
    assert "Seite 1 von 2" in inhalt and "55 Haushalte" in inhalt
    assert "Seite 2 von 2" in admin_client.get(LISTE, {"seite": 2}).content.decode()


def test_liste_kennzeichnet_abgelaufenen_ausweis(admin_client, bestand):
    inhalt = admin_client.get(LISTE).content.decode()
    assert '<span class="marke-warnung">pausiert</span>' in inhalt
    assert f'<span class="marke-warnung">{bestand.ausweis_gueltig_bis:%d.%m.%Y}</span>' in inhalt


# --- Detailansicht ------------------------------------------------------------------------


def test_buero_sieht_alles_und_zugriff_wird_protokolliert(als, bestand):
    client = als(rollen.BUERO)
    inhalt = client.get(detail("1001")).content.decode()
    for text in (
        "Musterweg 1",
        "0000 111111",
        "1,50 €",
        "Interne Notiz",
        "Max Beispiel",
        "Alte Sperre",
        "Arzttermin",
        "Schwerbehindert: ja",
        "bringt eigene Taschen",
        "Ausweis abgelaufen",
        "Gesperrt seit",
        "1 Erwachsene, 1 Kind",
    ):
        assert text in inhalt, text
    assert inhalt.count("Ausgabe Musterstadt") == 8
    assert "gespeicherten Abholungen" not in inhalt  # alle 8 sichtbar
    zugriff = Zugriff.objects.get()
    assert (zugriff.benutzername, zugriff.kundennummer) == ("büro", "1001")
    assert zugriff.besondere_kategorie is True
    assert "Zugriffe auf diesen Haushalt" not in inhalt


def test_ausgabe_sieht_nur_das_noetige(als, bestand, recht_nehmen):
    recht_nehmen(rollen.AUSGABE, "einlass.nutzen")  # sonst geht es gleich zum Einlass
    client = als(rollen.AUSGABE)
    inhalt = client.get(detail("1001")).content.decode()
    for text in (
        "Musterweg 1",
        "0000 111111",
        "Interne Notiz",
        "Alte Sperre",
        "Arzttermin",  # Ausnahmen
        "Schwerbehindert",
    ):
        assert text not in inhalt, text
    assert "bringt eigene Taschen" in inhalt and "Gesperrt seit" in inhalt
    # Hauptperson und Abholberechtigte mit Geburtsdatum, Kontostand, Karte, Notizen
    assert "12.03.1968" in inhalt and "Max Beispiel" in inhalt and "Abholberechtigt" in inhalt
    assert "1,50 €" in inhalt and "Karte gültig bis" in inhalt and "Eigene Notiz" in inhalt
    assert "Kim Mustermann" in inhalt and "01.01.2015" in inhalt and "Erwachsene" in inhalt
    assert "5 von 8 gespeicherten Abholungen" in inhalt
    assert Zugriff.objects.get().besondere_kategorie is False


def test_ausgabe_mit_freigabe_fuer_besondere_kategorie(als, bestand, recht_geben, recht_nehmen):
    recht_geben(rollen.AUSGABE, "kunden.besondere_kategorie")
    recht_nehmen(rollen.AUSGABE, "einlass.nutzen")
    inhalt = als(rollen.AUSGABE).get(detail("1001")).content.decode()
    assert "Schwerbehindert: ja" in inhalt
    assert Zugriff.objects.get().besondere_kategorie is True


def test_ausgabestelle_geht_gleich_zum_einlass(als, bestand, admin, anmelden):
    from django.test import Client

    ausgabe = als(rollen.AUSGABE)
    antwort = ausgabe.get(detail("1001"))
    assert antwort.url == "/ausgabe/?nummer=1001"
    # Der Link „Alle Angaben zum Haushalt“ am Einlass führte nur im Kreis: nicht anzeigen
    assert "Alle Angaben zum Haushalt" not in ausgabe.get(antwort.url).content.decode()
    verwaltung = anmelden(Client(), admin)
    assert verwaltung.get(detail("1001")).status_code == 200  # Verwaltung: Haushaltsseite
    assert "Alle Angaben zum Haushalt" in verwaltung.get(antwort.url).content.decode()


def test_abgeschaltete_felder_werden_nicht_angezeigt(admin_client, bestand):
    e = KundenEinstellungen.laden()
    e.telefon_erfassen = False
    e.save()
    inhalt = admin_client.get(detail("1001")).content.decode()
    assert "0000 111111" not in inhalt
    assert "Zugriffe auf diesen Haushalt" in inhalt


def test_haushalt_ohne_besondere_angaben(admin_client):
    h = Haushalt.objects.create(kundennummer="AB/7")
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Alex", nachname="Probe")
    antwort = admin_client.get(detail("AB/7"))
    assert antwort.status_code == 200
    inhalt = antwort.content.decode()
    assert "Keine Sperren." in inhalt and "Keine Abholungen." in inhalt
    assert "Ausweis abgelaufen" not in inhalt
    assert Zugriff.objects.get().besondere_kategorie is False


def test_unbekannte_kundennummer(admin_client):
    assert admin_client.get(detail("999")).status_code == 404
    assert not Zugriff.objects.exists()


# --- Zugriffsprotokoll --------------------------------------------------------------------


def test_zugriffsprotokoll_filtern(admin_client, bestand):
    Zugriff.objects.create(benutzername="büro", kundennummer="1001")
    Zugriff.objects.create(benutzername="ausgabe", kundennummer="1002")
    alle = admin_client.get(ZUGRIFFE)
    assert len(alle.context["seite"]) == 2 and "nach 365 Tagen" in alle.content.decode()
    nach_nummer = admin_client.get(ZUGRIFFE, {"kundennummer": "1002"}).context["seite"]
    assert [z.benutzername for z in nach_nummer] == ["ausgabe"]
    nach_name = admin_client.get(ZUGRIFFE, {"benutzer": "BÜRO"}).context["seite"]
    assert [z.kundennummer for z in nach_name] == ["1001"]


def test_zugriffe_nach_frist_geloescht():
    alt = Zugriff.objects.create(benutzername="x", kundennummer="1")
    Zugriff.objects.filter(pk=alt.pk).update(zeitpunkt=timezone.now() - dt.timedelta(days=366))
    Zugriff.objects.create(benutzername="x", kundennummer="2")
    assert abgelaufene_zugriffe_loeschen() == 1
    assert list(Zugriff.objects.values_list("kundennummer", flat=True)) == ["2"]
    assert fristen_anwenden() == 0
    assert str(Zugriff.objects.get()) == "Zugriff auf 2 durch x"


# --- Anzeige von Zusatzfeldern ------------------------------------------------------------


@pytest.mark.parametrize(
    ("typ", "wert", "anzeige"),
    [
        (Zusatzfeld.Typ.JA_NEIN, True, "ja"),
        (Zusatzfeld.Typ.JA_NEIN, False, "nein"),
        (Zusatzfeld.Typ.JA_NEIN, None, ""),
        (Zusatzfeld.Typ.DATUM, "2026-05-04", "04.05.2026"),
        (Zusatzfeld.Typ.DATUM, "kaputt", "kaputt"),
        (Zusatzfeld.Typ.TEXT, "", ""),
        (Zusatzfeld.Typ.AUSWAHL, "vegetarisch", "vegetarisch"),
    ],
)
def test_wert_anzeigen(typ, wert, anzeige):
    assert Zusatzfeld(typ=typ).wert_anzeigen(wert) == anzeige
