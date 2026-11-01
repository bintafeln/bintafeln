import datetime as dt

import pytest
from auditlog.models import LogEntry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.konten import personal, rollen, verwaltung
from apps.konten.models import PersonalEinstellungen, Schulung, Stammdaten

pytestmark = pytest.mark.django_db

HEUTE = dt.date(2026, 10, 24)


def url(name, ziel, *args):
    return reverse(f"konten:{name}", args=[ziel.pk, *args])


@pytest.fixture(autouse=True)
def fristen():
    """Wiedervorlagen eingeschaltet (Vorgabe ist 0 = keine)."""
    PersonalEinstellungen.objects.update_or_create(
        pk=PersonalEinstellungen.EINZIGE_ID,
        defaults={"fs_pruefung_monate": 6, "ifsg_wiederholung_monate": 24},
    )


@pytest.fixture
def fahrer(benutzer_mit_rolle):
    return benutzer_mit_rolle("kim", rollen.FAHRER)


@pytest.fixture
def kopien_erlaubt():
    e = PersonalEinstellungen.laden()
    e.fs_kopie_erlaubt = True
    e.save()


def bild(name="fs.jpg", inhalt=b"\xff\xd8 erfundenes Bild", typ="image/jpeg"):
    return SimpleUploadedFile(name, inhalt, content_type=typ)


def was(faelligkeiten, benutzer=None):
    return [(f.was, f.faellig_am) for f in faelligkeiten if benutzer in (None, f.benutzer)]


# --- Datumsrechnung ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("datum", "monate", "ergebnis"),
    [
        (dt.date(2026, 1, 31), 1, dt.date(2026, 2, 28)),
        (dt.date(2026, 10, 24), 6, dt.date(2027, 4, 24)),
        (dt.date(2026, 3, 31), -36, dt.date(2023, 3, 31)),
    ],
)
def test_monate_spaeter(datum, monate, ergebnis):
    assert personal.monate_spaeter(datum, monate) == ergebnis


# --- Wiedervorlagen ----------------------------------------------------------------------


def test_fahrer_ohne_angaben_ist_ueberfaellig(fahrer):
    faellig = personal.faelligkeiten(HEUTE)
    assert was(faellig, fahrer) == [("Führerschein ansehen", None), ("Belehrung nach IfSG", None)]
    assert all(f.ueberfaellig for f in faellig)


def test_fahrer_mit_aktuellen_angaben(fahrer):
    Stammdaten.objects.create(
        benutzer=fahrer,
        fs_gesehen_am=dt.date(2026, 9, 1),
        fs_gueltig_bis=dt.date(2030, 1, 1),
        ifsg_erstbelehrung_am=dt.date(2020, 1, 1),
        ifsg_belehrung_am=dt.date(2026, 1, 1),
    )
    assert personal.faelligkeiten(HEUTE) == []


def test_faellig_innerhalb_des_vorlaufs(fahrer):
    Stammdaten.objects.create(
        benutzer=fahrer,
        fs_gesehen_am=dt.date(2026, 5, 1),  # + 6 Monate = 01.11.2026, im Vorlauf
        fs_gueltig_bis=dt.date(2026, 11, 2),
        ifsg_erstbelehrung_am=dt.date(2024, 11, 1),
    )
    assert was(personal.faelligkeiten(HEUTE)) == [
        ("Führerschein läuft ab", dt.date(2026, 11, 2)),
        ("Führerschein ansehen", dt.date(2026, 11, 1)),
        ("Belehrung nach IfSG", dt.date(2026, 11, 1)),
    ]
    f = personal.faelligkeiten(HEUTE)[0]
    assert not f.ueberfaellig


def test_ifsg_nur_fuer_lebensmittel_rollen(benutzer_mit_rolle, admin):
    benutzer_mit_rolle("kiosk", rollen.KIOSK)
    ausgabe = benutzer_mit_rolle("ausgabe", rollen.AUSGABE)
    assert was(personal.faelligkeiten(HEUTE)) == [("Belehrung nach IfSG", None)]
    assert personal.faelligkeiten(HEUTE)[0].benutzer == ausgabe


