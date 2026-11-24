import datetime as dt

import pytest
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core.models import TafelEinstellungen
from apps.konten import geburtstage, rollen

pytestmark = pytest.mark.django_db

GEB = reverse("konten:geburtstage")
START = reverse("core:start")


def mitarbeiter(django_user_model, nachname, geb, *, aktiv=True, stelle=False):
    konto = django_user_model.objects.create_user(
        username=nachname.lower(), last_name=nachname, is_active=aktiv
    )
    if stelle:
        from apps.kunden.models import Ausgabestelle

        konto.stelle = Ausgabestelle.objects.create(name=f"Stelle {nachname}")
        konto.save()
    Adresse.objects.create(art=Adresse.Art.PERSON, nachname=nachname, konto=konto, geburtsdatum=geb)
    return konto


def test_naechste_nur_aktive_mitarbeitende(django_user_model):
    heute = dt.date(2026, 3, 10)
    mitarbeiter(django_user_model, "Bald", dt.date(1980, 3, 15))  # in 5 Tagen
    mitarbeiter(django_user_model, "Spaet", dt.date(1990, 4, 20))  # außerhalb 14 Tage
    mitarbeiter(django_user_model, "Gesperrt", dt.date(1970, 3, 12), aktiv=False)
    mitarbeiter(django_user_model, "Tablet", dt.date(1975, 3, 11), stelle=True)
    # Person im Adressbuch ohne Konto zählt nicht als Mitarbeiter
    Adresse.objects.create(
        art=Adresse.Art.PERSON, nachname="Spender", geburtsdatum=dt.date(1960, 3, 13)
    )

    naechste = geburtstage.naechste(14, heute)
    assert [g["name"] for g in naechste] == ["Bald"]
    assert naechste[0]["wird"] == 46 and naechste[0]["in_tagen"] == 5


def test_naechste_heute_und_jahreswechsel(django_user_model):
    heute = dt.date(2026, 12, 28)
    mitarbeiter(django_user_model, "Heute", dt.date(1990, 12, 28))
    mitarbeiter(django_user_model, "Neujahr", dt.date(2000, 1, 2))  # im nächsten Jahr, in 5 Tagen
    naechste = geburtstage.naechste(14, heute)
    namen = [g["name"] for g in naechste]
    assert namen == ["Heute", "Neujahr"]
    assert naechste[0]["ist_heute"] and naechste[1]["in_tagen"] == 5
    assert naechste[1]["wird"] == 27  # Geburtstag 2027


def test_schalttag_wird_in_normaljahr_am_28_februar(django_user_model):
    heute = dt.date(2026, 2, 20)  # 2026 ist kein Schaltjahr
    mitarbeiter(django_user_model, "Schalt", dt.date(2000, 2, 29))
    naechste = geburtstage.naechste(14, heute)
    assert naechste and naechste[0]["naechster"] == dt.date(2026, 2, 28)


def test_kalender_nach_monaten(django_user_model):
    heute = dt.date(2026, 5, 1)
    mitarbeiter(django_user_model, "Maerz", dt.date(1980, 3, 15))
    mitarbeiter(django_user_model, "MaerzFrueh", dt.date(1985, 3, 2))
    kal = geburtstage.kalender(heute)
    maerz = kal[2]
    assert maerz["name"] == "März"
    assert [e["name"] for e in maerz["eintraege"]] == ["MaerzFrueh", "Maerz"]  # nach Tag sortiert


def test_seite_braucht_recht(admin_client, client, anmelden, benutzer_mit_rolle, django_user_model):
    mitarbeiter(django_user_model, "Heute", _heute_geb())
    # Admin (alle Rechte) sieht die Seite samt Name
    inhalt = admin_client.get(GEB).content.decode()
    assert "Geburtstage des Teams" in inhalt and "Heute" in inhalt
    # Rolle ohne das Recht: kein Zugriff
    anmelden(client, benutzer_mit_rolle("aus", rollen.AUSGABE))
    assert client.get(GEB).status_code == 403


def test_startseite_kachel_nur_mit_einstellung(admin_client, django_user_model):
    mitarbeiter(django_user_model, "Heute", _heute_geb())
    # Vorgabe aus → keine Kachel
    assert "Nächste Geburtstage" not in admin_client.get(START).content.decode()
    t = TafelEinstellungen.laden()
    t.geburtstage_startseite = True
    t.save()
    inhalt = admin_client.get(START).content.decode()
    assert "Nächste Geburtstage" in inhalt and "Heute" in inhalt


def _heute_geb() -> dt.date:
    from django.utils import timezone

    heute = timezone.localdate()
    # ein Geburtstag „heute", aber in einem früheren Jahr (29.02. gibt es 1980)
    return dt.date(1980, heute.month, heute.day)


