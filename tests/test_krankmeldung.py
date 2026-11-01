"""Krankmeldung eines Kunden (ADR 0075). Nur erfundene Daten."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen
from apps.kunden import krankmeldung
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    KundenEinstellungen,
    Kundengruppe,
    Notiz,
    Person,
    fristen_anwenden,
)

pytestmark = pytest.mark.django_db
HEUTE = timezone.localdate()
EMPFANG = reverse("ausgabe:empfang")


@pytest.fixture
def h():
    stelle = Ausgabestelle.objects.create(name="Mitte")
    g = Kundengruppe.objects.create(name="Jeden Tag", ausgabestelle=stelle,
                                    wochentage="Mo, Di, Mi, Do, Fr, Sa, So")  # fmt: skip
    h = Haushalt.objects.create(kundennummer="00042", kundengruppe=g,
                                ausweis_gueltig_bis=HEUTE + dt.timedelta(days=100))  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster")
    return h


@pytest.fixture
def an():
    KundenEinstellungen.objects.update_or_create(pk=1, defaults={"krankmeldung": True})


def test_ausgeschaltet_kein_formular(h, admin_client):
    seite = admin_client.get(reverse("kunden:haushalt", args=["00042"])).content.decode()
    assert "Krank melden …" not in seite
    daten = {"krank_grund": "krank", "krank_von": HEUTE.isoformat()}
    antwort = admin_client.post(reverse("kunden:krank_neu", args=["00042"]), daten)
    assert antwort.status_code == 403 and not Notiz.objects.exists()


def test_melden_in_der_verwaltung(h, an, admin_client):
    url = reverse("kunden:haushalt", args=["00042"])
    seite = admin_client.get(url).content.decode()
    assert "Krank melden …" in seite and 'summary class="knopf knopf-vorlage"' in seite
    bis = HEUTE + dt.timedelta(days=13)
    admin_client.post(reverse("kunden:krank_neu", args=["00042"]), {
        "krank_grund": "reha", "krank_von": HEUTE.isoformat(), "krank_bis": bis.isoformat(),
        "krank_anmerkung": "Tochter holt ab"})  # fmt: skip
    n = Notiz.objects.get()
    assert (n.krank_von, n.krank_bis, n.krank_grund) == (HEUTE, bis, "reha")
    assert n.text == (f"**Krank gemeldet** (Reha) vom {HEUTE:%d.%m.%Y} bis {bis:%d.%m.%Y}.\n"
                      "Tochter holt ab")  # fmt: skip
    assert krankmeldung.aktuelle("00042") == n
    assert 'class="notiz notiz-krank"' in admin_client.get(url).content.decode()


@pytest.mark.parametrize(("daten", "fehler"), [
    ({"krank_grund": "grippe"}, "Bitte einen Grund wählen."),
    ({"krank_von": ""}, "Bitte Beginn und Ende angeben."),
    ({"krank_bis": "2000-01-01"}, "Das Ende liegt vor dem Beginn."),
    ({"krank_von": "2000-01-01", "krank_bis": "2000-01-02"}, "Das Ende liegt in der Vergangenh"),
    ({"krank_bis": "2099-01-01"}, "Höchstens 365 Tage."),
])  # fmt: skip
def test_falsche_angaben(h, an, admin_client, daten, fehler):
    post = {"krank_grund": "krank", "krank_von": HEUTE.isoformat(), **daten}
    antwort = admin_client.post(reverse("kunden:krank_neu", args=["00042"]), post, follow=True)
    assert fehler in antwort.content.decode() and not Notiz.objects.exists()


def test_einlass_zeigt_und_meldet(h, an, client, admin, benutzer_mit_rolle, anmelden):
    anmelden(client, benutzer_mit_rolle("ausgabe", rollen.AUSGABE))
    seite = client.post(reverse("ausgabe:krank", args=["00042"]),
                        {"krank_grund": "krankenhaus", "krank_von": HEUTE.isoformat()},
                        HTTP_HX_REQUEST="true").content.decode()  # fmt: skip
    assert "Krankmeldung gespeichert." in seite
    assert "<strong>Krank gemeldet</strong> (Krankenhaus)" in seite
    assert f"bis {HEUTE:%d.%m.%Y}. Abholen darf nur" in seite
    fehler = client.post(reverse("ausgabe:krank", args=["00042"]), {"krank_grund": "x"},
                         HTTP_HX_REQUEST="true").content.decode()  # fmt: skip
    assert "Bitte einen Grund wählen." in fehler


def test_nach_dem_ende_weg(h, an, admin_client):
    alt = Notiz.objects.create(kundennummer="00042", text="krank", krank_grund="krank",
                               krank_von=HEUTE - dt.timedelta(days=9),
                               krank_bis=HEUTE - dt.timedelta(days=1))  # fmt: skip
    Notiz.objects.create(kundennummer="00042", text="Bringt Bescheid")
    seite = admin_client.get(reverse("kunden:haushalt", args=["00042"])).content.decode()
    assert "Bringt Bescheid" in seite and "notiz-krank" not in seite
    assert krankmeldung.aktuelle("00042") is None
    fristen_anwenden()
    assert not Notiz.objects.filter(pk=alt.pk).exists()
    assert Notiz.objects.filter(text="Bringt Bescheid").exists()


def test_faellt_weg_wenn_kunde_wieder_kommt(h, an, admin):
    """Kommt der Kunde innerhalb der laufenden Zeit, ist er offenbar nicht mehr krank: Die
    Meldung wird nicht mehr angezeigt und beim täglichen Lauf gelöscht."""
    from apps.kunden.models import Abholung

    n = krankmeldung.melden(h, admin, HEUTE - dt.timedelta(days=2), HEUTE + dt.timedelta(days=5),
                            "krank")  # fmt: skip
    assert krankmeldung.aktuelle("00042") == n
    # Abholung vor dem Beginn zählt nicht.
    Abholung.objects.create(haushalt=h, datum=HEUTE - dt.timedelta(days=4))
    assert krankmeldung.aktuelle("00042") == n
    # Abholung ab dem Beginn hebt die Meldung auf.
    Abholung.objects.create(haushalt=h, datum=HEUTE)
    assert krankmeldung.aktuelle("00042") is None
    fristen_anwenden()
    assert not Notiz.objects.filter(pk=n.pk).exists()
