"""Wechselwunsch eines Kunden: andere Uhrzeit, anderer Tag, andere Ausgabestelle (ADR 0173).
Alle Daten sind erfunden."""

import datetime as dt

import pytest
from django.core import mail as django_mail
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core import geheimnis
from apps.core.models import MailEinstellungen
from apps.kunden import wechsel
from apps.kunden.models import (
    Ausgabestelle,
    GeplanterWechsel,
    Haushalt,
    HaushaltEreignis,
    Kundengruppe,
    Notiz,
    Person,
    Wechselwunsch,
)

pytestmark = pytest.mark.django_db
LISTE = reverse("kunden:wechselwuensche")


def gruppe(name, stelle, tage, uhr, maximum=5):
    return Kundengruppe.objects.create(
        name=name, ausgabestelle=stelle, wochentage=tage, maximum=maximum,
        uhrzeit=dt.time(*uhr) if uhr else None,
    )  # fmt: skip


def haushalt(nummer, g, **mehr):
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=g, **mehr)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                          nachname=f"Muster{nummer}")  # fmt: skip
    return h


@pytest.fixture
def lage(admin):
    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()
    zentrale = Ausgabestelle.objects.create(name="Zentrale")
    nord = Ausgabestelle.objects.create(name="Nord")
    g = {
        "mi12": gruppe("Mi 12:00", zentrale, "Mi", (12, 0)),
        "mi10": gruppe("Mi 10:00", zentrale, "Mi", (10, 0)),
        "mi14": gruppe("Mi 14:00", zentrale, "Mi", (14, 0), maximum=1),
        "do12": gruppe("Do 12:00", zentrale, "Do", (12, 0)),
        "nord": gruppe("Nord Mo", nord, "Mo", (11, 0)),
        "parken": gruppe("Parken", zentrale, "Mi", (9, 0)),
    }
    Kundengruppe.objects.filter(pk=g["parken"].pk).update(intern=True)
    haushalt("900", g["mi14"])  # macht „Mi 14:00“ voll
    h = haushalt("100", g["mi12"], telefon="01234 5550")
    return {"h": h, "st_zentrale": zentrale, "st_nord": nord, **g}


def namen(liste):
    return [e["gruppe"].name for e in liste]


def test_moeglichkeiten_grenzen_ein(lage):
    h = lage["h"]
    assert [a for a, _ in wechsel.arten(h)] == ["uhrzeit", "tag", "stelle"]
    # selber Tag: früher / später / egal – nur mit freiem Platz, nie die eigene oder eine interne
    assert namen(wechsel.moeglichkeiten(h, "uhrzeit", "frueher")) == ["Mi 10:00"]
    assert namen(wechsel.moeglichkeiten(h, "uhrzeit", "spaeter")) == []  # Mi 14:00 ist voll
    assert namen(wechsel.moeglichkeiten(h, "uhrzeit", "egal")) == ["Mi 10:00"]
    Kundengruppe.objects.filter(name="Mi 14:00").update(maximum=2)
    assert namen(wechsel.moeglichkeiten(h, "uhrzeit", "spaeter")) == ["Mi 14:00"]
    assert namen(wechsel.moeglichkeiten(h, "uhrzeit", "egal")) == ["Mi 10:00", "Mi 14:00"]
    # ein geplanter Zuzug belegt den Platz schon
    GeplanterWechsel.objects.create(
        haushalt=Haushalt.objects.get(kundennummer="900"), ziel_gruppe=lage["mi14"],
        ab=timezone.localdate() + dt.timedelta(days=3),
    )  # fmt: skip
    # anderer Tag an derselben Ausgabestelle, andere Ausgabestelle
    assert wechsel.tage_zur_wahl(h) == [("Do", "Donnerstag")]
    assert namen(wechsel.moeglichkeiten(h, "tag", tag="Do")) == ["Do 12:00"]
    assert wechsel.stellen_zur_wahl(h) == [lage["st_nord"]]
    assert namen(wechsel.moeglichkeiten(h, "stelle", stelle=lage["st_nord"].pk)) == ["Nord Mo"]
    assert wechsel.moeglichkeiten(h, "stelle") == [] and wechsel.moeglichkeiten(h, "x") == []
    assert wechsel.gruppe_text(lage["mi10"]) == "Zentrale – Mi 10:00 (Mi, 10:00 Uhr)"
    # ohne Kundengruppe bleibt nur die Wahl der Ausgabestelle
    ohne = haushalt("200", None)
    assert [a for a, _ in wechsel.arten(ohne)] == ["stelle"]
    assert wechsel.stellen_zur_wahl(ohne) == [lage["st_nord"], lage["st_zentrale"]]


