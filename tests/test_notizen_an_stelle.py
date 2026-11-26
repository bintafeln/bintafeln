"""Notizen der Verwaltung an die Ausgabestelle, z. B. nach dem Ausweisdruck (erfundene Daten)."""

import pytest
from django.test import Client
from django.urls import reverse

from apps.konten import rollen
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    Kundengruppe,
    Nachricht,
    Notiz,
    NotizVorlage,
)

pytestmark = pytest.mark.django_db
START = reverse("core:start")


@pytest.fixture
def mitte():
    return Ausgabestelle.objects.create(name="Mitte")


@pytest.fixture
def zentrale():
    return Ausgabestelle.objects.create(name="Zentrale", ausweise_hier=True)


def haushalt(nummer, stelle):
    gruppe, _ = Kundengruppe.objects.get_or_create(name=f"Gruppe {stelle}", ausgabestelle=stelle)
    return Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe)


@pytest.fixture
def ausgabe(mitte, benutzer_mit_rolle, anmelden):
    konto = benutzer_mit_rolle("anton", rollen.AUSGABE)
    konto.ausgabestellen.set([mitte])
    return anmelden(Client(), konto)


def test_ausweis_drucken_beantwortet_die_meldung(admin_client, ausgabe, mitte, zentrale):
    h = haushalt("501", mitte)
    z = haushalt("502", zentrale)
    vorlage = NotizVorlage.objects.get(melden="ausweis")  # feste Vorlage aus der Migration
    # Die Ausgabestelle meldet mit dem Notiz-Knopf „Neuen Ausweis drucken“
    ausgabe.post(reverse("ausgabe:notiz", args=["501"]), {"text": vorlage.text})
    assert Nachricht.objects.filter(kundennummer="501", anliegen="ausweis").exists()
    Nachricht.objects.create(kundennummer="502", anliegen="ausweis")
    # Ohne Meldung passiert beim Druck nichts
    haushalt("503", mitte)
    admin_client.get(reverse("kunden:ausweis", args=["503"]))
    assert not Notiz.objects.filter(an_stelle=True).exists()
    # Druck: Notiz an die Ausgabestelle, Meldung erledigt, gemeldete Notiz gestrichen
    admin_client.get(reverse("kunden:ausweis", args=["501"]))
    antwort = Notiz.objects.get(kundennummer="501")
    assert antwort.an_stelle and antwort.text == (
        "Neuer Ausweis ist gedruckt und wird zur Ausgabestelle geschickt."
    )
    assert not Nachricht.objects.filter(kundennummer="501", erledigt_am__isnull=True).exists()
    # Zweiter Druck: keine zweite Antwort
    admin_client.get(reverse("kunden:ausweis", args=["501"]))
    assert Notiz.objects.filter(kundennummer="501").count() == 1
    # Sammeldruck, Zentrale: „liegt im Schrank“
    admin_client.get(reverse("kunden:ausweise"))
    assert Notiz.objects.get(kundennummer="502").text == (
        "Neuer Ausweis ist gedruckt und liegt im Schrank."
    )
    assert h and z


def test_ausweis_notiz_geht_nach_frist_in_den_papierkorb(admin_client, mitte):
    """Die Antwort „Neuer Ausweis ist gedruckt“ verschwindet nach der eingestellten Frist von
    selbst (Vorgabe 14 Tage); andere Notizen bleiben."""
    import datetime as dt

    from django.utils import timezone

    from apps.core.models import PapierkorbEintrag
    from apps.kunden.models import KundenEinstellungen, verwaiste_notizen_loeschen

    haushalt("601", mitte)
    haushalt("602", mitte)
    heute = timezone.localdate()
    Nachricht.objects.create(kundennummer="601", anliegen="ausweis")
    admin_client.get(reverse("kunden:ausweis", args=["601"]))
    antwort = Notiz.objects.get(kundennummer="601")
    assert antwort.loeschen_am == heute + dt.timedelta(days=14)
    andere = Notiz.objects.create(kundennummer="601", text="Bitte Bescheid mitbringen")
    # vor dem Tag bleibt sie stehen
    assert verwaiste_notizen_loeschen() == 0
    Notiz.objects.filter(pk=antwort.pk).update(loeschen_am=heute)
    assert verwaiste_notizen_loeschen() == 1
    assert list(Notiz.objects.filter(kundennummer="601")) == [andere]
    assert PapierkorbEintrag.objects.count() == 1  # wiederherstellbar
    # Frist 0: die Notiz bleibt, bis sie jemand löscht
    e = KundenEinstellungen.laden()
    e.ausweis_notiz_tage = 0
    e.save()
    Nachricht.objects.create(kundennummer="602", anliegen="ausweis")
    admin_client.get(reverse("kunden:ausweis", args=["602"]))
    assert Notiz.objects.get(kundennummer="602").loeschen_am is None


