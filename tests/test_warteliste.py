"""Modul Warteliste (ADR 0051): Status, Einladen, Termine, Abgleich, Dubletten, Streichungen."""

import datetime as dt

import pytest
from django.core import mail as django_mail
from django.urls import reverse
from django.utils import timezone

from apps.antraege import auskunft
from apps.antraege.models import Antrag
from apps.core import geheimnis
from apps.core.models import MailEinstellungen, TafelEinstellungen
from apps.konten import rollen
from apps.kunden.models import Haushalt, Person, Zusatzfeld
from apps.warteliste import ablauf
from apps.warteliste.models import (
    Einladung,
    Streichung,
    Termin,
    WartelisteEinstellungen,
    Wartestand,
)

pytestmark = pytest.mark.django_db
S = Wartestand.Status


@pytest.fixture
def modul_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["warteliste"]
    t.name = "Tafel Musterstadt"
    t.save()


@pytest.fixture
def mailserver():
    m = MailEinstellungen.laden()
    m.server, m.port, m.benutzer, m.absender = "mail.example.org", 587, "tafel", "t@example.org"
    m.passwort_verschluesselt = geheimnis.verschluesseln("erfunden")
    m.save()
    return m


def antrag(vorname="Erika", nachname="Beispiel", tage=3, **mehr):
    a = Antrag.objects.create(vorname=vorname, nachname=nachname, **mehr)
    Antrag.objects.filter(pk=a.pk).update(eingegangen_am=timezone.now() - dt.timedelta(days=tage))
    a.refresh_from_db()
    return a


def ws(a):
    return Wartestand.objects.get(antrag=a)


def termin(tage=7):
    return Termin.objects.create(datum=timezone.localdate() + dt.timedelta(days=tage),
                                 von=dt.time(10), bis=dt.time(12))  # fmt: skip


# ── Status und Automatik ─────────────────────────────────────────────────────


def test_automatik_neu_wartend_und_wartezeit():
    alt, heute_neu = antrag(tage=3), antrag("Neu", "Heute", tage=0)
    ablauf.automatik()
    assert ws(alt).status == S.WARTEND and ws(heute_neu).status == S.NEU
    ablauf.status_setzen(ws(alt), S.WARTEZEIT, "Büro", timezone.localdate() - dt.timedelta(1))
    assert "Wartezeit bis" in alt.anmerkungen.get().text
    ablauf.automatik()
    assert ws(alt).status == S.WARTEZEIT_UM
    with pytest.raises(ValueError):
        ablauf.status_setzen(ws(alt), S.WARTEZEIT, "Büro")


def test_automatik_streichen_moeglich_und_direkt():
    e = WartelisteEinstellungen.laden()
    a, b = antrag(), antrag("Max", "Probe")
    ablauf.automatik()
    alt = Termin.objects.create(datum=timezone.localdate() - dt.timedelta(days=20), von=dt.time(9))
    ablauf.einladen([a, b], alt, "Büro", mail_senden=False)
    ablauf.automatik()
    assert ws(a).status == S.STREICHEN_MOEGLICH
    e.automatik = e.Automatik.STREICHEN
    e.save()
    ablauf.automatik()
    a.refresh_from_db()
    assert ws(a).status == S.GESTRICHEN and a.status == Antrag.Status.ABGELEHNT
    assert Streichung.objects.filter(antragsnummer=a.nummer, weg="automatik").exists()
    # Streichungsliste nach der Frist leer
    Streichung.objects.update(gestrichen_am=timezone.now() - dt.timedelta(days=40))
    ablauf.automatik()
    assert not Streichung.objects.exists()


def test_aufgenommen_und_abgelehnt_werden_uebernommen():
    a, b = antrag(), antrag("Max", "Probe")
    ablauf.automatik()
    a.kundennummer = "4711"
    a.status_setzen(Antrag.Status.ERLEDIGT, "Büro")
    b.status_setzen(Antrag.Status.ABGELEHNT, "Büro")
    ablauf.automatik()
    assert ws(a).status == S.AUFGENOMMEN and ws(b).status == S.GESTRICHEN


