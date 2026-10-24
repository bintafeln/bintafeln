import datetime as dt
from decimal import Decimal as D

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.konten import personal, rollen, verwaltung
from apps.personal import arbeitszeit, berechnung
from apps.personal.forms import ZeitbuchungForm
from apps.personal.models import Arbeitsvertrag, ArbeitszeitEinstellungen, Zeitbuchung

pytestmark = pytest.mark.django_db


def zeit(tag, uhr):
    """Ortszeit am Tag `tag` (datetime.date) um `uhr` ('HH:MM')."""
    stunde, minute = map(int, uhr.split(":"))
    return dt.datetime.combine(tag, dt.time(stunde, minute), timezone.get_current_timezone())


TAG = dt.date(2026, 10, 20)


@pytest.fixture
def fest(benutzer_mit_rolle):
    b = benutzer_mit_rolle("kim", rollen.AUSGABE)
    b.beschaeftigung = b.Beschaeftigung.FEST
    b.save()
    return b


@pytest.fixture
def ehrenamt(benutzer_mit_rolle):
    return benutzer_mit_rolle("eli", rollen.AUSGABE)


def buchen(benutzer, von, bis=None, tag=TAG):
    return Zeitbuchung.objects.create(
        benutzer=benutzer, beginn=zeit(tag, von), ende=zeit(tag, bis) if bis else None
    )


def einstellen(**werte):
    e = ArbeitszeitEinstellungen.laden()
    for k, v in werte.items():
        setattr(e, k, v)
    e.save()


# --- Rechenregeln -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("zeiten", "netto", "abzug"),
    [
        ([("08:00", "14:00")], D("6"), D("0")),  # genau 6 Stunden: keine Pause nötig
        ([("08:00", "15:00")], D("6.5"), D("0.5")),
        ([("08:00", "12:00"), ("12:30", "15:00")], D("6.5"), D("0")),  # Pause gestempelt
        ([("08:00", "12:00"), ("12:10", "15:00")], D("6.5"), D("0.3333")),  # zu kurz
        ([("07:00", "17:00")], D("9.25"), D("0.75")),
    ],
)
def test_pausen_nach_arbzg(fest, zeiten, netto, abzug):
    for von, bis in zeiten:
        buchen(fest, von, bis)
    tag = berechnung.arbeitstage_aus(fest.zeitbuchungen.all())[0]
    assert round(tag.netto, 2) == round(netto, 2)
    assert round(tag.pause_abzug, 4) == abzug


def test_ohne_automatische_pause_und_offene_buchung(fest):
    buchen(fest, "07:00", "17:00")
    buchen(fest, "18:00")
    tag = berechnung.arbeitstage_aus(fest.zeitbuchungen.all(), pausen_automatisch=False)[0]
    assert (tag.netto, tag.pause_abzug, len(tag.buchungen)) == (D("10"), 0, 2)
    assert fest.zeitbuchungen.first().stunden == 0  # offen
    assert str(fest.zeitbuchungen.first()) == "Arbeitszeit ab 20.10.2026 18:00"


def test_stundenkonto_zaehlt_gestempelte_zeit(fest):
    Arbeitsvertrag.objects.create(benutzer=fest, beginn=TAG, wochenstunden=D("40"))
    buchen(fest, "08:00", "17:00")  # 9 Stunden, 30 Minuten Pause
    monat = berechnung.stundenkonto(fest, 2026, TAG).monate[0]
    assert (monat.soll, monat.gestempelt, monat.saldo) == (D("8"), D("8.5"), D("0.5"))


# --- Stempeln ----------------------------------------------------------------------------


def test_darf_stempeln(fest, ehrenamt, client):
    from django.contrib.auth.models import AnonymousUser

    assert arbeitszeit.darf_stempeln(fest) and not arbeitszeit.darf_stempeln(ehrenamt)
    assert not arbeitszeit.darf_stempeln(AnonymousUser())
    einstellen(ehrenamtliche_stempeln=True)
    assert arbeitszeit.darf_stempeln(ehrenamt)
    fest.is_active = False
    assert not arbeitszeit.darf_stempeln(fest)


