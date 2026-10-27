"""Papierkorb für gelöschte Daten (ADR 0073). Nur erfundene Daten."""

import datetime as dt
from decimal import Decimal

import pytest
from django.contrib.auth.models import Group
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone

from apps.adressen.models import Adresse
from apps.ausgabe import konto
from apps.ausgabe.models import Buchung
from apps.core import papierkorb, privatdateien
from apps.core.forms import EinstellungenForm
from apps.core.models import PapierkorbEintrag, TafelEinstellungen
from apps.konten import rollen
from apps.konten.models import Rolle
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    HaushaltDokument,
    Kundengruppe,
    Notiz,
    Person,
)

pytestmark = pytest.mark.django_db
KORB = reverse("core:papierkorb")


@pytest.fixture
def stellen():
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    return {
        s.name: Kundengruppe.objects.create(name=f"{s.name} Mo", ausgabestelle=s, wochentage="Mo")
        for s in (mitte, nord)
    }


def haushalt(nummer, gruppe=None):
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster")
    Person.objects.create(haushalt=h, vorname="Kim", nachname="Muster")
    return h


def test_haushalt_mit_allem_wiederherstellen(admin, admin_client, stellen):
    h = haushalt("4711", stellen["Mitte"])
    Notiz.objects.create(kundennummer="4711", text="Bringt Tasche mit", verfasst_von="chefin")
    buchung = konto.einzahlen(h, Decimal("5"), None, "chefin")
    admin_client.post(reverse("kunden:haushalt_loeschen", args=["4711"]))
    assert not Haushalt.objects.exists() and not Notiz.objects.exists()
    assert Buchung.objects.get(pk=buchung.pk).haushalt_id is None  # bleibt für die Kasse
    e = PapierkorbEintrag.objects.get()
    assert (e.art, e.bezeichnung, e.recht) == ("Haushalt", "4711 – Erika Muster", "kunden.loeschen")
    assert e.stelle_id == stellen["Mitte"].ausgabestelle_id and e.geloescht_von == "chefin"

    seite = admin_client.get(KORB).content.decode()
    assert "4711 – Erika Muster" in seite and "Wiederherstellen" in seite
    assert "Papierkorb leeren nach" in seite  # Weg zur Einstellung
    detail = admin_client.get(reverse("core:papierkorb_eintrag", args=[e.pk])).content.decode()
    assert "Bringt Tasche mit" in detail and "Kim" in detail

    admin_client.post(reverse("core:papierkorb_wiederherstellen", args=[e.pk]))
    h2 = Haushalt.objects.get(kundennummer="4711")
    assert h2.pk == h.pk and h2.personen.count() == 2 and Notiz.objects.count() == 1
    assert Buchung.objects.get(pk=buchung.pk).haushalt_id == h.pk
    assert not PapierkorbEintrag.objects.exists()
    assert "Der Papierkorb ist leer" in admin_client.get(KORB).content.decode()


def test_konflikt_laesst_eintrag_liegen(admin, admin_client, stellen):
    h = haushalt("4712", stellen["Mitte"])
    e = papierkorb.loeschen(admin, "Haushalt", "4712", h, recht="kunden.loeschen",
                            kundennummer="4712")  # fmt: skip
    Haushalt.objects.create(kundennummer="4712")  # Nummer inzwischen neu vergeben
    antwort = admin_client.post(reverse("core:papierkorb_wiederherstellen", args=[e.pk]),
                                follow=True)  # fmt: skip
    assert "neu vergebene Kundennummer" in antwort.content.decode()
    assert PapierkorbEintrag.objects.filter(pk=e.pk).exists()
    assert Person.objects.count() == 0  # nichts halb wiederhergestellt

    # Fehlt etwas, auf das verwiesen wird, auch: Kundengruppe inzwischen weg
    Haushalt.objects.all().delete()
    stellen["Mitte"].delete()
    with pytest.raises(papierkorb.PapierkorbFehler, match="gelöschte Kundengruppe"):
        papierkorb.wiederherstellen(e)
    # Gibt es einen Datensatz mit derselben Nummer schon, wird nichts überschrieben
    nord = stellen["Nord"].pk
    e2 = papierkorb.loeschen(admin, "Kundengruppe", "Nord", stellen["Nord"],
                             recht="einstellungen.listen")  # fmt: skip
    Kundengruppe.objects.create(pk=nord, name="Neu", wochentage="Di")
    with pytest.raises(papierkorb.PapierkorbFehler, match="gibt es schon"):
        papierkorb.wiederherstellen(e2)