def test_entschuldigt_vermerkt_termin_und_streichen_zuruecknehmen():
    a = antrag()
    t = termin()
    ablauf.einladen([a], t, "Büro", mail_senden=False)
    ablauf.status_setzen(ws(a), S.ENTSCHULDIGT, "Büro")
    assert f"Entschuldigt für den Termin {t}" in a.anmerkungen.last().text
    ablauf.status_setzen(ws(a), S.GESTRICHEN, "Büro")
    a.refresh_from_db()
    assert a.status == Antrag.Status.ABGELEHNT
    ablauf.status_setzen(ws(a), S.WARTEND, "Büro")
    a.refresh_from_db()
    assert a.status == Antrag.Status.IN_BEARBEITUNG and ws(a).status == S.WARTEND


# ── Einladen und Absagen ─────────────────────────────────────────────────────


def test_einladen_mit_und_ohne_mail(mailserver):
    mit = antrag(email="erika@example.org")
    ohne = antrag("Max", "Probe")
    warte = antrag("Wanda", "Warten")
    ablauf.automatik()
    ablauf.status_setzen(ws(warte), S.WARTEZEIT, "Büro", timezone.localdate() + dt.timedelta(30))
    t = termin()
    ergebnisse = ablauf.einladen([mit, ohne, warte], t, "Büro")
    assert [e["ok"] for e in ergebnisse] == [True, False, False]
    assert "keine E-Mail-Adresse" in ergebnisse[1]["hinweis"]
    assert "Wartezeit bis" in ergebnisse[2]["hinweis"]
    assert ws(mit).status == S.EINGELADEN and ws(ohne).status == S.EINGELADEN
    assert ws(warte).status == S.WARTEZEIT
    nachricht = django_mail.outbox[0]
    assert nachricht.to == ["erika@example.org"] and "Einladung zur Anmeldung" in nachricht.subject
    assert "Erika Beispiel" in nachricht.body and "10:00 Uhr bis 12:00 Uhr" in nachricht.body
    mit.refresh_from_db()
    assert mit.status == Antrag.Status.IN_BEARBEITUNG
    assert Einladung.objects.filter(antrag=ohne, weg="E-Mail").exists() is False
    # Absage
    django_mail.outbox.clear()
    ergebnisse = ablauf.absagen(t, [mit, ohne], "Büro")
    assert [e["ok"] for e in ergebnisse] == [True, False]
    assert (
        "ENTFÄLLT" in django_mail.outbox[0].body
        and "Termin entfällt" in django_mail.outbox[0].subject
    )
    assert ws(mit).status == S.WARTEND and ws(mit).termin is None
    assert Einladung.objects.filter(antrag=mit, art="absage").count() == 1


def test_gestrichene_werden_nicht_eingeladen():
    a = antrag()
    ablauf.automatik()
    ablauf.status_setzen(ws(a), S.GESTRICHEN, "Büro")
    assert ablauf.einladen([a], termin(), "Büro", mail_senden=False)[0]["ok"] is False


def test_ort_aus_tafel_oder_einstellungen():
    t = TafelEinstellungen.laden()
    t.name, t.strasse, t.plz, t.ort = "Tafel Musterstadt", "Beispielweg 1", "12345", "Musterstadt"
    t.save()
    assert ablauf.ort(termin()) == "Tafel Musterstadt\nBeispielweg 1\n12345 Musterstadt"
    e = WartelisteEinstellungen.laden()
    e.ort = "Büro im Hinterhof"
    e.save()
    assert ablauf.ort(termin()) == "Büro im Hinterhof"
    assert ablauf.ort(Termin(datum=timezone.localdate(), von=dt.time(9), ort="Saal")) == "Saal"


