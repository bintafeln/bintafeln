"""Menü links: Einstellungen in Untermenüs (Tafel, Kunden, Ausgabe, Verein, …)."""

import pytest
from django.test import RequestFactory
from django.urls import reverse

from apps.core.menue import menue
from apps.core.models import TafelEinstellungen
from apps.konten import rollen

pytestmark = pytest.mark.django_db


def einstellungen(benutzer, pfad="/"):
    anfrage = RequestFactory().get(pfad)
    anfrage.user = benutzer
    return next((b for b in menue(anfrage) if b["titel"] == "Einstellungen"), None)


def titel(bereich):
    return {g["titel"]: [e["titel"] for e in g["eintraege"]] for g in bereich["gruppen"]}


def _team(benutzer):
    anfrage = RequestFactory().get("/")
    anfrage.user = benutzer
    verein = next((b for b in menue(anfrage) if b["titel"] == "Verein"), None)
    return next((g for g in verein["gruppen"] if g["titel"] == "Team"), None)


def test_vertraege_und_zeiten_als_unterpunkt_von_angestellte(admin):
    team = _team(admin)
    # „Verträge & Zeiten“ ist kein eigener Team-Eintrag, sondern Unterpunkt von „Angestellte“.
    assert [e["titel"] for e in team["eintraege"]] == ["Ehrenamtliche", "Angestellte"]
    angestellte = next(e for e in team["eintraege"] if e["titel"] == "Angestellte")
    assert [k["titel"] for k in angestellte.get("kinder", [])] == ["Verträge & Zeiten"]


def test_vertraege_und_zeiten_eigenstaendig_ohne_verwaltung(benutzer_mit_rolle):
    # Rolle Angestellte darf „Verträge & Zeiten“, aber nicht Mitarbeitende verwalten: eigener
    # Eintrag, damit sie überhaupt hinkommt.
    team = _team(benutzer_mit_rolle("hr", rollen.PERSONAL))
    assert [e["titel"] for e in team["eintraege"]] == ["Verträge & Zeiten"]


def test_admin_sieht_alle_untermenues(admin):
    gruppen = titel(einstellungen(admin))
    assert list(gruppen) == ["Tafel", "Kunden", "Ausgabe", "Verein", "Team",
                             "Systemsteuerung"]  # fmt: skip
    assert "Rollen und Rechte" in gruppen["Team"]
    assert "Kundengruppen" in gruppen["Kunden"] and "Sicherungen" in gruppen["Systemsteuerung"]
    assert "Aufruf, Monitor und Kiosk" not in gruppen["Ausgabe"]  # Modul aus


def test_modul_haengt_sich_ins_passende_untermenue(admin):
    t = TafelEinstellungen.laden()
    t.module = ["aufruf"]
    t.save()
    assert "Aufruf, Monitor und Kiosk" in titel(einstellungen(admin))["Ausgabe"]


def test_aktive_seite_oeffnet_ihr_untermenue(admin):
    bereich = einstellungen(admin, reverse("core:protokoll"))
    assert bereich["offen"]
    offen = [g["titel"] for g in bereich["gruppen"] if g["offen"]]
    assert offen == ["Systemsteuerung"]


def test_nur_untermenues_mit_rechten(benutzer_mit_rolle, recht_geben):
    recht_geben(rollen.AUSGABE, "einstellungen.ausgabe")
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    assert list(titel(einstellungen(anton))) == ["Ausgabe"]
    assert einstellungen(benutzer_mit_rolle("berta", rollen.KIOSK)) is None


def test_untermenues_auf_der_seite(admin_client):
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert (
        '<details class="menue-gruppe" name="menue-gruppe">' in seite
        and "<summary>Systemsteuerung</summary>" in seite
    )


def test_nur_ein_bereich_offen(admin_client):
    """Gleicher ``name`` an den <details>: Der Browser schließt beim Öffnen die anderen."""
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert seite.count('name="menue-bereich"') > 3 and 'name="menue-gruppe"' in seite


