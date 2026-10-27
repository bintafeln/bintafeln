"""Modul Aufruf (ADR 0049, 0050): Modulschalter, Reihenfolge aus dem Kundenstamm, Seiten."""

import datetime as dt
import json

import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.aufruf import ablauf
from apps.aufruf.models import AufrufEinstellungen, AufrufInfo, AufrufTag
from apps.ausgabe.ampel import WOCHENTAGE
from apps.core import datensicherung, hilfe, module
from apps.core.models import TafelEinstellungen
from apps.konten import rechte, rollen
from apps.kunden.models import (
    Abholung,
    Ausgabestelle,
    Haushalt,
    Kundengruppe,
    Person,
    Zusatzfeld,
)

pytestmark = pytest.mark.django_db


def heute():
    return timezone.localdate()


def kuerzel(tag=None):
    return WOCHENTAGE[(tag or heute()).weekday()]


@pytest.fixture
def modul_an(admin):
    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()


@pytest.fixture
def mitte():
    return Ausgabestelle.objects.create(name="Mitte")


def gruppe(stelle, name, uhrzeit, tage=None):
    return Kundengruppe.objects.create(
        name=name, ausgabestelle=stelle, wochentage=tage if tage is not None else kuerzel(),
        uhrzeit=dt.time(*uhrzeit),
    )  # fmt: skip


def haushalte(g, *nummern, status=Haushalt.Status.AKTIV):
    for n in nummern:
        h = Haushalt.objects.create(kundennummer=n, kundengruppe=g, status=status)
        Person.objects.create(haushalt=h, ist_hauptperson=True, vorname="Erika", nachname="Muster")


@pytest.fixture
def tag_daten(mitte):
    """Zwei Gruppen heute (12:00 mit 5, 13:00 mit 4 Haushalten), eine an einem anderen Tag."""
    frueh = gruppe(mitte, "Früh", (12, 0))
    spaet = gruppe(mitte, "Spät", (13, 0))
    anders = gruppe(mitte, "Anders", (12, 0), tage=WOCHENTAGE[(heute().weekday() + 1) % 7])
    haushalte(frueh, "101", "102", "103", "104", "105")
    haushalte(spaet, "201", "202", "203", "204")
    haushalte(anders, "301")
    haushalte(frueh, "199", status=Haushalt.Status.GESPERRT)
    return frueh, spaet


# ── Modulschalter ────────────────────────────────────────────────────────────


def test_modul_aus_ist_unsichtbar(admin_client):
    assert module.aktiv("aufruf") is False
    assert admin_client.get(reverse("aufruf:start")).status_code == 404
    assert admin_client.get(reverse("aufruf:einstellungen")).status_code == 404
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert "aufruf-leiste" not in seite
    assert "aufruf.steuern" in rechte.ALLE  # im Katalog, aber nicht in der Rollenverwaltung
    assert all(r.code != "aufruf.steuern" for _, liste in rechte.bereiche() for r in liste)
    assert 'id="aufruf"' not in admin_client.get(reverse("core:hilfe")).content.decode()


def test_modul_einschalten_in_den_tafel_einstellungen(admin_client):
    seite = admin_client.get(reverse("core:einstellungen")).content.decode()
    assert "Zusätzliche Module" in seite and "Aufruf –" in seite
    antwort = admin_client.post(reverse("core:einstellungen"), {
        "name": "Tafel Musterstadt", "farbe": "#e5007d", "hintergrund_staerke": 15,
        "module": ["aufruf"],
    })  # fmt: skip
    assert antwort.status_code == 302
    assert TafelEinstellungen.laden().module == ["aufruf"]
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert reverse("aufruf:leiste") in seite and "Aufruf, Monitor und Kiosk" in seite
    assert any(r.code == "aufruf.steuern" for _, liste in rechte.bereiche() for r in liste)
    assert 'id="aufruf"' in admin_client.get(reverse("core:hilfe")).content.decode()


def test_rechte_ausgeschalteter_module_bleiben_beim_speichern_der_rolle(admin_client):
    from apps.konten.models import Rolle

    rolle = Rolle.objects.get(gruppe__name=rollen.AUSGABE)
    assert "aufruf.steuern" in rolle.rechte  # Datenmigration
    antwort = admin_client.post(reverse("konten:rolle", args=[rolle.pk]), {
        "name": rolle.name, "beschreibung": "", "reihenfolge": rolle.reihenfolge,
        "rechte": ["einlass.nutzen"],
    })  # fmt: skip
    assert antwort.status_code == 302
    rolle.refresh_from_db()
    assert "aufruf.steuern" in rolle.rechte


def test_handbuch_kapitel_und_datensicherung():
    kennungen = [k.kennung for k in hilfe.alle_kapitel()]
    assert "aufruf" in kennungen and len(kennungen) == len(set(kennungen))
    assert "aufruf" in datensicherung.EIGENE_APPS
    assert "aufruf.aufruftag" in datensicherung.AUSGENOMMEN
    assert AufrufEinstellungen in datensicherung.modelle("kunden")


# ── Reihenfolge ──────────────────────────────────────────────────────────────


def test_neuer_stand_nur_heutige_gruppen_aktive_haushalte(mitte, tag_daten):
    e = AufrufEinstellungen.laden(mitte)
    s = ablauf.neuer_stand(mitte, heute(), e)
    assert [g["name"] for g in s["gruppen"]] == ["Früh", "Spät"]
    assert sorted(s["gruppen"][0]["wartend"]) == ["101", "102", "103", "104", "105"]
    assert sorted(s["gruppen"][1]["wartend"]) == ["201", "202", "203", "204"]


