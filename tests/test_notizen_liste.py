"""Liste aller Notizen (ADR 0143): filtern, exportieren, löschen. Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe, Notiz, Person

pytestmark = pytest.mark.django_db
URL = reverse("kunden:notizen")
LOESCHEN = reverse("kunden:notizen_loeschen")


def _haushalt(nummer, nachname, stelle):
    gruppe = Kundengruppe.objects.create(name=f"Gruppe {nummer}", ausgabestelle=stelle)
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe)
    Person.objects.create(haushalt=h, vorname="Erika", nachname=nachname, ist_hauptperson=True)
    return h


@pytest.fixture
def notizen(admin):
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    _haushalt("00042", "Beispiel", mitte)
    _haushalt("00077", "Muster", nord)
    jetzt = timezone.now()
    return {
        "einfach": Notiz.objects.create(kundennummer="00042", text="Bringt Tüten mit",
                                        verfasst_von="Büro", erstellt_am=jetzt),
        "stelle": Notiz.objects.create(kundennummer="00077", text="Bitte Ausweis zeigen lassen",
                                       verfasst_von="Büro", an_stelle=True,
                                       erstellt_am=jetzt - dt.timedelta(days=3)),
        "krank": Notiz.objects.create(kundennummer="00077", text="Krank gemeldet",
                                      verfasst_von="Einlass", krank_von=dt.date(2026, 11, 2),
                                      krank_bis=dt.date(2026, 11, 9), krank_grund="krank",
                                      erstellt_am=jetzt - dt.timedelta(days=20)),
        "mitte": mitte, "nord": nord,
    }  # fmt: skip


def _texte(antwort):
    inhalt = antwort.content.decode()
    return [t for t in ("Bringt Tüten mit", "Bitte Ausweis zeigen lassen", "Krank gemeldet")
            if t in inhalt]  # fmt: skip


def test_liste_und_filter(admin_client, notizen):
    inhalt = admin_client.get(URL).content.decode()
    assert "3 Notizen" in inhalt and "Beispiel, Erika" in inhalt and "Nord" in inhalt
    assert reverse("kunden:haushalt", args=["00042"]) in inhalt
    assert _texte(admin_client.get(URL, {"art": "an_stelle"})) == ["Bitte Ausweis zeigen lassen"]
    assert _texte(admin_client.get(URL, {"art": "ungelesen"})) == ["Bitte Ausweis zeigen lassen"]
    assert _texte(admin_client.get(URL, {"art": "abwesend"})) == ["Krank gemeldet"]
    assert _texte(admin_client.get(URL, {"art": "einfach"})) == ["Bringt Tüten mit"]
    assert _texte(admin_client.get(URL, {"stelle": notizen["mitte"].pk})) == ["Bringt Tüten mit"]
    assert _texte(admin_client.get(URL, {"q": "muster"})) == ["Bitte Ausweis zeigen lassen",
                                                              "Krank gemeldet"]  # fmt: skip
    assert _texte(admin_client.get(URL, {"q": "tüten"})) == ["Bringt Tüten mit"]
    gestern = (timezone.localdate() - dt.timedelta(days=1)).isoformat()
    assert _texte(admin_client.get(URL, {"von": gestern})) == ["Bringt Tüten mit"]
    assert _texte(admin_client.get(URL, {"bis": gestern})) == ["Bitte Ausweis zeigen lassen",
                                                               "Krank gemeldet"]  # fmt: skip
    assert "Keine Notizen gefunden" in admin_client.get(URL, {"q": "gibtesnicht"}).content.decode()
    # gelesene Notiz an die Stelle ist nicht mehr „ungelesen“
    Notiz.objects.filter(pk=notizen["stelle"].pk).update(gelesen_am=timezone.now())
    assert _texte(admin_client.get(URL, {"art": "ungelesen"})) == []


def test_export_alle_und_angehakte(admin_client, notizen):
    alles = admin_client.get(URL, {"aktion": "csv"})
    assert alles["Content-Type"].startswith("text/csv")
    text = alles.content.decode()
    assert text.splitlines()[0].startswith("Geschrieben am;Kundennummer;Kunde;Ausgabestelle;Art")
    assert "00042;Beispiel, Erika;Mitte;Notiz;Bringt Tüten mit;Büro" in text
    assert "Krank gemeldet 02.11.2026 bis 09.11.2026" in text and len(text.splitlines()) == 4
    nur = admin_client.get(URL, {"aktion": "csv", "id": notizen["krank"].pk}).content.decode()
    assert len(nur.splitlines()) == 2 and "Krank gemeldet" in nur
    assert admin_client.get(URL, {"aktion": "pdf"})["Content-Type"] == "application/pdf"


def test_loeschen_in_den_papierkorb(admin_client, notizen):
    from apps.core.models import PapierkorbEintrag

    assert admin_client.get(LOESCHEN).status_code == 405
    antwort = admin_client.post(LOESCHEN, {"id": [notizen["einfach"].pk, notizen["krank"].pk],
                                           "zurueck": URL + "?art=einfach"})  # fmt: skip
    assert antwort.url == URL + "?art=einfach"
    assert list(Notiz.objects.values_list("text", flat=True)) == ["Bitte Ausweis zeigen lassen"]
    assert PapierkorbEintrag.objects.count() == 2
    # fremdes Ziel wird nicht angesprungen, ohne Haken passiert nichts
    antwort = admin_client.post(LOESCHEN, {"zurueck": "https://boese.example/"})
    assert antwort.url == URL and Notiz.objects.count() == 1


def test_nur_mit_recht_und_nur_eigene_kunden(client, admin, notizen, benutzer_mit_rolle, anmelden,
                                             recht_geben):  # fmt: skip
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.ausgabestellen.set([notizen["mitte"]])
    c = anmelden(Client(), anton)
    assert c.get(URL).status_code == 403  # Einlass: Notizen nur beim einzelnen Kunden
    assert c.post(LOESCHEN, {"id": notizen["einfach"].pk}).status_code == 403
    recht_geben(rollen.AUSGABE, "kunden.notizen_loeschen")
    c = anmelden(Client(), anton)
    assert _texte(c.get(URL)) == ["Bringt Tüten mit"]  # nur Kunden der eigenen Ausgabestelle
    assert "Ausgabestelle</label>" not in c.get(URL).content.decode()  # nur eine: kein Filter
    c.post(LOESCHEN, {"id": [notizen["stelle"].pk, notizen["einfach"].pk]})
    assert sorted(Notiz.objects.values_list("kundennummer", flat=True)) == ["00077", "00077"]


def test_im_menue_unter_kunden(admin):
    from django.test import RequestFactory

    from apps.core.menue import menue

    anfrage = RequestFactory().get("/")
    anfrage.user = admin
    bereiche = {b["titel"]: str(b) for b in menue(anfrage)}
    assert URL in bereiche["Kunden"]


def _reihenfolge(antwort):
    inhalt = antwort.content.decode()
    texte = ("Bringt Tüten mit", "Bitte Ausweis zeigen lassen", "Krank gemeldet")
    return [t.split()[0] for t in sorted(texte, key=inhalt.index)]


def test_spalten_sortieren(admin_client, notizen):
    """Jeder Spaltenkopf sortiert, wie in den anderen Listen; Vorgabe: neueste zuerst."""
    assert _reihenfolge(admin_client.get(URL)) == ["Bringt", "Bitte", "Krank"]
    assert _reihenfolge(admin_client.get(URL, {"sort": "datum"})) == ["Krank", "Bitte", "Bringt"]
    assert _reihenfolge(admin_client.get(URL, {"sort": "text"})) == ["Bitte", "Bringt", "Krank"]
    assert _reihenfolge(admin_client.get(URL, {"sort": "-text"})) == ["Krank", "Bringt", "Bitte"]
    assert _reihenfolge(admin_client.get(URL, {"sort": "kunde"}))[0] == "Bringt"  # 00042 vor 00077
    assert _reihenfolge(admin_client.get(URL, {"sort": "-stelle"}))[-1] == "Bringt"  # Nord, Mitte
    assert _reihenfolge(admin_client.get(URL, {"sort": "art"})) == ["Bringt", "Bitte", "Krank"]
    assert _reihenfolge(admin_client.get(URL, {"sort": "von"}))[-1] == "Krank"  # Büro, Einlass
    assert _reihenfolge(admin_client.get(URL, {"sort": "unsinn"})) == ["Bringt", "Bitte", "Krank"]
    inhalt = admin_client.get(URL, {"sort": "text", "art": "einfach"}).content.decode()
    assert 'name="sort" value="text"' in inhalt  # der Filter behält die Sortierung
    assert "sort=-text" in inhalt and "art=einfach" in inhalt  # der Kopf behält den Filter