def test_schulungen_juengste_je_thema(benutzer_mit_rolle, admin):
    b = benutzer_mit_rolle("buero", rollen.BUERO)
    Schulung.objects.create(benutzer=b, thema="Erste Hilfe", datum=dt.date(2023, 1, 1),
                            gueltig_bis=dt.date(2025, 1, 1))  # fmt: skip
    Schulung.objects.create(benutzer=b, thema="erste hilfe ", datum=dt.date(2025, 1, 1),
                            gueltig_bis=dt.date(2027, 1, 1))  # fmt: skip
    Schulung.objects.create(benutzer=b, thema="Hygiene", datum=dt.date(2024, 1, 1),
                            gueltig_bis=dt.date(2026, 10, 1))  # fmt: skip
    Schulung.objects.create(benutzer=b, thema="Gabelstapler", datum=dt.date(2024, 1, 1))
    assert was(personal.faelligkeiten(HEUTE), b) == [("Schulung „Hygiene“", dt.date(2026, 10, 1))]
    assert str(Schulung.objects.get(thema="Hygiene")) == "Hygiene am 01.01.2024"


def test_gesperrte_zaehlen_nicht(fahrer, admin):
    verwaltung.sperren(admin, fahrer)
    assert personal.faelligkeiten(HEUTE) == []


# --- Löschfrist ---------------------------------------------------------------------------


def test_stammdaten_leeren(fahrer, admin, benutzer_mit_rolle, kopien_erlaubt):
    s = Stammdaten.objects.create(
        benutzer=fahrer, strasse="Musterweg 1", telefon="0000 1", eintritt=dt.date(2015, 1, 1),
        austritt=dt.date(2022, 6, 30), fs_klassen="B", ifsg_belehrung_am=dt.date(2021, 1, 1),
    )  # fmt: skip
    personal.kopie_speichern(s, bild())
    datei = personal._kopie_pfad(s.fs_kopie_datei)
    Schulung.objects.create(benutzer=fahrer, thema="Hygiene", datum=dt.date(2020, 1, 1))
    verwaltung.sperren(admin, fahrer)
    # noch aktiv bzw. kürzlich gesperrt: bleibt
    jung = benutzer_mit_rolle("jung", rollen.AUSGABE)
    Stammdaten.objects.create(benutzer=jung, strasse="Bleibt 2")
    verwaltung.sperren(admin, jung)
    assert LogEntry.objects.get_for_object(s).exists()

    assert personal.stammdaten_leeren(HEUTE) == 1
    s.refresh_from_db()
    assert (s.strasse, s.telefon, s.fs_klassen, s.ifsg_belehrung_am) == ("", "", "", None)
    assert s.eintritt == dt.date(2015, 1, 1) and s.austritt and s.geleert_am
    assert not s.fs_kopie_datei and not datei.exists()
    assert not Schulung.objects.exists()
    assert not LogEntry.objects.get_for_object(s).exists()
    assert Stammdaten.objects.get(benutzer=jung).strasse == "Bleibt 2"
    assert personal.stammdaten_leeren(HEUTE) == 0  # schon geleert


def test_leeren_nach_sperrdatum_ohne_austritt(fahrer, admin):
    Stammdaten.objects.create(benutzer=fahrer, handy="0000 2")
    verwaltung.sperren(admin, fahrer)
    fahrer.__class__.objects.filter(pk=fahrer.pk).update(
        gesperrt_am=timezone.now() - dt.timedelta(days=4 * 365)
    )
    assert personal.stammdaten_leeren() == 1


# --- Seiten -------------------------------------------------------------------------------