def test_vorrang_zuerst(mitte, tag_daten):
    feld = Zusatzfeld.objects.create(schluessel="schwerbehindert", bezeichnung="Schwerbehindert",
                                     typ=Zusatzfeld.Typ.JA_NEIN)  # fmt: skip
    for n in ("104", "105"):
        p = Haushalt.objects.get(kundennummer=n).personen.get()
        p.zusatz = {"schwerbehindert": True}
        p.save()
    e = AufrufEinstellungen.laden(mitte)
    e.vorrang_feld = feld
    e.save()
    s = ablauf.neuer_stand(mitte, heute(), e)
    assert set(s["gruppen"][0]["wartend"][:2]) == {"104", "105"}
    tag = ablauf.starten(mitte, heute())
    d = ablauf.stand_fuer_anzeige(tag, e, heute())
    assert d["priority_flags"][:2] == [True, True] and d["priority_flags"][2] is False
    e.vorrang_symbol = False
    e.save()
    assert ablauf.stand_fuer_anzeige(tag, e, heute())["priority_flags"] == [False] * 3


def test_ablauf_starten_weiter_zurueck_fertig(mitte, tag_daten):
    e = AufrufEinstellungen.laden(mitte)
    with pytest.raises(ablauf.AufrufFehler):
        ablauf.weiter(mitte, heute())
    tag = ablauf.starten(mitte, heute())
    d = ablauf.stand_fuer_anzeige(tag, e, heute())
    erste = d["current_numbers"]
    assert len(erste) == 3 and d["current_slot"] == "Früh (12:00)" and d["total_numbers"] == 9
    tag = ablauf.weiter(mitte, heute())
    d = ablauf.stand_fuer_anzeige(tag, e, heute())
    assert len(d["current_numbers"]) == 2 and d["past_numbers"] == erste
    assert d["can_undo"] and d["total_completed"] == 3
    tag = ablauf.zurueck(mitte, heute())
    assert ablauf.stand_fuer_anzeige(tag, e, heute())["current_numbers"] == erste
    for _ in range(2):
        tag = ablauf.weiter(mitte, heute())
    d = ablauf.stand_fuer_anzeige(tag, e, heute())
    assert d["current_slot"] == "Spät (13:00)" and d["slot_index"] == 2
    for _ in range(2):
        tag = ablauf.weiter(mitte, heute())
    d = ablauf.stand_fuer_anzeige(tag, e, heute())
    assert d["finished"] and d["total_completed"] == 9
    tag = ablauf.zurueck(mitte, heute())  # auch der letzte Schritt lässt sich zurücknehmen
    assert not ablauf.stand_fuer_anzeige(tag, e, heute())["finished"]


def test_anzahl_einstellbar(mitte, tag_daten):
    e = AufrufEinstellungen.laden(mitte)
    e.anzahl = 2
    e.save()
    tag = ablauf.starten(mitte, heute())
    assert len(ablauf.stand_fuer_anzeige(tag, e, heute())["current_numbers"]) == 2


def test_schon_eingelassene_fallen_heraus(mitte, tag_daten):
    tag = ablauf.starten(mitte, heute())
    wartend = tag.stand["gruppen"][0]["wartend"]
    aktuell, spaeter = wartend[0], wartend[4]
    for n in (aktuell, spaeter, "203"):
        Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer=n), datum=heute())
    # Gerade aufgerufen und schon am Einlass: sofort aus „Bitte eintreten“, Platz bleibt leer
    e = AufrufEinstellungen.laden(mitte)
    d = ablauf.stand_fuer_anzeige(tag, e, heute())
    assert d["current_numbers"] == wartend[1:3] and len(d["priority_flags"]) == 2
    assert wartend[3] not in d["current_numbers"]  # niemand wird nachgerufen
    tag = ablauf.weiter(mitte, heute())
    g = tag.stand["gruppen"]
    assert aktuell in g[0]["aufgerufen"]  # war schon aufgerufen: bleibt bei den Erledigten
    assert spaeter in g[0]["eingelassen"] and spaeter not in g[0]["wartend"]
    assert "203" in g[1]["eingelassen"] and "203" not in g[1]["wartend"]
    assert ablauf.abfrage(mitte, heute(), "203")["schon_dran"] is True


def test_eingelassene_bleiben_wenn_ausgeschaltet(mitte, tag_daten):
    e = AufrufEinstellungen.laden(mitte)
    e.eingelassene_ausblenden = False
    e.save()
    Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer="203"), datum=heute())
    tag = ablauf.starten(mitte, heute())
    assert "203" in tag.stand["gruppen"][1]["wartend"]
    erster = tag.stand["gruppen"][0]["wartend"][0]
    Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer=erster), datum=heute())
    assert erster in ablauf.stand_fuer_anzeige(tag, e, heute())["current_numbers"]