def test_eintragen_schritt_fuer_schritt_mit_kontaktpruefung(admin_client, admin, lage):
    h = lage["h"]
    ziel = reverse("kunden:wechselwunsch", args=[h.kundennummer])
    # am Kunden steht der Knopf
    seite = admin_client.get(reverse("kunden:haushalt", args=[h.kundennummer])).content.decode()
    assert "Will wechseln" in seite and ziel in seite
    # Schritt 1: nur die erste Frage
    seite = admin_client.get(ziel).content.decode()
    assert "1. Was soll sich ändern?" in seite and 'wechsel-frage" id="weiter' not in seite
    assert 'id="frei"' not in seite
    assert "Bisher: Zentrale – Mi 12:00" in seite
    # Schritt 2 erscheint mit der Wahl
    seite = admin_client.get(ziel, {"was": "uhrzeit"}).content.decode()
    assert "2. Früher oder später?" in seite and 'id="frei"' not in seite
    assert "2. An welchem Tag?" in admin_client.get(ziel, {"was": "tag"}).content.decode()
    # Schritt 3 und 4: freie Möglichkeiten und Erreichbarkeit (E-Mail fehlt, Telefon ist da)
    seite = admin_client.get(ziel, {"was": "uhrzeit", "richtung": "frueher"}).content.decode()
    assert "3. Was ist dafür aktuell frei?" in seite and "Mi 10:00" in seite
    assert "Mi 14:00" not in seite and "4. Ist der Kunde erreichbar?" in seite
    assert 'name="email"' in seite and 'name="telefon"' not in seite
    assert "Ohne E-Mail-Adresse können wir nicht zurückschreiben" in seite
    daten = {"was": "uhrzeit", "richtung": "frueher", "gruppe": lage["mi10"].pk}
    # ohne E-Mail und ohne Haken: Fehler, nichts gespeichert
    antwort = admin_client.post(ziel, daten)
    assert antwort.status_code == 200 and "E-Mail-Adresse des Kunden eintragen" in (
        antwort.content.decode()
    )
    assert not Wechselwunsch.objects.exists()
    assert "so nicht gültig" in admin_client.post(ziel, {**daten, "email": "x"}).content.decode()
    # ohne Wahl einer Möglichkeit: Fehler
    ohne = admin_client.post(ziel, {"was": "uhrzeit", "richtung": "frueher", "ohne_email": "1"})
    assert "eine der freien Möglichkeiten wählen" in ohne.content.decode()
    # mit E-Mail: gespeichert, E-Mail steht jetzt am Kunden, Notiz, Historie
    antwort = admin_client.post(
        ziel, {**daten, "email": "erika@example.org", "anmerkung": " wegen  Arbeit "}, follow=True
    )
    assert "Wir prüfen das; der Kunde wird per E-Mail benachrichtigt" in antwort.content.decode()
    w = Wechselwunsch.objects.get()
    assert (w.kundennummer, w.art, w.status, w.wunsch_gruppe) == (
        "100",
        "uhrzeit",
        "offen",
        lage["mi10"],
    )
    assert w.wunsch == "andere Uhrzeit am selben Tag (früher) → Zentrale – Mi 10:00 (Mi, 10:00 Uhr)"
    assert (w.anmerkung, w.ohne_email, w.von) == ("wegen Arbeit", False, "chefin")
    assert w.bisher.startswith("Zentrale – Mi 12:00")
    h.refresh_from_db()
    assert h.email == "erika@example.org" and h.geaendert_von == "chefin"
    assert HaushaltEreignis.objects.filter(kundennummer="100").exists()
    notiz = Notiz.objects.get(kundennummer="100")
    assert notiz.text.startswith("Will wechseln: andere Uhrzeit") and "prüft das" in notiz.text
    assert h.kundengruppe == lage["mi12"]  # entschieden ist noch nichts
    # ein zweiter Wunsch geht erst nach der Entscheidung
    seite = admin_client.get(ziel).content.decode()
    assert "schon ein Wechselwunsch offen" in seite and 'id="frei"' not in seite
    with pytest.raises(wechsel.WechselFehler, match="schon ein Wechselwunsch offen"):
        wechsel.eintragen(h, admin, "tag", tag="Do", gruppe=lage["do12"])


