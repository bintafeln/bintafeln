import datetime as dt
from decimal import Decimal as D

import pytest
from auditlog.models import LogEntry
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from django.utils import timezone

from apps.core import privatdateien
from apps.konten import personal as konten_personal
from apps.konten import rollen, verwaltung
from apps.konten.models import PersonalEinstellungen, Rolle
from apps.personal import berechnung
from apps.personal.models import (
    DOKUMENT_ORDNER,
    Abwesenheit,
    Arbeitsvertrag,
    Stunden,
    Urlaubsjahr,
)

pytestmark = pytest.mark.django_db

LISTE = reverse("personal:liste")
URLAUB, KRANK = Abwesenheit.Art.URLAUB, Abwesenheit.Art.KRANK


@pytest.fixture
def kim(benutzer_mit_rolle):
    b = benutzer_mit_rolle("kim", rollen.AUSGABE)
    b.first_name, b.last_name, b.beschaeftigung = "Kim", "Probe", "fest"
    b.save()
    return b


def vertrag(person, beginn, ende=None, stunden="40", urlaub="30", **mehr):
    return Arbeitsvertrag.objects.create(
        benutzer=person, beginn=beginn, ende=ende, wochenstunden=D(stunden),
        urlaubstage=D(urlaub), **mehr,
    )  # fmt: skip


def abwesenheit(person, von, bis, art=URLAUB, tage=None):
    return Abwesenheit.objects.create(benutzer=person, art=art, von=von, bis=bis, tage=tage)


def url(name, *args):
    return reverse(f"personal:{name}", args=args)


# --- Berechnung: Werktage und Anspruch ----------------------------------------------------


def test_werktage():
    assert berechnung.werktage(dt.date(2026, 10, 19), dt.date(2026, 10, 25)) == 5
    assert berechnung.werktage(dt.date(2026, 10, 25), dt.date(2026, 10, 19)) == 0


@pytest.mark.parametrize(
    ("beginn", "ende", "urlaub", "anspruch"),
    [
        (dt.date(2025, 1, 1), None, "30", D("30")),
        (dt.date(2026, 3, 15), None, "30", D("23")),  # 9 volle Monate = 22,5 → aufrunden
        (dt.date(2026, 2, 1), None, "30", D("28")),  # 11 Monate = 27,5 → 28
        (dt.date(2026, 6, 1), None, "26", D("15.2")),  # 7 Monate = 15,17 → bleibt
        (dt.date(2026, 1, 1), dt.date(2026, 6, 15), "24", D("10")),  # Jan–Mai
    ],
)
def test_anspruch_anteilig(kim, beginn, ende, urlaub, anspruch):
    vertrag(kim, beginn, ende, urlaub=urlaub)
    assert berechnung.anspruch_berechnet(list(kim.vertraege.all()), 2026) == anspruch


def test_verfallsdatum_aus_einstellungen():
    assert berechnung.verfall_standard(2026) == dt.date(2026, 3, 31)
    PersonalEinstellungen.objects.update_or_create(
        pk=1, defaults={"urlaub_verfall_monat": 2, "urlaub_verfall_tag": 31}
    )
    assert berechnung.verfall_standard(2028) == dt.date(2028, 2, 29)


# --- Berechnung: Übertrag und Verfall -----------------------------------------------------


@pytest.fixture
def mit_resturlaub(kim):
    """2025 30 Tage Anspruch, 25 genommen: 5 Tage Übertrag nach 2026."""
    vertrag(kim, dt.date(2025, 1, 1))
    abwesenheit(kim, dt.date(2025, 7, 1), dt.date(2025, 7, 31), tage=D("25"))
    abwesenheit(kim, dt.date(2025, 9, 1), dt.date(2025, 9, 2), art=KRANK)
    return kim


def test_uebertrag_vor_dem_verfall(mit_resturlaub):
    s = berechnung.urlaub(mit_resturlaub, 2026, dt.date(2026, 2, 15))
    assert (s.anspruch, s.uebertrag, s.genommen) == (D("30"), D("5"), D("0"))
    assert (s.verfaellt, s.verfallen, s.rest) == (D("5"), D("0"), D("35"))
    assert s.verfall_am == dt.date(2026, 3, 31)


def test_genommener_uebertrag_verfaellt_nicht(mit_resturlaub):
    abwesenheit(mit_resturlaub, dt.date(2026, 2, 2), dt.date(2026, 2, 4))  # 3 Werktage
    abwesenheit(mit_resturlaub, dt.date(2026, 5, 4), dt.date(2026, 5, 8))  # 5 Werktage
    s = berechnung.urlaub(mit_resturlaub, 2026, dt.date(2026, 6, 1))
    assert (s.genommen, s.verfaellt, s.verfallen, s.rest) == (D("8"), D("2"), D("2"), D("25"))
    # Ins nächste Jahr geht der Rest, der Verfall ist dann endgültig.
    assert berechnung.urlaub(mit_resturlaub, 2027, dt.date(2027, 1, 2)).uebertrag == D("25")


