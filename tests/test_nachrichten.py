"""Nachrichten der Ausgabestellen an die Verwaltung zu fremden Kunden (ADR 0062)."""

import datetime as dt

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.konten import rollen
from apps.kunden.models import (
    Ausgabestelle,
    Haushalt,
    Kundengruppe,
    Nachricht,
    Person,
    alte_nachrichten_loeschen,
)

pytestmark = pytest.mark.django_db
EMPFANG = reverse("ausgabe:empfang")


@pytest.fixture
def lage(admin, benutzer_mit_rolle, anmelden):
    mitte = Ausgabestelle.objects.create(name="Mitte")
    nord = Ausgabestelle.objects.create(name="Nord")
    g = Kundengruppe.objects.create(name="Nord Mo", ausgabestelle=nord, wochentage="Mo")
    h = Haushalt.objects.create(kundennummer="501", kundengruppe=g)
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Geheim")
    b = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b.ausgabestellen.set([mitte])
    return anmelden(Client(), b), mitte


def test_einlass_und_liste(lage, admin_client):
    c, mitte = lage
    c.post(reverse("ausgabe:ausgabestelle"), {"ausgabestelle": mitte.pk})
    seite = c.get(EMPFANG, {"nummer": "501"}).content.decode()
    assert "gehört nicht zu Ihrer Ausgabestelle" in seite and "Nachricht an die Verwaltung" in seite
    assert "Geheim" not in seite
    url = reverse("kunden:nachricht", args=["501"])
    antwort = c.post(url, {"text": "War heute hier, wohnt jetzt bei uns.", "zurueck": EMPFANG})
    assert antwort.url == EMPFANG
    n = Nachricht.objects.get()
    assert (n.kundennummer, n.stelle, n.von) == ("501", mitte, "anton")
    # leer, fremde Rücksprungadresse, unbekannter Kunde
    c.post(url, {"text": " ", "zurueck": EMPFANG})
    assert c.post(url, {"text": "x", "zurueck": "https://boese.example/"}).url == "/"
    assert c.post(reverse("kunden:nachricht", args=["999"]), {"text": "x"}).status_code == 404
    assert Nachricht.objects.count() == 2
    # Kundenliste: Suche nach der Nummer zeigt den Knopf ebenfalls
    liste = c.get(reverse("kunden:uebersicht"), {"q": "501"}).content.decode()
    assert "Nachricht an die Verwaltung" in liste
    # Die Ausgabestelle darf die Nachrichten nicht lesen
    assert c.get(reverse("kunden:nachrichten")).status_code == 403
    # Verwaltung: Startseite, Menü, Liste, Haushaltsseite, erledigen
    assert "2 × Sonstiges" in admin_client.get("/").content.decode()  # je Anliegen (ADR 0068)
    seite = admin_client.get(reverse("kunden:nachrichten")).content.decode()
    assert "War heute hier" in seite and "anton (Mitte)" in seite
    haus = admin_client.get(reverse("kunden:haushalt", args=["501"])).content.decode()
    assert "Nachrichten der Ausgabestellen" in haus
    boese = {"nachricht": n.pk, "weiter": "https://boese.example/"}
    assert admin_client.post(reverse("kunden:nachrichten"), boese).url == "/kunden/nachrichten/"
    n.refresh_from_db()
    assert n.erledigt_am and n.erledigt_von == "chefin"
    admin_client.post(reverse("kunden:nachrichten"), {"nachricht": n.pk})
    n.refresh_from_db()
    assert n.erledigt_am is None


def test_recht_auskunft_und_frist(admin_client, lage, pdf_text):
    from apps.konten.models import Rolle

    assert "kunden.nachrichten" in Rolle.objects.get(gruppe__name=rollen.BUERO).rechte
    Nachricht.objects.create(kundennummer="501", text="Neue Adresse bekannt", von="anton")
    text = pdf_text(admin_client.get(reverse("kunden:auskunft", args=["501"])))
    assert "Nachrichten der Ausgabestellen" in text and "Neue Adresse bekannt" in text
    alt = Nachricht.objects.create(kundennummer="501", text="alt",
                                   erledigt_am=timezone.now() - dt.timedelta(days=91))  # fmt: skip
    assert alte_nachrichten_loeschen() == 1 and not Nachricht.objects.filter(pk=alt.pk).exists()


# ── Nachrichten an die Verwaltung ohne Kunden (ADR 0140) ─────────────────────

AN_VERWALTUNG = reverse("kunden:an_verwaltung")


@pytest.fixture
def mailserver(settings):
    from apps.core.models import MailEinstellungen, TafelEinstellungen

    settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
    e = MailEinstellungen.laden()
    e.server, e.absender = "smtp.example.org", "absender@example.org"
    e.save()
    t = TafelEinstellungen.laden()
    t.email = "verwaltung@example.org"
    t.save()