def test_letzte_sieben_tage(django_user_model, admin_client):
    heute = dt.date(2026, 1, 3)
    mitarbeiter(django_user_model, "Gestern", dt.date(1980, 1, 2))
    mitarbeiter(django_user_model, "Silvester", dt.date(1990, 12, 31))  # über den Jahreswechsel
    mitarbeiter(django_user_model, "Heute", dt.date(1985, 1, 3))  # heute zählt zu „nächste"
    mitarbeiter(django_user_model, "Zulange", dt.date(1970, 12, 20))  # 14 Tage her
    letzte = geburtstage.letzte(7, heute)
    assert [g["name"] for g in letzte] == ["Gestern", "Silvester"]
    assert letzte[0]["vor_tagen"] == 1 and letzte[0]["wurde"] == 46
    assert letzte[1]["vor_tagen"] == 3 and letzte[1]["wurde"] == 35


# --- Geburtstagsbrief auf der Startseite (ADR 0170) ---------------------------------------------

GESEHEN = reverse("konten:geburtstagsbrief_gesehen")


def _geb(tage_her=0, jahr=1980) -> dt.date:
    """Ein Geburtsdatum, dessen Geburtstag vor ``tage_her`` Tagen war (0 = heute)."""
    from django.utils import timezone

    tag = timezone.localdate() - dt.timedelta(days=tage_her)
    return dt.date(jahr, tag.month, tag.day)


def _person(django_user_model, vorname, nachname, geb, rolle=None):
    konto = mitarbeiter(django_user_model, nachname, geb)
    Adresse.objects.filter(konto=konto).update(vorname=vorname)
    if rolle:
        from django.contrib.auth.models import Group

        konto.groups.add(Group.objects.get(name=rolle))
    return konto


def test_eigener_brief_heute_und_danke(client, anmelden, django_user_model, admin):
    from django.utils import timezone

    from apps.konten.models import GeburtstagGruss

    heute = timezone.localdate()
    if (heute.month, heute.day) == (2, 29):
        pytest.skip("am Schalttag gibt es 1980 den 29.02., der Test rechnet mit festen Jahren")
    ich = _person(django_user_model, "Erika", "Probe", _geb(), "Ausgabe")
    _person(django_user_model, "Otto", "Kollege", _geb())  # hat auch heute, geht mich nichts an
    anmelden(client, ich)
    seite = client.get(START).content.decode()
    assert 'template class="geburtstagsbrief"' in seite and "js/geburtstagsbrief.js" in seite
    assert "Alles Gute zum Geburtstag, Erika!" in seite and "Nachträglich" not in seite
    assert "Kollege" not in seite and ">Danke!<" in seite and "wird " not in seite
    ich_adresse = Adresse.objects.get(konto=ich)
    assert f'value="{ich_adresse.pk}:{heute:%Y-%m-%d}"' in seite
    # nur POST; „Danke!“ merkt es, danach kommt der Brief nicht wieder
    assert client.get(GESEHEN).status_code == 405
    antwort = client.post(GESEHEN, {"gruss": f"{ich_adresse.pk}:{heute:%Y-%m-%d}"})
    assert antwort.url == START
    assert GeburtstagGruss.objects.get().benutzer == ich
    assert "geburtstagsbrief" not in client.get(START).content.decode()


def test_eigener_brief_gestern(client, anmelden, django_user_model, admin):
    ich = _person(django_user_model, "Erika", "Probe", _geb(1), "Ausgabe")
    anmelden(client, ich)
    seite = client.get(START).content.decode()
    assert "Nachträglich alles Gute zum Geburtstag, Erika!" in seite
    # vorgestern ist vorbei
    Adresse.objects.filter(konto=ich).update(geburtsdatum=_geb(2))
    assert "geburtstagsbrief" not in client.get(START).content.decode()