def test_ohne_email_nur_mit_haken_und_nichts_frei(admin_client, admin, lage):
    h = lage["h"]
    ziel = reverse("kunden:wechselwunsch", args=[h.kundennummer])
    # später ist nichts frei: der Wunsch wird trotzdem aufgenommen
    seite = admin_client.get(ziel, {"was": "uhrzeit", "richtung": "spaeter"}).content.decode()
    assert "nichts frei" in seite and 'type="radio"' not in seite
    antwort = admin_client.post(
        ziel, {"was": "uhrzeit", "richtung": "spaeter", "gruppe": "keine", "ohne_email": "1"},
        follow=True,
    )  # fmt: skip
    assert "Ohne E-Mail-Adresse können wir nicht zurückschreiben" in antwort.content.decode()
    w = Wechselwunsch.objects.get()
    assert w.wunsch_gruppe is None and w.ohne_email and "aktuell nichts frei" in w.wunsch
    # ganz ohne Kontakt geht es nicht; Telefon wird beim Kunden gespeichert
    stumm = haushalt("300", lage["mi12"])
    with pytest.raises(wechsel.WechselFehler, match="nicht erreichen"):
        wechsel.eintragen(stumm, admin, "tag", tag="Do", gruppe=lage["do12"], ohne_email=True)
    wechsel.eintragen(stumm, admin, "tag", tag="Do", gruppe=lage["do12"], ohne_email=True,
                      telefon=" 0123  456 ")  # fmt: skip
    stumm.refresh_from_db()
    assert stumm.telefon == "0123 456" and stumm.email == ""
    # eine Gruppe, die nicht zum Wunsch passt, wird abgelehnt
    dritter = haushalt("400", lage["mi12"], email="k@example.org")
    with pytest.raises(wechsel.WechselFehler, match="passt nicht"):
        wechsel.eintragen(dritter, admin, "tag", tag="Do", gruppe=lage["nord"])
    with pytest.raises(wechsel.WechselFehler, match="was sich ändern soll"):
        wechsel.eintragen(dritter, admin, "quatsch")