def test_verfallsdatum_je_jahr_aenderbar(mit_resturlaub):
    abwesenheit(mit_resturlaub, dt.date(2026, 5, 4), dt.date(2026, 5, 8))
    Urlaubsjahr.objects.create(benutzer=mit_resturlaub, jahr=2026, verfall_am=dt.date(2026, 6, 30))
    s = berechnung.urlaub(mit_resturlaub, 2026, dt.date(2026, 7, 1))
    assert (s.verfaellt, s.verfallen, s.rest) == (D("0"), D("0"), D("30"))


def test_anspruch_je_jahr_aenderbar_und_negativer_rest(kim):
    vertrag(kim, dt.date(2026, 1, 1))
    Urlaubsjahr.objects.create(benutzer=kim, jahr=2026, anspruch=D("2"))
    abwesenheit(kim, dt.date(2026, 3, 2), dt.date(2026, 3, 4))
    s = berechnung.urlaub(kim, 2026, dt.date(2026, 4, 1))
    assert (s.anspruch, s.rest) == (D("2"), D("-1"))
    assert berechnung.urlaub(kim, 2027, dt.date(2027, 1, 2)).uebertrag == D("0")


def test_ohne_vertrag(kim):
    s = berechnung.urlaub(kim, 2026, dt.date(2026, 6, 1))
    assert (s.anspruch, s.rest) == (D("0.0"), D("0.0"))
    assert berechnung.stundenkonto(kim, 2026, dt.date(2026, 6, 1)).monate == []


# --- Berechnung: Stundenkonto -------------------------------------------------------------


def test_stundenkonto_monat(kim):
    vertrag(kim, dt.date(2026, 10, 1))  # 40 Std. = 8 je Werktag
    Stunden.objects.create(benutzer=kim, datum=dt.date(2026, 10, 2), stunden=D("50"))
    abwesenheit(kim, dt.date(2026, 10, 5), dt.date(2026, 10, 5))
    abwesenheit(kim, dt.date(2026, 10, 6), dt.date(2026, 10, 6), art=KRANK)
    abwesenheit(kim, dt.date(2026, 9, 1), dt.date(2026, 9, 1), art=KRANK)  # ohne Vertrag
    konto = berechnung.stundenkonto(kim, 2026, dt.date(2026, 10, 9))
    (m,) = konto.monate
    assert (m.soll, m.ist, m.urlaub, m.krank, m.saldo) == (
        D("56"), D("50"), D("8"), D("8"), D("10"),
    )  # fmt: skip
    assert konto.vorjahre == D("0") and konto.saldo == D("10")


def test_stundenkonto_mit_vorjahren(kim):
    vertrag(kim, dt.date(2026, 12, 1), stunden="5")  # 1 Stunde je Werktag
    konto = berechnung.stundenkonto(kim, 2027, dt.date(2027, 1, 5))
    assert konto.vorjahre == D("-23") and [m.soll for m in konto.monate] == [D("3")]
    assert konto.saldo == D("-26")


# --- Seiten: Rechte -----------------------------------------------------------------------


def test_nur_admin_und_personal(client, admin, benutzer_mit_rolle, anmelden, kim):
    anmelden(client, benutzer_mit_rolle("buero", rollen.BUERO))
    assert client.get(LISTE).status_code == 403
    assert "Personal</a>" not in client.get("/").content.decode()
    client.logout()
    anmelden(client, benutzer_mit_rolle("hr", rollen.PERSONAL))
    assert client.get(LISTE).status_code == 200
    assert "Personal</a>" in client.get("/").content.decode()


def test_personal_rolle_vergibt_nur_ein_admin(admin, benutzer_mit_rolle):
    Rolle.objects.filter(gruppe__name="Büro").update(
        rechte=Rolle.objects.get(gruppe__name="Büro").rechte + ["mitarbeitende.verwalten"]
    )
    buero = benutzer_mit_rolle("buero", rollen.BUERO)
    assert rollen.PERSONAL not in verwaltung.vergebbare_rollen(buero)
    assert rollen.PERSONAL in verwaltung.vergebbare_rollen(admin)


# --- Seiten: Liste und Person -------------------------------------------------------------


