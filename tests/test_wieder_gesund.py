"""Längere Ausfälle am Monitor und „wieder gesund“ ohne automatisches Zurücktragen (ADR 0085).
Alle Namen sind erfunden."""

import datetime as dt

import pytest
from django.urls import reverse

from apps.core import ausfall as ausfallregeln
from apps.fahrdienst import plan
from apps.fahrdienst.models import Ausfall, Ersatz
from tests.test_aushang import MITTWOCH, _platz, fahrer, heute, module_an  # noqa: F401

pytestmark = pytest.mark.django_db
WOCHE = dt.timedelta(days=7)


def _frei(datum) -> list:
    springer, weitere = plan.verfuegbar(datum)
    return springer + weitere


@pytest.mark.parametrize(
    ("dauer", "bis", "erwartet"),
    [("tag", "", MITTWOCH), ("", "", MITTWOCH), ("w1", "", MITTWOCH + dt.timedelta(days=6)),
     ("w2", "", MITTWOCH + dt.timedelta(days=13)), ("bis", "2026-12-02", dt.date(2026, 12, 2))],
)  # fmt: skip
def test_bis_berechnen(dauer, bis, erwartet):
    assert ausfallregeln.bis_berechnen(MITTWOCH, dauer, bis) == erwartet


@pytest.mark.parametrize(
    ("dauer", "bis", "fehler"),
    [("bis", "", "Bitte das Datum"), ("bis", "2026-11-10", "liegt vor"),
     ("bis", "2028-01-01", "höchstens ein Jahr"), ("w5", "", "wie lange"), ("x", "", "wie lange")],
)  # fmt: skip
def test_bis_berechnen_fehler(dauer, bis, fehler):
    with pytest.raises(ValueError, match=fehler):
        ausfallregeln.bis_berechnen(MITTWOCH, dauer, bis)


def test_am_monitor_fuer_mehrere_wochen_austragen(fahrer, heute, client):  # noqa: F811
    leute, tour, aushang = fahrer
    daten = {"platz": f"fahrdienst|{heute:%Y-%m-%d}|{tour.pk}|1", "aktion": "ausfall",
             "person": leute["max"].pk, "pin": "482915", "grund": "krank"}  # fmt: skip
    fehler = client.post(_platz(aushang), {**daten, "dauer": "bis", "bis": "2026-11-01"}).json()
    assert "liegt vor" in fehler["fehler"] and not Ausfall.objects.exists()
    antwort = client.post(_platz(aushang), {**daten, "dauer": "w3"}).json()
    assert antwort["ok"] and "vom 11.11. bis 01.12.2026" in antwort["meldung"]
    a = Ausfall.objects.get()
    assert (a.von, a.bis, a.grund) == (heute, dt.date(2026, 12, 1), "krank")
    for woche in range(3):
        assert plan.platz(heute + woche * WOCHE, tour, 1).status == plan.OFFEN
    assert plan.platz(heute + 3 * WOCHE, tour, 1).status == plan.OK


def test_wieder_gesund_traegt_nicht_zurueck_ein(fahrer, heute, client):  # noqa: F811
    leute, tour, aushang = fahrer
    max_ = leute["max"]
    a = Ausfall.objects.create(benutzer=max_, von=heute - WOCHE, bis=heute + 3 * WOCHE,
                               grund="krank")  # fmt: skip
    Ersatz.objects.create(datum=heute + WOCHE, tour=tour, platz=1, benutzer=leute["ole"])
    kennung = f"fahrdienst|{heute:%Y-%m-%d}|{tour.pk}|1"
    html = client.get(_platz(aushang), {"platz": kennung}).content.decode()
    assert "Ich bin Max Mustermann und wieder gesund" in html
    assert max_ not in _frei(heute)  # noch krank: kann nicht einspringen
    daten = {"platz": kennung, "aktion": "gesund", "person": leute["jan"].pk, "pin": "482915"}
    assert "nur die Person selbst" in client.post(_platz(aushang), daten).json()["fehler"]
    antwort = client.post(_platz(aushang), {**daten, "person": max_.pk}).json()
    assert antwort["ok"] and "bleiben frei bzw. beim Ersatz" in antwort["meldung"]
    a.refresh_from_db()
    assert a.gesund_ab == heute and a.bis == heute + 3 * WOCHE
    # nicht zurück: heute und in zwei Wochen fehlt jemand, nächste Woche bleibt Ole
    assert plan.platz(heute, tour, 1).status == plan.OFFEN
    assert plan.platz(heute + WOCHE, tour, 1).wer == leute["ole"]
    assert plan.platz(heute + 2 * WOCHE, tour, 1).status == plan.OFFEN
    # aber Max kann jetzt einspringen, auch auf seinem alten Platz
    assert max_ in _frei(heute + 2 * WOCHE)
    html = client.get(_platz(aushang), {"platz": kennung}).content.decode()
    assert "wieder da, der Platz bleibt aber frei" in html and "wieder gesund" not in html
    selbst = {"platz": f"fahrdienst|{heute + 2 * WOCHE:%Y-%m-%d}|{tour.pk}|1",
              "aktion": "einspringen", "einspringer": f"{max_.pk}:{max_.pk}",
              "pin": "482915"}  # fmt: skip
    assert client.post(_platz(aushang), selbst).json()["ok"]
    assert plan.platz(heute + 2 * WOCHE, tour, 1).status == plan.ERSETZT
    # ein zweites Mal geht nicht
    antwort = client.post(_platz(aushang), {**daten, "person": max_.pk}).json()
    assert antwort["fehler"] == "Hier ist kein Ausfall, der noch läuft."