def test_genehmigen_sofort_spaeter_und_ablehnen(admin_client, admin, lage):
    h = lage["h"]
    Haushalt.objects.filter(pk=h.pk).update(email="erika@example.org")
    h.refresh_from_db()
    w = wechsel.eintragen(h, admin, "uhrzeit", "frueher", gruppe=lage["mi10"])
    seite = admin_client.get(LISTE).content.decode()
    assert "Offen (1)" in seite and "Mi 10:00" in seite and "Muster100" in seite
    assert admin_client.get(reverse("core:start")).content.decode().count("Wechselwünsche offen: 1")
    ziel = reverse("kunden:wechsel_entscheiden", args=[w.pk])
    # ohne Gruppe: Fehler; in der Vergangenheit: Fehler
    assert "neue Kundengruppe wählen" in admin_client.post(ziel, {}, follow=True).content.decode()
    gestern = (timezone.localdate() - dt.timedelta(days=1)).isoformat()
    vergangen = admin_client.post(ziel, {"gruppe": lage["mi10"].pk, "ab": gestern}, follow=True)
    assert "nicht in der Vergangenheit" in vergangen.content.decode()
    # sofort genehmigen: Gruppe gewechselt, Mail an den Kunden, Notizen
    antwort = admin_client.post(
        ziel, {"gruppe": lage["mi10"].pk, "antwort": "Bitte pünktlich sein."}, follow=True
    )
    assert "genehmigt" in antwort.content.decode() and "gesendet am" in antwort.content.decode()
    h.refresh_from_db()
    w.refresh_from_db()
    assert h.kundengruppe == lage["mi10"] and w.status == "genehmigt"
    assert w.ab == timezone.localdate() and w.entschieden_von == "chefin"
    (post,) = django_mail.outbox
    assert post.to == ["erika@example.org"] and "genehmigt" in post.subject
    assert "Mi 10:00" in post.body and "Bitte pünktlich sein." in post.body
    texte = list(Notiz.objects.filter(kundennummer="100").values_list("text", flat=True))
    assert any(t.startswith("Wechselwunsch genehmigt: ab sofort") for t in texte)
    assert any(t.startswith("Ausweis drucken") for t in texte)
    assert "Zuletzt entschieden" in admin_client.get(LISTE).content.decode()
    # zweimal entscheiden geht nicht
    assert (
        "schon entschieden"
        in admin_client.post(ziel, {"gruppe": lage["mi10"].pk}, follow=True).content.decode()
    )
    # zu einem späteren Tag: als geplanter Wechsel, die Gruppe bleibt bis dahin
    w2 = wechsel.eintragen(h, admin, "tag", tag="Do", gruppe=lage["do12"])
    spaeter = timezone.localdate() + dt.timedelta(days=10)
    wechsel.genehmigen(w2, admin, lage["do12"], spaeter)
    h.refresh_from_db()
    plan = GeplanterWechsel.objects.get(haushalt=h, erledigt_am__isnull=True)
    assert h.kundengruppe == lage["mi10"] and (plan.ziel_gruppe, plan.ab) == (lage["do12"], spaeter)
    assert f"Ab dem {spaeter:%d.%m.%Y} gilt für Sie" in django_mail.outbox[-1].body
    # ablehnen: nichts ändert sich, Mail und Notiz
    w3 = wechsel.eintragen(h, admin, "stelle", stelle=lage["st_nord"], gruppe=lage["nord"])
    admin_client.post(reverse("kunden:wechsel_entscheiden", args=[w3.pk]),
                      {"ablehnen": "1", "antwort": "Dort ist es zu voll."})  # fmt: skip
    w3.refresh_from_db()
    h.refresh_from_db()
    assert w3.status == "abgelehnt" and h.kundengruppe == lage["mi10"]
    assert "leider nicht" in django_mail.outbox[-1].body
    assert "Dort ist es zu voll." in django_mail.outbox[-1].body
    assert Notiz.objects.filter(text__startswith="Wechselwunsch abgelehnt").exists()


def test_ohne_email_keine_mail_und_frist(admin, lage):
    h = lage["h"]
    w = wechsel.eintragen(h, admin, "uhrzeit", "frueher", gruppe=lage["mi10"], ohne_email=True)
    wechsel.genehmigen(w, admin, lage["mi10"])
    w.refresh_from_db()
    assert not django_mail.outbox and w.mail_stand.startswith("keine E-Mail-Adresse")
    # entschiedene verschwinden nach 90 Tagen, offene bleiben
    from apps.kunden.models import alte_wechselwuensche_loeschen

    offen = wechsel.eintragen(h, admin, "tag", tag="Do", gruppe=lage["do12"], ohne_email=True)
    Wechselwunsch.objects.filter(pk=w.pk).update(
        entschieden_am=timezone.now() - dt.timedelta(days=91)
    )
    assert alte_wechselwuensche_loeschen() == 1
    assert list(Wechselwunsch.objects.all()) == [offen]


def test_rechte(lage, admin, benutzer_mit_rolle, anmelden, recht_geben, pdf_text, admin_client):
    h = lage["h"]
    w = wechsel.eintragen(h, admin, "uhrzeit", "frueher", gruppe=lage["mi10"], ohne_email=True)
    buero = anmelden(Client(), benutzer_mit_rolle("bernd", "Büro"))
    # eintragen darf, wer Notizen schreibt; entscheiden nur mit dem eigenen Recht
    assert buero.get(reverse("kunden:wechselwunsch", args=["100"])).status_code == 200
    assert buero.get(LISTE).status_code == 403
    ziel = reverse("kunden:wechsel_entscheiden", args=[w.pk])
    assert buero.post(ziel, {"gruppe": lage["mi10"].pk}).status_code == 403
    assert "Wechselwünsche" not in buero.get(reverse("core:start")).content.decode()
    recht_geben("Büro", "kunden.wechsel_entscheiden")
    buero = anmelden(Client(), benutzer_mit_rolle("berta", "Büro"))
    assert buero.get(LISTE).status_code == 200
    assert "Wechselwünsche" in buero.get(reverse("core:start")).content.decode()
    # steht in der Auskunft zum Kunden
    auskunft = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["100"])))
    assert "Wechselwünsche" in auskunft and "andere Uhrzeit" in auskunft


