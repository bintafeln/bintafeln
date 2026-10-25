"""Sonderaktionen (ADR 0032). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe import sonderaktionen
from apps.ausgabe.models import Sonderaktion, SonderaktionAuswahl, Teilnahme
from apps.konten import rollen
from apps.kunden.models import Haushalt, KundenEinstellungen, Person

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}
HEUTE = dt.date(2026, 12, 10)


@pytest.fixture
def h():
    h = Haushalt.objects.create(kundennummer="4711")
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Probe",
                          geburtsdatum=dt.date(1980, 1, 1))  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Mia", nachname="Probe",
                          geburtsdatum=dt.date(2018, 5, 5))  # fmt: skip
    Person.objects.create(haushalt=h, vorname="Tim", nachname="Probe",
                          geburtsdatum=dt.date(2020, 6, 6))  # fmt: skip
    return h


def aktion(heute=None, **mehr):
    heute = heute or timezone.localdate()
    daten = {"bezeichnung": "Weihnachtsgutschein", "von": heute - dt.timedelta(days=3),
             "bis": heute + dt.timedelta(days=3), **mehr}  # fmt: skip
    return Sonderaktion.objects.create(**daten)


def test_menge():
    a = Sonderaktion(menge=Sonderaktion.Menge.EINMAL)
    assert sonderaktionen.menge(a, 2, 3) == 1
    a.menge = Sonderaktion.Menge.JE_KIND
    assert sonderaktionen.menge(a, 2, 3) == 3
    a.menge = Sonderaktion.Menge.JE_PERSON
    assert sonderaktionen.menge(a, 2, 3) == 5


def test_eintragen_regeln(h):
    a = aktion(HEUTE, menge="je_kind", nur_mit_kindern=True)
    spielzeug = SonderaktionAuswahl.objects.create(aktion=a, bezeichnung="Spielzeug")
    kw = {"erwachsene": 1, "kinder": 2, "stelle": None, "von": "anton", "heute": HEUTE}
    with pytest.raises(sonderaktionen.SonderaktionFehler, match="Auswahl"):
        sonderaktionen.eintragen(a, h, auswahl=None, **kw)
    t = sonderaktionen.eintragen(a, h, auswahl=spielzeug, **kw)
    assert (t.menge, t.auswahl, t.eingetragen_von) == (2, spielzeug, "anton")
    with pytest.raises(sonderaktionen.SonderaktionFehler, match="schon eingetragen"):
        sonderaktionen.eintragen(a, h, auswahl=spielzeug, **kw)
    with pytest.raises(sonderaktionen.SonderaktionFehler, match="nur für Haushalte mit Kindern"):
        sonderaktionen.eintragen(a, h, auswahl=spielzeug, **{**kw, "kinder": 0})
    with pytest.raises(sonderaktionen.SonderaktionFehler, match="läuft heute nicht"):
        sonderaktionen.eintragen(a, h, auswahl=spielzeug, **{**kw, "heute": HEUTE.replace(day=30)})
    b = aktion(HEUTE, bezeichnung="Nur Kinder", menge="je_kind")
    with pytest.raises(sonderaktionen.SonderaktionFehler, match="bekommt dieser Haushalt nichts"):
        sonderaktionen.eintragen(b, h, auswahl=None, **{**kw, "kinder": 0})


def test_fuer_haushalt(h):
    a = aktion(HEUTE, nur_mit_kindern=True)
    aktion(HEUTE, bezeichnung="Vorbei", von=HEUTE.replace(day=1), bis=HEUTE.replace(day=2))
    liste = sonderaktionen.fuer_haushalt(h, HEUTE, 1, 0)
    assert [s["aktion"] for s in liste] == [a]
    assert liste[0]["grund"] == "Nur für Haushalte mit Kindern."
    Teilnahme.objects.create(aktion=a, kundennummer="4711")
    assert sonderaktionen.fuer_haushalt(h, HEUTE, 1, 2)[0]["teilnahme"] is not None


def test_einlass(client, admin, benutzer_mit_rolle, anmelden, h):
    a = aktion(menge="je_kind", beschreibung="Nur gegen Unterschrift")
    SonderaktionAuswahl.objects.create(aktion=a, bezeichnung="Spielzeug", reihenfolge=0)
    kleidung = SonderaktionAuswahl.objects.create(aktion=a, bezeichnung="Kleidung", reihenfolge=1)
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    seite = client.get(reverse("ausgabe:empfang"), {"nummer": "4711"}, **HX).content.decode()
    assert "Sonderaktion: Weihnachtsgutschein" in seite and "Nur gegen Unterschrift" in seite
    assert "2× Spielzeug" in seite and "2× Kleidung" in seite

    url = reverse("ausgabe:sonderaktion_eintragen", args=["4711", a.pk])
    seite = client.post(url, {"auswahl": kleidung.pk}, **HX).content.decode()
    assert "Weihnachtsgutschein (Kleidung) eingetragen: 2×." in seite
    assert "✓ Erhalten am" in seite and "Korrektur beantragen" in seite
    t = Teilnahme.objects.get()
    assert (t.kundennummer, t.menge, t.auswahl, t.eingetragen_von) == ("4711", 2, kleidung, "anton")
    seite = client.post(url, {"auswahl": kleidung.pk}, **HX).content.decode()
    assert "schon eingetragen" in seite

    # Die Ausgabe nimmt nicht selbst zurück (ADR 0035), sondern bittet darum.
    zurueck = reverse("ausgabe:teilnahme_zuruecknehmen", args=[t.pk])
    assert client.post(zurueck, **HX).status_code == 403
    wunsch = reverse("ausgabe:korrektur_beantragen", args=["teilnahme", t.pk])
    seite = client.post(wunsch, {"grund": "Versehentlich gebucht"}, **HX).content.decode()
    assert "Korrekturwunsch gesendet" in seite and "wartet auf Entscheidung" in seite
    assert Teilnahme.objects.exists()


def test_verwalten(client, admin_client, benutzer_mit_rolle, anmelden, h):
    heute = timezone.localdate()
    admin_client.post(reverse("ausgabe:sonderaktion_neu"), {
        "bezeichnung": "Schulranzen", "von": heute.isoformat(), "bis": heute.isoformat(),
        "menge": "je_kind", "nur_mit_kindern": "on", "auswahl_text": "Blau\nRot\nblau\n",
    })  # fmt: skip
    a = Sonderaktion.objects.get()
    assert [x.bezeichnung for x in a.auswahl.all()] == ["Blau", "Rot"]
    blau = a.auswahl.get(bezeichnung="Blau")
    Teilnahme.objects.create(aktion=a, kundennummer="4711", auswahl=blau, menge=2)

    seite = admin_client.get(reverse("ausgabe:sonderaktion", args=[a.pk])).content.decode()
    assert "1 Haushalt, 2 Stück" in seite and "4711" in seite
    liste = admin_client.get(reverse("ausgabe:sonderaktionen")).content.decode()
    assert "Schulranzen" in liste and "Sonderaktionen" in admin_client.get("/").content.decode()
    csv = admin_client.get(reverse("ausgabe:sonderaktion", args=[a.pk]), {"format": "csv"})
    assert "4711;Blau;2;" in csv.content.decode("utf-8-sig")

    # Auswahl umbenennen: vorhandene bleiben, entfernte verlieren nur die Zuordnung
    admin_client.post(reverse("ausgabe:sonderaktion_bearbeiten", args=[a.pk]), {
        "bezeichnung": "Schulranzen", "von": heute.isoformat(), "bis": heute.isoformat(),
        "menge": "je_kind", "auswahl_text": "Grün\nBlau",
    })  # fmt: skip
    assert [x.bezeichnung for x in a.auswahl.all()] == ["Grün", "Blau"]
    assert Teilnahme.objects.get().auswahl == blau
    ungueltig = admin_client.post(reverse("ausgabe:sonderaktion_neu"), {
        "bezeichnung": "X", "von": heute.isoformat(),
        "bis": (heute - dt.timedelta(days=1)).isoformat(), "menge": "einmal",
    })  # fmt: skip
    assert "nicht vor" in ungueltig.content.decode()

    admin_client.post(reverse("ausgabe:sonderaktion_loeschen", args=[a.pk]))
    assert not Sonderaktion.objects.exists() and not Teilnahme.objects.exists()

    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))  # derselbe Client
    assert client.get(reverse("ausgabe:sonderaktionen")).status_code == 403


def test_frist_auskunft_und_haushalt(admin_client, h, pdf_text):
    a = aktion()
    Teilnahme.objects.create(aktion=a, kundennummer="4711", menge=2)
    text = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["4711"])))
    assert "Sonderaktionen" in text and "Weihnachtsgutschein" in text

    e = KundenEinstellungen.laden()
    alt = Teilnahme.objects.create(aktion=aktion(bezeichnung="Alt"), kundennummer="4711")
    Teilnahme.objects.filter(pk=alt.pk).update(
        zeitpunkt=timezone.now() - dt.timedelta(days=366 * (e.abholungen_aufbewahren_jahre + 1))
    )
    assert sonderaktionen.fristen_anwenden() == 1

    admin_client.post(reverse("kunden:bearbeiten", args=["4711"]),
                      {"kundennummer": "4712", "status": "aktiv"})  # fmt: skip
    assert Teilnahme.objects.get().kundennummer == "4712"
    seite = admin_client.get(reverse("kunden:haushalt_loeschen", args=["4712"])).content.decode()
    assert "Teilnahmen an Sonderaktionen" in seite
    admin_client.post(reverse("kunden:haushalt_loeschen", args=["4712"]))
    assert not Teilnahme.objects.exists()
