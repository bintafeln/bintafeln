"""Post der Verwaltung an die Ausgabestellen mit der Eule in der Kopfzeile (ADR 0142).
Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen
from apps.kunden import eulenpost
from apps.kunden.models import Ausgabestelle, PostEmpfang, Rundschreiben, alte_nachrichten_loeschen

pytestmark = pytest.mark.django_db
SCHREIBEN = reverse("kunden:post_schreiben")
POSTFACH = reverse("kunden:postfach")


@pytest.fixture
def stellen(admin, benutzer_mit_rolle, anmelden):
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    Ausgabestelle.objects.create(name="Alt", aktiv=False)
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.ausgabestellen.set([mitte])
    return anmelden(Client(), anton), mitte, nord


def test_schreiben_eule_lesen(stellen, admin_client):
    c, mitte, nord = stellen
    seite = admin_client.get(SCHREIBEN).content.decode()
    # nur aktive Ausgabestellen – am Auswahlfeld geprüft, nicht am bloßen Wort „Alt“: Das stand
    # sonst zufällig auch einmal im Sicherheits-Token der Seite
    assert "Eule losschicken" in seite and "> Mitte</label>" in seite
    assert "> Alt</label>" not in seite
    # nichts angehakt = alle aktiven
    antwort = admin_client.post(SCHREIBEN, {"betreff": "Kühlware", "text": "Morgen keine Kühlware.",
                                            "wichtig": "on"})  # fmt: skip
    assert antwort.url == SCHREIBEN
    r = Rundschreiben.objects.get()
    assert r.wichtig and r.von == "chefin"
    assert sorted(e.stelle.name for e in r.empfaenge.all()) == ["Mitte", "Nord"]
    admin_client.post(SCHREIBEN, {"stellen": [nord.pk], "betreff": "Nur Nord", "text": "Hallo"})
    assert PostEmpfang.objects.filter(stelle=mitte).count() == 1
    # Ausgabestelle: Eule in der Kopfzeile (auch am Einlass), wichtige Post als Hinweis
    start = c.get("/").content.decode()
    assert 'id="eulenpost"' in start and 'class="eulen-landeplatz"' in start
    assert "eulen-wichtig" in start and "Morgen keine Kühlware." in start
    kopf = c.get(reverse("kunden:post_kopf")).content.decode()
    assert 'data-schluessel="' in kopf and "1 neue Post" in kopf
    # Die Kopfzeile lädt sich jede Minute neu: „Gelesen“ führt dann auf die Seite zurück, auf der
    # man ist – nie auf das Stück Kopfzeile selbst (das wäre eine weiße Seite)
    kopf_adresse = reverse("kunden:post_kopf")
    assert f'name="zurueck" value="{kopf_adresse}"' not in kopf
    assert f'name="zurueck" value="{POSTFACH}"' in kopf  # ohne Angabe: Postfach
    seite = "http://testserver/ausgabe/?nummer=42"
    kopf = c.get(kopf_adresse, headers={"HX-Current-URL": seite}).content.decode()
    assert 'name="zurueck" value="http://testserver/ausgabe/?nummer=42"' in kopf
    assert "Nur Nord" not in c.get(POSTFACH).content.decode()
    empfang = PostEmpfang.objects.get(stelle=mitte)
    gelesen = reverse("kunden:post_gelesen", args=[empfang.pk])
    assert c.post(gelesen, {"zurueck": "https://boese.example/"}).url == POSTFACH
    assert c.post(gelesen, {"zurueck": kopf_adresse}).url == POSTFACH
    assert c.post(gelesen, {"zurueck": seite}).url == seite
    empfang.refresh_from_db()
    assert empfang.gelesen_am and empfang.gelesen_von == "anton"
    assert "eulen-landeplatz" not in c.get("/").content.decode()
    # HTMX: frische Kopfzeile ohne Eule
    htmx = c.post(gelesen, headers={"HX-Request": "true"}).content.decode()
    assert 'id="eulenpost"' in htmx and "eulen-landeplatz" not in htmx
    # fremde Post kann man nicht als gelesen markieren
    fremd = PostEmpfang.objects.get(stelle=nord, rundschreiben__betreff="Nur Nord")
    assert c.post(reverse("kunden:post_gelesen", args=[fremd.pk])).status_code == 404
    # Verwaltung sieht den Lesestand
    gesendet = admin_client.get(SCHREIBEN).content.decode()
    assert "Mitte: ✓ gelesen" in gesendet and "noch nicht gelesen" in gesendet
    # die Ausgabestelle darf nicht schreiben
    assert c.get(SCHREIBEN).status_code == 403


def test_ohne_aktive_stellen_und_frist(admin, admin_client):
    Ausgabestelle.objects.create(name="Alt", aktiv=False)
    antwort = admin_client.post(SCHREIBEN, {"betreff": "x", "text": "y"})
    assert "keine aktive Ausgabestelle" in antwort.content.decode()
    mitte = Ausgabestelle.objects.create(name="Mitte")
    alt = eulenpost.schreiben([mitte], admin, "Alt", "Text")
    Rundschreiben.objects.filter(pk=alt.pk).update(
        erstellt_am=timezone.now() - dt.timedelta(days=91))  # fmt: skip
    alte_nachrichten_loeschen()
    assert Rundschreiben.objects.filter(pk=alt.pk).exists()  # noch nicht gelesen: bleibt
    eulenpost.gelesen(alt.empfaenge.get(), admin)
    alte_nachrichten_loeschen()
    assert not Rundschreiben.objects.filter(pk=alt.pk).exists()
    assert eulenpost.stand(None) == {"zahl": 0, "wichtig": None, "schluessel": ""}
    assert not eulenpost.postfach(None).exists()
    assert "Post der Verwaltung an Mitte" in admin_client.get(POSTFACH).content.decode()


def test_post_ganz_loeschen(stellen, admin_client):
    from apps.core.models import PapierkorbEintrag

    c, mitte, nord = stellen
    admin_client.post(SCHREIBEN, {"betreff": "Versehen", "text": "Falsch geschickt"})
    r = Rundschreiben.objects.get()
    empfang = PostEmpfang.objects.get(stelle=mitte)
    eulenpost.gelesen(empfang, r.benutzer)  # gelesen oder nicht: beide verschwinden
    assert "Löschen</button>" in admin_client.get(SCHREIBEN).content.decode()
    url = reverse("kunden:post_loeschen", args=[r.pk])
    assert c.post(url).status_code == 403  # die Ausgabestelle darf das nicht
    assert admin_client.get(url).status_code == 405
    assert admin_client.post(url).url == SCHREIBEN
    assert not Rundschreiben.objects.exists() and not PostEmpfang.objects.exists()
    assert "Falsch geschickt" not in c.get(POSTFACH).content.decode()
    assert PapierkorbEintrag.objects.get().art == "Post an Ausgabestellen"


def test_post_im_menue_unter_einstellungen_ausgabe(admin):
    from django.test import RequestFactory

    from apps.core.menue import menue

    anfrage = RequestFactory().get("/")
    anfrage.user = admin
    bereiche = {b["titel"]: str(b) for b in menue(anfrage)}
    ziel = reverse("kunden:post_schreiben")
    # Alles Verwalten der Ausgabe steht an einem Ort: Einstellungen → Ausgabe
    assert ziel in bereiche["Einstellungen"]
    assert ziel not in bereiche["Ausgabestelle"] and ziel not in bereiche.get("Kunden", "")