def test_brief_zu_allen_nur_mit_recht(client, anmelden, django_user_model, recht_geben, admin):
    from django.utils import timezone

    from apps.konten.models import GeburtstagGruss

    heute = timezone.localdate()
    _person(django_user_model, "Otto", "Heutig", _geb(0, 1976))
    _person(django_user_model, "Paula", "Gestrig", _geb(1, 1990))
    _person(django_user_model, "Karl", "Frueher", _geb(3))
    mitarbeiter(django_user_model, "Gesperrt", _geb(), aktiv=False)
    mitarbeiter(django_user_model, "Stellenkonto", _geb(), stelle=True)
    vorstand = _person(django_user_model, "Vera", "Vorstand", _geb(100), "Büro")
    anmelden(client, vorstand)
    # ohne das Recht: nichts
    assert "geburtstagsbrief" not in client.get(START).content.decode()
    assert geburtstage.brief(vorstand, heute) == []
    recht_geben("Büro", "mitarbeitende.geburtstagsbrief")
    seite = client.get(START).content.decode()
    assert "Geburtstag im Team" in seite and ">Gratuliert<" in seite
    assert f"Heute hat <strong>Otto Heutig</strong> Geburtstag (wird {heute.year - 1976})" in seite
    gestern = heute - dt.timedelta(days=1)
    assert (
        f"Gestern hatte <strong>Paula Gestrig</strong> Geburtstag (wurde {gestern.year - 1990})"
        in seite
    )
    assert seite.index("Otto Heutig") < seite.index("Paula Gestrig")  # heute vor gestern
    # vor drei Tagen, gesperrt, Konto einer Ausgabestelle: nicht dabei
    vorstand = django_user_model.objects.get(pk=vorstand.pk)  # Rechte frisch laden
    assert [e["name"] for e in geburtstage.brief(vorstand, heute)] == [
        "Otto Heutig",
        "Paula Gestrig",
    ]
    assert "Karl Frueher" not in seite
    # „Gratuliert“ nur für Otto: Paula bleibt stehen
    otto = Adresse.objects.get(nachname="Heutig")
    client.post(GESEHEN, {"gruss": [f"{otto.pk}:{heute:%Y-%m-%d}", "quatsch", "7:kein-datum"]})
    seite = client.get(START).content.decode()
    assert "Otto Heutig" not in seite and "Paula Gestrig" in seite
    # Fremdes lässt sich nicht merken: Karl steht mir nicht als Brief zu
    karl = Adresse.objects.get(nachname="Frueher")
    client.post(GESEHEN, {"gruss": f"{karl.pk}:{heute:%Y-%m-%d}"})
    assert GeburtstagGruss.objects.count() == 1
    # ein anderes Konto mit dem Recht sieht Otto weiter – gemerkt wird je Konto
    zweite = _person(django_user_model, "Zora", "Zweite", _geb(50), "Büro")
    assert [e["name"] for e in geburtstage.brief(zweite, heute)] == ["Otto Heutig", "Paula Gestrig"]


def test_eigener_und_andere_in_einem_brief(admin, admin_client, django_user_model):
    """Admin hat alle Rechte: eigener Glückwunsch vorn, die anderen darunter."""
    Adresse.objects.create(
        art=Adresse.Art.PERSON, vorname="Anna", nachname="Admin", konto=admin, geburtsdatum=_geb()
    )
    _person(django_user_model, "Otto", "Heutig", _geb())
    seite = admin_client.get(START).content.decode()
    assert "Alles Gute zum Geburtstag, Anna!" in seite and "Otto Heutig" in seite
    assert "Anna Admin</strong>" not in seite and "Danke – und gratuliert" in seite


def test_schalter_aus_und_frist(admin_client, django_user_model, admin):
    from django.utils import timezone

    from apps.konten.models import GeburtstagGruss

    _person(django_user_model, "Otto", "Heutig", _geb())
    assert "geburtstagsbrief" in admin_client.get(START).content.decode()
    t = TafelEinstellungen.laden()
    assert t.geburtstagsbrief  # Vorgabe an
    t.geburtstagsbrief = False
    t.save()
    assert "geburtstagsbrief" not in admin_client.get(START).content.decode()
    # Merker verschwinden nach 30 Tagen
    heute = timezone.localdate()
    otto = Adresse.objects.get(nachname="Heutig")
    for alt in (31, 30):
        GeburtstagGruss.objects.create(
            benutzer=admin, adresse=otto, tag=heute - dt.timedelta(days=alt)
        )
    assert geburtstage.fristen_anwenden(heute) == 1
    assert GeburtstagGruss.objects.get().tag == heute - dt.timedelta(days=30)


def test_schalttag_im_brief(django_user_model, admin):
    """29.02. wird in einem Jahr ohne Schalttag am 28.02. gefeiert – auch im Brief."""
    _person(django_user_model, "Lea", "Schalt", dt.date(1988, 2, 29))
    assert [e["gestern"] for e in geburtstage.brief(admin, dt.date(2026, 2, 28))] == [False]
    assert [e["gestern"] for e in geburtstage.brief(admin, dt.date(2026, 3, 1))] == [True]
    assert geburtstage.brief(admin, dt.date(2026, 3, 2)) == []
    assert [e["alter"] for e in geburtstage.brief(admin, dt.date(2028, 2, 29))] == [40]
    # Jahreswechsel: Silvester ist am 1.1. „gestern“
    _person(django_user_model, "Sil", "Vester", dt.date(1990, 12, 31))
    (eintrag,) = geburtstage.brief(admin, dt.date(2027, 1, 1))
    assert (eintrag["name"], eintrag["gestern"], eintrag["alter"]) == ("Sil Vester", True, 36)