def test_liste(admin_client, kim, benutzer_mit_rolle):
    ohne = benutzer_mit_rolle("alex", rollen.AUSGABE)
    vertrag(ohne, dt.date(2020, 1, 1), dt.date(2020, 12, 31))
    vertrag(kim, dt.date(2026, 1, 1), taetigkeit="Lager")
    inhalt = admin_client.get(LISTE).content.decode()
    assert "Kim Probe" in inhalt and "Lager" in inhalt and "unbefristet" in inhalt
    assert "kein gültiger Vertrag" in inhalt  # alex
    assert "chefin" not in inhalt.split("<main", 1)[1]  # oben steht nur der eigene Name


def test_person_mit_jahr(admin_client, kim):
    vertrag(kim, dt.date(2025, 1, 1), stundenlohn=D("14.50"))
    inhalt = admin_client.get(url("person", kim.pk), {"jahr": "2025"}).content.decode()
    assert "Urlaub 2025" in inhalt and "14,50 € pro Stunde" in inhalt
    assert "jahr=2024" in inhalt and "jahr=2026" in inhalt
    assert admin_client.get(url("person", kim.pk), {"jahr": "x"}).context["jahr"] == (
        timezone.localdate().year
    )
    assert admin_client.get(url("person", kim.pk), {"jahr": "1999"}).context["jahr"] == 2000


def test_ohne_gueltigen_vertrag_hinweis(admin_client, kim):
    inhalt = admin_client.get(url("person", kim.pk)).content.decode()
    assert "Heute gilt kein Arbeitsvertrag" in inhalt and "Noch kein Arbeitsvertrag" in inhalt


# --- Seiten: Verträge und Dokumente -------------------------------------------------------


def test_vertrag_eintragen_und_bearbeiten(admin_client, kim):
    daten = {"beginn": "2026-01-01", "wochenstunden": "38,5", "urlaubstage": "30",
             "stundenlohn": "14,50", "jahr": "2026"}  # fmt: skip
    antwort = admin_client.post(url("vertrag_neu", kim.pk), daten)
    assert antwort.url == f"{url('person', kim.pk)}?jahr=2026"
    v = Arbeitsvertrag.objects.get()
    assert (v.wochenstunden, v.stundenlohn) == (D("38.50"), D("14.50"))
    assert str(v) == "Arbeitsvertrag ab 01.01.2026"
    fehler = admin_client.post(url("vertrag_neu", kim.pk), {**daten, "ende": "2025-01-01"},
                               follow=True).content.decode()  # fmt: skip
    assert "Nicht gespeichert. Ende: Das Ende liegt vor dem Beginn." in fehler

    seite = url("vertrag", kim.pk, v.pk)
    assert "Vertragsdokument" in admin_client.get(seite).content.decode()
    admin_client.post(seite, {**daten, "taetigkeit": "Fahrer"})
    v.refresh_from_db()
    assert v.taetigkeit == "Fahrer"
    assert admin_client.post(seite, {"beginn": ""}).status_code == 200


def test_vertragsdokument(admin_client, kim):
    v = vertrag(kim, dt.date(2026, 1, 1))
    hochladen = url("dokument_hochladen", kim.pk, v.pk)
    assert "Bitte eine Datei" in admin_client.post(hochladen, follow=True).content.decode()
    falsch = SimpleUploadedFile("v.txt", b"x", content_type="text/plain")
    assert "PDF" in admin_client.post(hochladen, {"dokument": falsch}, follow=True).content.decode()
    pdf = SimpleUploadedFile("v.pdf", b"%PDF erfundener Vertrag", content_type="application/pdf")
    admin_client.post(hochladen, {"dokument": pdf})
    v.refresh_from_db()
    datei = privatdateien.pfad(DOKUMENT_ORDNER, v.dokument_datei)
    assert b"erfundener Vertrag" not in datei.read_bytes()
    antwort = admin_client.get(url("dokument_ansehen", kim.pk, v.pk))
    assert antwort.content == b"%PDF erfundener Vertrag"
    assert LogEntry.objects.get_for_object(v).filter(action=LogEntry.Action.ACCESS).count() == 1
    # ersetzen löscht die alte Datei
    pdf2 = SimpleUploadedFile("v2.pdf", b"%PDF neu", content_type="application/pdf")
    admin_client.post(hochladen, {"dokument": pdf2})
    assert not datei.exists()
    admin_client.post(url("dokument_loeschen", kim.pk, v.pk))
    v.refresh_from_db()
    assert not v.dokument_datei
    assert admin_client.get(url("dokument_ansehen", kim.pk, v.pk)).status_code == 404


