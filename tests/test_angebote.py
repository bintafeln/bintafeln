"""Angebote mit Anmeldung (ADR 0131), z. B. ein Kochkurs. Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.http import HttpResponse
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.angebote import ablauf
from apps.angebote.models import Angebot, Interesse
from apps.core.models import TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Haushalt, Person

pytestmark = pytest.mark.django_db

HX = {"HTTP_HX_REQUEST": "true"}
HEUTE = dt.date(2026, 3, 10)
S = Interesse.Stand


@pytest.fixture(autouse=True)
def modul_an():
    t = TafelEinstellungen.laden()
    t.module = ["angebote"]
    t.save()


def haushalt(nummer, *vornamen, telefon="0123 456"):
    h = Haushalt.objects.create(kundennummer=nummer, telefon=telefon)
    for nr, vorname in enumerate(vornamen or ("Erika",)):
        Person.objects.create(
            haushalt=h,
            ist_hauptperson=nr == 0,
            vorname=vorname,
            nachname=f"Probe{nummer}",
            geburtsdatum=dt.date(1980, 1, 1 + nr),
        )
    return h


@pytest.fixture
def h():
    return haushalt("4711", "Erika", "Max")


def kurs(heute=None, **mehr):
    heute = heute or timezone.localdate()
    daten = {"bezeichnung": "Kochkurs Frühjahr", "plaetze": 2, "hoechstens": 3,
             "anmeldung_von": heute - dt.timedelta(days=3),
             "anmeldung_bis": heute + dt.timedelta(days=3), **mehr}  # fmt: skip
    return Angebot.objects.create(**daten)


def ein(a, h, vorname=None, heute=HEUTE, **mehr):
    personen = list(h.personen.order_by("pk"))
    person = next(p for p in personen if vorname in (None, p.vorname))
    return ablauf.eintragen(a, h, person, von="anton", heute=heute, **mehr)


def test_eintragen_bis_die_liste_voll_ist(h):
    a = kurs(HEUTE)
    e = ein(a, h, "Erika")
    assert (e.kundennummer, e.name, e.telefon, e.stand) == ("4711", "Erika Probe4711", "0123 456",
                                                            S.INTERESSIERT)  # fmt: skip
    assert str(e) == "Erika Probe4711 (Kochkurs Frühjahr)" and str(a) == "Kochkurs Frühjahr"
    with pytest.raises(ablauf.AngebotFehler, match="schon eingetragen"):
        ein(a, h, "Erika")
    ein(a, h, "Max")  # jede Person des Haushalts zählt einzeln
    assert ablauf.anzahl(a) == 2 and ablauf.offen(a, HEUTE)
    ein(a, haushalt("4712"))
    # Höchstzahl erreicht: die Liste schließt von selbst
    assert ablauf.anzahl(a) == 3 and not ablauf.offen(a, HEUTE) and ablauf.laeuft(a, HEUTE)
    with pytest.raises(ablauf.AngebotFehler, match="ist voll"):
        ein(a, haushalt("4713"))
    # eine Absage macht den Platz auf der Liste wieder frei
    Interesse.objects.filter(vorname="Max").update(stand=S.ABGESAGT)
    assert ablauf.offen(a, HEUTE) and ablauf.zahlen(a)["frei"] == 1


def test_eintragen_nur_im_zeitraum_offen_und_eigene_person(h):
    a = kurs(HEUTE)
    with pytest.raises(ablauf.AngebotFehler, match="keine Anmeldung"):
        ein(a, h, heute=HEUTE + dt.timedelta(days=10))
    a.geschlossen = True
    a.save()
    with pytest.raises(ablauf.AngebotFehler, match="geschlossen"):
        ein(a, h)
    a.geschlossen = False
    a.save()
    fremd = haushalt("4799").personen.get()
    with pytest.raises(ablauf.AngebotFehler, match="gehört nicht zu diesem Haushalt"):
        ablauf.eintragen(a, h, fremd, heute=HEUTE)
    assert not Interesse.objects.exists()


def test_plaetze_nach_reihenfolge_vergeben():
    a = kurs(HEUTE, plaetze=2, hoechstens=5)
    for nr in range(4):
        e = ein(a, haushalt(f"50{nr}"))
        Interesse.objects.filter(pk=e.pk).update(
            eingetragen_am=timezone.now() + dt.timedelta(minutes=nr))  # fmt: skip
    Interesse.objects.filter(kundennummer="500").update(stand=S.ABGESAGT)
    assert ablauf.plaetze_vergeben(a) == (2, 1)
    staende = dict(Interesse.objects.values_list("kundennummer", "stand"))
    assert staende == {"500": S.ABGESAGT, "501": S.ZUGESAGT, "502": S.ZUGESAGT,
                       "503": S.NACHRUECKER}  # fmt: skip
    z = ablauf.zahlen(a)
    assert (z["anzahl"], z["zugesagt"], z["nachruecker"], z["abgesagt"], z["frei"]) == (
        3, 2, 1, 1, 2)  # fmt: skip


def test_angebot_pruefen():
    a = kurs(HEUTE)
    a.full_clean()
    for feld, wert, text in [
        ("anmeldung_bis", HEUTE - dt.timedelta(days=30), "nicht vor"),
        ("hoechstens", 1, "Mindestens so viele"),
        ("plaetze", 0, "Mindestens ein Platz"),
        ("endet_am", HEUTE - dt.timedelta(days=30), "vor dem Beginn"),
    ]:
        b = kurs(HEUTE, **{feld: wert})
        with pytest.raises(Exception, match=text):
            b.full_clean()
    assert a.ende == a.anmeldung_bis
    a.endet_am = HEUTE + dt.timedelta(days=40)
    assert a.ende == a.endet_am


def test_fristen_loeschen_die_eintraege_nach_dem_ende(h):
    a = kurs(HEUTE, loeschen_nach_tagen=30)
    ein(a, h)
    ende = a.anmeldung_bis
    assert ablauf.fristen_anwenden(ende + dt.timedelta(days=30)) == 0
    assert ablauf.fristen_anwenden(ende + dt.timedelta(days=31)) == 1
    assert Angebot.objects.filter(pk=a.pk).exists() and not Interesse.objects.exists()
    # ein späteres Ende des Angebots verschiebt die Frist
    ein(a, h)
    a.endet_am = ende + dt.timedelta(days=60)
    a.save()
    assert ablauf.fristen_anwenden(ende + dt.timedelta(days=31)) == 0


def test_einlass_zeigt_stand_und_traegt_ein(client, admin, benutzer_mit_rolle, anmelden, h):
    a = kurs(beschreibung="4 Abende, dienstags 17 Uhr")
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    karte = client.get(reverse("ausgabe:empfang"), {"nummer": "4711"}, **HX).content.decode()
    assert "Kochkurs Frühjahr – 0 von 3 Interessierten" in karte
    assert "Interesse eintragen …" in karte and "4 Abende, dienstags 17 Uhr" in karte
    url = reverse("angebote:eintragen", args=[a.pk, "4711"])
    assert url in karte
    # der Knopf führt zur Auswahl der Person; die Hauptperson ist vorbelegt
    seite = client.post(url).content.decode()
    assert "Wer hat Interesse?" in seite and seite.count('name="person"') == 2
    assert seite.count(" checked") == 1 and "(Hauptperson)" in seite
    erika, max_ = h.personen.order_by("pk")
    antwort = client.post(url, {"person": [erika.pk, max_.pk]})
    assert antwort.status_code == 302 and "nummer=4711" in antwort.url
    assert sorted(Interesse.objects.values_list("vorname", flat=True)) == ["Erika", "Max"]
    assert Interesse.objects.first().eingetragen_von == "anton"
    karte = client.get(reverse("ausgabe:empfang"), {"nummer": "4711"}, **HX).content.decode()
    assert "2 von 3 Interessierten. Eingetragen: Erika Probe4711, Max Probe4711" in karte
    assert "Eintrag ändern …" in karte
    # schon eingetragen: austragen (in den Papierkorb), dann zurück zum Einlass
    seite = client.get(url).content.decode()
    assert "Schon eingetragen" in seite and "Alle Personen dieses Haushalts" in seite
    eintrag = Interesse.objects.get(vorname="Max")
    antwort = client.post(reverse("angebote:austragen", args=[eintrag.pk]))
    assert antwort.status_code == 302 and Interesse.objects.count() == 1
    # Liste voll: der Einlass fragt nicht weiter
    ein(a, haushalt("4712"), heute=timezone.localdate())
    ein(a, haushalt("4713"), heute=timezone.localdate())
    karte = client.get(reverse("ausgabe:empfang"), {"nummer": "4712"}, **HX).content.decode()
    assert "3 von 3 Interessierten" in karte and "Liste voll" in karte
    neu = haushalt("4720")
    karte = client.get(reverse("ausgabe:empfang"), {"nummer": "4720"}, **HX).content.decode()
    assert "Liste voll" in karte and reverse("angebote:eintragen", args=[a.pk, "4720"]) not in karte
    seite = client.get(reverse("angebote:eintragen", args=[a.pk, "4720"])).content.decode()
    assert "Es kann niemand mehr eingetragen werden" in seite
    person = neu.personen.get()
    antwort = client.post(reverse("angebote:eintragen", args=[a.pk, "4720"]),
                          {"person": [person.pk]}, follow=True)  # fmt: skip
    assert not Interesse.objects.filter(kundennummer="4720").exists()
    # von Hand geschlossen und außerhalb des Zeitraums
    a.geschlossen = True
    a.save()
    karte = client.get(reverse("ausgabe:empfang"), {"nummer": "4720"}, **HX).content.decode()
    assert "Anmeldung geschlossen" in karte
    Angebot.objects.update(anmeldung_bis=timezone.localdate() - dt.timedelta(days=1))
    karte = client.get(reverse("ausgabe:empfang"), {"nummer": "4720"}, **HX).content.decode()
    assert "Kochkurs" not in karte


def test_verwalten_liste_plaetze_und_ausgabe(admin_client, h, pdf_text):
    assert "Noch kein Angebot" in admin_client.get(reverse("angebote:liste")).content.decode()
    heute = timezone.localdate()
    daten = {"bezeichnung": "Kochkurs Frühjahr", "beschreibung": "4 Abende",
             "anmeldung_von": f"{heute:%d.%m.%Y}",
             "anmeldung_bis": f"{heute + dt.timedelta(days=14):%d.%m.%Y}",
             "plaetze": 1, "hoechstens": 3, "loeschen_nach_tagen": 90}  # fmt: skip
    seite = admin_client.get(reverse("angebote:neu")).content.decode()
    assert 'value="12"' in seite and 'value="20"' in seite  # Vorgaben
    falsch = admin_client.post(reverse("angebote:neu"), daten | {"hoechstens": 0})
    assert "Mindestens so viele" in falsch.content.decode()
    antwort = admin_client.post(reverse("angebote:neu"), daten)
    a = Angebot.objects.get()
    assert antwort.url == reverse("angebote:angebot", args=[a.pk])
    assert "Noch niemand eingetragen" in admin_client.get(antwort.url).content.decode()
    ein(a, h, "Erika", heute=heute)
    ein(a, h, "Max", heute=heute)
    seite = admin_client.get(antwort.url).content.decode()
    assert "2 von 3" in seite and "0123 456" in seite and "data-sortierbar" in seite
    liste = admin_client.get(reverse("angebote:liste")).content.decode()
    assert "Anmeldung läuft" in liste and "2 von 3" in liste
    # Plätze vergeben, einen Stand von Hand ändern
    admin_client.post(reverse("angebote:plaetze", args=[a.pk]))
    assert list(Interesse.objects.values_list("stand", flat=True)) == [S.ZUGESAGT, S.NACHRUECKER]
    zweiter = Interesse.objects.get(vorname="Max")
    admin_client.post(reverse("angebote:stand", args=[zweiter.pk]), {"stand": "abgesagt"})
    admin_client.post(reverse("angebote:stand", args=[zweiter.pk]), {"stand": "gibt es nicht"})
    zweiter.refresh_from_db()
    assert zweiter.stand == S.ABGESAGT
    # schließen und wieder öffnen
    admin_client.post(reverse("angebote:schliessen", args=[a.pk]), {"geschlossen": "1"})
    assert Angebot.objects.get().geschlossen
    assert "von Hand geschlossen" in admin_client.get(antwort.url).content.decode()
    admin_client.post(reverse("angebote:schliessen", args=[a.pk]), {"geschlossen": "0"})
    assert not Angebot.objects.get().geschlossen
    # bearbeiten, PDF und CSV
    admin_client.post(reverse("angebote:bearbeiten", args=[a.pk]), daten | {"plaetze": 2})
    assert Angebot.objects.get().plaetze == 2
    text = pdf_text(admin_client.get(reverse("angebote:liste_pdf", args=[a.pk])))
    assert "Kochkurs Frühjahr" in text and "Probe4711" in text and "4 Abende" in text
    csv = admin_client.get(reverse("angebote:liste_csv", args=[a.pk])).content.decode("utf-8-sig")
    assert csv.splitlines()[0].startswith("Nr.;Kundennr.;Nachname;Vorname;Telefon")
    assert "1;4711;Probe4711;Erika;0123 456" in csv
    # löschen legt das Angebot samt Einträgen in den Papierkorb
    admin_client.post(reverse("angebote:loeschen", args=[a.pk]))
    assert not Angebot.objects.exists() and not Interesse.objects.exists()


def test_rechte_und_modul(admin, benutzer_mit_rolle, anmelden, client, h):
    a = kurs()
    e = ein(a, h, heute=timezone.localdate())
    ausgabe = anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    # der Einlass trägt ein, sieht aber die Liste mit Telefonnummern nicht
    assert ausgabe.get(reverse("angebote:eintragen", args=[a.pk, "4711"])).status_code == 200
    for name, args in [("liste", []), ("angebot", [a.pk]), ("liste_pdf", [a.pk]),
                       ("liste_csv", [a.pk]), ("neu", [])]:  # fmt: skip
        assert ausgabe.get(reverse(f"angebote:{name}", args=args)).status_code == 403
    assert (
        ausgabe.post(reverse("angebote:stand", args=[e.pk]), {"stand": "abgesagt"}).status_code
        == 403
    )
    assert reverse("angebote:liste") not in ausgabe.get(reverse("core:start")).content.decode()
    buero = anmelden(Client(), benutzer_mit_rolle("berta", rollen.BUERO))
    assert reverse("angebote:liste") in buero.get(reverse("core:start")).content.decode()
    assert "Kochkurs" in buero.get(reverse("angebote:liste")).content.decode()
    assert "Angebote mit Anmeldung" in buero.get(reverse("core:hilfe")).content.decode()
    # Modul aus: Seiten gesperrt, am Einlass kein Hinweis
    t = TafelEinstellungen.laden()
    t.module = []
    t.save()
    assert buero.get(reverse("angebote:liste")).status_code in (403, 404)
    karte = ausgabe.get(reverse("ausgabe:empfang"), {"nummer": "4711"}, **HX).content.decode()
    assert "Kochkurs" not in karte


def test_auskunft_nennt_die_eintraege(admin_client, h, pdf_text):
    from apps.kunden import auskunft

    def text():
        return pdf_text(HttpResponse(auskunft.kunde_pdf(h), "application/pdf"))

    assert "Angebote mit Anmeldung" not in text()
    ein(kurs(HEUTE), h, "Erika")
    inhalt = text()
    assert "Angebote mit Anmeldung" in inhalt and "Kochkurs Frühjahr" in inhalt