def test_wer_plant_meldet_am_monitor_gesund(fahrer, heute, client):  # noqa: F811
    leute, tour, aushang = fahrer
    Ausfall.objects.create(benutzer=leute["max"], von=heute, bis=heute + WOCHE, grund="urlaub")
    daten = {"platz": f"fahrdienst|{heute:%Y-%m-%d}|{tour.pk}|1", "aktion": "gesund",
             "person": leute["eva"].pk, "pin": "482915"}  # fmt: skip
    assert client.post(_platz(aushang), daten).json()["ok"]
    assert Ausfall.objects.get().gesund_ab == heute


def test_wieder_gesund_im_programm(fahrer, heute, client, anmelden):  # noqa: F811
    from apps.fahrdienst.models import FahrdienstEinstellungen

    leute, tour, _ = fahrer
    e = FahrdienstEinstellungen.laden()
    e.selbst_melden = True
    e.save()
    a = Ausfall.objects.create(benutzer=leute["max"], von=heute, bis=heute + WOCHE, grund="krank")
    url = reverse("fahrdienst:ausfall_gesund", args=[a.pk])
    anmelden(client, leute["jan"])
    assert client.post(url).status_code == 403  # fremder Ausfall
    anmelden(client, leute["max"])
    assert "wieder gesund" in client.get(reverse("fahrdienst:meine")).content.decode()
    assert client.post(url).url == reverse("fahrdienst:meine")
    a.refresh_from_db()
    assert a.gesund_ab == heute
    seite = client.get(reverse("fahrdienst:meine")).content.decode()
    assert "wieder da ab 11.11.2026" in seite
    client.post(url)  # zweites Mal: nur ein Hinweis
    assert plan.platz(heute + WOCHE, tour, 1).status == plan.OFFEN


def test_dienstplan_wieder_gesund(heute):  # noqa: F811
    from apps.dienstplan import beispiel
    from apps.dienstplan import plan as dplan
    from apps.dienstplan.models import Aufgabe
    from apps.dienstplan.models import Ausfall as DAusfall

    beispiel.anlegen(seed=1)
    aufgabe = Aufgabe.objects.filter(wochentag="Mi", besetzung__isnull=False).first()
    h = aufgabe.besetzung.helfer
    a = DAusfall.objects.create(helfer=h, von=heute, bis=heute + 2 * WOCHE, grund="krank")
    assert h not in dplan.verfuegbar(heute + WOCHE)
    assert dplan.gesund_melden(a, heute + WOCHE) and a.gesund_ab == heute + WOCHE
    assert not dplan.gesund_melden(a, heute + WOCHE)  # schon gemeldet
    assert dplan.platz(heute + WOCHE, aufgabe).status == dplan.OFFEN  # Platz bleibt frei
    assert h in dplan.verfuegbar(heute + WOCHE) and h not in dplan.verfuegbar(heute)
    dplan.ersatz_eintragen(heute + WOCHE, aufgabe, h, "test")
    assert dplan.platz(heute + WOCHE, aufgabe).status == dplan.ERSETZT
    vorbei = DAusfall.objects.create(helfer=h, von=heute, bis=heute, grund="krank")
    assert not dplan.gesund_melden(vorbei, heute + WOCHE)


def test_eingesprungen_und_dann_selbst_krank(fahrer, heute, client):  # noqa: F811
    """Ole ist für Max eingesprungen, wird selbst krank, meldet sich für zwei Wochen ab und später
    gesund: Seine Plätze als Ersatz bleiben abgesagt, bis er sich neu einträgt."""
    leute, tour, aushang = fahrer
    ole = leute["ole"]
    Ausfall.objects.create(benutzer=leute["max"], von=heute, bis=heute + 3 * WOCHE, grund="urlaub")
    for woche in range(2):
        plan.ersatz_eintragen(heute + woche * WOCHE, tour, 1, ole, "test")
    kennung = f"fahrdienst|{heute:%Y-%m-%d}|{tour.pk}|1"
    html = client.get(_platz(aushang), {"platz": kennung}).content.decode()
    assert "Ich bin Ole Hansen und kann nicht" in html
    daten = {"platz": kennung, "aktion": "ausfall", "person": ole.pk, "pin": "482915",
             "grund": "krank", "dauer": "w2"}  # fmt: skip
    antwort = client.post(_platz(aushang), daten).json()
    assert antwort["ok"] and "Ole Hansen fällt vom 11.11. bis 24.11.2026 aus" in antwort["meldung"]
    for woche in range(2):  # beide Einsätze als Ersatz sind wieder offen
        p = plan.platz(heute + woche * WOCHE, tour, 1)
        assert p.status == plan.OFFEN and p.wer == ole
    assert ole not in _frei(heute)
    # Jan kann nicht für Ole austragen; Ole meldet sich gesund
    html = client.get(_platz(aushang), {"platz": kennung}).content.decode()
    assert "Ich bin Ole Hansen und wieder gesund" in html
    antwort = client.post(_platz(aushang), {**daten, "aktion": "gesund"}).json()
    assert antwort["ok"]
    # nicht automatisch zurück: der alte Ersatz-Eintrag nächste Woche bleibt abgesagt …
    assert plan.platz(heute + WOCHE, tour, 1).status == plan.OFFEN
    assert ole in _frei(heute + WOCHE)
    # … bis Ole sich neu einträgt
    plan.ersatz_eintragen(heute + WOCHE, tour, 1, ole, "test")
    assert plan.platz(heute + WOCHE, tour, 1).status == plan.ERSETZT