def test_startseite_und_gelesen(admin_client, ausgabe, mitte):
    haushalt("601", mitte)
    haushalt("602", mitte)
    andere = haushalt("701", Ausgabestelle.objects.create(name="Nord"))
    seite = ausgabe.get(START).content.decode()
    assert "Notiz der Verwaltung" not in seite
    # Ohne Haken: nur eine Notiz am Haushalt, nichts auf der Startseite
    admin_client.post(reverse("kunden:notiz_neu", args=["601"]), {"text": "Nur intern"})
    assert "Nur intern" not in ausgabe.get(START).content.decode()
    # Mit Haken: eine Notiz steht ganz auf der Startseite
    admin_client.post(reverse("kunden:notiz_neu", args=["601"]),
                      {"text": "Bitte Bescheid mitbringen", "an_stelle": "1"})  # fmt: skip
    seite = ausgabe.get(START).content.decode()
    assert "Notiz der Verwaltung" in seite and "Bitte Bescheid mitbringen" in seite
    # Mehrere: Link zur Sammelseite
    admin_client.post(reverse("kunden:notiz_neu", args=["602"]),
                      {"text": "Neue Anschrift eingetragen", "an_stelle": "1"})  # fmt: skip
    admin_client.post(reverse("kunden:notiz_neu", args=[andere.kundennummer]),
                      {"text": "Für Nord", "an_stelle": "1"})  # fmt: skip
    seite = ausgabe.get(START).content.decode()
    assert "2 neue Notizen der Verwaltung" in seite
    sammel = ausgabe.get(reverse("kunden:notizen_an_stelle")).content.decode()
    assert "Bitte Bescheid mitbringen" in sammel and "Für Nord" not in sammel
    # „gelesen“ nimmt sie von der Startseite; fremde Ausgabestellen können nichts abhaken
    n = Notiz.objects.get(text="Bitte Bescheid mitbringen")
    ausgabe.post(reverse("kunden:notiz_gelesen", args=[n.pk]), {"zurueck": "https://boese.example"})
    n.refresh_from_db()
    assert n.gelesen_am and n.gelesen_von == "anton"
    nord = Notiz.objects.get(text="Für Nord")
    assert ausgabe.post(reverse("kunden:notiz_gelesen", args=[nord.pk])).status_code == 404
    seite = ausgabe.get(START).content.decode()
    assert "Neue Anschrift eingetragen" in seite and "Bitte Bescheid mitbringen" not in seite
    # Am Haushalt steht, ob gelesen
    seite = admin_client.get(reverse("kunden:haushalt", args=["601"])).content.decode()
    assert "An die Ausgabestelle · gelesen" in seite


def test_sammelseite_ohne_stelle(admin_client, mitte):
    Ausgabestelle.objects.create(name="Nord")
    seite = admin_client.get(reverse("kunden:notizen_an_stelle")).content.decode()
    assert "Ausgabestelle wählen" in seite


def test_verwaltung_antwortet_auf_nachricht(admin_client, ausgabe, mitte):
    """Antwort auf eine Nachricht: an die schreibende Ausgabestelle, auch bei fremden Kunden."""
    fremd = haushalt("801", Ausgabestelle.objects.create(name="Nord"))
    n = Nachricht.objects.create(kundennummer=fremd.kundennummer, anliegen="adresse",
                                 stelle=mitte, von="anton", text="Neue Anschrift?")  # fmt: skip
    seite = admin_client.get(reverse("kunden:nachrichten")).content.decode()
    assert "Antwort an Mitte" in seite
    admin_client.post(
        reverse("kunden:nachrichten"), {"nachricht": n.pk, "antwort": "Ist erledigt."}
    )
    n.refresh_from_db()
    assert n.erledigt_am is not None
    notiz = Notiz.objects.get(kundennummer="801")
    assert notiz.text == "Antwort zu „Neue Anschrift oder Telefon“: Ist erledigt."
    assert notiz.an_stelle and notiz.fuer_stelle == mitte
    assert "Ist erledigt." in ausgabe.get(START).content.decode()  # bei Mitte, nicht bei Nord
    # Ohne Antworttext bleibt es beim Abhaken
    m = Nachricht.objects.create(kundennummer="801", anliegen="sonstiges", stelle=mitte, text="x")
    admin_client.post(reverse("kunden:nachrichten"), {"nachricht": m.pk, "antwort": "  "})
    m.refresh_from_db()
    assert m.erledigt_am and Notiz.objects.count() == 1


