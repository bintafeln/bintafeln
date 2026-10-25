import datetime as dt
from decimal import Decimal
from pathlib import Path

import pytest
from auditlog.models import LogEntry

from apps.kunden import importieren
from apps.kunden.models import (
    Abholer,
    Abholung,
    Ausgabestelle,
    Ausnahme,
    Bemerkung,
    Einkommensart,
    Haushalt,
    ImportLauf,
    KundenEinstellungen,
    Kundengruppe,
    Person,
    Sperre,
    Zusatzfeld,
)

pytestmark = pytest.mark.django_db

HEUTE = dt.date(2026, 6, 15)
BEISPIELE = Path(__file__).resolve().parent.parent / "docs" / "beispiele" / "import"


def csv(*zeilen: str) -> bytes:
    return ("\n".join(zeilen) + "\n").encode("utf-8")


def pruefen(**dateien):
    return importieren.pruefen(
        {name.replace("_csv", ".csv"): inhalt for name, inhalt in dateien.items()}, heute=HEUTE
    )


def texte(ergebnis, stufe=None):
    return [m["text"] for m in ergebnis.bericht if stufe is None or m["stufe"] == stufe]


def uebernehmen(ergebnis, benutzer=None):
    assert ergebnis.daten is not None, ergebnis.bericht
    return importieren.uebernehmen(
        ergebnis.daten,
        benutzer=benutzer,
        dateien=ergebnis.dateien,
        pruefsumme=ergebnis.pruefsumme,
        anzahl_warnungen=len(ergebnis.warnungen),
    )


MINIMAL = csv("kundennummer;nachname;vorname", "001;Mustermann;Erika", "002;Beispiel;Max")


# --- Beispieldateien aus der Doku ----------------------------------------------------------


@pytest.fixture
def zusatzfeld_schwerbehindert():
    return Zusatzfeld.objects.create(
        schluessel="schwerbehindert",
        bezeichnung="Schwerbehindert",
        gilt_fuer=Zusatzfeld.GiltFuer.PERSON,
        typ=Zusatzfeld.Typ.JA_NEIN,
        besondere_kategorie=True,
    )


def test_beispieldateien_vollstaendig(zusatzfeld_schwerbehindert):
    einstellungen = KundenEinstellungen.laden()
    einstellungen.bemerkungen_importieren = True
    einstellungen.save()
    dateien = {p.name: p.read_bytes() for p in BEISPIELE.glob("*.csv")}
    assert len(dateien) == 8

    ergebnis = importieren.pruefen(dateien, heute=HEUTE)
    assert ergebnis.fehler == []
    # In einer leeren Installation sind die Einkommensarten noch unbekannt.
    assert set(texte(ergebnis)) == {"Einkommensart unbekannt; wird angelegt."}
    lauf = uebernehmen(ergebnis)

    assert (lauf.anzahl_haushalte, lauf.anzahl_personen) == (3, 6)
    assert (lauf.anzahl_abholer, lauf.anzahl_sperren, lauf.anzahl_bemerkungen) == (1, 1, 1)
    assert (lauf.anzahl_abholungen, lauf.anzahl_ausnahmen) == (3, 1)
    h = Haushalt.objects.get(kundennummer="1001")
    assert h.kundengruppe.kuerzel == "MO1"
    assert h.kundengruppe.ausgabestelle.name == "Ausgabestelle Mitte"
    assert h.kundengruppe.uhrzeit == dt.time(12, 30) and h.kundengruppe.maximum == 50
    assert h.einkommensart.bezeichnung == "Bürgergeld"
    assert h.kontostand == Decimal("0.00")
    assert h.ausweis_gueltig_bis == dt.date(2027, 1, 31)
    assert h.hauptperson.vorname == "Erika"
    assert h.hauptperson.zusatz == {"schwerbehindert": False}
    assert h.groesse(18, HEUTE) == (2, 1)
    assert Haushalt.objects.get(kundennummer="1002").hauptperson.zusatz == {"schwerbehindert": True}
    assert Haushalt.objects.get(kundennummer="1005").status == "pausiert"
    assert "\n" in Bemerkung.objects.get().text
    assert Sperre.objects.get().bis == dt.date(2026, 3, 31)
    abholung = Abholung.objects.filter(haushalt__kundennummer="1002").get()
    assert (abholung.datum, abholung.uhrzeit) == (dt.date(2026, 5, 12), dt.time(14, 10))
    assert abholung.beitrag == Decimal("1.50") and abholung.eingetragen_von == ""
    assert abholung.ausgabestelle.name == "Ausgabestelle Nord"
    assert Ausgabestelle.objects.count() == 2
    assert Ausnahme.objects.get().haushalt.kundennummer == "1002"
    assert ImportLauf.objects.get() == lauf
    assert str(lauf).startswith("Import vom ")


