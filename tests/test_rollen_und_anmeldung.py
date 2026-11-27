import pytest
from django.contrib.auth.models import AnonymousUser, Group
from django.urls import reverse
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.konten import rollen
from tests.conftest import PASSWORT

pytestmark = pytest.mark.django_db


def test_rollen_als_gruppen_angelegt():
    assert set(Group.objects.values_list("name", flat=True)) >= set(rollen.MITGELIEFERT)
    assert {r.name for r in rollen.alle_rollen()} >= set(rollen.MITGELIEFERT)


def test_rollen_von(benutzer_mit_rolle, admin):
    assert rollen.rollen_von(AnonymousUser()) == set()
    assert rollen.rollen_von(admin) == {rollen.ADMIN}
    kiosk = benutzer_mit_rolle("kiosk", rollen.KIOSK)
    assert rollen.rollen_von(kiosk) == {rollen.KIOSK}
    assert not rollen.ist_admin(kiosk) and rollen.ist_admin(admin)


def test_anmelden_und_abmelden(client, admin):
    antwort = client.post(reverse("konten:anmelden"), {"username": "chefin", "password": PASSWORT})
    assert antwort.status_code == 302
    assert antwort.url == reverse("core:start")
    assert client.get(reverse("konten:anmelden")).status_code == 302  # schon angemeldet
    assert client.get(reverse("konten:abmelden")).status_code == 405  # nur POST
    client.post(reverse("konten:abmelden"))
    assert client.get("/").status_code == 302


def test_anmelden_falsches_passwort(client, admin):
    assert "einschweben" in client.get(reverse("konten:anmelden")).content.decode()
    antwort = client.post(reverse("konten:anmelden"), {"username": "chefin", "password": "nein"})
    assert antwort.status_code == 200
    assert "falsch" in antwort.content.decode()
    assert "einschweben" not in antwort.content.decode()  # nach einem Fehler nicht noch einmal


def test_anmelden_ohne_felder(client, admin):
    antwort = client.post(reverse("konten:anmelden"), {"username": "chefin"})
    assert antwort.status_code == 200


def test_weiterleitung_nur_auf_eigene_seiten(client, admin):
    daten = {"username": "chefin", "password": PASSWORT}
    antwort = client.post(reverse("konten:anmelden"), {**daten, "next": "https://boese.example"})
    assert antwort.url == reverse("core:start")
    client.post(reverse("konten:abmelden"))
    antwort = client.post(reverse("konten:anmelden"), {**daten, "next": "/einstellungen/"})
    assert antwort.url == "/einstellungen/"


def test_admin_login_nutzt_eigene_anmeldung(client, admin):
    antwort = client.get("/admin/login/?next=/admin/")
    assert antwort.status_code == 302
    assert antwort.url.startswith(reverse("konten:anmelden"))


def test_zwei_faktor_wenn_geraet_eingerichtet(client, admin):
    geraet = TOTPDevice.objects.create(user=admin, name="Handy", confirmed=True)
    url, code_url = reverse("konten:anmelden"), reverse("konten:anmelden_code")
    ohne_code = client.post(url, {"username": "chefin", "password": PASSWORT, "next": "/kunden/"})
    assert ohne_code.url == code_url and "_auth_user_id" not in client.session

    falscher_code = client.post(code_url, {"otp_token": "000000"})
    assert falscher_code.status_code == 200

    # Nach einem Fehlversuch sperrt django-otp kurz (Schutz vor Durchprobieren).
    geraet.refresh_from_db()
    assert geraet.throttling_failure_count == 1
    geraet.throttle_reset()

    totp = TOTP(geraet.bin_key, geraet.step, geraet.t0, geraet.digits, geraet.drift)
    code = f"{totp.token():0{geraet.digits}d}"
    antwort = client.post(code_url, {"otp_token": code})
    assert antwort.status_code == 302 and antwort.url == "/kunden/"
    assert client.session.get("otp_device_id")