# ── Dubletten und Abgleich ───────────────────────────────────────────────────


def test_dubletten_und_zusammenfuehren(admin):
    a = antrag("Erika", "Beispiel", geburtsdatum=dt.date(1980, 2, 3))
    b = antrag("Erika", "Beispiell", geburtsdatum=dt.date(1980, 2, 3))
    antrag("Max", "Anders")
    paare = ablauf.dubletten()
    assert len(paare) == 1 and {paare[0]["a"], paare[0]["b"]} == {a, b}
    ablauf.ignorieren(a, b, admin)
    assert ablauf.dubletten() == []
    c = antrag("Erika", "Beispiel")
    paar = ablauf.dubletten()[0]
    ablauf.zusammenfuehren(paar["a"], paar["b"], "Büro")
    weg = paar["b"]
    assert ws(weg).status == S.GESTRICHEN
    assert f"Antrag {weg.nummer}" in paar["a"].anmerkungen.last().text
    assert c in (paar["a"], paar["b"])


def test_kundenabgleich_sperrzeit_und_ausnahmen():
    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="900", ausweis_gueltig_bis=heute - dt.timedelta(60))
    p = Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika",
                              nachname="Beispiel", geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    e = ablauf.kundenabgleich([a], heute)[0]
    assert e["sperr"] and "Sperrzeit bis" in e["treffer"][0]["hinweise"][0]["text"]
    # Ausnahme über ein Zusatzfeld
    feld = Zusatzfeld.objects.create(schluessel="schwerbehindert", bezeichnung="Schwerbehindert",
                                     typ=Zusatzfeld.Typ.JA_NEIN)  # fmt: skip
    p.zusatz = {"schwerbehindert": True}
    p.save()
    w = WartelisteEinstellungen.laden()
    w.ausnahme_feld = feld
    w.save()
    hinweis = ablauf.kundenabgleich([a], heute)[0]["treffer"][0]["hinweise"][0]
    assert hinweis["art"] == "ok" and "Schwerbehindert" in hinweis["text"]
    # Ausweis noch gültig
    h.ausweis_gueltig_bis = heute + dt.timedelta(30)
    h.save()
    hinweis = ablauf.kundenabgleich([a], heute)[0]["treffer"][0]["hinweise"][0]
    assert "Verlängerung statt Neuanmeldung" in hinweis["text"]
    # Sperrzeit vorbei
    w.ausnahme_feld = None
    w.save()
    h.ausweis_gueltig_bis = heute - dt.timedelta(400)
    h.save()
    hinweis = ablauf.kundenabgleich([a], heute)[0]["treffer"][0]["hinweise"][0]
    assert hinweis["art"] == "ok" and "Sperrzeit vorbei" in hinweis["text"]


def test_auskunft_enthaelt_warteliste(pdf_text):
    a = antrag()
    ablauf.einladen([a], termin(), "Büro", mail_senden=False)
    from django.http import HttpResponse

    inhalt = pdf_text(HttpResponse(auskunft.antrag_pdf(a), content_type="application/pdf"))
    assert "Warteliste" in inhalt and "eingeladen" in inhalt


# ── Seiten ───────────────────────────────────────────────────────────────────


def test_modul_aus(admin_client):
    assert admin_client.get(reverse("warteliste:liste")).status_code == 404


