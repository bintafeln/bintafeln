"""Liste aller Anmerkungen zu Haushalten (ADR 0143). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen
from apps.kunden.models import Ausgabestelle, Bemerkung, Haushalt, Kundengruppe, Person

pytestmark = pytest.mark.django_db
URL = reverse("kunden:anmerkungen")
LOESCHEN = reverse("kunden:anmerkungen_loeschen")
UMWANDELN = reverse("kunden:anmerkungen_umwandeln")
TEXTE = ("Zahlt im Voraus", "Kommt mit Begleitung", "Umzug angekündigt")


def _haushalt(nummer, nachname, stelle):
    gruppe = Kundengruppe.objects.create(name=f"Gruppe {nummer}", ausgabestelle=stelle)
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe)
    Person.objects.create(haushalt=h, vorname="Erika", nachname=nachname, ist_hauptperson=True)
    return h


@pytest.fixture
def anmerkungen(admin):
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    a = _haushalt("00042", "Beispiel", mitte)
    b = _haushalt("00077", "Muster", nord)
    return {
        "voraus": Bemerkung.objects.create(haushalt=a, datum=dt.date(2026, 11, 10),
                                           text=TEXTE[0], verfasst_von="Büro"),
        "begleitung": Bemerkung.objects.create(haushalt=b, datum=dt.date(2026, 10, 5),
                                               text=TEXTE[1], verfasst_von="Büro"),
        "umzug": Bemerkung.objects.create(haushalt=b, datum=dt.date(2026, 9, 1),
                                          text=TEXTE[2], verfasst_von="Verwaltung"),
        "mitte": mitte,
    }  # fmt: skip


def _texte(antwort):
    inhalt = antwort.content.decode()
    return [t for t in TEXTE if t in inhalt]


def test_liste_filter_und_suche(admin_client, anmerkungen):
    inhalt = admin_client.get(URL).content.decode()
    assert "3 Anmerkungen" in inhalt and "Muster, Erika" in inhalt and "Nord" in inhalt
    assert reverse("kunden:haushalt", args=["00042"]) in inhalt
    assert _texte(admin_client.get(URL, {"stelle": anmerkungen["mitte"].pk})) == [TEXTE[0]]
    assert _texte(admin_client.get(URL, {"q": "muster"})) == [TEXTE[1], TEXTE[2]]
    assert _texte(admin_client.get(URL, {"q": "voraus"})) == [TEXTE[0]]
    assert _texte(admin_client.get(URL, {"q": "verwaltung"})) == [TEXTE[2]]
    assert _texte(admin_client.get(URL, {"von": "2026-10-01"})) == [TEXTE[0], TEXTE[1]]
    assert _texte(admin_client.get(URL, {"bis": "2026-10-01"})) == [TEXTE[2]]
    assert "Keine Anmerkungen gefunden" in admin_client.get(URL, {"q": "xyz"}).content.decode()


def test_export(admin_client, anmerkungen):
    text = admin_client.get(URL, {"aktion": "csv"}).content.decode()
    assert text.splitlines()[0] == "Datum;Kundennummer;Kunde;Ausgabestelle;Anmerkung;Verfasst von"
    assert "10.11.2026;00042;Beispiel, Erika;Mitte;Zahlt im Voraus;Büro" in text
    assert len(text.splitlines()) == 4
    nur = admin_client.get(URL, {"aktion": "csv", "id": anmerkungen["umzug"].pk}).content.decode()
    assert len(nur.splitlines()) == 2 and TEXTE[2] in nur
    assert admin_client.get(URL, {"aktion": "pdf"})["Content-Type"] == "application/pdf"


def test_loeschen_in_den_papierkorb(admin_client, anmerkungen):
    from apps.core.models import PapierkorbEintrag

    assert admin_client.get(LOESCHEN).status_code == 405
    antwort = admin_client.post(LOESCHEN, {"id": [anmerkungen["voraus"].pk],
                                           "zurueck": URL + "?q=voraus"})  # fmt: skip
    assert antwort.url == URL + "?q=voraus"
    assert sorted(Bemerkung.objects.values_list("text", flat=True)) == sorted(TEXTE[1:])
    assert PapierkorbEintrag.objects.count() == 1
    # wie beim Löschen am Haushalt: der Haushalt gilt als in bintafeln geändert
    assert Haushalt.objects.get(kundennummer="00042").geaendert_am is not None
    assert Haushalt.objects.get(kundennummer="00077").geaendert_am is None
    antwort = admin_client.post(LOESCHEN, {"zurueck": "https://boese.example/"})
    assert antwort.url == URL and Bemerkung.objects.count() == 2


def test_in_notizen_umwandeln(admin_client, anmerkungen):
    """Angehakte Anmerkungen werden Notizen: Datum, Text, Verfasser bleiben; kein Papierkorb."""
    from apps.core.models import PapierkorbEintrag
    from apps.kunden.models import Notiz

    assert "in Notizen umwandeln" in admin_client.get(URL).content.decode()
    assert admin_client.get(UMWANDELN).status_code == 405
    antwort = admin_client.post(UMWANDELN, {"id": [anmerkungen["begleitung"].pk],
                                            "zurueck": URL + "?sort=datum"})  # fmt: skip
    assert antwort.url == URL + "?sort=datum"
    assert sorted(Bemerkung.objects.values_list("text", flat=True)) == sorted([TEXTE[0], TEXTE[2]])
    notiz = Notiz.objects.get()
    assert (notiz.kundennummer, notiz.text, notiz.verfasst_von) == ("00077", TEXTE[1], "Büro")
    assert timezone.localtime(notiz.erstellt_am).date() == dt.date(2026, 10, 5)
    assert not notiz.an_stelle and notiz.krank_von is None
    assert not PapierkorbEintrag.objects.exists()
    assert Haushalt.objects.get(kundennummer="00077").geaendert_am is not None
    assert Haushalt.objects.get(kundennummer="00042").geaendert_am is None
    # steht jetzt in der Liste der Notizen
    assert TEXTE[1] in admin_client.get(reverse("kunden:notizen")).content.decode()
    # ohne Haken: Meldung, nichts geändert; fremdes Ziel wird nicht angesprungen
    antwort = admin_client.post(UMWANDELN, {"zurueck": "https://boese.example/"}, follow=True)
    assert "Bitte zuerst die Anmerkungen anhaken" in antwort.content.decode()
    assert Bemerkung.objects.count() == 2 and Notiz.objects.count() == 1


def test_umwandeln_nur_eigene_kunden(admin, anmerkungen, benutzer_mit_rolle, anmelden,
                                     recht_geben):  # fmt: skip
    from apps.kunden.models import Notiz

    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.ausgabestellen.set([anmerkungen["mitte"]])
    recht_geben(rollen.AUSGABE, "kunden.anmerkungen")
    recht_geben(rollen.AUSGABE, "kunden.bearbeiten")
    c = anmelden(Client(), anton)
    c.post(UMWANDELN, {"id": [anmerkungen["voraus"].pk, anmerkungen["umzug"].pk]})
    assert [n.text for n in Notiz.objects.all()] == [TEXTE[0]]  # die fremde bleibt Anmerkung
    assert sorted(Bemerkung.objects.values_list("text", flat=True)) == sorted(TEXTE[1:])


def test_rechte_und_nur_eigene_kunden(admin, anmerkungen, benutzer_mit_rolle, anmelden,
                                      recht_geben):  # fmt: skip
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.ausgabestellen.set([anmerkungen["mitte"]])
    c = anmelden(Client(), anton)
    assert c.get(URL).status_code == 403
    recht_geben(rollen.AUSGABE, "kunden.anmerkungen")
    c = anmelden(Client(), anton)
    inhalt = c.get(URL).content.decode()
    assert _texte(c.get(URL)) == [TEXTE[0]]  # nur Kunden der eigenen Ausgabestelle
    assert "Angehakte löschen" not in inhalt  # sehen ja, löschen nur mit „Kundenstamm bearbeiten“
    assert c.post(LOESCHEN, {"id": anmerkungen["voraus"].pk}).status_code == 403
    assert "in Notizen umwandeln" not in inhalt
    assert c.post(UMWANDELN, {"id": anmerkungen["voraus"].pk}).status_code == 403
    recht_geben(rollen.AUSGABE, "kunden.bearbeiten")
    c = anmelden(Client(), anton)
    c.post(LOESCHEN, {"id": [anmerkungen["voraus"].pk, anmerkungen["umzug"].pk]})
    assert sorted(Bemerkung.objects.values_list("text", flat=True)) == sorted(TEXTE[1:])


def test_im_menue_unter_kunden(admin):
    from django.test import RequestFactory

    from apps.core.menue import menue

    anfrage = RequestFactory().get("/")
    anfrage.user = admin
    bereiche = {b["titel"]: str(b) for b in menue(anfrage)}
    assert URL in bereiche["Kunden"]


def _reihenfolge(antwort):
    inhalt = antwort.content.decode()
    return [TEXTE.index(t) for t in sorted(TEXTE, key=inhalt.index)]


def test_spalten_sortieren(admin_client, anmerkungen):
    """Jeder Spaltenkopf sortiert, wie in den anderen Listen; Vorgabe: neueste zuerst."""
    assert _reihenfolge(admin_client.get(URL)) == [0, 1, 2]
    assert _reihenfolge(admin_client.get(URL, {"sort": "datum"})) == [2, 1, 0]
    assert _reihenfolge(admin_client.get(URL, {"sort": "-kunde"}))[-1] == 0  # 00077 vor 00042
    assert _reihenfolge(admin_client.get(URL, {"sort": "stelle"}))[0] == 0  # Mitte vor Nord
    assert _reihenfolge(admin_client.get(URL, {"sort": "-von"}))[0] == 2  # Verwaltung vor Büro
    nach_text = sorted(range(3), key=lambda i: TEXTE[i])
    assert _reihenfolge(admin_client.get(URL, {"sort": "text"})) == nach_text
    assert _reihenfolge(admin_client.get(URL, {"sort": "unsinn"})) == [0, 1, 2]
    inhalt = admin_client.get(URL, {"sort": "text"}).content.decode()
    assert 'name="sort" value="text"' in inhalt and "sort=-text" in inhalt
