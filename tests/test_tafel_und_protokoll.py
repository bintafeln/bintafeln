import io

import pytest
from auditlog.models import LogEntry
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from apps.core.forms import LOGO_MAX_BYTES
from apps.core.models import TafelEinstellungen
from apps.konten import rollen

pytestmark = pytest.mark.django_db


def png(name="logo.png"):
    puffer = io.BytesIO()
    Image.new("RGB", (4, 4), "green").save(puffer, "PNG")
    return SimpleUploadedFile(name, puffer.getvalue(), content_type="image/png")


def test_einstellungen_sind_singleton():
    erste = TafelEinstellungen.laden()
    zweite = TafelEinstellungen(name="Andere")
    zweite.save()
    assert TafelEinstellungen.objects.count() == 1
    assert erste.pk == zweite.pk
    assert str(TafelEinstellungen.laden()) == "Andere"
    with pytest.raises(ValueError):
        zweite.delete()


def test_anschrift_und_str():
    leer = TafelEinstellungen.laden()
    assert str(leer) == "Tafel-Einstellungen"
    assert leer.anschrift == ""
    leer.strasse, leer.plz, leer.ort = "Hauptstr. 1", "12345", "Musterstadt"
    assert leer.anschrift == "Hauptstr. 1, 12345 Musterstadt"


@pytest.mark.parametrize("rolle", [rollen.BUERO, rollen.AUSGABE, rollen.KIOSK])
def test_nur_admin_darf_einstellungen(client, admin, benutzer_mit_rolle, anmelden, rolle):
    anmelden(client, benutzer_mit_rolle("person", rolle))
    assert client.get(reverse("core:einstellungen")).status_code == 403
    assert client.get(reverse("core:protokoll")).status_code == 403


def test_einstellungen_anonym_zur_anmeldung(client, admin):
    antwort = client.get(reverse("core:einstellungen"))
    assert antwort.status_code == 302
    assert antwort.url.startswith(reverse("konten:anmelden"))


def test_einstellungen_speichern_mit_logo_und_protokoll(admin_client, admin):
    antwort = admin_client.post(
        reverse("core:einstellungen"),
        {"name": "Tafel Musterstadt", "ort": "Musterstadt", "logo": png()},
    )
    assert antwort.status_code == 302
    einstellungen = TafelEinstellungen.laden()
    assert einstellungen.name == "Tafel Musterstadt"
    assert einstellungen.logo.name.startswith("oeffentlich/logo/")

    eintrag = LogEntry.objects.get_for_object(einstellungen).latest("timestamp")
    assert eintrag.actor == admin
    assert "name" in eintrag.changes_dict

    seite = admin_client.get("/").content.decode()
    assert "Tafel Musterstadt" in seite
    assert einstellungen.logo.url in seite


def test_logo_zu_gross(admin_client, monkeypatch):
    monkeypatch.setattr("apps.core.forms.LOGO_MAX_BYTES", 10)
    antwort = admin_client.post(reverse("core:einstellungen"), {"name": "X", "logo": png()})
    assert antwort.status_code == 200
    assert "höchstens 2 MB" in antwort.content.decode()
    assert LOGO_MAX_BYTES == 2 * 1024 * 1024


def test_kein_svg_als_logo(admin_client):
    svg = SimpleUploadedFile("logo.svg", b"<svg onload='alert(1)'/>", content_type="image/svg+xml")
    antwort = admin_client.post(reverse("core:einstellungen"), {"name": "X", "logo": svg})
    assert antwort.status_code == 200
    assert not TafelEinstellungen.laden().logo


def test_benutzeraenderung_wird_protokolliert_ohne_passwort(admin, django_user_model):
    person = django_user_model.objects.create_user(username="neu", password="geheim-geheim")
    person.first_name = "Neu"
    person.set_password("noch-geheimer-1")
    person.save()
    for eintrag in LogEntry.objects.get_for_object(person):
        assert "password" not in eintrag.changes_dict


