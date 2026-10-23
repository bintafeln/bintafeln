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
