"""Push-Nachrichten an Mitarbeitende (ADR 0158): Technik im Kern, einschalten auf „Mein Konto“."""

import json

import pytest
from django.urls import reverse

from apps.core import push
from apps.core.models import PushAbo, PushEinstellungen
from apps.konten import rollen
from tests.test_aufruf_handy import _browser, _entschluesseln

ADRESSE = "https://fcm.googleapis.com/fcm/send/"


@pytest.fixture
def gesendet(monkeypatch):
    """Statt an den Push-Dienst: Liste (Adresse, Kopfzeilen, verschlüsselte Daten)."""
    liste = []

    def _senden(adresse, daten, kopf):
        liste.append((adresse, kopf, daten))
        return 201

    monkeypatch.setattr(push, "_senden", _senden)
    return liste


def _abo(adresse, p256dh, auth):
    return json.dumps({"abo": {"endpoint": adresse, "keys": {"p256dh": p256dh, "auth": auth}}})


@pytest.mark.django_db
def test_nachricht_kommt_verschluesselt_auf_alle_geraete(benutzer_mit_rolle, gesendet):
    fritz = benutzer_mit_rolle("fritz", rollen.AUSGABE)
    erna = benutzer_mit_rolle("erna", rollen.AUSGABE)
    privat, p256dh, auth = _browser()
    push.abonnieren(fritz, ADRESSE + "eins", p256dh, auth, "Handy")
    push.abonnieren(fritz, ADRESSE + "zwei", p256dh, auth, "Tablet")
    push.abonnieren(erna, ADRESSE + "erna", p256dh, auth)
    assert push.geraete(fritz) == 2
    assert push.an_benutzer(fritz, "Neuer Stopp", "Musterladen", "/touren/heute/", "stopp-1") == 2
    assert {g[0] for g in gesendet} == {ADRESSE + "eins", ADRESSE + "zwei"}
    adresse, kopf, daten = gesendet[0]
    assert kopf["Content-Encoding"] == "aes128gcm" and kopf["Authorization"].startswith("vapid ")
    assert b"Musterladen" not in daten  # der Push-Dienst kann nichts lesen
    assert json.loads(_entschluesseln(daten, privat, p256dh, auth)) == {
        "titel": "Neuer Stopp", "text": "Musterladen", "link": "/touren/heute/",
        "kennung": "stopp-1",
    }  # fmt: skip
    # mehrere Konten auf einmal; fremde Adressen als Ziel werden nicht mitgeschickt
    gesendet.clear()
    assert push.an_benutzer([fritz, erna, None], "A", "B", "https://example.org/") == 3
    assert json.loads(_entschluesseln(gesendet[0][2], privat, p256dh, auth))["link"] == ""
    assert push.an_benutzer(fritz, "A", "B", "//example.org/") == 2
    assert json.loads(_entschluesseln(gesendet[-1][2], privat, p256dh, auth))["link"] == ""


@pytest.mark.django_db
def test_abgemeldete_geraete_und_gesperrte_konten(benutzer_mit_rolle, monkeypatch):
    fritz = benutzer_mit_rolle("fritz", rollen.AUSGABE)
    _, p256dh, auth = _browser()
    push.abonnieren(fritz, ADRESSE + "weg", p256dh, auth)
    push.abonnieren(fritz, ADRESSE + "da", p256dh, auth)
    monkeypatch.setattr(push, "_senden", lambda a, d, k: 410 if a.endswith("weg") else 201)
    assert push.an_benutzer(fritz, "A", "B") == 1
    assert [a.adresse for a in PushAbo.objects.all()] == [ADRESSE + "da"]  # 410: vergessen
    monkeypatch.setattr(push, "_senden", lambda a, d, k: 0)  # Netzfehler: Gerät bleibt
    assert push.an_benutzer(fritz, "A", "B") == 0 and push.geraete(fritz) == 1
    fritz.is_active = False
    fritz.save()
    monkeypatch.setattr(push, "_senden", lambda a, d, k: 201)
    assert push.an_benutzer(fritz, "A", "B") == 0  # gesperrtes Konto bekommt nichts


@pytest.mark.django_db
def test_geraet_gehoert_einem_konto_und_hoechstens_fuenf(benutzer_mit_rolle):
    fritz = benutzer_mit_rolle("fritz", rollen.AUSGABE)
    erna = benutzer_mit_rolle("erna", rollen.AUSGABE)
    _, p256dh, auth = _browser()
    push.abonnieren(fritz, ADRESSE + "gemeinsam", p256dh, auth)
    push.abonnieren(erna, ADRESSE + "gemeinsam", p256dh, auth)  # Erna meldet sich am Gerät an
    assert push.geraete(fritz) == 0 and push.geraete(erna) == 1
    for n in range(push.GERAETE_JE_KONTO + 2):
        push.abonnieren(fritz, f"{ADRESSE}{n}", p256dh, auth)
    adressen = set(PushAbo.objects.filter(benutzer=fritz).values_list("adresse", flat=True))
    assert len(adressen) == push.GERAETE_JE_KONTO and f"{ADRESSE}0" not in adressen
    assert push.abbestellen(fritz, f"{ADRESSE}6") == 1
    assert push.abbestellen(fritz) == push.GERAETE_JE_KONTO - 1 and push.geraete(erna) == 1
    for falsch in ("https://example.org/push", "http://fcm.googleapis.com/x", ""):
        with pytest.raises(ValueError):
            push.abonnieren(fritz, falsch, p256dh, auth)
    with pytest.raises(ValueError):
        push.abonnieren(fritz, ADRESSE + "x", "", auth)