def test_protokoll_ansicht_und_htmx_filter(admin_client):
    einstellungen = TafelEinstellungen.laden()
    einstellungen.name = "Eins"
    einstellungen.save()
    antwort = admin_client.get(reverse("core:protokoll"))
    inhalt = antwort.content.decode()
    assert antwort.status_code == 200
    assert "<html" in inhalt and "Eins" in inhalt
    assert "Angelegt" in inhalt and "Geändert" in inhalt

    eintrag = LogEntry.objects.get_for_object(TafelEinstellungen.laden()).first()
    teil = admin_client.get(
        reverse("core:protokoll"),
        {"modell": eintrag.content_type_id},
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="protokoll-liste",
    )
    assert "<html" not in teil.content.decode()
    assert "Eins" in teil.content.decode()

    leer = admin_client.get(reverse("core:protokoll"), {"modell": 999999, "seite": "x"})
    assert "Noch keine Einträge" in leer.content.decode()


def test_protokoll_blaettern(admin_client):
    einstellungen = TafelEinstellungen.laden()
    for nummer in range(55):
        einstellungen.name = f"Name {nummer}"
        einstellungen.save()
    inhalt = admin_client.get(reverse("core:protokoll"), {"seite": 2}).content.decode()
    assert "Seite 2 von" in inhalt
    assert "« Neuer" in inhalt


def test_404_seite(admin_client):
    antwort = admin_client.get("/gibt-es-nicht/")
    assert antwort.status_code == 404


def test_verwaltung_einstellungen_nicht_doppelt_oder_loeschbar(admin_client):
    url = reverse("admin:core_tafeleinstellungen_add")
    assert admin_client.get(url).status_code == 200
    TafelEinstellungen.laden()
    assert admin_client.get(url).status_code == 403
    loeschen = reverse("admin:core_tafeleinstellungen_delete", args=[1])
    assert admin_client.get(loeschen).status_code == 403


def test_protokoll_zeigt_loeschen_und_abruf(admin_client, django_user_model):
    from auditlog.models import LogEntry as Eintrag

    person = django_user_model.objects.create_user(username="weg", password="x")
    person.delete()
    Eintrag.objects.create(
        content_type=Eintrag.objects.first().content_type,
        object_pk="1",
        object_repr="Abruf",
        action=Eintrag.Action.ACCESS,
    )
    person2 = django_user_model.objects.create_user(username="bleibt", password="x")
    person2.groups.add(Group.objects.get(name=rollen.KIOSK))
    inhalt = admin_client.get(reverse("core:protokoll")).content.decode()
    assert "hinzugefügt: Kiosk" in inhalt
    assert "Gelöscht" in inhalt
    assert "Abgerufen" in inhalt


def test_hintergrundbild(admin_client, monkeypatch):
    url = reverse("core:einstellungen")
    seite = admin_client.get(url).content.decode()
    assert 'type="range"' in seite and "Aktuell 15 %" in seite
    assert 'class="hintergrund"' not in seite  # ohne Bild kein Hintergrund
    admin_client.post(url, {"name": "X", "hintergrund_anmeldung": png("bild.png"),
                            "hintergrund_staerke": "30"})  # fmt: skip
    t = TafelEinstellungen.laden()
    assert t.hintergrund_anmeldung.name.startswith("oeffentlich/hintergrund/")
    assert t.hintergrund_bild == t.hintergrund_anmeldung and t.hintergrund_deckkraft == "0.30"
    seite = admin_client.get("/").content.decode()
    assert f"url('{t.hintergrund_anmeldung.url}'); opacity: 0.30;" in seite
    admin_client.post(url, {"name": "X", "hintergrund": png("seiten.png"),
                            "hintergrund_staerke": "0"})  # fmt: skip
    t = TafelEinstellungen.laden()
    assert t.hintergrund_bild == t.hintergrund and t.hintergrund_staerke == 0
    assert 'class="hintergrund"' not in admin_client.get("/").content.decode()  # 0 % = aus
    seite = admin_client.get(url).content.decode()
    assert 'class="bild-vorschau"' in seite and "Bild entfernen" in seite
    assert "Zurücksetzen" not in seite and "Derzeit" not in seite
    admin_client.post(url, {"name": "X", "hintergrund-clear": "on", "hintergrund_staerke": "0"})
    assert not TafelEinstellungen.laden().hintergrund  # nur dieses Bild entfernt
    assert TafelEinstellungen.laden().hintergrund_anmeldung
    monkeypatch.setattr("apps.core.forms.HINTERGRUND_MAX_BYTES", 10)
    fehler = admin_client.post(url, {"name": "X", "hintergrund": png()}).content.decode()
    assert "höchstens 5 MB" in fehler
    from django.test import Client  # admin_client ist derselbe Client wie client

    anmeldung = Client().get(reverse("konten:anmelden")).content.decode()
    assert f"url('{t.hintergrund_anmeldung.url}');\"" in anmeldung  # volle Stärke