def test_mein_konto_zeigt_eigene_rollen(client, benutzer_mit_rolle, admin, anmelden):
    anmelden(client, admin)
    inhalt = client.get(reverse("konten:mein_konto")).content.decode()
    assert '<span class="marke-rolle">Admin</span>' in inhalt
    client.post(reverse("konten:abmelden"))

    anmelden(client, benutzer_mit_rolle("zwei", rollen.KIOSK, rollen.AUSGABE))
    inhalt = client.get(reverse("konten:mein_konto")).content.decode()
    # in der festen Reihenfolge der Rollen
    assert inhalt.index(">Ausgabe<") < inhalt.index(">Kiosk<")
    assert "keine – bitte" not in inhalt


def test_zweiter_schritt_nur_kurz_und_mit_wenigen_versuchen(client, admin, anmelden):
    from apps.konten import views

    TOTPDevice.objects.create(user=admin, name="Handy", confirmed=True)
    url, code_url = reverse("konten:anmelden"), reverse("konten:anmelden_code")
    # ohne ersten Schritt geht es nicht
    assert client.get(code_url, follow=True).redirect_chain[-1][0] == url
    client.post(url, {"username": "chefin", "password": PASSWORT})
    for _ in range(views.ZWEITER_SCHRITT_VERSUCHE - 1):
        TOTPDevice.objects.update(throttling_failure_count=0, throttling_failure_timestamp=None)
        assert client.post(code_url, {"otp_token": "000000"}).status_code == 200
    antwort = client.post(code_url, {"otp_token": "000000"}, follow=True)
    assert "Zu viele falsche Codes" in antwort.content.decode()
    # nach Ablauf der Zeit wieder von vorn
    client.post(url, {"username": "chefin", "password": PASSWORT})
    sitzung = client.session
    offen = sitzung[views.SITZUNG_ZWEITER_SCHRITT]
    offen["zeit"] -= views.ZWEITER_SCHRITT_MINUTEN * 60 + 1
    sitzung[views.SITZUNG_ZWEITER_SCHRITT] = offen
    sitzung.save()
    antwort = client.get(code_url, follow=True)
    assert "Bitte zuerst Benutzername und Passwort" in antwort.content.decode()
    # Angemeldete landen auf der Startseite
    anmelden(client, admin)
    assert client.get(code_url).url == reverse("core:start")


def test_impressum_auf_der_anmeldeseite(client, admin):
    from apps.antraege.models import AntragEinstellungen
    from apps.core.models import TafelEinstellungen

    assert "Impressum" not in client.get(reverse("konten:anmelden")).content.decode()
    e = AntragEinstellungen.laden()
    e.impressum_url = "https://tafel.example.org/impressum"
    e.save()
    TafelEinstellungen.objects.update(name="Tafel Musterstadt")
    seite = client.get(reverse("konten:anmelden")).content.decode()
    assert 'href="https://tafel.example.org/impressum" rel="noopener">Impressum der Tafel ' in seite
    assert seite.count("https://tafel.example.org/impressum") == 2  # auch unten in der Fußzeile
    # Externer Link hat Vorrang: der interne Text greift erst, wenn kein Link gesetzt ist – auch im
    # App-/Anmelde-Footer (ADR 0094).
    TafelEinstellungen.objects.update(impressum_text="<p>Impressum der Tafel Musterstadt</p>")
    assert client.get(reverse("konten:anmelden")).content.decode().count(
        "https://tafel.example.org/impressum"
    ) == 2  # Link weiter maßgeblich  # fmt: skip
    e.impressum_url = ""
    e.save()
    intern = reverse("antrag:rechtstext", args=["de", "impressum"])
    seite = client.get(reverse("konten:anmelden")).content.decode()
    assert intern in seite and "tafel.example.org/impressum" not in seite