def test_seiten(modul_an, admin_client, mailserver):
    a = antrag(email="erika@example.org", staatsangehoerigkeit="Ukraine")
    b = antrag("Max", "Probe", staatsangehoerigkeit="Syrien")
    seite = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert "Beispiel, Erika" in seite and "Probe, Max" in seite
    filter_ = {"staat_modus": "nicht", "staat": ["Syrien"]}
    seite = admin_client.get(reverse("warteliste:liste"), filter_).content.decode()
    assert "Beispiel, Erika" in seite and "Probe, Max" not in seite
    datum = (timezone.localdate() + dt.timedelta(days=5)).isoformat()
    antwort = admin_client.post(reverse("warteliste:einladen"), {
        "ids": [a.pk, b.pk], "datum": datum, "von": "10:00", "bis": "11:30", "mail": "on",
    })  # fmt: skip
    assert antwort.status_code == 200 and "Einladung an erika@example.org gesendet" in (
        antwort.content.decode()
    )
    t = Termin.objects.get()
    seite = admin_client.get(reverse("warteliste:termin", args=[t.pk])).content.decode()
    assert "Beispiel, Erika" in seite
    pdf = admin_client.get(reverse("warteliste:druckliste", args=[t.pk]))
    assert pdf["Content-Type"] == "application/pdf"
    admin_client.post(reverse("warteliste:status"), {
        "ids": [b.pk], "status": "erschienen", "zurueck": reverse("warteliste:termin", args=[t.pk]),
    })  # fmt: skip
    assert ws(b).status == S.ERSCHIENEN
    antwort = admin_client.post(reverse("warteliste:status"), {
        "ids": [b.pk], "status": "erschienen", "zurueck": "https://boese.example.org/",
    })  # fmt: skip
    assert antwort.url == reverse("warteliste:liste")
    admin_client.post(reverse("warteliste:termin_absagen", args=[t.pk]), {"ids": [a.pk]})
    assert ws(a).status == S.WARTEND
    assert admin_client.get(reverse("warteliste:eintrag", args=[a.pk])).status_code == 200
    for name in ("termine", "abgleich", "dubletten", "streichungsliste", "einstellungen"):
        assert admin_client.get(reverse(f"warteliste:{name}")).status_code == 200, name
    assert (
        admin_client.get(reverse("warteliste:streichungsliste"), {"pdf": 1})["Content-Type"]
        == "application/pdf"
    )
    seite = admin_client.get(reverse("warteliste:einstellungen")).content.decode()
    assert "Erika Musterfrau" in seite  # Vorschau
    # Termin mit Eingeladenen lässt sich nicht löschen
    admin_client.post(reverse("warteliste:einladen"), {"ids": [a.pk], "termin": t.pk})
    admin_client.post(reverse("warteliste:termin_loeschen", args=[t.pk]))
    assert Termin.objects.filter(pk=t.pk).exists()


def test_rechte(modul_an, client, anmelden, benutzer_mit_rolle):
    anmelden(client, benutzer_mit_rolle("berta", rollen.BUERO))
    assert client.get(reverse("warteliste:liste")).status_code == 200
    assert client.get(reverse("warteliste:einstellungen")).status_code == 403
    anmelden(client, benutzer_mit_rolle("anton", rollen.AUSGABE))
    assert client.get(reverse("warteliste:liste")).status_code == 403


def test_hilfe_und_menue(modul_an, admin_client):
    seite = admin_client.get(reverse("core:hilfe")).content.decode()
    assert 'id="warteliste"' in seite
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert "Abgleich mit Kundenstamm" in seite and "Warteliste und Einladungen" in seite


