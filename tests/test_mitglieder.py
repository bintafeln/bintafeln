"""Mitglieder (ADR 0046). Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.konten import rollen
from apps.mitglieder.models import Mitglied, MitgliederEinstellungen, naechste_nummer
from apps.spenden.models import Spende

pytestmark = pytest.mark.django_db
D = Decimal


@pytest.fixture
def erika():
    return Adresse.objects.create(art="person", vorname="Erika", nachname="Muster",
                                  strasse="Weg 1", plz="12345", ort="Musterstadt")  # fmt: skip


def mitglied(adresse, **mehr):
    werte = {"nummer": "1", "art": "Ordentliches Mitglied", "eintritt": dt.date(2025, 4, 15),
             "jahresbeitrag": D("36")} | mehr  # fmt: skip
    return Mitglied.objects.create(adresse=adresse, **werte)


def test_soll_monate_und_gezahlt(erika):
    m = mitglied(erika, austritt=dt.date(2026, 6, 30))
    assert m.monate(2024) == 0 and m.monate(2025) == 9 and m.monate(2026) == 6
    assert m.soll(2025, anteilig=False) == D("36") and m.soll(2025, anteilig=True) == D("27.00")
    assert m.soll(2027, anteilig=False) == 0
    assert m.ist_mitglied(dt.date(2026, 6, 30)) and not m.ist_mitglied(dt.date(2026, 7, 1))
    Spende.objects.create(adresse=erika, datum=dt.date(2025, 5, 1), betrag=D("20"),
                          mitgliedsbeitrag=True)  # fmt: skip
    Spende.objects.create(adresse=erika, datum=dt.date(2025, 6, 1), betrag=D("100"))  # Spende
    assert m.gezahlt(2025) == D("20")


def test_nummern():
    e = MitgliederEinstellungen.laden()
    e.naechste_nummer = 5
    e.save()
    mitglied(Adresse.objects.create(organisation="Verein X"), nummer="6")
    assert naechste_nummer() == "5" and naechste_nummer() == "7"


def beitraege_an():
    e = MitgliederEinstellungen.laden()
    e.beitraege = True
    e.save()


def test_anlegen_liste_beitraege(admin_client, erika):
    beitraege_an()
    neu = reverse("mitglieder:neu")
    seite = admin_client.get(neu, {"adresse": erika.pk}).content.decode()
    assert f'<option value="{erika.pk}" selected>' in seite and "Fördermitglied" in seite
    assert 'value="1"' in seite  # vorgeschlagene Nummer
    daten = {"adresse": erika.pk, "nummer": "1", "art": "Fördermitglied",
             "eintritt": "2026-02-01", "jahresbeitrag": "36,00", "zahlweise": "jährlich",
             "zahlungsart": "Überweisung"}  # fmt: skip
    antwort = admin_client.post(neu, daten)
    m = Mitglied.objects.get()
    assert antwort.url == reverse("mitglieder:mitglied", args=[m.pk])
    assert MitgliederEinstellungen.laden().naechste_nummer == 2
    # Austritt braucht einen Grund
    fehlt = admin_client.post(reverse("mitglieder:bearbeiten", args=[m.pk]),
                              daten | {"austritt": "2026-12-31"})  # fmt: skip
    assert "Grund des Austritts" in fehlt.content.decode()
    # Beitragsseite mit Link zur Zahlung (Spende als Mitgliedsbeitrag, vorbelegt)
    seite = admin_client.get(antwort.url).content.decode()
    assert "Zahlung erfassen" in seite and "betrag=36.00" in seite
    spende = admin_client.get(
        reverse("spenden:neu"), {"adresse": erika.pk, "mitgliedsbeitrag": "1", "betrag": "36.00"}
    )
    formular = spende.content.decode()
    assert 'name="mitgliedsbeitrag" id="id_mitgliedsbeitrag" checked' in formular
    assert 'value="36,00"' in formular
    Spende.objects.create(adresse=erika, datum=dt.date(2026, 3, 1), betrag=D("36"),
                          mitgliedsbeitrag=True)  # fmt: skip
    liste = admin_client.get(reverse("mitglieder:liste"), {"jahr": "2026"}).content.decode()
    assert "Erika Muster" in liste and "36,00 €" in liste
    offen = admin_client.get(reverse("mitglieder:liste"), {"jahr": "2026", "nur_offen": "1"})
    assert "Erika Muster" not in offen.content.decode()
    csv = admin_client.get(reverse("mitglieder:liste"), {"jahr": "2026", "csv": "1"})
    assert "1;Erika Muster;Weg 1, 12345 Musterstadt" in csv.content.decode()
    # Adresse zeigt die Mitgliedschaft und ist nicht löschbar
    adresse = admin_client.get(reverse("adressen:adresse", args=[erika.pk])).content.decode()
    assert "Mitglied Nr. 1" in adresse
    admin_client.post(reverse("adressen:loeschen", args=[erika.pk]))
    assert Adresse.objects.filter(pk=erika.pk).exists()
    admin_client.post(reverse("mitglieder:loeschen", args=[m.pk]))
    assert not Mitglied.objects.exists() and Spende.objects.exists()


def test_ohne_beitraege_nichts_zu_beitraegen(admin_client, erika, pdf_text):
    assert not MitgliederEinstellungen.mit_beitraegen()  # Vorgabe: die meisten Tafeln ohne
    formular = admin_client.get(reverse("mitglieder:neu")).content.decode()
    assert "Jahresbeitrag" not in formular and "Zahlweise" not in formular
    daten = {"adresse": erika.pk, "nummer": "1", "art": "Fördermitglied", "eintritt": "2026-02-01"}
    admin_client.post(reverse("mitglieder:neu"), daten)
    m = Mitglied.objects.get()
    assert m.jahresbeitrag == 0
    for seite in (reverse("mitglieder:liste"), reverse("mitglieder:mitglied", args=[m.pk])):
        inhalt = admin_client.get(seite).content.decode()
        assert "Erika Muster" in inhalt
        assert not any(
            w in inhalt for w in ("Soll", "offenem Beitrag", "Jahresbeitrag", "Zahlung erfassen")
        )
    csv = admin_client.get(reverse("mitglieder:liste"), {"csv": "1"}).content.decode()
    assert "Soll" not in csv and csv.splitlines()[1].endswith(";Fördermitglied;01.02.2026;")
    assert "mitgliedsbeitrag" not in admin_client.get(reverse("spenden:neu")).content.decode()
    einst = admin_client.get(reverse("mitglieder:einstellungen")).content.decode()
    assert "Mitglieder zahlen Beiträge" in einst and "standard_beitrag" not in einst
    serien = admin_client.get(reverse("serienbriefe:erstellen")).content.decode()
    assert "nur_offen" not in serien
    vorlage = admin_client.get(reverse("serienbriefe:vorlage_neu")).content.decode()
    assert "{beitrag_offen}" not in vorlage and "{mitgliedsnummer}" in vorlage
    text = pdf_text(admin_client.get(reverse("adressen:auskunft", args=[erika.pk])))
    assert "Fördermitglied" in text and "Jahresbeitrag" not in text
    # Einschalten: alles wieder da
    admin_client.post(
        reverse("mitglieder:einstellungen"), {"beitraege": "on", "naechste_nummer": 2}
    )
    assert MitgliederEinstellungen.mit_beitraegen()
    einst = admin_client.get(reverse("mitglieder:einstellungen")).content.decode()
    assert "standard_beitrag" in einst
    assert "Soll" in admin_client.get(reverse("mitglieder:liste")).content.decode()
    assert "mitgliedsbeitrag" in admin_client.get(reverse("spenden:neu")).content.decode()
    assert "nur_offen" in admin_client.get(reverse("serienbriefe:erstellen")).content.decode()


def test_vorhandener_mitgliedsbeitrag_bleibt_sichtbar(admin_client, erika):
    s = Spende.objects.create(adresse=erika, datum=dt.date(2026, 3, 1), betrag=D("36"),
                              mitgliedsbeitrag=True)  # fmt: skip
    seite = admin_client.get(reverse("spenden:bearbeiten", args=[s.pk])).content.decode()
    assert 'name="mitgliedsbeitrag"' in seite


def test_auskunft(admin_client, erika, pdf_text):
    mitglied(erika)
    text = pdf_text(admin_client.get(reverse("adressen:auskunft", args=[erika.pk])))
    assert "Mitgliedschaft" in text and "Ordentliches Mitglied" in text


def test_rechte(client, admin, benutzer_mit_rolle, anmelden, erika):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(reverse("mitglieder:liste")).status_code == 200
    assert client.get(reverse("mitglieder:einstellungen")).status_code == 403
    client.logout()
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(reverse("mitglieder:liste")).status_code == 403


def test_migration_behaelt_genutzte_beitraege(erika):
    import importlib

    from django.apps import apps

    schritt = importlib.import_module("apps.mitglieder.migrations.0002_beitraege_einstellbar")
    schritt.bisherige_beitraege_behalten(apps, None)
    assert not MitgliederEinstellungen.mit_beitraegen()
    mitglied(erika)  # Jahresbeitrag 36
    schritt.bisherige_beitraege_behalten(apps, None)
    assert MitgliederEinstellungen.mit_beitraegen()


def test_mitgliedschaft_direkt_bei_der_adresse(admin_client, benutzer_mit_rolle, anmelden, client):
    """Adresse bearbeiten mit Abschnitt „Vereinsmitgliedschaft“; Querlinks in beide Richtungen."""
    seite = admin_client.get(reverse("mitglieder:neu")).content.decode()
    assert f'href="{reverse("adressen:neu")}?mitglied=1"' in seite
    formular = admin_client.get(reverse("adressen:neu"), {"mitglied": "1"}).content.decode()
    assert 'name="ist_mitglied" value="1" checked' in formular and 'name="m-nummer"' in formular
    # Ohne Häkchen: nur die Adresse, Mitgliedsfelder werden nicht geprüft
    admin_client.post(reverse("adressen:neu"), {"art": "person", "nachname": "Nur",
                                                "m-nummer": ""})  # fmt: skip
    assert not Mitglied.objects.exists()
    # Mit Häkchen, aber fehlender Art: nichts gespeichert, Fehler am Feld
    fehlt = admin_client.post(reverse("adressen:neu"), {"art": "person", "nachname": "Probe",
                                                        "ist_mitglied": "1", "m-nummer": "77",
                                                        "m-eintritt": "2026-01-01"})  # fmt: skip
    assert fehlt.status_code == 200 and not Adresse.objects.filter(nachname="Probe").exists()
    daten = {"art": "person", "nachname": "Probe", "ist_mitglied": "1", "m-nummer": "77",
             "m-art": "Fördermitglied", "m-eintritt": "2026-01-01"}  # fmt: skip
    antwort = admin_client.post(reverse("adressen:neu"), daten)
    a = Adresse.objects.get(nachname="Probe")
    m = Mitglied.objects.get(adresse=a)
    assert antwort.url == reverse("adressen:adresse", args=[a.pk])
    assert (m.nummer, m.art, m.eintritt) == ("77", "Fördermitglied", dt.date(2026, 1, 1))
    assert MitgliederEinstellungen.laden().naechste_nummer == 78
    # Bearbeiten: Mitgliedsangaben stehen dabei und lassen sich ändern
    url = reverse("adressen:bearbeiten", args=[a.pk])
    seite = admin_client.get(url).content.decode()
    assert 'name="ist_mitglied" value="1">' in seite and "Mitglied Nr. 77" in seite
    admin_client.post(url, {**daten, "m-art": "Ehrenmitglied", "m-austritt": "2026-06-30",
                            "m-austrittsgrund": ""})  # fmt: skip
    assert Mitglied.objects.get(pk=m.pk).art == "Fördermitglied"  # Grund fehlt: nicht gespeichert
    admin_client.post(url, {**daten, "m-art": "Ehrenmitglied"})
    assert Mitglied.objects.get(pk=m.pk).art == "Ehrenmitglied" and Mitglied.objects.count() == 1
    # Querlinks: Adressbuch zeigt das Mitglied, Mitgliederliste führt ins Adressbuch
    liste = admin_client.get(reverse("adressen:liste")).content.decode()
    assert f'href="{reverse("mitglieder:mitglied", args=[m.pk])}"' in liste
    assert reverse("mitglieder:liste") in liste
    mitglieder = admin_client.get(reverse("mitglieder:liste")).content.decode()
    assert reverse("adressen:liste") in mitglieder
    # Ohne Recht „Mitglieder bearbeiten“: kein Abschnitt, Häkchen wirkt nicht
    anmelden(client, benutzer_mit_rolle("bea", rollen.BUERO))
    from apps.konten.models import Rolle

    r = Rolle.objects.get(gruppe__name=rollen.BUERO)
    r.rechte = [x for x in r.rechte if x != "mitglieder.bearbeiten"]
    r.save()
    assert "Vereinsmitgliedschaft" not in client.get(reverse("adressen:neu")).content.decode()
    client.post(reverse("adressen:neu"), {"art": "person", "nachname": "Ohne", **{
        k: v for k, v in daten.items() if k.startswith("m-") or k == "ist_mitglied"}})  # fmt: skip
    assert not Mitglied.objects.filter(adresse__nachname="Ohne").exists()


def test_liste_sortiert_nummern_wie_zahlen(admin_client):
    for nr in ("10", "2", "1"):
        a = Adresse.objects.create(nachname=f"Probe{nr}x", vorname="Erfunden")
        Mitglied.objects.create(adresse=a, nummer=nr, art="Fördermitglied",
                                eintritt=dt.date(2020, 1, 1))  # fmt: skip
    seite = admin_client.get(reverse("mitglieder:liste")).content.decode()
    assert seite.index("Probe1x") < seite.index("Probe2x") < seite.index("Probe10x")