def test_sichtbar_nur_mit_recht_und_eigener_stelle(admin, client, benutzer_mit_rolle, anmelden,
                                                  stellen, recht_geben):  # fmt: skip
    papierkorb.loeschen(admin, "Haushalt", "Mitte", haushalt("1", stellen["Mitte"]),
                        recht="kunden.loeschen", kundennummer="1")  # fmt: skip
    papierkorb.loeschen(admin, "Haushalt", "Nord", haushalt("2", stellen["Nord"]),
                        recht="kunden.loeschen", kundennummer="2")  # fmt: skip
    a = Adresse.objects.create(nachname="Spender", vorname="Sam")
    papierkorb.loeschen(admin, "Adresse", "Sam Spender", a, recht="adressen.loeschen")

    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anmelden(client, anton)
    assert client.get(KORB).status_code == 200
    assert "Der Papierkorb ist leer" in client.get(KORB).content.decode()
    assert "Papierkorb" not in client.get(reverse("core:start")).content.decode()  # kein Menü
    eintrag = PapierkorbEintrag.objects.get(bezeichnung="Mitte")
    assert client.get(reverse("core:papierkorb_eintrag", args=[eintrag.pk])).status_code == 404
    assert client.post(reverse("core:papierkorb_loeschen", args=[eintrag.pk])).status_code == 404

    recht_geben(rollen.AUSGABE, "kunden.loeschen")
    anton.ausgabestellen.add(stellen["Mitte"].ausgabestelle)
    sichtbar = list(papierkorb.sichtbar(anton).values_list("bezeichnung", flat=True))
    assert sichtbar == ["Mitte"]  # nur die eigene Ausgabestelle, keine Adresse
    seite = client.get(reverse("core:start")).content.decode()
    assert 'title="Einträge im Papierkorb">1<' in seite
    # Filter nach Art (Admin sieht alles)
    assert set(papierkorb.sichtbar(admin).values_list("art", flat=True)) == {"Haushalt", "Adresse"}


def test_frist_und_dateien(admin, stellen, django_capture_on_commit_callbacks):
    h = haushalt("3001", stellen["Mitte"])

    class Datei:
        name, size, content_type = "b.pdf", 4, "application/pdf"

        def read(self):
            return b"%PDF"

    from apps.kunden.models import Dokumentart

    art, _ = Dokumentart.objects.get_or_create(bezeichnung="Bescheid")
    d = HaushaltDokument.objects.create(
        kundennummer="3001", art=art, titel="Bescheid",
        datei=privatdateien.speichern(HaushaltDokument.ORDNER, Datei()), typ="application/pdf",
    )  # fmt: skip
    datei = privatdateien.pfad(HaushaltDokument.ORDNER, d.datei)
    e = papierkorb.loeschen(admin, "Haushalt", "3001", h,
                            HaushaltDokument.objects.filter(kundennummer="3001"),
                            recht="kunden.loeschen", kundennummer="3001")  # fmt: skip
    assert e.dateien == [[HaushaltDokument.ORDNER, d.datei]] and datei.exists()
    jetzt = timezone.now()
    assert papierkorb.fristen_anwenden(jetzt + dt.timedelta(days=29)) == 0
    t = TafelEinstellungen.laden()
    t.papierkorb_tage = 60
    t.save()
    assert papierkorb.fristen_anwenden(jetzt + dt.timedelta(days=31)) == 0
    assert papierkorb.endgueltig_am(e, 60) == timezone.localdate(e.geloescht_am) + dt.timedelta(60)
    with django_capture_on_commit_callbacks(execute=True):
        assert papierkorb.fristen_anwenden(jetzt + dt.timedelta(days=61)) == 1
    assert not PapierkorbEintrag.objects.exists() and not datei.exists()


def test_einstellung_tage():
    form = EinstellungenForm(instance=TafelEinstellungen.laden())
    assert [w for w, _ in form.fields["papierkorb_tage"].choices if w] == [30, 60, 90, 365]
    form = EinstellungenForm({"name": "Tafel", "papierkorb_tage": "365"},
                             instance=TafelEinstellungen.laden())  # fmt: skip
    assert form.is_valid(), form.errors
    assert form.save().papierkorb_tage == 365
    form = EinstellungenForm({"name": "Tafel"}, instance=TafelEinstellungen.laden())
    assert form.is_valid() and form.save().papierkorb_tage == 365  # fehlt: bleibt


def test_rolle_mit_konten_und_rechten(admin, admin_client, benutzer_mit_rolle, recht_geben):
    gruppe = Group.objects.create(name="Fahrdienst")
    Rolle.objects.filter(gruppe=gruppe).update(rechte=["kunden.liste", "system.update"])
    benutzer_mit_rolle("fritz", "Fahrdienst")
    admin_client.post(reverse("konten:rolle_loeschen", args=[gruppe.rolle.pk]))
    assert not Group.objects.filter(name="Fahrdienst").exists()
    e = PapierkorbEintrag.objects.get(art="Rolle")
    # Wer nicht alle Rechte der Rolle hat, holt sie nicht zurück
    buero = benutzer_mit_rolle("berta", rollen.BUERO)
    recht_geben(rollen.BUERO, "einstellungen.rollen")
    with pytest.raises(papierkorb.PapierkorbFehler, match="Rechte, die Sie nicht haben"):
        papierkorb.wiederherstellen(e, buero)
    papierkorb.wiederherstellen(e, admin)
    assert list(Group.objects.get(name="Fahrdienst").user_set.values_list("username", flat=True)
                ) == ["fritz"]  # fmt: skip