def test_import_wird_zusammengefasst_protokolliert():
    uebernehmen(pruefen(haushalte_csv=MINIMAL))
    assert not LogEntry.objects.filter(content_type__model__in=["haushalt", "person"]).exists()
    assert LogEntry.objects.filter(content_type__model="importlauf").count() == 1


# --- Minimalfall und Vollaustausch --------------------------------------------------------


def test_minimalfall_und_anzahlen():
    ergebnis = pruefen(
        haushalte_csv=csv(
            "Kundennummer;Nachname;Vorname;Anzahl_Erwachsene;Anzahl_Kinder",
            "00030;Musterfrau;Petra;1;2",
            "",
            "00031;Muster;Paul;;",
        )
    )
    assert ergebnis.bericht == []
    uebernehmen(ergebnis)
    h = Haushalt.objects.get(kundennummer="00030")
    assert h.status == "aktiv"
    assert h.groesse(18, HEUTE) == (1, 2)
    assert Haushalt.objects.count() == 2


def test_vollaustausch_ersetzt_alles():
    uebernehmen(
        pruefen(
            haushalte_csv=MINIMAL,
            sperren_csv=csv("kundennummer;von", "001;01.01.2026"),
        )
    )
    assert Sperre.objects.count() == 1
    ergebnis = pruefen(haushalte_csv=csv("kundennummer;nachname;vorname", "003;Neu;Nina"))
    assert "Datei fehlt; die bisher vorhandenen Angaben dieser Art werden entfernt." in texte(
        ergebnis, importieren.WARNUNG
    )
    uebernehmen(ergebnis)
    assert list(Haushalt.objects.values_list("kundennummer", flat=True)) == ["003"]
    assert not Sperre.objects.exists()
    assert Person.objects.count() == 1
    assert ImportLauf.objects.count() == 2


def test_bom_und_abschliessende_leerzeilen():
    ergebnis = importieren.pruefen(
        {"haushalte.csv": "﻿kundennummer;nachname;vorname\r\n1;A;B\r\n;;\r\n".encode()},
        heute=HEUTE,
    )
    assert ergebnis.bericht == []
    assert len(ergebnis.daten["haushalte"]) == 1


# --- Fehler --------------------------------------------------------------------------------


def test_haushalte_fehlt():
    ergebnis = pruefen(personen_csv=csv("kundennummer;nachname;vorname"))
    assert ergebnis.daten is None
    assert "Pflichtdatei haushalte.csv fehlt." in texte(ergebnis)


def test_unbekannte_datei_ist_warnung():
    ergebnis = pruefen(haushalte_csv=MINIMAL, notizen_txt=b"x")
    assert ergebnis.daten is not None
    assert "Unbekannte Datei wird ignoriert." in texte(ergebnis, importieren.WARNUNG)


@pytest.mark.parametrize(
    ("inhalt", "meldung"),
    [
        (b"kundennummer;nachname\n1;A\n", "Pflichtspalte „vorname“ fehlt."),
        (b"kundennummer,nachname,vorname\n1,A,B\n", "Kein Semikolon"),
        (b"", "Kein Semikolon"),
        ("kundennummer;nachname;vorname\n1;Müller;B\n".encode("latin-1"), "nicht in UTF-8"),
    ],
)
def test_formatfehler(inhalt, meldung):
    ergebnis = pruefen(haushalte_csv=inhalt)
    assert ergebnis.daten is None
    assert any(meldung in t for t in texte(ergebnis, importieren.FEHLER))