def test_kommen_und_gehen(fest):
    jetzt = zeit(TAG, "08:00")
    b = arbeitszeit.kommen(fest, jetzt)
    with pytest.raises(arbeitszeit.StempelFehler, match="schon eingestempelt"):
        arbeitszeit.kommen(fest, jetzt)
    assert arbeitszeit.gehen(fest, zeit(TAG, "12:00")).stunden == D("4")
    with pytest.raises(arbeitszeit.StempelFehler, match="Kein offenes"):
        arbeitszeit.gehen(fest, zeit(TAG, "12:05"))
    b.refresh_from_db()
    assert b.ende == zeit(TAG, "12:00")
    # Gleich wieder gehen: mindestens eine Minute
    arbeitszeit.kommen(fest, zeit(TAG, "13:00"))
    assert arbeitszeit.gehen(fest, zeit(TAG, "13:00")).ende == zeit(TAG, "13:01")


def test_vergessenes_gehen(fest):
    alt = arbeitszeit.kommen(fest, zeit(TAG, "08:00"))
    morgen = zeit(TAG + dt.timedelta(days=1), "08:00")
    assert arbeitszeit.laufend(fest, morgen) is None
    assert list(arbeitszeit.vergessen(fest, morgen)) == [alt]
    neu = arbeitszeit.kommen(fest, morgen)  # neuer Tag trotz offenem Vortag
    assert arbeitszeit.gehen(fest, morgen + dt.timedelta(hours=1)) == neu
    alt.refresh_from_db()
    assert alt.ende is None


def test_ueberschneidung(fest):
    buchen(fest, "08:00", "12:00")
    offen = buchen(fest, "14:00")
    assert arbeitszeit.ueberschneidung(Zeitbuchung(benutzer=fest, beginn=zeit(TAG, "11:00")))
    neu = Zeitbuchung(benutzer=fest, beginn=zeit(TAG, "12:00"), ende=zeit(TAG, "13:00"))
    assert arbeitszeit.ueberschneidung(neu) is None
    neu.ende = zeit(TAG, "15:00")
    assert arbeitszeit.ueberschneidung(neu) == offen
    vorher = Zeitbuchung(benutzer=fest, beginn=zeit(TAG, "06:00"), ende=zeit(TAG, "07:00"))
    assert arbeitszeit.ueberschneidung(vorher) is None


def test_meine_arbeitszeit_seite(client, admin, anmelden, fest):
    anmelden(client, fest)
    url = reverse("personal:meine_arbeitszeit")
    seite = client.get(url).content.decode()
    assert "Nicht eingestempelt" in seite and "Meine Arbeitszeit</a>" in seite
    assert "Stundenkonto" not in seite  # ohne Vertrag kein Konto
    antwort = client.post(reverse("personal:stempeln"), {"aktion": "kommen"}, follow=True)
    assert "Kommen um" in antwort.content.decode() and "Eingestempelt seit" in (
        antwort.content.decode()
    )
    doppelt = client.post(reverse("personal:stempeln"), {"aktion": "kommen"}, follow=True)
    assert "schon eingestempelt" in doppelt.content.decode()
    gehen = client.post(reverse("personal:stempeln"), {"aktion": "gehen"}, follow=True)
    assert "Gehen um" in gehen.content.decode()
    Arbeitsvertrag.objects.create(benutzer=fest, beginn=TAG, wochenstunden=D("20"))
    Zeitbuchung.objects.create(benutzer=fest, beginn=timezone.now() - dt.timedelta(days=2))
    seite = client.get(url).content.decode()
    assert "Stundenkonto" in seite and "fehlt das „Gehen“" in seite
    vormonat = client.get(url, {"monat": "2026-01"}).content.decode()
    assert "Keine Zeiten in diesem Monat" in vormonat and "Januar 2026" in vormonat