def test_listeneintrag_und_geschuetzt(admin, admin_client, stellen):
    url = reverse(
        "kunden:listeneintrag_loeschen", args=["ausgabestellen", stellen["Nord"].ausgabestelle_id]
    )
    admin_client.post(url)  # Kundengruppe verweist noch darauf: bleibt
    assert Ausgabestelle.objects.filter(name="Nord").exists()
    assert not PapierkorbEintrag.objects.exists()
    with pytest.raises(ProtectedError):
        papierkorb.loeschen(admin, "Ausgabestelle", "Nord", stellen["Nord"].ausgabestelle,
                            recht="einstellungen.listen")  # fmt: skip
    url = reverse("kunden:listeneintrag_loeschen", args=["kundengruppen", stellen["Nord"].pk])
    admin_client.post(url)
    assert PapierkorbEintrag.objects.get().art == "Kundengruppe"


def test_endgueltig_und_unlesbare_daten(admin, admin_client):
    a = Adresse.objects.create(nachname="Spender", vorname="Sam")
    admin_client.post(reverse("adressen:loeschen", args=[a.pk]))
    e = PapierkorbEintrag.objects.get()
    assert e.art == "Adresse" and not Adresse.objects.exists()
    # Felder nach einem Update weg: lesbare Meldung statt Fehler
    e.daten[0]["fields"]["gibt_es_nicht"] = 1
    e.save()
    inhalt = papierkorb.inhalt(e)
    assert inhalt[0]["art"] == "Adresse" and ("Gibt_es_nicht", 1) in inhalt[0]["felder"]
    with pytest.raises(papierkorb.PapierkorbFehler, match="nach einem Update"):
        papierkorb.wiederherstellen(e)
    e.daten = [{"model": "alt.weg", "pk": 1, "fields": {"name": "x"}}]
    e.save()
    assert papierkorb.inhalt(e) == [{"art": "alt.weg", "pk": 1, "felder": [("Name", "x")]}]
    admin_client.post(reverse("core:papierkorb_loeschen", args=[e.pk]))
    assert not PapierkorbEintrag.objects.exists()


def test_auskunft_nennt_papierkorb(admin_client, stellen, pdf_text):
    haushalt("5001", stellen["Mitte"])
    n = Notiz.objects.create(kundennummer="5001", text="Ruft vorher an")
    admin_client.post(reverse("kunden:notiz_loeschen", args=[n.pk]))
    text = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["5001"])))
    assert "Gelöscht, noch im Papierkorb" in text and "Ruft vorher an" in text


def test_zuordnungen_und_inhalt_nur_mit_recht(admin, client, benutzer_mit_rolle, anmelden,
                                             stellen, recht_geben):  # fmt: skip
    from apps.ausgabe.models import Sonderausgabe
    from apps.kunden.models import Zugriff

    s = Sonderausgabe.objects.create(datum=dt.date(2026, 12, 23),
                                     ausgabestelle=stellen["Mitte"].ausgabestelle)  # fmt: skip
    s.kundengruppen.set([stellen["Mitte"], stellen["Nord"]])
    e = papierkorb.loeschen(admin, "Sonderausgabe", str(s), s, recht="einstellungen.listen")
    papierkorb.wiederherstellen(e)
    assert set(Sonderausgabe.objects.get().kundengruppen.all()) == set(stellen.values())

    h = haushalt("6001", stellen["Mitte"])
    h.personen.update(zusatz={"schwerbehindert": True})
    e = papierkorb.loeschen(admin, "Haushalt", "6001", h, recht="kunden.loeschen",
                            kundennummer="6001")  # fmt: skip
    url = reverse("core:papierkorb_eintrag", args=[e.pk])
    berta = benutzer_mit_rolle("berta", rollen.BUERO)
    recht_geben(rollen.BUERO, "kunden.loeschen")
    Rolle.objects.filter(gruppe__name=rollen.BUERO).update(rechte=["kunden.loeschen"])
    anmelden(client, berta)
    seite = client.get(url).content.decode()
    assert "<li>Person</li>" in seite and "schwerbehindert" not in seite
    assert not Zugriff.objects.filter(benutzername="berta").exists()
    recht_geben(rollen.BUERO, "kunden.besondere_kategorie")
    assert "schwerbehindert" in client.get(url).content.decode()
    assert Zugriff.objects.get(benutzername="berta").kundennummer == "6001"