@pytest.mark.parametrize(
    ("zeilen", "meldung"),
    [
        (["1;A;B", "1;C;D"], "Kundennummer kommt doppelt vor."),
        (["1;;B"], "Pflichtangabe „nachname“ ist leer."),
        (["x" * 21 + ";A;B"], "„kundennummer“ ist zu lang (höchstens 20 Zeichen)."),
    ],
)
def test_fehler_in_haushalten(zeilen, meldung):
    ergebnis = pruefen(haushalte_csv=csv("kundennummer;nachname;vorname", *zeilen))
    assert ergebnis.daten is None
    assert meldung in texte(ergebnis, importieren.FEHLER)
    fehler = ergebnis.fehler[0]
    assert fehler["datei"] == "haushalte.csv" and fehler["zeile"] >= 2


def test_unbekannter_status():
    ergebnis = pruefen(haushalte_csv=csv("kundennummer;nachname;vorname;status", "1;A;B;weg"))
    assert "Unbekannter Status." in texte(ergebnis, importieren.FEHLER)


def test_zuordnung_zu_unbekanntem_haushalt():
    ergebnis = pruefen(
        haushalte_csv=MINIMAL,
        personen_csv=csv("kundennummer;nachname;vorname;geburtsdatum", "999;A;B;01.01.2010"),
        abholer_csv=csv("kundennummer;nachname;vorname", "998;A;B"),
    )
    assert (
        texte(ergebnis, importieren.FEHLER).count("Kundennummer gibt es nicht in haushalte.csv.")
        == 2
    )


@pytest.mark.parametrize(
    ("zeile", "meldung"),
    [
        ("001;31.02.2026;", "„von“ ist kein gültiges Datum."),
        ("001;;", "Pflichtangabe „von“ ist leer."),
        ("001;10.03.2026;01.03.2026", "„bis“ liegt vor „von“."),
    ],
)
def test_sperren_fehler(zeile, meldung):
    ergebnis = pruefen(haushalte_csv=MINIMAL, sperren_csv=csv("kundennummer;von;bis", zeile))
    assert meldung in texte(ergebnis, importieren.FEHLER)


def test_kundengruppen_doppelt():
    ergebnis = pruefen(
        haushalte_csv=MINIMAL,
        kundengruppen_csv=csv("kuerzel;name;ausgabestelle", "A1;Montag;Mitte", "a1;montag;Mitte"),
    )
    assert "Kürzel kommt doppelt vor." in texte(ergebnis)
    assert "Name kommt doppelt vor." in texte(ergebnis)


def test_kundengruppe_name_bei_anderem_kuerzel():
    Kundengruppe.objects.create(kuerzel="B1", name="Montag")
    ergebnis = pruefen(
        haushalte_csv=MINIMAL,
        kundengruppen_csv=csv("kuerzel;name;ausgabestelle", "A1;Montag;Mitte"),
    )
    assert "Name ist bereits einer Kundengruppe mit anderem Kürzel zugeordnet." in texte(ergebnis)


# --- Warnungen -----------------------------------------------------------------------------