def test_abgleich_mit_dem_kundenstamm(mitte, tag_daten):
    frueh, spaet = tag_daten
    tag = ablauf.starten(mitte, heute())
    aktuell = tag.stand["gruppen"][0]["wartend"][:3]
    weg = tag.stand["gruppen"][0]["wartend"][0]  # gerade aufgerufen: bleibt sichtbar
    Haushalt.objects.filter(kundennummer__in=[weg, "202"]).update(status=Haushalt.Status.BEENDET)
    haushalte(frueh, "106", "107")
    tag = ablauf.aktualisieren(mitte, heute())  # noch nicht: höchstens alle 20 Sekunden
    assert "106" not in tag.stand["gruppen"][0]["wartend"]
    tag.stand["abgeglichen"] = "2000-01-01T00:00:00+00:00"
    tag.save()
    tag = ablauf.aktualisieren(mitte, heute())
    g = tag.stand["gruppen"]
    assert g[0]["wartend"][:3] == aktuell
    assert {"106", "107"} <= set(g[0]["wartend"][3:])
    assert "202" not in g[1]["wartend"]


def test_neu_mischen(mitte, tag_daten):
    ablauf.starten(mitte, heute())
    ablauf.weiter(mitte, heute())
    tag = ablauf.neu_mischen(mitte, heute())
    assert tag.stand["rueckgaengig"] == [] and len(tag.stand["gruppen"][0]["wartend"]) == 5


def test_spaetzuender(mitte, tag_daten):
    e = AufrufEinstellungen.laden(mitte)
    e.spaetzuender_versatz = 4
    e.save()
    tag = ablauf.starten(mitte, heute())
    zuerst = tag.stand["gruppen"][0]["wartend"][0]
    with pytest.raises(ablauf.AufrufFehler):
        ablauf.spaetzuender(mitte, heute(), zuerst)  # noch nicht aufgerufen
    ablauf.weiter(mitte, heute())
    ergebnis = ablauf.spaetzuender(mitte, heute(), zuerst)
    assert ergebnis["bereits"] is False and ergebnis["vor_der_nummer"] == 4
    a = ablauf.abfrage(mitte, heute(), zuerst)
    assert a["neu_einsortiert"] is True and a["vor_der_nummer"] == 4
    assert ablauf.spaetzuender(mitte, heute(), zuerst)["bereits"] is True
    # „Zurück“ holt ihn nicht an den alten Platz zurück (sonst stünde er doppelt da)
    tag = ablauf.zurueck(mitte, heute())
    alle = [x for g in tag.stand["gruppen"] for x in g["wartend"] + g["aufgerufen"]]
    assert alle.count(zuerst) == 1
    zeile = next(z for z in ablauf.reihenfolge(tag) if z["nummer"] == zuerst)
    assert "zu spät" in zeile["anmerkung"]


def test_abgeholte_nicht_neu_einsortieren(mitte, tag_daten):
    tag = ablauf.starten(mitte, heute())
    erster, eingelassen = tag.stand["gruppen"][0]["wartend"][0], "203"
    ablauf.weiter(mitte, heute())
    for n, uhr in ((erster, dt.time(13, 41)), (eingelassen, None)):
        Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer=n), datum=heute(),
                                uhrzeit=uhr)  # fmt: skip
    a = ablauf.abfrage(mitte, heute(), erster)
    assert a["abgeholt"] is True and a["abgeholt_um"] == "13:41" and a["schon_dran"] is True
    with pytest.raises(ablauf.AufrufFehler, match="um 13:41 schon abgeholt"):
        ablauf.spaetzuender(mitte, heute(), erster)
    with pytest.raises(ablauf.AufrufFehler, match="heute schon abgeholt"):
        ablauf.spaetzuender(mitte, heute(), eingelassen)
    ablauf.weiter(mitte, heute())  # 203 wandert zu den Eingelassenen
    b = ablauf.abfrage(mitte, heute(), eingelassen)
    assert b["abgeholt"] is True and b["abgeholt_um"] == "" and b["eingelassen"] is True
    assert "abgeholt" not in ablauf.abfrage(mitte, heute(), "201")


def test_abfrage(mitte, tag_daten):
    Person.objects.filter(haushalt__kundennummer="201").update(staatsangehoerigkeit="Syrien")
    vorab = ablauf.abfrage(mitte, heute(), "201")
    assert vorab["vorschau"] is True and vorab["gefunden"] and vorab["sprache"] == "ar"
    platz = vorab["gesamt_platz"]
    tag = ablauf.starten(mitte, heute())  # die vorab genannte Reihenfolge bleibt
    assert ablauf.abfrage(mitte, heute(), "201")["gesamt_platz"] == platz
    erster = tag.stand["gruppen"][0]["wartend"][0]
    a = ablauf.abfrage(mitte, heute(), erster)
    assert a["schon_dran"] is False and a["vor_der_nummer"] == 0
    ablauf.weiter(mitte, heute())
    assert ablauf.abfrage(mitte, heute(), erster)["schon_dran"] is True
    assert ablauf.abfrage(mitte, heute(), "301")["gefunden"] is False
    assert ablauf.abfrage(mitte, heute(), " 0201 ")["nummer"] == "201"


def test_keine_gruppe_heute(mitte):
    assert ablauf.abfrage(mitte, heute(), "1")["active"] is False
    with pytest.raises(ablauf.AufrufFehler, match="keine Kundengruppe"):
        ablauf.starten(mitte, heute())


def test_probelauf_als_wochentag(mitte):
    morgen = (heute().weekday() + 1) % 7
    haushalte(gruppe(mitte, "Morgen", (10, 0), tage=WOCHENTAGE[morgen]), "501")
    e = AufrufEinstellungen.laden(mitte)
    e.wochentag_probe = morgen
    e.save()
    tag = ablauf.starten(mitte, heute())
    assert tag.stand["gruppen"][0]["wartend"] == ["501"]