def test_am_einlass_ueber_die_notizen(admin_client, lage):
    """Der Knopf steht am Einlass bei den Notizen, und nach dem Eintragen ist man wieder am
    Einlass bei diesem Kunden."""
    einlass = reverse("ausgabe:empfang")
    weg = reverse("kunden:wechselwunsch", args=["100"])
    seite = admin_client.get(einlass, {"nummer": "100"}, HTTP_HX_REQUEST="true").content.decode()
    assert f'href="{weg}?von=einlass"' in seite and "Will wechseln" in seite

    seite = admin_client.get(weg, {"von": "einlass", "was": "uhrzeit", "richtung": "frueher"})
    assert f'href="{einlass}?nummer=100"' in seite.content.decode()  # „zurück zum Kunden“
    antwort = admin_client.post(weg, {
        "von": "einlass", "was": "uhrzeit", "richtung": "frueher",
        "gruppe": str(lage["mi10"].pk), "email": "erika@example.org",
    })  # fmt: skip
    assert antwort.status_code == 302 and antwort["Location"] == f"{einlass}?nummer=100"
    assert Wechselwunsch.objects.get(kundennummer="100").wunsch_gruppe == lage["mi10"]
    # Zurück am Einlass steht der Wunsch als Notiz beim Kunden
    seite = admin_client.get(einlass, {"nummer": "100"}, HTTP_HX_REQUEST="true").content.decode()
    assert "Will wechseln:" in seite


def _angebot(admin_client, admin, lage, **mehr):
    """Legt einen Wunsch an, bietet den Platz „Mi 14:00“ (Maximum 1) an und liefert Wunsch und
    Schlüssel aus dem Link der Mail."""
    import re

    h = lage["h"]
    Haushalt.objects.filter(pk=h.pk).update(email="erika@example.org")
    h.refresh_from_db()
    Kundengruppe.objects.filter(pk=lage["mi14"].pk).update(maximum=2)  # genau ein Platz frei
    w = wechsel.eintragen(h, admin, "uhrzeit", "spaeter", gruppe=lage["mi14"])
    antwort = admin_client.post(
        reverse("kunden:wechsel_entscheiden", args=[w.pk]),
        {"anbieten": "1", "gruppe": lage["mi14"].pk, "antwort": "Bitte Tasche mitbringen.", **mehr},
        follow=True,
    )
    assert "Platz angeboten" in antwort.content.decode()
    (post,) = django_mail.outbox
    schluessel = re.search(r"/kunden/wechsel/([\w-]+)/\?antwort=ja", post.body).group(1)
    w.refresh_from_db()
    return w, schluessel, post


