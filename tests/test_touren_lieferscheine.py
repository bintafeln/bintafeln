"""Modul Touren: Lieferscheine mit Unterschrift, PDF und Mail an die Station (ADR 0149).
Alle Daten sind erfunden."""

import base64
import datetime as dt
import io
from decimal import Decimal

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.core import privatdateien
from apps.core.models import MailEinstellungen, PapierkorbEintrag, TafelEinstellungen
from apps.touren import ablauf, lieferscheine
from apps.touren.models import Lieferschein, Station, Tour, TourenEinstellungen, Warengruppe

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def eingerichtet():
    t = TafelEinstellungen.laden()
    t.module, t.name = ["touren"], "Tafel Musterstadt"
    t.save()
    e = MailEinstellungen.laden()
    e.server, e.absender = "smtp.example.org", "tafel@example.org"
    e.save()
    versand("an")


def unterschrift(leer=False) -> str:
    bild = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
    if not leer:
        ImageDraw.Draw(bild).line([(20, 90), (120, 30), (280, 80)], fill=(17, 17, 17, 255), width=3)
    puffer = io.BytesIO()
    bild.save(puffer, "PNG")
    return "data:image/png;base64," + base64.b64encode(puffer.getvalue()).decode()


def versand(wert, test_email=""):
    e = TourenEinstellungen.laden()
    e.versand, e.test_email = wert, test_email
    e.save()


def station(**mehr):
    daten = {"kennung": "M-1", "art": "markt", "name": "Beispielmarkt Mitte",
             "strasse": "Musterstraße", "hausnummer": "1", "plz": "12345", "ort": "Musterstadt",
             "email": "markt@example.org", **mehr}  # fmt: skip
    return Station.objects.create(**daten)


def gruppe(name):
    return Warengruppe.objects.get(name=name)


def eingaben(**mehr):
    obst, brot = gruppe("Obst/Gemüse").pk, gruppe("Backwaren").pk
    return {
        f"menge_{obst}": "12", f"menge_{brot}": "3,5", f"einheit_{brot}": "kg",
        "anmerkung": "Zwei Kisten beschädigt", "unterschrift": unterschrift(), **mehr,
    }  # fmt: skip


# --- Regeln ------------------------------------------------------------------------------------


def test_warengruppen_als_vorgabe():
    namen = [g.name for g in lieferscheine.warengruppen()]
    assert namen[0] == "Obst/Gemüse" and namen[-1] == "Sonstiges" and len(namen) == 7


def test_positionen_lesen():
    zeilen = lieferscheine.positionen_lesen(eingaben())
    assert zeilen == [
        ("Obst/Gemüse", Decimal("12.0"), "kisten"),
        ("Backwaren", Decimal("3.5"), "kg"),
    ]
    for falsch in ({f"menge_{gruppe('Backwaren').pk}": "viel"}, {},
                   {f"menge_{gruppe('Backwaren').pk}": "-2"},
                   {f"menge_{gruppe('Backwaren').pk}": "0"}):  # fmt: skip
        with pytest.raises(lieferscheine.LieferscheinFehler):
            lieferscheine.positionen_lesen(falsch)


def test_unterschrift_lesen():
    assert lieferscheine.unterschrift_lesen(unterschrift()).startswith(b"\x89PNG")
    for falsch in ("", unterschrift(leer=True), "data:image/png;base64,###",
                   "data:image/png;base64," + base64.b64encode(b"kein Bild").decode(),
                   "data:text/html;base64,PGI+"):  # fmt: skip
        with pytest.raises(lieferscheine.LieferscheinFehler):
            lieferscheine.unterschrift_lesen(falsch)