def test_alte_tage_werden_geloescht(mitte, tag_daten):
    alt = AufrufTag.objects.create(ausgabestelle=mitte, datum=heute() - dt.timedelta(days=40))
    ablauf.starten(mitte, heute())
    assert not AufrufTag.objects.filter(pk=alt.pk).exists()


def test_sprachen():
    from apps.aufruf.sprachen import sprachcode

    assert sprachcode("Ukraine") == "uk" and sprachcode("Arabische Republik Syrien") == "ar"
    assert sprachcode("Deutschland") == "de" and sprachcode("") is None
    assert sprachcode("Atlantis") is None


# ── Seiten mit Anmeldung ─────────────────────────────────────────────────────


def test_steuerung_ablauf_ueber_die_seiten(modul_an, admin_client, mitte, tag_daten):
    url = reverse("aufruf:steuerung", args=[mitte.pk])
    assert admin_client.get(reverse("aufruf:start")).url == url  # nur eine Ausgabestelle
    seite = admin_client.get(url).content.decode()
    assert "Ausgabe starten" in seite and "2 Kundengruppen" in seite
    admin_client.post(reverse("aufruf:starten", args=[mitte.pk]))
    seite = admin_client.get(url).content.decode()
    assert "Weiter zu den nächsten Kundennummern" in seite and "Früh (12:00)" in seite
    admin_client.post(reverse("aufruf:weiter", args=[mitte.pk]))
    admin_client.post(reverse("aufruf:zurueck", args=[mitte.pk]))
    for _ in range(4):
        admin_client.post(reverse("aufruf:weiter", args=[mitte.pk]))
    assert "abgeschlossen" in admin_client.get(url).content.decode()
    csv = admin_client.get(reverse("aufruf:liste", args=[mitte.pk])).content.decode("utf-8-sig")
    assert csv.startswith("Platz gesamt;Kundengruppe") and "101" in csv and "Erika" not in csv


def test_api_wie_bisher(modul_an, admin_client, mitte, tag_daten):
    def post(name, **daten):
        return admin_client.post(
            reverse(f"aufruf:{name}", args=[mitte.pk]),
            json.dumps(daten),
            content_type="application/json",
        ).json()

    status = admin_client.get(reverse("aufruf:api_status", args=[mitte.pk])).json()
    assert status["has_active_session"] is False and status["available_days"]
    stand = admin_client.get(reverse("aufruf:api_stand", args=[mitte.pk])).json()
    assert "error" in stand
    assert post("api_starten")["success"] is True
    d = post("api_weiter")
    assert d["success"] and d["message"] == "3 Kundennummer(n) bearbeitet" and d["can_undo"]
    assert len(d["current_numbers"]) == 2 and "upcoming_numbers" in d
    erste = admin_client.get(reverse("aufruf:api_stand", args=[mitte.pk])).json()["past_numbers"]
    s = post("api_spaetzuender", nummer=erste[0])
    assert s["success"] and s["versatz"] == 30
    assert post("api_spaetzuender")["success"] is False
    abfrage = admin_client.get(reverse("aufruf:api_abfrage", args=[mitte.pk]),
                               {"nummer": erste[1]}).json()  # fmt: skip
    assert abfrage["schon_dran"] is True
    assert post("api_zurueck")["success"] is True


def test_mobil_und_steuerung_seiten(modul_an, admin_client, mitte, tag_daten):
    ablauf.starten(mitte, heute())
    seite = admin_client.get(reverse("aufruf:mobil", args=[mitte.pk])).content.decode()
    assert "Aktuelle Kunden" in seite and "const SPAET_VERSATZ = 30;" in seite
    assert reverse("aufruf:api_weiter", args=[mitte.pk]) in seite


def test_nur_eigene_ausgabestelle(modul_an, client, anmelden, benutzer_mit_rolle, mitte, tag_daten):
    andere = Ausgabestelle.objects.create(name="Nord")
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    anton.ausgabestellen.add(mitte)
    anmelden(client, anton)
    assert client.get(reverse("aufruf:steuerung", args=[mitte.pk])).status_code == 200
    assert client.get(reverse("aufruf:steuerung", args=[andere.pk])).status_code == 403
    assert client.get(reverse("aufruf:einstellungen")).status_code == 403


# ── Anzeige-Geräte ohne Anmeldung ────────────────────────────────────────────