def test_stammdaten_bearbeiten(admin_client, fahrer):
    seite = admin_client.get(url("stammdaten", fahrer)).content.decode()
    assert (
        "Belehrung nach Infektionsschutzgesetz" in seite and "Kopie des Führerscheins" not in seite
    )
    antwort = admin_client.post(
        url("stammdaten", fahrer),
        {"strasse": "Musterweg 1", "handy": "0000 3", "fs_gesehen_am": "2026-10-01",
         "fs_gesehen_von": "chefin"},
    )  # fmt: skip
    assert antwort.url == url("stammdaten", fahrer)
    assert Stammdaten.objects.get(benutzer=fahrer).fs_gesehen_am == dt.date(2026, 10, 1)
    assert "Stammdaten von kim gespeichert" in admin_client.get(antwort.url).content.decode()
    assert (
        url("stammdaten", fahrer) in admin_client.get(url("mitarbeiter", fahrer)).content.decode()
    )


def test_geleert_hinweis(admin_client, fahrer):
    Stammdaten.objects.create(benutzer=fahrer, geleert_am=timezone.now())
    assert (
        "nach Ablauf der Löschfrist geleert"
        in admin_client.get(url("stammdaten", fahrer)).content.decode()
    )


def test_zugriff_nur_fuer_verwaltende(
    client, admin, benutzer_mit_rolle, anmelden, fahrer, recht_geben
):
    buero = benutzer_mit_rolle("buero", rollen.BUERO)
    anmelden(client, buero)
    assert client.get(url("stammdaten", fahrer)).status_code == 403
    recht_geben(rollen.BUERO, "mitarbeitende.verwalten")
    assert client.get(url("stammdaten", fahrer)).status_code == 200
    assert client.get(url("stammdaten", admin)).status_code == 403
    assert client.get(reverse("konten:personal_einstellungen")).status_code == 403


def test_faellig_auf_liste_und_startseite(admin_client, fahrer):
    liste = admin_client.get(reverse("konten:mitarbeitende")).content.decode()
    assert "Fällig" in liste and "noch nichts eingetragen" in liste
    assert (
        "2 Wiedervorlagen bei den Mitarbeitenden fällig" in admin_client.get("/").content.decode()
    )
    Stammdaten.objects.create(benutzer=fahrer, fs_gesehen_am=dt.date(2026, 1, 1))
    assert "seit 01.07.2026" in admin_client.get(reverse("konten:mitarbeitende")).content.decode()


def test_personal_einstellungen(admin_client):
    url_ = reverse("konten:personal_einstellungen")
    assert (
        "Fristen einstellen" in admin_client.get(reverse("konten:mitarbeitende")).content.decode()
    )
    antwort = admin_client.post(
        url_, {"fs_pruefung_monate": "3", "ifsg_wiederholung_monate": "24", "vorlauf_tage": "7",
               "fs_kopie_erlaubt": "on", "stammdaten_loeschen_jahre": "5",
               "urlaub_verfall_monat": "3", "urlaub_verfall_tag": "31"},
    )  # fmt: skip
    assert antwort.url == url_
    e = PersonalEinstellungen.laden()
    assert (e.fs_pruefung_monate, e.fs_kopie_erlaubt, e.stammdaten_loeschen_jahre) == (3, True, 5)
    assert str(e) == "Einstellungen Angestellte"
    assert "Fristen für Wiedervorlagen" in admin_client.get(url_).content.decode()
    assert admin_client.post(url_, {"fs_pruefung_monate": "0"}).status_code == 200
    assert str(Stammdaten(benutzer=admin_client.get("/").wsgi_request.user)) == "Stammdaten chefin"


# --- Führerschein-Kopie -------------------------------------------------------------------


def test_kopie_nur_wenn_erlaubt(admin_client, fahrer):
    antwort = admin_client.post(url("kopie_hochladen", fahrer), {"kopie": bild()}, follow=True)
    assert "nicht erlaubt" in antwort.content.decode()
    assert admin_client.get(url("kopie_ansehen", fahrer)).status_code == 404


