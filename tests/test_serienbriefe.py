"""Serienbriefe (ADR 0047). Alle Daten sind erfunden."""

import datetime as dt
from decimal import Decimal

import pytest
from django.core import mail as django_mail
from django.urls import reverse

from apps.adressen.models import Adresse, AdressKategorie
from apps.core.models import MailEinstellungen
from apps.konten import rollen
from apps.kunden.models import Haushalt, Person
from apps.mitglieder.models import Mitglied
from apps.serienbriefe import empfaenger as emp
from apps.serienbriefe.models import Versand, Vorlage
from apps.spenden.models import Spende

pytestmark = pytest.mark.django_db
URL = reverse("serienbriefe:erstellen")
JAHR = dt.date.today().year


@pytest.fixture
def daten():
    spender = AdressKategorie.objects.get(name="Spender")
    erika = Adresse.objects.create(art="person", anrede="Frau", vorname="Erika", nachname="Muster",
                                   strasse="Weg 1", plz="12345", ort="Musterstadt",
                                   email="erika@example.org", einwilligung_post=dt.date(2026, 1, 1),
                                   einwilligung_email=dt.date(2026, 1, 1))  # fmt: skip
    erika.kategorien.add(spender)
    baeckerei = Adresse.objects.create(
        organisation="Bäckerei Probe", strasse="Markt 2", plz="12345", ort="Musterstadt"
    )  # ohne Einwilligung
    baeckerei.kategorien.add(spender)
    Spende.objects.create(adresse=erika, datum=dt.date(JAHR, 2, 1), betrag=Decimal("150"))
    Spende.objects.create(adresse=baeckerei, datum=dt.date(JAHR, 3, 1), betrag=Decimal("20"))
    Mitglied.objects.create(adresse=baeckerei, nummer="7", art="Fördermitglied",
                            eintritt=dt.date(2020, 1, 1), jahresbeitrag=Decimal("60"))  # fmt: skip
    h = Haushalt.objects.create(kundennummer="1001", strasse="Kundenweg 3", plz="12345",
                                ort="Musterstadt")  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, anrede="Herr", vorname="Max",
                          nachname="Kunde")  # fmt: skip
    return erika, baeckerei


def test_anrede_und_platzhalter():
    assert emp.briefanrede("Frau", "Erika", "Muster", False) == "Sehr geehrte Frau Muster,"
    assert emp.briefanrede("Herr", "", "Probe", False) == "Sehr geehrter Herr Probe,"
    assert emp.briefanrede("", "Kim", "Test", False) == "Guten Tag Kim Test,"
    assert emp.briefanrede("", "", "", True) == "Sehr geehrte Damen und Herren,"
    # persönliche Anrede: Liebe/Lieber richtet sich nach der Anrede
    assert emp.anrede_du("Frau", "Erika", "Muster", False) == "Liebe Erika,"
    assert emp.anrede_du("Herr", " Max ", "Probe", False) == "Lieber Max,"
    assert emp.anrede_du("", "Kim", "Test", False) == "Hallo Kim,"  # Anrede unbekannt
    assert emp.anrede_du("Divers", "Kim", "Test", False) == "Hallo Kim,"
    assert emp.anrede_du("Herr", "", "Probe", False) == "Sehr geehrter Herr Probe,"  # kein Vorname
    assert emp.anrede_du("", "Erika", "", True) == "Sehr geehrte Damen und Herren,"
    e = emp.Empfaenger("a:1", "X", [], werte={"name": "Erika"})
    assert emp.einsetzen("Hallo {name}, {unbekannt} {", e, {"jahr": 2026}) == (
        "Hallo Erika, {unbekannt} {")  # fmt: skip