def alle_bereiche(benutzer, module=()):
    t = TafelEinstellungen.laden()
    t.module = list(module)
    t.save()
    benutzer.__dict__.pop("_bintafeln_rechte", None)  # Rechte hängen an den Modulen
    anfrage = RequestFactory().get("/")
    anfrage.user = benutzer
    return {b["titel"]: b for b in menue(anfrage)}


def test_neue_ordnung_fuer_die_verwaltung(admin):
    """Start, Ausgabestelle, Kunden, Verein, Auswertungen, Einstellungen, Hilfe; Module darin."""
    b = alle_bereiche(admin, ["abrechnung", "wochenuebersicht", "listen", "warteliste"])
    assert list(b) == ["Start", "Ausgabestelle", "Kunden", "Verein", "Auswertungen",
                       "Einstellungen", "Hilfe"]  # fmt: skip
    abschnitte = {a["titel"]: [e["titel"] for e in a["eintraege"]]
                  for a in b["Ausgabestelle"]["abschnitte"]}  # fmt: skip
    assert abschnitte[""][:2] == ["Einlass", "Kasse"]
    assert "Abrechnung" in abschnitte[""] and "Kundenliste" not in abschnitte[""]
    assert "Selbstabholer" in abschnitte["Wochenübersicht"]
    assert "Alle Ausgabestellen" not in abschnitte["Verwaltung"]  # jetzt unter Einstellungen
    ausgabe = next(g for g in b["Einstellungen"]["gruppen"] if g["titel"] == "Ausgabe")
    assert [e["titel"] for e in ausgabe["eintraege"]][:2] == [
        "Ausgabestellen",
        "Ausgabestellen-Konten",
    ]
    kunden = {a["titel"]: [e["titel"] for e in a["eintraege"]] for a in b["Kunden"]["abschnitte"]}
    assert "Warteliste" in kunden["Anträge und Warteliste"]
    assert [g["titel"] for g in b["Verein"]["gruppen"]] == ["Mitglieder", "Spenden", "Adressen",
                                                            "Serienbriefe", "Team"]  # fmt: skip
    assert [e["titel"] for e in b["Auswertungen"]["eintraege"]] == [
        "Statistik",
        "Verbandsstatistik",
        "Listen",
    ]
    assert "Mein Konto" not in b  # über den Namen oben rechts
    # jede Adresse nur einmal im ganzen Menü
    urls = [e["url"] for x in b.values() for e in x["eintraege"]]
    assert len(urls) == len(set(urls))


def aktive_bereiche(benutzer, pfad):
    anfrage = RequestFactory().get(pfad)
    anfrage.user = benutzer
    return {b["titel"]: b for b in menue(anfrage)}


def test_tiefe_einstellungsseite_leuchtet_nur_in_einstellungen(admin):
    """Auf einer Einstellungsseite (z. B. „Einstellungen → Anträge“) ist nur der Einstellungs-
    Eintrag aktiv – nicht der kürzere Listen-Eintrag „Kunden → Anträge“ mit gleichem Anfang."""
    b = aktive_bereiche(admin, reverse("antraege:einstellungen"))
    assert not b["Kunden"]["offen"]
    assert b["Einstellungen"]["offen"]
    aktiv = [e["titel"] for e in b["Einstellungen"]["eintraege"] if e["aktiv"]]
    assert aktiv == ["Anträge"]


def test_noch_tiefere_seite_leuchtet_nur_in_einstellungen(admin):
    """Auch unterhalb der Einstellungsseite (Texte je Sprache) bleibt nur Einstellungen offen."""
    b = aktive_bereiche(admin, reverse("antraege:texte", args=["bg"]))
    assert not b["Kunden"]["offen"]
    assert b["Einstellungen"]["offen"]


