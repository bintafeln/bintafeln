"""Historie eines Haushalts (ADR 0031). Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.antraege import aufnahme
from apps.konten import rollen
from apps.kunden import historie, importieren
from apps.kunden.models import (
    Haushalt,
    HaushaltEreignis,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    alte_historie_loeschen,
)
from tests.test_aufnahme import antrag

pytestmark = pytest.mark.django_db


def stand(**mehr):
    return {"status": "aktiv", "kundengruppe": "Montag", "ausweis": dt.date(2026, 1, 31),
            "personen": ["Erika Probe"], **mehr}  # fmt: skip


def texte(nummer=None):
    ereignisse = HaushaltEreignis.objects.order_by("id")
    if nummer:
        ereignisse = ereignisse.filter(kundennummer=nummer)
    return list(ereignisse.values_list("text", flat=True))


def test_unterschiede():
    assert historie.unterschiede(None, None) == []
    assert historie.unterschiede(None, stand()) == ["Neu im Kundenstamm"]
    assert historie.unterschiede(stand(), None) == ["Nicht mehr im Kundenstamm"]
    assert historie.unterschiede(stand(), stand()) == []
    assert historie.unterschiede(
        stand(),
        stand(status="pausiert", kundengruppe="", ausweis=dt.date(2027, 1, 31),
              personen=["Erika Probe", "Mia Probe (geb. 18.08.2015)"]),
    ) == [
        "Status: aktiv → pausiert",
        "Kundengruppe: Montag → –",
        "Ausweis verlängert: 31.01.2026 → 31.01.2027",
        "Person hinzugekommen: Mia Probe (geb. 18.08.2015)",
    ]  # fmt: skip
    assert historie.unterschiede(stand(), stand(ausweis=None, personen=[])) == [
        "Ausweis gültig bis geändert: 31.01.2026 → –",
        "Person entfallen: Erika Probe",
    ]


def importieren_csv(*zeilen, von=None):
    datei = "kundennummer;nachname;vorname;status;ausweis_gueltig_bis\n" + "\n".join(zeilen)
    ergebnis = importieren.pruefen({"haushalte.csv": (datei + "\n").encode()})
    assert ergebnis.daten is not None, ergebnis.bericht
    return importieren.uebernehmen(
        ergebnis.daten, benutzer=von, dateien=ergebnis.dateien,
        pruefsumme=ergebnis.pruefsumme, anzahl_warnungen=0,
    )  # fmt: skip


def test_import_haelt_unterschiede_fest(admin):
    importieren_csv("1;Probe;Erika;aktiv;2026-01-31", "2;Test;Max;aktiv;", von=admin)
    assert texte() == ["Neu im Kundenstamm", "Neu im Kundenstamm"]
    assert set(HaushaltEreignis.objects.values_list("quelle", "von")) == {("import", "chefin")}

    HaushaltEreignis.objects.all().delete()
    importieren_csv("1;Probe;Erika;pausiert;2027-01-31", "3;Neu;Nina;aktiv;")
    assert texte("1") == ["Status: aktiv → pausiert", "Ausweis verlängert: 31.01.2026 → 31.01.2027"]
    assert texte("2") == ["Nicht mehr im Kundenstamm"]
    assert texte("3") == ["Neu im Kundenstamm"]

    HaushaltEreignis.objects.all().delete()
    importieren_csv("1;Probe;Erika;pausiert;2027-01-31", "3;Neu;Nina;aktiv;")
    assert texte() == []  # gleicher Stand, nichts Neues


def test_bearbeiten_haelt_fest(admin_client, gruppe_behalten):
    gruppe = Kundengruppe.objects.create(name="Dienstag")
    admin_client.post(reverse("kunden:haushalt_neu"), {
        "kundennummer": "77", "hp-vorname": "Erika", "hp-nachname": "Neu", "a-TOTAL_FORMS": "0",
        "a-INITIAL_FORMS": "0", "gueltig_bis": ""})  # fmt: skip
    assert texte("77") == ["Angelegt"]
    admin_client.post(
        reverse("kunden:bearbeiten", args=["77"]),
        {"kundennummer": "77", "status": "gesperrt", "kundengruppe": gruppe.pk},
    )
    assert texte("77")[1:] == ["Status: aktiv → gesperrt", "Kundengruppe: – → Dienstag"]
    assert HaushaltEreignis.objects.filter(von="chefin", quelle="bearbeitung").count() == 3

    admin_client.post(
        reverse("kunden:teil_neu", args=["77", "person"]),
        {"vorname": "Mia", "nachname": "Probe", "geburtsdatum": "2015-08-18"},
    )
    assert texte("77")[-1] == "Person hinzugekommen: Mia Probe (geb. 18.08.2015)"
    p = Person.objects.get(vorname="Mia")
    admin_client.post(reverse("kunden:teil_loeschen", args=["77", "person", p.pk]))
    assert texte("77")[-1] == "Person entfallen: Mia Probe (geb. 18.08.2015)"

    # Kundennummer ändern nimmt die Historie mit, Löschen entfernt sie
    admin_client.post(
        reverse("kunden:bearbeiten", args=["77"]), {"kundennummer": "78", "status": "gesperrt"}
    )
    assert not HaushaltEreignis.objects.filter(kundennummer="77").exists()
    assert (
        "Einträge der Historie"
        in admin_client.get(reverse("kunden:haushalt_loeschen", args=["78"])).content.decode()
    )
    admin_client.post(reverse("kunden:haushalt_loeschen", args=["78"]))
    assert not HaushaltEreignis.objects.exists()


def test_aufnahme_haelt_fest():
    a = antrag()
    zustand = {"haushalt": None, "werte": {"vorname": "Erika", "nachname": "Mustermann"},
               "personen": [{"pk": None, "vorname": "Mia", "nachname": "Mustermann",
                             "geburtsdatum": "2015-08-18"}],
               "gueltig_bis": "2027-10-31"}  # fmt: skip
    h = aufnahme.uebernehmen(a, zustand, "berta")
    assert texte(h.kundennummer) == [f"Aufgenommen mit Antrag {a.nummer}"]
    assert set(HaushaltEreignis.objects.values_list("quelle", "von")) == {("aufnahme", "berta")}

    b = antrag(vorname="Erika")
    zustand = {**zustand, "haushalt": h.kundennummer, "gueltig_bis": "2028-10-31"}
    aufnahme.uebernehmen(b, zustand, "berta")
    assert texte(h.kundennummer)[-2:] == [
        f"Aktualisiert mit Antrag {b.nummer}",
        "Ausweis verlängert: 31.10.2027 → 31.10.2028",
    ]


def test_anzeige_nur_admin_und_buero(client, admin_client, benutzer_mit_rolle, anmelden):
    h = Haushalt.objects.create(kundennummer="5")
    HaushaltEreignis.objects.create(kundennummer="5", quelle="import", text="Neu im Kundenstamm")
    seite = admin_client.get(reverse("kunden:haushalt", args=["5"])).content.decode()
    assert "Historie" in seite and "Neu im Kundenstamm" in seite
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    seite = client.get(reverse("kunden:haushalt", args=[h.kundennummer])).content.decode()
    assert "Neu im Kundenstamm" not in seite


def test_frist():
    e = KundenEinstellungen.laden()
    e.historie_aufbewahren_jahre = 2
    e.save()
    alt = HaushaltEreignis.objects.create(kundennummer="5", quelle="import", text="alt")
    HaushaltEreignis.objects.filter(pk=alt.pk).update(
        zeitpunkt=timezone.make_aware(dt.datetime(2024, 10, 23, 23, 0))
    )
    HaushaltEreignis.objects.create(kundennummer="5", quelle="import", text="neu")
    assert alte_historie_loeschen(dt.date(2026, 10, 24)) == 1
    assert texte() == ["neu"]
    assert alte_historie_loeschen(dt.date(2028, 2, 29)) == 0  # Schalttag geht


def test_auskunft_nennt_historie(admin_client, pdf_text):
    Haushalt.objects.create(kundennummer="5")
    HaushaltEreignis.objects.create(
        kundennummer="5", quelle="import", text="Status: aktiv → pausiert"
    )
    text = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["5"])))
    assert "Historie" in text and "pausiert" in text