def test_quellen(daten, admin):
    erika, baeckerei = daten
    d = {"jahr": JAHR, "versandart": "brief", "nur_einwilligung": True,
         "kategorien": [AdressKategorie.objects.get(name="Spender")]}  # fmt: skip
    assert [e.name for e in emp.suchen("adressen", d)] == ["Erika Muster"]
    assert len(emp.suchen("adressen", d | {"nur_einwilligung": False})) == 2
    spender = emp.suchen("spender", d | {"mindestbetrag": Decimal("100")})
    assert [e.name for e in spender] == ["Erika Muster"]
    assert spender[0].werte["spendensumme"] == "150,00 €"
    mitglieder = emp.suchen("mitglieder", d | {"nur_offen": True})
    assert [e.werte["mitgliedsnummer"] for e in mitglieder] == ["7"]
    assert mitglieder[0].werte["beitrag_offen"] == "60,00 €"
    assert mitglieder[0].werte["anrede"] == "Sehr geehrte Damen und Herren,"
    kunden = emp.suchen("kunden", d, admin)
    assert kunden[0].werte["anrede"] == "Sehr geehrter Herr Kunde,"
    assert kunden[0].werte["anrede_du"].startswith("Lieber ")
    assert mitglieder[0].werte["anrede_du"] == "Sehr geehrte Damen und Herren,"
    assert ("anrede_du", "Liebe/Lieber + Vorname") in [(k, n) for k, n, _ in emp.karten()]
    assert kunden[0].anschrift == ["Herr Max Kunde", "Kundenweg 3", "12345 Musterstadt"]
    ok, ohne = emp.aufteilen(kunden, "email")
    assert not ok and ohne


def test_pdf_und_vermerk(admin_client, daten, pdf_text):
    vorlage = Vorlage.objects.get(name="Dank für Spenden")
    daten_form = {"vorlage": vorlage.pk, "quelle": "spender", "versandart": "brief",
                  "jahr": JAHR, "nur_einwilligung": "on"}  # fmt: skip
    vorschau = admin_client.post(URL, daten_form).content.decode()
    assert "</span> von 1 Empfängern" in vorschau and "Sehr geehrte Frau Muster," in vorschau
    assert "150,00 €" in vorschau and "PDF mit Briefen erzeugen" in vorschau
    antwort = admin_client.post(URL, daten_form | {"schritt": "pdf"})
    text = pdf_text(antwort)
    assert "Sehr geehrte Frau Muster," in text and "Weg 1" in text and "150,00" in text
    v = Versand.objects.get()
    assert (v.art, v.anzahl, v.empfaenger) == ("brief", 1, [f"a:{daten[0].pk}"])
    auskunft = pdf_text(admin_client.get(reverse("adressen:auskunft", args=[daten[0].pk])))
    assert "Serienbriefe" in auskunft and "Herzlichen Dank" in auskunft
    seite = admin_client.get(reverse("serienbriefe:vorlagen")).content.decode()
    assert "Spender eines Jahres" in seite


def test_email(admin_client, daten):
    m = MailEinstellungen.laden()
    m.server, m.absender = "smtp.example.org", "tafel@example.org"
    m.save()
    vorlage = Vorlage.objects.get(name="Dank für Spenden")
    form = {"vorlage": vorlage.pk, "quelle": "adressen", "versandart": "email", "jahr": JAHR,
            "nur_einwilligung": "on", "schritt": "senden"}  # fmt: skip
    antwort = admin_client.post(URL, form, follow=True)
    assert "1 E-Mail gesendet" in antwort.content.decode()
    assert len(django_mail.outbox) == 1 and django_mail.outbox[0].to == ["erika@example.org"]
    assert "Sehr geehrte Frau Muster," in django_mail.outbox[0].body
    assert Versand.objects.get().art == "email"


def test_vorlagen_pflegen(admin_client):
    neu = reverse("serienbriefe:vorlage_neu")
    assert "{spendensumme}" in admin_client.get(neu).content.decode()
    admin_client.post(neu, {"name": "Test", "betreff": "Hallo", "text": "{anrede}\n\nText"})
    v = Vorlage.objects.get(name="Test")
    admin_client.post(reverse("serienbriefe:vorlage_loeschen", args=[v.pk]))
    assert not Vorlage.objects.filter(name="Test").exists()


def test_rechte(client, admin, benutzer_mit_rolle, anmelden, daten):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    seite = client.get(URL).content.decode()
    assert "Spender eines Jahres" in seite and "Kunden (Haushalte)" not in seite
    client.logout()
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(URL).status_code == 403


# --- Ehrenamtliche, einzelne Empfänger abhaken, Einwilligungs-Haken merken ----------------------