def test_warnungen_haushalte():
    Zusatzfeld.objects.create(
        schluessel="essen",
        bezeichnung="Essen",
        gilt_fuer="haushalt",
        typ="auswahl",
        optionen="vegetarisch\nkeine Einschränkung",
    )
    Zusatzfeld.objects.create(schluessel="alt", bezeichnung="Alt", aktiv=False)
    kopf = (
        "kundennummer;nachname;vorname;geburtsdatum;telefon;email;kontostand;"
        "ausweis_gueltig_bis;kunde_seit;einkommensart;kundengruppe;ausgabestelle;"
        "anzahl_kinder;zusatz_essen;zusatz_alt;zusatz_fehlt;sonstwas"
    )
    ergebnis = pruefen(
        haushalte_csv=csv(
            kopf,
            "1;A;B;01.01.2030;201234;kaputt;zehn;01.01.2026;gestern;Rente;Neu Mo;Nord;"
            "zwei;halal;x;y;z",
            "2;C;D;01.01.1900;0201;c@example.org;1,50;;;rente;neu mo;;1;VEGETARISCH;;;;zuviel",
        )
    )
    assert ergebnis.fehler == []
    w = texte(ergebnis, importieren.WARNUNG)
    for erwartet in [
        "Unbekannte Spalte „sonstwas“ wird ignoriert.",
        "Zusatzfeld „zusatz_alt“ ist inaktiv und wird ignoriert.",
        "Zu „zusatz_fehlt“ ist kein Zusatzfeld angelegt; Spalte wird ignoriert.",
        "Geburtsdatum unplausibel, bleibt leer.",
        "Telefonnummer beginnt nicht mit 0 oder + (führende 0 verloren?).",
        "E-Mail-Adresse ungültig, bleibt leer.",
        "„kontostand“ ist kein Betrag, bleibt leer.",
        "Ausweis ist abgelaufen.",
        "„kunde_seit“ ist kein gültiges Datum, bleibt leer.",
        "Einkommensart unbekannt; wird angelegt.",
        "Kundengruppe unbekannt; wird mit dem angegebenen Namen angelegt.",
        "„anzahl_kinder“ ist keine ganze Zahl, bleibt leer.",
        "Wert für „zusatz_essen“ passt nicht, bleibt leer.",
        "Mehr Werte als Spalten; überzählige ignoriert.",
    ]:
        assert erwartet in w, erwartet
    # gleiche Einkommensart / Gruppe nur einmal gemeldet
    assert w.count("Einkommensart unbekannt; wird angelegt.") == 1
    assert w.count("Kundengruppe unbekannt; wird mit dem angegebenen Namen angelegt.") == 1

    uebernehmen(ergebnis)
    eins, zwei = Haushalt.objects.order_by("kundennummer")
    assert eins.hauptperson.geburtsdatum is None and eins.email == "" and eins.kontostand is None
    assert eins.telefon == "201234"
    assert eins.zusatz == {}
    assert zwei.zusatz == {"essen": "vegetarisch"}
    assert zwei.kontostand == Decimal("1.50") and zwei.anzahl_kinder == 1
    assert eins.kundengruppe == zwei.kundengruppe
    assert eins.kundengruppe.name == "Neu Mo" and eins.kundengruppe.ausgabestelle.name == "Nord"
    assert Einkommensart.objects.count() == 1


def test_abgeschaltete_felder_werden_nicht_gespeichert():
    e = KundenEinstellungen.laden()
    e.telefon_erfassen = e.email_erfassen = e.staatsangehoerigkeit_erfassen = False
    e.familienstand_erfassen = False
    e.save()
    ergebnis = pruefen(
        haushalte_csv=csv(
            "kundennummer;nachname;vorname;telefon;email;staatsangehoerigkeit;familienstand",
            "1;A;B;0201;a@example.org;deutsch;ledig",
        ),
        personen_csv=csv(
            "kundennummer;nachname;vorname;geburtsdatum;staatsangehoerigkeit",
            "1;A;C;01.01.2010;deutsch",
        ),
    )
    w = texte(ergebnis, importieren.WARNUNG)
    assert sum("abgeschaltet" in t for t in w) == 5
    uebernehmen(ergebnis)
    h = Haushalt.objects.get()
    assert (h.telefon, h.email) == ("", "")
    assert set(Person.objects.values_list("staatsangehoerigkeit", flat=True)) == {""}
    assert h.hauptperson.familienstand == ""