def test_sperre_nach_zu_vielen_falschen_passwoertern(client, admin):
    """Nach 5 falschen Passwörtern ist auch das richtige kurz gesperrt (Schutz vor Durchprobieren).

    Der Zähler liegt im Datenbank-Cache (ADR 0093), gilt also über alle Prozesse und übersteht
    einen Neustart.
    """
    url = reverse("konten:anmelden")
    for _ in range(5):  # Vorgabe: 5 Fehlversuche
        antwort = client.post(url, {"username": "chefin", "password": "falsch"})
        assert "falsch" in antwort.content.decode()
    # jetzt gesperrt – sogar das richtige Passwort wird abgewiesen
    antwort = client.post(url, {"username": "chefin", "password": PASSWORT})
    assert antwort.status_code == 200 and "Zu viele falsche Versuche" in antwort.content.decode()
    # ein anderes Konto ist nicht betroffen (Zähler je Benutzername)
    assert client.post(url, {"username": "chefin", "password": PASSWORT}).status_code == 200


def test_richtige_anmeldung_setzt_den_zaehler_zurueck(client, admin):
    url = reverse("konten:anmelden")
    for _ in range(4):  # einer weniger als die Grenze (Vorgabe 5)
        client.post(url, {"username": "chefin", "password": "falsch"})
    # richtige Anmeldung klappt noch und löscht den Zähler
    start = reverse("core:start")
    assert client.post(url, {"username": "chefin", "password": PASSWORT}).url == start
    client.post(reverse("konten:abmelden"))
    # danach stehen wieder volle Versuche zur Verfügung
    for _ in range(4):
        client.post(url, {"username": "chefin", "password": "falsch"})
    assert client.post(url, {"username": "chefin", "password": PASSWORT}).url == start


def test_fehlversuche_einstellbar_und_admin_hebt_sperre_auf(admin_client, benutzer_mit_rolle):
    """Die Zahl der Fehlversuche stellt die Tafel ein; ein Admin hebt die Sperre sofort auf
    (ADR 0120)."""
    from django.test import Client

    from apps.konten import anmeldesperre

    client = Client()  # eigener Browser der Person (admin_client ist schon angemeldet)
    from apps.konten.models import AnmeldeEinstellungen

    helfer = benutzer_mit_rolle("helfer", rollen.AUSGABE)
    e = AnmeldeEinstellungen.laden()
    e.fehlversuche, e.sperre_minuten = 8, 30
    e.save()
    url = reverse("konten:anmelden")
    for _ in range(7):
        client.post(url, {"username": "helfer", "password": "falsch"})
    assert not anmeldesperre.ist_gesperrt("helfer")  # 7 von 8: noch nicht gesperrt
    client.post(url, {"username": "helfer", "password": "falsch"})
    assert anmeldesperre.ist_gesperrt("helfer")
    antwort = client.post(url, {"username": "helfer", "password": PASSWORT})
    assert "Bitte 30 Minuten warten" in antwort.content.decode()
    # Der Admin sieht den Knopf bei der Person und hebt die Sperre sofort auf
    seite = admin_client.get(reverse("konten:mitarbeiter", args=[helfer.pk])).content.decode()
    assert "Anmelde-Sperre aufheben" in seite
    admin_client.post(reverse("konten:anmeldesperre_aufheben", args=[helfer.pk]))
    assert not anmeldesperre.ist_gesperrt("helfer")
    assert client.post(url, {"username": "helfer", "password": PASSWORT}).status_code == 302
    seite = admin_client.get(reverse("konten:mitarbeiter", args=[helfer.pk])).content.decode()
    assert "Anmelde-Sperre aufheben" not in seite


@pytest.mark.django_db
def test_datenbank_cache_funktioniert():
    """Der im Betrieb genutzte Datenbank-Cache (ADR 0093) kann setzen, lesen und hochzählen."""
    from django.test import override_settings

    datenbank_cache = {
        "default": {
            "BACKEND": "django.core.cache.backends.db.DatabaseCache",
            "LOCATION": "bintafeln_cache",
        }
    }
    with override_settings(CACHES=datenbank_cache):
        from django.core.cache import cache

        cache.set("probe", 1, 60)
        assert cache.get("probe") == 1
        cache.incr("probe")
        assert cache.get("probe") == 2
        cache.delete("probe")
        assert cache.get("probe") is None