def test_anzeige_nur_mit_schluessel(modul_an, mitte, tag_daten):
    e = AufrufEinstellungen.laden(mitte)
    c = Client()
    assert c.get(reverse("aufruf:monitor", args=["falsch"])).status_code == 404
    seite = c.get(reverse("aufruf:monitor", args=[e.schluessel])).content.decode()
    assert "Ausgabe hat noch nicht begonnen" in seite
    assert "error" in c.get(reverse("aufruf:anzeige_stand", args=[e.schluessel])).json()
    ablauf.starten(mitte, heute())
    seite = c.get(reverse("aufruf:monitor", args=[e.schluessel])).content.decode()
    assert "Bitte eintreten" in seite and "--info-display-width: 45%" in seite
    assert "Erika" not in seite
    d = c.get(reverse("aufruf:anzeige_stand", args=[e.schluessel])).json()
    assert len(d["current_numbers"]) == 3 and d["infos"] == []
    for name in ("anzeige", "kiosk", "abfrage"):
        assert c.get(reverse(f"aufruf:{name}", args=[e.schluessel])).status_code == 200
    kiosk = c.get(reverse("aufruf:kiosk", args=[e.schluessel])).content.decode()
    assert "Mitte" in kiosk and "Frohnhauser" not in kiosk
    a = c.get(reverse("aufruf:anzeige_abfrage", args=[e.schluessel]), {"nummer": "201"}).json()
    assert a["gefunden"] is True
    Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer="201"), datum=heute(),
                            uhrzeit=dt.time(9, 5))  # fmt: skip
    a = c.get(reverse("aufruf:anzeige_abfrage", args=[e.schluessel]), {"nummer": "201"}).json()
    assert a["abgeholt"] is True and "abgeholt_um" not in a  # ohne Anmeldung keine Uhrzeit
    while not ablauf.stand_fuer_anzeige(ablauf.weiter(mitte, heute()), e, heute())["finished"]:
        pass
    seite = c.get(reverse("aufruf:monitor", args=[e.schluessel])).content.decode()
    assert "abgeschlossen" in seite.lower()


def test_anzeige_aus_wenn_modul_aus(admin, mitte):
    e = AufrufEinstellungen.laden(mitte)
    assert Client().get(reverse("aufruf:monitor", args=[e.schluessel])).status_code == 404


def test_layout_vom_monitor(modul_an, mitte):
    e = AufrufEinstellungen.laden(mitte)
    c = Client(enforce_csrf_checks=False)
    url = reverse("aufruf:anzeige_layout", args=[e.schluessel])
    antwort = c.post(url, json.dumps({"nextCustomers": 20, "currentNumbers": 40, "infoDisplay": 60,
                                      "currentNumbersFont": 99, "headerFont": "x"}),
                     content_type="application/json").json()  # fmt: skip
    assert antwort["success"]
    layout = antwort["layout"]
    assert layout["nextCustomers"] + layout["currentNumbers"] + layout["infoDisplay"] == 100
    assert layout["currentNumbersFont"] == 15.0 and layout["headerFont"] == 2.8
    e.refresh_from_db()
    assert e.layout_werte()["current_numbers_font"] == 15.0
    assert c.post(url, "kaputt", content_type="application/json").status_code == 400


def test_infos_auf_dem_monitor(modul_an, admin_client, mitte, tag_daten):
    e = AufrufEinstellungen.laden(mitte)
    nord = Ausgabestelle.objects.create(name="Nord")
    antwort = admin_client.post(reverse("aufruf:info_neu"), {
        "titel": "Öffnungszeiten", "art": "text", "text": "Montag bis Freitag", "dauer": 10,
        "reihenfolge": 1, "aktiv": "on",
    })  # fmt: skip
    assert antwort.status_code == 302
    bild = SimpleUploadedFile("bild.png", b"\x89PNG\r\n\x1a\n" + b"0" * 20, "image/png")
    admin_client.post(reverse("aufruf:info_neu"), {
        "titel": "Bild", "art": "bild", "datei": bild, "dauer": 5, "reihenfolge": 2, "aktiv": "on",
    })  # fmt: skip
    fehler = admin_client.post(reverse("aufruf:info_neu"), {
        "titel": "Leer", "art": "pdf", "dauer": 5, "reihenfolge": 3, "aktiv": "on",
    })  # fmt: skip
    assert "Bitte ein PDF hochladen." in fehler.content.decode()
    admin_client.post(reverse("aufruf:info_neu"), {
        "titel": "Nur Nord", "art": "text", "text": "x", "dauer": 5, "reihenfolge": 4,
        "aktiv": "on", "ausgabestellen": [nord.pk],
    })  # fmt: skip
    ablauf.starten(mitte, heute())
    c = Client()
    seite = c.get(reverse("aufruf:monitor", args=[e.schluessel])).content.decode()
    assert "Montag bis Freitag" in seite and "Nur Nord" not in seite
    info = AufrufInfo.objects.get(titel="Bild")
    datei = c.get(reverse("aufruf:anzeige_datei", args=[e.schluessel, info.pk]))
    assert datei.status_code == 200 and datei["X-Frame-Options"] == "SAMEORIGIN"
    nord_e = AufrufEinstellungen.laden(nord)
    url = reverse("aufruf:anzeige_datei", args=[nord_e.schluessel, info.pk])
    assert c.get(url).status_code == 200
    nur_nord = AufrufInfo.objects.get(titel="Nur Nord")
    url = reverse("aufruf:anzeige_datei", args=[e.schluessel, nur_nord.pk])
    assert c.get(url).status_code == 404
    assert len(c.get(reverse("aufruf:anzeige_stand", args=[e.schluessel])).json()["infos"]) == 2
    admin_client.post(reverse("aufruf:info_loeschen", args=[info.pk]))
    assert not AufrufInfo.objects.filter(pk=info.pk).exists()