def test_bemerkungen_nur_wenn_eingeschaltet():
    bemerkungen = csv("kundennummer;datum;text", "001;01.01.2026;Erfunden")
    ergebnis = pruefen(haushalte_csv=MINIMAL, bemerkungen_csv=bemerkungen)
    assert any("Anmerkungen ist in den Einstellungen abgeschaltet" in t for t in texte(ergebnis))
    uebernehmen(ergebnis)
    assert not Bemerkung.objects.exists()

    e = KundenEinstellungen.laden()
    e.bemerkungen_importieren = True
    e.save()
    uebernehmen(pruefen(haushalte_csv=MINIMAL, bemerkungen_csv=bemerkungen))
    assert Bemerkung.objects.count() == 1
    # Fehlt die Datei beim nächsten Mal, gibt es einen Hinweis
    assert any("Datei fehlt" in t for t in texte(pruefen(haushalte_csv=MINIMAL)))


def test_personen_warnungen_und_zusatz_geltung():
    Zusatzfeld.objects.create(
        schluessel="essen", bezeichnung="Essen", gilt_fuer="haushalt", typ="text"
    )
    Zusatzfeld.objects.create(schluessel="sb", bezeichnung="SB", gilt_fuer="person", typ="ja_nein")
    ergebnis = pruefen(
        haushalte_csv=csv(
            "kundennummer;nachname;vorname;anzahl_erwachsene;zusatz_sb", "001;A;B;2;ja"
        ),
        personen_csv=csv("kundennummer;nachname;vorname;zusatz_essen;zusatz_sb", "001;A;C;x;nein"),
    )
    w = texte(ergebnis, importieren.WARNUNG)
    assert "Angehörige Person ohne Geburtsdatum." in w
    assert "Zusatzfeld „zusatz_essen“ gilt für Haushalte und wird hier ignoriert." in w
    assert "Anzahl Erwachsene/Kinder wird ignoriert, weil personen.csv geliefert wurde." in w
    uebernehmen(ergebnis)
    h = Haushalt.objects.get()
    assert h.anzahl_erwachsene is None
    assert h.hauptperson.zusatz == {"sb": True}
    assert Person.objects.get(ist_hauptperson=False).zusatz == {"sb": False}


def test_kundengruppen_warnungen_und_platzhalter():
    platzhalter = Kundengruppe.objects.create(name="Montag")
    ergebnis = pruefen(
        haushalte_csv=csv(
            "kundennummer;nachname;vorname;kundengruppe", "001;A;B;montag", "002;C;D;a1"
        ),
        kundengruppen_csv=csv(
            "kuerzel;name;ausgabestelle;wochentage;uhrzeit;maximum;aktiv",
            "A1;Montag;Mitte;Mo,Xy;25:00;viele;vielleicht",
        ),
    )
    w = texte(ergebnis, importieren.WARNUNG)
    assert "Unbekannter Wochentag, Angabe bleibt leer." in w
    assert "„uhrzeit“ ist keine Uhrzeit, bleibt leer." in w
    assert "„maximum“ ist keine ganze Zahl, bleibt leer." in w
    assert "„aktiv“ ist kein Ja/Nein-Wert, gilt als ja." in w
    uebernehmen(ergebnis)
    # Der Platzhalter mit gleichem Namen wird übernommen und bekommt sein Kürzel.
    gruppe = Kundengruppe.objects.get()
    assert gruppe.pk == platzhalter.pk
    assert gruppe.kuerzel == "A1" and gruppe.aktiv and gruppe.uhrzeit is None
    assert set(Haushalt.objects.values_list("kundengruppe", flat=True)) == {gruppe.pk}


def test_bestehende_gruppe_nach_kuerzel_aktualisiert():
    stelle = Ausgabestelle.objects.create(name="Alt")
    gruppe = Kundengruppe.objects.create(kuerzel="A1", name="Alt", ausgabestelle=stelle)
    uebernehmen(
        pruefen(
            haushalte_csv=csv("kundennummer;nachname;vorname;kundengruppe", "001;A;B;Alt"),
            kundengruppen_csv=csv("kuerzel;name;ausgabestelle;wochentage", "a1;Neu;Mitte;di, do"),
        )
    )
    gruppe.refresh_from_db()
    assert (gruppe.kuerzel, gruppe.name, gruppe.wochentage) == ("a1", "Neu", "Di,Do")
    assert gruppe.ausgabestelle.name == "Mitte"
    assert Haushalt.objects.get().kundengruppe == gruppe


