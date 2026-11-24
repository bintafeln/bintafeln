"""Status nach dem Ausweis (ADR 0176): abgelaufen → pausiert, verlängert → aktiv; von Hand
gesetzte Status bleiben; Verstorbene nach Frist in den Papierkorb. Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.core.models import PapierkorbEintrag
from apps.kunden import gruppen, status
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Sperre,
    fristen_anwenden,
)

pytestmark = pytest.mark.django_db
S = Haushalt.Status


def haushalt(nummer, **mehr):
    h = Haushalt.objects.create(kundennummer=nummer, **mehr)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                          nachname=f"Muster{nummer}")  # fmt: skip
    return h


@pytest.fixture
def an():
    e = KundenEinstellungen.laden()
    e.status_nach_ausweis = True
    e.save()
    return e


@pytest.fixture
def tage():
    heute = timezone.localdate()
    return heute, heute - dt.timedelta(days=1), heute + dt.timedelta(days=30)


def test_aus_bleibt_alles_wie_es_ist(tage):
    heute, gestern, _ = tage
    h = haushalt("1", ausweis_gueltig_bis=gestern)
    assert status.regel_anwenden() == 0 and status.pruefen(h) == ""
    h.refresh_from_db()
    assert h.status == S.AKTIV


def test_abgelaufen_pausiert_und_verlaengert_wieder_aktiv(an, tage):
    heute, gestern, spaeter = tage
    abgelaufen = haushalt("1", ausweis_gueltig_bis=gestern)
    heute_noch = haushalt("2", ausweis_gueltig_bis=heute)  # gilt heute noch
    ohne_datum = haushalt("3")  # unbekannt ist nicht abgelaufen
    von_hand = haushalt("4", ausweis_gueltig_bis=spaeter, status=S.PAUSIERT)
    gesperrt = haushalt("5", ausweis_gueltig_bis=gestern, status=S.GESPERRT)
    assert len(status.betroffene()) == 1
    assert status.regel_anwenden() == 1
    for h in (abgelaufen, heute_noch, ohne_datum, von_hand, gesperrt):
        h.refresh_from_db()
    assert abgelaufen.status == S.PAUSIERT and abgelaufen.status_automatisch
    assert abgelaufen.status_seit == heute
    assert [heute_noch.status, ohne_datum.status] == [S.AKTIV, S.AKTIV]
    assert von_hand.status == S.PAUSIERT and gesperrt.status == S.GESPERRT  # nie angefasst
    ereignis = HaushaltEreignis.objects.get(kundennummer="1")
    assert "Status: aktiv → pausiert (Ausweis abgelaufen am" in ereignis.text
    assert status.regel_anwenden() == 0  # ein zweiter Lauf ändert nichts

    # Verlängerung: der automatisch Pausierte wird wieder aktiv, der von Hand Pausierte nicht
    Haushalt.objects.filter(kundennummer="1").update(ausweis_gueltig_bis=spaeter)
    assert status.regel_anwenden() == 1
    abgelaufen.refresh_from_db()
    von_hand.refresh_from_db()
    assert abgelaufen.status == S.AKTIV and not abgelaufen.status_automatisch
    assert von_hand.status == S.PAUSIERT
    assert HaushaltEreignis.objects.filter(
        kundennummer="1", text__contains="pausiert → aktiv (Ausweis wieder gültig)"
    ).exists()


def test_taeglich_ueber_die_fristen_und_gruppe_faellt_weg(an, tage):
    _, gestern, _ = tage
    stelle = Ausgabestelle.objects.create(name="Zentrale")
    g = Kundengruppe.objects.create(name="Mi", ausgabestelle=stelle, wochentage="Mi")
    h = haushalt("1", ausweis_gueltig_bis=gestern, kundengruppe=g)
    fristen_anwenden()
    h.refresh_from_db()
    assert h.status == S.PAUSIERT and h.kundengruppe is None


def test_sofort_beim_bearbeiten_und_von_hand_bleibt_von_hand(an, tage):
    heute, gestern, spaeter = tage
    h = haushalt("1", ausweis_gueltig_bis=gestern)
    gruppen.pruefen(h)
    assert "Status pausiert: Ausweis abgelaufen" in h.status_meldung
    h.refresh_from_db()
    assert h.status == S.PAUSIERT and h.status_automatisch
    # Wer den automatisch Pausierten von Hand sperrt, nimmt ihn aus der Automatik
    h.status = S.GESPERRT
    h.ausweis_gueltig_bis = spaeter
    h.save()
    assert not h.status_automatisch and h.status_seit == heute
    h.refresh_from_db()
    assert h.status == S.GESPERRT
    # save(update_fields=["status"]) hält „seit“ ebenfalls fest
    h.status = S.BEENDET
    h.status_seit = None
    h.save(update_fields=["status"])
    h.refresh_from_db()
    assert h.status_seit == heute


def test_einschalten_stellt_den_bestand_um(admin_client, tage):
    _, gestern, _ = tage
    haushalt("1", ausweis_gueltig_bis=gestern)
    haushalt("2", ausweis_gueltig_bis=gestern)
    seite = reverse("kunden:einstellungen")
    inhalt = admin_client.get(seite).content.decode()
    assert "Das beträfe heute 2 Kunden: 0 auf „gesperrt“" in inhalt
    felder = {}
    form = admin_client.get(seite).context["form"]
    for name, feld in form.fields.items():
        wert = form.initial.get(name, feld.initial)
        if isinstance(wert, bool):
            if wert:
                felder[name] = "on"
        elif wert not in (None, ""):
            felder[name] = list(wert) if isinstance(wert, (list, tuple, set)) else wert
    felder["status_nach_ausweis"] = "on"
    antwort = admin_client.post(seite, felder, follow=True)
    assert "Status nach dem Ausweis umgestellt: 2 Kunden" in antwort.content.decode()
    assert Haushalt.objects.filter(status=S.PAUSIERT, status_automatisch=True).count() == 2


def test_verstorben_zaehlt_nicht_und_wird_nach_frist_geloescht(tage):
    heute, _, _ = tage
    stelle = Ausgabestelle.objects.create(name="Zentrale")
    g = Kundengruppe.objects.create(name="Mi", ausgabestelle=stelle, wochentage="Mi", maximum=5)
    h = haushalt("1", kundengruppe=g)
    haushalt("2", kundengruppe=g)
    h.status = S.VERSTORBEN
    h.save()
    assert h.status_seit == heute
    assert "Status verstorben" in gruppen.pruefen(h)  # fällt aus der Kundengruppe
    assert [x["belegt"] for x in gruppen.mit_plaetzen() if x["gruppe"] == g] == [1]
    # vor der Frist (Vorgabe 3 Monate) bleibt er
    assert status.verstorbene_entfernen() == 0
    Haushalt.objects.filter(pk=h.pk).update(status_seit=heute - dt.timedelta(days=100))
    assert fristen_anwenden() >= 1
    assert not Haushalt.objects.filter(kundennummer="1").exists()
    eintrag = PapierkorbEintrag.objects.get()
    assert eintrag.kundennummer == "1" and eintrag.art == "Haushalt"  # wiederherstellbar
    # 0 = nie automatisch
    e = KundenEinstellungen.laden()
    e.verstorben_loeschen_monate = 0
    e.save()
    Haushalt.objects.filter(kundennummer="2").update(
        status=S.VERSTORBEN, status_seit=heute - dt.timedelta(days=900))  # fmt: skip
    assert status.verstorbene_entfernen() == 0


def test_sperre_geht_vor_gesperrt_statt_pausiert(an, tage):
    """Wer eine laufende Sperre eingetragen hat, steht auf „gesperrt“, nicht auf „pausiert“ –
    auch wenn er vorher schon vom Programm pausiert wurde. Endet die Sperre, gilt der Ausweis."""
    heute, gestern, spaeter = tage
    abgelaufen = haushalt("1", ausweis_gueltig_bis=gestern)
    gueltig = haushalt("2", ausweis_gueltig_bis=spaeter)
    schon_pausiert = haushalt("3", ausweis_gueltig_bis=gestern)
    Haushalt.objects.filter(pk=schon_pausiert.pk).update(status=S.PAUSIERT, status_automatisch=True)
    von_hand = haushalt("4", ausweis_gueltig_bis=gestern, status=S.PAUSIERT)
    alte_sperre = haushalt("5", ausweis_gueltig_bis=spaeter)
    for h in (abgelaufen, gueltig, schon_pausiert, von_hand):
        Sperre.objects.create(haushalt=h, von=gestern, begruendung="erfunden")
    Sperre.objects.create(haushalt=alte_sperre, von=gestern - dt.timedelta(days=30), bis=gestern)
    assert status.regel_anwenden() == 3
    for h in (abgelaufen, gueltig, schon_pausiert, von_hand, alte_sperre):
        h.refresh_from_db()
    assert [abgelaufen.status, gueltig.status, schon_pausiert.status] == [S.GESPERRT] * 3
    assert abgelaufen.status_automatisch and gueltig.status_automatisch
    assert von_hand.status == S.PAUSIERT  # von Hand gesetzt: bleibt
    assert alte_sperre.status == S.AKTIV  # die Sperre ist vorbei
    assert HaushaltEreignis.objects.filter(
        kundennummer="3", text__contains="pausiert → gesperrt (Sperre eingetragen)"
    ).exists()
    # sofort nach einer Änderung im Programm
    neu = haushalt("6", ausweis_gueltig_bis=spaeter)
    Sperre.objects.create(haushalt=neu, von=heute)
    gruppen.pruefen(neu)
    assert neu.status_meldung == "Status gesperrt: Sperre eingetragen"
    # Sperre endet: wieder nach dem Ausweis – aktiv bzw. pausiert
    Sperre.objects.filter(haushalt__in=[abgelaufen, gueltig]).update(bis=gestern)
    assert status.regel_anwenden() == 2
    abgelaufen.refresh_from_db()
    gueltig.refresh_from_db()
    assert abgelaufen.status == S.PAUSIERT and gueltig.status == S.AKTIV
    assert HaushaltEreignis.objects.filter(
        kundennummer="2", text__contains="gesperrt → aktiv (Sperre beendet)"
    ).exists()
    # von Hand „gesperrt“ ohne Sperre-Eintrag bleibt gesperrt
    hand = haushalt("7", ausweis_gueltig_bis=spaeter, status=S.GESPERRT)
    assert status.regel_anwenden() == 0
    hand.refresh_from_db()
    assert hand.status == S.GESPERRT