def test_abgleich_entscheiden_sperrzeit_und_einladen(admin_client, modul_an):
    """Treffer bestätigen: Sperrzeit wird zur Wartezeit; ungeprüft lädt „Einladen“ nicht ein."""
    from apps.warteliste.models import AbgleichEntscheidung

    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="900", ausweis_gueltig_bis=heute - dt.timedelta(60))
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    ablauf.automatik()
    liste = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert "mit möglicher Sperrzeit" in liste and "⚠ Sperrzeit? Prüfen" in liste
    ergebnis = ablauf.einladen([a], termin(), "Büro", mail_senden=False)
    assert not ergebnis[0]["ok"] and "erst im Abgleich prüfen" in ergebnis[0]["hinweis"]

    seite = admin_client.get(reverse("warteliste:abgleich")).content.decode()
    assert "✓ Ja, derselbe Haushalt – Wartezeit bis" in seite and "✗ Nein" in seite
    antwort = admin_client.post(reverse("warteliste:abgleich_entscheiden"),
                                {"antrag": a.pk, "kundennummer": "900", "gleich": "1"},
                                follow=True)  # fmt: skip
    assert "derselbe Haushalt wie Kunde 900 – Wartezeit bis" in antwort.content.decode()
    a.refresh_from_db()
    ws = Wartestand.objects.get(antrag=a)
    assert ws.status == "wartezeit" and ws.wartezeit_bis > heute and a.kundennummer == "900"
    assert "Abgleich: derselbe Haushalt wie Kunde 900" in a.anmerkungen.first().text
    seite = admin_client.get(reverse("warteliste:abgleich")).content.decode()
    assert "Kein ungeprüfter Antrag" in seite and "Zuletzt geprüft" in seite
    assert (
        "⚠ Sperrzeit? Prüfen" not in admin_client.get(reverse("warteliste:liste")).content.decode()
    )

    # Zurücknehmen bringt den Treffer zurück
    d = AbgleichEntscheidung.objects.get()
    admin_client.post(reverse("warteliste:abgleich_entscheiden"), {"zuruecknehmen": d.pk})
    assert not AbgleichEntscheidung.objects.exists()


def test_abgleich_nein_und_gueltiger_ausweis(admin_client, modul_an):
    heute = timezone.localdate()
    h = Haushalt.objects.create(kundennummer="901", ausweis_gueltig_bis=heute + dt.timedelta(90))
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Beispiel",
                          geburtsdatum=dt.date(1980, 2, 3))  # fmt: skip
    a = antrag(geburtsdatum=dt.date(1980, 2, 3))
    b = antrag(vorname="Erika", geburtsdatum=dt.date(1980, 2, 3))
    url = reverse("warteliste:abgleich_entscheiden")
    admin_client.post(url, {"antrag": a.pk, "kundennummer": "901", "gleich": "0"})
    assert ablauf.kundenabgleich(Antrag.objects.filter(pk=a.pk)) == []  # ausgeblendet
    admin_client.post(url, {"antrag": b.pk, "kundennummer": "901", "gleich": "1",
                            "weiter": reverse("warteliste:eintrag", args=[b.pk])})  # fmt: skip
    b.refresh_from_db()
    assert b.art == "verlaengerung" and b.kundennummer == "901"
    antwort = admin_client.post(url, {"antrag": b.pk, "kundennummer": "999", "gleich": "1"},
                                follow=True)  # fmt: skip
    assert "gibt es nicht mehr" in antwort.content.decode()


def test_streichungsliste_suche_und_anmerkungen(admin_client, modul_an):
    from apps.warteliste.models import Streichung

    Streichung.objects.create(antragsnummer="17", name="Probe, Gisela", von="Büro")
    Streichung.objects.create(antragsnummer="23", name="Muster, Jonas", von="Büro")
    url = reverse("warteliste:streichungsliste")
    seite = admin_client.get(url, {"q": "gisela"}).content.decode()
    assert "Probe, Gisela" in seite and "Muster, Jonas" not in seite and "hx-get" in seite
    assert "Nichts gefunden" in admin_client.get(url, {"q": "zzz"}).content.decode()

    a = antrag()
    ablauf.automatik()
    admin_client.post(reverse("warteliste:eintrag", args=[a.pk]),
                      {"anmerkung": "Hat angerufen, kommt ab Dezember"})  # fmt: skip
    assert a.anmerkungen.last().text == "Hat angerufen, kommt ab Dezember"
    liste = admin_client.get(reverse("warteliste:liste")).content.decode()
    assert 'data-spalten-wahl="warteliste"' in liste and 'data-spalte="anmerkung"' in liste
    assert "Hat angerufen, kommt ab Dezember" in liste