def test_einstellungen_und_neue_links(modul_an, admin_client, mitte):
    e = AufrufEinstellungen.laden(mitte)
    seite = admin_client.get(reverse("aufruf:einstellungen")).content.decode()
    assert reverse("aufruf:monitor", args=[e.schluessel]) in seite
    antwort = admin_client.post(reverse("aufruf:einstellungen_stelle", args=[mitte.pk]), {
        "aktiv": "on", "anzahl": 4, "spaetzuender_versatz": 20, "vorrang_symbol": "on",
        "info_rotation": "on",
        "eingelassene_ausblenden": "on", "wochentag_probe": "", "zu_spaet_minuten": 15,
    })  # fmt: skip
    assert antwort.status_code == 302
    e.refresh_from_db()
    assert (e.anzahl, e.spaetzuender_versatz) == (4, 20)
    alt = e.schluessel
    admin_client.post(reverse("aufruf:schluessel_neu", args=[mitte.pk]))
    e.refresh_from_db()
    assert e.schluessel != alt
    assert Client().get(reverse("aufruf:monitor", args=[alt])).status_code == 404


# ── Hinweis am Einlass ───────────────────────────────────────────────────────


def test_einlass_hinweise(mitte, tag_daten):
    h = Haushalt.objects.get(kundennummer="201")
    assert ablauf.einlass(h, heute()) == []  # Aufruf nicht gestartet
    tag = ablauf.starten(mitte, heute())
    erster = Haushalt.objects.get(kundennummer=tag.stand["gruppen"][0]["wartend"][0])
    assert "Gerade aufgerufen" in ablauf.einlass(erster, heute())[0]["text"]
    hinweis = ablauf.einlass(h, heute())[0]
    assert hinweis["farbe"] == "gelb" and hinweis["text"].startswith("Noch nicht aufgerufen: ")
    assert hinweis["text"].endswith("zu früh") and "Kundengruppe" not in hinweis["text"]
    assert hinweis["ampel"] == "Kunde ist zu früh (Aufruf)" and hinweis["wort"] == "ZU FRÜH"
    ablauf.weiter(mitte, heute())
    hinweis = ablauf.einlass(erster, heute())[0]
    assert hinweis["farbe"] == "gruen" and hinweis["text"].startswith("Aufgerufen um")
    # 20 Minuten später: zu spät (Vorgabe 15 Minuten)
    tag = ablauf.tag_holen(mitte, heute())
    frueher = timezone.now() - dt.timedelta(minutes=20)
    tag.stand["rueckgaengig"][-1]["zeitpunkt"] = frueher.isoformat()
    tag.save()
    hinweis = ablauf.einlass(erster, heute())[0]
    assert (
        hinweis["farbe"] == "rot"
        and "Zu spät" in hinweis["text"]
        and "20 Minuten" in hinweis["text"]
    )
    assert hinweis["knopf"]["text"] == "30 Nummern verschieben"  # Vorgabe 30 Plätze
    assert hinweis["wort"] == "ZU SPÄT"  # grüne Ampel, Gelb blinkt dazu
    assert "30 wartende Nummern" in hinweis["knopf"]["erklaerung"]
    e = AufrufEinstellungen.laden(mitte)
    e.zu_spaet_minuten = 0
    e.save()
    assert ablauf.einlass(erster, heute())[0]["farbe"] == "gruen"
    ablauf.spaetzuender(mitte, heute(), erster.kundennummer)
    assert "neu einsortiert" in ablauf.einlass(erster, heute())[0]["text"]
    assert ablauf.einlass(erster, heute())[0]["wort"] == "ZU FRÜH"
    fremd = Haushalt.objects.get(kundennummer="301")
    assert ablauf.einlass(fremd, heute())[0]["text"] == "Nicht in der heutigen Aufruf-Liste"


def test_einlass_karte_zeigt_aufruf(modul_an, admin_client, mitte, tag_daten):
    ablauf.starten(mitte, heute())
    seite = admin_client.get(reverse("ausgabe:empfang"), {"nummer": "201"}).content.decode()
    assert "Aufruf:</strong> Noch nicht aufgerufen" in seite
    assert "ampel-blinkt" in seite and "ZU FRÜH" in seite  # Grün leuchtet, Gelb blinkt dazu
    assert "lampe lampe-gelb an" in seite
    assert "Kunde ist zu früh (Aufruf)" in seite and "Abholung möglich" in seite
    assert "Abholung eintragen" in seite
    t = TafelEinstellungen.laden()
    t.module = []
    t.save()
    seite = admin_client.get(reverse("ausgabe:empfang"), {"nummer": "201"}).content.decode()
    assert "Noch nicht aufgerufen" not in seite


def test_steuerung_ueber_die_leiste_im_neuen_tab(modul_an, admin_client):
    """Kein eigener Menüeintrag mehr: Der Kasten „Aufruf“ unter dem Menü führt zur Steuerung."""
    seite = admin_client.get(reverse("aufruf:leiste")).content.decode()
    link = f'href="{reverse("aufruf:start")}"'
    stelle = seite.index(link)
    assert 'target="_blank"' in seite[stelle : stelle + 200]
    assert "oben im Menü die Ausgabestelle wählen" in seite