def test_notiztext_fett_und_maskiert():
    from apps.core.templatetags.notiz import notiz_text, ohne_auszeichnung

    html = notiz_text("Ausweis kann **NICHT!** verlängert werden.\n<b>x</b> & **y")
    assert html == ("Ausweis kann <strong>NICHT!</strong> verlängert werden.<br>"
                    "&lt;b&gt;x&lt;/b&gt; &amp; **y")  # fmt: skip
    assert ohne_auszeichnung("kann **NICHT!** werden") == "kann NICHT! werden"
    assert notiz_text(None) == ""


def test_alle_gemeldeten_ausweise_auf_einmal_drucken(admin_client, mitte, zentrale, pdf_text):
    haushalt("601", mitte)
    haushalt("602", zentrale)
    haushalt("603", mitte)
    Nachricht.objects.create(kundennummer="601", anliegen="ausweis")
    Nachricht.objects.create(kundennummer="602", anliegen="ausweis")
    Nachricht.objects.create(kundennummer="603", anliegen="adresse")  # anderes Anliegen
    seite = admin_client.get(reverse("kunden:nachrichten") + "?anliegen=adresse").content.decode()
    assert "Alle gemeldeten Ausweise drucken (2)" in seite
    url = reverse("kunden:ausweise_auswahl")
    # Ein Link mit eigenem Fenster, damit man in der iPad-App zurückkommt
    assert f'href="{url}?gemeldet=1" target="_blank"' in seite
    antwort = admin_client.get(url, {"gemeldet": "1"})
    assert antwort["Content-Type"] == "application/pdf"
    text = pdf_text(antwort)
    assert "(601)" in text and "(602)" in text and "(603)" not in text
    assert set(Notiz.objects.filter(an_stelle=True).values_list("kundennummer", flat=True)) == {
        "601",
        "602",
    }
    assert not Nachricht.objects.filter(anliegen="ausweis", erledigt_am__isnull=True).exists()
    assert "Alle gemeldeten Ausweise" not in admin_client.get(
        reverse("kunden:nachrichten")).content.decode()  # fmt: skip
    antwort = admin_client.post(url, {"gemeldet": "1"})
    assert antwort.url == reverse("kunden:nachrichten")  # nichts mehr offen


def test_verlaengerte_ausweise_auswaehlen_und_drucken(admin_client, mitte, pdf_text):
    from django.utils import timezone

    verlaengert = "Verlängert bis 31.10.2027"
    for nummer, ergebnis in (("701", verlaengert), ("702", verlaengert),
                             ("703", "Nicht verlängert: Alter fehlt")):  # fmt: skip
        haushalt(nummer, mitte)
        Nachricht.objects.create(kundennummer=nummer, anliegen="verlaengern", ergebnis=ergebnis,
                                 erledigt_am=timezone.now(), erledigt_von="chefin")  # fmt: skip
    seite = admin_client.get(reverse("kunden:verlaengern")).content.decode()
    assert 'name="nummer" value="701" form="ausweise-drucken"' in seite
    assert 'value="703" form="ausweise-drucken"' not in seite  # nicht verlängert
    assert "Angehakte Ausweise drucken (PDF)" in seite
    assert 'method="get"' in seite and 'target="_blank"' in seite
    antwort = admin_client.get(reverse("kunden:ausweise_auswahl"), {"nummer": ["702"]})
    text = pdf_text(antwort)
    assert "(702)" in text and "(701)" not in text
    leer = admin_client.post(reverse("kunden:ausweise_auswahl"))
    assert leer.url == reverse("kunden:verlaengern")


def test_ausweise_auswahl_nur_mit_recht_und_eigene_stelle(
    client, admin, mitte, benutzer_mit_rolle, anmelden, recht_geben
):
    nord = Ausgabestelle.objects.create(name="Nord")
    haushalt("801", nord)
    haushalt("802", mitte)
    url = reverse("kunden:ausweise_auswahl")
    konto = benutzer_mit_rolle("anton", rollen.AUSGABE)
    konto.ausgabestellen.set([mitte])
    anmelden(client, konto)
    assert client.post(url, {"nummer": ["801"]}).status_code == 403
    recht_geben(rollen.AUSGABE, "kunden.ausweis")
    antwort = client.post(url, {"nummer": ["801"]})  # fremde Ausgabestelle
    assert antwort.status_code == 302 and antwort.url == reverse("kunden:verlaengern")
    assert client.post(url, {"nummer": ["801", "802"]})["Content-Type"] == "application/pdf"


