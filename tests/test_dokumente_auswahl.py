import datetime as dt

import pytest
from auditlog.models import LogEntry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.core import papierkorb, privatdateien
from apps.core.auswahl import ANREDEN, mit_vorhandenem
from apps.core.models import PapierkorbEintrag
from apps.konten import personal, rollen, verwaltung
from apps.konten.forms import StammdatenForm
from apps.konten.models import Dokument, DokumentKategorie, Rolle, Stammdaten

pytestmark = pytest.mark.django_db


@pytest.fixture
def kim(benutzer_mit_rolle):
    return benutzer_mit_rolle("kim", rollen.FAHRER)


def pdf(inhalt=b"%PDF erfundenes Dokument"):
    return SimpleUploadedFile("d.pdf", inhalt, content_type="application/pdf")


def kategorie(name):
    return DokumentKategorie.objects.get(name=name)


def hochladen(client, ziel, name="Sonstiges", **mehr):
    daten = {"kategorie": kategorie(name).pk, "titel": f"Testdokument {name}", "datei": pdf(),
             **mehr}  # fmt: skip
    return client.post(reverse("konten:dokument_hochladen", args=[ziel.pk]), daten, follow=True)


# --- Dokumente ---------------------------------------------------------------------------


def test_vorgabe_kategorien():
    namen = dict(DokumentKategorie.objects.values_list("name", "nur_personal"))
    assert namen["Arbeitsvertrag"] and namen["Lohnunterlagen"] and not namen["Sonstiges"]
    assert str(kategorie("Sonstiges")) == "Sonstiges"


def test_hochladen_ansehen_loeschen(admin_client, kim, django_capture_on_commit_callbacks):
    seite = reverse("konten:stammdaten", args=[kim.pk])
    antwort = hochladen(admin_client, kim, weiter=seite, datum="2026-10-01")
    assert "Dokument verschlüsselt gespeichert." in antwort.content.decode()
    d = Dokument.objects.get()
    assert (d.hochgeladen_von, str(d)) == ("chefin", "Testdokument Sonstiges")
    assert b"erfundenes" not in privatdateien.pfad(Dokument.ORDNER, d.datei).read_bytes()
    ansehen = reverse("konten:dokument_ansehen", args=[kim.pk, d.pk])
    assert admin_client.get(ansehen).content == b"%PDF erfundenes Dokument"
    assert LogEntry.objects.get_for_object(d).filter(action=LogEntry.Action.ACCESS).exists()
    assert "Testdokument Sonstiges" in admin_client.get(seite).content.decode()
    admin_client.post(reverse("konten:dokument_loeschen", args=[kim.pk, d.pk]))
    assert not Dokument.objects.exists()
    datei = privatdateien.pfad(Dokument.ORDNER, d.datei)
    # Die Datei bleibt im Papierkorb, bis er geleert wird (ADR 0073)
    assert datei.exists()
    with django_capture_on_commit_callbacks(execute=True):
        papierkorb.endgueltig_loeschen(PapierkorbEintrag.objects.get())
    assert not datei.exists()


def test_hochladen_fehler_und_fremde_weiterleitung(admin_client, kim):
    url = reverse("konten:dokument_hochladen", args=[kim.pk])
    antwort = admin_client.post(url, {"titel": "x", "weiter": "https://example.org/"})
    assert antwort.url == reverse("konten:stammdaten", args=[kim.pk])
    falsch = SimpleUploadedFile("d.txt", b"x", content_type="text/plain")
    seite = admin_client.post(url, {"kategorie": kategorie("Sonstiges").pk, "titel": "x",
                                    "datei": falsch}, follow=True).content.decode()  # fmt: skip
    assert "PDF" in seite and not Dokument.objects.exists()


def test_unlesbares_dokument(admin_client, kim):
    hochladen(admin_client, kim)
    d = Dokument.objects.get()
    privatdateien.pfad(Dokument.ORDNER, d.datei).unlink()
    assert (
        admin_client.get(reverse("konten:dokument_ansehen", args=[kim.pk, d.pk])).status_code == 404
    )


def test_nur_personal_dokumente(client, admin, benutzer_mit_rolle, anmelden, admin_client, kim):
    hochladen(admin_client, kim, "Arbeitsvertrag")
    hochladen(admin_client, kim, "Sonstiges")
    vertrag = Dokument.objects.get(kategorie__name="Arbeitsvertrag")
    Rolle.objects.filter(gruppe__name="Büro").update(
        rechte=Rolle.objects.get(gruppe__name="Büro").rechte + ["mitarbeitende.verwalten"]
    )
    admin_client.logout()

    anmelden(client, benutzer_mit_rolle("buero", rollen.BUERO))
    seite = client.get(reverse("konten:stammdaten", args=[kim.pk])).content.decode()
    assert "Testdokument Sonstiges" in seite and "Testdokument Arbeitsvertrag" not in seite
    assert '">Arbeitsvertrag</option>' not in seite  # nicht als Kategorie wählbar
    ansehen = reverse("konten:dokument_ansehen", args=[kim.pk, vertrag.pk])
    assert client.get(ansehen).status_code == 404
    assert client.get(reverse("konten:dokument_ansehen", args=[kim.pk, 999])).status_code == 404
    client.logout()

    anmelden(client, benutzer_mit_rolle("hr", rollen.PERSONAL))
    seite = client.get(reverse("personal:person", args=[kim.pk])).content.decode()
    assert "Testdokument Arbeitsvertrag" in seite and "nur Personal" in seite
    assert client.get(ansehen).status_code == 200


