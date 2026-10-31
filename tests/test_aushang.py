"""Modul Aushang-Monitore (ADR 0080). Alle Namen sind erfunden (Beispieldaten der Module)."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.adressen.models import Adresse
from apps.aushang import anzeige
from apps.aushang.models import Aushang, AushangSeite
from apps.core.models import PapierkorbEintrag, TafelEinstellungen
from apps.dienstplan import beispiel as dp_beispiel
from apps.fahrdienst import beispiel as fd_beispiel
from apps.konten import rollen
from apps.kunden.models import Ausgabestelle

pytestmark = pytest.mark.django_db
MITTWOCH = dt.date(2026, 11, 11)
LISTE = reverse("aushang:liste")


@pytest.fixture(autouse=True)
def module_an():
    t = TafelEinstellungen.laden()
    t.module = ["aushang", "dienstplan", "fahrdienst"]
    t.bundesland = "NW"
    t.save()


@pytest.fixture
def heute(monkeypatch):
    """Mittwoch, 11.11.2026, 10 Uhr."""
    jetzt = timezone.make_aware(dt.datetime(2026, 11, 11, 10, 0))
    monkeypatch.setattr("django.utils.timezone.localtime", lambda *a: jetzt)
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a: MITTWOCH)
    return MITTWOCH


@pytest.fixture
def plaene():
    dp_beispiel.anlegen(seed=1)
    fd_beispiel.anlegen(seed=1)
    return Ausgabestelle.objects.get(name=dp_beispiel.STELLE)


def test_zeitraum_ganze_monate():
    assert anzeige.zeitraum(MITTWOCH, 1) == (dt.date(2026, 11, 1), dt.date(2026, 11, 30))
    assert anzeige.zeitraum(MITTWOCH, 2) == (dt.date(2026, 11, 1), dt.date(2026, 12, 31))
    assert anzeige.zeitraum(dt.date(2026, 12, 31), 2) == (
        dt.date(2026, 12, 1),
        dt.date(2027, 1, 31),
    )
    # Die nächsten Wochen ab heute: vergangene Tage fallen weg
    assert anzeige.zeitraum(MITTWOCH, 2, 9) == (MITTWOCH, MITTWOCH + dt.timedelta(days=62))


def test_fahrer_naechste_wochen_eine_folie(plaene, heute, admin_client):
    aushang = Aushang.objects.create(name="Monitor Fahrerraum")
    seite = reverse("aushang:bearbeiten", args=[aushang.pk])
    admin_client.post(seite, {"aktion": "seite", "seite": "fahrdienst:", "zeitraum": "w",
                              "wochen": 3})  # fmt: skip
    s = aushang.seiten.get()
    assert (s.wochen, s.zeitraum_text()) == (3, "die nächsten 3 Wochen ab heute")
    assert "die nächsten 3 Wochen ab heute" in admin_client.get(seite).content.decode()
    folien = anzeige.folien(aushang, heute)
    ende = heute + dt.timedelta(days=20)
    assert [(f[0], f[3]) for f in folien] == [
        (f"Fahrerplan {heute:%d.%m.} bis {ende:%d.%m.%Y}", "Fahrer")]  # fmt: skip
    gestern = heute - dt.timedelta(days=1)
    assert f"{gestern:%d.%m.}" not in folien[0][1] and f"{heute:%d.%m.}" in folien[0][1]
    # Zeitraum einer vorhandenen Seite ändern: zurück auf ganze Monate
    admin_client.post(seite, {"aktion": "zeitraum", "seite": s.pk, "zeitraum": "m1"})
    s.refresh_from_db()
    assert (s.monate, s.wochen) == (1, 0)
    admin_client.post(seite, {"aktion": "zeitraum", "seite": s.pk, "zeitraum": "w", "wochen": ""})
    s.refresh_from_db()
    assert s.wochen == 9
    assert admin_client.post(seite, {"aktion": "zeitraum", "seite": 999999,
                                     "zeitraum": "m1"}).status_code == 404  # fmt: skip


def test_einrichten_seiten_reihenfolge_und_link(plaene, admin_client):
    antwort = admin_client.post(LISTE, {"name": "Monitor Fahrerraum"})
    aushang = Aushang.objects.get()
    assert antwort.url == reverse("aushang:bearbeiten", args=[aushang.pk])
    seite = reverse("aushang:bearbeiten", args=[aushang.pk])
    html = admin_client.get(seite).content.decode()
    assert f"dienstplan:{plaene.pk}" in html and 'value="fahrdienst:"' in html
    admin_client.post(seite, {"aktion": "seite", "seite": f"dienstplan:{plaene.pk}",
                              "zeitraum": "m1"})  # fmt: skip
    admin_client.post(seite, {"aktion": "seite", "seite": "fahrdienst:", "zeitraum": "m2"})
    assert [(s.art, s.wert, s.monate) for s in aushang.seiten.all()] == [
        ("dienstplan", str(plaene.pk), 1), ("fahrdienst", "", 2)]  # fmt: skip
    html = admin_client.get(seite).content.decode()
    assert f"Dienstplan einer Ausgabestelle: {dp_beispiel.STELLE}" in html
    fahrer = aushang.seiten.get(art="fahrdienst")
    admin_client.post(seite, {"aktion": "hoch", "seite": fahrer.pk})
    assert [s.art for s in aushang.seiten.all()] == ["fahrdienst", "dienstplan"]
    admin_client.post(seite, {"aktion": "runter", "seite": fahrer.pk})
    assert [s.art for s in aushang.seiten.all()] == ["dienstplan", "fahrdienst"]
    assert admin_client.post(seite, {"aktion": "hoch", "seite": 999999}).status_code == 404

    admin_client.post(seite, {"aktion": "einstellungen", "name": "Monitor Flur", "aktiv": "on",
                              "nebeneinander": 2, "sekunden": 30})  # fmt: skip
    aushang.refresh_from_db()
    assert (aushang.name, aushang.nebeneinander, aushang.sekunden) == ("Monitor Flur", 2, 30)
    assert admin_client.post(seite, {"aktion": "einstellungen", "name": "x", "nebeneinander": 1,
                                     "sekunden": 2}).status_code == 200  # fmt: skip
    alt = aushang.schluessel
    admin_client.post(seite, {"aktion": "schluessel"})
    aushang.refresh_from_db()
    assert aushang.schluessel != alt
    assert Client().get(reverse("aushang:anzeige", args=[alt])).status_code == 404

    admin_client.post(seite, {"aktion": "entfernen", "seite": fahrer.pk})
    assert [s.art for s in aushang.seiten.all()] == ["dienstplan"]
    admin_client.post(reverse("aushang:loeschen", args=[aushang.pk]))
    assert not Aushang.objects.exists() and not AushangSeite.objects.exists()
    assert PapierkorbEintrag.objects.filter(bezeichnung="Monitor Flur").exists()
    assert "Aushang-Monitore" in admin_client.get(reverse("core:start")).content.decode()


def test_monitor_ohne_anmeldung_nur_namen(plaene, heute, admin):
    aushang = Aushang.objects.create(name="Monitor Fahrerraum")
    AushangSeite.objects.create(aushang=aushang, art="dienstplan", wert=str(plaene.pk), monate=1)
    AushangSeite.objects.create(aushang=aushang, art="fahrdienst", monate=2, reihenfolge=1)
    antwort = Client().get(reverse("aushang:anzeige", args=[aushang.schluessel]))
    html = antwort.content.decode()
    assert antwort.status_code == 200
    # Dienstplan: je Ausgabetag (Mo, Mi, Fr) eine Seite, ganzer Monat; Fahrerplan je Monat
    folien = anzeige.folien(aushang, heute)
    titel = [f[0] for f in folien]
    assert [f[3] for f in folien][-2:] == ["Fahrer November", "Fahrer Dezember"]
    assert folien[0][3] == f"Ausgabe {dp_beispiel.STELLE} Montag"
    tage = ("Montag", "Mittwoch", "Freitag")
    assert titel == [f"Dienstplan {dp_beispiel.STELLE} · {t}" for t in tage] + [
        "Fahrerplan November 2026", "Fahrerplan Dezember 2026"]  # fmt: skip
    assert "11.11." in html and "02.11." not in html and "09.11." not in html  # ab heute
    assert '<button type="button" data-nr="3">Fahrer November</button>' in html
    assert "Teamleitung:" in html and "Mittwoch, 11.11.2026" in html and "Stand 10:00 Uhr" in html
    helfer = Adresse.objects.filter(notiz=dp_beispiel.KENNUNG, helfer=True).first()
    assert helfer.name in html and helfer.telefon not in html and "0123 45" not in html
    assert 'class="knopf' not in html and "menue" not in html  # ganzseitig, ohne Menü
    assert "aushang.js" in html and 'data-sekunden="20"' in html

    aushang.aktiv = False
    aushang.save()
    url = reverse("aushang:anzeige", args=[aushang.schluessel])
    assert Client().get(url).status_code == 404
    assert Client().get(url, headers={"X-Aushang": "1"}).status_code == 204  # Monitor leert sich


def test_seiten_ausgeschalteter_module_fallen_weg(plaene, heute, admin_client):
    aushang = Aushang.objects.create(name="Monitor")
    AushangSeite.objects.create(aushang=aushang, art="fahrdienst", monate=1)
    t = TafelEinstellungen.laden()
    t.module = ["aushang", "dienstplan"]
    t.save()
    assert anzeige.folien(aushang, heute) == []
    html = Client().get(reverse("aushang:anzeige", args=[aushang.schluessel])).content.decode()
    assert "Zurzeit gibt es hier nichts anzuzeigen." in html
    html = admin_client.get(reverse("aushang:bearbeiten", args=[aushang.pk])).content.decode()
    assert "fahrdienst (Modul ausgeschaltet)" in html
    # Ganz ohne Modul Aushang: auch der Monitor ist weg
    t.module = ["dienstplan"]
    t.save()
    assert Client().get(reverse("aushang:anzeige", args=[aushang.schluessel])).status_code == 404


def test_unbekannte_stelle_zeigt_nichts(plaene, heute):
    aushang = Aushang.objects.create(name="Monitor")
    AushangSeite.objects.create(aushang=aushang, art="dienstplan", wert="999999")
    AushangSeite.objects.create(aushang=aushang, art="dienstplan", wert="x")
    assert anzeige.folien(aushang, heute) == []


def test_seiten_nur_mit_recht_den_plan_zu_planen(plaene, client, anmelden, benutzer_mit_rolle,
                                                 recht_geben, admin):  # fmt: skip
    recht_geben(rollen.FAHRER, "aushang.einrichten", "fahrdienst.planen")
    anmelden(client, benutzer_mit_rolle("max", rollen.FAHRER))
    aushang = Aushang.objects.create(name="Monitor")
    seite = reverse("aushang:bearbeiten", args=[aushang.pk])
    html = client.get(seite).content.decode()
    assert 'value="fahrdienst:"' in html and "dienstplan:" not in html
    antwort = client.post(
        seite, {"aktion": "seite", "seite": f"dienstplan:{plaene.pk}", "zeitraum": "m2"}
    )
    assert antwort.status_code == 200 and not aushang.seiten.exists()


def test_ohne_moegliche_seiten_ein_hinweis(admin_client):
    t = TafelEinstellungen.laden()
    t.module = ["aushang"]
    t.save()
    aushang = Aushang.objects.create(name="Monitor")
    html = admin_client.get(reverse("aushang:bearbeiten", args=[aushang.pk])).content.decode()
    assert "Sie können keine Seiten hinzufügen" in html
    assert "Monitor" in admin_client.get(LISTE).content.decode()


# --- Ändern am Monitor mit persönlicher PIN ---------------------------------------------------


@pytest.fixture
def fahrer(benutzer_mit_rolle, admin):
    """Tour Mitte mittwochs mit Max (Fahrer) und Jan (Beifahrer); Eva plant (Büro)."""
    from apps.aushang import pin
    from apps.fahrdienst.models import Besetzung, Tour

    leute = {}
    namen = [("Max Mustermann", rollen.FAHRER), ("Jan Beispiel", rollen.BEIFAHRER),
             ("Eva Lindner", rollen.BUERO), ("Ole Hansen", rollen.BEIFAHRER)]  # fmt: skip
    for name, rolle in namen:
        b = benutzer_mit_rolle(name.split()[0].lower(), rolle)
        b.first_name, b.last_name = name.split()
        b.save()
        pin.setzen(b, "482915")
        leute[b.username] = b
    tour = Tour.objects.create(name="Mitte", plaetze=2, mindestbesetzung=2)
    Besetzung.objects.create(tour=tour, wochentag="Mi", platz=1, benutzer=leute["max"])
    Besetzung.objects.create(tour=tour, wochentag="Mi", platz=2, benutzer=leute["jan"])
    aushang = Aushang.objects.create(name="Monitor Fahrerraum")
    AushangSeite.objects.create(aushang=aushang, art="fahrdienst", monate=1)
    return leute, tour, aushang


def _platz(aushang):
    return reverse("aushang:platz", args=[aushang.schluessel])


def test_meine_pin_festlegen_und_loeschen(client, anmelden, benutzer_mit_rolle, admin):
    from apps.aushang.models import MonitorPin

    seite = reverse("aushang:meine_pin")
    max_ = benutzer_mit_rolle("max", rollen.FAHRER)
    anmelden(client, max_)
    assert "Sie haben noch keine PIN." in client.get(seite).content.decode()
    for falsch, text in (("12345", "mindestens 6"), ("12a456", "nur Ziffern"),
                         ("123456", "einfache Folge"), ("777777", "einfache Folge")):  # fmt: skip
        html = client.post(seite, {"pin": falsch, "wiederholen": falsch}).content.decode()
        assert text in html.replace("Mindestens", "mindestens"), falsch
    html = client.post(seite, {"pin": "482915", "wiederholen": "482916"}).content.decode()
    assert "nicht gleich" in html
    konto = reverse("konten:mein_konto")
    assert "PIN für Aushang-Monitore" in client.get(konto).content.decode()
    antwort = client.post(seite, {"pin": "482915", "wiederholen": "482915"})
    assert antwort.url == konto and "Eingerichtet" in client.get(konto).content.decode()
    eintrag = MonitorPin.objects.get(benutzer=max_)
    assert eintrag.pin != "482915" and "$" in eintrag.pin  # nur gehasht
    assert "Sie haben eine PIN" in client.get(seite).content.decode()
    client.post(seite, {"aktion": "loeschen"})
    assert not MonitorPin.objects.exists()
    # Ohne Dienst- oder Fahrerplan kein Abschnitt auf „Mein Konto“
    anmelden(client, benutzer_mit_rolle("lohn", rollen.PERSONAL))
    assert "PIN für Aushang-Monitore" not in client.get(konto).content.decode()


def test_sich_am_monitor_austragen_nur_mit_eigener_pin(fahrer, heute, client):
    from auditlog.models import LogEntry

    from apps.aushang.models import MonitorPin
    from apps.fahrdienst.models import Ausfall

    leute, tour, aushang = fahrer
    kennung = f"fahrdienst|{heute:%Y-%m-%d}|{tour.pk}|1"
    html = client.get(_platz(aushang), {"platz": kennung}).content.decode()
    assert "Ich bin Max Mustermann und kann nicht" in html and "Wie lange" in html
    assert "Für andere eintragen" in html and "Eva Lindner" in html  # Eva plant
    daten = {"platz": kennung, "aktion": "ausfall", "person": leute["max"].pk, "grund": "krank"}
    # Jans PIN passt nicht zu Max; Jan darf Max auch nicht austragen
    assert client.post(_platz(aushang), {**daten, "pin": "000000"}).json() == {
        "ok": False, "fehler": "Die PIN stimmt nicht."}  # fmt: skip
    antwort = client.post(_platz(aushang), {**daten, "person": leute["jan"].pk, "pin": "482915"})
    assert "nur die Person selbst" in antwort.json()["fehler"]
    antwort = client.post(_platz(aushang), {**daten, "pin": "482915"}).json()
    assert antwort["ok"] and "Max Mustermann fällt am 11.11. aus" in antwort["meldung"]
    ausfall = Ausfall.objects.get()
    assert (ausfall.benutzer, ausfall.von, ausfall.bis) == (leute["max"], heute, heute)
    assert ausfall.eingetragen_von == "max am Monitor „Monitor Fahrerraum“"
    assert LogEntry.objects.get_for_object(ausfall).get().actor == leute["max"]
    assert MonitorPin.objects.get(benutzer=leute["max"]).fehler == 0


def test_falsche_pin_sperrt_nach_fuenf_versuchen(fahrer, heute, client):
    leute, tour, aushang = fahrer
    daten = {"platz": f"fahrdienst|{heute:%Y-%m-%d}|{tour.pk}|1", "aktion": "ausfall",
             "person": leute["max"].pk, "grund": "krank", "pin": "111222"}  # fmt: skip
    for _ in range(5):
        assert client.post(_platz(aushang), daten).json()["fehler"] == "Die PIN stimmt nicht."
    fehler = client.post(_platz(aushang), {**daten, "pin": "482915"}).json()["fehler"]
    assert fehler.startswith("Zu viele falsche Versuche")
    antwort = client.post(_platz(aushang), {**daten, "person": 999999}).json()
    assert antwort["fehler"] == "Für diese Person ist keine PIN eingerichtet."


def test_einspringen_selbst_planen_fuer_andere(fahrer, heute, client):
    from apps.fahrdienst import plan
    from apps.fahrdienst.models import Ausfall, Ersatz

    leute, tour, aushang = fahrer
    Ausfall.objects.create(benutzer=leute["max"], von=heute, bis=heute, grund="krank")
    kennung = f"fahrdienst|{heute:%Y-%m-%d}|{tour.pk}|1"
    html = client.get(_platz(aushang), {"platz": kennung}).content.decode()
    assert "Ich springe ein" in html and "Ole Hansen" in html
    # Ole springt selbst ein, Jan kann Ole nicht eintragen, Gast nur wer plant
    ole = f"{leute['ole'].pk}:{leute['ole'].pk}"
    daten = {"platz": kennung, "aktion": "ersatz", "helfer": leute["ole"].pk,
             "person": leute["jan"].pk, "pin": "482915"}  # fmt: skip
    assert "Einspringen kann man nur selbst" in client.post(_platz(aushang), daten).json()["fehler"]
    assert "nur, wer den Fahrdienst plant" in client.post(_platz(aushang), {
        **daten, "aktion": "gast", "gast": "Paul"}).json()["fehler"]  # fmt: skip
    selbst = {"platz": kennung, "aktion": "einspringen", "einspringer": ole, "pin": "482915"}
    antwort = client.post(_platz(aushang), selbst).json()
    assert antwort["ok"] and "Ole Hansen springt am 11.11. ein" in antwort["meldung"]
    assert plan.platz(heute, tour, 1).status == plan.ERSETZT
    # Eva plant: Eintrag zurücknehmen und einen Gast eintragen
    eva = {"platz": kennung, "person": leute["eva"].pk, "pin": "482915"}
    assert client.post(_platz(aushang), {**eva, "aktion": "zuruecknehmen"}).json()["ok"]
    assert not Ersatz.objects.exists()
    antwort = client.post(_platz(aushang), {**eva, "aktion": "gast", "gast": "Paul Probe"}).json()
    assert antwort["ok"] and Ersatz.objects.get().gast == "Paul Probe"
    assert client.post(_platz(aushang), {**eva, "aktion": "gast"}).json()["fehler"].startswith(
        "Bitte den Namen")  # fmt: skip
    assert (
        client.post(_platz(aushang), {**eva, "aktion": "x"}).json()["fehler"]
        == "Unbekannte Aktion."
    )


def test_am_monitor_nichts_aendern_wenn_aus_vergangen_oder_unbekannt(fahrer, heute, client):
    leute, tour, aushang = fahrer
    gestern = heute - dt.timedelta(days=7)
    assert client.get(_platz(aushang), {"platz": f"fahrdienst|{gestern:%Y-%m-%d}|{tour.pk}|1"}
                      ).status_code == 404  # fmt: skip
    assert client.get(_platz(aushang), {"platz": "unbekannt|x"}).status_code == 404
    antwort = client.post(_platz(aushang), {"platz": f"fahrdienst|{gestern:%Y-%m-%d}|{tour.pk}|1",
                                            "aktion": "ausfall"}).json()  # fmt: skip
    assert antwort["fehler"] == "Diesen Platz gibt es nicht (mehr)."
    assert client.post(_platz(aushang), {"platz": "x|y"}).json()["ok"] is False
    aushang.aendern = False
    aushang.save()
    kennung = f"fahrdienst|{heute:%Y-%m-%d}|{tour.pk}|1"
    assert client.get(_platz(aushang), {"platz": kennung}).status_code == 404
    html = Client().get(reverse("aushang:anzeige", args=[aushang.schluessel])).content.decode()
    assert "Auf einen Namen oder Platz tippen" not in html and "<svg" in html  # QR-Code bleibt
    aushang.qr_code = False
    aushang.save()
    html = Client().get(reverse("aushang:anzeige", args=[aushang.schluessel])).content.decode()
    assert "<svg" not in html


def test_dienstplan_am_monitor_helfer_mit_konto(plaene, heute, client, benutzer_mit_rolle, admin):
    from apps.aushang import pin
    from apps.dienstplan.models import Aufgabe, Ausfall

    a = Aufgabe.objects.filter(stelle__ausgabestelle=plaene, wochentag="Mi", name="Kasse").get()
    h = a.besetzung.helfer
    h.konto = benutzer_mit_rolle("lohn", rollen.PERSONAL)
    h.save()
    pin.setzen(h.konto, "482915")
    aushang = Aushang.objects.create(name="Monitor")
    kennung = f"dienstplan|{heute:%Y-%m-%d}|{a.pk}"
    assert f"Ich bin {h}" in client.get(_platz(aushang), {"platz": kennung}).content.decode()
    daten = {"platz": kennung, "aktion": "ausfall", "grund": "urlaub", "person": h.konto.pk,
             "pin": "482915"}  # fmt: skip
    antwort = client.post(_platz(aushang), daten).json()
    assert antwort["ok"] and "Teamleitung wird benachrichtigt" in antwort["meldung"]
    assert Ausfall.objects.get().helfer == h
    html = Client().get(reverse("aushang:anzeige", args=[aushang.schluessel])).content.decode()
    assert f'data-platz="{kennung}"' not in html  # Aushang ohne Seiten