def test_sammeldruck_zuruecknehmen_oder_bestaetigen(admin_client, admin, ausgabe, mitte):
    """„Alle gemeldeten Ausweise drucken“ merkt sich den Druck (ADR 0167): Hat der Drucker nichts
    ausgegeben, nimmt „Nein, zurücknehmen“ alles zurück."""
    from apps.kunden import an_stelle
    from apps.kunden.models import Ausweisdruck

    haushalt("801", mitte)
    haushalt("802", mitte)
    vorlage = NotizVorlage.objects.get(melden="ausweis")
    ausgabe.post(reverse("ausgabe:notiz", args=["801"]), {"text": vorlage.text})
    Nachricht.objects.create(kundennummer="802", anliegen="ausweis")
    gemeldet = Notiz.objects.get(kundennummer="801")
    url = reverse("kunden:nachrichten")
    assert "ordentlich aus dem Drucker" not in admin_client.get(url).content.decode()
    # Einzeldruck merkt sich nichts
    Nachricht.objects.create(kundennummer="803", anliegen="ausweis")
    haushalt("803", mitte)
    admin_client.get(reverse("kunden:ausweis", args=["803"]))
    assert not Ausweisdruck.objects.exists()
    # Sammeldruck: Meldungen erledigt, Antwort bei der Ausgabestelle, gemeldete Notiz gestrichen
    pdf = admin_client.get(reverse("kunden:ausweise_auswahl"), {"gemeldet": "1"})
    assert pdf["Content-Type"] == "application/pdf"
    druck = Ausweisdruck.objects.get()
    assert druck.kundennummern == ["801", "802"] and druck.offen and len(druck.nachrichten) == 2
    assert not Nachricht.objects.filter(erledigt_am__isnull=True).exists()
    assert not Notiz.objects.filter(pk=gemeldet.pk).exists()
    assert Notiz.objects.filter(an_stelle=True, kundennummer__in=["801", "802"]).count() == 2
    seite = admin_client.get(url).content.decode()
    assert "2 Ausweise gedruckt" in seite and "801, 802" in seite
    # Ohne das Recht: kein Kasten, kein Zurücknehmen
    zurueck = reverse("kunden:ausweisdruck", args=[druck.pk, "zuruecknehmen"])
    assert ausgabe.post(zurueck).status_code == 403
    assert admin_client.get(zurueck).status_code == 405
    # Zurücknehmen: alles wie vor dem Druck
    antwort = admin_client.post(zurueck, follow=True)
    assert "2 Meldungen wieder offen" in antwort.content.decode()
    assert Nachricht.objects.filter(erledigt_am__isnull=True, anliegen="ausweis").count() == 2
    assert not Notiz.objects.filter(an_stelle=True, kundennummer__in=["801", "802"]).exists()
    wieder = Notiz.objects.get(kundennummer="801")
    assert wieder.text == vorlage.text and wieder.erstellt_am == gemeldet.erstellt_am
    assert wieder.verfasst_von == gemeldet.verfasst_von
    druck.refresh_from_db()
    assert not druck.offen and druck.zurueckgenommen_am and druck.entschieden_von
    assert "ordentlich aus dem Drucker" not in admin_client.get(url).content.decode()
    # Ein zweites Mal geht nicht
    antwort = admin_client.post(zurueck, follow=True)
    assert "schon entschieden" in antwort.content.decode()
    with pytest.raises(an_stelle.DruckFehler):
        an_stelle.druck_bestaetigen(druck, admin)
    # Erneut drucken und bestätigen: Der Kasten verschwindet, alles bleibt erledigt
    admin_client.get(reverse("kunden:ausweise_auswahl"), {"gemeldet": "1"})
    neu = Ausweisdruck.objects.exclude(pk=druck.pk).get()
    assert neu.kundennummern == ["801", "802"]
    antwort = admin_client.post(reverse("kunden:ausweisdruck", args=[neu.pk, "bestaetigen"]),
                                follow=True)  # fmt: skip
    assert "als erledigt vermerkt" in antwort.content.decode()
    assert "ordentlich aus dem Drucker" not in antwort.content.decode()
    assert not Nachricht.objects.filter(erledigt_am__isnull=True).exists()
    assert admin_client.post(reverse("kunden:ausweisdruck", args=[neu.pk, "quatsch"])
                             ).status_code == 404  # fmt: skip


def test_alte_ausweisdrucke_werden_geloescht():
    import datetime as dt

    from django.utils import timezone

    from apps.kunden.models import Ausweisdruck, alte_nachrichten_loeschen

    alt = Ausweisdruck.objects.create(gedruckt_am=timezone.now() - dt.timedelta(days=91))
    neu = Ausweisdruck.objects.create()
    alte_nachrichten_loeschen()
    assert not Ausweisdruck.objects.filter(pk=alt.pk).exists()
    assert Ausweisdruck.objects.filter(pk=neu.pk).exists()
