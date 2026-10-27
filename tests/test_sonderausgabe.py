"""Außerplanmäßige Ausgabe (ADR 0072). Nur erfundene Daten."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.ausgabe import ampel, ausgabetag
from apps.ausgabe import stelle as stelle_wahl
from apps.ausgabe.forms import SonderausgabeForm
from apps.ausgabe.models import AusgabeEinstellungen, Sonderausgabe
from apps.kunden.models import Ausgabestelle, Haushalt, Kundengruppe, Person

pytestmark = pytest.mark.django_db
MITTWOCH = dt.date(2026, 12, 23)


@pytest.fixture
def stellen():
    mitte, nord = (Ausgabestelle.objects.create(name="Mitte"),
                   Ausgabestelle.objects.create(name="Nord"))  # fmt: skip
    g = {
        "mi": Kundengruppe.objects.create(name="Mi früh", ausgabestelle=mitte, wochentage="Mi"),
        "do": Kundengruppe.objects.create(name="Do früh", ausgabestelle=mitte, wochentage="Do"),
        "do2": Kundengruppe.objects.create(
            name="Do spät", ausgabestelle=mitte, wochentage="Do", uhrzeit=dt.time(14)
        ),  # fmt: skip
        "fr": Kundengruppe.objects.create(name="Fr", ausgabestelle=mitte, wochentage="Fr"),
        "nord": Kundengruppe.objects.create(name="Nord Mo", ausgabestelle=nord, wochentage="Mo"),
    }
    return mitte, nord, g


def haushalt(nummer, gruppe):
    h = Haushalt.objects.create(kundennummer=nummer, kundengruppe=gruppe,
                                ausweis_gueltig_bis=MITTWOCH + dt.timedelta(days=200))  # fmt: skip
    Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname=nummer)
    return h


def sonder(stelle, datum=MITTWOCH, tag="", gruppen=(), anmerkung=""):
    s = Sonderausgabe.objects.create(datum=datum, ausgabestelle=stelle, wie_wochentag=tag,
                                     anmerkung=anmerkung)  # fmt: skip
    s.kundengruppen.set(gruppen)
    return s


def namen(gruppen):
    return [g.name for g in gruppen]


def test_gruppen_am_tag(stellen):
    mitte, nord, g = stellen
    assert namen(ausgabetag.gruppen_am(mitte, MITTWOCH)) == ["Mi früh"]  # regulär
    s = sonder(mitte, tag="Do", gruppen=[g["fr"], g["nord"]])
    # Nur die gewählten: alle Donnerstagsgruppen und die einzelnen, nicht die regulären vom Mi
    assert namen(ausgabetag.gruppen_am(mitte, MITTWOCH)) == ["Do spät", "Do früh", "Fr", "Nord Mo"]
    assert s.wer() == "Kunden vom Donnerstag + Fr + Nord Mo"
    assert ausgabetag.gruppen_am(nord, MITTWOCH) == []  # Nord hat keine Sonderausgabe
    s.wie_wochentag = ""
    s.save()
    assert namen(ausgabetag.gruppen_am(mitte, MITTWOCH)) == ["Fr", "Nord Mo"]
    assert ausgabetag.dran(g["fr"], MITTWOCH, mitte) == (True, s)
    assert ausgabetag.dran(g["mi"], MITTWOCH, mitte) == (False, s)
    assert ausgabetag.dran(g["mi"], MITTWOCH + dt.timedelta(days=7)) == (True, None)


def test_ampel_an_der_sonderausgabe(stellen):
    mitte, _, g = stellen
    e = AusgabeEinstellungen.laden()
    sonder(mitte, tag="Do", gruppen=[g["nord"]])

    def texte(h):
        return [m.text for m in ampel.bewerten(h, MITTWOCH, mitte, e).meldungen]

    assert texte(haushalt("1", g["do"])) == ["Alles in Ordnung"]
    nicht = texte(haushalt("2", g["mi"]))
    assert nicht == ["Heute nicht dran: Sonderausgabe (Kunden vom Donnerstag + Nord Mo), "
                     "Kundengruppe Mi früh ist nicht dabei"]  # fmt: skip
    assert texte(haushalt("3", g["nord"])) == ["Alles in Ordnung"]  # andere Stelle, gewählt
    # Eigene Texte der Tafel gibt es auch für diese Meldung
    e.meldungstexte = {"nicht_dran_sonder": "Nicht dabei: {gruppe}"}
    assert ampel.bewerten(Haushalt.objects.get(kundennummer="2"), MITTWOCH, mitte, e
                          ).meldungen[0].text == "Nicht dabei: Mi früh"  # fmt: skip


def test_fortschritt_und_aufruf(stellen):
    from apps.aufruf import ablauf

    mitte, _, g = stellen
    haushalt("1", g["do"])
    haushalt("2", g["mi"])
    assert stelle_wahl.fortschritt(mitte, MITTWOCH).erwartet == 1  # regulär: Mi
    sonder(mitte, tag="Do", gruppen=[g["fr"]])
    haushalt("3", g["fr"])
    f = stelle_wahl.fortschritt(mitte, MITTWOCH)
    assert (f.erwartet, f.gruppen) == (2, ["Do spät", "Do früh", "Fr"])
    assert namen(ablauf.gruppen_heute(mitte, MITTWOCH)) == ["Do spät", "Do früh", "Fr"]


def test_fortschritt_zaehlt_alle_gruppen_des_tages(stellen):
    """Alle Kundengruppen des Tages zusammen; wer trotzdem abholt (z. B. reguläre Kunden trotz
    Sonderausgabe, Ausnahme, ohne Gruppe), zählt mit – abgeholt ist nie mehr als erwartet."""
    from apps.kunden.models import Abholung, Ausnahme

    mitte, nord, g = stellen
    sonder(mitte, gruppen=[g["fr"], g["do"]])
    fr = [haushalt(f"f{i}", g["fr"]) for i in range(3)]
    do = haushalt("d1", g["do"])
    mi = [haushalt(f"m{i}", g["mi"]) for i in range(2)]  # regulär Mi, heute nicht geplant
    ohne = haushalt("x1", None)
    for h in (fr[0], fr[1], mi[0], ohne):
        Abholung.objects.create(haushalt=h, datum=MITTWOCH, ausgabestelle=mitte)
    Abholung.objects.create(haushalt=do, datum=MITTWOCH, ausgabestelle=nord)  # andere Stelle
    Ausnahme.objects.create(haushalt=mi[0], datum=MITTWOCH)
    f = stelle_wahl.fortschritt(mitte, MITTWOCH)
    assert [(z.name, z.abgeholt, z.erwartet, z.ausnahmen, z.geplant) for z in f.zeilen] == [
        ("Do früh", 0, 1, 0, True),
        ("Fr", 2, 3, 0, True),
        ("Mi früh", 1, 2, 1, False),
        ("ohne Kundengruppe", 1, 1, 0, False),
    ]
    assert (f.abgeholt, f.erwartet, f.ausnahmen, f.offen) == (4, 7, 1, 3)
    assert stelle_wahl.fortschritt(nord, MITTWOCH).zeilen[0].name == "Do früh"  # nur abgeholt
    assert stelle_wahl.fortschritt(nord, MITTWOCH + dt.timedelta(days=1)) is None


def test_formular_und_einstellungen(stellen, admin_client):
    mitte, _, g = stellen
    leer = SonderausgabeForm({"datum": "2026-12-23", "ausgabestelle": mitte.pk})
    assert not leer.is_valid() and "niemand dran" in str(leer.errors)
    url = reverse("kunden:listeneintrag_neu", args=["sonderausgaben"])
    seite = admin_client.get(url).content.decode()
    assert "Kunden vom Wochentag" in seite and "Do früh (Mitte, Do)" in seite
    antwort = admin_client.post(url, {"datum": "2026-12-23", "ausgabestelle": mitte.pk,
                                      "wie_wochentag": "Do", "kundengruppen": [g["fr"].pk],
                                      "anmerkung": "Weihnachten"})  # fmt: skip
    assert antwort.status_code == 302
    s = Sonderausgabe.objects.get()
    assert s.wie_wochentag == "Do" and list(s.kundengruppen.all()) == [g["fr"]]
    liste = admin_client.get(reverse("kunden:liste", args=["sonderausgaben"])).content.decode()
    assert "Kunden vom Donnerstag + Fr" in liste and "Weihnachten" in liste
    doppelt = SonderausgabeForm({"datum": "2026-12-23", "ausgabestelle": mitte.pk,
                                 "wie_wochentag": "Fr"})  # fmt: skip
    assert not doppelt.is_valid()  # je Tag und Ausgabestelle nur eine
    assert "Sonderausgaben" in admin_client.get(reverse("core:start")).content.decode()


def test_einlass_hinweis_und_kundenliste(stellen, admin, admin_client):
    mitte, _, g = stellen
    heute = timezone.localdate()
    admin.gewaehlte_stelle = mitte
    admin.save()
    sonder(mitte, datum=heute, tag="Do", anmerkung="Weihnachtsausgabe")
    seite = admin_client.get(reverse("ausgabe:empfang")).content.decode()
    assert "Heute Sonderausgabe" not in seite  # kein eigener Hinweis mehr (Platz auf dem Handy)
    # Kundenliste startet mit dem Wochentag der Sonderausgabe
    antwort = admin_client.get(reverse("kunden:uebersicht"))
    assert antwort.context["filter"]["tag"] == "Do"
    Sonderausgabe.objects.update(wie_wochentag="")
    Sonderausgabe.objects.get().kundengruppen.set([g["fr"]])
    assert admin_client.get(reverse("kunden:uebersicht")).context["filter"]["tag"] == ""


def test_fortschritt_nennt_die_sonderausgabe(stellen):
    mitte, _, g = stellen
    sonder(mitte, tag="Do", gruppen=[g["fr"]])
    assert stelle_wahl.fortschritt(mitte, MITTWOCH).sonderausgabe == "Kunden vom Donnerstag + Fr"