@pytest.mark.django_db
def test_schluessel_wird_einmal_erzeugt_und_verschluesselt_gespeichert():
    eins = push.oeffentlicher_schluessel()
    assert eins == push.oeffentlicher_schluessel()
    gespeichert = PushEinstellungen.laden().schluessel
    assert gespeichert and "PRIVATE KEY" not in gespeichert


@pytest.mark.django_db
def test_einschalten_auf_mein_konto(client, admin, anmelden, benutzer_mit_rolle, gesendet):
    fritz = benutzer_mit_rolle("fritz", rollen.AUSGABE)
    erna = benutzer_mit_rolle("erna", rollen.AUSGABE)
    anmelden(client, fritz)
    seite = client.get(reverse("konten:mein_konto")).content.decode()
    assert "Nachrichten auf dieses Gerät" in seite and push.oeffentlicher_schluessel() in seite
    assert reverse("core:push_sw") in seite and "js/push.js" in seite
    _, p256dh, auth = _browser()
    abo = _abo(ADRESSE + "fritz", p256dh, auth)

    def post(name, daten=abo):
        return client.post(reverse(name), daten, content_type="application/json")

    assert post("core:push_stand").json() == {"an": False}
    assert post("core:push_probe").json() == {"ok": False, "gesendet": 0}
    assert post("core:push_an").json() == {"ok": True}
    assert PushAbo.objects.get().benutzer == fritz
    assert post("core:push_stand").json() == {"an": True}
    assert post("core:push_probe").json() == {"ok": True, "gesendet": 1} and len(gesendet) == 1
    # das Gerät eines anderen Kontos ist für mich „aus“ und lässt sich von mir nicht abmelden
    push.abonnieren(erna, ADRESSE + "erna", p256dh, auth)
    fremd = _abo(ADRESSE + "erna", p256dh, auth)
    assert post("core:push_stand", fremd).json() == {"an": False}
    assert post("core:push_aus", fremd).status_code == 200 and push.geraete(erna) == 1
    assert post("core:push_aus").json() == {"ok": True} and push.geraete(fritz) == 0
    # Unsinn wird abgelehnt, nichts gespeichert
    assert post("core:push_an", "kein json").status_code == 400
    assert post("core:push_aus", "[]").status_code == 400
    assert post("core:push_stand", "kein json").status_code == 400
    assert post("core:push_an", _abo("https://example.org/x", p256dh, auth)).status_code == 400
    assert push.geraete(fritz) == 0


@pytest.mark.django_db
def test_service_worker_oeffentlich_ohne_vertrauliches(client, admin):
    antwort = client.get(reverse("core:push_sw"))
    assert antwort.status_code == 200 and reverse("core:push_sw") == "/push-sw.js"
    assert antwort["Content-Type"].startswith("application/javascript")
    text = antwort.content.decode()
    assert "showNotification" in text and "__START__" not in text and "__SYMBOL__" not in text
    for name in ("core:push_an", "core:push_aus", "core:push_stand", "core:push_probe"):
        assert client.post(reverse(name), "{}", content_type="application/json").status_code == 302


@pytest.mark.django_db
def test_konto_einer_ausgabestelle_ohne_kachel(client, admin, anmelden, benutzer_mit_rolle):
    from apps.kunden.models import Ausgabestelle

    konto = benutzer_mit_rolle("stelle-mitte", rollen.AUSGABE)
    konto.stelle = Ausgabestelle.objects.create(name="Mitte")
    konto.save()
    seite = anmelden(client, konto).get(reverse("konten:mein_konto")).content.decode()
    assert "Nachrichten auf dieses Gerät" not in seite


@pytest.mark.django_db(transaction=True)
def test_schluessel_zieht_aus_dem_aufruf_in_den_kern():
    """aufruf.0015: Der bisherige Schlüssel der Tafel gilt weiter (sonst kämen bei Kunden mit
    eingeschalteter Benachrichtigung keine Nachrichten mehr an) – vorwärts und zurück."""
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from tests.test_umbau_migration import _leaves_mit, _migriere

    try:
        _migriere(_leaves_mit({"aufruf": "0014_push_nachrichten"}))
        alt = MigrationExecutor(connection).loader.project_state(
            [("aufruf", "0014_push_nachrichten")]
        ).apps  # fmt: skip
        alt.get_model("aufruf", "HandyEinstellungen").objects.update_or_create(
            pk=1, defaults={"push_schluessel": "gAAAA-erfunden"}
        )
        PushEinstellungen.objects.all().delete()
        _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())
        assert PushEinstellungen.objects.get().schluessel == "gAAAA-erfunden"
        # zurück auf die ältere Version: Der Schlüssel steht wieder im Modul
        PushEinstellungen.objects.update(schluessel="gAAAA-neuer")
        _migriere(_leaves_mit({"aufruf": "0014_push_nachrichten"}))
        with connection.cursor() as c:
            c.execute("SELECT push_schluessel FROM aufruf_handyeinstellungen")
            assert c.fetchall() == [("gAAAA-neuer",)]
    finally:
        _migriere(MigrationExecutor(connection).loader.graph.leaf_nodes())