def _helfer(django_user_model, vorname, nachname, *, aktiv=True, art="ehrenamtlich"):
    konto = django_user_model.objects.create_user(
        username=nachname.lower(), is_active=aktiv, beschaeftigung=art
    )
    return Adresse.objects.create(art="person", vorname=vorname, nachname=nachname, konto=konto,
                                  strasse="Weg 5", plz="12345", ort="Musterstadt",
                                  email=f"{nachname.lower()}@example.org")  # fmt: skip


def test_ehrenamtliche_und_ehemalige_als_empfaenger(daten, admin, django_user_model):
    from apps.konten.verwaltung import EHEMALIGE_KATEGORIE

    _helfer(django_user_model, "Anna", "Aktiv")
    _helfer(django_user_model, "Fritz", "Fest", art="fest")
    _helfer(django_user_model, "Gerd", "Gesperrt", aktiv=False)
    gewesen = _helfer(django_user_model, "Eva", "Ehemals")
    ehemalige, _ = AdressKategorie.objects.get_or_create(name=EHEMALIGE_KATEGORIE)
    gewesen.kategorien.add(ehemalige)
    # ohne Konto, aber als ehemalig geführt
    otto = Adresse.objects.create(art="person", vorname="Otto", nachname="Ohnekonto",
                                  strasse="Weg 6", plz="12345", ort="Musterstadt")  # fmt: skip
    otto.kategorien.add(ehemalige)
    d = {"jahr": JAHR, "versandart": "brief", "nur_einwilligung": True}
    assert [e.name for e in emp.suchen("ehrenamtliche", d)] == ["Anna Aktiv"]
    assert [e.name for e in emp.suchen("ehemalige", d)] == [
        "Eva Ehemals", "Gerd Gesperrt", "Otto Ohnekonto",
    ]  # fmt: skip
    assert dict(emp.QUELLEN)["ehrenamtliche"] == "Ehrenamtliche"
    # Angestellte als eigener Kreis; gesperrte Konten zählen nicht
    _helfer(django_user_model, "Greta", "Gegangen", art="fest", aktiv=False)
    assert [e.name for e in emp.suchen("angestellte", d)] == ["Fritz Fest"]
    assert dict(emp.QUELLEN)["angestellte"] == "Angestellte"


def test_einzelne_empfaenger_abhaken(admin_client, daten, pdf_text):
    erika, baeckerei = daten
    vorlage = Vorlage.objects.get(name="Dank für Spenden")
    form = {"vorlage": vorlage.pk, "quelle": "spender", "versandart": "brief", "jahr": JAHR}
    antwort = admin_client.post(URL, form)
    seite = antwort.content.decode()
    # beide stehen angehakt in der Liste
    assert seite.count('name="an"') == 2 and seite.count(" checked>") >= 2
    assert "</span> von 2 Empfängern" in seite
    kennung = antwort.context["auswahl_fuer"]
    nur_erika = form | {"auswahl_fuer": kennung, "an": [f"a:{erika.pk}"]}
    vorschau = admin_client.post(URL, nur_erika)
    angehakt = {e.name: an for e, an in vorschau.context["liste"]}
    assert angehakt == {"Erika Muster": True, "Bäckerei Probe": False}
    text = pdf_text(admin_client.post(URL, nur_erika | {"schritt": "pdf"}))
    assert "Frau Muster" in text and "Bäckerei" not in text
    assert Versand.objects.get().empfaenger == [f"a:{erika.pk}"]
    # niemand angehakt: nichts wird erzeugt
    keiner = admin_client.post(URL, form | {"auswahl_fuer": kennung, "schritt": "pdf"})
    assert "mindestens einen Empfänger" in keiner.content.decode()
    assert Versand.objects.count() == 1
    # andere Auswahl darüber: das alte Abhaken gilt nicht mehr, alle sind wieder angehakt
    anders = admin_client.post(URL, nur_erika | {"mindestbetrag": "10"})
    assert all(an for _, an in anders.context["liste"])