def test_vorhandene_gruppe_ohne_csv_wird_gefunden():
    gruppe = Kundengruppe.objects.create(kuerzel="W11", name="Zentrale Mo 12:30")
    ergebnis = pruefen(
        haushalte_csv=csv(
            "kundennummer;nachname;vorname;kundengruppe", "1;A;B;w11", "2;C;D;Zentrale Mo 12:30"
        )
    )
    assert ergebnis.warnungen == []
    uebernehmen(ergebnis)
    assert set(Haushalt.objects.values_list("kundengruppe", flat=True)) == {gruppe.pk}
    # bereits vorhandene Gruppe aus neuer_gruppe wird nicht doppelt angelegt
    importieren.uebernehmen(
        {**ergebnis.daten, "neue_gruppen": [{"name": "zentrale mo 12:30", "ausgabestelle": ""}]},
        benutzer=None,
        dateien=[],
        pruefsumme="",
        anzahl_warnungen=0,
    )
    assert Kundengruppe.objects.count() == 1


def test_abholer_und_ungueltiges_optionales_datum():
    ergebnis = pruefen(
        haushalte_csv=MINIMAL,
        abholer_csv=csv(
            "kundennummer;nachname;vorname;geburtsdatum;eigene_kundennummer",
            "001;Abhol;Lena;kein;002",
        ),
        sperren_csv=csv("kundennummer;von;bis", "001;01.01.2026;irgendwann"),
    )
    assert "„geburtsdatum“ ist kein gültiges Datum, bleibt leer." in texte(ergebnis)
    assert "„bis“ ist kein gültiges Datum, bleibt leer." in texte(ergebnis)
    uebernehmen(ergebnis)
    assert Abholer.objects.get().eigene_kundennummer == "002"
    assert Sperre.objects.get().bis is None


def test_pruefsumme_haengt_vom_inhalt_ab():
    a = pruefen(haushalte_csv=MINIMAL)
    b = pruefen(haushalte_csv=MINIMAL)
    c = pruefen(haushalte_csv=MINIMAL + b"003;X;Y\n")
    assert a.pruefsumme == b.pruefsumme != c.pruefsumme


def test_bericht_gruppiert():
    bericht = [
        {"stufe": "warnung", "datei": "haushalte.csv", "zeile": n, "text": "W"}
        for n in range(2, 22)
    ] + [{"stufe": "fehler", "datei": "personen.csv", "zeile": None, "text": "F"}]
    gruppen = importieren.bericht_gruppiert(bericht)
    assert gruppen[0]["stufe"] == "fehler" and gruppen[0]["anzahl"] == 1
    assert gruppen[1]["anzahl"] == 20
    assert gruppen[1]["zeilen_kurz"].endswith("… (+5)")


def test_neue_gruppe_ohne_ausgabestelle_und_gemeinsame_stelle():
    uebernehmen(
        pruefen(
            haushalte_csv=csv("kundennummer;nachname;vorname;kundengruppe", "1;A;B;Freitag"),
            kundengruppen_csv=csv(
                "kuerzel;name;ausgabestelle", "M1;Montag;Mitte", "D1;Dienstag;mitte"
            ),
        )
    )
    assert Kundengruppe.objects.get(name="Freitag").ausgabestelle is None
    assert Ausgabestelle.objects.count() == 1
    assert Kundengruppe.objects.filter(ausgabestelle__name="Mitte").count() == 2


# --- Abholungen und Ausnahmen ------------------------------------------------------------