def test_liste_leuchtet_auf_ihrer_eigenen_seite(admin):
    """Die Antragsliste selbst macht weiter den Bereich „Kunden“ auf, nicht Einstellungen."""
    b = aktive_bereiche(admin, reverse("antraege:liste"))
    assert b["Kunden"]["offen"] and not b["Einstellungen"]["offen"]


def test_dienstplaene_unter_einem_punkt(admin):
    """Fahrdienst und Dienstplan der Ausgabe stehen unter „Dienstpläne“, ihre Einstellungen
    unter „Einstellungen → Dienstpläne“."""
    b = alle_bereiche(admin, ["fahrdienst", "dienstplan"])
    assert "Fahrdienst" not in b
    teile = {
        a["titel"]: [e["titel"] for e in a["eintraege"]] for a in b["Dienstpläne"]["abschnitte"]
    }
    assert teile == {"Ausgabe": ["Dienstplan der Ausgabe", "Meine Dienste"],
                     "Fahrdienst": ["Fahrerplan", "Meine Einsätze"]}  # fmt: skip
    dp = next(g for g in b["Einstellungen"]["gruppen"] if g["titel"] == "Dienstpläne")
    assert sorted(e["titel"] for e in dp["eintraege"]) == ["Ausgabe: Aufgaben und Besetzung",
                                                     "Fahrdienst: Touren und Springer"]  # fmt: skip
    assert list(b).index("Dienstpläne") == list(b).index("Ausgabestelle") + 1


def test_ausgabe_sieht_keine_warteliste_und_stempeln_nur_wer_stempelt(benutzer_mit_rolle):
    anton = benutzer_mit_rolle("anton", rollen.AUSGABE)
    b = alle_bereiche(anton, ["warteliste", "abrechnung"])
    assert "Ausgabestelle" in b and "Meine Arbeitszeit" not in b
    alles = [e["titel"] for x in b.values() for e in x["eintraege"]]
    assert "Warteliste" not in alles and "Abrechnung" in alles


def test_name_oben_rechts_oeffnet_mein_konto(admin_client):
    seite = admin_client.get(reverse("core:start")).content.decode()
    assert f'class="angemeldet" href="{reverse("konten:mein_konto")}"' in seite
    # Bereich → Untergruppe → Einträge: Untergruppen sind zu, bis man sie wählt
    assert '<details class="menue-gruppe" name="menue-gruppe">' in seite
    assert "<summary>Kundenstamm</summary>" in seite


def test_fest_angestellte_stempeln_im_menue(benutzer_mit_rolle):
    berta = benutzer_mit_rolle("berta", rollen.AUSGABE)
    berta.beschaeftigung = berta.Beschaeftigung.FEST
    berta.save()
    assert "Meine Arbeitszeit" in alle_bereiche(berta)


def test_mitarbeitende_sammelliste_oeffnet_verein(admin):
    # /konten/mitarbeitende/ (Sammel-Liste und Detailseiten, ohne eigenen Eintrag) öffnet den
    # Bereich Verein über „Ehrenamtliche“ – sonst klappt das Menü dort komplett zu.
    anfrage = RequestFactory().get(reverse("konten:mitarbeitende"))
    anfrage.user = admin
    verein = next(b for b in menue(anfrage) if b["titel"] == "Verein")
    assert verein["offen"]
    ehren = next(e for g in verein["gruppen"] if g["titel"] == "Team"
                 for e in g["eintraege"] if e["titel"] == "Ehrenamtliche")  # fmt: skip
    assert ehren["aktiv"]


def test_spenden_zweite_ebene_heisst_spendenliste(admin):
    gruppen = titel(next(b for b in _bereiche(admin) if b["titel"] == "Verein"))
    assert "Spendenliste" in gruppen["Spenden"] and "Spenden" not in gruppen["Spenden"]


def _bereiche(benutzer):
    anfrage = RequestFactory().get("/")
    anfrage.user = benutzer
    return menue(anfrage)