def test_vertrag_loeschen_entfernt_dokument(admin_client, kim):
    v = vertrag(kim, dt.date(2026, 1, 1))
    pdf = SimpleUploadedFile("v.pdf", b"%PDF", content_type="application/pdf")
    admin_client.post(url("dokument_hochladen", kim.pk, v.pk), {"dokument": pdf})
    v.refresh_from_db()
    datei = privatdateien.pfad(DOKUMENT_ORDNER, v.dokument_datei)
    admin_client.post(url("vertrag_loeschen", kim.pk, v.pk))
    assert not Arbeitsvertrag.objects.exists() and not datei.exists()


# --- Seiten: Abwesenheiten, Urlaubsjahr, Stunden ------------------------------------------


def test_abwesenheiten_und_stunden(admin_client, kim):
    vertrag(kim, dt.date(2026, 1, 1))
    person = url("person", kim.pk)
    krank = {"art": "krank", "von": "2026-03-02", "bis": "2026-03-03", "jahr": "2026"}
    admin_client.post(url("abwesenheit_neu", kim.pk), krank)
    admin_client.post(url("abwesenheit_neu", kim.pk),
                      {"art": "urlaub", "von": "2026-04-06", "bis": "2026-04-06", "tage": "0,5",
                       "jahr": "2026"})  # fmt: skip
    fehler = admin_client.post(url("abwesenheit_neu", kim.pk),
                               {"art": "urlaub", "von": "2026-05-02", "bis": "2026-05-01"},
                               follow=True).content.decode()  # fmt: skip
    assert "„Bis“ liegt vor „Von“" in fehler
    admin_client.post(url("stunden_neu", kim.pk), {"datum": "2026-03-04", "stunden": "7,5"})
    inhalt = admin_client.get(person, {"jahr": "2026"}).content.decode()
    assert "ohne AU" in inhalt and "2 Arbeitstage" in inhalt  # krank
    assert "Resturlaub" in inhalt and "29,5 Tage" in inhalt
    assert str(Abwesenheit.objects.get(art=KRANK)) == "krank 02.03.2026–03.03.2026"
    assert str(Stunden.objects.get()) == "7.50 Stunden am 04.03.2026"

    for art, modell in (("abwesenheit", Abwesenheit), ("stunden", Stunden)):
        eintrag = modell.objects.first()
        admin_client.post(url("loeschen", kim.pk, art, eintrag.pk), {"jahr": "2026"})
        assert not modell.objects.filter(pk=eintrag.pk).exists()
    assert admin_client.post(url("loeschen", kim.pk, "unbekannt", 1)).status_code == 404


def test_urlaubsjahr_abweichungen(admin_client, kim):
    ziel = url("urlaubsjahr", kim.pk)
    admin_client.post(ziel, {"jahr": "2026", "anspruch": "12,5"})
    admin_client.post(ziel, {"jahr": "2026", "anspruch": "12,5", "verfall_am": "2026-06-30"})
    u = Urlaubsjahr.objects.get()
    assert (u.anspruch, u.verfall_am, str(u)) == (
        D("12.5"),
        dt.date(2026, 6, 30),
        "Urlaubsjahr 2026",
    )


# --- Löschfrist ---------------------------------------------------------------------------


def test_loeschfrist_entfernt_personaldaten(admin, kim):
    v = vertrag(kim, dt.date(2015, 1, 1), dt.date(2020, 12, 31))
    pdf = SimpleUploadedFile("v.pdf", b"%PDF", content_type="application/pdf")
    v.dokument_datei, v.dokument_typ = (
        privatdateien.speichern(DOKUMENT_ORDNER, pdf),
        "application/pdf",
    )
    v.save()
    abwesenheit(kim, dt.date(2020, 3, 2), dt.date(2020, 3, 3), art=KRANK)
    Stunden.objects.create(benutzer=kim, datum=dt.date(2020, 3, 4), stunden=D("8"))
    Urlaubsjahr.objects.create(benutzer=kim, jahr=2020, anspruch=D("10"))
    verwaltung.sperren(admin, kim)
    kim.__class__.objects.filter(pk=kim.pk).update(
        gesperrt_am=timezone.now() - dt.timedelta(days=5 * 365)
    )
    assert LogEntry.objects.get_for_object(v).exists()

    assert konten_personal.stammdaten_leeren() == 1
    for modell in (Arbeitsvertrag, Abwesenheit, Stunden, Urlaubsjahr):
        assert not modell.objects.exists()
    assert not privatdateien.pfad(DOKUMENT_ORDNER, v.dokument_datei).exists()
    assert not LogEntry.objects.filter(content_type__app_label="personal").exists()
    kim.refresh_from_db()
    assert kim.stammdaten.geleert_am and kim.username == "kim"