def test_zurueckgenommene_abholung_kommt_an_alten_platz(mitte, tag_daten):
    from apps.ausgabe import korrekturen

    tag = ablauf.starten(mitte, heute())
    wartend = list(tag.stand["gruppen"][0]["wartend"])  # 5 Nummern, 3 werden angezeigt
    versehentlich, danach = wartend[3], wartend[4]
    abholung = Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer=versehentlich),
                                       datum=heute())  # fmt: skip
    spaet_letzter = tag.stand["gruppen"][1]["wartend"][-1]
    letzte = Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer=spaet_letzter),
                                     datum=heute())  # fmt: skip
    tag = ablauf.aktualisieren(mitte, heute())
    tag.stand["abgeglichen"] = "2000-01-01T00:00:00+00:00"
    tag.save()
    tag = ablauf.aktualisieren(mitte, heute())
    g = tag.stand["gruppen"]
    assert versehentlich in g[0]["eingelassen"] and spaet_letzter in g[1]["eingelassen"]
    # Korrekturwunsch genehmigt: Abholungen weg -> beim nächsten Abgleich zurück an den alten Platz
    for a in (abholung, letzte):
        k = korrekturen.beantragen("abholung", a.pk, grund="Versehentlich gebucht", anmerkung="",
                                   von="anton")  # fmt: skip
        korrekturen.entscheiden(k, annehmen=True, von="chefin")
    tag.stand["abgeglichen"] = "2000-01-01T00:00:00+00:00"
    tag.save()
    tag = ablauf.aktualisieren(mitte, heute())
    g = tag.stand["gruppen"]
    assert versehentlich not in g[0]["eingelassen"]
    assert g[0]["wartend"].index(versehentlich) == g[0]["wartend"].index(danach) - 1
    assert g[1]["wartend"][-1] == spaet_letzter  # war die letzte: wieder ans Ende


def test_zurueckgenommen_nachdem_platz_vorbei_ist(mitte, tag_daten):
    e = AufrufEinstellungen.laden(mitte)
    e.anzahl = 1
    e.save()
    tag = ablauf.starten(mitte, heute())
    wartend = list(tag.stand["gruppen"][0]["wartend"])
    x = wartend[2]
    a = Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer=x), datum=heute())
    for _ in range(3):  # 4 Nummern (auch der Nachfolger) sind dran gewesen
        tag = ablauf.weiter(mitte, heute())
    assert x in tag.stand["gruppen"][0]["eingelassen"]
    a.delete()
    tag.stand["abgeglichen"] = "2000-01-01T00:00:00+00:00"
    tag.save()
    tag = ablauf.aktualisieren(mitte, heute())
    g = tag.stand["gruppen"][tag.stand["index"]]
    assert g["wartend"][1] == x  # als nächste nach der gerade angezeigten


def test_zurueckgenommen_wenn_gruppe_oder_tag_schon_fertig(mitte, tag_daten):
    tag = ablauf.starten(mitte, heute())
    x = tag.stand["gruppen"][0]["wartend"][4]
    a = Abholung.objects.create(haushalt=Haushalt.objects.get(kundennummer=x), datum=heute())
    while not ablauf.stand_fuer_anzeige(
        ablauf.weiter(mitte, heute()), AufrufEinstellungen.laden(mitte), heute()
    )["finished"]:
        pass  # fmt: skip
    a.delete()
    tag = ablauf.tag_holen(mitte, heute())
    tag.stand["abgeglichen"] = "2000-01-01T00:00:00+00:00"
    tag.save()
    tag = ablauf.aktualisieren(mitte, heute())
    letzte = tag.stand["gruppen"][-1]
    assert tag.stand["index"] == len(tag.stand["gruppen"]) - 1 and x in letzte["wartend"]


# ── Kurz-Steuerung unter dem Menü ────────────────────────────────────────────


def test_leiste_unter_dem_menue(modul_an, mitte, tag_daten, benutzer_mit_rolle, anmelden):
    konto = benutzer_mit_rolle("anton", rollen.AUSGABE)
    konto.ausgabestellen.set([mitte])
    c = anmelden(Client(), konto)
    url = reverse("aufruf:leiste")
    assert f'hx-get="{url}"' in c.get(reverse("core:start")).content.decode()
    seite = c.get(url).content.decode()
    assert "Heute noch nicht gestartet" in seite and "Aufruf starten" in seite
    seite = c.post(url, {"aktion": "starten"}).content.decode()
    erste = ablauf.tag_holen(mitte, heute()).stand["gruppen"][0]["wartend"][:3]
    assert "Bitte eintreten" in seite and all(f">{n}</span>" in seite for n in erste)
    seite = c.post(url, {"aktion": "weiter"}).content.decode()
    assert f">{erste[0]}</span>" not in seite and "letzten Schritt zurück" in seite
    seite = c.post(url, {"aktion": "zurueck"}).content.decode()
    assert f">{erste[0]}</span>" in seite
    # Unbekannte Aktion ändert nichts; Fehler werden angezeigt
    assert c.post(url, {"aktion": "loeschen"}).status_code == 200
    ablauf.weiter(mitte, heute())
    ablauf.weiter(mitte, heute())
    ablauf.weiter(mitte, heute())
    ablauf.weiter(mitte, heute())
    seite = c.get(url).content.decode()
    assert "Ausgabe beendet" in seite and "Nummern aufgerufen" in seite
    assert "neu starten" in seite and "letzten Schritt zurück" in seite
    assert 'role="alert"' not in seite
    # neu starten: wieder von vorn
    seite = c.post(url, {"aktion": "neustart"}).content.decode()
    assert "Bitte eintreten" in seite and "Ausgabe beendet" not in seite