def test_zwei_faktor_neu_einrichten(client, admin, anmelden):
    """„Mein Konto → Zwei-Faktor neu einrichten“ (neues Handy): nur mit einem gültigen Code, und
    die bisherige App gilt, bis die neue bestätigt ist – auch bei Pflicht."""
    from django_otp.plugins.otp_static.models import StaticToken

    from apps.konten import zwei_faktor

    alt = TOTPDevice.objects.create(user=admin, name="App", confirmed=True)
    notfall = zwei_faktor.notfallcodes_erzeugen(admin)
    anmelden(client, admin)
    konto, neu = reverse("konten:mein_konto"), reverse("konten:zwei_faktor_neu")
    einrichten = reverse("konten:zwei_faktor_einrichten")
    assert zwei_faktor.ist_pflicht(admin)
    assert "Zwei-Faktor neu einrichten" in client.get(konto).content.decode()
    # ohne Freigabe kommt man nicht zur Einrichtung; ein falscher Code gibt nichts frei
    assert client.get(einrichten).url == konto
    assert client.post(neu, {"code": "000000"}).url == konto
    assert client.get(einrichten).url == konto
    assert not TOTPDevice.objects.filter(user=admin, confirmed=False).exists()
    # (nach einem Fehlversuch sperrt django-otp kurz – Schutz vor Durchprobieren)
    from django_otp.plugins.otp_static.models import StaticDevice

    for g in [*TOTPDevice.objects.filter(user=admin), *StaticDevice.objects.filter(user=admin)]:
        g.throttle_reset()
    # mit einem Notfallcode: weiter zur Einrichtung, die alte App gilt noch
    assert client.post(neu, {"code": notfall[0]}).url == einrichten
    seite = client.get(einrichten).content.decode()
    assert "Zwei-Faktor neu einrichten" in seite and "Die bisherige App gilt noch" in seite
    geraet = TOTPDevice.objects.get(user=admin, confirmed=False)
    assert TOTPDevice.objects.filter(pk=alt.pk, confirmed=True).exists()
    # falscher Code der neuen App: nichts ändert sich
    client.post(einrichten, {"code": "000000"})
    assert TOTPDevice.objects.filter(pk=alt.pk, confirmed=True).exists()
    geraet.refresh_from_db()
    geraet.throttle_reset()
    totp = TOTP(geraet.bin_key, geraet.step, geraet.t0, geraet.digits, geraet.drift)
    antwort = client.post(einrichten, {"code": f"{totp.token():0{geraet.digits}d}"})
    assert antwort.status_code == 200 and "Notfallcode" in antwort.content.decode()
    # jetzt gilt nur noch das neue Gerät, mit neuen Notfallcodes
    assert list(TOTPDevice.objects.filter(user=admin)) == [geraet]
    geraet.refresh_from_db()
    assert geraet.confirmed
    neue = set(StaticToken.objects.filter(device__user=admin).values_list("token", flat=True))
    assert len(neue) == 10 and not neue & set(notfall)
    assert client.session.get("otp_device_id") == geraet.persistent_id
    # die Freigabe ist verbraucht
    assert client.get(einrichten).url == konto
    # nach 15 Minuten verfällt eine Freigabe von selbst
    sitzung = client.session
    sitzung[zwei_faktor.NEU_SITZUNG] = 1.0
    sitzung.save()
    assert client.get(einrichten).url == konto


def test_zwei_faktor_neu_ohne_einrichtung_fuehrt_zur_einrichtung(client, admin, benutzer_mit_rolle):
    b = benutzer_mit_rolle("ohne2fa", rollen.AUSGABE)
    client.force_login(b)
    antwort = client.post(reverse("konten:zwei_faktor_neu"), {"code": "123456"})
    assert antwort.url == reverse("konten:zwei_faktor_einrichten")