def test_erstellen_und_senden(admin, pdf_text):
    s = station(email_lieferschein="ls@example.org")
    tour = Tour.objects.create(name="Tour 1")
    e = TourenEinstellungen.laden()
    e.naechste_nummer = 41
    e.save()
    bild = lieferscheine.unterschrift_lesen(unterschrift())
    zeilen = lieferscheine.positionen_lesen(eingaben())
    ls = lieferscheine.erstellen(s, admin, zeilen, bild, "Hinweis", tour)
    assert ls.nummer == 41 and TourenEinstellungen.laden().naechste_nummer == 42
    assert ls.station_name == "Beispielmarkt Mitte" and ls.tour_name == "Tour 1"
    assert [p.menge_text for p in ls.positionen.all()] == ["12 Kisten", "3,5 kg"]
    inhalt = lieferscheine.pdf(ls)
    assert inhalt.startswith(b"%PDF")
    # verschlüsselt abgelegt
    assert b"%PDF" not in privatdateien.pfad(Lieferschein.ORDNER, ls.datei).read_bytes()
    assert lieferscheine.senden(ls)
    m = mail.outbox[0]
    assert m.to == ["ls@example.org"] and "Lieferschein Nr. 41" in m.subject
    # der Text, wie ihn die Märkte kennen: Tafel und Station sind eingesetzt
    assert m.body.startswith(
        "Guten Tag!\n\nHiermit erhalten Sie den Digitalen Lieferschein der Tafel Musterstadt "
        "für folgenden Markt: Beispielmarkt Mitte.\n\nViele Grüße\nIhre Tafel Musterstadt\n"
    )
    assert "Sie erhalten diese Nachricht, weil Ihre E-Mail-Adresse bei uns" in m.body
    assert "Lieferscheine für Beispielmarkt Mitte eingetragen ist" in m.body
    assert "Datenschutz" not in m.body  # keine Domain, keine Erklärung hinterlegt: kein Link
    html = m.alternatives[0][0]
    assert "<h2>Guten Tag!</h2>" in html and "Viele Grüße<br>Ihre Tafel Musterstadt" in html
    assert "<hr>" in html and "eco" not in html.lower()
    assert m.attachments[0][0] == f"Lieferschein-41-{ls.datum:%Y-%m-%d}.pdf"
    ls.refresh_from_db()
    assert ls.gesendet_an == "ls@example.org" and ls.gesendet_am and not ls.mail_fehler