def test_leiste_fehler_und_ohne_stelle(modul_an, mitte, benutzer_mit_rolle, anmelden):
    konto = benutzer_mit_rolle("anton", rollen.AUSGABE)
    c = anmelden(Client(), konto)
    Ausgabestelle.objects.create(name="Nord")
    url = reverse("aufruf:leiste")
    seite = c.get(url).content.decode()  # keine Stelle gewählt: nur der Weg zur Steuerung
    assert reverse("aufruf:start") in seite and "Bitte eintreten" not in seite
    konto.ausgabestellen.set([mitte])
    seite = c.post(url, {"aktion": "weiter"}).content.decode()  # nicht gestartet
    assert 'role="alert"' in seite and "Aufruf starten" not in seite  # heute keine Gruppen
    t = TafelEinstellungen.laden()
    t.module = []
    t.save()
    assert "aufruf-leiste" not in c.get(reverse("core:start")).content.decode()


def test_einlass_knopf_verschieben(modul_an, mitte, tag_daten, benutzer_mit_rolle, anmelden,
                                   recht_nehmen):  # fmt: skip
    e = AufrufEinstellungen.laden(mitte)
    e.spaetzuender_versatz = 3
    e.save()
    tag = ablauf.starten(mitte, heute())
    erster = tag.stand["gruppen"][0]["wartend"][0]
    ablauf.weiter(mitte, heute())
    tag = ablauf.tag_holen(mitte, heute())
    frueher = timezone.now() - dt.timedelta(minutes=20)
    tag.stand["rueckgaengig"][-1]["zeitpunkt"] = frueher.isoformat()
    tag.save()
    konto = benutzer_mit_rolle("anton", rollen.AUSGABE)
    konto.ausgabestellen.set([mitte])
    c = anmelden(Client(), konto)
    seite = c.get(reverse("ausgabe:empfang"), {"nummer": erster}).content.decode()
    url = reverse("aufruf:verschieben", args=[mitte.pk, erster])
    assert f'action="{url}"' in seite and "3 Nummern verschieben" in seite
    assert "wartende Nummern hinter den gerade aufgerufenen" in seite  # Erklärung (Maus darüber)
    antwort = c.post(url, follow=True)
    seite = antwort.content.decode()
    assert antwort.redirect_chain[-1][0].endswith(f"?nummer={erster}")
    assert "3 Plätze später einsortiert" in seite and "Nummern zu früh" in seite
    assert "bereits neu einsortiert" in c.post(url, follow=True).content.decode()
    # Fehler (nicht in der Liste) als Meldung; ohne Recht kein Knopf und kein Zugriff
    assert (
        "noch nicht aufgerufen"
        in c.post(
            reverse("aufruf:verschieben", args=[mitte.pk, "999"]), follow=True
        ).content.decode()
    )
    recht_nehmen(rollen.AUSGABE, "aufruf.steuern")
    assert c.post(url).status_code == 403
    seite = c.get(reverse("ausgabe:empfang"), {"nummer": erster}).content.decode()
    assert "Nummern verschieben" not in seite


def test_ausgabestelle_ohne_aufruf(modul_an, admin_client, mitte, tag_daten, benutzer_mit_rolle,
                                   anmelden):  # fmt: skip
    """Nicht jede Ausgabestelle ruft auf: aus = kein Kasten, keine Steuerung, kein Hinweis."""
    tag = ablauf.starten(mitte, heute())
    nummer = tag.stand["gruppen"][0]["wartend"][4]
    admin_client.post(
        reverse("aufruf:einstellungen_stelle", args=[mitte.pk]),
        {
            "anzahl": 3,
            "spaetzuender_versatz": 30,
            "zu_spaet_minuten": 15,
            "wochentag_probe": "",
        },
    )  # fmt: skip  (ohne „aktiv“ = ausgeschaltet)
    assert AufrufEinstellungen.laden(mitte).aktiv is False
    assert (
        "Kein Aufruf an dieser Ausgabestelle"
        in admin_client.get(reverse("aufruf:einstellungen")).content.decode()
    )
    konto = benutzer_mit_rolle("anton", rollen.AUSGABE)
    konto.ausgabestellen.set([mitte])
    c = anmelden(Client(), konto)
    assert c.get(reverse("aufruf:leiste")).content == b""
    assert c.get(reverse("aufruf:steuerung", args=[mitte.pk])).status_code == 403
    assert ablauf.einlass(Haushalt.objects.get(kundennummer=nummer), heute()) == []


def test_einlass_an_stelle_ohne_aufruf_zeigt_nichts(modul_an, admin_client, mitte, tag_daten):
    """Aufruf an der Einlass-Stelle aus: kein „zu früh“, kein Blinken, kein Verschieben – auch
    nicht für Kunden einer anderen Stelle, an der der Aufruf läuft."""
    tag = ablauf.starten(mitte, heute())
    nummer = tag.stand["gruppen"][0]["wartend"][4]
    h = Haushalt.objects.get(kundennummer=nummer)
    nord = Ausgabestelle.objects.create(name="Nord")
    assert ablauf.einlass(h, heute(), nord)  # Aufruf an Nord an: Hinweis von Mitte
    e = AufrufEinstellungen.laden(nord)
    e.aktiv = False
    e.save()
    assert ablauf.einlass(h, heute(), nord) == []
    admin = admin_client.get(reverse("core:start")).wsgi_request.user
    admin.gewaehlte_stelle = nord
    admin.save()
    seite = admin_client.get(reverse("ausgabe:empfang"), {"nummer": nummer}).content.decode()
    assert "Aufruf:" not in seite and "ampel-blinkt" not in seite
    assert "zu früh" not in seite and "Nummern verschieben" not in seite