def test_platz_anbieten_und_kunde_bestaetigt(admin_client, admin, lage):
    """Angebot per Mail mit Link: Der Platz ist reserviert, ein bloßer Aufruf ändert nichts,
    erst der Knopf bestätigt – dann zieht der Kunde von selbst um (ADR 0175)."""
    from apps.kunden import gruppen

    w, schluessel, post = _angebot(admin_client, admin, lage)
    assert post.to == ["erika@example.org"] and "Platz anbieten" in post.subject
    assert "Mi 14:00" in post.body and "Bitte Tasche mitbringen." in post.body
    html = post.alternatives[0][0]
    assert (
        "Ja, ich möchte wechseln" in html and f"/kunden/wechsel/{schluessel}/?antwort=nein" in html
    )
    # gespeichert ist nur die Prüfsumme; im Mail-Archiv steht der Link nicht
    from apps.core.models import GesendeteMail

    assert schluessel not in w.angebot_schluessel and len(w.angebot_schluessel) == 64
    assert not GesendeteMail.objects.filter(text__contains=schluessel).exists()
    assert w.status == "offen" and w.angebot_laeuft
    assert w.angebot_bis == timezone.localdate() + dt.timedelta(days=wechsel.ANGEBOT_TAGE)
    # reserviert: Die Gruppe mit einem Platz ist für andere nicht mehr frei
    assert gruppen.reservierte_zugaenge()[lage["mi14"].pk] == 1
    anderer = haushalt("200", lage["mi12"])
    assert "Mi 14:00" not in namen(wechsel.moeglichkeiten(anderer, "uhrzeit", "spaeter"))
    liste = admin_client.get(LISTE).content.decode()
    assert "Antwort bis" in liste and 'name="anbieten"' not in liste  # läuft: kein zweites
    # ein zweites Angebot geht nicht, solange eines läuft
    with pytest.raises(wechsel.WechselFehler):
        wechsel.anbieten(w, admin, lage["mi10"], None, "", lambda s: s)

    # Die Seite ist ohne Anmeldung erreichbar und zeigt nur das Angebot, keinen Namen
    kunde = Client()
    seite = reverse("kunden:wechsel_angebot", args=[schluessel])
    inhalt = kunde.get(seite + "?antwort=ja").content.decode()
    assert "Mi 14:00" in inhalt and "Ja, verbindlich wechseln" in inhalt
    assert "Muster100" not in inhalt and "Erika" not in inhalt and ">100<" not in inhalt
    lage["h"].refresh_from_db()
    assert lage["h"].kundengruppe == lage["mi12"]  # der bloße Aufruf hat nichts geändert
    assert kunde.get(reverse("kunden:wechsel_angebot", args=["falsch"])).status_code == 404

    django_mail.outbox.clear()
    antwort = kunde.post(seite, {"antwort": "ja"}, follow=True).content.decode()
    assert "der Wechsel ist eingetragen" in antwort
    lage["h"].refresh_from_db()
    w.refresh_from_db()
    assert lage["h"].kundengruppe == lage["mi14"]
    assert w.status == "genehmigt" and w.angebot_antwort == "ja"
    assert w.entschieden_von == "chefin (vom Kunden bestätigt)"
    assert "genehmigt" in django_mail.outbox[0].subject  # Bestätigung an den Kunden
    # ein zweiter Klick ändert nichts mehr
    assert "der Wechsel ist eingetragen" in kunde.post(seite, {"antwort": "nein"},
                                                       follow=True).content.decode()  # fmt: skip
    w.refresh_from_db()
    assert w.angebot_antwort == "ja"
    assert gruppen.reservierte_zugaenge().get(lage["mi14"].pk, 0) == 0


def test_angebot_spaeter_abgelehnt_abgelaufen(admin_client, admin, lage):
    kunde = Client()
    spaeter = timezone.localdate() + dt.timedelta(days=20)
    w, schluessel, _ = _angebot(admin_client, admin, lage, ab=spaeter.isoformat())
    seite = reverse("kunden:wechsel_angebot", args=[schluessel])
    # „Nein“: nichts ändert sich, der Wunsch bleibt offen, die Verwaltung sieht die Antwort
    assert "Sie möchten nicht wechseln" in kunde.post(seite, {"antwort": "nein"},
                                                     follow=True).content.decode()  # fmt: skip
    w.refresh_from_db()
    lage["h"].refresh_from_db()
    assert w.status == "offen" and w.angebot_antwort == "nein" and not w.angebot_laeuft
    assert lage["h"].kundengruppe == lage["mi12"]
    liste = admin_client.get(LISTE).content.decode()
    assert "vom Kunden abgelehnt" in liste and 'name="anbieten"' in liste  # neu anbieten geht
    assert Notiz.objects.filter(kundennummer="100", text__startswith="Angebotenen Platz").exists()
    # neues Angebot mit späterem Datum: „Ja“ plant den Wechsel zum Stichtag
    django_mail.outbox.clear()
    import re

    ziel = reverse("kunden:wechsel_entscheiden", args=[w.pk])
    admin_client.post(ziel, {"anbieten": "1", "gruppe": lage["mi14"].pk,
                             "ab": spaeter.isoformat()})  # fmt: skip
    neu = re.search(r"/kunden/wechsel/([\w-]+)/", django_mail.outbox[0].body).group(1)
    assert neu != schluessel
    assert kunde.get(seite).status_code == 404  # der alte Link gilt nicht mehr
    seite = reverse("kunden:wechsel_angebot", args=[neu])
    # abgelaufen: die Seite sagt es, nichts passiert, der Platz ist wieder frei
    Wechselwunsch.objects.filter(pk=w.pk).update(
        angebot_bis=timezone.localdate() - dt.timedelta(days=1))  # fmt: skip
    assert "gilt nicht mehr" in kunde.post(seite, {"antwort": "ja"},
                                          follow=True).content.decode()  # fmt: skip
    assert "keine Antwort" in admin_client.get(LISTE).content.decode()
    from apps.kunden import gruppen

    assert gruppen.reservierte_zugaenge().get(lage["mi14"].pk, 0) == 0
    Wechselwunsch.objects.filter(pk=w.pk).update(angebot_bis=timezone.localdate())
    kunde.post(seite, {"antwort": "ja"})
    w.refresh_from_db()
    lage["h"].refresh_from_db()
    assert w.status == "genehmigt" and w.ab == spaeter
    assert lage["h"].kundengruppe == lage["mi12"]  # erst zum Stichtag
    assert GeplanterWechsel.objects.get(haushalt=lage["h"]).ab == spaeter