def test_mehrere_hintergrundbilder_wechseln(admin_client):
    from django.test import Client  # admin_client ist derselbe Client wie client

    from apps.core.models import Hintergrundbild, PapierkorbEintrag

    url = reverse("core:einstellungen")
    seite = admin_client.get(url).content.decode()
    assert 'name="weitere_anmeldung"' in seite and "multiple" in seite
    assert 'name="hintergrund_wechsel"' in seite and "Weitere Hintergrundbilder" not in seite
    admin_client.post(url, {"name": "X", "hintergrund_anmeldung": png("a.png"),
                            "weitere_anmeldung": [png("b.png"), png("c.png")],
                            "hintergrund_staerke": "30", "hintergrund_wechsel": "20"})  # fmt: skip
    t = TafelEinstellungen.laden()
    assert t.hintergrund_wechsel == 20
    weitere = list(Hintergrundbild.objects.all())
    assert [h.bereich for h in weitere] == ["anmeldung", "anmeldung"]
    assert [h.reihenfolge for h in weitere] == [1, 2]
    assert len(t.anmeldung_bilder) == 3 and t.seiten_bilder == t.anmeldung_bilder  # ohne eigene

    anmeldung = Client().get(reverse("konten:anmelden")).content.decode()
    assert f'data-bilder="{" ".join(t.anmeldung_bilder)}"' in anmeldung
    assert 'data-sekunden="20" data-bereich="anmeldung"' in anmeldung
    assert "hintergrund.js" in anmeldung
    start = admin_client.get("/").content.decode()
    assert 'data-bereich="seiten"' in start and "opacity: 0.30;" in start

    # Eigene Bilder für die übrigen Seiten; eins entfernen (Papierkorb)
    admin_client.post(url, {"name": "X", "weitere_seiten": [png("d.png")],
                            "hintergrund_staerke": "30"})  # fmt: skip
    t = TafelEinstellungen.laden()
    assert len(t.seiten_bilder) == 1 and "/hintergrund/d" in t.seiten_bilder[0]
    start = admin_client.get("/").content.decode()
    assert "data-bilder" not in start and "hintergrund.js" not in start  # ein Bild: kein Wechsel
    seite = admin_client.get(url).content.decode()
    assert "Weitere Hintergrundbilder" in seite and "übrige Seiten" in seite
    seiten_bild = Hintergrundbild.objects.get(bereich="seiten")
    admin_client.post(reverse("core:hintergrund_entfernen", args=[seiten_bild.pk]))
    assert not Hintergrundbild.objects.filter(bereich="seiten").exists()
    assert PapierkorbEintrag.objects.get().art == "Hintergrundbild"
    assert TafelEinstellungen.laden().seiten_bilder == TafelEinstellungen.laden().anmeldung_bilder