def test_ehrenamtliche_ohne_freigabe(client, admin, anmelden, ehrenamt):
    anmelden(client, ehrenamt)
    assert "Meine Arbeitszeit" not in client.get(reverse("core:start")).content.decode()
    assert client.get(reverse("personal:meine_arbeitszeit")).status_code == 403
    assert client.post(reverse("personal:stempeln"), {"aktion": "kommen"}).status_code == 403


# --- Korrektur durch das Personal ---------------------------------------------------------


def test_nachtragen_korrigieren_loeschen(admin_client, fest):
    url = reverse("personal:zeit_neu", args=[fest.pk])
    assert "Zeit nachtragen" in admin_client.get(url).content.decode()
    daten = {"datum": "2026-10-20", "kommen": "08:00", "gehen": "16:00", "bemerkung": "vergessen"}
    antwort = admin_client.post(url, daten)
    assert antwort.url.endswith("?monat=2026-10")
    b = Zeitbuchung.objects.get()
    assert (b.stunden, b.korrigiert_von, b.bemerkung) == (D("8"), "chefin", "vergessen")

    zweite = admin_client.post(url, daten | {"kommen": "09:00"}).content.decode()
    assert "Überschneidet sich" in zweite
    bearbeiten = reverse("personal:zeit", args=[fest.pk, b.pk])
    assert 'value="08:00"' in admin_client.get(bearbeiten).content.decode()
    falsch = admin_client.post(bearbeiten, daten | {"gehen": "07:00"}).content.decode()
    assert "muss nach „Kommen“ liegen" in falsch
    admin_client.post(bearbeiten, daten | {"gehen": ""})
    b.refresh_from_db()
    assert b.ende is None

    unvollstaendig = admin_client.post(url, {"datum": "2026-10-20"}).content.decode()
    assert "Pflichtfeld" in unvollstaendig or "erforderlich" in unvollstaendig

    seite = admin_client.get(reverse("personal:zeiten", args=[fest.pk]), {"monat": "2026-10"})
    assert "korrigiert von chefin" in seite.content.decode()
    admin_client.post(reverse("personal:zeit_loeschen", args=[fest.pk, b.pk]))
    assert not Zeitbuchung.objects.exists()


def test_form_mit_bestehender_buchung(fest):
    b = buchen(fest, "08:00")
    form = ZeitbuchungForm(buchung=b)
    assert form.initial["gehen"] is None and form.initial["kommen"] == dt.time(8, 0)


def test_liste_zeigt_vergessene(admin_client, ehrenamt):
    einstellen(ehrenamtliche_stempeln=True)
    Zeitbuchung.objects.create(benutzer=ehrenamt, beginn=timezone.now() - dt.timedelta(days=2))
    seite = admin_client.get(reverse("personal:liste")).content.decode()
    assert "Fehlendes „Gehen“" in seite and "eli" in seite
    person = admin_client.get(reverse("personal:zeiten", args=[ehrenamt.pk])).content.decode()
    assert "Fehlendes „Gehen“" in person


def test_einstellungen(admin_client, client, anmelden, fest):
    url = reverse("personal:arbeitszeit_einstellungen")
    assert "Arbeitszeiterfassung" in admin_client.get(url).content.decode()
    admin_client.post(url, {"offen_hoechstens_stunden": "10"})
    e = ArbeitszeitEinstellungen.laden()
    assert (e.offen_hoechstens_stunden, e.pausen_automatisch, str(e)) == (
        10, False, "Einstellungen Arbeitszeit"
    )  # fmt: skip
    anmelden(client, fest)
    assert client.get(url).status_code == 403


def test_loeschfrist_entfernt_zeiten(admin, fest):
    buchen(fest, "08:00", "12:00")
    verwaltung.sperren(admin, fest)
    fest.__class__.objects.filter(pk=fest.pk).update(
        gesperrt_am=timezone.now() - dt.timedelta(days=5 * 365)
    )
    assert personal.stammdaten_leeren() == 1
    assert not Zeitbuchung.objects.exists()