def test_abholungen_frist_und_warnungen():
    ergebnis = pruefen(
        haushalte_csv=MINIMAL,
        abholungen_csv=csv(
            "kundennummer;datum;uhrzeit;beitrag;ausgabestelle;eingetragen_von",
            "001;15.06.2023;10:00;1;;",  # genau am Fristbeginn: bleibt
            "001;14.06.2023;10:00;1;;",  # einen Tag älter: entfällt
            "001;01.06.2026;25:00;viel;Neue Stelle;",
            "002;02.06.2026;;;neue stelle;",
        ),
        ausnahmen_csv=csv(
            "kundennummer;datum;begruendung",
            "002;01.01.2020;alt",
            "002;03.06.2026;",
        ),
    )
    assert ergebnis.fehler == []
    assert texte(ergebnis) == [
        "Älter als die Aufbewahrungsfrist; wird nicht übernommen.",
        "Ausgabestelle unbekannt; wird angelegt.",
        "„beitrag“ ist kein Betrag, bleibt leer.",
        "„uhrzeit“ ist keine Uhrzeit, bleibt leer.",
        "Älter als die Aufbewahrungsfrist; wird nicht übernommen.",
    ]
    lauf = uebernehmen(ergebnis)
    assert (lauf.anzahl_abholungen, lauf.anzahl_ausnahmen) == (3, 1)
    neu = Abholung.objects.filter(datum=dt.date(2026, 6, 1)).get()
    assert neu.uhrzeit is None and neu.beitrag is None
    assert Ausgabestelle.objects.get().name == "Neue Stelle"
    assert Abholung.objects.filter(ausgabestelle__isnull=False).count() == 2


@pytest.mark.parametrize("datei", ["abholungen_csv", "ausnahmen_csv"])
def test_abholdaten_fehler(datei):
    ergebnis = pruefen(
        haushalte_csv=MINIMAL,
        **{datei: csv("kundennummer;datum", "001;", "001;gestern", "999;01.06.2026")},
    )
    assert ergebnis.daten is None
    assert texte(ergebnis, importieren.FEHLER) == [
        "Kundennummer gibt es nicht in haushalte.csv.",
        "Pflichtangabe „datum“ ist leer.",
        "„datum“ ist kein gültiges Datum.",
    ]


def test_frist_aus_einstellungen_und_fehlende_datei_warnt():
    e = KundenEinstellungen.laden()
    e.abholungen_aufbewahren_jahre = 1
    e.save()
    abholungen = csv("kundennummer;datum", "001;01.06.2025", "001;01.06.2026")
    uebernehmen(pruefen(haushalte_csv=MINIMAL, abholungen_csv=abholungen))
    assert list(Abholung.objects.values_list("datum", flat=True)) == [dt.date(2026, 6, 1)]

    ergebnis = pruefen(haushalte_csv=MINIMAL)
    assert texte(ergebnis) == [
        "Datei fehlt; die bisher vorhandenen Angaben dieser Art werden entfernt."
    ]
    uebernehmen(ergebnis)
    assert not Abholung.objects.exists()


def test_vorbereitung_aus_aelterer_version_ohne_abholdaten():
    ergebnis = pruefen(haushalte_csv=MINIMAL)
    del ergebnis.daten["abholungen"], ergebnis.daten["ausnahmen"]
    lauf = uebernehmen(ergebnis)
    assert (lauf.anzahl_haushalte, lauf.anzahl_abholungen) == (2, 0)


def test_leere_wochentage_im_import_ueberschreiben_eingetragene_nicht():
    gruppe = Kundengruppe.objects.create(kuerzel="W5", name="Zentrale Fr 13:30", wochentage="Fr")
    uebernehmen(
        pruefen(
            haushalte_csv=csv("kundennummer;nachname;vorname;kundengruppe", "001;A;B;W5"),
            kundengruppen_csv=csv(
                "kuerzel;name;ausgabestelle;wochentage", "W5;Zentrale Fr 13:30;Mitte;"
            ),
        )
    )
    gruppe.refresh_from_db()
    assert gruppe.wochentage == "Fr"
