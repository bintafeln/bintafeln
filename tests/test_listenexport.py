"""Listen als PDF herunterladen und per E-Mail senden (ADR 0096)."""

import pytest
from django.contrib.auth import get_user_model
from django.core import mail as django_mail
from django.urls import reverse

from apps.adressen.models import Adresse
from apps.core import geheimnis, listenexport
from apps.core.models import MailEinstellungen

pytestmark = pytest.mark.django_db

CSV = "﻿Name;Ort\r\nErika Beispiel;Musterstadt\r\n"


def _mailserver():
    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()


def test_pdf_aus_csv_ist_pdf():
    assert listenexport.pdf_aus_csv("Testliste", CSV)[:4] == b"%PDF"


def test_liste_als_pdf(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "pdf"})
    assert antwort.status_code == 200
    assert antwort["Content-Type"] == "application/pdf" and antwort.content[:4] == b"%PDF"


def test_liste_als_csv_unveraendert(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "csv"})
    assert "text/csv" in antwort["Content-Type"] and b"Beispiel" in antwort.content


def test_liste_per_mail_mit_pdf_und_csv(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    _mailserver()
    antwort = admin_client.get(
        reverse("adressen:liste"),
        {"aktion": "mail", "email": "buero@example.org", "weiter": reverse("adressen:liste")},
    )
    assert antwort.status_code == 302
    assert len(django_mail.outbox) == 1
    gesendet = django_mail.outbox[0]
    assert gesendet.to == ["buero@example.org"]
    namen = [anhang[0] for anhang in gesendet.attachments]
    assert len(namen) == 2
    assert any(n.endswith(".pdf") for n in namen) and any(n.endswith(".csv") for n in namen)


def test_mail_ohne_adresse_sendet_nicht(admin_client):
    Adresse.objects.create(nachname="Beispiel", ort="Musterstadt")
    _mailserver()
    antwort = admin_client.get(reverse("adressen:liste"), {"aktion": "mail", "email": ""})
    assert antwort.status_code == 302 and not django_mail.outbox


def test_pdf_laesst_ausgeblendete_spalten_weg(pdf_text):
    """Das PDF zeigt nur die Spalten, die nicht ausgeblendet sind; ohne Angabe alle."""
    from django.http import HttpResponse

    def text(*ohne):
        return pdf_text(
            HttpResponse(
                listenexport.pdf_aus_csv("Testliste", CSV, *ohne), content_type="application/pdf"
            )
        )

    alles = text()
    assert "Erika Beispiel" in alles and "Musterstadt" in alles
    ohne = text({"Ort"})
    assert "Erika Beispiel" in ohne and "Musterstadt" not in ohne and "Ort" not in ohne
    # blendet jemand alles aus, kommt lieber die ganze Liste als ein leeres Blatt
    assert "Musterstadt" in text({"Name", "Ort"})


def _pdf_woerter(pdf_text, antwort) -> str:
    """Der Text eines Listen-PDFs ohne Leerzeichen und Umbrüche: Schmale Spalten brechen Wörter
    mitten im Wort um, deshalb alle Textstücke aneinanderhängen."""
    import re

    return "".join(re.findall(r"\(((?:[^()\\]|\\.)*)\) Tj", pdf_text(antwort))).replace(" ", "")


def test_spaltenauswahl_gilt_im_pdf_jeder_liste(admin_client, admin, pdf_text, benutzer_mit_rolle):
    """In jeder Liste mit Spaltenauswahl folgt das PDF der eigenen Auswahl; die CSV-Datei behält
    alle Spalten."""
    from apps.konten import rollen
    from apps.kunden.models import Haushalt, Person
    from apps.mitglieder.models import Mitglied
    from apps.spenden.models import Spende

    # Team-Liste: Benutzername ausgeblendet
    benutzer_mit_rolle("erna.eifrig", rollen.AUSGABE)
    admin.listen_spalten_aus = {"mitarbeitende": ["benutzername", "rollen"],
                                "adressen": ["ort"], "mitglieder": ["art"],
                                "spenden": ["bezeichnung"]}  # fmt: skip
    admin.kundenliste_aus = ["nachname"]
    admin.antraege_liste_aus = ["email"]
    admin.save()
    url = reverse("konten:ehrenamtliche")
    text = _pdf_woerter(pdf_text, admin_client.get(url, {"aktion": "pdf"}))
    assert "Nachname" in text and "erna.eifrig" not in text and "Benutzername" not in text
    assert "Rollen" not in text and "Zwei-Faktor" in text  # sichtbare Spalte ist jetzt im Export
    csv_text = admin_client.get(url, {"aktion": "csv"}).content.decode("utf-8-sig")
    assert "Benutzername" in csv_text and "erna.eifrig" in csv_text  # CSV bleibt vollständig

    # Adressbuch: Ort ausgeblendet
    a = Adresse.objects.create(art="person", vorname="Otto", nachname="Ortlos", ort="Musterstadt",
                               strasse="Beispielweg 3")  # fmt: skip
    text = _pdf_woerter(pdf_text, admin_client.get(reverse("adressen:liste"), {"aktion": "pdf"}))
    assert "Ortlos" in text and "Beispielweg3" in text and "Musterstadt" not in text

    # Mitglieder: Art ausgeblendet
    Mitglied.objects.create(adresse=a, nummer="7", art="Fördermitglied", eintritt="2024-01-01")
    text = _pdf_woerter(pdf_text, admin_client.get(reverse("mitglieder:liste"), {"aktion": "pdf"}))
    assert "Ortlos" in text and "Fördermitglied" not in text

    # Spenden: Bezeichnung/Zweck ausgeblendet
    import datetime as dt

    Spende.objects.create(adresse=a, datum=dt.date.today(), art="geld", betrag=25,
                          beschreibung="Kollekte", zweck="Jugendarbeit")  # fmt: skip
    text = _pdf_woerter(pdf_text, admin_client.get(reverse("spenden:liste"), {"aktion": "pdf"}))
    assert "Ortlos" in text and "Kollekte" not in text and "Jugendarbeit" not in text

    # Kundenliste: Nachname ausgeblendet
    h = Haushalt.objects.create(kundennummer="00042")
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Geheimname")
    text = _pdf_woerter(
        pdf_text, admin_client.get(reverse("kunden:exportieren"), {"aktion": "pdf"})
    )
    assert "00042" in text and "Erika" in text and "Geheimname" not in text

    # Anträge: E-Mail ausgeblendet
    from apps.antraege.models import Antrag

    Antrag.objects.create(vorname="Anna", nachname="Antrag", email="anna@example.org")
    text = _pdf_woerter(pdf_text, admin_client.get(reverse("antraege:export"), {"aktion": "pdf"}))
    assert "Antrag" in text and "anna@example.org" not in text


def test_warteliste_spalten_passen_zum_export():
    """Die Spaltenauswahl der Warteliste trifft im PDF nur, wenn die Überschriften der Liste auch
    die des Exports sind."""
    from apps.core import listen
    from apps.warteliste import views

    assert {titel for _, titel in views.SPALTEN} <= set(views.EXPORT_KOPF)

    class Person:
        listen_spalten_aus = {"warteliste": ["wohnort", "termin"]}

    assert listen.pdf_ohne(Person(), "warteliste", dict(views.SPALTEN)) == {"Wohnort", "Termin"}


def test_adressfelder_als_spalten_in_mitglieder_und_spenden(
    admin_client, admin, pdf_text, client, anmelden, benutzer_mit_rolle, recht_geben
):
    """Mitglieder- und Spendenliste bieten die Adressfelder als Spalten an: in der Vorgabe
    ausgeblendet, je Person einschaltbar, im PDF genau die eingeblendeten – und nur für Konten,
    die das Adressbuch sehen dürfen."""
    import datetime as dt

    from apps.konten import rollen
    from apps.mitglieder.models import Mitglied
    from apps.spenden.models import Spende

    a = Adresse.objects.create(art="person", vorname="Berta", nachname="Beispiel",
                               strasse="Musterweg 5", plz="12345", ort="Musterstadt",
                               telefon="0000-111", email="berta@example.org")  # fmt: skip
    Mitglied.objects.create(adresse=a, nummer="7", art="Mitglied", eintritt="2024-01-01")
    Spende.objects.create(adresse=a, datum=dt.date.today(), art="geld", betrag=25)
    # früher gespeicherte Wahl ohne die neuen Spalten: sie bleiben trotzdem ausgeblendet
    admin.listen_spalten_aus = {"mitglieder": ["art"]}
    admin.save()

    for liste in ("mitglieder", "spenden"):
        url = reverse(f"{liste}:liste")
        seite = admin_client.get(url).content.decode()
        assert 'value="strasse"' in seite and 'value="strasse" checked' not in seite, liste
        assert "Musterweg 5" not in seite
        text = _pdf_woerter(pdf_text, admin_client.get(url, {"aktion": "pdf"}))
        assert "Beispiel" in text and "Musterweg5" not in text and "0000-111" not in text, liste

        vorgabe = ["name", "eintritt"] if liste == "mitglieder" else ["spender", "betrag"]
        admin_client.post(reverse(f"{liste}:spalten"),
                          {"spalte": [*vorgabe, "strasse", "telefon"]})  # fmt: skip
        admin.refresh_from_db()
        seite = admin_client.get(url).content.decode()
        assert 'value="strasse" checked' in seite and 'value="ort" checked' not in seite
        assert "Musterweg 5" in seite and "0000-111" in seite and "Musterstadt" not in seite
        text = _pdf_woerter(pdf_text, admin_client.get(url, {"aktion": "pdf"}))
        assert "Musterweg5" in text and "0000-111" in text and "Musterstadt" not in text, liste
        # die CSV behält alle Spalten
        csv_text = admin_client.get(url, {"aktion": "csv"}).content.decode("utf-8-sig")
        assert "Straße" in csv_text and "Musterstadt" in csv_text and "Telefon" in csv_text
        # nach einem Adressfeld sortieren
        assert admin_client.get(url, {"sort": "-strasse"}).status_code == 200
        assert admin_client.get(url, {"sort": "geburtsdatum"}).status_code == 200

    # ohne Recht aufs Adressbuch: keine Adressspalten, auch nicht in der CSV
    ohne = benutzer_mit_rolle("nur.spenden", rollen.AUSGABE)
    recht_geben(rollen.AUSGABE, "spenden.sehen", "mitglieder.sehen")
    anmelden(client, ohne)
    for liste in ("mitglieder", "spenden"):
        url = reverse(f"{liste}:liste")
        assert 'value="strasse"' not in client.get(url).content.decode()
        client.post(reverse(f"{liste}:spalten"), {"spalte": ["strasse", "telefon"]})
        assert "Musterweg 5" not in client.get(url).content.decode()
        assert "Telefon" not in client.get(url, {"aktion": "csv"}).content.decode("utf-8-sig")


def test_listen_merken_filter_und_suche(admin_client, admin, benutzer_mit_rolle):
    """Wer aus einer Liste einen Eintrag öffnet und über „Zurück“ oder das Menü wiederkommt,
    findet Filter, Suche und Sortierung wie verlassen – bis „Zurücksetzen“."""
    from apps.core.models import TafelEinstellungen
    from apps.konten import rollen

    tafel = TafelEinstellungen.laden()
    tafel.module = ["tickets"]
    tafel.save()
    benutzer_mit_rolle("erna.eifrig", rollen.AUSGABE)
    faelle = [
        (reverse("adressen:liste"), "adressen", {"q": "Muster", "art": "person", "sort": "ort"},
         "sort=ort"),
        (reverse("mitglieder:liste"), "mitglieder", {"stand": "", "q": "Muster", "sort": "-name"},
         "sort=-name"),
        (reverse("spenden:liste"), "spenden", {"art": "geld", "q": "Muster", "sort": "betrag"},
         "sort=betrag"),
        (reverse("antraege:liste"), "antraege", {"ansicht": "alle", "suche": "Muster"},
         "ansicht=alle"),
        (reverse("konten:ehrenamtliche"), "team-ehrenamtliche", {"q": "erna", "sort": "ort"}, ""),
        (reverse("tickets:liste"), "tickets", {"status": "erledigt", "kategorie": ""}, ""),
    ]  # fmt: skip
    for url, liste, filter_, bleibt in faelle:
        assert admin_client.get(url).status_code == 200, liste  # noch nichts gemerkt
        seite = admin_client.get(url, filter_)
        assert seite.status_code == 200, liste
        assert "filter=zuruecksetzen" in seite.content.decode(), liste
        zurueck = admin_client.get(url)  # „Zurück“ oder Menü: ohne Angaben
        assert zurueck.status_code == 302, liste
        for name, wert in filter_.items():
            assert f"{name}={wert}" in zurueck.url, (liste, name)
        # die Suche beim Tippen (htmx) wird nie umgeleitet
        assert admin_client.get(url, HTTP_HX_REQUEST="true").status_code == 200, liste
        # „Zurücksetzen“ vergisst die Filter; was der Knopf behält (Sortierung), bleibt
        behalten = dict(p.split("=") for p in bleibt.split("&") if p)
        antwort = admin_client.get(url, {**behalten, "filter": "zuruecksetzen"})
        assert antwort.url == (f"{url}?{bleibt}" if bleibt else url), liste
        admin.refresh_from_db()
        assert admin.listen_filter.get(liste, "") == bleibt, liste
    # eine andere Person hat ihre eigenen Filter
    andere = get_user_model().objects.get(username="erna.eifrig")
    assert "adressen" not in (andere.listen_filter or {})


def test_kategorie_filter_in_team_mitglieder_spenden(admin_client, admin, benutzer_mit_rolle):
    """Team-, Mitglieder- und Spendenliste lassen sich wie das Adressbuch nach der Kategorie der
    Adresse filtern; der Filter gilt auch im Export und wird gemerkt."""
    import datetime as dt

    from apps.adressen.models import AdressKategorie
    from apps.konten import rollen, verwaltung
    from apps.mitglieder.models import Mitglied
    from apps.spenden.models import Spende

    presse = AdressKategorie.objects.get_or_create(name="Presse")[0]
    drin = Adresse.objects.create(art="person", vorname="Paula", nachname="Passend")
    draussen = Adresse.objects.create(art="person", vorname="Olaf", nachname="Ohne")
    drin.kategorien.add(presse)
    for i, a in enumerate((drin, draussen)):
        verwaltung.konto_fuer_adresse(admin, a, [rollen.FAHRER])
        Mitglied.objects.create(adresse=a, nummer=str(70 + i), art="Mitglied",
                                eintritt="2024-01-01")  # fmt: skip
        Spende.objects.create(adresse=a, datum=dt.date.today(), art="geld", betrag=10 + i)

    behoerde = AdressKategorie.objects.get_or_create(name="Behörde")[0]
    dritte = Adresse.objects.create(art="person", vorname="Berta", nachname="Behoerdlich")
    dritte.kategorien.add(behoerde, presse)  # trägt beide: darf nicht doppelt erscheinen
    verwaltung.konto_fuer_adresse(admin, dritte, [rollen.FAHRER])
    Mitglied.objects.create(adresse=dritte, nummer="79", art="Mitglied", eintritt="2024-01-01")
    Spende.objects.create(adresse=dritte, datum=dt.date.today(), art="geld", betrag=99)

    for name in ("konten:ehrenamtliche", "mitglieder:liste", "spenden:liste", "adressen:liste"):
        url = reverse(name)
        alle = admin_client.get(url).content.decode()
        assert "Passend" in alle and "Ohne" in alle, name
        # Mehrfachauswahl mit Häkchen statt einfachem Auswahlfeld
        assert "data-mehrfach" in alle and 'type="checkbox" name="kategorie"' in alle, name
        seite = admin_client.get(url, {"kategorie": presse.pk}).content.decode()
        assert "Passend" in seite and ">Ohne<" not in seite, name
        assert f'name="kategorie" value="{presse.pk}"' in seite, name
        # zwei Kategorien: alle mit einer davon, jede Zeile nur einmal
        beide = admin_client.get(url, {"kategorie": [presse.pk, behoerde.pk]}).content.decode()
        assert "Passend" in beide and ">Ohne<" not in beide, name
        assert beide.count("Behoerdlich</a>") == 1, name
        nur = admin_client.get(url, {"kategorie": [behoerde.pk]}).content.decode()
        assert "Behoerdlich" in nur and "Passend" not in nur, name
        csv_text = admin_client.get(url, {"kategorie": presse.pk, "aktion": "csv"})
        csv_text = csv_text.content.decode("utf-8-sig")
        assert "Passend" in csv_text and "Ohne" not in csv_text, name
        # gemerkt: ohne Angaben zurück zur gefilterten Liste; Unsinn im Filter zeigt alle
        assert f"kategorie={presse.pk}" in admin_client.get(url).url, name
        assert "Ohne" in admin_client.get(url, {"kategorie": "x"}).content.decode(), name


def test_spalten_reihenfolge_je_person(admin_client, admin, pdf_text):
    """Unter „Spalten wählen“ lässt sich die Reihenfolge der Spalten festlegen: Sie gilt in der
    Liste und im PDF, je Person, bis „Reihenfolge zurücksetzen“."""
    import datetime as dt
    import re

    from django.http import HttpResponse

    from apps.core import listen
    from apps.konten import rollen, verwaltung
    from apps.mitglieder.models import Mitglied
    from apps.spenden.models import Spende

    def koepfe(url):
        seite = admin_client.get(url, follow=True).content.decode()
        assert "<!--s:" not in seite  # die Marken der Vorlage fallen immer weg
        kopf = seite[seite.index("<thead>") : seite.index("</thead>")]
        zellen = re.findall(r"<th\b.*?</th>", kopf, re.S)
        return [re.sub(r"<[^>]+>|[↕▲▼]", "", t).strip() for t in zellen]

    a = Adresse.objects.create(art="person", vorname="Rita", nachname="Reihe", ort="Musterstadt",
                               plz="12345", telefon="0123 4")  # fmt: skip
    verwaltung.konto_fuer_adresse(admin, a, [rollen.FAHRER])
    verwaltung.stammdaten_aus_adresse(a)
    Mitglied.objects.create(adresse=a, nummer="7", art="Mitglied", eintritt="2024-01-01")
    Spende.objects.create(adresse=a, datum=dt.date.today(), art="geld", betrag=25)

    faelle = [  # Liste, Speichern, sichtbare Spalten, gewünschte Folge, erwartete Köpfe vorn
        ("konten:ehrenamtliche", "konten:mitarbeitende_spalten", ["ort", "vorname", "telefon"],
         ["ort", "nachname", "telefon", "vorname"], ["Ort", "Nachname", "Telefon", "Vorname"]),
        ("adressen:liste", "adressen:spalten", ["ort", "vorname", "telefon"],
         ["telefon", "ort", "name", "vorname"], ["Telefon", "Ort", "Nachname", "Vorname"]),
        ("mitglieder:liste", "mitglieder:spalten", ["name", "art", "eintritt"],
         ["eintritt", "name", "nummer", "art"], ["Eintritt", "Name", "Nr.", "Art"]),
        ("spenden:liste", "spenden:spalten", ["spender", "betrag", "art"],
         ["betrag", "art", "datum", "spender"],
         ["Betrag/Wert", "Art", "Datum", "Nachname / Organisation", "Vorname"]),
    ]  # fmt: skip
    for liste, speichern, sichtbar, folge, erwartet in faelle:
        url = reverse(liste)
        vorher = koepfe(url)
        seite = admin_client.get(url, follow=True).content.decode()
        assert "data-spalten-folge" in seite and 'name="folge"' in seite, liste
        assert "Reihenfolge zurücksetzen" not in seite, liste
        admin_client.post(reverse(speichern), {"spalte": sichtbar, "folge": folge},
                          HTTP_REFERER=url)  # fmt: skip
        nachher = koepfe(url)
        assert nachher[0] == "", liste  # das Auswahlkästchen bleibt vorn
        assert nachher[1 : 1 + len(erwartet)] == erwartet, (liste, nachher)
        # die Zeilen folgen derselben Ordnung wie der Kopf
        seite = admin_client.get(url, follow=True).content.decode()
        zeile = seite[seite.index("<tbody>") :]
        zeile = zeile[: zeile.index("</tr>")]
        titel = re.findall(r'<td[^>]*data-titel="([^"]+)"', zeile)
        assert titel[: len(erwartet)] == erwartet, (liste, titel)
        assert "Reihenfolge zurücksetzen" in seite, liste
        # das Menü zeigt die Spalten in der neuen Folge
        menue = re.findall(r'name="folge" value="([a-z_]+)"', seite)
        assert menue[: len(folge)] == folge, liste
        # PDF in derselben Reihenfolge
        pdf = admin_client.get(url, {"aktion": "pdf"})
        assert pdf["Content-Type"] == "application/pdf", liste
        # zurücksetzen: wieder wie die Vorlage
        admin_client.post(reverse(speichern), {"spalte": sichtbar, "folge_zuruecksetzen": "1",
                                               "folge": folge}, HTTP_REFERER=url)  # fmt: skip
        admin.refresh_from_db()
        assert not any(k.endswith(":folge") for k in admin.listen_spalten_aus), liste
        zurueck = koepfe(url)
        assert [k for k in zurueck if k in vorher] == [k for k in vorher if k in zurueck], liste

    # PDF: Spalten in der gewählten Reihenfolge, der Rest dahinter; ohne Angabe wie die CSV
    csv_text = "Nummer;Nachname;Ort\r\n1;Reihe;Musterstadt\r\n"

    def als_pdf(**angaben):
        daten = listenexport.pdf_aus_csv("T", csv_text, **angaben)
        return pdf_text(HttpResponse(daten, content_type="application/pdf"))

    text = als_pdf(reihenfolge=["Ort"])
    assert text.index("Ort") < text.index("Nummer") < text.index("Nachname")
    text = als_pdf()
    assert text.index("Nummer") < text.index("Nachname") < text.index("Ort")
    # die reine Funktion: Vorspann bleibt, Unbekanntes hinten, ohne Folge nur Marken weg
    html = "<tr><td>x</td><!--s:a--><td>A</td><!--s:b--><td>B</td><!--s:_z--><td>Z</td></tr>"
    geordnet = "<tr><td>x</td><td>B</td><td>A</td><td>Z</td></tr>"
    assert listen.spalten_ordnen(html, ["b", "a"]) == geordnet
    assert listen.spalten_ordnen(html, None) == "<tr><td>x</td><td>A</td><td>B</td><td>Z</td></tr>"


def test_leerspalten_im_pdf(admin_client, pdf_text, rf):
    """Ein oder zwei leere Spalten rechts im PDF (zum Eintragen oder Unterschreiben), mit oder
    ohne Überschrift; die CSV-Datei bleibt unverändert."""
    from django.http import HttpResponse

    # Angaben aus der Adresse: höchstens zwei, Überschriften mit Komma, Unsinn zählt als keine
    def gelesen(**angaben):
        return listenexport.leerspalten(rf.get("/", angaben))

    assert gelesen() == [] and gelesen(leer="0") == [] and gelesen(leer="x") == []
    assert gelesen(leer="1") == [""]
    assert gelesen(leer="2", leer_titel="Unterschrift, Anmerkung") == ["Unterschrift", "Anmerkung"]
    assert gelesen(leer="2", leer_titel="Unterschrift") == ["Unterschrift", ""]
    assert gelesen(leer="9", leer_titel="a,b,c") == ["a", "b"]
    assert gelesen(leer="1", leer_titel="a,b") == ["a"]
    # Breiten: jede Leerspalte ein Fünftel, der Rest nach Länge des Inhalts, zusammen das Blatt
    kopf, zeilen, breiten = listenexport.mit_leerspalten(
        ["Nr", "Name"], [["1", "Erika Beispiel aus Musterstadt"]], ["Unterschrift", ""]
    )
    assert kopf == ["Nr", "Name", "Unterschrift", ""] and zeilen[0][:2] == [
        "1",
        "Erika Beispiel aus Musterstadt",
    ]
    assert len(zeilen[0]) == 4 and not any(isinstance(z, str) for z in zeilen[0][2:])
    assert breiten[2:] == [0.2, 0.2] and breiten[0] < breiten[1]
    assert abs(sum(breiten) - 1) < 1e-9
    assert listenexport.mit_leerspalten(["Nr"], [["1"]], []) == (["Nr"], [["1"]], None)
    text = pdf_text(
        HttpResponse(
            listenexport.pdf_aus_csv("Testliste", CSV, leer=["Unterschrift"]),
            content_type="application/pdf",
        )
    )
    assert "Erika Beispiel" in text and "Unterschrift" in text
    # eine leere Liste bleibt „Keine Einträge.“
    assert listenexport.pdf_aus_csv("T", "Name;Ort\r\n", leer=["x"])[:4] == b"%PDF"
    # über eine echte Liste: Felder stehen im Aufklapper, das PDF hat die Spalte, die CSV nicht
    Adresse.objects.create(art=Adresse.Art.PERSON, nachname="Beispiel", vorname="Erika")
    liste = reverse("adressen:liste")
    seite = admin_client.get(liste).content.decode()
    assert 'name="leer" form="auswahl"' in seite and 'name="leer_titel" form="auswahl"' in seite
    angaben = {"leer": "2", "leer_titel": "Unterschrift,Datum"}
    antwort = admin_client.get(liste, {"aktion": "pdf", **angaben})
    text = pdf_text(antwort)
    assert "Unterschrift" in text and "Datum" in text  # (das Adressbuch hat sehr viele Spalten)
    datei = admin_client.get(liste, {"aktion": "csv", **angaben}).content.decode()
    assert "Unterschrift" not in datei and "Beispiel" in datei
    # „Liste zusammenstellen“ (Mitarbeitende und Personen, auch Archiv) kann es ebenso
    druck = reverse("adressen:druckliste")
    assert 'name="leer"' in admin_client.get(druck).content.decode()
    text = pdf_text(admin_client.get(druck, {"aktion": "pdf", **angaben}))
    assert "Unterschrift" in text and "Datum" in text and "Beispiel" in text
    assert "Unterschrift" not in pdf_text(admin_client.get(druck, {"aktion": "pdf"}))