def test_kopie_verschluesselt_und_protokolliert(admin_client, fahrer, kopien_erlaubt):
    admin_client.post(url("kopie_hochladen", fahrer), {"kopie": bild()})
    s = Stammdaten.objects.get(benutzer=fahrer)
    gespeichert = personal._kopie_pfad(s.fs_kopie_datei).read_bytes()
    assert b"erfundenes Bild" not in gespeichert
    antwort = admin_client.get(url("kopie_ansehen", fahrer))
    assert antwort.content == b"\xff\xd8 erfundenes Bild"
    assert antwort["Content-Type"] == "image/jpeg" and "no-cache" in antwort["Cache-Control"]
    assert LogEntry.objects.get_for_object(s).filter(action=LogEntry.Action.ACCESS).count() == 1
    assert "Ansehen" in admin_client.get(url("stammdaten", fahrer)).content.decode()

    alt = personal._kopie_pfad(s.fs_kopie_datei)
    admin_client.post(
        url("kopie_hochladen", fahrer), {"kopie": bild("fs.pdf", b"%PDF", "application/pdf")}
    )
    s.refresh_from_db()
    assert not alt.exists() and s.fs_kopie_typ == "application/pdf"
    admin_client.post(url("kopie_entfernen", fahrer))
    s.refresh_from_db()
    assert not s.fs_kopie_datei and s.fs_kopie_am is None


@pytest.mark.parametrize(
    ("daten", "text"),
    [
        ({}, "Bitte eine Datei auswählen."),
        ({"kopie": bild("fs.txt", b"x", "text/plain")}, "Foto (JPG, PNG, WebP) oder ein PDF"),
        ({"kopie": bild(inhalt=b"x" * (5 * 1024 * 1024 + 1))}, "höchstens 5 MB"),
    ],
)
def test_kopie_fehler(admin_client, fahrer, kopien_erlaubt, daten, text):
    antwort = admin_client.post(url("kopie_hochladen", fahrer), daten, follow=True)
    assert text in antwort.content.decode()


def test_kopie_nach_schluesselwechsel_unlesbar(admin_client, fahrer, kopien_erlaubt):
    admin_client.post(url("kopie_hochladen", fahrer), {"kopie": bild()})
    s = Stammdaten.objects.get(benutzer=fahrer)
    with override_settings(SECRET_KEY="anderer-schluessel-nur-fuer-tests"):
        assert personal.kopie_lesen(s) is None
    personal._kopie_pfad(s.fs_kopie_datei).unlink()
    assert personal.kopie_lesen(s) is None


def test_alte_kopie_sichtbar_auch_wenn_abgeschaltet(admin_client, fahrer, kopien_erlaubt):
    admin_client.post(url("kopie_hochladen", fahrer), {"kopie": bild()})
    PersonalEinstellungen.objects.update(fs_kopie_erlaubt=False)
    seite = admin_client.get(url("stammdaten", fahrer)).content.decode()
    assert (
        "Kopie löschen" in seite and "Neue Kopien sind in den Einstellungen abgeschaltet" in seite
    )


# --- Schulungen ---------------------------------------------------------------------------


def test_schulungen_eintragen_und_loeschen(admin_client, fahrer):
    neu = url("schulung_neu", fahrer)
    fehler = admin_client.post(neu, {"thema": ""}, follow=True).content.decode()
    assert "Thema und Datum sind Pflicht" in fehler
    admin_client.post(neu, {"thema": "Hygiene", "datum": "2026-10-01"})
    sch = Schulung.objects.get()
    assert sch.benutzer == fahrer
    assert "Hygiene" in admin_client.get(url("stammdaten", fahrer)).content.decode()
    admin_client.post(url("schulung_loeschen", fahrer, sch.pk))
    assert not Schulung.objects.exists()


def test_null_monate_keine_wiedervorlage(fahrer, benutzer_mit_rolle):
    benutzer_mit_rolle("lena", rollen.AUSGABE)
    assert was(personal.faelligkeiten(HEUTE), fahrer)  # Führerschein, Belehrung fehlen
    PersonalEinstellungen.objects.update(fs_pruefung_monate=0, ifsg_wiederholung_monate=0)
    assert personal.faelligkeiten(HEUTE) == []
    assert PersonalEinstellungen._meta.get_field("fs_pruefung_monate").default == 0