def test_liste_aus_dem_adressbuch_als_empfaenger(
    admin_client, client, anmelden, benutzer_mit_rolle, daten, django_user_model, pdf_text
):
    """„Liste zusammenstellen“ im Adressbuch → „Serienbrief an diese Personen“: genau die
    Angehakten sind die Empfänger. Die Liste liegt nur in der Sitzung."""
    anna = _helfer(django_user_model, "Anna", "Aktiv")
    fritz = _helfer(django_user_model, "Fritz", "Fest", art="fest")
    _helfer(django_user_model, "Gerd", "Gesperrt")
    druckliste = reverse("adressen:druckliste")
    vorlage = Vorlage.objects.get(name="Dank für Spenden")
    # ohne mitgebrachte Liste steht der Empfängerkreis nicht zur Wahl
    assert "Zusammengestellte Liste" not in admin_client.get(URL).content.decode()
    assert 'value="serienbrief"' in admin_client.get(druckliste).content.decode()
    antwort = admin_client.get(druckliste, {"aktion": "serienbrief", "id": [anna.pk, fritz.pk]})
    assert antwort.status_code == 302 and antwort.url == URL + "?liste=1"
    seite = admin_client.get(antwort.url).content.decode()
    assert "Zusammengestellte Liste aus dem Adressbuch (2 Adressen)" in seite
    assert '<option value="liste" selected>' in seite
    form = {"vorlage": vorlage.pk, "quelle": "liste", "versandart": "brief", "jahr": JAHR}
    vorschau = admin_client.post(URL, form)
    assert [e.name for e, _ in vorschau.context["liste"]] == ["Anna Aktiv", "Fritz Fest"]
    text = pdf_text(admin_client.post(URL, form | {"schritt": "pdf"}))
    assert "Anna Aktiv" in text and "Fritz Fest" in text and "Gesperrt" not in text
    assert Versand.objects.get().auswahl == "Zusammengestellte Liste aus dem Adressbuch"
    # „Nur mit Einwilligung“ gilt auch hier, wenn der Haken sitzt
    mit = admin_client.post(URL, form | {"nur_einwilligung": "on"})
    assert mit.context["liste"] == []
    # ohne Haken: die ganze gefilterte Liste
    admin_client.get(druckliste, {"aktion": "serienbrief", "suche": "Gesperrt"})
    assert [e.name for e, _ in admin_client.post(URL, form).context["liste"]] == ["Gerd Gesperrt"]
    # nichts gefunden: zurück zur Liste, die alte Auswahl bleibt
    leer = admin_client.get(druckliste, {"aktion": "serienbrief", "suche": "gibtesnicht"})
    assert leer.status_code == 302 and leer.url.startswith(druckliste)
    assert "aktion" not in leer.url
    # eine andere Sitzung hat die Liste nicht; eine gebaute Anfrage findet ohne sie niemanden
    anmelden(client, benutzer_mit_rolle("zweite", rollen.ADMIN))
    assert "Zusammengestellte Liste" not in client.get(URL).content.decode()
    assert "Bitte eine gültige Auswahl" in client.post(URL, form).content.decode()
    # ohne das Recht für Serienbriefe: kein Knopf, kein Weg
    anmelden(client, benutzer_mit_rolle("nurlesen", rollen.AUSGABE))
    recht_seite = client.get(druckliste)
    if recht_seite.status_code == 200:
        assert 'value="serienbrief"' not in recht_seite.content.decode()
    assert client.get(druckliste, {"aktion": "serienbrief"}).status_code == 403


def test_einwilligungs_haken_wird_gemerkt(admin, admin_client, daten):
    vorlage = Vorlage.objects.get(name="Dank für Spenden")
    assert admin_client.get(URL).context["form"]["nur_einwilligung"].value() is True
    form = {"vorlage": vorlage.pk, "quelle": "adressen", "versandart": "brief", "jahr": JAHR}
    admin_client.post(URL, form)  # Haken abgewählt
    assert admin_client.get(URL).context["form"]["nur_einwilligung"].value() is False
    # bei Empfängern ohne diesen Haken (Mitglieder) ändert sich nichts am Gemerkten
    admin_client.post(URL, form | {"quelle": "mitglieder", "nur_einwilligung": "on"})
    assert admin_client.get(URL).context["form"]["nur_einwilligung"].value() is False
    admin_client.post(URL, form | {"nur_einwilligung": "on"})  # wieder angehakt
    assert admin_client.get(URL).context["form"]["nur_einwilligung"].value() is True