def test_angebot_ohne_email_geht_nicht(admin_client, admin, lage):
    w = wechsel.eintragen(lage["h"], admin, "uhrzeit", "frueher", gruppe=lage["mi10"],
                          ohne_email=True)  # fmt: skip
    liste = admin_client.get(LISTE).content.decode()
    assert "Ohne E-Mail-Adresse geht kein Angebot" in liste
    ziel = reverse("kunden:wechsel_entscheiden", args=[w.pk])
    antwort = admin_client.post(ziel, {"anbieten": "1", "gruppe": lage["mi10"].pk}, follow=True)
    assert "keine E-Mail-Adresse" in antwort.content.decode()
    w.refresh_from_db()
    assert not w.angebot_am and not django_mail.outbox


def test_angebot_texte_in_allen_sprachen():
    """Jede Sprache des Antrags hat alle Texte des Angebots, mit denselben Platzhaltern."""
    import re

    from apps.antraege import sprachen

    deutsch = wechsel.texte("de")
    for code in sprachen.NACH_CODE:
        assert (wechsel.TEXTE / f"{code}.json").is_file(), code
        t = wechsel.texte(code)
        assert set(t) == set(deutsch), code
        for schluessel, wert in deutsch.items():
            assert t[schluessel].strip(), (code, schluessel)
            assert re.findall(r"\{\w+\}", t[schluessel]) == re.findall(r"\{\w+\}", wert), (
                code, schluessel)  # fmt: skip


def test_angebot_deutsch_und_sprache_des_kunden(admin_client, admin, lage):
    """Mail und Seite: zuerst Deutsch, darunter die Sprache zur Staatsangehörigkeit der
    Hauptperson. Ohne Angabe (oder deutsch) bleibt es bei Deutsch."""
    from apps.antraege import sprachen
    from apps.core.auswahl import LAENDERCODE

    land = next(name for name, code in LAENDERCODE.items()
                if sprachen.LAND_SPRACHE.get(code) == "ar")  # fmt: skip
    Person.objects.filter(haushalt=lage["h"]).update(staatsangehoerigkeit=land)
    w, schluessel, post = _angebot(admin_client, admin, lage)
    ar = wechsel.texte("ar")
    deutsch_zuerst = post.body.index("Wir können Ihnen einen Platz anbieten")
    assert deutsch_zuerst < post.body.index(ar["angebot"])
    assert post.body.count("?antwort=ja") == 2 and ar["ja"] in post.body
    assert post.body.count("Bitte Tasche mitbringen.") == 1  # der freie Zusatz nur einmal
    html = post.alternatives[0][0]
    assert '<div lang="ar" dir="rtl">' in html and ar["nein"] in html
    seite = Client().get(reverse("kunden:wechsel_angebot", args=[schluessel])).content.decode()
    assert seite.index("Ja, verbindlich wechseln") < seite.index(ar["ja"])
    assert 'lang="ar" dir="rtl"' in seite and "{bis}" not in seite and "{ab}" not in seite
    # ohne Staatsangehörigkeit: nur Deutsch
    assert wechsel.zweitsprache(haushalt("300", lage["mi12"])) is None