def test_nachricht_an_die_verwaltung_mit_antwort(lage, admin_client, mailserver,
                                                django_capture_on_commit_callbacks):  # fmt: skip
    from django.core import mail as django_mail

    from apps.kunden.models import StellenNachricht

    c, mitte = lage
    # ohne gewählte Ausgabestelle (Admin): nur ein Hinweis, nichts gespeichert
    assert "Ausgabestelle wählen" in admin_client.get(AN_VERWALTUNG).content.decode()
    admin_client.post(AN_VERWALTUNG, {"betreff": "x", "text": "y"})
    assert not StellenNachricht.objects.exists()
    start = c.get("/").content.decode()
    assert AN_VERWALTUNG in start and "Nachricht an die Verwaltung" in start
    # leer: Fehler am Feld
    leer = c.post(AN_VERWALTUNG, {"betreff": "", "text": ""})
    assert set(leer.context["form"].errors) == {"betreff", "text"}
    with django_capture_on_commit_callbacks(execute=True):
        antwort = c.post(AN_VERWALTUNG, {"betreff": "Kühlschrank", "text": "Tür schließt nicht."})
    assert antwort.url == AN_VERWALTUNG
    n = StellenNachricht.objects.get()
    assert (n.stelle, n.von, n.betreff) == (mitte, "anton", "Kühlschrank")
    gesendet = django_mail.outbox[-1]
    assert gesendet.to == ["verwaltung@example.org"]
    assert "Mitte" in gesendet.subject and "Tür schließt nicht." in gesendet.body
    assert "/kunden/nachrichten/?anliegen=allgemein" in gesendet.body
    assert "Tür schließt nicht." in c.get(AN_VERWALTUNG).content.decode()
    # Verwaltung: Startseite, Menüzahl, Reiter, Antwort
    assert "1 × ohne Kunde" in admin_client.get("/").content.decode()
    seite = admin_client.get(reverse("kunden:nachrichten")).content.decode()
    assert "Kühlschrank" in seite and "Ohne Kunde: offen (1)" in seite
    nur = admin_client.get(reverse("kunden:nachrichten"), {"anliegen": "allgemein"})
    assert "Kühlschrank" in nur.content.decode() and "Zu Kunden" not in nur.content.decode()
    antwort = {"stellen_nachricht": n.pk, "antwort": "Hausmeister kommt Freitag."}
    admin_client.post(reverse("kunden:nachrichten"), antwort)
    n.refresh_from_db()
    assert n.erledigt_am and n.antwort == "Hausmeister kommt Freitag." and n.antwort_von == "chefin"
    # Ausgabestelle: Antwort auf der Startseite bis „gelesen“
    assert "Hausmeister kommt Freitag." in c.get("/").content.decode()
    gelesen = reverse("kunden:antwort_gelesen", args=[n.pk])
    assert c.post(gelesen, {"zurueck": "https://boese.example/"}).url == "/"
    n.refresh_from_db()
    assert n.gelesen_am and n.gelesen_von == "anton"
    assert "Hausmeister kommt Freitag." not in c.get("/").content.decode()
    assert c.post(gelesen).status_code == 404  # schon gelesen
    # die Ausgabestelle darf die Liste nicht lesen und nicht antworten
    assert c.get(reverse("kunden:nachrichten")).status_code == 403


def test_verwaltung_erledigt_ohne_antwort_und_frist(lage, admin_client):
    from apps.kunden.models import StellenNachricht

    _, mitte = lage
    n = StellenNachricht.objects.create(stelle=mitte, von="anton", betreff="Info", text="Nur so")
    url = reverse("kunden:nachrichten")
    assert admin_client.post(url, {"stellen_nachricht": n.pk}).url == f"{url}?anliegen=allgemein"
    n.refresh_from_db()
    assert n.erledigt_am and not n.antwort
    assert "✓ erledigt" in admin_client.get(url, {"anliegen": "allgemein"}).content.decode()
    admin_client.post(url, {"stellen_nachricht": n.pk})
    n.refresh_from_db()
    assert n.erledigt_am is None
    assert admin_client.post(url, {"stellen_nachricht": "abc"}).status_code == 404
    n.erledigt_am = timezone.now() - dt.timedelta(days=91)
    n.save()
    assert alte_nachrichten_loeschen() == 1 and not StellenNachricht.objects.exists()


def test_benachrichtigung_an_gewaehlte_und_entfaellt_wenn_erledigt(lage, mailserver):
    from django.contrib.auth import get_user_model

    from apps.core import benachrichtigung
    from apps.core.models import MailEmpfaenger
    from apps.kunden import an_verwaltung

    _, mitte = lage
    chefin = get_user_model().objects.get(username="chefin")
    chefin.email = "chefin@example.org"
    chefin.save()
    art = benachrichtigung.arten()["nachricht_verwaltung"]
    assert [k.username for k in art.wahl.berechtigte()] == ["chefin"]
    # Häkchen bei der Chefin, „wie vorgesehen“ (Tafel-Mail) aus: nur die Chefin
    eintrag = MailEmpfaenger.objects.create(art="nachricht_verwaltung", vorgabe=False)
    eintrag.personen.set([chefin])
    assert benachrichtigung.an("nachricht_verwaltung", ["verwaltung@example.org"]) == [
        "chefin@example.org"
    ]
    n = an_verwaltung.schreiben(mitte, chefin, "Betreff", "Text")
    assert an_verwaltung.offen(str(n.pk)) and not an_verwaltung.offen("")
    an_verwaltung.umschalten(n, chefin)
    assert not an_verwaltung.offen(str(n.pk))
    assert not an_verwaltung.antworten_offen(None).exists()
    assert not an_verwaltung.von_stelle(None).exists()


def test_nachricht_an_die_verwaltung_in_der_auskunft(lage, pdf_text):
    from apps.kunden import an_verwaltung

    c, mitte = lage
    anton = c.get("/").wsgi_request.user
    an_verwaltung.schreiben(mitte, anton, "Schlüssel", "Wer hat den Schlüssel?")
    text = pdf_text(c.get(reverse("konten:meine_auskunft")))
    assert "Nachrichten an die Verwaltung" in text and "Wer hat den" in text