def test_pdf_inhalt(admin, pdf_text, client, anmelden):
    s = station()
    ls = lieferscheine.erstellen(s, admin, [("Obst/Gemüse", Decimal("12"), "kisten")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    anmelden(client, admin)
    text = pdf_text(client.get(reverse("touren:lieferschein_pdf", args=[ls.pk])))
    # Aussehen des bekannten Vordrucks: Spender, Empfänger, Datum, Nummer, Tabelle
    assert "Lieferschein" in text and "Verordnung (EG) Nr. 178/2002" in text
    assert "Spender/in:" in text and "Beispielmarkt Mitte" in text
    assert "Empfänger/in:" in text and "Tafel Musterstadt" in text
    assert "Nr:" in text and f"{ls.datum:%d.%m.%Y}" in text
    assert "Produktbezeichnung" in text and "12 Kisten" in text
    assert "Molkereiprodukte" in text  # jede Warengruppe hat ihre Zeile, auch ohne Menge
    assert "Unterschrift Empfänger/in" in text
    assert "Erstellt am" not in text and "Seite 1" not in text  # keine Fußzeile


def test_pdf_mit_logo_und_anmerkung(admin, settings, tmp_path):
    """Oben steht das Logo der Tafel; lässt es sich nicht lesen, ersatzweise ihr Name."""
    from django.core.files.uploadedfile import SimpleUploadedFile
    from pypdf import PdfReader

    settings.MEDIA_ROOT = tmp_path
    puffer = io.BytesIO()
    Image.new("RGBA", (300, 100), (0, 90, 160, 255)).save(puffer, format="PNG")
    t = TafelEinstellungen.laden()
    t.logo = SimpleUploadedFile("logo.png", puffer.getvalue(), content_type="image/png")
    t.save()
    zeichnung = lieferscheine.unterschrift_lesen(unterschrift())
    ls = lieferscheine.erstellen(station(), admin, [("Backwaren", Decimal("2"), "kisten")],
                                 zeichnung, anmerkung="Brot von gestern")  # fmt: skip
    seite = PdfReader(io.BytesIO(lieferscheine.pdf(ls))).pages[0]
    assert len(seite.images) == 2  # Logo und Unterschrift
    assert "Bemerkungen: Brot von gestern" in " ".join(seite.extract_text().split())
    t.logo = "oeffentlich/logo/fehlt.png"
    t.save()
    ls = lieferscheine.erstellen(station(kennung="zwei"), admin,
                                 [("Backwaren", Decimal("2"), "kisten")], zeichnung)  # fmt: skip
    seite = PdfReader(io.BytesIO(lieferscheine.pdf(ls))).pages[0]
    assert len(seite.images) == 1 and "Tafel Musterstadt" in seite.extract_text()


def test_pdf_viele_und_abgeschaltete_warengruppen(admin):
    """Viele Warengruppen passen auf eine Seite; eine Menge zu einer Gruppe, die es nicht (mehr)
    gibt, steht trotzdem darauf."""
    from pypdf import PdfReader

    for nr in range(25):
        Warengruppe.objects.create(name=f"Gruppe {nr}", reihenfolge=100 + nr)
    ls = lieferscheine.erstellen(station(), admin, [("Blumen", Decimal("3"), "kisten")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    leser = PdfReader(io.BytesIO(lieferscheine.pdf(ls)))
    text = leser.pages[0].extract_text()
    assert len(leser.pages) == 1 and "Gruppe 24" in text and "Blumen" in text


def test_ohne_mail_gespeichert_aber_nicht_verschickt(admin):
    s = station(email="")
    ls = lieferscheine.erstellen(s, admin, [("Backwaren", Decimal("1"), "kg")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    assert not lieferscheine.senden(ls)
    assert "keine E-Mail" in ls.mail_fehler and not mail.outbox and ls.gesendet_am is None


def test_frist_loescht_samt_pdf(admin):
    s = station()
    alt = lieferscheine.erstellen(s, admin, [("Backwaren", Decimal("1"), "kg")],
                                  lieferscheine.unterschrift_lesen(unterschrift()),
                                  datum=dt.date(2016, 11, 1))  # fmt: skip
    neu = lieferscheine.erstellen(s, admin, [("Backwaren", Decimal("1"), "kg")],
                                  lieferscheine.unterschrift_lesen(unterschrift()),
                                  datum=dt.date(2016, 12, 1))  # fmt: skip
    datei = privatdateien.pfad(Lieferschein.ORDNER, alt.datei)
    assert lieferscheine.fristen_anwenden(dt.date(2026, 11, 21)) == 1
    assert not datei.exists() and list(Lieferschein.objects.all()) == [neu]


# --- Seiten ------------------------------------------------------------------------------------


@pytest.fixture
def buero(client, admin, benutzer_mit_rolle, anmelden):
    return anmelden(client, benutzer_mit_rolle("bernd", "Büro"))


@pytest.fixture
def fahrer(client, admin, django_user_model, benutzer_mit_rolle, anmelden):
    konto = benutzer_mit_rolle("fritz", "Fahrer")
    konto.first_name, konto.last_name = "Fritz", "Probe"
    konto.save()
    return anmelden(client, konto)


def _auf_die_tour(tour, benutzername="fritz"):
    """Trägt das Konto als Fahrer der Tour ein (Lieferscheine gibt es nur auf der eigenen)."""
    from apps.adressen.models import Adresse
    from apps.konten.models import Benutzer

    konto = Benutzer.objects.get(username=benutzername)
    person = Adresse.objects.filter(konto=konto).first() or Adresse.objects.create(
        art=Adresse.Art.PERSON, vorname="Fritz", nachname="Probe", konto=konto
    )
    tour.fahrer = person
    tour.save()
    tour.personen.add(person)
    return person


def test_fahrer_fuellt_unterwegs_aus(fahrer):
    s = station()
    tour = Tour.objects.create(name="Tour 1")
    ablauf.halt_anhaengen(tour, s)
    heute = timezone.localdate()
    # auf einer fremden Tour: kein Lieferschein zu sehen oder auszufüllen (ADR 0156)
    fremd = fahrer.get(reverse("touren:fahren", args=[tour.pk])).content.decode()
    assert "Lieferschein ausfüllen" not in fremd
    _auf_die_tour(tour)
    seite = fahrer.get(reverse("touren:fahren", args=[tour.pk])).content.decode()
    ziel = reverse("touren:lieferschein", args=[s.pk])
    assert "Lieferschein ausfüllen" in seite and ziel in seite
    formular = fahrer.get(ziel, {"tour": tour.pk, "tag": f"{heute}"}).content.decode()
    assert "Obst/Gemüse" in formular and "unterschrift_feld.js" in formular
    antwort = fahrer.post(ziel, eingaben(tour=tour.pk, tag=f"{heute}"))
    assert antwort.url == f"{reverse('touren:fahren', args=[tour.pk])}?tag={heute}"
    ls = Lieferschein.objects.get()
    assert ls.unterschrieben_von == "Fritz Probe" and ls.tour == tour and ls.datum == heute
    assert ls.anmerkung == "Zwei Kisten beschädigt" and mail.outbox[0].to == ["markt@example.org"]
    seite = fahrer.get(reverse("touren:fahren", args=[tour.pk])).content.decode()
    assert f"Lieferschein Nr. {ls.nummer}" in seite and "Lieferschein ausfüllen" not in seite
    # das eigene PDF ja, die Liste aller nicht
    assert fahrer.get(reverse("touren:lieferschein_pdf", args=[ls.pk])).status_code == 200
    assert fahrer.get(reverse("touren:lieferscheine")).status_code == 403
    assert fahrer.get(reverse("touren:einstellungen")).status_code == 403


def test_fremdes_pdf_nicht_fuer_fahrer(fahrer, admin):
    ls = lieferscheine.erstellen(station(), admin, [("Backwaren", Decimal("1"), "kg")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    assert fahrer.get(reverse("touren:lieferschein_pdf", args=[ls.pk])).status_code == 403
    assert fahrer.get(reverse("touren:lieferschein_pdf", args=[999999])).status_code == 403


def test_fehler_bleiben_im_formular(fahrer):
    s = station()
    ziel = reverse("touren:lieferschein", args=[s.pk])
    seite = fahrer.post(ziel, eingaben(unterschrift="")).content.decode()
    assert "Bitte im Feld unterschreiben" in seite and 'value="12"' in seite
    seite = fahrer.post(ziel, {"unterschrift": unterschrift()}).content.decode()
    assert "mindestens bei einer Warengruppe" in seite
    assert not Lieferschein.objects.exists()


def test_abgeschaltet_je_station_und_insgesamt(fahrer):
    aus = station(lieferschein=False)
    assert fahrer.get(reverse("touren:lieferschein", args=[aus.pk])).status_code == 404
    an = station(kennung="M-2", name="Zweiter")
    e = TourenEinstellungen.laden()
    e.lieferscheine = False
    e.save()
    assert fahrer.get(reverse("touren:lieferschein", args=[an.pk])).status_code == 404
    tour = Tour.objects.create(name="Tour 1")
    ablauf.halt_anhaengen(tour, an)
    seite = fahrer.get(reverse("touren:fahren", args=[tour.pk])).content.decode()
    assert "Lieferschein ausfüllen" not in seite


def test_buero_liste_nachsenden_loeschen(buero, admin):
    s = station(email="")
    ls = lieferscheine.erstellen(s, admin, [("Backwaren", Decimal("2"), "kisten")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    lieferscheine.senden(ls)
    seite = buero.get(reverse("touren:lieferscheine"), {"stand": "offen"}).content.decode()
    assert (
        "Beispielmarkt Mitte" in seite
        and "Backwaren: 2 Kisten" in seite
        and "keine E-Mail" in seite
    )
    s.email = "markt@example.org"
    s.save()
    buero.post(reverse("touren:lieferschein_senden", args=[ls.pk]))
    ls.refresh_from_db()
    assert ls.gesendet_an == "markt@example.org" and len(mail.outbox) == 1
    seite = buero.get(reverse("touren:lieferscheine"), {"stand": "offen"}).content.decode()
    assert "Keine Lieferscheine gefunden" in seite
    buero.post(reverse("touren:lieferschein_loeschen", args=[ls.pk]))
    assert not Lieferschein.objects.exists()
    assert PapierkorbEintrag.objects.filter(art="Lieferschein").exists()
    assert buero.get(reverse("touren:einstellungen")).status_code == 403  # nur Admin


def test_station_geloescht_lieferschein_bleibt(admin):
    s = station()
    ls = lieferscheine.erstellen(s, admin, [("Backwaren", Decimal("2"), "kisten")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    s.delete()
    ls.refresh_from_db()
    assert ls.station is None and ls.station_name == "Beispielmarkt Mitte"


def test_admin_stellt_ein(admin_client):
    """Der Admin entscheidet über Versand und Aufbewahrung; Warengruppen, Fahrzeuge, Zentrale
    und den Text der Mail richtet ein, wer Touren plant („Touren → Einrichten“)."""
    seite = admin_client.get(reverse("touren:einstellungen")).content.decode()
    assert "Mailversand, Karte und Aufbewahrung" in seite and "Warengruppen</h2>" not in seite
    assert reverse("touren:einrichten") in seite
    admin_client.post(reverse("touren:einstellungen"), {
        "versand": "aus", "aufbewahrung_jahre": "6"})  # fmt: skip
    e = TourenEinstellungen.laden()
    assert not e.lieferscheine and e.aufbewahrung_jahre == 6
    seite = admin_client.get(reverse("touren:einrichten")).content.decode()
    assert "Warengruppen" in seite and "Obst/Gemüse" in seite and "Fahrzeuge" in seite
    admin_client.post(reverse("touren:einrichten"), {
        "einrichten": "1", "mail_text": "Hallo", "zentrale": "Zentralweg 1",
        "kiste_kg": "10"})  # fmt: skip
    e = TourenEinstellungen.laden()
    assert e.mail_text == "Hallo" and e.zentrale == "Zentralweg 1"
    assert e.aufbewahrung_jahre == 6  # die Admin-Angaben bleiben unberührt
    gruppen = list(Warengruppe.objects.all())
    daten = {
        "warengruppen": "1",
        "wg-TOTAL_FORMS": len(gruppen) + 2,
        "wg-INITIAL_FORMS": len(gruppen),
        "wg-MIN_NUM_FORMS": 0,
        "wg-MAX_NUM_FORMS": 1000,
    }
    for nr, g in enumerate(gruppen):
        daten |= {
            f"wg-{nr}-id": g.pk,
            f"wg-{nr}-name": g.name,
            f"wg-{nr}-reihenfolge": g.reihenfolge,
        }  # ohne Häkchen: aus
    daten |= {f"wg-{len(gruppen)}-name": "Getränke", f"wg-{len(gruppen)}-reihenfolge": 5,
              f"wg-{len(gruppen)}-aktiv": "on", f"wg-{len(gruppen) + 1}-name": "",
              f"wg-{len(gruppen) + 1}-reihenfolge": 0,
              f"wg-{len(gruppen) + 1}-aktiv": "on"}  # fmt: skip
    admin_client.post(reverse("touren:einrichten"), daten)
    assert [g.name for g in lieferscheine.warengruppen()] == ["Getränke"]


def test_einrichten_fuer_die_fahrdienstleitung(buero):
    """Wer Touren plant, richtet ein – ohne Admin zu sein; Fahrer nicht."""
    seite = buero.get(reverse("touren:einrichten")).content.decode()
    assert "Touren einrichten" in seite and "stellt der Admin ein" in seite
    assert buero.post(reverse("touren:einrichten"), {
        "einrichten": "1", "mail_text": "Guten Tag", "zentrale": "Lagerweg 2",
        "zentrale_aus": "", "kiste_kg": "10"}).status_code == 302  # fmt: skip
    assert TourenEinstellungen.laden().zentrale == "Lagerweg 2"
    assert buero.get(reverse("touren:einstellungen")).status_code == 403


def test_umstaende_pflegt_die_tafel_selbst(buero):
    """Die Liste „Was war an der Station?“ steht unter „Einrichten“ (ADR 0163)."""
    from apps.touren.models import Umstand

    namen = list(Umstand.objects.values_list("name", flat=True))
    assert namen == ["Abgeholt", "Keine Ware", "Markt geschlossen", "Blockiert durch andere",
                     "Sonstiges"]  # fmt: skip
    assert Umstand.objects.get(name="Sonstiges").anmerkung_pflicht
    seite = buero.get(reverse("touren:einrichten")).content.decode()
    assert "Station ohne Lieferschein: Was war?" in seite and "Markt geschlossen" in seite
    alle = list(Umstand.objects.all())
    daten = {"umstaende": "1", "um-TOTAL_FORMS": len(alle) + 1, "um-INITIAL_FORMS": len(alle),
             "um-MIN_NUM_FORMS": 0, "um-MAX_NUM_FORMS": 1000}  # fmt: skip
    for nr, u in enumerate(alle):
        daten |= {f"um-{nr}-id": u.pk, f"um-{nr}-name": u.name,
                  f"um-{nr}-reihenfolge": u.reihenfolge}  # fmt: skip
        if u.name != "Blockiert durch andere":
            daten[f"um-{nr}-aktiv"] = "on"
    daten |= {f"um-{len(alle)}-name": "Rampe zugeparkt", f"um-{len(alle)}-reihenfolge": 45,
              f"um-{len(alle)}-aktiv": "on", f"um-{len(alle)}-anmerkung_pflicht": "on"}  # fmt: skip
    assert buero.post(reverse("touren:einrichten"), daten).status_code == 302
    neu = Umstand.objects.get(name="Rampe zugeparkt")
    assert neu.aktiv and neu.anmerkung_pflicht
    assert not Umstand.objects.get(name="Blockiert durch andere").aktiv
    assert str(neu) == "Rampe zugeparkt"


def test_einrichten_nicht_fuer_fahrer(fahrer):
    assert fahrer.get(reverse("touren:einrichten")).status_code == 403


def test_versand_ausgeschaltet_speichert_nur(admin):
    """Vorgabe: Es geht keine Mail hinaus; der Lieferschein bleibt zum Nachsenden stehen."""
    assert TourenEinstellungen._meta.get_field("versand").default == "aus"
    versand("aus")
    ls = lieferscheine.erstellen(station(), admin, [("Backwaren", Decimal("1"), "kg")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    assert not lieferscheine.senden(ls)
    assert not mail.outbox and ls.gesendet_am is None and "ausgeschaltet" in ls.mail_fehler
    versand("an")  # später eingeschaltet: nachsenden geht an die Station
    assert lieferscheine.senden(ls)
    assert mail.outbox[0].to == ["markt@example.org"] and ls.gesendet_am and not ls.mail_fehler


def test_versand_zum_test_nur_an_die_testadresse(admin):
    versand("test", "probe@example.org")
    ls = lieferscheine.erstellen(station(), admin, [("Backwaren", Decimal("1"), "kg")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    assert not lieferscheine.senden(ls)  # gilt weiter als nicht an die Station verschickt
    (post,) = mail.outbox
    assert post.to == ["probe@example.org"] and post.subject.startswith("[Test] ")
    assert "markt@example.org" in post.body and len(post.attachments) == 1
    assert ls.gesendet_am is None and ls.gesendet_an == ""
    assert "probe@example.org" in ls.mail_fehler
    versand("test")  # ohne Test-Adresse geht nichts hinaus – auch nicht an die Station
    assert not lieferscheine.senden(ls) and len(mail.outbox) == 1
    assert "Test-Adresse" in ls.mail_fehler


def test_einstellungen_testbetrieb_braucht_adresse(client, admin, anmelden):
    anmelden(client, admin)
    daten = {"einstellungen": "1", "lieferscheine": "on", "versand": "test", "test_email": "",
             "mail_text": "Hallo", "aufbewahrung_jahre": "10"}  # fmt: skip
    antwort = client.post(reverse("touren:einstellungen"), daten)
    assert "bitte eine Adresse" in antwort.content.decode()
    antwort = client.post(reverse("touren:einstellungen"), {**daten, "test_email": "p@example.org"})
    assert antwort.status_code == 302
    e = TourenEinstellungen.laden()
    assert (e.versand, e.test_email) == ("test", "p@example.org")


def test_mail_eigener_text_und_datenschutz_link(admin, settings):
    """Ein eigener Text ohne {tafel} bekommt wie bisher den Namen der Tafel darunter; mit Domain
    und hinterlegter Datenschutzerklärung steht der Link dabei. Inhalte sind maskiert."""
    s = station(name="Markt <b>Ecke</b>", email_lieferschein="ls@example.org")
    ls = lieferscheine.erstellen(s, admin, [("Obst/Gemüse", Decimal("1"), "kisten")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    tafel = TafelEinstellungen.laden()
    text, html = lieferscheine.mail_inhalt(ls, "Hallo,\n\nanbei der Schein.\n\nGruß", tafel)
    assert text.startswith("Hallo,\n\nanbei der Schein.\n\nGruß\nTafel Musterstadt\n")
    assert "<h2>Hallo,</h2><p>anbei der Schein.</p>" in html
    assert "&lt;b&gt;Ecke&lt;/b&gt;" in html and "<b>Ecke</b>" not in html
    assert lieferscheine.datenschutz_adresse(tafel) == ""
    settings.DOMAIN = "tafel.example.org"
    tafel.datenschutz_text = "<p>Erfundene Erklärung</p>"
    tafel.save()
    adresse = "https://tafel.example.org/antrag/de/seite/datenschutz/"
    assert lieferscheine.datenschutz_adresse(tafel) == adresse
    text, html = lieferscheine.mail_inhalt(ls, "Hallo {station} von {tafel}", tafel)
    assert text.startswith("Hallo Markt <b>Ecke</b> von Tafel Musterstadt\n")
    assert f"Informationen zum Datenschutz: {adresse}" in text
    assert f'<a href="{adresse}">hier</a>' in html


def test_mail_im_testbetrieb_mit_hinweis(admin):
    s = station(email_lieferschein="ls@example.org")
    e = TourenEinstellungen.laden()
    e.versand, e.test_email = TourenEinstellungen.Versand.TEST, "test@example.org"
    e.save()
    ls = lieferscheine.erstellen(s, admin, [("Obst/Gemüse", Decimal("1"), "kisten")],
                                 lieferscheine.unterschrift_lesen(unterschrift()))  # fmt: skip
    assert not lieferscheine.senden(ls)  # gilt weiter als nicht verschickt
    m = mail.outbox[-1]
    assert m.to == ["test@example.org"] and m.subject.startswith("[Test]")
    assert m.body.startswith("Testbetrieb: Diese Mail ginge sonst an ls@example.org")
    assert "<em>Testbetrieb: Diese Mail ginge sonst an ls@example.org" in m.alternatives[0][0]


def test_alter_vorgabetext_wird_ersetzt_eigener_bleibt():
    from importlib import import_module

    from django.apps import apps as django_apps

    from apps.touren.models import MAIL_TEXT, MAIL_TEXT_ALT

    migration = import_module("apps.touren.migrations.0021_lieferschein_mail_text")
    e = TourenEinstellungen.laden()
    assert e.mail_text == MAIL_TEXT  # neue Installation
    for vorher, nachher in (
        (MAIL_TEXT_ALT, MAIL_TEXT),
        ("Unser eigener Text", "Unser eigener Text"),
    ):
        TourenEinstellungen.objects.update(mail_text=vorher)
        migration.neuer_text(django_apps, None)
        assert TourenEinstellungen.laden().mail_text == nachher
    TourenEinstellungen.objects.update(mail_text=MAIL_TEXT)
    migration.alter_text(django_apps, None)
    assert TourenEinstellungen.laden().mail_text == MAIL_TEXT_ALT