def test_ohne_recht_kein_zugriff(client, admin, benutzer_mit_rolle, anmelden, kim):
    anmelden(client, benutzer_mit_rolle("ausgabe", rollen.AUSGABE))
    url = reverse("konten:dokument_hochladen", args=[kim.pk])
    assert client.post(url, {}).status_code == 403


def test_kategorien_pflegen(admin_client, kim):
    seite = reverse("konten:personal_einstellungen")
    assert "Dokumentkategorien" in admin_client.get(seite).content.decode()
    admin_client.post(reverse("konten:kategorie_neu"), {"name": "Führungszeugnis",
                                                        "nur_personal": "on"})  # fmt: skip
    assert kategorie("Führungszeugnis").nur_personal
    doppelt = admin_client.post(reverse("konten:kategorie_neu"), {"name": "Führungszeugnis"},
                                follow=True).content.decode()  # fmt: skip
    assert "gibt es schon" in doppelt
    hochladen(admin_client, kim, "Sonstiges")
    loeschen = reverse("konten:kategorie_loeschen", args=[kategorie("Sonstiges").pk])
    belegt = admin_client.post(loeschen, follow=True).content.decode()
    assert "enthält noch Dokumente" in belegt
    admin_client.post(reverse("konten:kategorie_loeschen", args=[kategorie("Führungszeugnis").pk]))
    assert not DokumentKategorie.objects.filter(name="Führungszeugnis").exists()


def test_loeschfrist_entfernt_dokumente(admin, admin_client, kim):
    hochladen(admin_client, kim)
    d = Dokument.objects.get()
    verwaltung.sperren(admin, kim)
    kim.__class__.objects.filter(pk=kim.pk).update(
        gesperrt_am=timezone.now() - dt.timedelta(days=5 * 365)
    )
    assert personal.stammdaten_leeren() == 1
    assert not Dokument.objects.exists()
    assert not privatdateien.pfad(Dokument.ORDNER, d.datei).exists()


# --- Auswahl statt Freitext ---------------------------------------------------------------


def test_mit_vorhandenem():
    assert mit_vorhandenem(ANREDEN, "Herr") == ANREDEN
    assert mit_vorhandenem(ANREDEN, "Dr.")[-1] == ("Dr.", "Dr.")


def test_stammdaten_auswahlfelder(admin_client, admin, kim):
    seite = admin_client.get(reverse("konten:stammdaten", args=[kim.pk])).content.decode()
    assert '<option value="Frau">Frau</option>' in seite
    assert 'value="C1E"' in seite and 'type="checkbox"' in seite
    assert '<option value="chefin" selected>chefin</option>' in seite  # vorbelegt
    admin_client.post(
        reverse("konten:stammdaten", args=[kim.pk]),
        {"anrede": "Herr", "fs_klassen": ["B", "C1"], "fs_gesehen_am": "2026-10-01",
         "fs_gesehen_von": "kim"},
    )  # fmt: skip
    s = Stammdaten.objects.get(benutzer=kim)
    assert (s.anrede, s.fs_klassen, s.fs_gesehen_von) == ("Herr", "B, C1", "kim")
    nicht_erlaubt = admin_client.post(reverse("konten:stammdaten", args=[kim.pk]),
                                      {"fs_gesehen_von": "jemand anderes"})  # fmt: skip
    assert nicht_erlaubt.status_code == 200  # nur registrierte Mitarbeitende


def test_ohne_datum_kein_gesehen_von(admin, kim):
    form = StammdatenForm({"fs_gesehen_von": "chefin"}, instance=Stammdaten(benutzer=kim),
                          angemeldet=admin)  # fmt: skip
    assert form.is_valid() and form.cleaned_data["fs_gesehen_von"] == ""


def test_alte_werte_bleiben_waehlbar(admin, kim):
    s = Stammdaten.objects.create(benutzer=kim, anrede="Dr.", fs_klassen="B, 2 (alt)",
                                  fs_gesehen_von="Ehemalige Person")  # fmt: skip
    form = StammdatenForm(instance=s, angemeldet=admin)
    assert ("Dr.", "Dr.") in form.fields["anrede"].choices
    assert ("2 (alt)", "2 (alt)") in form.fields["fs_klassen"].choices
    assert form.initial["fs_klassen"] == ["B", "2 (alt)"]
    assert ("Ehemalige Person", "Ehemalige Person") in form.fields["fs_gesehen_von"].choices
    assert form.initial["fs_gesehen_von"] == "Ehemalige Person"
